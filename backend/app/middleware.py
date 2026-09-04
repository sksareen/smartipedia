"""Request logging middleware.

Classifies every request and buffers it in memory, flushing to Postgres on a
timer. Buffering matters because crawler traffic dominates — a synchronous
INSERT per request would roughly double the database write load for data nobody
reads in real time.

Written as raw ASGI rather than BaseHTTPMiddleware on purpose: BaseHTTPMiddleware
consumes the response body to re-emit it, which stalls the SSE stream the MCP
server mounted at /mcp depends on.

The buffer is per-process, which is fine while prod runs uvicorn --workers 1.
With more workers each keeps its own buffer and flushes independently; the rows
still land in the same table.
"""

import asyncio
import contextlib
import logging
import time

from starlette.datastructures import Headers

from .database import async_session
from .models import RequestLog
from .services.traffic import classify, hash_ip, surface_for

log = logging.getLogger(__name__)

FLUSH_INTERVAL_SECONDS = 5
BUFFER_LIMIT = 200

# Assets and probes: high volume, zero attribution value.
SKIP_PREFIXES = ("/static", "/favicon", "/apple-touch-icon", "/health")

_buffer: list[dict] = []


def _truncate(value: str | None, length: int) -> str | None:
    return value[:length] if value is not None else None


def _client_ip(scope, headers: Headers) -> str | None:
    """Real client IP, accounting for the Caddy reverse proxy in front of us."""
    forwarded = headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = scope.get("client")
    return client[0] if client else None


class TrafficLoggerMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path.startswith(SKIP_PREFIXES):
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        user_agent = headers.get("user-agent")
        client_type, ua_family = classify(user_agent)

        # Route handlers read request.state.client_type to decide whether a hit
        # counts as a human view.
        scope.setdefault("state", {})
        scope["state"]["client_type"] = client_type
        scope["state"]["ua_family"] = ua_family

        status_code = 500

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        started = time.perf_counter()
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            _buffer.append({
                "path": _truncate(path, 512),
                "method": scope.get("method", "GET")[:8],
                "status_code": status_code,
                "surface": surface_for(path),
                "client_type": client_type,
                "ua_family": _truncate(ua_family, 64),
                "user_agent": _truncate(user_agent, 512),
                "ip_hash": hash_ip(_client_ip(scope, headers)),
                "referrer": _truncate(headers.get("referer"), 512),
                "duration_ms": int((time.perf_counter() - started) * 1000),
            })
            # Safe to await here — the response has already been sent.
            if len(_buffer) >= BUFFER_LIMIT:
                await flush()


async def flush() -> int:
    """Write buffered rows. Never raises — analytics must not break the site."""
    if not _buffer:
        return 0
    batch, _buffer[:] = _buffer[:], []
    try:
        async with async_session() as db:
            db.add_all([RequestLog(**row) for row in batch])
            await db.commit()
        return len(batch)
    except Exception:
        log.exception("request log flush failed, dropping %d rows", len(batch))
        return 0


async def _flush_loop() -> None:
    while True:
        try:
            await asyncio.sleep(FLUSH_INTERVAL_SECONDS)
            await flush()
        except asyncio.CancelledError:
            await flush()
            raise
        except Exception:
            log.exception("request log flush loop error")


@contextlib.asynccontextmanager
async def traffic_flusher():
    """Runs the periodic flush for the lifetime of the app."""
    task = asyncio.create_task(_flush_loop())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
