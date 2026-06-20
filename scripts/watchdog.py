#!/usr/bin/env python3
"""Crisis Monitor watchdog — polls /api/system/health and alerts on issues.

Alerts on:
  - API down (status != "ok")
  - DB unreachable (db != "ok")
  - Stale pipeline (last_pipeline_run > 26h ago)
  - Excessive errors (last_24h_errors > 5)

Does NOT alert on fallback_dots (per decision — fallbacks are expected during
API outages and handled gracefully by the system).

Silent on success — only emits output when there's a problem to report.
"""

import json
import urllib.request
import sys
from datetime import datetime, timezone, timedelta

HEALTH_URL = "http://localhost:8000/api/system/health"
TIMEOUT_SEC = 10
STALE_PIPELINE_HOURS = 26
MAX_ERRORS = 5


def fetch_health() -> dict | None:
    """Fetch the health endpoint. Returns parsed JSON, or None on failure."""
    try:
        req = urllib.request.Request(HEALTH_URL)
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            data = json.loads(resp.read().decode())
            return data
    except Exception as e:
        print(f"CRISIS MONITOR WATCHDOG: API unreachable — {e}", file=sys.stderr)
        return None


def check_pipeline_stale(last_pipeline_run: str | None) -> bool:
    """Return True if last pipeline run is older than STALE_PIPELINE_HOURS."""
    if last_pipeline_run is None:
        return True  # No runs at all
    try:
        last = datetime.fromisoformat(last_pipeline_run.replace("Z", "+00:00"))
        cutoff = datetime.now(timezone.utc) - timedelta(hours=STALE_PIPELINE_HOURS)
        return last < cutoff
    except (ValueError, TypeError):
        return True


def main() -> int:
    data = fetch_health()
    if data is None:
        # API entirely down
        print("ALERT: Crisis Monitor API is DOWN — /api/system/health returned no response")
        return 1

    alerts = []

    # Check overall status
    status = data.get("status", "unknown")
    if status != "ok":
        alerts.append(f"API status is '{status}' (expected 'ok')")

    # Check DB
    db_status = data.get("db", "unknown")
    if db_status != "ok":
        alerts.append(f"DB is '{db_status}' (expected 'ok')")

    # Check pipeline freshness
    last_run = data.get("last_pipeline_run")
    if check_pipeline_stale(last_run):
        if last_run:
            alerts.append(f"Pipeline stale — last run was {last_run} (>26h ago)")
        else:
            alerts.append("Pipeline never run — no pipeline runs found")

    # Check error count
    errors = data.get("last_24h_errors", 0)
    if isinstance(errors, (int, float)) and errors > MAX_ERRORS:
        alerts.append(f"High error count — {errors} errors in last 24h (threshold: {MAX_ERRORS})")

    if alerts:
        print("ALERT: Crisis Monitor issues detected:")
        for a in alerts:
            print(f"  - {a}")
        print(f"  Full health: {json.dumps(data, indent=2)}")
        return 2

    # All good — silent exit
    return 0


if __name__ == "__main__":
    sys.exit(main())
