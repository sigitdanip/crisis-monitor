from fastapi import APIRouter, Query
from src.db.database import get_db
from src.agent.graph import run_pipeline
from src.agent.normalize import fetch_and_normalize
import json

router = APIRouter()

# In-memory store for last pipeline run (ponytail: global dict, file-based if persistence matters)
_last_run: dict | None = None


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

    # Parse JSON fields in report so the frontend receives proper objects
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
    edges = [
        {"source": "composite_scorer_0", "target": "indicator_narrator_0"},
        {"source": "indicator_narrator_0", "target": "dot_analyzers"},
        {"source": "dot_analyzers", "target": "pathway_synthesizer"},
        {"source": "pathway_synthesizer", "target": "end_state_assessor"},
        {"source": "end_state_assessor", "target": "save_to_db"},
    ]
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


@router.post("/trigger/daily")
async def trigger_daily():
    global _last_run
    indicators, news = fetch_and_normalize()
    result = await run_pipeline(indicators, news)
    _last_run = result
    return {
        "status": "completed",
        "composite_score": result["composite_score"],
        "end_state": result.get("end_state", {}).get("end_state"),
        "total_duration_ms": result["total_duration_ms"],
        "success_count": result["success_count"],
        "errors": result["errors"],
    }
