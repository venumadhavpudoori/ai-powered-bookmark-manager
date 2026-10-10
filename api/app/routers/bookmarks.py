"""Bookmark CRUD router."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user, ownership_filter
from app.models import Bookmark, BookmarkStatus, BookmarkTag, Job, JobStatus, Tag, User
from app.schemas import (
    BookmarkCreate,
    BookmarkListOut,
    BookmarkOut,
    BookmarkStatusOut,
    BookmarkUpdate,
)
from app.security.urls import validate_url

router = APIRouter(prefix="/bookmarks", tags=["bookmarks"])


async def _get_bookmark_or_404(
    bookmark_id: uuid.UUID, user: User, db: AsyncSession
) -> Bookmark:
    """Fetch a bookmark owned by the current user or raise 404."""
    result = await db.execute(
        select(Bookmark)
        .options(selectinload(Bookmark.bookmark_tags).selectinload(BookmarkTag.tag))
        .where(Bookmark.id == bookmark_id, ownership_filter(Bookmark, user))
    )
    bookmark = result.scalar_one_or_none()
    if bookmark is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bookmark not found")
    return bookmark


async def _get_or_create_tag(name: str, user: User, db: AsyncSession) -> Tag:
    """Find an existing user tag by name (case-insensitive) or create a new one."""
    result = await db.execute(
        select(Tag).where(
            Tag.user_id == user.id,
            func.lower(Tag.name) == name.strip().lower(),
        )
    )
    tag = result.scalar_one_or_none()
    if tag is None:
        tag = Tag(user_id=user.id, name=name.strip())
        db.add(tag)
        await db.flush()
    return tag


@router.post("", response_model=BookmarkOut, status_code=status.HTTP_201_CREATED)
async def create_bookmark(
    body: BookmarkCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BookmarkOut:
    """Save a new bookmark and queue it for processing."""
    # Validate and normalize URL
    try:
        canonical_url = validate_url(body.url)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )

    # Check for duplicate (same user + canonical URL)
    result = await db.execute(
        select(Bookmark).where(
            Bookmark.user_id == user.id,
            Bookmark.canonical_url == canonical_url,
        )
    )
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bookmark already exists for this URL",
        )

    # Create bookmark
    bookmark = Bookmark(
        user_id=user.id,
        url=body.url.strip(),
        canonical_url=canonical_url,
        title=body.title,
        notes=body.notes,
        collection_id=body.collection_id,
        status=BookmarkStatus.pending,
    )
    db.add(bookmark)
    await db.flush()

    # Add user-provided tags
    if body.tags:
        for tag_name in body.tags:
            tag = await _get_or_create_tag(tag_name, user, db)
            bt = BookmarkTag(bookmark_id=bookmark.id, tag_id=tag.id, source="user")
            db.add(bt)

    # Queue processing job
    job = Job(
        bookmark_id=bookmark.id,
        user_id=user.id,
        status=JobStatus.queued,
    )
    db.add(job)
    await db.flush()

    # Reload with tags
    await db.refresh(bookmark)
    bookmark = await _get_bookmark_or_404(bookmark.id, user, db)
    return BookmarkOut.from_bookmark(bookmark)


@router.get("", response_model=BookmarkListOut)
async def list_bookmarks(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    collection_id: uuid.UUID | None = None,
    tag: str | None = None,
    status: BookmarkStatus | None = None,
    archived: bool | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BookmarkListOut:
    """List bookmarks for the current user with optional filters."""
    query = (
        select(Bookmark)
        .options(selectinload(Bookmark.bookmark_tags).selectinload(BookmarkTag.tag))
        .where(ownership_filter(Bookmark, user))
    )

    # Apply filters
    if collection_id is not None:
        query = query.where(Bookmark.collection_id == collection_id)
    if status is not None:
        query = query.where(Bookmark.status == status)
    if archived is not None:
        query = query.where(Bookmark.archived == archived)
    if tag is not None:
        query = query.join(BookmarkTag).join(Tag).where(
            func.lower(Tag.name) == tag.lower()
        )

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Paginate
    query = query.order_by(Bookmark.created_at.desc())
    query = query.offset((page - 1) * size).limit(size)
    result = await db.execute(query)
    bookmarks = result.scalars().unique().all()

    return BookmarkListOut(
        items=[BookmarkOut.from_bookmark(b) for b in bookmarks],
        total=total,
        page=page,
        size=size,
    )


@router.get("/{bookmark_id}", response_model=BookmarkOut)
async def get_bookmark(
    bookmark_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BookmarkOut:
    """Get a single bookmark by ID."""
    bookmark = await _get_bookmark_or_404(bookmark_id, user, db)
    return BookmarkOut.from_bookmark(bookmark)


@router.patch("/{bookmark_id}", response_model=BookmarkOut)
async def update_bookmark(
    bookmark_id: uuid.UUID,
    body: BookmarkUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BookmarkOut:
    """Update a bookmark's editable fields."""
    bookmark = await _get_bookmark_or_404(bookmark_id, user, db)

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(bookmark, field, value)

    await db.flush()
    await db.refresh(bookmark)
    bookmark = await _get_bookmark_or_404(bookmark.id, user, db)
    return BookmarkOut.from_bookmark(bookmark)


@router.delete("/{bookmark_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bookmark(
    bookmark_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a bookmark and all associated data (tags, chunks, jobs)."""
    bookmark = await _get_bookmark_or_404(bookmark_id, user, db)
    await db.delete(bookmark)


@router.post("/{bookmark_id}/process", response_model=BookmarkStatusOut)
async def reprocess_bookmark(
    bookmark_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BookmarkStatusOut:
    """Queue a bookmark for (re-)processing."""
    bookmark = await _get_bookmark_or_404(bookmark_id, user, db)

    # Reset bookmark status
    bookmark.status = BookmarkStatus.pending
    bookmark.error_message = None

    # Create a new processing job
    job = Job(
        bookmark_id=bookmark.id,
        user_id=user.id,
        status=JobStatus.queued,
    )
    db.add(job)
    await db.flush()

    return BookmarkStatusOut(
        bookmark_id=bookmark.id,
        status=bookmark.status,
        error_message=None,
        job_status=job.status,
        job_stage=job.stage,
        attempt_count=job.attempt_count,
    )


@router.get("/{bookmark_id}/status", response_model=BookmarkStatusOut)
async def get_bookmark_status(
    bookmark_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BookmarkStatusOut:
    """Get the processing status of a bookmark."""
    bookmark = await _get_bookmark_or_404(bookmark_id, user, db)

    # Get the latest job
    result = await db.execute(
        select(Job)
        .where(Job.bookmark_id == bookmark.id, ownership_filter(Job, user))
        .order_by(Job.created_at.desc())
        .limit(1)
    )
    job = result.scalar_one_or_none()

    return BookmarkStatusOut(
        bookmark_id=bookmark.id,
        status=bookmark.status,
        error_message=bookmark.error_message,
        job_status=job.status if job else None,
        job_stage=job.stage if job else None,
        attempt_count=job.attempt_count if job else None,
    )
