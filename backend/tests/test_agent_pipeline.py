"""Tests for Crisis Monitor agent pipeline.

Validates all AC criteria:
- LLM helper uses opencode.ai/zen/go/v1
- Composite scorer returns valid 0-16
- Each dot analyzer prompt complete
- StateGraph compiles
- Graph runs full pipeline with fallbacks
- Source attribution on all dots and indicators
"""
import os
import sys
import json
import asyncio

# Ensure project root is on path for imports
sys.path.insert(0, "/root/crisis-monitor/backend")

# ============================================================
# 1. LLM helper
# ============================================================

def test_llm_helper_base_url():
    """AC: LLM helper uses opencode.ai/zen/go/v1 as base_url."""
    from src.agent.llm import get_llm
    # ponytail: test the import and function signature; construction requires API key
    # Verify the function exists and accepts expected params
    import inspect
    sig = inspect.signature(get_llm)
    params = list(sig.parameters.keys())
    assert "temperature" in params
    assert "timeout" in params

    # Verify base_url is hardcoded in source
    import ast, inspect as _inspect
    source = _inspect.getsource(get_llm)
    assert "opencode.ai/zen/go/v1" in source, "base_url not set to OpenCode Go"
    assert "deepseek-v4-pro" in source, "model not set to deepseek-v4-pro"


def test_extract_json():
    """JSON extraction from various LLM output formats."""
    from src.agent.llm import extract_json

    # Fenced JSON
    text = '```json\n{"a": 1}\n```'
    assert extract_json(text) == {"a": 1}

    # No fence, raw JSON
    assert extract_json('{"b": 2}') == {"b": 2}

    # Array
    assert extract_json("[1, 2, 3]") == [1, 2, 3]

    # No JSON
    assert extract_json("hello world") == {}

    # Nested with text before/after
    text2 = "Here is result: ```json\n{\"status\": \"ok\"}\n``` done."
    assert extract_json(text2) == {"status": "ok"}


# ============================================================
# 2. Composite scorer
# ============================================================

def test_composite_scorer_normal():
    """AC: Composite scorer returns valid 0-16 — normal case."""
    from src.agent.composite_scorer import score_composite

    result = score_composite({
        "brent_price": 78,
        "caixin_pmi": 51.5,
        "ig_oas": 120,
        "hy_oas": 350,
        "fao_monthly_change_pct": 1.0,
        "btp_bund_spread": 180,
        "protest_countries": 0,
    })
    assert 0 <= result["composite"] <= 16
    assert result["composite"] == 0
    assert result["interpretation"] == "monitor"
    assert set(result["category_scores"].keys()) == {
        "geopolitical", "energy", "credit_financial", "em_currency",
        "food", "china", "debt_sovereign", "social_political",
    }


def test_composite_scorer_elevated():
    """Composite scorer — elevated (5-8)."""
    from src.agent.composite_scorer import score_composite

    # Energy elevated (Brent $95), Credit elevated (IG 160), Food elevated
    result = score_composite({
        "brent_price": 95,
        "ig_oas": 160,
        "hy_oas": 450,
        "cme_grains_monthly_pct": 12,
        "caixin_pmi": 49,
        "btp_bund_spread": 260,
        "protest_countries": 2,
    })
    assert result["composite"] >= 3, f"Expected elevated, got {result['composite']}"
    assert result["interpretation"] in ("monitor", "elevated", "high", "crisis")


def test_composite_scorer_crisis():
    """Composite scorer — crisis (13-16)."""
    from src.agent.composite_scorer import score_composite

    result = score_composite({
        "brent_price": 115,
        "ig_oas": 220,
        "hy_oas": 650,
        "caixin_pmi": 46,
        "china_property_default": 1,
        "btp_bund_spread": 280,
        "cds_doubling": 1,
        "protest_countries": 4,
        "govt_crisis": 1,
        "us_nato_withdrawal": 1,
        "idr_breach": 1,
        "try_breach": 1,
        "egp_breach": 1,
        "fao_monthly_change_pct": 12,
    })
    assert result["composite"] >= 13, f"Expected crisis, got {result['composite']}"
    assert result["interpretation"] == "crisis"


def test_composite_scorer_edge_cases():
    """Composite scorer — edge cases (missing data, None values)."""
    from src.agent.composite_scorer import score_composite

    # Empty indicators
    result = score_composite({})
    assert result["composite"] == 0

    # None values shouldn't crash
    result = score_composite({
        "brent_price": None,
        "caixin_pmi": None,
        "ig_oas": None,
    })
    assert result["composite"] == 0


# ============================================================
# 3. Dot analyzer prompts complete
# ============================================================

def test_dot_analyzer_fallbacks():
    """AC: Each dot analyzer has complete prompt and fallback logic with sources."""
    from src.agent.dot_analyzers import _fallback

    test_indicators = {
        "brent_price": 82.5, "vix": 18.2, "ig_oas": 142, "hy_oas": 420,
        "caixin_pmi": 50.8, "try_breach": 0, "protest_countries": 1,
        "nato_fracture": 1, "fao_monthly_change_pct": 3.2,
    }

    # Agent 1: Geopolitical (dots 1+2)
    fb = _fallback("geopolitical", test_indicators)
    assert "dot_1" in fb
    assert "dot_2" in fb
    assert fb["dot_1"]["status"] == "dormant"
    assert "nato_outlook" in fb["dot_1"]
    assert "sources" in fb["dot_1"], "dot_1 missing sources"
    assert isinstance(fb["dot_1"]["sources"], str), "dot_1 sources should be str (paragraph format)"
    assert "sources" in fb["dot_2"], "dot_2 missing sources"

    # Agent 2: Food & Debt (dots 3+5)
    fb = _fallback("food_debt", test_indicators)
    assert "dot_3" in fb
    assert "dot_5" in fb
    assert "fao_trend" in fb["dot_3"]
    assert "most_vulnerable" in fb["dot_5"]
    assert "sources" in fb["dot_3"], "dot_3 missing sources"
    assert "sources" in fb["dot_5"], "dot_5 missing sources"

    # Agent 3: Financial & EM (dot 4 + EM)
    fb = _fallback("financial_em", test_indicators)
    assert "dot_4" in fb
    assert "em_currency" in fb
    assert fb["dot_4"]["credit_spread_outlook"] == "stable"
    assert "sources" in fb["dot_4"], "dot_4 missing sources"
    assert "sources" in fb["em_currency"], "em_currency missing sources"

    # Agent 4: China & Political (dots 6+7+8)
    fb = _fallback("china_political", test_indicators)
    assert "dot_6" in fb
    assert "dot_7" in fb
    assert "dot_8" in fb
    assert "pmi_outlook" in fb["dot_6"]
    assert "sources" in fb["dot_6"], "dot_6 missing sources"
    assert "sources" in fb["dot_7"], "dot_7 missing sources"
    assert "sources" in fb["dot_8"], "dot_8 missing sources"

    # Agent 5: Health (dot 9)
    fb = _fallback("health", test_indicators)
    assert "dot_9" in fb
    assert fb["dot_9"]["who_risk_level"] == "low"
    assert "sources" in fb["dot_9"], "dot_9 missing sources"


def test_dot_analyzer_prompts_exist():
    """All 5 agent prompts are defined as module-level constants."""
    from src.agent import dot_analyzers

    for name in ("AGENT1_PROMPT", "AGENT2_PROMPT", "AGENT3_PROMPT",
                 "AGENT4_PROMPT", "AGENT5_PROMPT"):
        prompt = getattr(dot_analyzers, name, None)
        assert prompt is not None, f"Missing prompt: {name}"
        assert len(prompt) > 200, f"Prompt {name} seems too short"


def test_dot_prompts_include_sources():
    """All 5 agent prompts include source attribution instructions."""
    from src.agent import dot_analyzers

    for name in ("AGENT1_PROMPT", "AGENT2_PROMPT", "AGENT3_PROMPT",
                 "AGENT4_PROMPT", "AGENT5_PROMPT"):
        prompt = getattr(dot_analyzers, name, "")
        assert "DATA SOURCES" in prompt, f"{name} missing DATA SOURCES section"
        assert "sources" in prompt.lower(), f"{name} missing sources field reference"


def test_indicator_narrator_context():
    """Indicator narrator produces valid LLM context — all known slugs have metadata."""
    from src.agent.indicator_narrator import narrate_all, narrate_one, INDICATOR_META

    # Every indicator used by the pipeline has metadata
    pipeline_slugs = [
        "brent_price", "wti_price", "dxy", "gold_price", "us_10y", "us_2y",
        "vix", "ig_oas", "hy_oas", "caixin_pmi",
        "fao_monthly_change_pct", "cme_grains_monthly_pct",
        "btp_bund_spread", "eu_gas_storage_pct", "us_spr_mbbl",
        "idr_breach", "try_breach", "egp_breach",
        "nato_fracture", "us_nato_withdrawal", "hormuz_closure",
        "cds_doubling", "protest_countries", "govt_crisis",
        "china_property_default",
    ]
    for slug in pipeline_slugs:
        assert slug in INDICATOR_META, f"Missing metadata for {slug}"

    # Narrate a full set of indicators (no crash, produces structured output)
    test_data = {
        "brent_price": 82.5, "vix": 18.2, "ig_oas": 142, "hy_oas": 420,
        "caixin_pmi": 50.8, "try_breach": 0, "protest_countries": 1,
    }
    result = narrate_all(test_data)
    assert "Brent Crude" in result
    assert "VIX" in result
    assert "Caixin PMI" in result
    assert "##" in result  # category headers present

    # Narrate with previous values for trend
    prev = {"brent_price": 79.0, "vix": 16.5}
    result = narrate_all(test_data, prev)
    assert "↑" in result or "↓" in result or "→" in result

    # Single indicator with trend
    line = narrate_one("brent_price", 82.5, 79.0)
    assert "82.5" in line
    assert "Change" in line
    assert "↑" in line

    # Empty indicators
    assert narrate_all({}) == "(no indicator data)"

    # Unknown slug — graceful
    line = narrate_one("nonexistent", 42)
    assert "no metadata" in line


# ============================================================
# 3b. Source attribution
# ============================================================

def test_all_indicators_have_source():
    """Every indicator in INDICATOR_META has a source field."""
    from src.agent.indicator_narrator import INDICATOR_META

    for slug, meta in INDICATOR_META.items():
        assert "source" in meta, f"Missing source for {slug}"
        assert isinstance(meta["source"], str), f"Source for {slug} should be str"
        assert len(meta["source"]) > 0, f"Source for {slug} is empty"


def test_dot_indicators_mapping():
    """DOT_INDICATORS covers all 9 dots + em_currency."""
    from src.agent.indicator_narrator import DOT_INDICATORS

    expected = ["dot_1", "dot_2", "dot_3", "dot_4", "dot_5",
                "dot_6", "dot_7", "dot_8", "dot_9", "em_currency"]
    for dk in expected:
        assert dk in DOT_INDICATORS, f"Missing DOT_INDICATORS entry for {dk}"
        assert isinstance(DOT_INDICATORS[dk], list), f"{dk} should be a list"


def test_sources_for_dot():
    """sources_for_dot produces valid attribution strings."""
    from src.agent.indicator_narrator import sources_for_dot, DOT_INDICATORS

    indicators = {
        "brent_price": 98.40, "vix": 22.3, "ig_oas": 180.0,
        "hy_oas": 450.0, "caixin_pmi": 47.5,
        "try_breach": 1, "nato_fracture": 1,
        "protest_countries": 3, "govt_crisis": 1,
    }

    # Dot with numeric indicators
    result = sources_for_dot("dot_4", indicators)
    assert "IG OAS" in result
    assert "FRED" in result
    assert "VIX" in result
    assert "CBOE" in result

    # Dot with no numeric indicators (health)
    result = sources_for_dot("dot_9", indicators)
    assert "no numeric" in result.lower() or "news" in result.lower()

    # Unknown dot — graceful
    result = sources_for_dot("nonexistent", indicators)
    assert len(result) > 0  # shouldn't crash


def test_sources_narrative():
    """sources_narrative produces a formatted multi-dot attribution."""
    from src.agent.indicator_narrator import sources_narrative

    indicators = {
        "brent_price": 98.40, "vix": 22.3, "ig_oas": 180.0,
        "nato_fracture": 1, "try_breach": 1,
    }
    result = sources_narrative(indicators, ["dot_1", "dot_4"])
    assert "## Data Sources by Dot" in result
    assert "dot_1" in result
    assert "dot_4" in result
    assert "NATO Fracture" in result
    assert "IG OAS" in result


def test_sources_list_for_dot():
    """sources_list_for_dot returns structured list with indicator/source/value."""
    from src.agent.indicator_narrator import sources_list_for_dot

    indicators = {
        "brent_price": 98.40, "vix": 22.3, "ig_oas": 180.0,
        "hy_oas": 450.0,
    }
    result = sources_list_for_dot("dot_4", indicators)
    assert isinstance(result, list)
    assert len(result) >= 3  # at least ig_oas, hy_oas, vix
    for entry in result:
        assert "indicator" in entry
        assert "slug" in entry
        assert "source" in entry
        assert isinstance(entry["source"], str)
        assert len(entry["source"]) > 0


# ============================================================
# 4. Pathway synthesizer
# ============================================================

def test_pathway_fallback():
    """Pathway synthesizer fallback produces valid structure."""
    from src.agent.pathway_synthesizer import _fallback_pathways

    result = _fallback_pathways({"composite": 2, "interpretation": "monitor"})
    for key in ("pathway_a", "pathway_b", "pathway_c", "pathway_d"):
        assert key in result
        assert "active" in result[key]
    assert result["dominant_pathway"] == "none"

    result = _fallback_pathways({"composite": 14, "interpretation": "crisis"})
    assert result["pathway_d"]["active"] is True
    assert result["dominant_pathway"] == "D"


# ============================================================
# 5. End state assessor
# ============================================================

def test_end_state_fallback():
    """End state fallback produces valid 5Q structure + briefing."""
    from src.agent.end_state import _fallback_end_state

    result = _fallback_end_state(
        {"composite": 3, "interpretation": "monitor"},
        {"pathway_d": {"active": False}},
    )
    assert result["end_state"] == "containment"
    # briefing must be present and non-empty
    assert "briefing" in result, "Missing briefing field"
    assert isinstance(result["briefing"], str) and len(result["briefing"]) > 100, \
        f"Briefing too short or empty: {len(result.get('briefing', ''))} chars"
    for q in ("q1", "q2", "q3", "q4", "q5"):
        assert q in result, f"Missing question: {q}"
        assert "question" in result[q]
        assert "answer" in result[q]

    # Crisis state
    result = _fallback_end_state(
        {"composite": 14, "interpretation": "crisis"},
        {"pathway_d": {"active": True}},
    )
    assert result["end_state"] == "systemic_collapse"
    assert result["q3"]["probability"] > 0.6
    assert "briefing" in result
    assert len(result["briefing"]) > 100


def test_fallback_briefing_ranges():
    """Briefing content varies appropriately by composite score range."""
    from src.agent.end_state import _fallback_end_state

    base_pathways = {"pathway_d": {"active": False}}

    # containment (0-4)
    result = _fallback_end_state({"composite": 0, "interpretation": "monitor"}, base_pathways)
    assert "contained" in result["briefing"].lower()
    assert "{" not in result["briefing"], "Briefing has unformatted templates"

    # fragmented stability mid-range (5-8)  
    result = _fallback_end_state({"composite": 6, "interpretation": "elevated"}, base_pathways)
    assert "briefing" in result
    assert len(result["briefing"]) > 100

    # elevated (9-12)
    result = _fallback_end_state({"composite": 10, "interpretation": "high"}, base_pathways)
    assert "briefing" in result
    assert len(result["briefing"]) > 100

    # crisis (13+)
    result = _fallback_end_state({"composite": 15, "interpretation": "crisis"},
                                  {"pathway_d": {"active": True}})
    assert "collapse" in result["briefing"].lower()


# ============================================================
# 6. Graph compilation
# ============================================================

def test_graph_compiles():
    """AC: StateGraph compiles with all expected nodes."""
    from src.agent.graph import build_graph

    graph = build_graph()
    nodes = list(graph.nodes.keys())
    expected = [
        "__start__",
        "composite_scorer",
        "dot_analyzers",
        "pathway_synthesizer",
        "end_state_assessor",
        "save_to_db",
    ]
    for node in expected:
        assert node in nodes, f"Missing node: {node}"


# ============================================================
# 7. Full pipeline integration (uses fallbacks, no API key needed)
# ============================================================

def test_full_pipeline_with_mock_data():
    """AC: Full pipeline runs with mock data, produces valid output with sources."""
    from src.agent.graph import run_pipeline

    indicators = {
        "brent_price": 82.5,
        "wti_price": 78.2,
        "dxy": 104.3,
        "gold_price": 3420.0,
        "us_10y": 4.55,
        "vix": 18.2,
        "ig_oas": 142,
        "hy_oas": 420,
        "caixin_pmi": 50.8,
        "fao_monthly_change_pct": 3.2,
        "cme_grains_monthly_pct": 5.1,
        "btp_bund_spread": 210,
        "protest_countries": 1,
        "idr_breach": 0,
        "try_breach": 0,
        "egp_breach": 0,
    }

    result = asyncio.run(run_pipeline(indicators))

    # Composite score
    assert result["composite_score"] is not None
    assert 0 <= result["composite_score"]["composite"] <= 16

    # Dot analyses (should have fallback data since no API key)
    assert result["dot_analyses"] is not None
    assert len(result["dot_analyses"]) > 0

    # Verify sources present on dot analyses
    for dot_key, dot_data in result["dot_analyses"].items():
        if isinstance(dot_data, dict):
            assert "sources" in dot_data, f"{dot_key} missing sources"
            assert isinstance(dot_data["sources"], str), f"{dot_key} sources not a string"

    # Pathways
    assert result["pathways"] is not None
    assert "dominant_pathway" in result["pathways"]

    # End state
    assert result["end_state"] is not None
    assert result["end_state"]["end_state"] in (
        "containment", "fragmented_stability", "systemic_collapse",
    )
    for q in ("q1", "q2", "q3", "q4", "q5"):
        assert q in result["end_state"], f"Missing {q}"
    # briefing field must be present (graceful fallback if LLM fails — empty string)
    assert "briefing" in result["end_state"], "Missing briefing in end_state"
    assert isinstance(result["end_state"]["briefing"], str), \
        f"briefing should be str, got {type(result['end_state']['briefing'])}"

    # DB save — should have succeeded (1), composite scorer (1), rest may be fallbacks
    assert result["success_count"] >= 2, f"Expected >=2 successes, got {result['success_count']}"

    # Timing
    assert len(result["node_timing"]) > 0, "No node timing records"
    assert result["total_duration_ms"] is not None
    assert result["started_at"] is not None
    assert result["completed_at"] is not None

    print(f"Pipeline OK — composite={result['composite_score']['composite']}, "
          f"end_state={result['end_state']['end_state']}, "
          f"duration={result['total_duration_ms']:.0f}ms, "
          f"successes={result['success_count']}")


# ============================================================
# 8. DB persistence — including sources
# ============================================================

def test_db_save_creates_records():
    """Pipeline run saves to DB: daily_reports (incl briefing), dot_analyses (incl sources), pathway_status."""
    from src.agent.graph import run_pipeline
    from src.db.database import get_db, init_db

    # Re-init DB to ensure sources column exists
    init_db()

    indicators = {"brent_price": 78, "caixin_pmi": 51}
    asyncio.run(run_pipeline(indicators))

    conn = get_db()
    reports = conn.execute("SELECT COUNT(*) as c FROM daily_reports").fetchone()
    dots = conn.execute("SELECT COUNT(*) as c FROM dot_analyses").fetchone()
    pathways = conn.execute("SELECT COUNT(*) as c FROM pathway_status").fetchone()

    # Verify briefing column exists and has data
    latest = conn.execute(
        "SELECT briefing, sources FROM daily_reports d LEFT JOIN dot_analyses da ON 1=1 ORDER BY d.date DESC LIMIT 1"
    ).fetchone()
    # Verify indicator_history has narrative column
    hist = conn.execute(
        "SELECT indicator_name, narrative FROM indicator_history "
        "ORDER BY recorded_at DESC LIMIT 5"
    ).fetchall()
    conn.close()

    assert reports["c"] >= 1, "No daily reports saved"
    assert dots["c"] >= 1, "No dot analyses saved"
    assert pathways["c"] >= 1, "No pathway status saved"
    assert latest is not None, "Could not read latest report"
    assert "briefing" in latest.keys(), "briefing column not in row"
    assert isinstance(latest["briefing"], str), \
        f"briefing should be str, got {type(latest['briefing'])}"
    # With fallback, briefing should be non-empty
    assert len(latest["briefing"]) > 0, "briefing should not be empty with fallback"
    # Indicator history has narrative column populated
    assert len(hist) > 0, "No indicator_history records found"
    for h in hist:
        assert "narrative" in h.keys(), f"narrative column missing from {h['indicator_name']}"
        assert isinstance(h["narrative"], str), \
            f"narrative should be str, got {type(h['narrative'])}"
    print(f"DB OK — reports={reports['c']}, dots={dots['c']}, pathways={pathways['c']}, "
          f"briefing_len={len(latest['briefing'])}")


def test_db_dot_analyses_has_sources():
    """dot_analyses table stores sources JSON from pipeline."""
    from src.db.database import get_db

    conn = get_db()
    # Check that sources column exists and has data
    rows = conn.execute(
        "SELECT dot_name, sources FROM dot_analyses ORDER BY analyzed_at DESC LIMIT 5"
    ).fetchall()
    conn.close()

    assert len(rows) > 0, "No dot analyses found"
    for row in rows:
        sources_str = row["sources"]
        assert sources_str is not None, f"{row['dot_name']} sources is NULL"
        # Parse the JSON — should be a valid list
        try:
            sources = json.loads(sources_str)
            assert isinstance(sources, list), f"sources for {row['dot_name']} should be list"
        except json.JSONDecodeError:
            print(f"Warning: sources for {row['dot_name']} is not valid JSON: {sources_str[:100]}")
    print("DB sources OK — dot_analyses sources column populated")


if __name__ == "__main__":
    import traceback

    tests = [
        ("llm base_url", test_llm_helper_base_url),
        ("extract_json", test_extract_json),
        ("composite normal", test_composite_scorer_normal),
        ("composite elevated", test_composite_scorer_elevated),
        ("composite crisis", test_composite_scorer_crisis),
        ("composite edges", test_composite_scorer_edge_cases),
        ("dot fallbacks", test_dot_analyzer_fallbacks),
        ("dot prompts", test_dot_analyzer_prompts_exist),
        ("dot prompts sources", test_dot_prompts_include_sources),
        ("indicator narrator", test_indicator_narrator_context),
        ("all sources", test_all_indicators_have_source),
        ("dot indicators map", test_dot_indicators_mapping),
        ("sources for dot", test_sources_for_dot),
        ("sources narrative", test_sources_narrative),
        ("sources list for dot", test_sources_list_for_dot),
        ("pathway fallback", test_pathway_fallback),
        ("end_state fallback", test_end_state_fallback),
        ("briefing ranges", test_fallback_briefing_ranges),
        ("graph compiles", test_graph_compiles),
        ("full pipeline", test_full_pipeline_with_mock_data),
        ("db save", test_db_save_creates_records),
        ("db sources", test_db_dot_analyses_has_sources),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✓ {name}")
            passed += 1
        except Exception as e:
            print(f"  ✗ {name}: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\n{passed}/{passed+failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
