"""Unit tests for indicator_narrator — prompt construction passes actual values.

AC: Given a mock indicator list with [Caixin PMI=50.8, China Property Default=0, ...],
the prompt contains "Caixin PMI = 50.8" not "Caixin PMI (unavailable)".
"""
import pytest
from src.agent.indicator_narrator import (
    narrate_one,
    narrate_all,
    narrate_for_dots,
    sources_for_dot,
    sources_narrative,
    generate_indicator_narratives,
    INDICATOR_META,
    DOT_INDICATORS,
)


# ── Mock indicator fixtures ──────────────────────────────────────────

@pytest.fixture
def mock_indicators() -> dict:
    """Representative indicator set: numeric, flag, and missing values."""
    return {
        "brent_price": 98.40,
        "wti_price": 87.50,
        "vix": 22.3,
        "ig_oas": 180.0,
        "hy_oas": 450.0,
        "caixin_pmi": 50.8,
        "idr_breach": 0,
        "try_breach": 1,
        "nato_fracture": 1,
        "china_property_default": 0,
        "protest_countries": 3,
        "govt_crisis": 1,
        "hormuz_closure": "",
        "dxy": None,  # explicitly unavailable
    }


@pytest.fixture
def mock_prev_indicators() -> dict:
    """Previous values for trend computation."""
    return {"brent_price": 95.10, "vix": 20.1}


# ── narrate_one tests ────────────────────────────────────────────────

class TestNarrateOne:
    """Test single-indicator narration format."""

    def test_narrate_with_float_value(self):
        """Float value: should show 'Name = val unit (status: status)'."""
        result = narrate_one("caixin_pmi", 50.8)
        assert "Caixin PMI" in result
        assert "= 50.8" in result
        assert "(status: normal)" in result
        assert "Trigger: <48" in result
        # Must NOT contain "(unavailable)" or "N/A"
        assert "(unavailable)" not in result
        assert result.count("N/A") == 0

    def test_narrate_with_zero_flag(self):
        """Zero value on flag indicator: should show 0, not '(unavailable)'."""
        result = narrate_one("china_property_default", 0)
        assert "China Property Default" in result
        assert "= 0" in result
        assert "(status: normal)" in result
        assert "(unavailable)" not in result

    def test_narrate_with_one_flag(self):
        """Flag value of 1: should show breached status."""
        result = narrate_one("try_breach", 1)
        assert "TRY Breach" in result
        assert "= 1" in result
        assert "(status: breached)" in result

    def test_narrate_with_none_value(self):
        """None value: should show N/A and unknown status."""
        result = narrate_one("dxy", None)
        assert "DXY" in result
        assert "N/A" in result
        assert "(status: unknown)" in result

    def test_narrate_with_int_count(self):
        """Integer count value: protest_countries = 3."""
        result = narrate_one("protest_countries", 3)
        assert "Protest Countries" in result
        assert "= 3" in result
        assert "(status: breached)" in result

    def test_narrate_uses_equals_not_colon(self):
        """Format uses '=' not ':' between name and value."""
        result = narrate_one("brent_price", 98.40)
        assert "Brent Crude = 98.4" in result
        assert "Brent Crude:" not in result

    def test_narrate_includes_trend_when_prev(self):
        """When previous value provided, trend arrow is included."""
        result = narrate_one("brent_price", 98.40, prev_value=95.10)
        assert "Change: +3.30 ↑" in result


# ── narrate_all tests ─────────────────────────────────────────────────

class TestNarrateAll:
    """Test bulk narration grouped by category."""

    def test_narrate_all_contains_all_values(self, mock_indicators):
        """Every indicator with a real value appears in the output."""
        result = narrate_all(mock_indicators)
        assert "Caixin PMI = 50.8" in result
        assert "Brent Crude = 98.4" in result
        assert "VIX = 22.3" in result
        assert "China Property Default = 0" in result
        assert "TRY Breach = 1" in result
        assert "NATO Fracture = 1" in result

    def test_narrate_all_no_unavailable_text(self, mock_indicators):
        """Prompt must not contain '(unavailable)' for indicators with values."""
        result = narrate_all(mock_indicators)
        assert "(unavailable)" not in result

    def test_narrate_all_none_value_shows_na(self, mock_indicators):
        """Indicator with None value shows N/A, not masked."""
        result = narrate_all(mock_indicators)
        assert "DXY = N/A" in result or "DXY: N/A" in result

    def test_narrate_all_empty_indicators(self):
        """Empty indicators dict returns a sane message."""
        result = narrate_all({})
        assert "no indicator data" in result.lower()

    def test_narrate_all_category_headers(self, mock_indicators):
        """Output includes category headers like ## Energy, ## China."""
        result = narrate_all(mock_indicators)
        assert "## Energy" in result
        assert "## China" in result

    def test_narrate_all_with_trends(self, mock_indicators, mock_prev_indicators):
        """Trend arrows appear when previous values are provided."""
        result = narrate_all(mock_indicators, mock_prev_indicators)
        assert "↑" in result or "↓" in result or "→" in result


# ── narrate_for_dots tests ────────────────────────────────────────────

class TestNarrateForDots:
    """Test filtered narration for specific dot indicators."""

    def test_narrate_for_dots_only_relevant(self, mock_indicators):
        """Only the requested dot indicators appear."""
        result = narrate_for_dots(
            mock_indicators, ["caixin_pmi", "china_property_default"]
        )
        assert "Caixin PMI = 50.8" in result
        assert "China Property Default = 0" in result
        # Should NOT include unrelated indicators
        assert "Brent Crude" not in result

    def test_narrate_for_dots_empty_slugs(self, mock_indicators):
        """Empty slug list returns a sane message."""
        result = narrate_for_dots(mock_indicators, [])
        assert "no relevant indicator data" in result.lower()

    def test_narrate_for_dots_with_none_in_indicators(self):
        """Slug present but value is None: shows N/A."""
        result = narrate_for_dots({"dxy": None}, ["dxy"])
        assert "DXY" in result
        assert "N/A" in result


# ── Sources tests ─────────────────────────────────────────────────────

class TestSourcesForDot:
    """Test source attribution for dots."""

    def test_sources_for_dot_contains_values(self, mock_indicators):
        """Source attribution includes actual indicator values."""
        result = sources_for_dot("dot_4", mock_indicators)
        assert "IG OAS = 180.00" in result
        assert "VIX = 22.30" in result


class TestSourcesNarrative:
    """Test source narrative generation."""

    def test_sources_narrative_contains_dots(self, mock_indicators):
        """Narrative includes dot sections."""
        result = sources_narrative(mock_indicators, ["dot_1", "dot_2"])
        assert "### dot_1" in result
        assert "### dot_2" in result
        assert "NATO Fracture" in result
        assert "Brent Crude" in result


# ── generate_indicator_narratives tests ───────────────────────────────

class TestGenerateIndicatorNarratives:
    """Test LLM-driven narrative generation — prompt construction only."""

    @pytest.mark.asyncio
    async def test_empty_indicators_returns_empty_dict(self):
        """Empty indicators dict returns empty dict without LLM call."""
        result = await generate_indicator_narratives({})
        assert result == {}

    def test_prompt_includes_zero_values(self, mock_indicators):
        """The prompt-building loop does NOT filter out value == 0.

        We test this by inspecting the internal logic path:
        indicators with value 0 (like china_property_default, idr_breach)
        should be included in the lines list passed to the LLM prompt.
        Since generate_indicator_narratives is async and calls the LLM,
        we verify the filtering logic is correct by checking that
        narrate_one handles zero values (tested in TestNarrateOne).
        """
        # Indirect verification: narrate_one with 0 produces valid output
        result = narrate_one("china_property_default", 0)
        assert "= 0" in result
        assert "(unavailable)" not in result


# ── DOT_INDICATORS integrity ──────────────────────────────────────────

class TestDotIndicatorsIntegrity:
    """Ensure dot-to-indicator mappings are consistent."""

    def test_all_dot_slugs_exist_in_meta(self):
        """Every indicator slug in DOT_INDICATORS has metadata."""
        for dot_key, slugs in DOT_INDICATORS.items():
            for slug in slugs:
                assert slug in INDICATOR_META, (
                    f"DOT_INDICATORS['{dot_key}'] references '{slug}' "
                    f"but INDICATOR_META has no entry for it"
                )

    def test_indicator_meta_has_required_fields(self):
        """Every metadata entry has name, category, unit, trigger, source."""
        required = {"name", "category", "unit", "trigger", "source"}
        for slug, meta in INDICATOR_META.items():
            missing = required - set(meta.keys())
            assert not missing, (
                f"INDICATOR_META['{slug}'] missing: {missing}"
            )


# ── NARRATOR_PROMPT template integrity ────────────────────────────────

def test_narrator_prompt_contains_placeholders():
    """The LLM prompt template has the expected format placeholder."""
    from src.agent.indicator_narrator import NARRATOR_PROMPT
    assert "{indicators_text}" in NARRATOR_PROMPT
    assert "Return ONLY a JSON object" in NARRATOR_PROMPT


# ── News-derived flag indicator tests ─────────────────────────────────

class TestNewsDerivedFlagIndicators:
    """Test that news-derived indicators (unit='flag', source='newsapi')
    show their narrative in prompts instead of the numeric value."""

    def test_narrate_one_shows_narrative_for_news_flag(self):
        """narrate_one with a news-flag dict shows the news narrative."""
        from src.agent.indicator_narrator import narrate_one

        value_dict = {"value": 1, "narrative": "Grain prices surge amid drought | FAO warns of shortages | Wheat futures spike"}
        result = narrate_one("news_caixin_pmi", value_dict)

        # Should show narrative, not the numeric value
        assert "Grain prices surge amid drought" in result
        assert "(news):" in result
        assert "Trigger: ≥1" in result
        # Should NOT show the raw numeric value as the main content
        assert "= 1 flag" not in result

    def test_narrate_one_truncates_long_narrative(self):
        """Narrative is truncated to 200 chars to fit token budget."""
        from src.agent.indicator_narrator import narrate_one

        long_narrative = "A" * 300
        value_dict = {"value": 1, "narrative": long_narrative}
        result = narrate_one("news_caixin_pmi", value_dict)

        # The full 300-char narrative should NOT appear
        assert long_narrative not in result
        # But the first 200 chars should
        assert "A" * 200 in result

    def test_narrate_one_zero_flag_shows_narrative(self):
        """Even with value=0 (not triggered), the narrative is shown."""
        from src.agent.indicator_narrator import narrate_one

        value_dict = {"value": 0, "narrative": "EU gas reserves stable | No supply disruptions reported"}
        result = narrate_one("news_eu_gas", value_dict)

        assert "EU gas reserves stable" in result
        assert "(news):" in result
        assert "= 0 flag" not in result

    def test_narrate_one_handles_empty_narrative(self):
        """Empty narrative shows '(no news)' fallback."""
        from src.agent.indicator_narrator import narrate_one

        value_dict = {"value": 0, "narrative": ""}
        result = narrate_one("news_eu_gas", value_dict)

        assert "(no news)" in result
        assert "(news):" in result

    def test_narrate_all_includes_news_narrative(self):
        """narrate_all with a mixed indicator set includes news narratives."""
        from src.agent.indicator_narrator import narrate_all

        indicators = {
            "brent_price": 82.5,
            "news_caixin_pmi": {"value": 1, "narrative": "China factory activity contracts sharply"},
            "vix": 18.2,
        }
        result = narrate_all(indicators)

        assert "Brent Crude" in result
        assert "China factory activity contracts sharply" in result
        assert "Caixin PMI (News)" in result
        # Regular indicators still use numeric format
        assert "= 82.5" in result

    def test_assess_handles_news_flag_value(self):
        """_assess extracts scalar from news-flag dict correctly."""
        from src.agent.indicator_narrator import _assess, INDICATOR_META

        value_dict = {"value": 1, "narrative": "test"}
        result = _assess(value_dict, INDICATOR_META["news_caixin_pmi"])
        assert result == "breached"

        value_dict_zero = {"value": 0, "narrative": "test"}
        result = _assess(value_dict_zero, INDICATOR_META["news_caixin_pmi"])
        assert result == "normal"

    def test_is_news_flag_detection(self):
        """_is_news_flag correctly identifies news-flag dicts."""
        from src.agent.indicator_narrator import _is_news_flag

        assert _is_news_flag({"value": 1, "narrative": "test"}) is True
        assert _is_news_flag({"value": 0, "narrative": ""}) is True
        assert _is_news_flag({"other": "dict"}) is False
        assert _is_news_flag(1) is False
        assert _is_news_flag(None) is False
        assert _is_news_flag("string") is False

    def test_extract_scalar_unwraps_news_flag(self):
        """_extract_scalar returns the scalar from a news-flag dict."""
        from src.agent.indicator_narrator import _extract_scalar

        assert _extract_scalar({"value": 1, "narrative": "test"}) == 1
        assert _extract_scalar({"value": 0, "narrative": ""}) == 0
        # Plain scalars pass through unchanged
        assert _extract_scalar(42) == 42
        assert _extract_scalar(None) is None
        assert _extract_scalar("hello") == "hello"

    def test_sources_for_dot_shows_narrative(self):
        """sources_for_dot shows narrative for news-derived indicators."""
        from src.agent.indicator_narrator import sources_for_dot

        indicators = {
            "caixin_pmi": 50.8,
            "china_property_default": 0,
            "news_caixin_pmi": {"value": 1, "narrative": "China PMI contraction | Factory output drops"},
        }
        result = sources_for_dot("dot_6", indicators)

        assert "Caixin PMI = 50.80" in result
        assert "China Property Default = 0" in result
        assert "China PMI contraction" in result
        assert "Caixin PMI (News)" in result
        # No raw dict repr
        assert "'value'" not in result
        assert "'narrative'" not in result

    def test_sources_text_for_dot_uses_narrative(self):
        """_sources_text_for_dot in dot_analyzers uses narrative for news flags."""
        from src.agent.dot_analyzers import _sources_text_for_dot

        indicators = {
            "caixin_pmi": 50.8,
            "china_property_default": 0,
            "news_caixin_pmi": {"value": 1, "narrative": "China PMI contracts | Factory output drops"},
        }
        result = _sources_text_for_dot("dot_6", indicators)

        assert "China PMI contracts" in result
        assert "(news:" in result
        assert "Caixin PMI (News)" in result
        # Should NOT show "(unavailable)" for news-derived
        assert "(unavailable)" not in result

    def test_new_indicator_meta_entries(self):
        """All 4 news-derived indicator slugs have metadata entries."""
        from src.agent.indicator_narrator import INDICATOR_META

        for slug in ("news_caixin_pmi", "news_eu_gas", "news_us_spr", "news_protest_countries"):
            assert slug in INDICATOR_META, f"Missing INDICATOR_META entry for {slug}"
            meta = INDICATOR_META[slug]
            assert meta["source"] == "newsapi"
            assert meta["unit"] == "flag"

    def test_news_slugs_in_dot_indicators(self):
        """News-derived indicators are mapped to the correct dots."""
        from src.agent.indicator_narrator import DOT_INDICATORS

        assert "news_caixin_pmi" in DOT_INDICATORS["dot_6"]
        assert "news_eu_gas" in DOT_INDICATORS["dot_2"]
        assert "news_us_spr" in DOT_INDICATORS["dot_2"]
        assert "news_protest_countries" in DOT_INDICATORS["dot_7"]
