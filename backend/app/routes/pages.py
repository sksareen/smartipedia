import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from slugify import slugify
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.moderation import ModerationError, check_title
from ..services.topics import (
    get_analytics_overview,
    get_discover_facets,
    get_missing_topics,
    get_or_create_topic,
    get_popular_topics,
    get_recent_edits,
    get_recent_topics,
    get_related_topics,
    get_topic_by_slug,
    get_topic_count,
    get_top_contributors,
    search_topics,
    update_topic,
)

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home(request: Request, db: AsyncSession = Depends(get_db)):
    recent = await get_recent_topics(db, limit=12)
    count = await get_topic_count(db)
    return request.app.state.templates.TemplateResponse(
        "pages/home.html",
        {"request": request, "recent": recent, "topic_count": count},
    )


@router.get("/search", response_class=HTMLResponse)
async def search_page(request: Request, q: str = "", db: AsyncSession = Depends(get_db)):
    results = []
    if q:
        results = await search_topics(db, q)
    is_htmx = request.headers.get("HX-Request") == "true"
    if is_htmx:
        return request.app.state.templates.TemplateResponse(
            "components/search_results.html",
            {"request": request, "results": results, "query": q},
        )
    return request.app.state.templates.TemplateResponse(
        "pages/search.html",
        {"request": request, "results": results, "query": q},
    )


@router.get("/topic/{slug}", response_class=HTMLResponse)
async def view_topic(request: Request, slug: str, db: AsyncSession = Depends(get_db)):
    topic = await get_topic_by_slug(db, slug)
    if not topic:
        return request.app.state.templates.TemplateResponse(
            "pages/topic_not_found.html",
            {"request": request, "slug": slug},
            status_code=404,
        )
    topic.view_count += 1
    await db.commit()
    await db.refresh(topic)
    related = await get_related_topics(db, topic)
    sources_json = json.dumps(topic.sources or [])
    # Send all topics for cross-linking (not just related), excluding current
    from sqlalchemy import select as sel
    from ..models import Topic
    all_topics_result = await db.execute(
        sel(Topic.slug, Topic.title, Topic.summary).where(Topic.slug != topic.slug)
    )
    all_topics = all_topics_result.all()
    related_json = json.dumps([
        {"slug": r.slug, "title": r.title, "summary": r.summary or ""}
        for r in all_topics
    ])
    infobox = topic.infobox or {}
    # Compute relative time
    now = datetime.now(timezone.utc)
    created = topic.created_at.replace(tzinfo=timezone.utc) if topic.created_at else now
    updated = topic.updated_at.replace(tzinfo=timezone.utc) if topic.updated_at else created
    delta = now - updated
    if delta.days > 0:
        time_ago = f"{delta.days} day{'s' if delta.days != 1 else ''} ago"
    elif delta.seconds >= 3600:
        hours = delta.seconds // 3600
        time_ago = f"{hours} hour{'s' if hours != 1 else ''} ago"
    else:
        mins = max(1, delta.seconds // 60)
        time_ago = f"{mins} minute{'s' if mins != 1 else ''} ago"

    # Hero image: use first source image or Unsplash fallback
    from urllib.parse import quote
    hero_image = f"https://source.unsplash.com/800x350/?{quote(topic.title)}"

    return request.app.state.templates.TemplateResponse(
        "pages/topic.html",
        {
            "request": request,
            "topic": topic,
            "related": related,
            "sources_json": sources_json,
            "related_json": related_json,
            "infobox": infobox,
            "time_ago": time_ago,
            "hero_image": hero_image,
        },
    )


@router.get("/stats", response_class=HTMLResponse)
async def stats_page(request: Request, db: AsyncSession = Depends(get_db)):
    overview = await get_analytics_overview(db)
    contributors = await get_top_contributors(db)
    recent_edits = await get_recent_edits(db, limit=15)
    missing = await get_missing_topics(db, limit=10)
    popular = await get_popular_topics(db, limit=10)
    facets = await get_discover_facets(db)
    quality = facets.get("quality_statuses", {})
    return request.app.state.templates.TemplateResponse(
        "pages/stats.html",
        {
            "request": request,
            "overview": overview,
            "contributors": contributors,
            "recent_edits": recent_edits,
            "missing": missing,
            "popular": popular,
            "quality": quality,
        },
    )


@router.get("/suggest", response_class=HTMLResponse)
async def suggest_page(request: Request, db: AsyncSession = Depends(get_db)):
    missing = await get_missing_topics(db, limit=10)
    return request.app.state.templates.TemplateResponse(
        "pages/suggest.html",
        {"request": request, "missing": missing},
    )


@router.get("/journeys", response_class=HTMLResponse)
async def journeys_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        "pages/journeys.html",
        {"request": request},
    )


@router.get("/graph", response_class=HTMLResponse)
async def graph_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        "pages/graph.html",
        {"request": request},
    )


@router.get("/api/quick-search", response_class=HTMLResponse)
async def quick_search(request: Request, q: str = "", db: AsyncSession = Depends(get_db)):
    """HTMX endpoint for Cmd+K search modal."""
    results = []
    if q and len(q) >= 2:
        results = await search_topics(db, q, limit=8)
    return request.app.state.templates.TemplateResponse(
        "components/quick_search_results.html",
        {"request": request, "results": results, "query": q},
    )


@router.post("/generate", response_class=HTMLResponse)
async def generate_page(request: Request, db: AsyncSession = Depends(get_db)):
    form = await request.form()
    title = form.get("title", "").strip()
    if not title:
        return RedirectResponse("/", status_code=303)
    slug = slugify(title, max_length=512)
    try:
        topic, created = await get_or_create_topic(db, title)
    except ModerationError as e:
        error_msg = str(e)
    except Exception as e:
        error_msg = str(e)
        if "402" in error_msg or "Payment" in error_msg:
            error_msg = "Article generation is temporarily unavailable. Please try again later."
        elif "rate" in error_msg.lower() or "limit" in error_msg.lower():
            error_msg = error_msg
        else:
            error_msg = "Something went wrong generating that article. Please try again."
        from urllib.parse import quote
        return RedirectResponse(f"/?error={quote(error_msg)}", status_code=303)
    return RedirectResponse(f"/topic/{topic.slug}", status_code=303)


@router.get("/topic/{slug}/generating", response_class=HTMLResponse)
async def generating_page(request: Request, slug: str, title: str = "", db: AsyncSession = Depends(get_db)):
    """Show a loading page while topic is being generated, then redirect when ready."""
    # Check if topic already exists (generation finished)
    topic = await get_topic_by_slug(db, slug)
    if topic:
        return RedirectResponse(f"/topic/{topic.slug}", status_code=303)
    display_title = title or slug.replace("-", " ").title()
    return request.app.state.templates.TemplateResponse(
        "pages/generating.html",
        {"request": request, "slug": slug, "title": display_title},
    )


@router.post("/generate-async", response_class=HTMLResponse)
async def generate_async(request: Request, db: AsyncSession = Depends(get_db)):
    """Start topic generation and redirect to the generating page."""
    form = await request.form()
    title = form.get("title", "").strip()
    if not title:
        return RedirectResponse("/", status_code=303)
    # Content moderation check
    try:
        check_title(title)
    except ModerationError as e:
        from urllib.parse import quote
        return RedirectResponse(f"/?error={quote(str(e))}", status_code=303)

    slug = slugify(title, max_length=512)

    # Check if already exists
    topic = await get_topic_by_slug(db, slug)
    if topic:
        return RedirectResponse(f"/topic/{topic.slug}", status_code=303)

    # Start generation in background
    import asyncio
    asyncio.create_task(_generate_in_background(title))

    from urllib.parse import quote
    return RedirectResponse(f"/topic/{slug}/generating?title={quote(title)}", status_code=303)


async def _generate_in_background(title: str):
    """Generate topic in a background task."""
    from ..database import async_session
    async with async_session() as db:
        try:
            await get_or_create_topic(db, title)
        except Exception as e:
            print(f"Background generation failed for '{title}': {e}")


@router.get("/topic/{slug}/edit", response_class=HTMLResponse)
async def edit_topic_page(request: Request, slug: str, db: AsyncSession = Depends(get_db)):
    topic = await get_topic_by_slug(db, slug)
    if not topic:
        return RedirectResponse("/", status_code=303)
    return request.app.state.templates.TemplateResponse(
        "pages/edit.html",
        {"request": request, "topic": topic},
    )


@router.post("/topic/{slug}/edit", response_class=HTMLResponse)
async def save_topic_edit(request: Request, slug: str, db: AsyncSession = Depends(get_db)):
    topic = await get_topic_by_slug(db, slug)
    if not topic:
        return RedirectResponse("/", status_code=303)
    form = await request.form()
    content_md = form.get("content_md", "")
    edit_summary = form.get("edit_summary", "")
    editor = form.get("editor", "user")
    await update_topic(db, topic, content_md, edit_summary, editor)
    return RedirectResponse(f"/topic/{topic.slug}", status_code=303)
