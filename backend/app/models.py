import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Topic(Base):
    __tablename__ = "topics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug = Column(String(512), unique=True, nullable=False, index=True)
    title = Column(String(512), nullable=False)
    summary = Column(Text)  # one-line summary for link previews
    content_md = Column(Text, nullable=False)  # markdown content
    content_html = Column(Text)  # pre-rendered HTML
    sources = Column(JSONB, default=list)  # [{url, title, snippet}]
    infobox = Column(JSONB, default=dict)  # structured key-value facts for sidebar
    metadata_ = Column("metadata", JSONB, default=dict)  # {tags, category, subcategory, difficulty, quality}
    model_used = Column(String(128))  # which LLM generated this
    embedding = Column(Vector(1536))  # for semantic similarity / graph links
    revision_number = Column(Integer, default=1, nullable=False)  # for optimistic concurrency
    view_count = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    revisions = relationship("TopicRevision", back_populates="topic", order_by="TopicRevision.created_at.desc()")
    outgoing_links = relationship("TopicLink", foreign_keys="TopicLink.source_id", back_populates="source")
    incoming_links = relationship("TopicLink", foreign_keys="TopicLink.target_id", back_populates="target")


class TopicRevision(Base):
    __tablename__ = "topic_revisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic_id = Column(UUID(as_uuid=True), ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    content_md = Column(Text, nullable=False)
    sources = Column(JSONB, default=list)
    edit_summary = Column(String(512))
    editor = Column(String(128), default="system")  # "system", "user", or agent identifier
    created_at = Column(DateTime, server_default=func.now())

    topic = relationship("Topic", back_populates="revisions")


class TopicLink(Base):
    """Directed edge in the knowledge graph."""
    __tablename__ = "topic_links"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id = Column(UUID(as_uuid=True), ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    target_id = Column(UUID(as_uuid=True), ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    relationship_type = Column(String(64), default="related")  # related, subtopic, prerequisite, see_also
    weight = Column(Integer, default=1)  # strength of connection

    source = relationship("Topic", foreign_keys=[source_id], back_populates="outgoing_links")
    target = relationship("Topic", foreign_keys=[target_id], back_populates="incoming_links")


class SearchLog(Base):
    """Tracks what people search for — helps identify missing topics."""
    __tablename__ = "search_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query = Column(String(512), nullable=False)
    result_count = Column(Integer, default=0)
    searcher = Column(String(128), default="anonymous")  # agent name or "web"
    created_at = Column(DateTime, server_default=func.now())
