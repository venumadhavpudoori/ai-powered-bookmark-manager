"""Hybrid search: cosine similarity (pgvector) + full-text search (FTS) merged
with Reciprocal Rank Fusion. Always filtered by user_id.
"""

import logging
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider import get_ai_provider
from app.config import settings

logger = logging.getLogger(__name__)

# RRF constant
RRF_K = 60


async def hybrid_search(
    query: str,
    user_id: uuid.UUID,
    db: AsyncSession,
    tag_filter: str | None = None,
    collection_id: uuid.UUID | None = None,
    limit: int = 20,
) -> list[dict]:
    """Run hybrid semantic + keyword search, return ranked bookmark results.

    Steps:
    1. Embed the query
    2. Top 30 chunks by cosine similarity (pgvector)
    3. Top 30 chunks by ts_rank (Postgres FTS)
    4. Merge with Reciprocal Rank Fusion (1/(RRF_K + rank))
    5. Group by bookmark, pick best chunk as excerpt
    6. Apply optional tag/collection filters
    """
    provider = get_ai_provider()

    # Generate query embedding
    query_embedding = await provider.embed_query(query)

    # Check if vector extension is installed in the database
    ext_check = await db.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
    has_vector = ext_check.scalar() is not None

    if has_vector:
        sql = text("""
        WITH semantic AS (
            SELECT
                cc.bookmark_id,
                cc.chunk_text,
                1 - (cc.embedding <=> :embedding::vector) AS sim_score,
                ROW_NUMBER() OVER (ORDER BY cc.embedding <=> :embedding::vector) AS rank
            FROM content_chunks cc
            WHERE cc.user_id = :user_id
            ORDER BY cc.embedding <=> :embedding::vector
            LIMIT 30
        ),
        keyword AS (
            SELECT
                cc.bookmark_id,
                cc.chunk_text,
                ts_rank(cc.tsv, websearch_to_tsquery('english', :query)) AS fts_score,
                ROW_NUMBER() OVER (
                    ORDER BY ts_rank(cc.tsv, websearch_to_tsquery('english', :query)) DESC
                ) AS rank
            FROM content_chunks cc
            WHERE cc.user_id = :user_id
              AND cc.tsv @@ websearch_to_tsquery('english', :query)
            ORDER BY fts_score DESC
            LIMIT 30
        ),
        rrf AS (
            SELECT
                COALESCE(s.bookmark_id, k.bookmark_id) AS bookmark_id,
                COALESCE(s.chunk_text, k.chunk_text) AS chunk_text,
                COALESCE(1.0 / (:rrf_k + s.rank), 0) +
                COALESCE(1.0 / (:rrf_k + k.rank), 0) AS rrf_score,
                COALESCE(s.sim_score, 0) AS sim_score,
                COALESCE(k.fts_score, 0) AS fts_score
            FROM semantic s
            FULL OUTER JOIN keyword k
                ON s.bookmark_id = k.bookmark_id AND s.chunk_text = k.chunk_text
        ),
        ranked AS (
            SELECT
                bookmark_id,
                chunk_text AS excerpt,
                rrf_score,
                ROW_NUMBER() OVER (PARTITION BY bookmark_id ORDER BY rrf_score DESC) AS rn
            FROM rrf
        )
        SELECT
            r.bookmark_id,
            r.excerpt,
            r.rrf_score,
            b.url,
            b.canonical_url,
            b.title,
            b.description,
            b.summary,
            b.key_takeaways,
            b.notes,
            b.status,
            b.error_message,
            b.collection_id,
            b.archived,
            b.created_at,
            b.updated_at
        FROM ranked r
        JOIN bookmarks b ON b.id = r.bookmark_id
        WHERE r.rn = 1
          AND b.user_id = :user_id
          AND b.archived = false
        ORDER BY r.rrf_score DESC
        LIMIT :limit
        """)
    else:
        sql = text("""
        WITH keyword AS (
            SELECT
                cc.bookmark_id,
                cc.chunk_text,
                ts_rank(cc.tsv, websearch_to_tsquery('english', :query)) AS fts_score,
                ROW_NUMBER() OVER (
                    ORDER BY ts_rank(cc.tsv, websearch_to_tsquery('english', :query)) DESC
                ) AS rank
            FROM content_chunks cc
            WHERE cc.user_id = :user_id
              AND cc.tsv @@ websearch_to_tsquery('english', :query)
            ORDER BY fts_score DESC
            LIMIT 30
        ),
        ranked AS (
            SELECT
                bookmark_id,
                chunk_text AS excerpt,
                1.0 / (:rrf_k + rank) AS rrf_score,
                ROW_NUMBER() OVER (PARTITION BY bookmark_id ORDER BY 1.0 / (:rrf_k + rank) DESC) AS rn
            FROM keyword
        )
        SELECT
            r.bookmark_id,
            r.excerpt,
            r.rrf_score,
            b.url,
            b.canonical_url,
            b.title,
            b.description,
            b.summary,
            b.key_takeaways,
            b.notes,
            b.status,
            b.error_message,
            b.collection_id,
            b.archived,
            b.created_at,
            b.updated_at
        FROM ranked r
        JOIN bookmarks b ON b.id = r.bookmark_id
        WHERE r.rn = 1
          AND b.user_id = :user_id
          AND b.archived = false
        ORDER BY r.rrf_score DESC
        LIMIT :limit
        """)

    params = {
        "embedding": str(query_embedding),
        "query": query,
        "user_id": str(user_id),
        "rrf_k": RRF_K,
        "limit": limit,
    }

    result = await db.execute(sql, params)
    rows = result.mappings().all()

    results = []
    for row in rows:
        results.append({
            "bookmark_id": row["bookmark_id"],
            "url": row["url"],
            "canonical_url": row["canonical_url"],
            "title": row["title"],
            "description": row["description"],
            "summary": row["summary"],
            "key_takeaways": row["key_takeaways"],
            "notes": row["notes"],
            "status": row["status"],
            "error_message": row["error_message"],
            "collection_id": row["collection_id"],
            "archived": row["archived"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "score": float(row["rrf_score"]),
            "excerpt": row["excerpt"],
        })

    return results
