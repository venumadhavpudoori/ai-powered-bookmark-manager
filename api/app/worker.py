"""Background worker that polls the jobs table and runs the processing pipeline.

Uses SELECT ... FOR UPDATE SKIP LOCKED to safely claim jobs without Redis/Celery.
Retries up to 3 times with exponential backoff.
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_factory
from app.models import Bookmark, BookmarkStatus, Job, JobStatus
from app.pipeline import run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 30  # 30s, 60s, 120s


async def claim_jobs(db: AsyncSession, batch_size: int) -> list[Job]:
    """Claim up to batch_size queued jobs using FOR UPDATE SKIP LOCKED."""
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(Job)
        .where(
            Job.status == JobStatus.queued,
            # Only pick jobs whose run_after has passed (or is null)
            (Job.run_after <= now) | (Job.run_after.is_(None)),
        )
        .order_by(Job.created_at)
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )
    jobs = list(result.scalars().all())

    # Mark as running
    for job in jobs:
        job.status = JobStatus.running
        job.attempt_count += 1

    await db.flush()
    return jobs


async def process_job(job: Job) -> None:
    """Process a single job in its own DB session (own transaction)."""
    async with async_session_factory() as db:
        try:
            # Re-fetch the job within this session
            result = await db.execute(select(Job).where(Job.id == job.id))
            job = result.scalar_one()

            await run_pipeline(job, db)
            await db.commit()

        except Exception as exc:
            await db.rollback()

            # Handle retry in a new session
            async with async_session_factory() as retry_db:
                result = await retry_db.execute(select(Job).where(Job.id == job.id))
                failed_job = result.scalar_one()

                error_msg = str(exc)[:500]

                if failed_job.attempt_count < MAX_RETRIES:
                    # Schedule retry with exponential backoff
                    delay = BACKOFF_BASE_SECONDS * (2 ** (failed_job.attempt_count - 1))
                    failed_job.status = JobStatus.queued
                    failed_job.run_after = datetime.now(timezone.utc) + timedelta(seconds=delay)
                    failed_job.error_message = error_msg
                    logger.warning(
                        "Job %s failed (attempt %d/%d), retrying in %ds: %s",
                        failed_job.id, failed_job.attempt_count, MAX_RETRIES, delay, error_msg,
                    )
                else:
                    # Max retries exceeded — mark as permanently failed
                    failed_job.status = JobStatus.failed
                    failed_job.error_message = error_msg

                    # Also mark the bookmark as failed
                    result = await retry_db.execute(
                        select(Bookmark).where(Bookmark.id == failed_job.bookmark_id)
                    )
                    bookmark = result.scalar_one_or_none()
                    if bookmark:
                        bookmark.status = BookmarkStatus.failed
                        bookmark.error_message = error_msg

                    logger.error(
                        "Job %s permanently failed after %d attempts: %s",
                        failed_job.id, MAX_RETRIES, error_msg,
                    )

                await retry_db.commit()


async def worker_loop() -> None:
    """Main worker loop: poll for jobs, process them, sleep, repeat."""
    logger.info(
        "Worker started (poll_interval=%ds, batch_size=%d)",
        settings.WORKER_POLL_INTERVAL,
        settings.WORKER_BATCH_SIZE,
    )

    while True:
        try:
            async with async_session_factory() as db:
                jobs = await claim_jobs(db, settings.WORKER_BATCH_SIZE)
                await db.commit()

            if jobs:
                logger.info("Claimed %d job(s)", len(jobs))
                # Process jobs sequentially to limit resource usage
                for job in jobs:
                    await process_job(job)
            else:
                await asyncio.sleep(settings.WORKER_POLL_INTERVAL)

        except Exception:
            logger.exception("Worker loop error")
            await asyncio.sleep(settings.WORKER_POLL_INTERVAL)


def main() -> None:
    """Entry point for python -m app.worker."""
    asyncio.run(worker_loop())


if __name__ == "__main__":
    main()
