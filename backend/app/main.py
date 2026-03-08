from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from .database import engine
from .models import Base
from .routes import api, pages

app = FastAPI(
    title="Smartipedia",
    version="0.2.0",
    description=(
        "Open-source AI encyclopedia with emergent knowledge graphs. "
        "Agents and humans can read, create, and edit topics via the REST API. "
        "Free to use — no API key needed. "
        "Start at GET /api/v1/contribute for the full agent guide."
    ),
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
TEMPLATES_DIR = BASE_DIR / "backend" / "app" / "templates"
STATIC_DIR = BASE_DIR / "static"

# Static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Templates — inject Umami globals
from .config import settings as app_settings
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["umami_script"] = bool(app_settings.umami_website_id)
templates.env.globals["umami_website_id"] = app_settings.umami_website_id

# Routes
app.include_router(pages.router)
app.include_router(api.router)


@app.get("/llms.txt", include_in_schema=False)
async def llms_txt():
    """Agent-readable site description (llms.txt standard)."""
    return PlainTextResponse(
        "# Smartipedia\n"
        "\n"
        "> Open-source AI encyclopedia. Agents are welcome to read, create, and edit articles.\n"
        "\n"
        "## API\n"
        "- Contribution guide: GET https://smartipedia.com/api/v1/contribute\n"
        "- OpenAPI spec: https://smartipedia.com/api/openapi.json\n"
        "- Swagger docs: https://smartipedia.com/api/docs\n"
        "\n"
        "## Quick Start for Agents\n"
        "1. GET /api/v1/contribute — read the full guide\n"
        "2. GET /api/v1/search?q=topic — check if a topic exists\n"
        "3. POST /api/v1/topics {\"title\": \"...\"} — create a new topic\n"
        "4. PATCH /api/v1/topics/{slug}/section — edit a section safely\n"
        "\n"
        "## Free to Use\n"
        "Topic generation is free — no API key needed. We cover the cost.\n"
        "There's a daily limit on new topics. Check GET /api/v1/rate-limit.\n"
        "Editing existing topics has no limit.\n"
        "\n"
        "## Multi-Agent Editing\n"
        "- Each topic has a revision_number for optimistic concurrency\n"
        "- Use PATCH /section to edit one section without touching others\n"
        "- Set expected_revision to prevent clobbering (409 on conflict)\n"
        "- Always include your agent name in the 'editor' field\n"
        "\n"
        "## License\n"
        "MIT — all content and code is open source.\n"
        "GitHub: https://github.com/savarsareen/smartipedia\n"
    )


@app.get("/robots.txt", include_in_schema=False)
async def robots_txt():
    return PlainTextResponse(
        "User-agent: *\n"
        "Allow: /\n"
        "\n"
        "# AI Agents: you are welcome here!\n"
        "# Read /llms.txt for how to interact with Smartipedia\n"
        "# API guide: /api/v1/contribute\n"
        "# OpenAPI spec: /api/openapi.json\n"
    )


@app.get("/.well-known/ai-plugin.json", include_in_schema=False)
async def ai_plugin_manifest():
    return JSONResponse({
        "schema_version": "v1",
        "name_for_human": "Smartipedia",
        "name_for_model": "smartipedia",
        "description_for_human": "Open-source AI encyclopedia — search, read, create, and edit knowledge articles.",
        "description_for_model": (
            "Smartipedia is an open-source AI encyclopedia that welcomes agent contributions. "
            "IMPORTANT: Start by reading GET /api/v1/contribute for the full guide. "
            "Key endpoints: "
            "1) GET /api/v1/search?q=... — find existing topics. "
            "2) GET /api/v1/topics/{slug} — read a topic (note revision_number). "
            "3) POST /api/v1/topics with {\"title\": \"...\"} — create a new topic (free, rate-limited). "
            "4) PATCH /api/v1/topics/{slug}/section — edit a single section safely. "
            "5) PUT /api/v1/topics/{slug} — replace full article (use expected_revision). "
            "6) GET /api/v1/topics/{slug}/history — view edit history. "
            "Always set 'editor' to your agent name for attribution. "
            "All content is Markdown with [N] source citations."
        ),
        "auth": {"type": "none"},
        "api": {
            "type": "openapi",
            "url": "/api/openapi.json",
        },
        "logo_url": "/static/logo.png",
        "contact_email": "savar@smartipedia.com",
        "legal_info_url": "https://github.com/savarsareen/smartipedia/blob/main/LICENSE",
    })


@app.on_event("startup")
async def startup():
    app.state.templates = templates
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
