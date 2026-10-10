"""Seed script to populate RecallAI database with demo data."""

import asyncio
import sys
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import async_session_factory
from app.models import (
    User,
    Collection,
    Bookmark,
    Tag,
    BookmarkTag,
    TagSource,
    BookmarkStatus,
    ContentChunk,
)
from app.security.auth import hash_password
from app.ai.provider import get_ai_provider

DEMO_USER_EMAIL = "demo@recallai.local"
DEMO_USER_PASSWORD = "password123"

DEMO_BOOKMARKS = [
    {
        "url": "https://fastapi.tiangolo.com/tutorial/first-steps/",
        "canonical_url": "https://fastapi.tiangolo.com/tutorial/first-steps",
        "title": "FastAPI Tutorial - First Steps",
        "summary": "Introduction to building high-performance modern Python APIs with FastAPI. Covers automatic interactive documentation with Swagger UI, path operations, and Pydantic request models.",
        "takeaways": [
            "FastAPI uses standard Python type hints for validation and OpenAPI schemas",
            "Automatic interactive docs available at /docs and /redoc",
            "High performance on ASGI servers like Uvicorn"
        ],
        "tags": ["python", "fastapi", "api", "backend"],
        "collection": "Backend & APIs",
        "content_text": "FastAPI is a modern, fast (high-performance), web framework for building APIs with Python 3.8+ based on standard Python type hints. Interactive API documentation is powered by Swagger UI and ReDoc.",
    },
    {
        "url": "https://nextjs.org/docs/app",
        "canonical_url": "https://nextjs.org/docs/app",
        "title": "Next.js App Router Documentation",
        "summary": "Comprehensive guide to the Next.js App Router architecture. Features React Server Components, nested routing, streaming with Suspense, and enhanced caching mechanisms.",
        "takeaways": [
            "React Server Components reduce client-side bundle size",
            "File-system based routing using app directory conventions",
            "Built-in streaming and layouts"
        ],
        "tags": ["react", "nextjs", "frontend", "typescript"],
        "collection": "Frontend Development",
        "content_text": "The Next.js App Router introduces a new mental model for building applications using React's latest features like Server Components and streaming with Suspense.",
    },
    {
        "url": "https://github.com/pgvector/pgvector",
        "canonical_url": "https://github.com/pgvector/pgvector",
        "title": "pgvector: Open-source vector similarity search for Postgres",
        "summary": "Postgres extension for storing and querying vector embeddings with exact and approximate nearest neighbor search support using HNSW and IVFFlat indexes.",
        "takeaways": [
            "Store embeddings directly in PostgreSQL relational database",
            "Supports L2 distance, inner product, and cosine distance operators",
            "HNSW indexing provides high-speed vector retrieval"
        ],
        "tags": ["postgres", "pgvector", "database", "ai", "search"],
        "collection": "AI & Vectors",
        "content_text": "pgvector adds vector similarity search to Postgres. Supports exact and approximate nearest neighbor search, L2 distance, cosine distance, and HNSW indexes.",
    },
    {
        "url": "https://en.wikipedia.org/wiki/Reciprocal_rank_fusion",
        "canonical_url": "https://en.wikipedia.org/wiki/reciprocal_rank_fusion",
        "title": "Reciprocal Rank Fusion - Hybrid Search Algorithm",
        "summary": "Method for combining rankings from multiple independent information retrieval systems without needing score normalization. Highly effective for merging lexical and semantic search results.",
        "takeaways": [
            "Formula RRF score = sum(1 / (k + rank)) where standard k is 60",
            "Prevents single retrieval systems with skewed score distributions from dominating",
            "Combines keyword search and semantic vector embeddings robustly"
        ],
        "tags": ["search", "algorithms", "hybrid-search", "ai"],
        "collection": "AI & Vectors",
        "content_text": "Reciprocal Rank Fusion (RRF) is an algorithmic technique for combining multiple search result lists into a single unified ranked result list. It calculates scores based on positional ranks.",
    },
]


async def seed() -> None:
    print("[*] Seeding RecallAI demo data...")
    provider = get_ai_provider()

    async with async_session_factory() as db:
        # Check or create demo user
        res = await db.execute(select(User).where(User.email == DEMO_USER_EMAIL))
        user = res.scalar_one_or_none()

        if not user:
            user = User(
                email=DEMO_USER_EMAIL,
                password_hash=hash_password(DEMO_USER_PASSWORD),
                display_name="Demo User",
            )
            db.add(user)
            await db.flush()
            print(f"  Created user: {DEMO_USER_EMAIL} (password: {DEMO_USER_PASSWORD})")
        else:
            print(f"  Existing user found: {DEMO_USER_EMAIL}")

        # Create collections
        collection_map = {}
        for item in DEMO_BOOKMARKS:
            col_name = item["collection"]
            if col_name not in collection_map:
                res = await db.execute(
                    select(Collection).where(
                        Collection.user_id == user.id,
                        Collection.name == col_name,
                    )
                )
                col = res.scalar_one_or_none()
                if not col:
                    col = Collection(user_id=user.id, name=col_name)
                    db.add(col)
                    await db.flush()
                collection_map[col_name] = col.id

        # Create bookmarks and chunks
        for item in DEMO_BOOKMARKS:
            res = await db.execute(
                select(Bookmark).where(
                    Bookmark.user_id == user.id,
                    Bookmark.canonical_url == item["canonical_url"],
                )
            )
            bm = res.scalar_one_or_none()

            if not bm:
                bm = Bookmark(
                    user_id=user.id,
                    url=item["url"],
                    canonical_url=item["canonical_url"],
                    title=item["title"],
                    summary=item["summary"],
                    key_takeaways=item["takeaways"],
                    content_text=item["content_text"],
                    collection_id=collection_map[item["collection"]],
                    status=BookmarkStatus.completed,
                )
                db.add(bm)
                await db.flush()

                # Add tags
                for tag_name in item["tags"]:
                    tag_res = await db.execute(
                        select(Tag).where(
                            Tag.user_id == user.id,
                            Tag.name == tag_name,
                        )
                    )
                    t = tag_res.scalar_one_or_none()
                    if not t:
                        t = Tag(user_id=user.id, name=tag_name)
                        db.add(t)
                        await db.flush()

                    db.add(BookmarkTag(bookmark_id=bm.id, tag_id=t.id, source=TagSource.ai))

                # Add content chunk and embedding
                try:
                    emb = await provider.embed_query(item["content_text"])
                except Exception:
                    # Fallback dummy embedding if offline
                    emb = [0.01 * (i % 50) for i in range(1536)]

                chunk = ContentChunk(
                    bookmark_id=bm.id,
                    user_id=user.id,
                    chunk_index=0,
                    chunk_text=item["content_text"],
                    embedding=emb,
                    model_name="demo-embed",
                )
                db.add(chunk)
                print(f"  Added bookmark: {item['title']}")

        await db.commit()
    print("[OK] Seed complete! You can log in with demo@recallai.local / password123")


if __name__ == "__main__":
    asyncio.run(seed())
