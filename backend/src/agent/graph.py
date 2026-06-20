"""LangGraph StateGraph — Crisis Monitor pipeline.

Nodes: Data Fetchers → Composite Scorer → Indicator Narrator →
       5 Dot Analyzers (parallel) → Pathway Synthesizer →
       End State Assessor → DB Save.

Each node tracks its own timing. State is typed with TypedDict.
"""
import time
import json
from datetime import datetime, timezone
from typing import TypedDict, Dict, Any, List, Optional
from langgraph.graph import StateGraph, END

from src.agent.llm import get_llm, extract_json
from src.agent.composite_scorer import score_composite
from src.agent.dot_analyzers import (
    analyze_geopolitical,
    analyze_food_debt,
    analyze_financial_em,
    analyze_china_political,
    analyze_health,
)
from src.agent.pathway_synthesizer import synthesize_pathways
from src.agent.end_state import assess_end_state
from src.agent.indicator_narrator import generate_indicator_narratives
from src.db.database import get_db


# ============================================================
# State
# ============================================================

class CrisisState(TypedDict):
    """State flowing through the crisis monitor pipeline."""
    # Input data
    indicators: Dict[str, Any]
    news: Optional[List[Dict[str, str]]]

    # Composite scoring
    composite_score: Optional[Dict[str, Any]]

    # Indicator narratives (per-indicator plain-language context)
    indicator_narratives: Optional[Dict[str, str]]

    # Dot analyses (9 dots from 5 agents)
    dot_analyses: Optional[Dict[str, Any]]

    # Pathway synthesis
    pathways: Optional[Dict[str, Any]]

    # End state
    end_state: Optional[Dict[str, Any]]

    # Timing — per-node duration tracking
    node_timing: List[Dict[str, Any]]

    # Pipeline metadata
    started_at: str
    completed_at: Optional[str]
    total_duration_ms: Optional[float]
    success_count: int
    errors: List[str]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_timing(
    state: CrisisState, node_name: str, node_type: str,
    status: str, duration_ms: float,
    input_summary: str = "", output_summary: str = "",
    error: str = "",
) -> None:
    """Append a timing record to state."""
    state["node_timing"].append({
        "id": f"{node_name}_{len(state['node_timing'])}",
        "type": node_type,
        "label": node_name,
        "status": status,
        "duration_ms": round(duration_ms, 1),
        "input_summary": input_summary,
        "output_summary": output_summary,
        "error": error,
    })


# ============================================================
# Nodes
# ============================================================

async def node_composite_scorer(state: CrisisState) -> CrisisState:
    """Run rule-based composite scorer on all indicators."""
    t0 = time.time()
    try:
        result = score_composite(state["indicators"])
        state["composite_score"] = result
        dur = (time.time() - t0) * 1000
        _record_timing(state, "Composite Scorer", "scorer", "success", dur,
                       input_summary=f"{len(state['indicators'])} indicators",
                       output_summary=f"Score {result['composite']}/16 ({result['interpretation']})")
        state["success_count"] += 1
    except Exception as e:
        dur = (time.time() - t0) * 1000
        _record_timing(state, "Composite Scorer", "scorer", "error", dur, error=str(e))
        state["errors"].append(f"Composite scorer: {e}")
        state["composite_score"] = {"composite": 0, "interpretation": "error", "category_scores": {}}
    return state


async def node_indicator_narrator(state: CrisisState) -> CrisisState:
    """Generate 1-sentence plain-language narrative context per indicator via LLM."""
    t0 = time.time()
    try:
        narratives = await generate_indicator_narratives(state["indicators"])
        state["indicator_narratives"] = narratives
        dur = (time.time() - t0) * 1000
        _record_timing(state, "Indicator Narrator", "agent", "success", dur,
                       input_summary=f"{len(state['indicators'])} indicators",
                       output_summary=f"{len(narratives)} narratives generated")
        state["success_count"] += 1
    except Exception as e:
        dur = (time.time() - t0) * 1000
        state["indicator_narratives"] = {}
        _record_timing(state, "Indicator Narrator", "agent", "fallback", dur,
                       error=str(e))
    return state


async def node_dot_analyzers(state: CrisisState) -> CrisisState:
    """Run all 5 dot analyzer LLMs in parallel."""
    t0 = time.time()
    indicators = state["indicators"]
    composite = state["composite_score"] or {"composite": 0, "interpretation": "unknown"}
    news = state.get("news")

    # Run all 5 in parallel
    import asyncio as _asyncio
    results = await _asyncio.gather(
        analyze_geopolitical(indicators, composite, news),
        analyze_food_debt(indicators, composite, news),
        analyze_financial_em(indicators, composite, news),
        analyze_china_political(indicators, composite, news),
        analyze_health(indicators, composite, news),
        return_exceptions=True,
    )

    from src.agent.dot_analyzers import _fallback as dot_fallback

    agent_names = ["geopolitical", "food_debt", "financial_em", "china_political", "health"]
    merged = {}

    for i, (name, result) in enumerate(zip(agent_names, results)):
        agent_num = i + 1
        if isinstance(result, Exception):
            # Use rule-based fallback when LLM call fails
            fallback = dot_fallback(name, indicators)
            merged.update(fallback)
            dur = 0  # no real duration since it failed instantly
            _record_timing(state, f"Agent {agent_num} ({name})", "agent", "fallback", dur,
                           output_summary=f"LLM unavailable — using rule-based fallback",
                           error=str(result))
        else:
            merged.update(result)
            dot_count = len(result)
            dur = 0  # rough — all run in parallel, individual timing not tracked
            _record_timing(state, f"Agent {agent_num} ({name})", "agent", "success", dur,
                           output_summary=f"{dot_count} dots analyzed")
            state["success_count"] += 1

    state["dot_analyses"] = merged
    dur = (time.time() - t0) * 1000
    _record_timing(state, "Dot Analyzers (parallel)", "agent", "success", dur,
                   output_summary=f"{len(merged)} total dots from 5 agents")
    return state


async def node_pathway_synthesizer(state: CrisisState) -> CrisisState:
    """Agent 6: Synthesize pathways from dot analyses."""
    t0 = time.time()
    try:
        pathways = await synthesize_pathways(
            state["dot_analyses"] or {},
            state["composite_score"] or {"composite": 0, "interpretation": "unknown"},
        )
        state["pathways"] = pathways
        dur = (time.time() - t0) * 1000

        active = [k for k, v in pathways.items() if isinstance(v, dict) and v.get("active")]
        dominant = pathways.get("dominant_pathway", "none")
        _record_timing(state, "Pathway Synthesizer", "synthesizer", "success", dur,
                       output_summary=f"Active: {active}, Dominant: {dominant}")
        state["success_count"] += 1
    except Exception as e:
        from src.agent.pathway_synthesizer import _fallback_pathways
        dur = (time.time() - t0) * 1000
        fallback = _fallback_pathways(
            state["composite_score"] or {"composite": 0, "interpretation": "unknown"}
        )
        state["pathways"] = fallback
        _record_timing(state, "Pathway Synthesizer", "synthesizer", "fallback", dur,
                       output_summary="LLM unavailable — using rule-based fallback",
                       error=str(e))
    return state


async def node_end_state_assessor(state: CrisisState) -> CrisisState:
    """Agent 7: Determine end state + answer 5 questions."""
    t0 = time.time()
    try:
        end_state = await assess_end_state(
            state["dot_analyses"] or {},
            state["pathways"] or {},
            state["composite_score"] or {"composite": 0, "interpretation": "unknown"},
        )
        state["end_state"] = end_state
        dur = (time.time() - t0) * 1000
        _record_timing(state, "End State Assessor", "assessor", "success", dur,
                       output_summary=f"{end_state.get('end_state', 'unknown')} (confidence: {end_state.get('confidence', 0)})")
        state["success_count"] += 1
    except Exception as e:
        from src.agent.end_state import _fallback_end_state
        dur = (time.time() - t0) * 1000
        fallback = _fallback_end_state(
            state["composite_score"] or {"composite": 0, "interpretation": "unknown"},
            state["pathways"] or {"pathway_d": {"active": False}},
        )
        state["end_state"] = fallback
        _record_timing(state, "End State Assessor", "assessor", "fallback", dur,
                       output_summary="LLM unavailable — using rule-based fallback",
                       error=str(e))
    return state


async def node_save_to_db(state: CrisisState) -> CrisisState:
    """Save all pipeline results to SQLite."""
    t0 = time.time()
    try:
        conn = get_db()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Save indicator snapshots with full metadata from INDICATOR_META registry
        from src.agent.indicator_narrator import INDICATOR_META, _assess, _is_news_flag, _extract_scalar
        narratives = state.get("indicator_narratives") or {}

        # Build a lookup of news-derived narratives keyed by their base slug
        # (e.g. news_caixin_pmi → narrative for fallback into caixin_pmi)
        news_narratives: dict[str, str] = {}
        for slug, val in state["indicators"].items():
            if _is_news_flag(val):
                narrative = val.get("narrative", "")
                if narrative:
                    # Strip "news_" prefix to map to the regular indicator slug
                    base_slug = slug.removeprefix("news_")
                    news_narratives[base_slug] = narrative

        for slug, val in state["indicators"].items():
            if isinstance(val, (int, float, str)):
                meta = INDICATOR_META.get(slug, {})
                display_name = meta.get("name", slug)
                category = meta.get("category", "")
                unit = meta.get("unit", "")
                trigger = meta.get("trigger", "")
                status = _assess(val, meta) if meta else "normal"
                narrative = narratives.get(slug, "")
                # Fall back to news-derived narrative if LLM narrative is empty
                if not narrative and slug in news_narratives:
                    narrative = news_narratives[slug]
                # Convert empty strings to None for SQLite REAL column compatibility
                db_val = None if isinstance(val, str) and val == "" else val
                conn.execute(
                    """INSERT INTO indicator_history
                       (indicator_name, display_name, category, value, unit, status, trigger_level, narrative)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (slug, display_name, category, db_val, unit, status, trigger, narrative),
                )
            elif _is_news_flag(val):
                # Persist news-derived flag indicators to indicator_history
                meta = INDICATOR_META.get(slug, {})
                display_name = meta.get("name", slug)
                category = meta.get("category", "")
                unit = meta.get("unit", "flag")
                trigger = meta.get("trigger", "")
                flag_value = val.get("value", 0)
                status = _assess(val, meta) if meta else "normal"
                narrative = val.get("narrative", "")
                conn.execute(
                    """INSERT INTO indicator_history
                       (indicator_name, display_name, category, value, unit, status, trigger_level, narrative)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (slug, display_name, category, flag_value, unit, status, trigger, narrative),
                )

        # Save dot analyses
        dots = state["dot_analyses"] or {}
        for dot_key, dot_data in dots.items():
            if not isinstance(dot_data, dict):
                continue
            dot_num = int(dot_key.split("_")[-1]) if dot_key.startswith("dot_") else 0
            # Sources: string paragraph from LLM, or empty string fallback.
            # Backward-compat: if LLM returned a list (old format), serialize as JSON.
            sources_raw = dot_data.get("sources", "")
            if isinstance(sources_raw, list):
                sources_raw = json.dumps(sources_raw)
            conn.execute(
                "INSERT INTO dot_analyses (dot_number, dot_name, status, summary, key_signals, sources) VALUES (?, ?, ?, ?, ?, ?)",
                (dot_num, dot_key, dot_data.get("status", "dormant"),
                 dot_data.get("summary", ""),
                 json.dumps(dot_data.get("key_signals", [])),
                 sources_raw),
            )

        # Save pathway status
        pathways = state["pathways"] or {}
        for pkey, pdata in pathways.items():
            if not isinstance(pdata, dict) or not pkey.startswith("pathway_"):
                continue
            conn.execute(
                "INSERT INTO pathway_status (pathway, active, signals, name, description) VALUES (?, ?, ?, ?, ?)",
                (pkey, 1 if pdata.get("active") else 0,
                 json.dumps(pdata.get("triggered_by", [])),
                 pdata.get("name", ""),
                 pdata.get("description", "")),
            )

        # Save daily report
        end_state = state["end_state"] or {}
        briefing = end_state.get("briefing", "")
        conn.execute(
            """INSERT OR REPLACE INTO daily_reports
               (date, dot_summary, pathway_summary, end_state, synthesis, five_questions, confidence, composite_score, briefing)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                today,
                json.dumps(state["dot_analyses"] or {}),
                json.dumps(state["pathways"] or {}),
                end_state.get("end_state", "unknown"),
                end_state.get("briefing", end_state.get("headline", "")),
                json.dumps({k: end_state.get(k) for k in ("q1", "q2", "q3", "q4", "q5") if k in end_state}),
                str(end_state.get("confidence", 0)),
                state["composite_score"]["composite"] if state["composite_score"] else 0,
                briefing,
            ),
        )
        conn.commit()
        conn.close()

        dur = (time.time() - t0) * 1000
        _record_timing(state, "Save to DB", "fetcher", "success", dur,
                       output_summary="All tables populated")
        state["success_count"] += 1
    except Exception as e:
        dur = (time.time() - t0) * 1000
        _record_timing(state, "Save to DB", "fetcher", "error", dur, error=str(e))
        state["errors"].append(f"DB save: {e}")
    return state


# ============================================================
# Graph Assembly
# ============================================================

def build_graph() -> StateGraph:
    """Build and compile the crisis monitor StateGraph."""
    graph = StateGraph(CrisisState)

    # Add nodes
    graph.add_node("composite_scorer", node_composite_scorer)
    graph.add_node("indicator_narrator", node_indicator_narrator)
    graph.add_node("dot_analyzers", node_dot_analyzers)
    graph.add_node("pathway_synthesizer", node_pathway_synthesizer)
    graph.add_node("end_state_assessor", node_end_state_assessor)
    graph.add_node("save_to_db", node_save_to_db)

    # Wire edges — sequential pipeline
    # composite_scorer → indicator_narrator → dot_analyzers → pathway_synthesizer
    # → end_state_assessor → save_to_db → END
    graph.set_entry_point("composite_scorer")
    graph.add_edge("composite_scorer", "indicator_narrator")
    graph.add_edge("indicator_narrator", "dot_analyzers")
    graph.add_edge("dot_analyzers", "pathway_synthesizer")
    graph.add_edge("pathway_synthesizer", "end_state_assessor")
    graph.add_edge("end_state_assessor", "save_to_db")
    graph.add_edge("save_to_db", END)

    return graph.compile()


# Singleton compiled graph
_graph = None


def get_graph():
    """Return the compiled graph singleton."""
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


async def run_pipeline(
    indicators: Dict[str, Any],
    news: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Run the full crisis monitor pipeline.

    Args:
        indicators: Dict of indicator name → value pairs.
        news: Optional list of news headline dicts.

    Returns:
        Pipeline results dict with node timing data.
    """
    graph = get_graph()
    t0 = time.time()

    initial_state: CrisisState = {
        "indicators": indicators,
        "news": news,
        "composite_score": None,
        "indicator_narratives": None,
        "dot_analyses": None,
        "pathways": None,
        "end_state": None,
        "node_timing": [],
        "started_at": _now_iso(),
        "completed_at": None,
        "total_duration_ms": None,
        "success_count": 0,
        "errors": [],
    }

    final_state = await graph.ainvoke(initial_state)

    total_ms = (time.time() - t0) * 1000
    final_state["completed_at"] = _now_iso()
    final_state["total_duration_ms"] = round(total_ms, 1)

    return final_state


# ============================================================
# Self-check
# ============================================================

if __name__ == "__main__":
    import asyncio

    async def _test():
        graph = build_graph()
        nodes = list(graph.nodes.keys())
        print(f"Graph compiled OK — {len(nodes)} nodes: {nodes}")
        # Verify expected nodes exist
        expected = ["composite_scorer", "indicator_narrator", "dot_analyzers",
                    "pathway_synthesizer", "end_state_assessor", "save_to_db"]
        for node in expected:
            assert node in nodes, f"Missing node: {node}"
        print("All expected nodes present")

    asyncio.run(_test())
