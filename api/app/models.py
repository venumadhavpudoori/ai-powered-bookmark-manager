"""SQLAlchemy ORM models for RecallAI."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.config import settings

# ── Enums ─────────────────────────────────────────────────


class BookmarkStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class TagSource(str, enum.Enum):
    ai = "ai"
    user = "user"


# ── Base ──────────────────────────────────────────────────


class Base(DeclarativeBase):
    pass


# ── Users ─────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    bookmarks = relationship("Bookmark", back_populates="user", cascade="all, delete-orphan")
    collections = relationship("Collection", back_populates="user", cascade="all, delete-orphan")
    tags = relationship("Tag", back_populates="user", cascade="all, delete-orphan")
    jobs = relationship("Job", back_populates="user", cascade="all, delete-orphan")


# ── Collections ───────────────────────────────────────────


class Collection(Base):
    __tablename__ = "collections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    user = relationship("User", back_populates="collections")
    bookmarks = relationship("Bookmark", back_populates="collection")

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_collection_user_name"),
    )


# ── Bookmarks ─────────────────────────────────────────────


class Bookmark(Base):
    __tablename__ = "bookmarks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    content_text: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    key_takeaways: Mapped[list | None] = mapped_column(JSONB)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[BookmarkStatus] = mapped_column(
        Enum(BookmarkStatus, name="bookmark_status"),
        default=BookmarkStatus.pending,
        server_default="pending",
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    collection_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("collections.id", ondelete="SET NULL"),
        nullable=True,
    )
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user = relationship("User", back_populates="bookmarks")
    collection = relationship("Collection", back_populates="bookmarks")
    bookmark_tags = relationship(
        "BookmarkTag", back_populates="bookmark", cascade="all, delete-orphan"
    )
    chunks = relationship(
        "ContentChunk", back_populates="bookmark", cascade="all, delete-orphan"
    )
    jobs = relationship("Job", back_populates="bookmark", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("user_id", "canonical_url", name="uq_bookmark_user_url"),
        Index("ix_bookmark_user_created", "user_id", "created_at"),
    )


# ── Tags ──────────────────────────────────────────────────


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Relationships
    user = relationship("User", back_populates="tags")
    bookmark_tags = relationship(
        "BookmarkTag", back_populates="tag", cascade="all, delete-orphan"
    )

    # NOTE: Functional unique index on (user_id, lower(name)) created in migration


class BookmarkTag(Base):
    __tablename__ = "bookmark_tags"

    bookmark_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bookmarks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    )
    source: Mapped[TagSource] = mapped_column(
        Enum(TagSource, name="tag_source"), nullable=False, default=TagSource.user
    )

    # Relationships
    bookmark = relationship("Bookmark", back_populates="bookmark_tags")
    tag = relationship("Tag", back_populates="bookmark_tags")


# ── Content Chunks ────────────────────────────────────────


class ContentChunk(Base):
    __tablename__ = "content_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    bookmark_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bookmarks.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    tsv: Mapped[str | None] = mapped_column(TSVECTOR)
    embedding = mapped_column(ARRAY(Float))
    model_name: Mapped[str | None] = mapped_column(String(100))

    # Relationships
    bookmark = relationship("Bookmark", back_populates="chunks")


# ── Jobs ──────────────────────────────────────────────────


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    bookmark_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bookmarks.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status"),
        default=JobStatus.queued,
        server_default="queued",
    )
    stage: Mapped[str | None] = mapped_column(String(50))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text)
    run_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    bookmark = relationship("Bookmark", back_populates="jobs")
    user = relationship("User", back_populates="jobs")


# ── AI Usage Logging ──────────────────────────────────────


class AIUsage(Base):
    __tablename__ = "ai_usage"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
