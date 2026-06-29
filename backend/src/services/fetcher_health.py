"""Fetcher health tracking — records per-fetcher success/failure to the
fetcher_health table for observability, tier classification, and alerting.

Best-effort: writes are wrapped in try/except so a DB failure never
crashes the pipeline.
"""

import logging
from datetime import datetime, timezone, timedelta

from src.db.database import get_db

logger = logging.getLogger(__name__)


def record_fetcher_health(
    fetcher_name: str,
    success: bool,
    error: str = "",
    result_count: int = 0,
) -> None:
    """Update the fetcher_health row for a single fetcher.

    Called after every fetch attempt. On success: records last_success,
    resets consecutive_failures, recalculates last_24h_success_rate.
    On failure: records last_failure + last_error, increments
    consecutive_failures.

    Args:
        fetcher_name: Unique fetcher identifier (e.g. 'market', 'credit').
        success: True if the fetch produced results.
        error: Error message on failure (empty string on success).
        result_count: Number of results produced (informational only).
    """
    try:
        conn = get_db()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Ensure the row exists
        conn.execute(
            "INSERT OR IGNORE INTO fetcher_health (fetcher_name) VALUES (?)",
            (fetcher_name,),
        )

        if success:
            # Calculate last 24h success rate: count all runs in last 24h,
            # then compute (successful / total).
            since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
            # We approximate by counting failures in last 24h from the
            # consecutive_failures pattern. For simplicity, we use a
            # sliding window: 1.0 if no failures lately, trending down
            # as consecutive_failures grows.
            row = conn.execute(
                "SELECT consecutive_failures FROM fetcher_health WHERE fetcher_name = ?",
                (fetcher_name,),
            ).fetchone()
            prev_failures = row["consecutive_failures"] if row else 0

            # Simple rate: assume ~24 runs/day (hourly). If there were
            # N consecutive failures, rate = 1 - N/24, clamped to [0,1].
            rate = max(0.0, 1.0 - prev_failures / 24.0)

            conn.execute(
                """UPDATE fetcher_health
                   SET last_success = ?,
                       consecutive_failures = 0,
                       last_24h_success_rate = ?
                   WHERE fetcher_name = ?""",
                (now, round(rate, 4), fetcher_name),
            )
        else:
            conn.execute(
                """UPDATE fetcher_health
                   SET last_failure = ?,
                       last_error = ?,
                       consecutive_failures = consecutive_failures + 1,
                       last_24h_success_rate = MAX(0.0, 1.0 - (consecutive_failures + 1) / 24.0)
                   WHERE fetcher_name = ?""",
                (now, error, fetcher_name),
            )

        conn.commit()
        conn.close()

        if success:
            logger.debug(
                "fetcher_health: %s succeeded (%d results)",
                fetcher_name,
                result_count,
            )
        else:
            logger.warning(
                "fetcher_health: %s failed — %s",
                fetcher_name,
                error[:200],
            )
    except Exception:
        logger.warning(
            "Failed to record fetcher_health for %s (non-fatal)",
            fetcher_name,
        )


def get_all_fetcher_health() -> dict[str, dict[str, object]]:
    """Read all fetcher health rows from the fetcher_health table.

    Returns a dict keyed by fetcher_name with values containing:
        last_success, last_failure, last_error, consecutive_failures,
        last_24h_success_rate.

    Returns an empty dict if the table is empty or unavailable.
    Best-effort: never raises.
    """
    try:
        conn = get_db()
        rows = conn.execute(
            "SELECT fetcher_name, last_success, last_failure, last_error, "
            "consecutive_failures, last_24h_success_rate "
            "FROM fetcher_health"
        ).fetchall()
        conn.close()
        result: dict[str, dict[str, object]] = {}
        for row in rows:
            result[row["fetcher_name"]] = {
                "last_success": row["last_success"],
                "last_failure": row["last_failure"],
                "last_error": row["last_error"],
                "consecutive_failures": row["consecutive_failures"],
                "last_24h_success_rate": row["last_24h_success_rate"],
            }
        return result
    except Exception:
        logger.warning("Failed to read fetcher_health (non-fatal)")
        return {}
