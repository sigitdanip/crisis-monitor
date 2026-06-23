from fastapi import APIRouter, Query, Depends
from fastapi.responses import JSONResponse
from src.db.database import get_db
from src.services.health import get_health
from src.services.auth import verify_crisis_token
from src.services.trigger_idempotency import find_recent_report
from src.services.pipeline_runner import execute_pipeline
from src.scheduler import get_last_run
import asyncio
import json
import logging
import time
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory cache of last pipeline run — owned by scheduler.py, imported above.
# get_last_run() is used throughout this module instead of a local global.

# Live progress state for the currently-running pipeline.
_progress: dict = {
    "running": False,
    "started_at": None,
    "current_node": None,
    "completed_nodes": [],
    "failed_node": None,
    "estimated_total_ms": 150_000,
}


def _reset_progress() -> None:
    """Reset the progress state to idle (not running)."""
    _progress["running"] = False
    _progress["started_at"] = None
    _progress["current_node"] = None
    _progress["completed_nodes"] = []
    _progress["failed_node"] = None


def _parse_json_field(value: str | None) -> dict | list | str | None:
    """Parse a JSON string field into a native Python object. Returns original value on failure."""
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped:
        return value
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, TypeError):
        return value


# ── Pipeline log file handler ───────────────────────────────────────────────

_pipeline_log_handler: logging.FileHandler | None = None


def _ensure_pipeline_log_handler() -> logging.FileHandler:
    """Create (once) a FileHandler that writes pipeline logs to /tmp/crisis-pipeline.log."""
    global _pipeline_log_handler
    if _pipeline_log_handler is None:
        _pipeline_log_handler = logging.FileHandler("/tmp/crisis-pipeline.log")
        _pipeline_log_handler.setLevel(logging.INFO)
        _pipeline_log_handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        # Attach to the crisis_monitor root logger so all child loggers inherit it
        root = logging.getLogger("crisis_monitor")
        root.addHandler(_pipeline_log_handler)
    return _pipeline_log_handler


# ── Public endpoints (no auth) ──────────────────────────────────────────────

@router.get("/dashboard")
async def get_dashboard():
    conn = get_db()
    indicators = conn.execute("""
        SELECT COALESCE(NULLIF(display_name, ''), indicator_name) as name,
               COALESCE(category, '') as category,
               value, COALESCE(unit, '') as unit,
               status, COALESCE(trigger_level, '') as trigger_level,
               COALESCE(narrative, '') as narrative,
               recorded_at as fetched_at
        FROM (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY indicator_name ORDER BY recorded_at DESC) as rn
            FROM indicator_history
        ) WHERE rn = 1
        ORDER BY category, indicator_name
    """).fetchall()
    dots = conn.execute("""
        SELECT dot_number, dot_name, status, summary, key_signals, sources, analyzed_at
        FROM (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY dot_number ORDER BY analyzed_at DESC) as rn
            FROM dot_analyses WHERE analyzed_at >= datetime('now', '-2 days')
        ) WHERE rn = 1
        ORDER BY dot_number
    """).fetchall()
    pathways = conn.execute("""
        SELECT pathway, name, description, active, signals, assessed_at
        FROM (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY pathway ORDER BY assessed_at DESC) as rn
            FROM pathway_status WHERE assessed_at >= datetime('now', '-2 days')
        ) WHERE rn = 1
        ORDER BY pathway
    """).fetchall()
    report = conn.execute("SELECT * FROM daily_reports ORDER BY date DESC LIMIT 1").fetchone()
    alerts = conn.execute("SELECT * FROM alerts ORDER BY triggered_at DESC LIMIT 20").fetchall()
    conn.close()

    report_dict = dict(report) if report else None
    if report_dict:
        report_dict["five_questions"] = _parse_json_field(report_dict.get("five_questions"))
        report_dict["dot_summary"] = _parse_json_field(report_dict.get("dot_summary"))
        report_dict["pathway_summary"] = _parse_json_field(report_dict.get("pathway_summary"))

    # Parse JSON-stringified array fields on dot and pathway rows
    dots_parsed = []
    for r in dots:
        d = dict(r)
        d["key_signals"] = _parse_json_field(d.get("key_signals"))
        dots_parsed.append(d)

    pathways_parsed = []
    for r in pathways:
        p = dict(r)
        p["signals"] = _parse_json_field(p.get("signals"))
        pathways_parsed.append(p)

    return {
        "indicators": [dict(r) for r in indicators],
        "dots": dots_parsed,
        "pathways": pathways_parsed,
        "report": report_dict,
        "alerts": [dict(r) for r in alerts],
    }


@router.get("/pipeline/status")
async def get_pipeline_status():
    """Return pipeline status including live progress if a run is in progress.

    When progress.running is True, the response includes per-node progress
    (current_node, completed_nodes, elapsed_ms, etc.) so the dashboard can
    show real-time feedback during the 60-150s pipeline run.

    Includes scheduler metadata (enabled, next_run, timezone) so the
    dashboard can confirm the in-process scheduler is active.
    """
    _last_run = get_last_run()

    if not _last_run and not _progress["running"]:
        return {
            "nodes": [], "edges": [],
            "last_run": None, "total_duration_ms": 0, "success_count": 0,
            "progress": {
                "running": False, "started_at": None, "current_node": None,
                "completed_nodes": [], "failed_node": None,
            },
            "scheduler": _get_scheduler_info(),
        }

    nodes = []
    edges = []
    last_run_ts = None
    total_duration_ms = 0
    success_count = 0

    if _last_run:
        nodes = _last_run.get("node_timing", [])
        dot_analyzer_ids = []
        dot_group_id = None
        for i, n in enumerate(nodes):
            nid = n["id"]
            if n.get("type") == "agent" and n.get("label", "").startswith("Agent "):
                dot_analyzer_ids.append(nid)
            if n.get("label") == "Dot Analyzers (parallel)":
                dot_group_id = nid
        prev_id = None
        for n in nodes:
            nid = n["id"]
            if prev_id and nid not in dot_analyzer_ids:
                edges.append({"source": prev_id, "target": nid})
            if nid not in dot_analyzer_ids:
                prev_id = nid
        if dot_group_id:
            for aid in dot_analyzer_ids:
                edges.append({"source": aid, "target": dot_group_id})
        last_run_ts = _last_run.get("completed_at")
        total_duration_ms = _last_run.get("total_duration_ms", 0)
        success_count = _last_run.get("success_count", 0)

    # Build progress field
    progress_resp: dict
    if _progress["running"]:
        elapsed_ms = 0
        if _progress["started_at"]:
            try:
                t0 = datetime.fromisoformat(_progress["started_at"])
                elapsed_ms = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
            except (ValueError, TypeError):
                pass
        remaining = max(0, _progress["estimated_total_ms"] - elapsed_ms)
        progress_resp = {
            "running": True,
            "started_at": _progress["started_at"],
            "elapsed_ms": elapsed_ms,
            "current_node": _progress["current_node"],
            "completed_nodes": list(_progress["completed_nodes"]),
            "failed_node": _progress["failed_node"],
            "estimated_remaining_ms": remaining,
        }
    else:
        progress_resp = {
            "running": False,
            "started_at": None,
            "elapsed_ms": None,
            "current_node": None,
            "completed_nodes": None,
            "failed_node": None,
            "estimated_remaining_ms": None,
        }

    return {
        "nodes": nodes,
        "edges": edges,
        "last_run": last_run_ts,
        "total_duration_ms": total_duration_ms,
        "success_count": success_count,
        "progress": progress_resp,
        "scheduler": _get_scheduler_info(),
    }


def _get_scheduler_info() -> dict:
    """Return scheduler metadata for the API response. Safe to call before scheduler starts."""
    try:
        from src.scheduler import get_scheduler_info as _sched_info
        return _sched_info()
    except Exception:
        return {"enabled": False, "next_run": None, "timezone": "Asia/Jakarta"}


@router.get("/reports/history")
async def report_history(days: int = Query(30)):
    conn = get_db()
    rows = conn.execute(
        "SELECT date, end_state, composite_score, confidence, synthesis, briefing FROM daily_reports ORDER BY date DESC LIMIT ?",
        (days,),
    ).fetchall()
    conn.close()
    return {"reports": [dict(r) for r in rows]}


@router.get("/timeseries")
async def get_timeseries(
    days: int = Query(7, ge=1, le=90),
    minutes: int = Query(None, ge=1, le=129600, description="[DEPRECATED] Use days instead. Minutes are converted to days (ceil(minutes/1440))."),
):
    """Daily-resolution timeseries. 1 point per indicator per day (the latest
    value from that day's pipeline run). Composite series 1 per day from
    daily_reports.

    Query params:
        days:   Lookback window in days (default 7, range 1-90).
        minutes: [DEPRECATED] Legacy param; auto-converted to days via
                 ceil(minutes / 1440). Prefer ``days`` for new callers.
    """
    import math, warnings

    # ── Legacy minutes → days conversion ──
    if minutes is not None:
        warnings.warn(
            "`minutes` query param is deprecated on GET /api/timeseries; use `days` instead. "
            f"Converting {minutes} minutes → {math.ceil(minutes / 1440)} days.",
            DeprecationWarning,
            stacklevel=2,
        )
        days = max(1, math.ceil(minutes / 1440))

    days = min(days, 90)

    now_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    from_ts = cutoff_date + "T00:00:00Z"
    to_ts = now_date + "T00:00:00Z"

    conn = get_db()

    # Per-indicator timeseries: 1 point per day per indicator
    # (latest value per day via ROW_NUMBER partitioned by DATE)
    indicator_rows = conn.execute("""
        SELECT indicator_name, display_name, category, value, unit, status,
               strftime('%Y-%m-%dT%H:%M:%SZ', recorded_at) as recorded_at
        FROM (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY indicator_name, DATE(recorded_at)
                ORDER BY recorded_at DESC
            ) as rn
            FROM indicator_history
            WHERE DATE(recorded_at) >= ?
        )
        WHERE rn = 1
        ORDER BY indicator_name, recorded_at
    """, (cutoff_date,)).fetchall()

    # Composite score series from daily_reports (1 row per day by date)
    composite_rows = conn.execute("""
        SELECT date as recorded_date, composite_score
        FROM daily_reports
        WHERE date >= ?
        ORDER BY date ASC
    """, (cutoff_date,)).fetchall()

    conn.close()

    # ── Build series grouped by indicator_name ──
    series_map: dict[str, dict] = {}
    for row in indicator_rows:
        name = row["indicator_name"]
        if name not in series_map:
            series_map[name] = {
                "indicator_name": name,
                "display_name": row["display_name"] or name,
                "category": row["category"] or "",
                "unit": row["unit"] or "",
                "points": [],
            }
        series_map[name]["points"].append({
            "recorded_at": row["recorded_at"],
            "value": row["value"] if row["value"] is not None else 0.0,
            "status": row["status"] or "normal",
        })

    series = list(series_map.values())

    # ── Build composite_series with interpretation ──
    def _interpret(score: int) -> str:
        if score <= 6:
            return "normal"
        elif score <= 12:
            return "monitor"
        elif score <= 20:
            return "elevated"
        elif score <= 25:
            return "alert"
        else:
            return "critical"

    composite_series = [
        {
            "recorded_at": row["recorded_date"] + "T00:00:00Z",
            "composite_score": row["composite_score"] or 0,
            "interpretation": _interpret(row["composite_score"] or 0),
        }
        for row in composite_rows
    ]

    return {
        "series": series,
        "composite_series": composite_series,
        "from": from_ts,
        "to": to_ts,
    }


# ── Health endpoint (Layer 2) ───────────────────────────────────────────────

@router.get("/system/health")
async def system_health():
    """Aggregated health check with DB, pipeline, error/fallback counts."""
    health_data = get_health()
    status = health_data["status"]
    # HTTP 200 when ok, HTTP 503 when degraded or down
    if status == "ok":
        return health_data
    return JSONResponse(
        status_code=503,
        content=health_data,
    )


# ── Status endpoint (metrics) ───────────────────────────────────────────────

# 1-second cache for /api/status to avoid hot-path cost
_status_cache: dict | None = None
_status_cache_ts: float = 0.0
_STATUS_CACHE_TTL: float = 1.0  # seconds


@router.get("/status")
async def api_status():
    """Metrics endpoint: uptime, requests, errors, latency, DB, memory.

    Response is cached for 1 second to avoid per-request overhead on
    the metrics middleware's data structures. Fields:

    - uptime_seconds: process uptime
    - process_start: ISO8601 UTC start time
    - requests_last_24h: total requests in last 24 hours
    - errors_last_24h: 4xx+5xx responses in last 24 hours
    - latency_p50_ms / latency_p95_ms: percentiles from last 100 requests
    - latency_sample_size: number of latency samples
    - db_status: "ok" or "unreachable"
    - memory_rss_mb: resident set size in MB
    """
    global _status_cache, _status_cache_ts

    now = time.time()
    if _status_cache is not None and (now - _status_cache_ts) < _STATUS_CACHE_TTL:
        return _status_cache

    from src.middleware.metrics import get_metrics

    _status_cache = get_metrics()
    _status_cache_ts = now
    return _status_cache


# ── Trigger endpoints (Layer 3: auth, Layer 4: idempotency) ─────────────────


async def _on_pipeline_progress(
    node_label: str,
    event: str,
    error_message: str | None,
) -> None:
    """Progress callback invoked by run_pipeline for each node transition.

    Args:
        node_label: Human-readable node name (e.g. "Composite Scorer").
        event: "started" or "completed".
        error_message: None for "started"; set for "completed" if node failed.
    """
    if event == "started":
        _progress["current_node"] = node_label
        logger.info("Node started: %s", node_label)
    elif event == "completed":
        _progress["completed_nodes"].append(node_label)
        if error_message:
            _progress["failed_node"] = node_label
            logger.error("Node failed: %s — %s", node_label, error_message)
        else:
            logger.info("Node completed: %s", node_label)
        # Clear current_node only if the next node hasn't already set it
        if _progress["current_node"] == node_label:
            _progress["current_node"] = None


async def _run_pipeline_background() -> None:
    """Run the full pipeline in the background and persist results.

    This is intentionally NOT awaited by the HTTP handler — it runs
    as a fire-and-forget background task. The pipeline takes 60-150s
    (fetchers + up to 8 LLM calls), which exceeds a reasonable HTTP
    response time. The endpoint returns immediately; results are
    persisted to DB and surfaced via /api/pipeline/status.

    Live progress is published via the _progress dict, which the
    /api/pipeline/status endpoint reads on every poll.
    """
    _ensure_pipeline_log_handler()

    # Reset and initialize progress state
    _reset_progress()
    _progress["running"] = True
    _progress["started_at"] = datetime.now(timezone.utc).isoformat()
    pipeline_start_ts = time.time()

    logger.info("Pipeline started — fetching indicators and news")
    try:
        result = await execute_pipeline(
            "api",
            progress_callback=_on_pipeline_progress,
        )

        # Update the scheduler's shared _last_run so /api/pipeline/status sees it
        from src.scheduler import _last_run as _scheduler_last_run
        import src.scheduler as _sched
        _sched._last_run = result

        pipeline_total_ms = int((time.time() - pipeline_start_ts) * 1000)
        logger.info(
            "Pipeline completed in %dms — score: %s, end_state: %s",
            pipeline_total_ms,
            result.get("composite_score", {}).get("composite", "?"),
            result.get("end_state", {}).get("end_state", "?"),
        )

    except Exception:
        logger.exception("Background pipeline failed")
        _progress["failed_node"] = _progress["current_node"]

    finally:
        _progress["running"] = False
        _progress["current_node"] = None


@router.post("/trigger/daily")
async def trigger_daily(
    _token: str = Depends(verify_crisis_token),
):
    """Trigger the daily pipeline run (auth required, idempotent).

    Starts the pipeline as a background task and returns immediately.
    The pipeline runs asynchronously; results are persisted to DB and
    surfaced via /api/pipeline/status and /api/dashboard.

    Idempotent: if triggered within 5 minutes of a previous run,
    returns the existing report instead of starting a new pipeline.
    """
    trigger_source = "api"

    # Layer 4: idempotency check
    existing = find_recent_report(trigger_source)
    if existing:
        return JSONResponse(
            status_code=200,
            content={
                "status": "idempotent",
                "message": "Recent pipeline run exists — returning existing report.",
                "report_id": existing["id"],
                "report": existing,
            },
        )

    # If a pipeline is already running, don't start another
    if _progress["running"]:
        return JSONResponse(
            status_code=200,
            content={
                "status": "already_running",
                "message": "Pipeline is already in progress. Check /api/pipeline/status.",
                "current_node": _progress["current_node"],
            },
        )

    asyncio.create_task(_run_pipeline_background())
    return JSONResponse(
        status_code=201,
        content={
            "status": "accepted",
            "message": "Pipeline started. Check /api/pipeline/status for results.",
        },
    )


@router.post("/trigger/dot/{dot_number}")
async def trigger_dot(
    dot_number: int,
    _token: str = Depends(verify_crisis_token),
):
    """Trigger a single dot analysis re-run (auth required)."""
    return {
        "status": "accepted",
        "message": f"Dot {dot_number} analysis triggered.",
    }
