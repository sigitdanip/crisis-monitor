"""Trigger idempotency check — prevents duplicate pipeline runs.

When POST /api/trigger/daily is called within 5 minutes of a previous
run with the same trigger_source, the second call returns the existing
report instead of starting a new pipeline.

Per-source tracking: a "scheduler" run within 5 minutes does NOT block
an "api" trigger, and vice versa. Each source has its own window.
"""

import logging
from datetime import datetime, timezone, timedelta

from src.db.database import get_db

logger = logging.getLogger("crisis_monitor.idempotency")

IDEMPOTENCY_WINDOW_MINUTES = 5


def find_recent_report(trigger_source: str) -> dict | None:
    """Check for a recent daily_report with the same trigger_source.

    Returns the report dict if one exists within the idempotency window,
    or None if the trigger should proceed.
    """
    try:
        conn = get_db()
        cutoff = (
            datetime.now(timezone.utc) - timedelta(minutes=IDEMPOTENCY_WINDOW_MINUTES)
        ).strftime("%Y-%m-%d %H:%M:%S")

        row = conn.execute(
            "SELECT id, date, end_state, composite_score, confidence, "
            "synthesis, briefing, created_at, trigger_source "
            "FROM daily_reports "
            "WHERE created_at >= ? AND trigger_source = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (cutoff, trigger_source),
        ).fetchone()
        conn.close()

        if row:
            logger.info(
                "Idempotency check: found recent report id=%s source=%s created=%s — returning existing",
                row["id"],
                trigger_source,
                row["created_at"],
            )
            return dict(row)
        return None
    except Exception:
        logger.warning("Idempotency check failed — proceeding with trigger")
        return None
