"""Request metrics middleware — tracks counts, errors, and latency for /api/status.

Uses in-memory data structures with time-based pruning:
- _request_times: deque of (timestamp, status_code) for the last 24h
- _latencies: deque of the last 100 request latencies (ms)
- _process_start: time.time() at module import (uptime baseline)

Thread-safe: FastAPI/Starlette runs async on a single event loop thread;
no locks needed for these simple data structures.
"""

import logging
import os
import time
from collections import deque
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("crisis_monitor.metrics")

# ── Metrics state ──────────────────────────────────────────────────────────

_PROCESS_START: float = time.time()
_request_times: deque[tuple[float, int]] = deque()   # (epoch, status_code)
_latencies: deque[float] = deque(maxlen=100)          # last 100 latencies in ms

# 24-hour window in seconds
_WINDOW_S = 24 * 60 * 60


def _prune_old_requests(now: float | None = None) -> None:
    """Drop entries older than 24h from the request_times deque."""
    if now is None:
        now = time.time()
    cutoff = now - _WINDOW_S
    while _request_times and _request_times[0][0] < cutoff:
        _request_times.popleft()


def get_metrics() -> dict:
    """Return current metrics snapshot for /api/status.

    Returns a dict with all required fields populated.
    """
    now = time.time()
    _prune_old_requests(now)

    # ── Request / error counts ──
    total_requests = len(_request_times)
    error_count = sum(1 for _, sc in _request_times if sc >= 400)

    # ── Latency percentiles ──
    lat_sorted = sorted(_latencies)
    n = len(lat_sorted)
    if n == 0:
        p50_ms = 0.0
        p95_ms = 0.0
    else:
        p50_idx = int(n * 0.50)
        p95_idx = int(n * 0.95)
        p50_ms = round(lat_sorted[p50_idx], 2)
        p95_ms = round(lat_sorted[min(p95_idx, n - 1)], 2)

    # ── DB status ──
    db_status = _check_db_connection()

    # ── Memory (RSS in MB) ──
    mem_mb = round(_read_rss_mb(), 2)

    # ── Uptime ──
    uptime_seconds = int(now - _PROCESS_START)

    return {
        "uptime_seconds": uptime_seconds,
        "process_start": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(_PROCESS_START)
        ),
        "requests_last_24h": total_requests,
        "errors_last_24h": error_count,
        "latency_p50_ms": p50_ms,
        "latency_p95_ms": p95_ms,
        "latency_sample_size": n,
        "db_status": db_status,
        "memory_rss_mb": mem_mb,
    }


def _check_db_connection() -> str:
    """Ping the SQLite database. Returns 'ok' or 'unreachable'."""
    try:
        from src.db.database import get_db
        conn = get_db()
        conn.execute("SELECT 1")
        conn.close()
        return "ok"
    except Exception:
        logger.warning("DB ping failed during metrics check")
        return "unreachable"


def _read_rss_mb() -> float:
    """Read RSS (resident set size) from /proc/self/status. Returns MB."""
    try:
        with open("/proc/self/status", "r") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    # Format: "VmRSS:    12345 kB"
                    parts = line.split()
                    if len(parts) >= 2:
                        kb = int(parts[1])
                        return kb / 1024.0
    except Exception:
        pass
    return 0.0


class MetricsMiddleware(BaseHTTPMiddleware):
    """Collects request metrics: count, errors, latency.

    Must be registered BEFORE RequestLoggingMiddleware so latencies
    include the full handler chain except CORS.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        t0 = time.time()
        response = await call_next(request)
        elapsed_ms = (time.time() - t0) * 1000

        # Record latency
        _latencies.append(elapsed_ms)

        # Record request with status
        _request_times.append((time.time(), response.status_code))
        _prune_old_requests()

        return response
