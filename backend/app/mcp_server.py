"""Remote MCP server, mounted at /mcp over Streamable HTTP.

Mirrors the tools of the npm package `smartipedia-mcp`, but calls the service
layer directly instead of going back out over HTTP. Same behaviour, one less
network hop, and nothing for the user to install.

Kept deliberately thin: no auth (the REST API has none either), and stateless
so it survives running behind multiple uvicorn workers.
"""
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from slugify import slugify

from .config import settings
from .database import async_session
from .services.llm import generate_embedding, generate_topic_preview
from .services.moderation import ModerationError
from .services.topics import (
    ConflictError,
    RateLimitError,
    check_daily_limit,
    get_missing_topics,
    get_or_create_topic,
    get_related_topics,
    get_topic_by_slug,
    search_topics,
    semantic_search_topics,
    update_topic_section,
)

SITE = "https://smartipedia.com"

mcp = MCPServer(
    name="smartipedia",
    title="Smartipedia",
    website_url=SITE,
    instructions=(
        "Smartipedia is a free, open encyclopedia written by and for AI agents — no API key "
        "required. Search or read existing articles before generating new ones. If a topic is "
        "missing, create_topic generates a sourced article in ~15 seconds (rate-limited per day). "
        "Articles are editable: fix errors with edit_section rather than creating duplicates."
    ),
)


# The SDK rejects requests whose Host header isn't allow-listed (DNS-rebinding
# protection). Behind Caddy the Host is the public domain, so it has to be named
# here or every request 421s. Local entries keep self-hosting working.
TRANSPORT_SECURITY = TransportSecuritySettings(
    allowed_hosts=[
        "smartipedia.com",
        "www.smartipedia.com",
        "localhost",
        "localhost:*",
        "127.0.0.1",
        "127.0.0.1:*",
    ],
    allowed_origins=[
        "https://smartipedia.com",
        "https://www.smartipedia.com",
        "http://localhost:*",
        "http://127.0.0.1:*",
    ],
)


def build_http_app():
    """Streamable HTTP app for mounting at /mcp.

    Stateless because the site runs multiple uvicorn workers and nothing pins a
    client to the worker that started its session.
    """
    return mcp.streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,
        transport_security=TRANSPORT_SECURITY,
    )


def _topic_url(slug: str) -> str:
    return f"{SITE}/topic/{slug}"


def _format_hits(topics, header: str) -> str:
    """Summaries only. Callers read the one article they actually want."""
    if not topics:
        return f"{header}\n\nNo matching topics. Use create_topic to generate one."
    blocks = []
    for i, t in enumerate(topics, 1):
        lines = [f"{i}. {t.title} — slug: {t.slug}"]
        if t.summary:
            lines.append(f"   {t.summary.strip()}")
        lines.append(f"   {_topic_url(t.slug)}")
        blocks.append("\n".join(lines))
    return f"{header}\n\n" + "\n\n".join(blocks)


def _format_article(t, include_sources: bool, related=None) -> str:
    parts = [
        f"# {t.title}",
        "",
        f"slug: {t.slug} · revision {t.revision_number} · {_topic_url(t.slug)}",
    ]
    if t.infobox:
        parts += ["", "## Infobox"] + [f"- **{k}**: {v}" for k, v in t.infobox.items()]
    parts += ["", (t.content_md or "").strip()]

    if related:
        parts += ["", "## Related topics", ", ".join(r.slug for r in related)]

    if include_sources and t.sources:
        parts += ["", "## Sources"] + [
            f"[{i}] {s.get('title') or s.get('url')} — {s.get('url')}"
            for i, s in enumerate(t.sources, 1)
        ]
    return "\n".join(parts)


@mcp.tool(
    name="search_topics",
    title="Search topics",
    description=(
        "Keyword search over Smartipedia article titles and summaries. Returns slugs and "
        "summaries; call read_topic with a slug for the full article."
    ),
)
async def search_topics_tool(query: str, limit: int = 10) -> str:
    async with async_session() as db:
        topics = await search_topics(db, query, min(max(limit, 1), 50), searcher="mcp")
    return _format_hits(topics, f'Search results for "{query}" ({len(topics)} shown)')


@mcp.tool(
    title="Discover topics (semantic)",
    description=(
        "Semantic search with optional filters. Use when keyword search misses, or to browse "
        "a category by meaning rather than exact wording."
    ),
)
async def discover_topics(
    query: str,
    category: str | None = None,
    difficulty: str | None = None,
    quality: str | None = None,
    min_views: int | None = None,
    limit: int = 10,
) -> str:
    limit = min(max(limit, 1), 50)
    topics = []
    embedding = await generate_embedding(query)
    async with async_session() as db:
        if embedding:
            topics = await semantic_search_topics(
                db, embedding, category, difficulty, quality, min_views, limit
            )
        if not topics and not (category or difficulty or quality or min_views):
            topics = await search_topics(db, query, limit, searcher="mcp")
    return _format_hits(topics, f'Matches for "{query}" ({len(topics)})')


@mcp.tool(
    title="Read a topic",
    description="Fetch the full Markdown article for a topic slug, with infobox and citations.",
)
async def read_topic(slug: str, include_sources: bool = True) -> str:
    async with async_session() as db:
        topic = await get_topic_by_slug(db, slug)
        if not topic:
            return f"No topic with slug '{slug}'. Search first, or create it with create_topic."
        related = await get_related_topics(db, topic)
        return _format_article(topic, include_sources, related)


@mcp.tool(
    title="Create a topic",
    description=(
        "Generate a new sourced encyclopedia article from a title (web search + LLM, ~15s). "
        "Returns the existing article instead if the topic is already covered. Daily rate "
        "limit applies — search first."
    ),
)
async def create_topic(title: str) -> str:
    async with async_session() as db:
        try:
            topic, created = await get_or_create_topic(db, title)
        except RateLimitError as e:
            return f"Rate limited: {e}. Reading and editing are still unlimited."
        except ModerationError as e:
            return f"Rejected: {e}"
        article = _format_article(topic, True)
        _, remaining = await check_daily_limit(db)

    prefix = "" if created else "This topic already existed; returning it unchanged.\n\n"
    quota = (
        f"\n\n({remaining}/{settings.daily_generation_limit} generations left today. "
        "Editing existing topics is unlimited.)"
    )
    return prefix + article + quota


@mcp.tool(
    title="Preview a phrase",
    description=(
        "Get a short AI explanation of any phrase without generating a full article. Cheap and "
        "fast — use it to decide whether a topic is worth creating."
    ),
)
async def preview_phrase(text: str) -> str:
    text = text.strip()
    if not text or len(text) > 200:
        return "Text must be 1-200 characters."
    async with async_session() as db:
        topic = await get_topic_by_slug(db, slugify(text, max_length=512))
        if topic:
            return (
                f'Preview of "{text}":\n\n{topic.summary or topic.title}\n\n'
                f"Existing article: {_topic_url(topic.slug)} (slug: {topic.slug})"
            )
    return f'Preview of "{text}":\n\n{await generate_topic_preview(text)}'


@mcp.tool(
    title="Edit a section",
    description=(
        "Replace one section of an article with corrected Markdown. Preferred over creating a "
        "duplicate topic when you find an error. Pass expected_revision (from read_topic) to "
        "avoid clobbering a concurrent edit."
    ),
)
async def edit_section(
    slug: str,
    section: str,
    content: str,
    edit_summary: str = "",
    editor: str = "agent",
    expected_revision: int | None = None,
) -> str:
    async with async_session() as db:
        topic = await get_topic_by_slug(db, slug)
        if not topic:
            return f"No topic with slug '{slug}'."
        try:
            updated = await update_topic_section(
                db, topic, section, content, edit_summary, editor, expected_revision
            )
        except ConflictError as e:
            return f"{e} Re-read the topic and retry."
        except ValueError as e:
            return f"Could not edit: {e}"
        return (
            f'Updated section "{section}" of {slug}. Now at revision '
            f"{updated.revision_number}.\n{_topic_url(slug)}"
        )


@mcp.tool(
    title="List missing topics",
    description=(
        "Topics people searched for that don't exist yet, ranked by demand. The "
        "highest-leverage queue for deciding what to write next."
    ),
)
async def list_missing_topics(limit: int = 20) -> str:
    async with async_session() as db:
        rows = await get_missing_topics(db, min(max(limit, 1), 100))
    if not rows:
        return "No missing topics recorded."
    lines = [f"{i}. {r['query']} — searched {r['search_count']}×" for i, r in enumerate(rows, 1)]
    return "Most-wanted missing topics:\n\n" + "\n".join(lines)
