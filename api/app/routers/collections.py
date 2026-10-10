"""Collections CRUD router."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, ownership_filter
from app.models import Collection, User
from app.schemas import CollectionCreate, CollectionOut, CollectionUpdate

router = APIRouter(prefix="/collections", tags=["collections"])


@router.get("", response_model=list[CollectionOut])
async def list_collections(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CollectionOut]:
    """List all collections for the current user."""
    result = await db.execute(
        select(Collection)
        .where(ownership_filter(Collection, user))
        .order_by(Collection.name)
    )
    return [CollectionOut.model_validate(c) for c in result.scalars().all()]


@router.post("", response_model=CollectionOut, status_code=status.HTTP_201_CREATED)
async def create_collection(
    body: CollectionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CollectionOut:
    """Create a new collection."""
    # Check for duplicate name
    result = await db.execute(
        select(Collection).where(
            Collection.user_id == user.id,
            Collection.name == body.name.strip(),
        )
    )
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Collection with this name already exists",
        )

    collection = Collection(user_id=user.id, name=body.name.strip())
    db.add(collection)
    await db.flush()
    await db.refresh(collection)
    return CollectionOut.model_validate(collection)


@router.get("/{collection_id}", response_model=CollectionOut)
async def get_collection(
    collection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CollectionOut:
    """Get a single collection by ID."""
    result = await db.execute(
        select(Collection).where(
            Collection.id == collection_id,
            ownership_filter(Collection, user),
        )
    )
    collection = result.scalar_one_or_none()
    if collection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found"
        )
    return CollectionOut.model_validate(collection)


@router.patch("/{collection_id}", response_model=CollectionOut)
async def update_collection(
    collection_id: uuid.UUID,
    body: CollectionUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CollectionOut:
    """Update a collection."""
    result = await db.execute(
        select(Collection).where(
            Collection.id == collection_id,
            ownership_filter(Collection, user),
        )
    )
    collection = result.scalar_one_or_none()
    if collection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found"
        )

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(collection, field, value)

    await db.flush()
    await db.refresh(collection)
    return CollectionOut.model_validate(collection)


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(
    collection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a collection. Bookmarks in it remain but lose their collection_id."""
    result = await db.execute(
        select(Collection).where(
            Collection.id == collection_id,
            ownership_filter(Collection, user),
        )
    )
    collection = result.scalar_one_or_none()
    if collection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found"
        )
    await db.delete(collection)
