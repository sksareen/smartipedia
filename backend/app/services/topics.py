import asyncio
import re
from datetime import datetime, timezone

import markdown
from slugify import slugify
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import GenerationLog, SearchLog, Topic, TopicLink, TopicRevision
from .llm import generate_embedding, generate_topic
from .moderation import ModerationError, check_title
from .search import web_search


async def get_topic_by_slug(db: AsyncSession, slug: str) -> Topic | None:
    result = await db.execute(select(Topic).where(Topic.slug == slug))
    return result.scalar_one_or_none()


async def check_daily_limit(db: AsyncSession) -> tuple[bool, int]:
    """Check if daily generation limit has been reached. Returns (allowed, remaining)."""
    if settings.daily_generation_limit <= 0:
        return True, 999

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(sqlfunc.count(GenerationLog.id))
        .where(GenerationLog.created_at >= today_start)
    )
    today_count = result.scalar_one()
    remaining = max(0, settings.daily_generation_limit - today_count)
    return remaining > 0, remaining


async def get_or_create_topic(
    db: AsyncSession,
    title: str,
) -> tuple[Topic, bool]:
    """Get existing topic or generate a new one. Returns (topic, was_created).

    Generation is free — uses the server's OpenRouter key.
    Subject to daily generation limit.
    """
    # Content moderation check
    check_title(title)

    slug = slugify(title, max_length=512)
    existing = await get_topic_by_slug(db, slug)
    if existing:
        existing.view_count += 1
        await db.commit()
        return existing, False

    # Check daily limit
    allowed, remaining = await check_daily_limit(db)
    if not allowed:
        raise RateLimitError(
            f"Daily generation limit reached ({settings.daily_generation_limit}/day). "
            f"Try again tomorrow, or edit existing topics."
        )

    # Generate new topic (always uses server key)
    search_results = await web_search(title)
    generated = await generate_topic(title, search_results)

    content_html = markdown.markdown(
        generated["content_md"],
        extensions=["tables", "fenced_code", "toc"],
    )

    topic = Topic(
        slug=slug,
        title=title,
        summary=generated["summary"],
        content_md=generated["content_md"],
        content_html=content_html,
        sources=search_results,
        infobox=generated.get("infobox", {}),
        metadata_=generated.get("metadata", {"quality": {"status": "generated", "reviewed_by": [], "flagged_issues": []}}),
        model_used=generated["model"],
        revision_number=1,
        view_count=1,
    )
    db.add(topic)

    # Save initial revision
    revision = TopicRevision(
        topic=topic,
        content_md=generated["content_md"],
        sources=search_results,
        edit_summary="Initial generation",
        editor="system",
    )
    db.add(revision)
    await db.flush()

    # Log the generation for rate limiting
    db.add(GenerationLog(topic_slug=slug, model_used=generated["model"]))

    # Create placeholder links for related topics
    for related_title in generated["related_topics"]:
        related_slug = slugify(related_title, max_length=512)
        result = await db.execute(select(Topic).where(Topic.slug == related_slug))
        related_topic = result.scalar_one_or_none()

        if related_topic:
            link = TopicLink(
                source_id=topic.id,
                target_id=related_topic.id,
                relationship_type="related",
            )
            db.add(link)

    await db.commit()
    await db.refresh(topic)

    # Generate embedding in background — don't block the response
    async def _set_embedding():
        try:
            embedding = await generate_embedding(f"{title}: {generated['summary']}")
            if embedding:
                topic.embedding = embedding
                await db.commit()
        except Exception:
            pass  # ok if it fails

    asyncio.create_task(_set_embedding())

    return topic, True


async def update_topic(
    db: AsyncSession,
    topic: Topic,
    content_md: str,
    edit_summary: str = "",
    editor: str = "user",
    expected_revision: int | None = None,
) -> Topic:
    """Update a topic's content and save a revision."""
    if expected_revision is not None and topic.revision_number != expected_revision:
        raise ConflictError(
            f"Conflict: topic is at revision {topic.revision_number}, "
            f"but you expected {expected_revision}. "
            f"Re-read the topic and retry your edit."
        )

    revision = TopicRevision(
        topic_id=topic.id,
        content_md=content_md,
        sources=topic.sources,
        edit_summary=edit_summary,
        editor=editor,
    )
    db.add(revision)

    topic.content_md = content_md
    topic.content_html = markdown.markdown(
        content_md, extensions=["tables", "fenced_code", "toc"]
    )
    topic.revision_number = (topic.revision_number or 0) + 1
    await db.commit()
    await db.refresh(topic)
    return topic


async def update_topic_section(
    db: AsyncSession,
    topic: Topic,
    section_heading: str,
    new_content: str,
    edit_summary: str = "",
    editor: str = "agent",
    expected_revision: int | None = None,
) -> Topic:
    """Edit a single section of a topic by heading name."""
    if expected_revision is not None and topic.revision_number != expected_revision:
        raise ConflictError(
            f"Conflict: topic is at revision {topic.revision_number}, "
            f"but you expected {expected_revision}."
        )

    lines = topic.content_md.split("\n")
    section_start = None
    section_end = None
    heading_level = None

    for i, line in enumerate(lines):
        heading_match = re.match(r"^(#{1,4})\s+(.+)", line)
        if heading_match:
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            if title.lower() == section_heading.lower():
                section_start = i
                heading_level = level
            elif section_start is not None and level <= heading_level:
                section_end = i
                break

    if section_start is None:
        raise SectionNotFoundError(f"Section '{section_heading}' not found in article.")

    if section_end is None:
        section_end = len(lines)

    new_lines = lines[:section_start + 1] + [new_content.strip()] + [""] + lines[section_end:]
    new_md = "\n".join(new_lines)

    return await update_topic(db, topic, new_md, edit_summary or f"Updated section: {section_heading}", editor, expected_revision=None)


async def review_topic(
    db: AsyncSession,
    topic: Topic,
    status: str,
    reviewer: str,
    issues: list[str] | None = None,
) -> Topic:
    """Update a topic's quality status."""
    meta = dict(topic.metadata_ or {})
    quality = dict(meta.get("quality", {}))
    quality["status"] = status
    reviewed_by = list(quality.get("reviewed_by", []))
    if reviewer not in reviewed_by:
        reviewed_by.append(reviewer)
    quality["reviewed_by"] = reviewed_by
    if issues is not None:
        quality["flagged_issues"] = issues
    quality["last_reviewed_at"] = datetime.now(timezone.utc).isoformat()
    meta["quality"] = quality
    topic.metadata_ = meta
    await db.commit()
    await db.refresh(topic)
    return topic


async def flag_topic(
    db: AsyncSession,
    topic: Topic,
    issue: str,
    reporter: str,
) -> Topic:
    """Flag an issue on a topic."""
    meta = dict(topic.metadata_ or {})
    quality = dict(meta.get("quality", {}))
    flagged = list(quality.get("flagged_issues", []))
    entry = f"{issue} (reported by {reporter})"
    if entry not in flagged:
        flagged.append(entry)
    quality["flagged_issues"] = flagged
    if quality.get("status") == "verified":
        quality["status"] = "disputed"
    meta["quality"] = quality
    topic.metadata_ = meta
    await db.commit()
    await db.refresh(topic)
    return topic


# ==================== SEARCH ====================

async def search_topics(db: AsyncSession, query: str, limit: int = 20, searcher: str = "anonymous") -> list[Topic]:
    """Full-text search across topic titles and summaries. Logs the search."""
    result = await db.execute(
        select(Topic)
        .where(
            Topic.title.ilike(f"%{query}%")
            | Topic.summary.ilike(f"%{query}%")
        )
        .order_by(Topic.view_count.desc())
        .limit(limit)
    )
    topics = list(result.scalars().all())

    # Log the search
    log = SearchLog(query=query, result_count=len(topics), searcher=searcher)
    db.add(log)
    await db.commit()

    return topics


async def semantic_search_topics(
    db: AsyncSession,
    query_embedding: list[float],
    category: str | None = None,
    difficulty: str | None = None,
    quality_status: str | None = None,
    min_views: int | None = None,
    limit: int = 20,
) -> list[Topic]:
    """Semantic search using pgvector cosine distance with JSONB filters."""
    stmt = select(Topic).where(Topic.embedding.isnot(None))

    if category:
        stmt = stmt.where(Topic.metadata_["category"].astext == category)
    if difficulty:
        stmt = stmt.where(Topic.metadata_["difficulty"].astext == difficulty)
    if quality_status:
        stmt = stmt.where(Topic.metadata_["quality"]["status"].astext == quality_status)
    if min_views:
        stmt = stmt.where(Topic.view_count >= min_views)

    stmt = stmt.order_by(Topic.embedding.cosine_distance(query_embedding)).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ==================== ANALYTICS ====================

async def get_missing_topics(db: AsyncSession, limit: int = 20) -> list[dict]:
    """Most-searched queries that returned 0 results."""
    result = await db.execute(
        select(
            SearchLog.query,
            sqlfunc.count(SearchLog.id).label("search_count"),
        )
        .where(SearchLog.result_count == 0)
        .group_by(SearchLog.query)
        .order_by(sqlfunc.count(SearchLog.id).desc())
        .limit(limit)
    )
    return [{"query": row.query, "search_count": row.search_count} for row in result]


async def get_stale_topics(db: AsyncSession, days: int = 30, limit: int = 20) -> list[Topic]:
    """High-view topics not updated recently."""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None)
    from datetime import timedelta
    cutoff = cutoff - timedelta(days=days)
    result = await db.execute(
        select(Topic)
        .where(Topic.updated_at < cutoff)
        .order_by(Topic.view_count.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_flagged_topics(db: AsyncSession, limit: int = 20) -> list[Topic]:
    """Topics with quality issues flagged."""
    result = await db.execute(
        select(Topic)
        .where(
            sqlfunc.jsonb_array_length(
                Topic.metadata_["quality"]["flagged_issues"]
            ) > 0
        )
        .order_by(Topic.view_count.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_analytics_overview(db: AsyncSession) -> dict:
    """Aggregated stats for the encyclopedia."""
    topic_count = (await db.execute(select(sqlfunc.count(Topic.id)))).scalar_one()
    search_count = (await db.execute(select(sqlfunc.count(SearchLog.id)))).scalar_one()
    miss_count = (await db.execute(
        select(sqlfunc.count(SearchLog.id)).where(SearchLog.result_count == 0)
    )).scalar_one()
    total_views = (await db.execute(select(sqlfunc.sum(Topic.view_count)))).scalar_one() or 0
    total_edits = (await db.execute(select(sqlfunc.count(TopicRevision.id)))).scalar_one()
    total_editors = (await db.execute(
        select(sqlfunc.count(sqlfunc.distinct(TopicRevision.editor)))
    )).scalar_one()

    return {
        "total_topics": topic_count,
        "total_searches": search_count,
        "search_misses": miss_count,
        "miss_rate": round(miss_count / max(search_count, 1) * 100, 1),
        "total_views": total_views,
        "total_edits": total_edits,
        "total_editors": total_editors,
    }


async def get_top_contributors(db: AsyncSession, limit: int = 15) -> list[dict]:
    result = await db.execute(
        select(
            TopicRevision.editor,
            sqlfunc.count(TopicRevision.id).label("edit_count"),
        )
        .group_by(TopicRevision.editor)
        .order_by(sqlfunc.count(TopicRevision.id).desc())
        .limit(limit)
    )
    return [{"editor": row.editor, "edit_count": row.edit_count} for row in result]


async def get_recent_edits(db: AsyncSession, limit: int = 20) -> list[dict]:
    result = await db.execute(
        select(TopicRevision, Topic.slug, Topic.title)
        .join(Topic, TopicRevision.topic_id == Topic.id)
        .order_by(TopicRevision.created_at.desc())
        .limit(limit)
    )
    now = datetime.now(timezone.utc)
    edits = []
    for row in result:
        rev = row[0]
        created = rev.created_at.replace(tzinfo=timezone.utc) if rev.created_at else now
        delta = now - created
        if delta.days > 0:
            time_ago = f"{delta.days}d ago"
        elif delta.seconds >= 3600:
            time_ago = f"{delta.seconds // 3600}h ago"
        else:
            time_ago = f"{max(1, delta.seconds // 60)}m ago"
        edits.append({
            "editor": rev.editor,
            "edit_summary": rev.edit_summary,
            "topic_slug": row[1],
            "topic_title": row[2],
            "time_ago": time_ago,
        })
    return edits


async def get_discover_facets(db: AsyncSession) -> dict:
    """Aggregated counts of categories, tags, difficulty levels."""
    result = await db.execute(select(Topic.metadata_))
    all_meta = [row[0] or {} for row in result]

    categories = {}
    difficulties = {}
    tags = {}
    quality_statuses = {}

    for m in all_meta:
        cat = m.get("category", "Unknown")
        categories[cat] = categories.get(cat, 0) + 1
        diff = m.get("difficulty", "unknown")
        difficulties[diff] = difficulties.get(diff, 0) + 1
        for tag in m.get("tags", []):
            tags[tag] = tags.get(tag, 0) + 1
        qs = m.get("quality", {}).get("status", "generated")
        quality_statuses[qs] = quality_statuses.get(qs, 0) + 1

    return {
        "categories": dict(sorted(categories.items(), key=lambda x: -x[1])),
        "difficulties": difficulties,
        "top_tags": dict(sorted(tags.items(), key=lambda x: -x[1])[:30]),
        "quality_statuses": quality_statuses,
    }


# ==================== QUERIES ====================

async def get_topic_revisions(db: AsyncSession, topic: Topic, limit: int = 20) -> list[TopicRevision]:
    result = await db.execute(
        select(TopicRevision)
        .where(TopicRevision.topic_id == topic.id)
        .order_by(TopicRevision.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_related_topics(db: AsyncSession, topic: Topic) -> list[Topic]:
    result = await db.execute(
        select(Topic)
        .join(TopicLink, TopicLink.target_id == Topic.id)
        .where(TopicLink.source_id == topic.id)
    )
    return list(result.scalars().all())


async def get_recent_topics(db: AsyncSession, limit: int = 20) -> list[Topic]:
    result = await db.execute(
        select(Topic).order_by(Topic.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


async def get_popular_topics(db: AsyncSession, limit: int = 20) -> list[Topic]:
    result = await db.execute(
        select(Topic).order_by(Topic.view_count.desc()).limit(limit)
    )
    return list(result.scalars().all())


async def get_topic_count(db: AsyncSession) -> int:
    result = await db.execute(select(sqlfunc.count(Topic.id)))
    return result.scalar_one()


class ConflictError(Exception):
    pass


class SectionNotFoundError(Exception):
    pass


class RateLimitError(Exception):
    pass
