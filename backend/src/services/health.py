"""Health aggregation service for /api/system/health endpoint.

Aggregates DB connectivity, last pipeline run, 24h error/fallback counts,
current model, and process uptime. Resilient: never crashes on DB failures.
"""

import logging
import os
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from src.db.database import get_db

logger = logging.getLogger("crisis_monitor.health")

# Process start time (set on import)
_PROCESS_START = time.time()

# Log file path — anchored to this file's backend root, no hardcoded /root/ path.
# health.py lives at src/services/health.py; parents[2] is the backend/ root.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_LOG_PATH = os.environ.get(
    "CRISIS_LOG_PATH",
    str(_BACKEND_ROOT / "server.log"),
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check_db() -> tuple[str, str | None, int, int]:
    """Check DB connectivity and collect health metrics.

    Returns: (db_status, last_pipeline_run_iso, last_24h_errors, last_24h_fallbacks)
    """
    try:
        conn = get_db()
    except Exception:
        logger.warning("DB unreachable during health check")
        return ("unreachable", None, 0, 0)

    last_run: str | None = None
    error_count = 0
    fallback_count = 0

    try:
        # Last successful pipeline run from daily_reports
        row = conn.execute(
            "SELECT created_at FROM daily_reports ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if row:
            last_run = row["created_at"]

        # Count fallback dot analyses in last 24h
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM dot_analyses WHERE status='fallback' AND analyzed_at >= ?",
            (cutoff,),
        ).fetchone()
        if row:
            fallback_count = row["cnt"]

    except Exception:
        logger.warning("DB query failed during health check")
        conn.close()
        return ("degraded", None, 0, 0)

    conn.close()

    # Count ERROR/Traceback lines in log file (last 24h)
    error_count = _count_recent_errors()

    return ("ok", last_run, error_count, fallback_count)


def _count_recent_errors() -> int:
    """Count ERROR and Traceback lines in the server log from the last 24 hours."""
    try:
        if not os.path.exists(_LOG_PATH):
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        count = 0
        with open(_LOG_PATH, "r") as f:
            for line in f:
                # Quick timestamp check — only parse if line could be recent
                if ("ERROR" in line or "Traceback" in line):
                    # Extract timestamp prefix: "2026-06-20 14:22:01,234"
                    match = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
                    if match:
                        try:
                            ts = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
                            ts = ts.replace(tzinfo=timezone.utc)
                            if ts >= cutoff:
                                count += 1
                        except ValueError:
                            continue
        return count
    except Exception:
        logger.warning("Failed to parse log file for error counting")
        return 0


def get_health() -> dict:
    """Return a complete health check dict matching the documented contract.

    Contract:
        {
            "status": "ok" | "degraded" | "down",
            "db": "ok" | "unreachable",
            "last_pipeline_run": "<iso8601 or null>",
            "last_24h_errors": <int>,
            "last_24h_fallbacks": <int>,
            "model": "mimo-v2.5",
            "uptime_seconds": <int>
        }
    """
    db_status, last_run, errors, fallbacks = _check_db()

    model = os.environ.get("LLM_MODEL", "mimo-v2.5")
    uptime = int(time.time() - _PROCESS_START)

    # Determine overall status
    if db_status == "unreachable":
        overall = "down"
    elif errors > 5 or fallbacks > 3:
        overall = "degraded"
    else:
        overall = "ok"

    return {
        "status": overall,
        "db": db_status,
        "last_pipeline_run": last_run,
        "last_24h_errors": errors,
        "last_24h_fallbacks": fallbacks,
        "model": model,
        "uptime_seconds": uptime,
    }
