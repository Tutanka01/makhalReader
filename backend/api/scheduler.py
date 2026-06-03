"""
Background task scheduler for Baṣīra.

Uses APScheduler to run periodic jobs:
- Threat Scan: every 24 hours
- Author Radar: every 7 days
- Citation Index: every 7 days (offset from author radar)

All jobs create their own DB session, run, log, and store last_run_at in settings.
Manual triggers via POST endpoints continue to work independently.
"""
from __future__ import annotations

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = structlog.get_logger().bind(service="scheduler")

_scheduler: AsyncIOScheduler | None = None


def start_scheduler() -> AsyncIOScheduler:
    """Create and start the background scheduler. Called once at API startup."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    _scheduler = AsyncIOScheduler()
    _scheduler._logger = structlog.get_logger("apscheduler")

    _scheduler.add_job(
        _run_threat_scan_job,
        IntervalTrigger(hours=24),
        id="threat_scan_daily",
        replace_existing=True,
        name="Threat Scan (daily)",
    )

    _scheduler.add_job(
        _run_author_radar_job,
        IntervalTrigger(days=7),
        id="author_radar_weekly",
        replace_existing=True,
        name="Author Radar (weekly)",
    )

    _scheduler.add_job(
        _run_citation_index_job,
        IntervalTrigger(days=7),
        id="citation_index_weekly",
        replace_existing=True,
        name="Citation Index (weekly)",
        # Offset from author radar by 1 hour so they don't clash
        next_run_time=None,
    )

    _scheduler.start()
    logger.info("scheduler_started", jobs=["threat_scan", "author_radar", "citation_index"])
    return _scheduler


def stop_scheduler() -> None:
    """Shut down the scheduler gracefully. Called at API shutdown."""
    global _scheduler
    if _scheduler is None:
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None
    logger.info("scheduler_stopped")


# ── Job wrappers ──────────────────────────────────────────────────────────────


async def _run_threat_scan_job() -> None:
    """Wrapper: create DB session, run threat scan for every active user."""
    from datetime import datetime, timezone

    from database import SessionLocal, User, set_setting

    db = SessionLocal()
    try:
        from routers.research import _run_threat_scan  # noqa: PLC0415

        user_ids = [u.id for u in db.query(User.id).all()]
        for uid in user_ids:
            try:
                result = await _run_threat_scan(db, user_id=uid, window_days=7)
                logger.info(
                    "scheduler_threat_scan_done",
                    user_id=uid,
                    scanned=result.scanned,
                    alerts_created=result.alerts_created,
                    skipped=result.skipped,
                )
            except Exception as e:
                logger.warning("scheduler_threat_scan_user_failed", user_id=uid, error=str(e))
                continue
        set_setting(db, "threat_scan_last_run_at", datetime.now(timezone.utc).isoformat())
    except Exception as e:
        logger.error("scheduler_threat_scan_failed", error=str(e))
    finally:
        db.close()


async def _run_author_radar_job() -> None:
    """Wrapper: create DB session, run author radar for every active user."""
    from datetime import datetime, timezone

    from database import SessionLocal, User, set_setting

    db = SessionLocal()
    try:
        from author_radar import run_author_radar_scan  # noqa: PLC0415

        user_ids = [u.id for u in db.query(User.id).all()]
        for uid in user_ids:
            try:
                result = await run_author_radar_scan(db, user_id=uid)
                logger.info(
                    "scheduler_author_radar_done",
                    user_id=uid,
                    authors_checked=result.authors_checked,
                    new_articles_queued=result.new_articles_queued,
                    skipped=result.skipped,
                )
            except Exception as e:
                logger.warning("scheduler_author_radar_user_failed", user_id=uid, error=str(e))
                continue
        set_setting(db, "author_radar_last_run_at", datetime.now(timezone.utc).isoformat())
    except Exception as e:
        logger.error("scheduler_author_radar_failed", error=str(e))
    finally:
        db.close()


async def _run_citation_index_job() -> None:
    """Wrapper: create DB session, run citation index, log result."""
    from datetime import datetime, timezone

    from database import SessionLocal, set_setting

    db = SessionLocal()
    try:
        from citation_indexer import index_citations  # noqa: PLC0415

        result = await index_citations(db)
        logger.info(
            "scheduler_citation_index_done",
            indexed_papers=result.get("indexed_papers", 0),
            total_citation_links=result.get("total_citation_links", 0),
        )
    except Exception as e:
        logger.error("scheduler_citation_index_failed", error=str(e))
    finally:
        db.close()
