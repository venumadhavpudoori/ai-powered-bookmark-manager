"""Search router."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Bookmark, BookmarkTag, User
from app.schemas import BookmarkOut, BookmarkTagOut, SearchResponse, SearchResult, TagOut
from app.search import hybrid_search

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchResponse)
async def search(
    q: str = Query(min_length=1, max_length=500, description="Search query"),
    tag: str | None = None,
    collection_id: uuid.UUID | None = None,
    limit: int = Query(20, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SearchResponse:
    """Search bookmarks by meaning using hybrid semantic + keyword search."""
    raw_results = await hybrid_search(
        query=q,
        user_id=user.id,
        db=db,
        tag_filter=tag,
        collection_id=collection_id,
        limit=limit,
    )

    # Build response with full bookmark data including tags
    results = []
    for r in raw_results:
        # Load bookmark with tags
        bm_result = await db.execute(
            select(Bookmark)
            .options(selectinload(Bookmark.bookmark_tags).selectinload(BookmarkTag.tag))
            .where(Bookmark.id == r["bookmark_id"])
        )
        bookmark = bm_result.scalar_one_or_none()
        if bookmark is None:
            continue

        # Apply tag filter if specified
        if tag:
            tag_names = [bt.tag.name.lower() for bt in bookmark.bookmark_tags]
            if tag.lower() not in tag_names:
                continue

        # Apply collection filter
        if collection_id and bookmark.collection_id != collection_id:
            continue

        bookmark_out = BookmarkOut.from_bookmark(bookmark)
        results.append(
            SearchResult(
                bookmark=bookmark_out,
                score=r["score"],
                excerpt=r.get("excerpt"),
            )
        )

    return SearchResponse(
        query=q,
        results=results,
        total=len(results),
    )
