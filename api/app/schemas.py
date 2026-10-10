"""Pydantic schemas for request/response validation."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, HttpUrl

from app.models import BookmarkStatus, JobStatus, TagSource


# ── Auth ──────────────────────────────────────────────────


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(None, max_length=255)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Collections ───────────────────────────────────────────


class CollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class CollectionUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)


class CollectionOut(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Tags ──────────────────────────────────────────────────


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class TagOut(BaseModel):
    id: uuid.UUID
    name: str

    model_config = {"from_attributes": True}


class BookmarkTagOut(BaseModel):
    tag: TagOut
    source: TagSource

    model_config = {"from_attributes": True}


# ── Bookmarks ─────────────────────────────────────────────


class BookmarkCreate(BaseModel):
    url: str = Field(description="URL to bookmark")
    title: str | None = None
    notes: str | None = None
    collection_id: uuid.UUID | None = None
    tags: list[str] | None = Field(None, description="Initial user tags")


class BookmarkUpdate(BaseModel):
    title: str | None = None
    notes: str | None = None
    collection_id: uuid.UUID | None = None
    archived: bool | None = None
    summary: str | None = None


class BookmarkOut(BaseModel):
    id: uuid.UUID
    url: str
    canonical_url: str
    title: str | None
    description: str | None
    summary: str | None
    key_takeaways: list[str] | None
    notes: str | None
    status: BookmarkStatus
    error_message: str | None
    collection_id: uuid.UUID | None
    archived: bool
    created_at: datetime
    updated_at: datetime
    tags: list[BookmarkTagOut] = []

    model_config = {"from_attributes": True}

    @classmethod
    def from_bookmark(cls, bookmark) -> "BookmarkOut":
        """Build from ORM bookmark with loaded bookmark_tags."""
        return cls(
            id=bookmark.id,
            url=bookmark.url,
            canonical_url=bookmark.canonical_url,
            title=bookmark.title,
            description=bookmark.description,
            summary=bookmark.summary,
            key_takeaways=bookmark.key_takeaways,
            notes=bookmark.notes,
            status=bookmark.status,
            error_message=bookmark.error_message,
            collection_id=bookmark.collection_id,
            archived=bookmark.archived,
            created_at=bookmark.created_at,
            updated_at=bookmark.updated_at,
            tags=[
                BookmarkTagOut(
                    tag=TagOut(id=bt.tag.id, name=bt.tag.name),
                    source=bt.source,
                )
                for bt in (bookmark.bookmark_tags or [])
            ],
        )


class BookmarkListOut(BaseModel):
    items: list[BookmarkOut]
    total: int
    page: int
    size: int


class BookmarkStatusOut(BaseModel):
    bookmark_id: uuid.UUID
    status: BookmarkStatus
    error_message: str | None
    job_status: JobStatus | None = None
    job_stage: str | None = None
    attempt_count: int | None = None

    model_config = {"from_attributes": True}


# ── Search ────────────────────────────────────────────────


class SearchResult(BaseModel):
    bookmark: BookmarkOut
    score: float
    excerpt: str | None = None


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    total: int
