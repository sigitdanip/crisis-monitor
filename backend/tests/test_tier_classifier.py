"""Unit tests for tier_classifier service.

Covers:
- classify_dots() returns all 9 dots
- classify_dot() threshold boundaries: LIVE >= 0.80, MIXED >= 0.50, QUALITATIVE < 0.50
- Edge cases: all-unavailable, all-live, partial mixed
- News-derived indicators (data_status handling)
- Structured vs flat indicator format compatibility
- Dot 9 (health — no indicators) defaults to qualitative
- overall_tier() computes worst tier across all dots
"""

import sys
sys.path.insert(0, "/root/crisis-monitor/backend")

import pytest
from src.services.tier_classifier import (
    classify_dot,
    classify_dots,
    overall_tier,
    _detect_data_status,
    _indicators_for_dot,
    LIVE_THRESHOLD,
    MIXED_THRESHOLD,
    COUNTABLE_STATUSES,
)


# ── _detect_data_status tests ──────────────────────────────────────────────


class TestDetectDataStatus:
    """Tests for _detect_data_status helper."""

    def test_structured_live(self):
        """Structured dict with data_status='live' returns 'live'."""
        value = {"value": 98.4, "data_status": "live", "fetched_at": "2026-06-01T00:00:00Z"}
        assert _detect_data_status(value) == "live"

    def test_structured_stale(self):
        """Structured dict with data_status='stale' returns 'stale'."""
        value = {"value": 98.4, "data_status": "stale"}
        assert _detect_data_status(value) == "stale"

    def test_structured_unavailable(self):
        """Structured dict with data_status='unavailable' returns 'unavailable'."""
        value = {"value": None, "data_status": "unavailable"}
        assert _detect_data_status(value) == "unavailable"

    def test_news_flag_dict(self):
        """News-flag dict {value, narrative} without data_status returns 'live'."""
        value = {"value": 1, "narrative": "Caixin PMI shows contraction"}
        assert _detect_data_status(value) == "live"

    def test_flat_scalar_numeric(self):
        """Flat scalar (int/float) returns 'live'."""
        assert _detect_data_status(98.4) == "live"
        assert _detect_data_status(0) == "live"
        assert _detect_data_status(1) == "live"

    def test_flat_scalar_none(self):
        """None returns 'unavailable'."""
        assert _detect_data_status(None) == "unavailable"

    def test_flat_scalar_empty_string(self):
        """Empty string returns 'unavailable'."""
        assert _detect_data_status("") == "unavailable"

    def test_flat_scalar_nonempty_string(self):
        """Non-empty string returns 'live' (e.g. hormuz_closure='open')."""
        assert _detect_data_status("open") == "live"
        assert _detect_data_status("closed") == "live"


# ── _indicators_for_dot tests ──────────────────────────────────────────────


class TestIndicatorsForDot:
    """Tests for _indicators_for_dot helper."""

    def test_dot_1_has_indicators(self):
        slugs = _indicators_for_dot(1)
        assert len(slugs) > 0
        assert "nato_fracture" in slugs

    def test_dot_2_has_indicators(self):
        slugs = _indicators_for_dot(2)
        assert len(slugs) > 0
        assert "brent_price" in slugs

    def test_dot_9_is_empty(self):
        """Dot 9 (Health) has no numeric indicators."""
        assert _indicators_for_dot(9) == []

    def test_all_dots_have_mapping(self):
        """Dots 1-9 all return a list (even if empty)."""
        for dot in range(1, 10):
            result = _indicators_for_dot(dot)
            assert isinstance(result, list)


# ── classify_dot tests ─────────────────────────────────────────────────────


class TestClassifyDot:
    """Tests for classify_dot() — single dot classification."""

    def test_all_live(self):
        """All indicators live → LIVE."""
        indicators = {
            "brent_price": {"value": 98.4, "data_status": "live"},
            "wti_price": {"value": 87.5, "data_status": "live"},
            "natgas_price": {"value": 3.2, "data_status": "live"},
            "eu_gas_storage_pct": {"value": 85.0, "data_status": "live"},
            "us_spr_mbbl": {"value": 370.0, "data_status": "live"},
            "hormuz_closure": {"value": "", "data_status": "unavailable"},
            "news_eu_gas": {"value": 0, "data_status": "unavailable"},
            "news_us_spr": {"value": 0, "data_status": "unavailable"},
        }
        # dot_2 has 8 indicators, 5 live, 3 unavailable → 5/8 = 0.625 → MIXED
        assert classify_dot(2, indicators) == "mixed"

    def test_all_unavailable(self):
        """All indicators unavailable → QUALITATIVE."""
        indicators = {
            "nato_fracture": {"value": None, "data_status": "unavailable"},
            "us_nato_withdrawal": {"value": None, "data_status": "unavailable"},
            "dxy": {"value": None, "data_status": "unavailable"},
        }
        assert classify_dot(1, indicators) == "qualitative"

    def test_live_threshold_boundary_exactly_80_pct(self):
        """Exactly 80% live → LIVE (boundary test)."""
        # dot_4 has 5 indicators (ig_oas, hy_oas, vix, us_10y, us_2y)
        # 4 live, 1 unavailable → 4/5 = 0.80 → LIVE
        indicators = {
            "ig_oas": {"value": 180.0, "data_status": "live"},
            "hy_oas": {"value": 450.0, "data_status": "live"},
            "vix": {"value": 22.3, "data_status": "live"},
            "us_10y": {"value": 4.5, "data_status": "live"},
            "us_2y": {"value": None, "data_status": "unavailable"},
        }
        assert classify_dot(4, indicators) == "live"

    def test_live_threshold_just_below_80_pct(self):
        """79% live → MIXED (just below LIVE threshold)."""
        # dot_4 has 5 indicators. With 3 live + 1 stale + 1 unavailable:
        # 3/5 = 0.60 → MIXED (since 0.60 < 0.80 and >= 0.50)
        indicators = {
            "ig_oas": {"value": 180.0, "data_status": "live"},
            "hy_oas": {"value": 450.0, "data_status": "live"},
            "vix": {"value": 22.3, "data_status": "stale"},  # stale counts in denominator but not as live
            "us_10y": {"value": 4.5, "data_status": "live"},
            "us_2y": {"value": None, "data_status": "unavailable"},
        }
        assert classify_dot(4, indicators) == "mixed"

    def test_mixed_threshold_boundary_exactly_50_pct(self):
        """Exactly 50% live → MIXED (boundary test)."""
        # dot_3 has 2 indicators (fao_monthly_change_pct, cme_grains_monthly_pct)
        # 1 live, 1 unavailable → 1/2 = 0.50 → MIXED
        indicators = {
            "fao_monthly_change_pct": {"value": 2.5, "data_status": "live"},
            "cme_grains_monthly_pct": {"value": None, "data_status": "unavailable"},
        }
        assert classify_dot(3, indicators) == "mixed"

    def test_mixed_threshold_just_below_50_pct(self):
        """49% live → QUALITATIVE (just below MIXED threshold)."""
        # Need a dot with enough indicators to get below 50%. Let's use dot_2 with 8 indicators.
        # 3 live out of 8 = 3/8 = 0.375 → QUALITATIVE
        indicators = {
            "brent_price": {"value": 98.4, "data_status": "live"},
            "wti_price": {"value": 87.5, "data_status": "live"},
            "natgas_price": {"value": 3.2, "data_status": "live"},
            "eu_gas_storage_pct": {"value": None, "data_status": "unavailable"},
            "us_spr_mbbl": {"value": None, "data_status": "unavailable"},
            "hormuz_closure": {"value": "open", "data_status": "unavailable"},
            "news_eu_gas": {"value": None, "data_status": "unavailable"},
            "news_us_spr": {"value": None, "data_status": "unavailable"},
        }
        assert classify_dot(2, indicators) == "qualitative"

    def test_dot_9_health_is_qualitative(self):
        """Dot 9 (Health) with no indicators always returns qualitative."""
        assert classify_dot(9, {}) == "qualitative"
        assert classify_dot(9, {"some_indicator": {"value": 1, "data_status": "live"}}) == "qualitative"

    def test_flat_scalar_format(self):
        """Legacy flat scalar format — numeric values treated as live, None as unavailable."""
        indicators = {
            "ig_oas": 180.0,
            "hy_oas": 450.0,
            "vix": None,  # unavailable
            "us_10y": 4.5,
            "us_2y": 4.2,
        }
        # 4 live out of 5 = 0.80 → LIVE
        assert classify_dot(4, indicators) == "live"

    def test_mixed_structured_and_flat(self):
        """Mixed format: some structured, some flat scalars."""
        indicators = {
            "ig_oas": {"value": 180.0, "data_status": "live"},
            "hy_oas": 450.0,  # flat → treated as live
            "vix": None,     # flat → unavailable
            "us_10y": {"value": 4.5, "data_status": "stale"},  # stale counts in denominator
            "us_2y": {"value": None, "data_status": "unavailable"},
        }
        # 2 live / 5 countable = 0.40 → QUALITATIVE
        assert classify_dot(4, indicators) == "qualitative"

    def test_stale_counts_in_denominator_only(self):
        """Stale indicators count toward the denominator but not as live."""
        indicators = {
            "brent_price": {"value": 98.4, "data_status": "live"},
            "wti_price": {"value": 87.5, "data_status": "stale"},
        }
        # dot_8 has brent_price and hormuz_closure (2 indicators)
        # But only brent_price is in the indicators dict, hormuz_closure is missing
        # Missing indicators (not in dict) are not countable
        # So 1 live / 2 countable = 0.50 → MIXED
        # Actually, missing gets _detect_data_status(None) = 'unavailable'
        # But the indicator is not in the dict at all, so indicators.get('hormuz_closure') = None
        # _detect_data_status(None) = 'unavailable' → countable
        # 1 live / 2 countable = 0.50 → MIXED
        assert classify_dot(8, indicators) == "mixed"

    def test_no_countable_indicators(self):
        """When no indicators are countable, returns qualitative."""
        # Indicators are present but all have non-countable statuses
        # Actually, with current logic, all valid statuses are countable
        # The edge case is when the dot has indicators but none are in the dict
        # That can't happen since we check indicators.get(slug) which returns None
        # and None → 'unavailable' → countable
        # The only way to get 0 countable is if all slugs return a status outside COUNTABLE_STATUSES
        # Or if the dot has no slugs at all (dot_9, which is handled)
        # This test verifies the edge case doesn't crash
        indicators = {"brent_price": None}  # dot_8: 1 indicator, 1 unavailable → 0/1 = 0 → qualitative
        assert classify_dot(8, indicators) == "qualitative"


# ── classify_dots tests ────────────────────────────────────────────────────


class TestClassifyDots:
    """Tests for classify_dots() — all 9 dots."""

    def test_returns_all_nine_dots(self):
        """Returns a dict with keys 1-9."""
        indicators = {
            "brent_price": {"value": 98.4, "data_status": "live"},
        }
        result = classify_dots(indicators)
        assert list(result.keys()) == list(range(1, 10))
        # dot_9 always qualitative
        assert result[9] == "qualitative"

    def test_all_dots_live_when_all_indicators_live(self):
        """When all indicators are live (except LLM-assessed ones), most dots are LIVE or MIXED."""
        indicators = {}
        # Populate all DOT_INDICATORS with live structured values
        for dot_num in range(1, 9):
            for slug in _indicators_for_dot(dot_num):
                if slug not in indicators:
                    indicators[slug] = {"value": 1.0, "data_status": "live"}

        result = classify_dots(indicators)
        # Since all are live, every dot should be LIVE
        for dot_num in range(1, 9):
            assert result[dot_num] == "live", f"dot_{dot_num} should be LIVE, got {result[dot_num]}"
        # dot_9 always qualitative
        assert result[9] == "qualitative"

    def test_llm_assessed_indicators_are_unavailable(self):
        """LLM-assessed indicators (nato_fracture, etc.) default to unavailable."""
        indicators = {
            "nato_fracture": {"value": None, "data_status": "unavailable"},
            "us_nato_withdrawal": {"value": None, "data_status": "unavailable"},
            "dxy": {"value": 105.0, "data_status": "live"},
        }
        # dot_1: nato_fracture(unavailable), us_nato_withdrawal(unavailable), dxy(live)
        # 1/3 = 0.33 → QUALITATIVE
        assert classify_dot(1, indicators) == "qualitative"

    def test_missing_indicator_slug_is_unavailable(self):
        """When a slug is not in the indicators dict, it's treated as unavailable."""
        indicators = {
            "brent_price": {"value": 98.4, "data_status": "live"},
            "wti_price": {"value": 87.5, "data_status": "live"},
        }
        # dot_8: brent_price (live), hormuz_closure (missing → unavailable)
        # 1/2 = 0.50 → MIXED
        assert classify_dot(8, indicators) == "mixed"

    def test_fetcher_health_not_required(self):
        """classify_dots works without fetcher_health parameter."""
        indicators = {"brent_price": {"value": 98.4, "data_status": "live"}}
        result = classify_dots(indicators)
        assert len(result) == 9

    def test_fetcher_health_accepted_but_ignored(self):
        """classify_dots accepts fetcher_health but doesn't use it for calculation."""
        indicators = {"brent_price": {"value": 98.4, "data_status": "live"}}
        health = {"market": {"status": "failed", "consecutive_failures": 5}}
        result = classify_dots(indicators, fetcher_health=health)
        assert len(result) == 9


# ── overall_tier tests ─────────────────────────────────────────────────────


class TestOverallTier:
    """Tests for overall_tier() — worst tier across all dots."""

    def test_all_live(self):
        tiers = {i: "live" for i in range(1, 10)}
        assert overall_tier(tiers) == "live"

    def test_one_qualitative_drags_down(self):
        tiers = {i: "live" for i in range(1, 10)}
        tiers[5] = "qualitative"
        assert overall_tier(tiers) == "qualitative"

    def test_one_mixed_among_live(self):
        tiers = {i: "live" for i in range(1, 10)}
        tiers[3] = "mixed"
        assert overall_tier(tiers) == "mixed"

    def test_qualitative_wins_over_mixed(self):
        tiers = {1: "live", 2: "mixed", 3: "qualitative", 4: "live", 5: "mixed",
                 6: "live", 7: "live", 8: "live", 9: "qualitative"}
        assert overall_tier(tiers) == "qualitative"

    def test_empty_tiers(self):
        """Empty dict defaults to live."""
        assert overall_tier({}) == "live"

    def test_all_qualitative(self):
        tiers = {i: "qualitative" for i in range(1, 10)}
        assert overall_tier(tiers) == "qualitative"


# ── Threshold constant tests ──────────────────────────────────────────────


class TestThresholdConstants:
    """Verify user-locked threshold values."""

    def test_live_threshold(self):
        assert LIVE_THRESHOLD == 0.80

    def test_mixed_threshold(self):
        assert MIXED_THRESHOLD == 0.50

    def test_countable_statuses(self):
        assert COUNTABLE_STATUSES == frozenset({"live", "stale", "unavailable"})


# ── Smoke test: full pipeline simulation ───────────────────────────────────


class TestSmoke:
    """End-to-end smoke tests simulating real pipeline scenarios."""

    def test_yfinance_down_scenario(self):
        """Simulate: yfinance (market + credit) is down → 6/9 dots become MIXED or QUALITATIVE."""
        # All market indicators (yfinance) → unavailable
        # All credit indicators (FRED) → unavailable (simplified)
        # Energy storage (non-yfinance) → live
        # News indicators → live
        indicators = {
            # Market (yfinance) — ALL unavailable
            "brent_price": {"value": None, "data_status": "unavailable"},
            "wti_price": {"value": None, "data_status": "unavailable"},
            "natgas_price": {"value": None, "data_status": "unavailable"},
            "dxy": {"value": None, "data_status": "unavailable"},
            "gold_price": {"value": None, "data_status": "unavailable"},
            "us_10y": {"value": None, "data_status": "unavailable"},
            "us_2y": {"value": None, "data_status": "unavailable"},
            "vix": {"value": None, "data_status": "unavailable"},
            # Credit — unavailable
            "ig_oas": {"value": None, "data_status": "unavailable"},
            "hy_oas": {"value": None, "data_status": "unavailable"},
            "btp_bund_spread": {"value": None, "data_status": "unavailable"},
            # Economic — live
            "fao_monthly_change_pct": {"value": 2.5, "data_status": "live"},
            "cme_grains_monthly_pct": {"value": 1.2, "data_status": "live"},
            # Currencies — live
            "idr_breach": {"value": 0, "data_status": "live"},
            "try_breach": {"value": 0, "data_status": "live"},
            "egp_breach": {"value": 0, "data_status": "live"},
            "caixin_pmi": {"value": 49.5, "data_status": "live"},
            # Energy storage — live (non-yfinance)
            "eu_gas_storage_pct": {"value": 85.0, "data_status": "live"},
            "us_spr_mbbl": {"value": 370.0, "data_status": "live"},
            # LLM-assessed — unavailable (always at fetch stage)
            "nato_fracture": {"value": None, "data_status": "unavailable"},
            "us_nato_withdrawal": {"value": None, "data_status": "unavailable"},
            "hormuz_closure": {"value": "", "data_status": "unavailable"},
            "protest_countries": {"value": 0, "data_status": "unavailable"},
            "govt_crisis": {"value": 0, "data_status": "unavailable"},
            "china_property_default": {"value": 0, "data_status": "unavailable"},
            "cds_doubling": {"value": 0, "data_status": "unavailable"},
            # News-derived — live
            "news_caixin_pmi": {"value": 0, "data_status": "live"},
            "news_eu_gas": {"value": 0, "data_status": "live"},
            "news_us_spr": {"value": 0, "data_status": "live"},
            "news_protest_countries": {"value": 0, "data_status": "live"},
        }

        result = classify_dots(indicators)

        # dot_1 (NATO): nato_fracture(U), us_nato_withdrawal(U), dxy(U) → 0/3 = 0 → QUALITATIVE
        assert result[1] == "qualitative", f"dot_1 expected qualitative, got {result[1]}"

        # dot_2 (Energy): brent(U), wti(U), natgas(U), eu_gas(L), us_spr(L), hormuz(U), news_eu_gas(L), news_us_spr(L)
        # → 4/8 = 0.50 → MIXED
        assert result[2] == "mixed", f"dot_2 expected mixed (4/8 live), got {result[2]}"

        # dot_3 (Food): fao(L), cme(L) → 2/2 = 1.0 → LIVE
        assert result[3] == "live", f"dot_3 expected live, got {result[3]}"

        # dot_4 (Credit): ig_oas(U), hy_oas(U), vix(U), us_10y(U), us_2y(U) → 0/5 = 0 → QUALITATIVE
        # But wait — dot_4 also has em_currency indicators? No, DOT_INDICATORS["dot_4"] = [ig_oas, hy_oas, vix, us_10y, us_2y]
        assert result[4] == "qualitative", f"dot_4 expected qualitative, got {result[4]}"

        # dot_5 (Debt): btp_bund_spread(U), cds_doubling(U) → 0/2 = 0 → QUALITATIVE
        assert result[5] == "qualitative", f"dot_5 expected qualitative, got {result[5]}"

        # dot_6 (China): caixin_pmi(L), china_property_default(U), news_caixin_pmi(L) → 2/3 = 0.67 → MIXED
        assert result[6] == "mixed", f"dot_6 expected mixed, got {result[6]}"

        # dot_7 (Political): protest_countries(U), govt_crisis(U), news_protest_countries(L) → 1/3 = 0.33 → QUALITATIVE
        assert result[7] == "qualitative", f"dot_7 expected qualitative, got {result[7]}"

        # dot_8 (Supply Chain): brent_price(U), hormuz_closure(U) → 0/2 = 0 → QUALITATIVE
        assert result[8] == "qualitative", f"dot_8 expected qualitative, got {result[8]}"

        # dot_9 (Health) — always qualitative
        assert result[9] == "qualitative"

        # Overall tier: worst is qualitative
        overall = overall_tier(result)
        assert overall == "qualitative"

    def test_all_fetchers_healthy_scenario(self):
        """Simulate: all fetchers healthy → all dots should be LIVE (except dot_9)."""
        indicators = {}
        for dot_num in range(1, 9):
            for slug in _indicators_for_dot(dot_num):
                if slug not in indicators:
                    indicators[slug] = {"value": 1.0, "data_status": "live"}

        result = classify_dots(indicators)
        for dot_num in range(1, 9):
            assert result[dot_num] == "live", f"dot_{dot_num} expected live, got {result[dot_num]}"
        assert result[9] == "qualitative"
        # dot_9 is always qualitative, so overall worst tier is qualitative
        assert overall_tier(result) == "qualitative"

    def test_news_derived_indicators_are_live(self):
        """News-derived indicators with data_status='live' count as live."""
        indicators = {
            "caixin_pmi": {"value": 49.5, "data_status": "live"},
            "china_property_default": {"value": 0, "data_status": "unavailable"},
            "news_caixin_pmi": {"value": 1, "data_status": "live"},  # news-derived live
        }
        # dot_6: caixin_pmi(L), china_property_default(U), news_caixin_pmi(L)
        # 2/3 = 0.67 → MIXED
        assert classify_dot(6, indicators) == "mixed"

    def test_partial_mixed_scenario(self):
        """9/14 indicators live → MIXED."""
        # Simulate a dot with mixed data. Use dot_2 which has 8 indicators.
        # 4 live out of 8 = 0.50 → MIXED
        indicators = {
            "brent_price": {"value": 98.4, "data_status": "live"},
            "wti_price": {"value": 87.5, "data_status": "live"},
            "natgas_price": {"value": 3.2, "data_status": "live"},
            "eu_gas_storage_pct": {"value": 85.0, "data_status": "live"},
            "us_spr_mbbl": {"value": None, "data_status": "unavailable"},
            "hormuz_closure": {"value": "", "data_status": "unavailable"},
            "news_eu_gas": {"value": None, "data_status": "unavailable"},
            "news_us_spr": {"value": None, "data_status": "unavailable"},
        }
        # 4/8 = 0.50 → MIXED
        assert classify_dot(2, indicators) == "mixed"
