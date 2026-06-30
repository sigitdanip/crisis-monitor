"""DB writer — persists pipeline results to SQLite.

Extracted from graph.node_save_to_db so that each persistence concern is a
focused, testable function. graph.py calls save_pipeline_results() as the
sole entry point.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from src.db.database import get_db_ctx

logger = logging.getLogger("crisis_monitor.db_writer")


def _now_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ── Public entry point ────────────────────────────────────────────────────


def save_pipeline_results(state: dict) -> None:
    """Persist all pipeline outputs (indicators, dots, pathways, report) to DB.

    Args:
        state: Final CrisisState dict from the LangGraph pipeline.

    Raises:
        Exception: Re-raises any DB error so the caller can record it.
    """
    with get_db_ctx() as conn:
        _save_indicators(conn, state)
        _save_dot_analyses(conn, state.get("dot_analyses") or {})
        _save_pathway_status(conn, state.get("pathways") or {})
        _save_daily_report(conn, state)
        conn.commit()


# ── Internal helpers ──────────────────────────────────────────────────────


def _is_structured_value(val: Any) -> bool:
    return isinstance(val, dict) and "data_status" in val


def _save_indicators(conn, state: dict) -> None:
    """Write one indicator_history row per indicator slug."""
    # Import here to avoid circular imports at module load time;
    # indicator_narrator depends on db indirectly.
    from src.agent.indicator_narrator import INDICATOR_META, _assess, _is_news_flag

    narratives: dict = state.get("indicator_narratives") or {}

    # Build a lookup of news-derived narratives keyed by their base slug
    # (e.g. news_caixin_pmi → narrative for fallback into caixin_pmi).
    news_narratives: dict[str, str] = {}
    for slug, val in state["indicators"].items():
        if _is_news_flag(val):
            narrative = val.get("narrative", "")
            if narrative:
                base_slug = slug.removeprefix("news_")
                news_narratives[base_slug] = narrative

    for slug, val in state["indicators"].items():
        meta = INDICATOR_META.get(slug, {})
        display_name = meta.get("name", slug)
        category = meta.get("category", "")
        unit = meta.get("unit", "")
        trigger = meta.get("trigger", "")

        if isinstance(val, (int, float, str)):
            status = _assess(val, meta) if meta else "normal"
            narrative = narratives.get(slug, "") or news_narratives.get(slug, "")
            db_val = None if isinstance(val, str) and val == "" else val
            conn.execute(
                "INSERT INTO indicator_history"
                " (indicator_name, display_name, category, value, unit, status, trigger_level, narrative, data_status)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (slug, display_name, category, db_val, unit, status, trigger, narrative, "live"),
            )

        elif _is_structured_value(val):
            from src.agent.indicator_narrator import _extract_scalar
            scalar = _extract_scalar(val)
            status = val.get("status") or (_assess(scalar, meta) if meta else "normal")
            narrative = narratives.get(slug, "") or val.get("narrative", "") or news_narratives.get(slug, "")
            db_val = None if isinstance(scalar, str) and scalar == "" else scalar
            conn.execute(
                "INSERT INTO indicator_history"
                " (indicator_name, display_name, category, value, unit, status, trigger_level, narrative, data_status)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (slug, display_name, category, db_val, unit or val.get("unit", ""), status, trigger, narrative, val.get("data_status", "live")),
            )

        elif _is_news_flag(val):
            flag_value = val.get("value", 0)
            status = _assess(val, meta) if meta else "normal"
            narrative = val.get("narrative", "")
            conn.execute(
                "INSERT INTO indicator_history"
                " (indicator_name, display_name, category, value, unit, status, trigger_level, narrative, data_status)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (slug, display_name, category, flag_value, unit or "flag", status, trigger, narrative, val.get("data_status", "live")),
            )

        else:
            # No data available — write a NULL row so every registered
            # indicator has a history entry.
            narrative = narratives.get(slug, "") or news_narratives.get(slug, "")
            if not narrative:
                narrative = "No data and no recent news coverage."
            conn.execute(
                "INSERT INTO indicator_history"
                " (indicator_name, display_name, category, value, unit, status, trigger_level, narrative, data_status)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (slug, display_name, category, None, unit, "unknown", trigger, narrative, "unavailable"),
            )


def _save_dot_analyses(conn, dots: dict) -> None:
    """Write one dot_analyses row per dot."""
    for dot_key, dot_data in dots.items():
        if not isinstance(dot_data, dict):
            continue
        dot_num = int(dot_key.split("_")[-1]) if dot_key.startswith("dot_") else 0
        sources_raw = dot_data.get("sources", "")
        if isinstance(sources_raw, list):
            sources_raw = json.dumps(sources_raw)
        conn.execute(
            "INSERT INTO dot_analyses"
            " (dot_number, dot_name, status, summary, key_signals, sources, tier)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                dot_num,
                dot_key,
                dot_data.get("status", "dormant"),
                dot_data.get("summary", ""),
                json.dumps(dot_data.get("key_signals", [])),
                sources_raw,
                dot_data.get("tier", "live"),
            ),
        )


def _save_pathway_status(conn, pathways: dict) -> None:
    """Write one pathway_status row per active pathway key."""
    for pkey, pdata in pathways.items():
        if not isinstance(pdata, dict) or not pkey.startswith("pathway_"):
            continue
        conn.execute(
            "INSERT INTO pathway_status (pathway, active, signals, name, description)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                pkey,
                1 if pdata.get("active") else 0,
                json.dumps(pdata.get("triggered_by", [])),
                pdata.get("name", ""),
                pdata.get("description", ""),
            ),
        )


def _save_daily_report(conn, state: dict) -> None:
    """Upsert today's daily_reports row."""
    today = _now_date()
    end_state = state.get("end_state") or {}
    briefing = end_state.get("briefing", "")
    composite_score = (
        state["composite_score"]["composite"] if state.get("composite_score") else 0
    )
    conn.execute(
        "INSERT OR REPLACE INTO daily_reports"
        " (date, dot_summary, pathway_summary, end_state, synthesis,"
        "  five_questions, confidence, composite_score, briefing, trigger_source,"
        "  dashboard_state, category_rss_scores)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            today,
            json.dumps(state.get("dot_analyses") or {}),
            json.dumps(state.get("pathways") or {}),
            end_state.get("end_state", "unknown"),
            end_state.get("briefing", end_state.get("headline", "")),
            json.dumps(
                {
                    k: end_state.get(k)
                    for k in ("q1", "q2", "q3", "q4", "q5")
                    if k in end_state
                }
            ),
            str(end_state.get("confidence", 0)),
            composite_score,
            briefing,
            state.get("trigger_source", ""),
            state.get("composite_score", {}).get("dashboard_state", "ACTIVE"),
            json.dumps(state.get("composite_score", {}).get("category_rss_scores", {})),
        ),
    )
