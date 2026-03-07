import re

import markdown
from slugify import slugify
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Topic, TopicLink, TopicRevision
from .llm import generate_topic
from .search import web_search


async def get_topic_by_slug(db: AsyncSession, slug: str) -> Topic | None:
    result = await db.execute(select(Topic).where(Topic.slug == slug))
    return result.scalar_one_or_none()


async def get_or_create_topic(
    db: AsyncSession,
    title: str,
    openrouter_key: str | None = None,
    model: str | None = None,
) -> tuple[Topic, bool]:
    """Get existing topic or generate a new one. Returns (topic, was_created)."""
    slug = slugify(title, max_length=512)
    existing = await get_topic_by_slug(db, slug)
    if existing:
        existing.view_count += 1
        await db.commit()
        return existing, False

    # Generate new topic
    search_results = await web_search(title)
    generated = await generate_topic(title, search_results, openrouter_key, model)

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
    return topic, True


async def update_topic(
    db: AsyncSession,
    topic: Topic,
    content_md: str,
    edit_summary: str = "",
    editor: str = "user",
    expected_revision: int | None = None,
) -> Topic:
    """Update a topic's content and save a revision.

    If expected_revision is provided, the update only succeeds if the topic's
    current revision_number matches. This prevents agents from clobbering
    each other's edits (optimistic concurrency).
    """
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
    """Edit a single section of a topic by heading name.

    Finds the section matching `section_heading` (case-insensitive) and replaces
    its content. Other sections are untouched. This allows multiple agents to
    edit different sections without conflicts.
    """
    if expected_revision is not None and topic.revision_number != expected_revision:
        raise ConflictError(
            f"Conflict: topic is at revision {topic.revision_number}, "
            f"but you expected {expected_revision}."
        )

    lines = topic.content_md.split("\n")
    section_start = None
    section_end = None
    heading_level = None

    # Find the section
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

    # Replace section content (keep the heading line)
    new_lines = lines[:section_start + 1] + [new_content.strip()] + [""] + lines[section_end:]
    new_md = "\n".join(new_lines)

    return await update_topic(db, topic, new_md, edit_summary or f"Updated section: {section_heading}", editor, expected_revision=None)


async def get_topic_revisions(db: AsyncSession, topic: Topic, limit: int = 20) -> list[TopicRevision]:
    result = await db.execute(
        select(TopicRevision)
        .where(TopicRevision.topic_id == topic.id)
        .order_by(TopicRevision.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def search_topics(db: AsyncSession, query: str, limit: int = 20) -> list[Topic]:
    """Full-text search across topic titles and summaries."""
    result = await db.execute(
        select(Topic)
        .where(
            Topic.title.ilike(f"%{query}%")
            | Topic.summary.ilike(f"%{query}%")
        )
        .order_by(Topic.view_count.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_related_topics(db: AsyncSession, topic: Topic) -> list[Topic]:
    """Get topics linked from this topic."""
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
    from sqlalchemy import func as sqlfunc
    result = await db.execute(select(sqlfunc.count(Topic.id)))
    return result.scalar_one()


class ConflictError(Exception):
    pass


class SectionNotFoundError(Exception):
    pass
