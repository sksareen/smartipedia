"""Server-side traffic attribution.

Google Analytics and Umami can only see visitors that execute JavaScript, which
means they are structurally blind to Smartipedia's primary audience: AI agents
hitting /api and /mcp. Everything here runs server-side so the stats page can
answer "who is actually using this" for humans, agents, and crawlers alike.

Classification is user-agent based, so it is a strong hint rather than proof —
a client can claim to be anything. It is still the only signal available, and
the declared AI crawlers (GPTBot, ClaudeBot, PerplexityBot) are honest about
who they are.
"""

import hashlib
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import func as sqlfunc
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import RequestLog

# Buckets, most specific first. Order matters: "GPTBot" also matches /bot/, so
# the AI patterns have to be tested before the generic crawler ones.
_AI_AGENT = [
    ("GPTBot", r"gptbot"),
    ("ChatGPT-User", r"chatgpt-user"),
    ("OAI-SearchBot", r"oai-searchbot"),
    ("ClaudeBot", r"claudebot|claude-web|anthropic-ai"),
    ("Claude-User", r"claude-user|claude-searchbot"),
    ("Claude Code", r"claude-code|claude-cli"),
    ("PerplexityBot", r"perplexitybot|perplexity-user"),
    ("Google-Extended", r"google-extended"),
    ("Gemini", r"gemini|google-cloudvertexbot"),
    ("Meta-ExternalAgent", r"meta-externalagent|meta-externalfetcher"),
    ("Applebot-Extended", r"applebot-extended"),
    ("Bytespider", r"bytespider"),
    ("CCBot", r"ccbot"),
    ("Cohere", r"cohere-ai|cohere-training-data-crawler"),
    ("MistralAI", r"mistralai"),
    ("DuckAssistBot", r"duckassistbot"),
    ("YouBot", r"youbot"),
    ("Diffbot", r"diffbot"),
    ("AI2Bot", r"ai2bot"),
    ("Timpibot", r"timpibot"),
    ("Firecrawl", r"firecrawl"),
    ("MCP client", r"modelcontextprotocol|mcp-client|mcp-remote"),
]

_API_CLIENT = [
    ("python-httpx", r"python-httpx"),
    ("python-requests", r"python-requests"),
    ("aiohttp", r"aiohttp"),
    ("openai-python", r"openai-python"),
    ("anthropic-sdk", r"anthropic-python|anthropic-sdk|anthropic-typescript"),
    ("curl", r"^curl/"),
    ("wget", r"^wget/"),
    ("node-fetch", r"node-fetch|undici"),
    ("axios", r"axios"),
    ("Go-http-client", r"go-http-client"),
    ("okhttp", r"okhttp"),
    ("Java", r"^java/|apache-httpclient"),
    ("Ruby", r"ruby|faraday"),
    ("PowerShell", r"powershell|winhttp"),
    ("n8n", r"n8n"),
    ("Postman", r"postman"),
]

_CRAWLER = [
    ("Googlebot", r"googlebot|google-inspectiontool|storebot-google|adsbot-google"),
    ("Bingbot", r"bingbot|adidxbot|msnbot"),
    ("Applebot", r"applebot"),
    ("DuckDuckBot", r"duckduckbot|duckduckgo"),
    ("YandexBot", r"yandex"),
    ("Baiduspider", r"baiduspider"),
    ("Sogou", r"sogou"),
    ("Facebook", r"facebookexternalhit|facebookbot|facebookcatalog"),
    ("Twitterbot", r"twitterbot"),
    ("Slackbot", r"slackbot|slack-imgproxy"),
    ("Discordbot", r"discordbot"),
    ("LinkedInBot", r"linkedinbot"),
    ("TelegramBot", r"telegrambot"),
    ("WhatsApp", r"whatsapp"),
    ("Ahrefs", r"ahrefsbot"),
    ("Semrush", r"semrushbot"),
    ("MJ12bot", r"mj12bot"),
    ("DotBot", r"dotbot"),
    ("PetalBot", r"petalbot"),
    ("Amazonbot", r"amazonbot"),
    ("SeznamBot", r"seznambot"),
    ("Bytedance", r"toutiaospider"),
    ("Archive.org", r"ia_archiver|archive\.org_bot"),
    ("UptimeRobot", r"uptimerobot|pingdom|statuscake|betteruptime"),
    ("Scrapy", r"scrapy|headlesschrome|phantomjs|puppeteer|playwright"),
    # "…Bot/1.0" is the common shape, so match a trailing delimiter too.
    ("Other bot", r"bot[/\s;)]|\bbot\b|crawler|spider|crawl|scraper|monitoring"),
]

# Browsers last: nearly every bot also embeds "Mozilla/5.0", so a UA only counts
# as human once it has failed every pattern above.
_BROWSER = [
    ("Edge", r"edg/|edge/"),
    ("Opera", r"opr/|opera"),
    ("Samsung Internet", r"samsungbrowser"),
    ("Firefox", r"firefox/|fxios"),
    ("Chrome", r"chrome/|crios"),
    ("Safari", r"safari/"),
]

_COMPILED = [
    (bucket, family, re.compile(pattern))
    for bucket, table in (
        ("ai_agent", _AI_AGENT),
        ("api_client", _API_CLIENT),
        ("crawler", _CRAWLER),
        ("human", _BROWSER),
    )
    for family, pattern in table
]

CLIENT_TYPES = ("human", "ai_agent", "api_client", "crawler", "unknown")


def classify(user_agent: str | None) -> tuple[str, str]:
    """Map a user-agent string to (client_type, ua_family)."""
    if not user_agent:
        return "unknown", "none"
    ua = user_agent.lower()
    for bucket, family, pattern in _COMPILED:
        if pattern.search(ua):
            return bucket, family
    return "unknown", "other"


def surface_for(path: str) -> str:
    """Which entry point a request came through."""
    if path.startswith("/mcp"):
        return "mcp"
    if path.startswith("/api"):
        return "api"
    return "web"


def hash_ip(ip: str | None) -> str:
    """Salted, truncated hash — enough to count uniques, not to identify anyone."""
    if not ip:
        return ""
    salted = f"{settings.session_secret}:{ip}".encode()
    return hashlib.sha256(salted).hexdigest()[:32]


# ==================== QUERIES ====================

def _cutoff(days: int) -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)


async def get_traffic_overview(db: AsyncSession, days: int = 7) -> dict:
    """Request counts and unique clients broken down by who sent them."""
    since = _cutoff(days)

    by_type = (await db.execute(
        select(
            RequestLog.client_type,
            sqlfunc.count(RequestLog.id).label("requests"),
            sqlfunc.count(sqlfunc.distinct(RequestLog.ip_hash)).label("uniques"),
        )
        .where(RequestLog.created_at >= since)
        .group_by(RequestLog.client_type)
        .order_by(sqlfunc.count(RequestLog.id).desc())
    )).all()

    by_surface = (await db.execute(
        select(
            RequestLog.surface,
            RequestLog.client_type,
            sqlfunc.count(RequestLog.id).label("requests"),
        )
        .where(RequestLog.created_at >= since)
        .group_by(RequestLog.surface, RequestLog.client_type)
    )).all()

    total = sum(row.requests for row in by_type)
    surfaces: dict[str, dict] = {}
    for row in by_surface:
        entry = surfaces.setdefault(row.surface, {"total": 0})
        entry[row.client_type] = row.requests
        entry["total"] += row.requests

    return {
        "days": days,
        "total_requests": total,
        "by_client_type": [
            {
                "client_type": row.client_type,
                "requests": row.requests,
                "uniques": row.uniques,
                "share": round(row.requests / max(total, 1) * 100, 1),
            }
            for row in by_type
        ],
        "by_surface": surfaces,
    }


async def get_top_clients(db: AsyncSession, days: int = 7, limit: int = 15) -> list[dict]:
    """Busiest user-agent families."""
    since = _cutoff(days)
    result = await db.execute(
        select(
            RequestLog.ua_family,
            RequestLog.client_type,
            sqlfunc.count(RequestLog.id).label("requests"),
            sqlfunc.count(sqlfunc.distinct(RequestLog.ip_hash)).label("uniques"),
            sqlfunc.max(RequestLog.created_at).label("last_seen"),
        )
        .where(RequestLog.created_at >= since)
        .group_by(RequestLog.ua_family, RequestLog.client_type)
        .order_by(sqlfunc.count(RequestLog.id).desc())
        .limit(limit)
    )
    return [
        {
            "ua_family": row.ua_family,
            "client_type": row.client_type,
            "requests": row.requests,
            "uniques": row.uniques,
            "last_seen": row.last_seen.isoformat() if row.last_seen else None,
        }
        for row in result
    ]


async def get_traffic_timeseries(db: AsyncSession, days: int = 14) -> list[dict]:
    """Daily request counts per client type, oldest first."""
    since = _cutoff(days)
    result = await db.execute(
        select(
            sqlfunc.date_trunc("day", RequestLog.created_at).label("day"),
            RequestLog.client_type,
            sqlfunc.count(RequestLog.id).label("requests"),
        )
        .where(RequestLog.created_at >= since)
        .group_by("day", RequestLog.client_type)
        .order_by("day")
    )
    days_map: dict[str, dict] = {}
    for row in result:
        key = row.day.date().isoformat()
        entry = days_map.setdefault(key, {"day": key, "total": 0})
        entry[row.client_type] = row.requests
        entry["total"] += row.requests
    return list(days_map.values())


async def get_top_paths(db: AsyncSession, days: int = 7, limit: int = 15,
                        client_type: str | None = None) -> list[dict]:
    """Most-requested paths, optionally for one audience."""
    stmt = (
        select(
            RequestLog.path,
            sqlfunc.count(RequestLog.id).label("requests"),
        )
        .where(RequestLog.created_at >= _cutoff(days))
    )
    if client_type:
        stmt = stmt.where(RequestLog.client_type == client_type)
    result = await db.execute(
        stmt.group_by(RequestLog.path)
        .order_by(sqlfunc.count(RequestLog.id).desc())
        .limit(limit)
    )
    return [{"path": row.path, "requests": row.requests} for row in result]


async def get_referrers(db: AsyncSession, days: int = 30, limit: int = 15) -> list[dict]:
    """Where human visitors came from."""
    since = _cutoff(days)
    result = await db.execute(
        select(
            RequestLog.referrer,
            sqlfunc.count(RequestLog.id).label("visits"),
        )
        .where(
            RequestLog.created_at >= since,
            RequestLog.client_type == "human",
            RequestLog.referrer.isnot(None),
            RequestLog.referrer != "",
        )
        .group_by(RequestLog.referrer)
        .order_by(sqlfunc.count(RequestLog.id).desc())
        .limit(limit)
    )
    return [{"referrer": row.referrer, "visits": row.visits} for row in result]
