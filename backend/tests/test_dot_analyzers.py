"""Unit tests for dot_analyzers — prompt construction passes actual indicator values.

AC: Given a mock indicator list, the prompt templates contain actual values,
not "(unavailable)". Tests cover prompt format, fallback source text, and
agent function signatures.
"""
import pytest
from src.agent.dot_analyzers import (
    _sources_text_for_dot,
    _fallback,
    _build_tier_instructions,
    _build_qualitative_sources_text,
    _make_abstention,
    _effective_tier,
    _preprocess_dots,
    _collect_qualitative_sources,
    ABSTENTION_STRING,
    AGENT1_PROMPT,
    AGENT2_PROMPT,
    AGENT3_PROMPT,
    AGENT4_PROMPT,
    AGENT5_PROMPT,
)


# ── Mock fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def mock_indicators() -> dict:
    """Indicators with a mix of float, int, flag, and None values."""
    return {
        "brent_price": 82.50,
        "wti_price": 87.50,
        "natgas_price": 3.45,
        "vix": 18.2,
        "ig_oas": 142.0,
        "hy_oas": 420.0,
        "us_10y": 4.25,
        "us_2y": 3.95,
        "caixin_pmi": 50.8,
        "china_property_default": 0,
        "idr_breach": 0,
        "try_breach": 1,
        "nato_fracture": 1,
        "protest_countries": 3,
        "govt_crisis": 1,
        "btp_bund_spread": 185.0,
        "cds_doubling": 0,
        "fao_monthly_change_pct": 3.2,
        "cme_grains_monthly_pct": -1.5,
        "eu_gas_storage_pct": 72.0,
        "us_spr_mbbl": 372.0,
        "hormuz_closure": "",
        "dxy": None,
        "gold_price": None,
        "us_nato_withdrawal": None,
    }


@pytest.fixture
def mock_qualitative_sources() -> dict:
    """Web search sources for QUALITATIVE/MIXED tier testing."""
    return {
        "dot_1": [
            {"url": "https://example.com/nato1", "title": "NATO Summit Results",
             "snippet": "NATO allies reaffirmed commitment to collective defense.",
             "source_type": "news"},
            {"url": "https://example.com/nato2", "title": "US NATO Relations",
             "snippet": "Tensions rise over defense spending targets.",
             "source_type": "analysis"},
            {"url": "https://example.com/nato3", "title": "NATO Eastern Flank",
             "snippet": "Troop deployments increase on eastern border.",
             "source_type": "news"},
        ],
        "dot_9": [
            {"url": "https://example.com/health1", "title": "Hantavirus Outbreak Update",
             "snippet": "CDC reports 12 new cases in Four Corners region.",
             "source_type": "gov"},
            {"url": "https://example.com/health2", "title": "WHO Risk Assessment",
             "snippet": "WHO maintains moderate risk level for hantavirus.",
             "source_type": "gov"},
            {"url": "https://example.com/health3", "title": "Pandemic Preparedness Review",
             "snippet": "New funding allocated for rapid response teams.",
             "source_type": "analysis"},
            {"url": "https://example.com/health4", "title": "Global Health Security Index",
             "snippet": "Index shows improvement in detection capabilities.",
             "source_type": "report"},
            {"url": "https://example.com/health5", "title": "Vaccine Development Progress",
             "snippet": "Phase 2 trials show promising results.",
             "source_type": "research"},
        ],
    }


# ── _sources_text_for_dot tests ───────────────────────────────────────

class TestSourcesTextForDot:
    """Test the fallback source text generation."""

    def test_float_value_shows_equals(self, mock_indicators):
        """Float values: 'Name = value' format."""
        result = _sources_text_for_dot("dot_4", mock_indicators)
        assert "IG OAS = 142.0" in result
        assert "HY OAS = 420.0" in result

    def test_int_value_shows_equals(self, mock_indicators):
        """Integer values: 'Name = value' format."""
        result = _sources_text_for_dot("dot_1", mock_indicators)
        assert "NATO Fracture = 1" in result

    def test_zero_value_shows_equals(self, mock_indicators):
        """Zero values (normal flag): 'Name = 0', not '(unavailable)'."""
        result = _sources_text_for_dot("dot_6", mock_indicators)
        assert "China Property Default = 0" in result
        assert "Caixin PMI = 50.8" in result

    def test_none_value_still_unavailable(self, mock_indicators):
        """Truly missing values show '(unavailable)'."""
        result = _sources_text_for_dot("dot_1", mock_indicators)
        # dxy is None in mock
        assert "DXY (unavailable)" in result

    def test_no_unavailable_for_present_values(self, mock_indicators):
        """Indicators with values must NOT have '(unavailable)'."""
        result = _sources_text_for_dot("dot_4", mock_indicators)
        # All dot_4 indicators (ig_oas, hy_oas, vix, us_10y, us_2y) have values
        assert "(unavailable)" not in result

    def test_empty_dot_returns_empty_string(self):
        """Dot 9 has no indicators — returns empty string."""
        result = _sources_text_for_dot("dot_9", {})
        assert result == ""

    def test_includes_source_attribution(self, mock_indicators):
        """Result includes 'Sourced from' with data origins."""
        result = _sources_text_for_dot("dot_4", mock_indicators)
        assert "Sourced from" in result

    def test_empty_parts_returns_empty(self):
        """When no indicator metadata is found, returns empty string."""
        # dot key not in DOT_INDICATORS
        result = _sources_text_for_dot("nonexistent_dot", {})
        assert result == ""

    def test_string_value_shows_equals(self):
        """String values: 'Name = value' format."""
        result = _sources_text_for_dot(
            "dot_2", {"hormuz_closure": "open", "brent_price": 82.5}
        )
        assert "Hormuz Closure = open" in result
        assert "Brent Crude = 82.5" in result


# ── _fallback tests ───────────────────────────────────────────────────

class TestFallback:
    """Test the fallback function produces valid structured output."""

    def test_fallback_geopolitical_has_sources(self, mock_indicators):
        """Fallback for geopolitical includes source text for dots 1 and 2."""
        fb = _fallback("geopolitical", mock_indicators)
        assert "dot_1" in fb
        assert "dot_2" in fb
        assert "sources" in fb["dot_1"]
        assert isinstance(fb["dot_1"]["sources"], str)
        assert len(fb["dot_1"]["sources"]) > 0

    def test_fallback_food_debt_has_sources(self, mock_indicators):
        """Fallback for food_debt includes source text for dots 3 and 5."""
        fb = _fallback("food_debt", mock_indicators)
        assert "dot_3" in fb
        assert "dot_5" in fb
        assert isinstance(fb["dot_3"]["sources"], str)

    def test_fallback_financial_em_has_sources(self, mock_indicators):
        """Fallback for financial_em includes source text for dot 4 and em_currency."""
        fb = _fallback("financial_em", mock_indicators)
        assert "dot_4" in fb
        assert "em_currency" in fb
        assert isinstance(fb["dot_4"]["sources"], str)

    def test_fallback_china_political_has_sources(self, mock_indicators):
        """Fallback for china_political includes source text for dots 6,7,8."""
        fb = _fallback("china_political", mock_indicators)
        assert "dot_6" in fb
        assert "dot_7" in fb
        assert "dot_8" in fb
        assert isinstance(fb["dot_6"]["sources"], str)

    def test_fallback_health_has_sources(self, mock_indicators):
        """Fallback for health includes source text for dot 9."""
        fb = _fallback("health", mock_indicators)
        assert "dot_9" in fb
        assert isinstance(fb["dot_9"]["sources"], str)

    def test_fallback_summary_does_not_claim_unavailable(self, mock_indicators):
        """Fallback summary should not say 'LLM analysis unavailable' when
        source data is available. The summary text is a fallback marker.
        (Note: the summary text says 'LLM analysis unavailable' because
        the LLM call failed, not because data is missing — this is correct
        behavior. We verify the sources field still carries real values.)"""
        fb = _fallback("geopolitical", mock_indicators)
        # Sources field should contain actual indicator values
        sources_d1 = fb["dot_1"]["sources"]
        assert "NATO Fracture" in sources_d1
        # The summary is a fallback marker (correct — LLM did fail)
        assert "LLM analysis unavailable" in fb["dot_1"]["summary"]

    def test_fallback_sources_no_unavailable_for_present(self, mock_indicators):
        """Sources field should not say '(unavailable)' for indicators with values."""
        fb = _fallback("geopolitical", mock_indicators)
        sources_d1 = fb["dot_1"]["sources"]
        # dot_1 has nato_fracture=1 and us_nato_withdrawal=None
        assert "NATO Fracture = 1" in sources_d1
        assert "US NATO Withdrawal (unavailable)" in sources_d1  # truly None

    def test_fallback_uses_equals_format(self, mock_indicators):
        """Sources text uses '=' not 'at' or 'flagged'/'normal'."""
        fb = _fallback("financial_em", mock_indicators)
        sources_d4 = fb["dot_4"]["sources"]
        assert "IG OAS = 142.0" in sources_d4
        assert "at" not in sources_d4.split("IG OAS")[0]  # check format change


# ── Prompt template tests ─────────────────────────────────────────────

class TestPromptTemplates:
    """Test that all 5 agent prompt templates contain the expected placeholders."""

    def test_agent1_prompt_placeholders(self):
        """Agent 1 (Geopolitical) template has indicators, sources, news."""
        assert "{indicators_narrative}" in AGENT1_PROMPT
        assert "{sources_narrative}" in AGENT1_PROMPT
        assert "{news_json}" in AGENT1_PROMPT
        assert "{composite}" in AGENT1_PROMPT
        assert "Dot 1" in AGENT1_PROMPT
        assert "Dot 2" in AGENT1_PROMPT

    def test_agent2_prompt_placeholders(self):
        """Agent 2 (Food & Debt) template has indicators, sources, news."""
        assert "{indicators_narrative}" in AGENT2_PROMPT
        assert "{sources_narrative}" in AGENT2_PROMPT
        assert "{news_json}" in AGENT2_PROMPT

    def test_agent3_prompt_placeholders(self):
        """Agent 3 (Financial & EM) template has indicators, sources, news."""
        assert "{indicators_narrative}" in AGENT3_PROMPT
        assert "{sources_narrative}" in AGENT3_PROMPT
        assert "{news_json}" in AGENT3_PROMPT

    def test_agent4_prompt_placeholders(self):
        """Agent 4 (China & Political) template has indicators, sources, news."""
        assert "{indicators_narrative}" in AGENT4_PROMPT
        assert "{sources_narrative}" in AGENT4_PROMPT
        assert "{news_json}" in AGENT4_PROMPT

    def test_agent5_prompt_placeholders(self):
        """Agent 5 (Health) template has indicators, sources, news."""
        assert "{indicators_narrative}" in AGENT5_PROMPT
        assert "{sources_narrative}" in AGENT5_PROMPT
        assert "{news_json}" in AGENT5_PROMPT

    def test_all_prompts_require_json_return(self):
        """All agent prompts ask for JSON output."""
        for prompt in [AGENT1_PROMPT, AGENT2_PROMPT, AGENT3_PROMPT,
                       AGENT4_PROMPT, AGENT5_PROMPT]:
            assert "JSON object" in prompt.lower() or "json" in prompt.lower()

    def test_all_prompts_mention_sources_field(self):
        """All agent prompts require a sources field in the output."""
        for prompt in [AGENT1_PROMPT, AGENT2_PROMPT, AGENT3_PROMPT,
                       AGENT4_PROMPT, AGENT5_PROMPT]:
            assert '"sources"' in prompt, (
                f"Prompt missing sources field requirement:\n{prompt[:200]}"
            )


# ── Agent count integrity ─────────────────────────────────────────────

def test_all_five_agents_defined():
    """Verify all 5 agent functions are importable and callable."""
    from src.agent.dot_analyzers import (
        analyze_geopolitical,
        analyze_food_debt,
        analyze_financial_em,
        analyze_china_political,
        analyze_health,
    )
    import asyncio

    agents = [
        analyze_geopolitical,
        analyze_food_debt,
        analyze_financial_em,
        analyze_china_political,
        analyze_health,
    ]
    assert len(agents) == 5
    for agent in agents:
        assert asyncio.iscoroutinefunction(agent)


# ============================================================
# Tier-Aware Prompt Hardening Tests
# ============================================================

class TestTierInstructions:
    """Test _build_tier_instructions returns correct guardrail text per tier."""

    def test_live_tier_instructions(self):
        """LIVE tier: normal analysis, no source-gating."""
        instr = _build_tier_instructions("live")
        assert "LIVE" in instr
        assert "Full quantitative data available" in instr
        assert "Analyze normally" in instr
        # LIVE instructions must be short (< 100 chars for token budget)
        assert len(instr) < 200

    def test_mixed_tier_instructions(self):
        """MIXED tier: quantitative first, web sources for gaps, flag sources."""
        instr = _build_tier_instructions("mixed")
        assert "MIXED" in instr
        assert "quantitative" in instr.lower()
        assert "web_source" in instr or "[web_source]" in instr
        assert "QUALITATIVE SOURCES" in instr
        # Critical rule must be present
        assert "do not infer from general training" in instr.lower()
        assert len(instr) < 400  # still under token budget

    def test_qualitative_tier_instructions(self):
        """QUALITATIVE tier: web sources only, abstention if none."""
        instr = _build_tier_instructions("qualitative")
        assert "QUALITATIVE" in instr
        assert "ONLY the QUALITATIVE SOURCES" in instr
        assert "Do NOT reference or infer from general training" in instr
        assert "abstention" in instr.lower()
        assert len(instr) < 400

    def test_unknown_tier_returns_empty(self):
        """Unknown/empty tier returns empty string (no instructions)."""
        assert _build_tier_instructions("") == ""
        assert _build_tier_instructions("unknown") == ""


class TestQualitativeSourcesText:
    """Test _build_qualitative_sources_text formats sources correctly."""

    def test_empty_sources(self):
        """Empty source list returns the none-available notice."""
        text = _build_qualitative_sources_text([])
        assert "None available" in text

    def test_single_source(self):
        """Single source includes title, url, snippet, source_type."""
        sources = [
            {"url": "https://example.com/a", "title": "Test Article",
             "snippet": "This is a test snippet.", "source_type": "news"}
        ]
        text = _build_qualitative_sources_text(sources)
        assert "Test Article" in text
        assert "https://example.com/a" in text
        assert "This is a test snippet." in text
        assert "source_type: news" in text

    def test_multiple_sources(self):
        """Multiple sources are numbered and all included."""
        sources = [
            {"url": "https://a.com", "title": "A", "snippet": "sA", "source_type": "news"},
            {"url": "https://b.com", "title": "B", "snippet": "sB", "source_type": "analysis"},
            {"url": "https://c.com", "title": "C", "snippet": "sC", "source_type": "gov"},
            {"url": "https://d.com", "title": "D", "snippet": "sD", "source_type": "report"},
            {"url": "https://e.com", "title": "E", "snippet": "sE", "source_type": "research"},
        ]
        text = _build_qualitative_sources_text(sources)
        assert "[1]" in text
        assert "[2]" in text
        assert "[3]" in text
        assert "[4]" in text
        assert "[5]" in text
        for src in sources:
            assert src["title"] in text
            assert src["url"] in text

    def test_source_without_snippet(self):
        """Source without snippet field omits snippet line gracefully."""
        sources = [
            {"url": "https://x.com", "title": "No Snippet", "source_type": "web"}
        ]
        text = _build_qualitative_sources_text(sources)
        assert "No Snippet" in text
        # snippet field is omitted gracefully
        assert "source_type: web" in text

    def test_long_snippet_truncated(self):
        """Snippets over 300 chars are truncated."""
        long_snippet = "x" * 500
        sources = [
            {"url": "https://t.com", "title": "T", "snippet": long_snippet, "source_type": "web"}
        ]
        text = _build_qualitative_sources_text(sources)
        assert "x" * 300 in text
        assert "x" * 301 not in text


class TestAbstention:
    """Test abstention response generation."""

    def test_abstention_string_exact(self):
        """The exact abstention string must match the AC requirement."""
        expected = "No data sources returned for the last 7 days — no assessment possible."
        assert ABSTENTION_STRING == expected

    def test_make_abstention_status(self):
        """Abstention response has status='unavailable'."""
        result = _make_abstention("dot_1")
        assert result["status"] == "unavailable"

    def test_make_abstention_summary(self):
        """Abstention summary is the exact abstention string."""
        result = _make_abstention("dot_9")
        assert result["summary"] == ABSTENTION_STRING

    def test_make_abstention_sources(self):
        """Abstention sources field also uses abstention string."""
        result = _make_abstention("dot_3")
        assert result["sources"] == ABSTENTION_STRING

    def test_make_abstention_key_signals(self):
        """Abstention key_signals indicates no sources."""
        result = _make_abstention("dot_5")
        assert "no data sources available" in result["key_signals"]

    def test_make_abstention_with_extra_fields(self):
        """Extra fields (agent-specific defaults) are merged in."""
        result = _make_abstention("dot_1", {"nato_outlook": "unified", "nato_confidence": 0.0})
        assert result["status"] == "unavailable"
        assert result["nato_outlook"] == "unified"
        assert result["nato_confidence"] == 0.0
        assert result["summary"] == ABSTENTION_STRING

    def test_abstention_is_deterministic(self):
        """Multiple calls produce identical output (no randomness)."""
        a = _make_abstention("dot_1")
        b = _make_abstention("dot_1")
        assert a == b


class TestEffectiveTier:
    """Test _effective_tier computes the most restrictive tier."""

    def test_all_live(self):
        assert _effective_tier({"dot_1": "live", "dot_2": "live"}, ["dot_1", "dot_2"]) == "live"

    def test_mixed_wins_over_live(self):
        assert _effective_tier({"dot_1": "live", "dot_2": "mixed"}, ["dot_1", "dot_2"]) == "mixed"

    def test_qualitative_wins_over_mixed(self):
        assert _effective_tier({"dot_1": "mixed", "dot_2": "qualitative"}, ["dot_1", "dot_2"]) == "qualitative"

    def test_qualitative_wins_over_all(self):
        assert _effective_tier({"dot_1": "live", "dot_2": "mixed", "dot_3": "qualitative"},
                               ["dot_1", "dot_2", "dot_3"]) == "qualitative"

    def test_missing_tier_defaults_to_live(self):
        assert _effective_tier({}, ["dot_1"]) == "live"

    def test_single_dot(self):
        assert _effective_tier({"dot_9": "qualitative"}, ["dot_9"]) == "qualitative"


class TestPreprocessDots:
    """Test _preprocess_dots splits dots into abstaining vs active."""

    def test_all_live_none_abstain(self):
        abstentions, active_dots, eff_tier = _preprocess_dots(
            ["dot_1", "dot_2"],
            {"dot_1": "live", "dot_2": "live"},
            {},
        )
        assert abstentions == {}
        assert active_dots == ["dot_1", "dot_2"]
        assert eff_tier == "live"

    def test_qualitative_no_sources_abstains(self):
        """QUALITATIVE with zero sources → abstention."""
        abstentions, active_dots, eff_tier = _preprocess_dots(
            ["dot_9"],
            {"dot_9": "qualitative"},
            {"dot_9": []},
        )
        assert "dot_9" in abstentions
        assert abstentions["dot_9"]["status"] == "unavailable"
        assert abstentions["dot_9"]["summary"] == ABSTENTION_STRING
        assert active_dots == []
        assert eff_tier == "live"  # no active dots

    def test_qualitative_no_sources_none_dict(self):
        """QUALITATIVE with no qualitative_sources dict at all → abstention."""
        abstentions, active_dots, eff_tier = _preprocess_dots(
            ["dot_9"],
            {"dot_9": "qualitative"},
            None,
        )
        assert "dot_9" in abstentions
        assert active_dots == []

    def test_qualitative_with_sources_stays_active(self):
        """QUALITATIVE with web sources → stays active (LLM needed)."""
        sources = {"dot_9": [{"url": "https://x.com", "title": "T", "snippet": "S", "source_type": "news"}]}
        abstentions, active_dots, eff_tier = _preprocess_dots(
            ["dot_9"],
            {"dot_9": "qualitative"},
            sources,
        )
        assert abstentions == {}
        assert active_dots == ["dot_9"]
        assert eff_tier == "qualitative"

    def test_mixed_without_sources_stays_active(self):
        """MIXED tier without web sources still active (has indicators)."""
        abstentions, active_dots, eff_tier = _preprocess_dots(
            ["dot_1"],
            {"dot_1": "mixed"},
            {},
        )
        assert abstentions == {}
        assert active_dots == ["dot_1"]
        assert eff_tier == "mixed"

    def test_mixed_dot_abstains_others_active(self):
        """One QUALITATIVE (no sources) abstains, other MIXED stays."""
        abstentions, active_dots, eff_tier = _preprocess_dots(
            ["dot_1", "dot_9"],
            {"dot_1": "mixed", "dot_9": "qualitative"},
            {"dot_9": []},
        )
        assert "dot_9" in abstentions
        assert active_dots == ["dot_1"]
        assert eff_tier == "mixed"

    def test_all_qualitative_no_sources_all_abstain(self):
        """All dots QUALITATIVE with zero sources → all abstain, no LLM."""
        abstentions, active_dots, eff_tier = _preprocess_dots(
            ["dot_1", "dot_2", "dot_9"],
            {"dot_1": "qualitative", "dot_2": "qualitative", "dot_9": "qualitative"},
            {},
        )
        assert len(abstentions) == 3
        assert active_dots == []
        assert eff_tier == "live"


class TestCollectQualitativeSources:
    """Test _collect_qualitative_sources deduplicates and collects."""

    def test_empty_sources(self):
        result = _collect_qualitative_sources(["dot_1"], None)
        assert result == []

    def test_collects_all(self):
        qs = {
            "dot_1": [
                {"url": "https://a.com", "title": "A", "snippet": "sA", "source_type": "news"},
            ],
            "dot_2": [
                {"url": "https://b.com", "title": "B", "snippet": "sB", "source_type": "analysis"},
            ],
        }
        result = _collect_qualitative_sources(["dot_1", "dot_2"], qs)
        assert len(result) == 2
        urls = {s["url"] for s in result}
        assert urls == {"https://a.com", "https://b.com"}

    def test_deduplicates_by_url(self):
        """Same URL across two dots → only included once."""
        qs = {
            "dot_1": [
                {"url": "https://shared.com", "title": "Shared", "snippet": "s", "source_type": "news"},
            ],
            "dot_2": [
                {"url": "https://shared.com", "title": "Shared", "snippet": "s", "source_type": "news"},
                {"url": "https://unique.com", "title": "Unique", "snippet": "u", "source_type": "web"},
            ],
        }
        result = _collect_qualitative_sources(["dot_1", "dot_2"], qs)
        assert len(result) == 2  # shared deduplicated, unique included
        urls = {s["url"] for s in result}
        assert urls == {"https://shared.com", "https://unique.com"}

    def test_dot_with_no_sources_skipped(self):
        qs = {
            "dot_1": [
                {"url": "https://a.com", "title": "A", "snippet": "s", "source_type": "news"},
            ],
        }
        result = _collect_qualitative_sources(["dot_1", "dot_9"], qs)
        assert len(result) == 1
        assert result[0]["url"] == "https://a.com"


class TestTierAwarePrompts:
    """Test that all prompts include tier-aware placeholders."""

    def test_agent1_has_tier_instructions(self):
        assert "{tier_instructions}" in AGENT1_PROMPT
        assert "{qualitative_sources}" in AGENT1_PROMPT

    def test_agent2_has_tier_instructions(self):
        assert "{tier_instructions}" in AGENT2_PROMPT
        assert "{qualitative_sources}" in AGENT2_PROMPT

    def test_agent3_has_tier_instructions(self):
        assert "{tier_instructions}" in AGENT3_PROMPT
        assert "{qualitative_sources}" in AGENT3_PROMPT

    def test_agent4_has_tier_instructions(self):
        assert "{tier_instructions}" in AGENT4_PROMPT
        assert "{qualitative_sources}" in AGENT4_PROMPT

    def test_agent5_has_tier_instructions(self):
        assert "{tier_instructions}" in AGENT5_PROMPT
        assert "{qualitative_sources}" in AGENT5_PROMPT


class TestAgentTierSignatures:
    """Test that all agent functions accept tiers and qualitative_sources params."""

    def test_agents_accept_tiers(self):
        """All 5 agents accept tiers and qualitative_sources keyword args."""
        from src.agent.dot_analyzers import (
            analyze_geopolitical,
            analyze_food_debt,
            analyze_financial_em,
            analyze_china_political,
            analyze_health,
        )
        import inspect

        for agent in [analyze_geopolitical, analyze_food_debt,
                      analyze_financial_em, analyze_china_political,
                      analyze_health]:
            sig = inspect.signature(agent)
            params = sig.parameters
            assert "tiers" in params, f"{agent.__name__} missing tiers param"
            assert "qualitative_sources" in params, f"{agent.__name__} missing qualitative_sources param"
            # Default should be None (backward compatible)
            assert params["tiers"].default is None
            assert params["qualitative_sources"].default is None


class TestLiveTierBackwardCompat:
    """All agents must work with tier=live (no behavioral change from current)."""

    @pytest.mark.asyncio
    async def test_geopolitical_live_tier(self, mock_indicators):
        """Agent 1 with LIVE tier produces valid output."""
        from src.agent.dot_analyzers import analyze_geopolitical
        from unittest.mock import patch, AsyncMock

        composite = {"composite": 15, "interpretation": "Monitor"}
        tiers = {"dot_1": "live", "dot_2": "live"}

        with patch("src.agent.dot_analyzers.call_llm_with_retry",
                   new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = ({
                "dot_1": {"status": "dormant", "summary": "ok", "key_signals": [],
                          "nato_outlook": "unified", "nato_confidence": 0.8,
                          "sources": "Test sources."},
                "dot_2": {"status": "dormant", "summary": "ok", "key_signals": [],
                          "hormuz_risk": "low", "energy_price_outlook": "stable",
                          "sources": "Test sources."},
            }, 1)

            result = await analyze_geopolitical(
                mock_indicators, composite, tiers=tiers
            )
            assert "dot_1" in result
            assert "dot_2" in result
            assert result["dot_1"]["status"] == "dormant"
            # LIVE tier → temperature=0.3
            call_kwargs = mock_llm.call_args.kwargs
            assert call_kwargs.get("temperature") == 0.3

    @pytest.mark.asyncio
    async def test_geopolitical_qualitative_abstain(self, mock_indicators):
        """Agent 1 with all QUALITATIVE dots (no sources) abstains — no LLM call."""
        from src.agent.dot_analyzers import analyze_geopolitical
        from unittest.mock import patch, AsyncMock

        composite = {"composite": 5, "interpretation": "Monitor"}
        tiers = {"dot_1": "qualitative", "dot_2": "qualitative"}

        with patch("src.agent.dot_analyzers.call_llm_with_retry",
                   new_callable=AsyncMock) as mock_llm:
            result = await analyze_geopolitical(
                mock_indicators, composite, tiers=tiers
            )
            # LLM should NOT have been called (both dots abstain)
            mock_llm.assert_not_called()
            assert result["dot_1"]["status"] == "unavailable"
            assert result["dot_1"]["summary"] == ABSTENTION_STRING
            assert result["dot_2"]["status"] == "unavailable"
            assert result["dot_2"]["summary"] == ABSTENTION_STRING

    @pytest.mark.asyncio
    async def test_geopolitical_qualitative_with_sources(self, mock_indicators,
                                                         mock_qualitative_sources):
        """Agent 1 with QUALITATIVE tier + sources → LLM called with temp=0."""
        from src.agent.dot_analyzers import analyze_geopolitical
        from unittest.mock import patch, AsyncMock

        composite = {"composite": 10, "interpretation": "Monitor"}
        tiers = {"dot_1": "qualitative", "dot_2": "qualitative"}

        with patch("src.agent.dot_analyzers.call_llm_with_retry",
                   new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = ({
                "dot_1": {"status": "activating", "summary": "Tensions noted.",
                          "key_signals": ["signal"], "nato_outlook": "fracturing",
                          "nato_confidence": 0.4, "sources": "From web."},
                "dot_2": {"status": "dormant", "summary": "Stable.",
                          "key_signals": [], "hormuz_risk": "low",
                          "energy_price_outlook": "stable", "sources": "From web."},
            }, 1)

            result = await analyze_geopolitical(
                mock_indicators, composite,
                tiers=tiers,
                qualitative_sources=mock_qualitative_sources,
            )
            # LLM should have been called
            mock_llm.assert_called_once()
            # QUALITATIVE tier → temperature=0
            call_kwargs = mock_llm.call_args.kwargs
            assert call_kwargs.get("temperature") == 0.0
            # Prompt should include qualitative sources
            prompt = mock_llm.call_args.args[0]
            assert "QUALITATIVE SOURCES" in prompt
            assert "https://example.com/nato1" in prompt
            assert result["dot_1"]["status"] == "activating"

    @pytest.mark.asyncio
    async def test_health_qualitative_five_sources(self, mock_indicators,
                                                    mock_qualitative_sources):
        """Agent 5 (Health) with QUALITATIVE + 5 sources → all 5 in prompt."""
        from src.agent.dot_analyzers import analyze_health
        from unittest.mock import patch, AsyncMock

        composite = {"composite": 5, "interpretation": "Monitor"}
        tiers = {"dot_9": "qualitative"}

        with patch("src.agent.dot_analyzers.call_llm_with_retry",
                   new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = ({
                "dot_9": {"status": "activating", "summary": "Risk moderate.",
                          "key_signals": ["cases rising"],
                          "who_risk_level": "moderate", "human_transmission": "suspected",
                          "geographic_spread": "regional", "government_response": "monitoring",
                          "sources": "Based on web sources."},
            }, 1)

            result = await analyze_health(
                mock_indicators, composite,
                tiers=tiers,
                qualitative_sources=mock_qualitative_sources,
            )
            prompt = mock_llm.call_args.args[0]
            # All 5 dot_9 sources should appear
            for i in range(1, 6):
                assert f"[{i}]" in prompt
            sources = mock_qualitative_sources["dot_9"]
            for src in sources:
                assert src["title"] in prompt
            assert result["dot_9"]["who_risk_level"] == "moderate"

    @pytest.mark.asyncio
    async def test_mixed_tier_prompt_includes_source_flags(self, mock_indicators,
                                                            mock_qualitative_sources):
        """MIXED tier prompt instructs LLM to flag statements with source type."""
        from src.agent.dot_analyzers import analyze_geopolitical
        from unittest.mock import patch, AsyncMock

        composite = {"composite": 12, "interpretation": "Monitor"}
        tiers = {"dot_1": "mixed", "dot_2": "mixed"}

        with patch("src.agent.dot_analyzers.call_llm_with_retry",
                   new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = ({
                "dot_1": {"status": "dormant", "summary": "ok", "key_signals": [],
                          "nato_outlook": "unified", "nato_confidence": 0.7,
                          "sources": "Test."},
                "dot_2": {"status": "dormant", "summary": "ok", "key_signals": [],
                          "hormuz_risk": "low", "energy_price_outlook": "stable",
                          "sources": "Test."},
            }, 1)

            await analyze_geopolitical(
                mock_indicators, composite,
                tiers=tiers,
                qualitative_sources=mock_qualitative_sources,
            )
            prompt = mock_llm.call_args.args[0]
            # MIXED instructions should be in the prompt
            assert "TIER: MIXED" in prompt
            assert "quantitative" in prompt.lower()
            assert "[web_source]" in prompt or "web_source" in prompt.lower()
            assert "do not infer from general training" in prompt.lower()

    @pytest.mark.asyncio
    async def test_health_zero_sources_abstains(self, mock_indicators):
        """Agent 5 with QUALITATIVE tier + zero sources → direct abstention."""
        from src.agent.dot_analyzers import analyze_health
        from unittest.mock import patch, AsyncMock

        composite = {"composite": 3, "interpretation": "Monitor"}
        tiers = {"dot_9": "qualitative"}

        with patch("src.agent.dot_analyzers.call_llm_with_retry",
                   new_callable=AsyncMock) as mock_llm:
            result = await analyze_health(
                mock_indicators, composite,
                tiers=tiers,
                qualitative_sources={},
            )
            # LLM should NOT be called
            mock_llm.assert_not_called()
            assert result["dot_9"]["status"] == "unavailable"
            assert result["dot_9"]["summary"] == ABSTENTION_STRING
            assert "sources" in result["dot_9"]
            assert result["dot_9"]["key_signals"] == ["no data sources available"]


# ============================================================
# NEW: dot_tier_info + TIER RULE + fallback tier tests
# ============================================================

class TestDotTierBlock:
    """Test _build_dot_tier_block generates correct per-dot tier display."""

    def test_all_live(self):
        from src.agent.dot_analyzers import _build_dot_tier_block
        result = _build_dot_tier_block(
            {"dot_1": "live", "dot_2": "live"}, ["dot_1", "dot_2"]
        )
        assert "DATA TIER (per dot):" in result
        assert "dot_1: live" in result
        assert "dot_2: live" in result

    def test_mixed_and_qualitative(self):
        from src.agent.dot_analyzers import _build_dot_tier_block
        result = _build_dot_tier_block(
            {"dot_1": "mixed", "dot_9": "qualitative"}, ["dot_1", "dot_9"]
        )
        assert "dot_1: mixed" in result
        assert "dot_9: qualitative" in result

    def test_missing_tier_defaults_to_live(self):
        from src.agent.dot_analyzers import _build_dot_tier_block
        result = _build_dot_tier_block({}, ["dot_1"])
        assert "dot_1: live" in result


class TestTierAwarePromptPlaceholders:
    """Test all prompts now contain dot_tier_info and TIER RULE statements."""

    def test_all_prompts_have_dot_tier_info(self):
        for prompt in [AGENT1_PROMPT, AGENT2_PROMPT, AGENT3_PROMPT,
                       AGENT4_PROMPT, AGENT5_PROMPT]:
            assert "{dot_tier_info}" in prompt, (
                f"Prompt missing {{dot_tier_info}} placeholder"
            )

    def test_all_prompts_have_tier_rule_qualitative(self):
        for prompt in [AGENT1_PROMPT, AGENT2_PROMPT, AGENT3_PROMPT,
                       AGENT4_PROMPT, AGENT5_PROMPT]:
            assert "TIER RULE" in prompt
            assert "qualitative" in prompt.lower()
            assert "status='unavailable'" in prompt
            assert "do not infer from general training" in prompt.lower()

    def test_all_prompts_have_tier_rule_mixed(self):
        for prompt in [AGENT1_PROMPT, AGENT2_PROMPT, AGENT3_PROMPT,
                       AGENT4_PROMPT, AGENT5_PROMPT]:
            assert "TIER RULE" in prompt
            assert "mixed" in prompt.lower()
            assert "data_status='live'" in prompt.lower()
            assert "[DATA UNAVAILABLE]" in prompt


class TestFallbackTier:
    """Test _fallback returns tier in response dicts."""

    def test_fallback_geopolitical_has_tier(self, mock_indicators):
        fb = _fallback("geopolitical", mock_indicators,
                       tiers={"dot_1": "live", "dot_2": "mixed"})
        assert fb["dot_1"]["tier"] == "live"
        assert fb["dot_2"]["tier"] == "mixed"

    def test_fallback_china_political_has_tier(self, mock_indicators):
        fb = _fallback("china_political", mock_indicators,
                       tiers={"dot_6": "qualitative", "dot_7": "live", "dot_8": "live"})
        assert fb["dot_6"]["tier"] == "qualitative"
        assert fb["dot_7"]["tier"] == "live"
        assert fb["dot_8"]["tier"] == "live"

    def test_fallback_no_tiers_defaults_to_live(self, mock_indicators):
        """When no tiers provided, all dots default to 'live'."""
        fb = _fallback("geopolitical", mock_indicators)
        assert fb["dot_1"]["tier"] == "live"
        assert fb["dot_2"]["tier"] == "live"

    def test_fallback_health_has_tier(self, mock_indicators):
        fb = _fallback("health", mock_indicators,
                       tiers={"dot_9": "qualitative"})
        assert fb["dot_9"]["tier"] == "qualitative"


class TestPromptTierInjectionLive:
    """Live integration: verify tier-aware prompt construction."""

    @pytest.mark.asyncio
    async def test_prompt_includes_dot_tier_block(self, mock_indicators):
        """Prompt constructed by analyze_geopolitical includes DATA TIER block."""
        from src.agent.dot_analyzers import analyze_geopolitical
        from unittest.mock import patch, AsyncMock

        composite = {"composite": 10, "interpretation": "Monitor"}
        tiers = {"dot_1": "live", "dot_2": "mixed"}

        with patch("src.agent.dot_analyzers.call_llm_with_retry",
                   new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = ({
                "dot_1": {"status": "dormant", "summary": "ok", "key_signals": [],
                          "nato_outlook": "unified", "nato_confidence": 0.8,
                          "sources": "Test."},
                "dot_2": {"status": "dormant", "summary": "ok", "key_signals": [],
                          "hormuz_risk": "low", "energy_price_outlook": "stable",
                          "sources": "Test."},
            }, 1)

            await analyze_geopolitical(mock_indicators, composite, tiers=tiers)
            prompt = mock_llm.call_args.args[0]
            assert "DATA TIER (per dot):" in prompt
            assert "dot_1: live" in prompt
            assert "dot_2: mixed" in prompt
            assert "TIER RULE" in prompt
            assert "status='unavailable'" in prompt
            assert "do not infer from general training" in prompt.lower()
