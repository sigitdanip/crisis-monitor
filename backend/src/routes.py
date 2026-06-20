from fastapi import APIRouter, Query, HTTPException, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from src.db.database import get_db
from src.agent.graph import run_pipeline
from src.agent.normalize import fetch_and_normalize
from src.services.health import get_health
from src.services.auth import verify_crisis_token
from src.services.trigger_idempotency import find_recent_report
import asyncio
import json
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory cache of last pipeline run, loaded from DB on startup.
_last_run: dict | None = None


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


# Load last run from DB on module import (startup).
_last_run = _load_last_run_from_db()


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

    return {
        "indicators": [dict(r) for r in indicators],
        "dots": [dict(r) for r in dots],
        "pathways": [dict(r) for r in pathways],
        "report": report_dict,
        "alerts": [dict(r) for r in alerts],
    }


@router.get("/pipeline/status")
async def get_pipeline_status():
    if not _last_run:
        return {"nodes": [], "edges": [], "last_run": None, "total_duration_ms": 0, "success_count": 0}

    nodes = _last_run.get("node_timing", [])
    edges = []
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
    return {
        "nodes": nodes,
        "edges": edges,
        "last_run": _last_run.get("completed_at"),
        "total_duration_ms": _last_run.get("total_duration_ms", 0),
        "success_count": _last_run.get("success_count", 0),
    }


@router.get("/reports/history")
async def report_history(days: int = Query(30)):
    conn = get_db()
    rows = conn.execute(
        "SELECT date, end_state, composite_score, confidence, synthesis, briefing FROM daily_reports ORDER BY date DESC LIMIT ?",
        (days,),
    ).fetchall()
    conn.close()
    return {"reports": [dict(r) for r in rows]}


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


# ── Trigger endpoints (Layer 3: auth, Layer 4: idempotency) ─────────────────

async def _run_pipeline_background() -> None:
    """Run the full pipeline in the background and persist results.

    This is intentionally NOT awaited by the HTTP handler — it runs
    as a fire-and-forget background task. The pipeline takes 60-150s
    (fetchers + up to 8 LLM calls), which exceeds a reasonable HTTP
    response time. The endpoint returns immediately; results are
    persisted to DB and surfaced via /api/pipeline/status.
    """
    global _last_run
    try:
        indicators, news = await asyncio.to_thread(fetch_and_normalize)
        result = await run_pipeline(indicators, news)
        _last_run = result
        _save_last_run_to_db(result)
        logger.info(
            "Pipeline completed in %dms — score: %s, end_state: %s",
            result.get("total_duration_ms", 0),
            result.get("composite_score", {}).get("composite", "?"),
            result.get("end_state", {}).get("end_state", "?"),
        )
    except Exception:
        logger.exception("Background pipeline failed")


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
