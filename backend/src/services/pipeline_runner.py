"""Shared pipeline execution — called by both the HTTP trigger and the scheduler.

This module owns the core "fetch -> run -> persist" logic so that
routes.py (HTTP) and scheduler.py (in-process cron) both go through
the same code path. No auth, no idempotency, no progress tracking —
those are caller concerns.
"""

import json
import logging
from typing import Callable, Awaitable, Optional

from src.agent.graph import run_pipeline
from src.agent.normalize import fetch_and_normalize
from src.db.database import get_db

logger = logging.getLogger("crisis_monitor.pipeline_runner")


def _save_last_run_to_db(run_data: dict) -> None:
    """Persist pipeline run data to the pipeline_runs table."""
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO pipeline_runs (run_data) VALUES (?)",
            (json.dumps(run_data),),
        )
        conn.commit()
        conn.close()
    except Exception:
        logger.warning("Failed to persist pipeline run to DB")


def _load_last_run_from_db() -> dict | None:
    """Load the most recent pipeline run from the pipeline_runs table."""
    try:
        conn = get_db()
        row = conn.execute(
            "SELECT run_data FROM pipeline_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if row:
            return json.loads(row["run_data"])
    except Exception:
        logger.warning("Failed to load last pipeline run from DB")
    return None


async def execute_pipeline(
    source: str,
    progress_callback: Optional[Callable[[str, str, Optional[str]], Awaitable[None]]] = None,
) -> dict:
    """Run the full pipeline: fetch indicators/news, run the graph, persist.

    Args:
        source: "api" or "scheduler" — used for idempotency tracking.
        progress_callback: Optional async callback for live progress
            (used by the HTTP trigger for /api/pipeline/status polling).

    Returns:
        Pipeline result dict with node timing, scores, etc.
    """
    import asyncio
    import time

    t0 = time.time()
    logger.info("Pipeline [%s]: fetching indicators and news", source)

    indicators, news = await asyncio.to_thread(fetch_and_normalize)
    fetch_dur = int((time.time() - t0) * 1000)
    logger.info(
        "Pipeline [%s]: fetchers completed in %dms — %d indicators loaded",
        source, fetch_dur, len(indicators),
    )

    result = await run_pipeline(indicators, news, source=source, progress_callback=progress_callback)
    _save_last_run_to_db(result)

    total_ms = int((time.time() - t0) * 1000)
    logger.info(
        "Pipeline [%s]: completed in %dms — score=%s, end_state=%s",
        source,
        total_ms,
        result.get("composite_score", {}).get("composite", "?"),
        result.get("end_state", {}).get("end_state", "?"),
    )

    return result
