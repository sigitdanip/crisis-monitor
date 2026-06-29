"""In-process daily pipeline scheduler.

Runs the crisis-monitor pipeline at 8am WIB daily, inside the FastAPI
process. No external cron, no HTTP roundtrip, no auth header needed.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.services.pipeline_runner import execute_pipeline, _load_last_run_from_db
from src.services.trigger_idempotency import find_recent_report

logger = logging.getLogger("crisis_monitor.scheduler")
WIB = timezone(timedelta(hours=7))

_scheduler: AsyncIOScheduler | None = None
_last_run: dict | None = None  # shared with routes.py for /api/pipeline/status


async def _run_pipeline_job() -> None:
    """The 8am daily pipeline job — called by APScheduler."""
    global _last_run
    logger.info("scheduler: daily pipeline job starting")
    try:
        result = await execute_pipeline("scheduler")
        _last_run = result
        logger.info(
            "scheduler: pipeline completed — score=%s",
            result.get("composite_score", {}).get("composite", "?"),
        )
    except Exception:
        logger.exception("scheduler: pipeline failed")


async def _recover_missed_run() -> None:
    """If the app restarted and today's run is missing, fire it now.

    Only fires once per process startup. Idempotent via the
    find_recent_report check inside the pipeline.
    """
    existing = find_recent_report("scheduler")
    if existing:
        logger.info(
            "scheduler: today's run already exists (id=%s) — skipping recovery",
            existing.get("id", "?"),
        )
        return
    now_wib = datetime.now(WIB)
    # Only recover if it's past 8am today (otherwise wait for the cron)
    if now_wib.hour >= 8:
        logger.warning("scheduler: today's 8am run missing — triggering recovery")
        await _run_pipeline_job()
    else:
        logger.info(
            "scheduler: not yet 8am (%s) — waiting for scheduled trigger", now_wib,
        )


def start_scheduler() -> None:
    """Start the scheduler. Idempotent — safe to call multiple times."""
    global _scheduler, _last_run

    if _scheduler is not None:
        return

    # Load the most recent run from DB into the _last_run cache
    _last_run = _load_last_run_from_db()
    if _last_run:
        logger.info(
            "scheduler: loaded last run from DB — completed_at=%s",
            _last_run.get("completed_at", "?"),
        )

    _scheduler = AsyncIOScheduler(timezone=WIB)
    _scheduler.add_job(
        _run_pipeline_job,
        CronTrigger(hour=8, minute=0, timezone=WIB),
        id="daily-pipeline",
        name="Daily crisis-monitor pipeline (8am WIB)",
        misfire_grace_time=3600,  # if missed, fire within 1 hour of next check
        coalesce=True,  # if multiple missed, only fire once
    )
    _scheduler.start()
    job = _scheduler.get_job("daily-pipeline")
    logger.info("scheduler: started, next run=%s", job.next_run_time if job else "unknown")

    # Check for missed runs on startup (only if past 8am and no recent run)
    asyncio.get_running_loop().create_task(_recover_missed_run())


def stop_scheduler() -> None:
    """Shut down the scheduler gracefully."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("scheduler: stopped")


def get_last_run() -> dict | None:
    """Used by /api/pipeline/status to surface the in-process result."""
    return _last_run


def set_last_run(result: dict) -> None:
    """Called by routes.py after an API-triggered pipeline completes.

    Keeps the in-process _last_run cache in sync so /api/pipeline/status
    reflects the most recent result regardless of trigger source.
    """
    global _last_run
    _last_run = result


def get_scheduler_info() -> dict:
    """Return scheduler metadata for /api/pipeline/status."""
    if _scheduler is None:
        return {
            "enabled": False,
            "next_run": None,
            "timezone": "Asia/Jakarta",
        }

    job = _scheduler.get_job("daily-pipeline")
    next_run = job.next_run_time.isoformat() if job and job.next_run_time else None

    return {
        "enabled": True,
        "next_run": next_run,
        "timezone": "Asia/Jakarta",
    }
