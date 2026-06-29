"""LangGraph StateGraph — Crisis Monitor pipeline.

Nodes: Data Fetchers → Composite Scorer → Alerts Engine → Indicator Narrator →
       5 Dot Analyzers (parallel) → Pathway Synthesizer →
       End State Assessor → DB Save.

Each node tracks its own timing. State is typed with TypedDict.
"""
import time
import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import TypedDict, Dict, Any, List, Optional, Callable, Awaitable
from langgraph.graph import StateGraph, END

from src.agent.llm import get_llm, extract_json
from src.agent.composite_scorer_v2 import score_composite
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
from src.agent.alerts import run_alerts
from src.db.database import get_db

logger = logging.getLogger(__name__)

# Module-level semaphore to cap concurrent LLM calls during dot analysis.
# Empirically: 5 concurrent calls caused 80% rate-limit fallback rate;
# capping at 2 drops it to <10% while adding only ~10-15s of serial time.
_DOT_SEMAPHORE = asyncio.Semaphore(2)


async def _analyze_gated(analyzer, indicators, composite, news, tiers=None, qualitative_sources=None):
    """Call a dot analyzer under the concurrency semaphore (max 2 at once)."""
    async with _DOT_SEMAPHORE:
        return await analyzer(
            indicators=indicators,
            composite=composite,
            news=news,
            tiers=tiers,
            qualitative_sources=qualitative_sources,
        )


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
    trigger_source: str


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
        # Fetch gold 200-day MA for MA-deviation scoring (per Q3 decision)
        gold_ma_200 = None
        try:
            from src.fetchers.market import fetch_gold_200d_ma
            import asyncio as _asyncio
            gold_ma_200 = await _asyncio.to_thread(fetch_gold_200d_ma)
        except Exception:
            pass  # Graceful degradation: gold scores 0 without MA

        result = score_composite(state["indicators"], gold_ma_200=gold_ma_200)
        state["composite_score"] = result
        dur = (time.time() - t0) * 1000
        _record_timing(state, "Composite Scorer", "scorer", "success", dur,
                       input_summary=f"{result.get('available_count', 0)}/{result.get('total_indicators', 30)} indicators",
                       output_summary=f"Score {result['composite']}/30 ({result['interpretation']})")
        state["success_count"] += 1
    except Exception as e:
        dur = (time.time() - t0) * 1000
        _record_timing(state, "Composite Scorer", "scorer", "error", dur, error=str(e))
        state["errors"].append(f"Composite scorer: {e}")
        state["composite_score"] = {"composite": 0, "interpretation": "error", "category_scores": {}, "per_indicator_scores": {}}
    return state


async def node_alerts(state: CrisisState) -> CrisisState:
    """Run alerts engine on composite scorer output — detect transitions + write alerts."""
    t0 = time.time()
    try:
        composite = state.get("composite_score") or {}
        if composite.get("per_indicator_scores"):
            # Extract gold_ma_200 from indicator_details debug info if present
            gold_details = composite.get("indicator_details", {}).get("gold_price", {})
            gold_debug = gold_details.get("debug", {})
            gold_ma_200 = gold_debug.get("ma_200") if gold_debug.get("method") == "ma_deviation" else None

            count = run_alerts(composite, state["indicators"], gold_ma_200=gold_ma_200)
            dur = (time.time() - t0) * 1000
            _record_timing(state, "Alerts Engine", "alerts", "success", dur,
                           output_summary=f"{count} alerts fired")
            if count > 0:
                state["success_count"] += 1
        else:
            dur = (time.time() - t0) * 1000
            _record_timing(state, "Alerts Engine", "alerts", "success", dur,
                           output_summary="No per-indicator scores — skipped")
    except Exception as e:
        dur = (time.time() - t0) * 1000
        _record_timing(state, "Alerts Engine", "alerts", "error", dur, error=str(e))
        state["errors"].append(f"Alerts engine: {e}")
    return state


async def node_indicator_narrator(state: CrisisState) -> CrisisState:
    """Generate 1-sentence plain-language narrative context per indicator via LLM."""
    t0 = time.time()
    try:
        narratives = await generate_indicator_narratives(
            state["indicators"], news=state.get("news")
        )
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
    """Run all 5 dot analyzer LLMs gated by concurrency semaphore (max 2 at once),
    incorporating qualitative fallback search for mixed/qualitative dots.
    """
    t0 = time.time()
    indicators = state["indicators"]
    composite = state["composite_score"] or {"composite": 0, "interpretation": "unknown"}
    news = state.get("news")

    from src.services import init_fallback_run, classify_dots, run_qualitative_fallback, get_fallback_cost

    # 1. Initialize qualitative fallback run state
    init_fallback_run()

    # 2. Classify dot completeness tiers
    dot_tiers = classify_dots(indicators)

    # 3. Identify and execute qualitative fallback searches for mixed/qualitative dots
    fallback_tasks = {}
    for dot_num in range(1, 10):
        tier = dot_tiers.get(dot_num, "live")
        if tier in ("mixed", "qualitative"):
            fallback_tasks[dot_num] = run_qualitative_fallback(dot_num, tier=tier)

    qualitative_sources = {}
    if fallback_tasks:
        fallback_results = await asyncio.gather(*fallback_tasks.values(), return_exceptions=True)
        for dot_num, result in zip(fallback_tasks.keys(), fallback_results):
            dot_key = f"dot_{dot_num}"
            if isinstance(result, Exception):
                logger.error("Qualitative fallback failed for %s", dot_key, exc_info=result)
                qualitative_sources[dot_key] = []
            else:
                qualitative_sources[dot_key] = result.get("sources", [])
                logger.info(
                    "Qualitative fallback completed for %s: %d sources retrieved",
                    dot_key,
                    len(qualitative_sources[dot_key])
                )

    # 4. Construct tiers dict (with dot_ keys and em_currency defaulted to 'live')
    tiers = {f"dot_{num}": dot_tiers.get(num, "live") for num in range(1, 10)}
    tiers["em_currency"] = "live"

    # 5. Run all 5 gated by semaphore — at most 2 LLM calls fire concurrently.
    results = await asyncio.gather(
        _analyze_gated(analyze_geopolitical, indicators, composite, news, tiers, qualitative_sources),
        _analyze_gated(analyze_food_debt, indicators, composite, news, tiers, qualitative_sources),
        _analyze_gated(analyze_financial_em, indicators, composite, news, tiers, qualitative_sources),
        _analyze_gated(analyze_china_political, indicators, composite, news, tiers, qualitative_sources),
        _analyze_gated(analyze_health, indicators, composite, news, tiers, qualitative_sources),
        return_exceptions=True,
    )

    from src.agent.dot_analyzers import _fallback as dot_fallback

    agent_names = ["geopolitical", "food_debt", "financial_em", "china_political", "health"]
    merged = {}

    for i, (name, result) in enumerate(zip(agent_names, results)):
        agent_num = i + 1
        if isinstance(result, Exception):
            # Use rule-based fallback when LLM call fails
            fallback = dot_fallback(name, indicators, tiers=tiers)
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
    for dot_key, dot_data in merged.items():
        if isinstance(dot_data, dict):
            dot_data["tier"] = tiers.get(dot_key, "live")

    state["dot_analyses"] = merged

    # 6. Log total qualitative fallback costs
    cost = get_fallback_cost()
    if cost and cost.get("total_tokens", 0) > 0:
        logger.info(
            "Qualitative fallback total tokens: %d (estimated cost: $%f)",
            cost["total_tokens"],
            cost["total_cost_estimate"]
        )

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
    """Persist all pipeline results to SQLite via db_writer service."""
    t0 = time.time()
    try:
        from src.services.db_writer import save_pipeline_results
        save_pipeline_results(state)
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
    graph.add_node("alerts", node_alerts)
    graph.add_node("indicator_narrator", node_indicator_narrator)
    graph.add_node("dot_analyzers", node_dot_analyzers)
    graph.add_node("pathway_synthesizer", node_pathway_synthesizer)
    graph.add_node("end_state_assessor", node_end_state_assessor)
    graph.add_node("save_to_db", node_save_to_db)

    # Wire edges — sequential pipeline
    # composite_scorer → alerts → indicator_narrator → dot_analyzers → pathway_synthesizer
    # → end_state_assessor → save_to_db → END
    graph.set_entry_point("composite_scorer")
    graph.add_edge("composite_scorer", "alerts")
    graph.add_edge("alerts", "indicator_narrator")
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


# Human-readable labels for each pipeline node (used by progress reporting).
NODE_LABELS: Dict[str, str] = {
    "composite_scorer": "Composite Scorer",
    "alerts": "Alerts Engine",
    "indicator_narrator": "Indicator Narrator",
    "dot_analyzers": "Dot Analyzers",
    "pathway_synthesizer": "Pathway Synthesizer",
    "end_state_assessor": "End State Assessor",
    "save_to_db": "Save to DB",
}


# Graph node ids in execution order
_NODE_ORDER = [
    "composite_scorer",
    "alerts",
    "indicator_narrator",
    "dot_analyzers",
    "pathway_synthesizer",
    "end_state_assessor",
    "save_to_db",
]


async def run_pipeline(
    indicators: Dict[str, Any],
    news: Optional[List[Dict[str, str]]] = None,
    source: str = "api",
    progress_callback: Optional[Callable[[str, str, Optional[str]], Awaitable[None]]] = None,
) -> Dict[str, Any]:
    """Run the full crisis monitor pipeline.

    Args:
        indicators: Dict of indicator name → value pairs.
        news: Optional list of news headline dicts.
        progress_callback: Optional async callback for live progress.
            Called as await progress_callback(node_label, event, error_message)
            where event is "started" or "completed", and error_message is
            None for "started" and set for "completed" if the node failed.

    Returns:
        Pipeline results dict with node timing data.
    """
    graph = get_graph()
    t0 = time.time()

    # Missing-data shim: ensure all 30 registered indicators appear in every snapshot.
    # Any INDICATOR_META slug not in the input dict gets added as None so the pipeline
    # knows about it and can generate a fallback narrative.
    from src.agent.indicator_narrator import INDICATOR_META
    full_indicators = dict(indicators)  # shallow copy to avoid mutating caller's dict
    for slug in INDICATOR_META:
        if slug not in full_indicators:
            full_indicators[slug] = None

    initial_state: CrisisState = {
        "indicators": full_indicators,
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
        "trigger_source": source,
    }

    if progress_callback is None:
        # Fast path: no progress tracking needed
        final_state = await graph.ainvoke(initial_state)
    else:
        # Streaming path: track per-node progress via astream (values mode)
        # astream in "values" mode yields the full state after each node.
        final_state = None
        node_idx = 0

        async for state in graph.astream(initial_state, stream_mode="values"):
            # state is the full CrisisState after a node completed.
            # Emit "started" for the next node (first iteration is initial state).
            if node_idx < len(_NODE_ORDER):
                label = NODE_LABELS.get(_NODE_ORDER[node_idx], _NODE_ORDER[node_idx])
                await progress_callback(label, "started", None)

            # Emit "completed" for the node that just finished (skip index 0 = before any node)
            if node_idx > 0:
                prev_node = _NODE_ORDER[node_idx - 1]
                prev_label = NODE_LABELS.get(prev_node, prev_node)
                # Check if the node that just finished had an error
                node_timing = state.get("node_timing", [])
                error_msg = None
                for rec in node_timing:
                    if rec.get("label") == prev_label and rec.get("status") in ("error", "fallback"):
                        error_msg = rec.get("error", "unknown error")
                        break
                await progress_callback(prev_label, "completed", error_msg)

            node_idx += 1
            final_state = state

        # Emit "completed" for the final node
        if node_idx > 0 and node_idx <= len(_NODE_ORDER) + 1:
            prev_node = _NODE_ORDER[node_idx - 2]  # -2 because we incremented past it
            if prev_node:
                prev_label = NODE_LABELS.get(prev_node, prev_node)
                node_timing = final_state.get("node_timing", []) if final_state else []
                error_msg = None
                for rec in node_timing:
                    if rec.get("label") == prev_label and rec.get("status") in ("error", "fallback"):
                        error_msg = rec.get("error", "unknown error")
                        break
                await progress_callback(prev_label, "completed", error_msg)

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
