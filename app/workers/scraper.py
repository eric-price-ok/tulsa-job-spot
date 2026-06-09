import asyncio
import importlib
import logging
from datetime import datetime, date

import httpx

logger = logging.getLogger(__name__)


async def run_scraper(ctx: dict, source_id: int) -> None:
    """ARQ task: run a single scraper source by ID."""
    from sqlalchemy import select

    from ..database import AsyncSessionLocal
    from ..models.scraping import ScraperSource, ScrapingLog

    async with AsyncSessionLocal() as db:
        source = await db.get(ScraperSource, source_id)
        if source is None or not source.is_active:
            logger.warning("run_scraper: source %d not found or inactive", source_id)
            return

        log = ScrapingLog(
            job_board=source.name,
            company_id=source.company_id,
            status="running",
            started_at=datetime.now(),
        )
        db.add(log)
        await db.flush()
        log_id = log.id
        await db.commit()

    try:
        # Dynamically import scraper class from app.scrapers package
        module_path, class_name = source.scraper_class.rsplit(".", 1)
        module = importlib.import_module(module_path)
        scraper_cls = getattr(module, class_name)
        scraper = scraper_cls(source=source)
        result = await scraper.run()
        status = "success"
        errors = None
        jobs_found = result.get("found", 0)
        jobs_added = result.get("added", 0)
        jobs_updated = result.get("updated", 0)
        jobs_skipped = result.get("skipped", 0)
    except (ImportError, AttributeError) as exc:
        logger.error("run_scraper: scraper class '%s' not found: %s", source.scraper_class, exc)
        status = "error"
        errors = f"Scraper class not found: {exc}"
        jobs_found = jobs_added = jobs_updated = jobs_skipped = 0
    except Exception as exc:
        logger.exception("run_scraper: source %d failed: %s", source_id, exc)
        status = "error"
        errors = str(exc)
        jobs_found = jobs_added = jobs_updated = jobs_skipped = 0

    async with AsyncSessionLocal() as db:
        log = await db.get(ScrapingLog, log_id)
        if log:
            log.status = status
            log.errors = errors
            log.jobs_found = jobs_found
            log.jobs_added = jobs_added
            log.jobs_updated = jobs_updated
            log.jobs_skipped = jobs_skipped
            log.completed_at = datetime.now()

        source = await db.get(ScraperSource, source_id)
        if source:
            source.last_run_at = datetime.now()
            source.last_status = status

        await db.commit()

    logger.info(
        "run_scraper: source '%s' finished — status=%s found=%d added=%d",
        source.name if source else source_id, status, jobs_found, jobs_added,
    )


async def check_scrapers(ctx: dict) -> None:
    """Daily cron: enqueue run_scraper for every active source."""
    from sqlalchemy import select

    from ..database import AsyncSessionLocal
    from ..models.scraping import ScraperSource

    async with AsyncSessionLocal() as db:
        sources = (
            await db.execute(
                select(ScraperSource).where(ScraperSource.is_active == True)
            )
        ).scalars().all()
        source_ids = [s.id for s in sources]

    if not source_ids:
        logger.info("check_scrapers: no active sources")
        return

    try:
        import arq
        from arq.connections import RedisSettings
        from ..config import settings

        pool = await arq.create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
        for sid in source_ids:
            await pool.enqueue_job("run_scraper", sid)
        await pool.aclose()
        logger.info("check_scrapers: queued %d sources", len(source_ids))
    except Exception as exc:
        logger.error("check_scrapers: failed to enqueue: %s", exc)


async def check_listing_links(ctx: dict) -> None:
    """Daily cron: HEAD-check all active external_url listings; expire dead ones."""
    from sqlalchemy import select

    from ..database import AsyncSessionLocal
    from ..models.job import JobListing
    from ..models.reference import JobStatus

    async with AsyncSessionLocal() as db:
        active_status_id = await db.scalar(
            select(JobStatus.id).where(JobStatus.name == "active")
        )
        expired_status_id = await db.scalar(
            select(JobStatus.id).where(JobStatus.name == "expired")
        )

        listings = (
            await db.execute(
                select(JobListing).where(
                    JobListing.approved == True,
                    JobListing.job_status_id == active_status_id,
                    JobListing.application_method == "external_url",
                    JobListing.posting_url.isnot(None),
                )
            )
        ).scalars().all()

        if not listings:
            logger.info("check_listing_links: no listings to check")
            return

        # Check up to 10 URLs concurrently
        semaphore = asyncio.Semaphore(10)
        expired_ids: list[int] = []

        async def _check(listing: JobListing) -> None:
            async with semaphore:
                try:
                    async with httpx.AsyncClient(
                        follow_redirects=True, timeout=10.0
                    ) as client:
                        resp = await client.head(listing.posting_url)
                        if resp.status_code == 404:
                            expired_ids.append(listing.id)
                except Exception:
                    pass  # timeout, DNS error, etc. — skip this round

        await asyncio.gather(*[_check(l) for l in listings])

        for listing_id in expired_ids:
            listing = await db.get(JobListing, listing_id)
            if listing:
                listing.job_status_id = expired_status_id

        if expired_ids:
            await db.commit()

        logger.info(
            "check_listing_links: checked %d listings, expired %d",
            len(listings), len(expired_ids),
        )
