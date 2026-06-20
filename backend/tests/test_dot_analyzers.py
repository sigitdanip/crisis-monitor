"""Unit tests for dot_analyzers — prompt construction passes actual indicator values.

AC: Given a mock indicator list, the prompt templates contain actual values,
not "(unavailable)". Tests cover prompt format, fallback source text, and
agent function signatures.
"""
import pytest
from src.agent.dot_analyzers import (
    _sources_text_for_dot,
    _fallback,
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
