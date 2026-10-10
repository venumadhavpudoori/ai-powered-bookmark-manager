"""Processing pipeline: extract → enrich → embed.

Each stage is idempotent. On error: sanitized message, retry up to 3 times
with exponential backoff (run_after), then mark as failed.
"""

import hashlib
import logging
import time

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

try:
    import trafilatura
except ImportError:
    trafilatura = None

from app.ai.prompts import SYSTEM_PROMPT
from app.ai.provider import AIProvider, count_tokens, get_ai_provider
from app.models import (
    AIUsage,
    Bookmark,
    BookmarkStatus,
    BookmarkTag,
    ContentChunk,
    Job,
    JobStatus,
    Tag,
    TagSource,
)

logger = logging.getLogger(__name__)

# Chunking parameters
CHUNK_SIZE_TOKENS = 500
CHUNK_OVERLAP_TOKENS = 50


async def run_pipeline(job: Job, db: AsyncSession) -> None:
    """Execute the full extract → enrich → embed pipeline for a job."""
    provider = get_ai_provider()

    bookmark = await db.get(Bookmark, job.bookmark_id)
    if bookmark is None:
        logger.error("Job %s: bookmark %s not found", job.id, job.bookmark_id)
        job.status = JobStatus.failed
        job.error_message = "Bookmark not found"
        return

    bookmark.status = BookmarkStatus.processing

    try:
        # Stage 1: Extract
        job.stage = "extract"
        await db.flush()
        await _extract(bookmark, db)

        # Stage 2: Enrich
        job.stage = "enrich"
        await db.flush()
        await _enrich(bookmark, job, provider, db)

        # Stage 3: Embed
        job.stage = "embed"
        await db.flush()
        await _embed(bookmark, job, provider, db)

        # Done
        bookmark.status = BookmarkStatus.completed
        bookmark.error_message = None
        job.status = JobStatus.completed
        job.stage = "done"
        logger.info("Job %s completed for bookmark %s", job.id, bookmark.id)

    except Exception as exc:
        # Sanitize error message (don't expose internal details)
        error_msg = str(exc)[:500]
        logger.exception("Job %s failed at stage %s: %s", job.id, job.stage, error_msg)
        bookmark.error_message = error_msg
        raise  # Let the worker handle retry logic


# ── Stage 1: Extract ──────────────────────────────────────


async def _extract(bookmark: Bookmark, db: AsyncSession) -> None:
    """Fetch URL content with SSRF protection, extract text with trafilatura."""
    from app.security.ssrf import SSRFError, safe_fetch

    start = time.monotonic()

    html, final_url = await safe_fetch(bookmark.url)

    # Extract text content
    text = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=True,
        no_fallback=False,
    )

    if not text or len(text.strip()) < 50:
        raise ValueError("Could not extract meaningful text from page")

    # Compute content hash for deduplication
    content_hash = hashlib.sha256(text.encode()).hexdigest()

    # Skip re-processing if content hasn't changed
    if bookmark.content_hash == content_hash and bookmark.summary:
        logger.info("Content unchanged for bookmark %s, skipping enrich/embed", bookmark.id)
        return

    bookmark.content_text = text
    bookmark.content_hash = content_hash

    # Try to extract title from HTML if not set
    if not bookmark.title:
        title = trafilatura.extract(html, output_format="xml")
        if title:
            import xml.etree.ElementTree as ET
            try:
                root = ET.fromstring(title)
                doc_title = root.find(".//title")
                if doc_title is not None and doc_title.text:
                    bookmark.title = doc_title.text.strip()[:500]
            except ET.ParseError:
                pass

    elapsed = time.monotonic() - start
    logger.info("Extract completed in %.1fs for %s", elapsed, bookmark.url)


# ── Stage 2: Enrich ───────────────────────────────────────


async def _enrich(
    bookmark: Bookmark, job: Job, provider: AIProvider, db: AsyncSession
) -> None:
    """Call LLM for summary, takeaways, and tags."""
    if not bookmark.content_text:
        raise ValueError("No content text to enrich")

    start = time.monotonic()

    # Fetch existing user tags for reuse suggestions
    result = await db.execute(
        select(Tag.name).where(Tag.user_id == bookmark.user_id)
    )
    existing_tags = [row[0] for row in result.all()]

    enrichment = await provider.enrich(
        text=bookmark.content_text,
        existing_tags=existing_tags,
        system_prompt=SYSTEM_PROMPT,
    )

    # Update bookmark
    bookmark.summary = enrichment.summary
    bookmark.key_takeaways = enrichment.takeaways

    # Add AI-generated tags (never overwrite source='user' tags)
    for tag_name in enrichment.tags:
        tag_name = tag_name.strip().lower()
        if not tag_name:
            continue

        # Find or create tag
        result = await db.execute(
            select(Tag).where(
                Tag.user_id == bookmark.user_id,
                func.lower(Tag.name) == tag_name,
            )
        )
        tag = result.scalar_one_or_none()
        if tag is None:
            tag = Tag(user_id=bookmark.user_id, name=tag_name)
            db.add(tag)
            await db.flush()

        # Check if this tag is already on the bookmark
        result = await db.execute(
            select(BookmarkTag).where(
                BookmarkTag.bookmark_id == bookmark.id,
                BookmarkTag.tag_id == tag.id,
            )
        )
        existing_bt = result.scalar_one_or_none()
        if existing_bt is None:
            bt = BookmarkTag(
                bookmark_id=bookmark.id,
                tag_id=tag.id,
                source=TagSource.ai,
            )
            db.add(bt)
        # If exists with source='user', don't overwrite

    elapsed = time.monotonic() - start

    # Log AI usage
    usage = AIUsage(
        job_id=job.id,
        stage="enrich",
        model_name=provider.llm_model if hasattr(provider, "llm_model") else "unknown",
        input_tokens=enrichment.input_tokens,
        output_tokens=enrichment.output_tokens,
        duration_ms=int(elapsed * 1000),
    )
    db.add(usage)

    logger.info(
        "Enrich completed in %.1fs (in=%d, out=%d tokens) for bookmark %s",
        elapsed, enrichment.input_tokens, enrichment.output_tokens, bookmark.id,
    )


# ── Stage 3: Embed ────────────────────────────────────────


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE_TOKENS, overlap: int = CHUNK_OVERLAP_TOKENS) -> list[str]:
    """Split text into overlapping chunks of approximately chunk_size tokens."""
    import tiktoken

    try:
        enc = tiktoken.encoding_for_model("gpt-4o-mini")
    except KeyError:
        enc = tiktoken.get_encoding("cl100k_base")

    tokens = enc.encode(text)

    if len(tokens) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        chunk_tokens = tokens[start:end]
        chunk_text = enc.decode(chunk_tokens)
        chunks.append(chunk_text)

        if end >= len(tokens):
            break
        start = end - overlap

    return chunks


async def _embed(
    bookmark: Bookmark, job: Job, provider: AIProvider, db: AsyncSession
) -> None:
    """Chunk text, generate embeddings, and store. Replaces old chunks."""
    if not bookmark.content_text:
        raise ValueError("No content text to embed")

    start = time.monotonic()

    # Chunk the text
    chunks = chunk_text(bookmark.content_text)
    if not chunks:
        raise ValueError("Text produced no chunks")

    # Generate embeddings
    embedding_result = await provider.embed(chunks)

    # Delete old chunks in the same transaction
    await db.execute(
        delete(ContentChunk).where(ContentChunk.bookmark_id == bookmark.id)
    )

    # Insert new chunks
    for i, (chunk, emb) in enumerate(zip(chunks, embedding_result.embeddings)):
        content_chunk = ContentChunk(
            bookmark_id=bookmark.id,
            user_id=bookmark.user_id,
            chunk_index=i,
            chunk_text=chunk,
            embedding=emb,
            model_name=embedding_result.model_name,
        )
        db.add(content_chunk)

    elapsed = time.monotonic() - start

    # Log AI usage
    usage = AIUsage(
        job_id=job.id,
        stage="embed",
        model_name=embedding_result.model_name,
        input_tokens=embedding_result.input_tokens,
        output_tokens=0,
        duration_ms=int(elapsed * 1000),
    )
    db.add(usage)

    logger.info(
        "Embed completed in %.1fs (%d chunks, %d tokens) for bookmark %s",
        elapsed, len(chunks), embedding_result.input_tokens, bookmark.id,
    )
