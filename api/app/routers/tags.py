"""Tags CRUD router."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, ownership_filter
from app.models import BookmarkTag, Tag, TagSource, User
from app.schemas import TagCreate, TagOut

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("", response_model=list[TagOut])
async def list_tags(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TagOut]:
    """List all tags for the current user."""
    result = await db.execute(
        select(Tag)
        .where(ownership_filter(Tag, user))
        .order_by(Tag.name)
    )
    tags = result.scalars().all()
    return [TagOut.model_validate(t) for t in tags]


@router.post("", response_model=TagOut, status_code=status.HTTP_201_CREATED)
async def create_tag(
    body: TagCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TagOut:
    """Create a new tag for the current user."""
    # Check for existing tag (case-insensitive)
    result = await db.execute(
        select(Tag).where(
            Tag.user_id == user.id,
            func.lower(Tag.name) == body.name.strip().lower(),
        )
    )
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tag already exists",
        )

    tag = Tag(user_id=user.id, name=body.name.strip())
    db.add(tag)
    await db.flush()
    await db.refresh(tag)
    return TagOut.model_validate(tag)


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    tag_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a tag. Removes it from all bookmarks."""
    result = await db.execute(
        select(Tag).where(Tag.id == tag_id, ownership_filter(Tag, user))
    )
    tag = result.scalar_one_or_none()
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    await db.delete(tag)


@router.post(
    "/{tag_id}/bookmarks/{bookmark_id}",
    status_code=status.HTTP_201_CREATED,
)
async def add_tag_to_bookmark(
    tag_id: uuid.UUID,
    bookmark_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Add a tag to a bookmark (user source)."""
    from app.models import Bookmark

    # Verify tag ownership
    result = await db.execute(
        select(Tag).where(Tag.id == tag_id, ownership_filter(Tag, user))
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")

    # Verify bookmark ownership
    result = await db.execute(
        select(Bookmark).where(Bookmark.id == bookmark_id, ownership_filter(Bookmark, user))
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bookmark not found")

    # Check if already tagged
    result = await db.execute(
        select(BookmarkTag).where(
            BookmarkTag.bookmark_id == bookmark_id,
            BookmarkTag.tag_id == tag_id,
        )
    )
    if result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tag already added")

    bt = BookmarkTag(
        bookmark_id=bookmark_id,
        tag_id=tag_id,
        source=TagSource.user,
    )
    db.add(bt)
    return {"status": "added"}


@router.delete(
    "/{tag_id}/bookmarks/{bookmark_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_tag_from_bookmark(
    tag_id: uuid.UUID,
    bookmark_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove a tag from a bookmark."""
    from app.models import Bookmark

    # Verify ownership of both
    result = await db.execute(
        select(Tag).where(Tag.id == tag_id, ownership_filter(Tag, user))
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")

    result = await db.execute(
        select(Bookmark).where(Bookmark.id == bookmark_id, ownership_filter(Bookmark, user))
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bookmark not found")

    result = await db.execute(
        select(BookmarkTag).where(
            BookmarkTag.bookmark_id == bookmark_id,
            BookmarkTag.tag_id == tag_id,
        )
    )
    bt = result.scalar_one_or_none()
    if bt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not on bookmark")
    await db.delete(bt)
