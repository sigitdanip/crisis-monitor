"""Composite Crisis Score v2 — Mathematical Formulation v2.

Replaces the 0-16 (8-category) system with a 0-30 (30-indicator) system.
Each indicator contributes 0-1 based on its distance from trigger thresholds
using a convexity exponent (p=2) to flatten normal noise and accelerate
near crisis thresholds.

Aggregation uses two layers:
  Layer 1: Intra-category normalized RSS (root-sum-square)
  Layer 2: Locked-denominator (9.9) weighted composite

Per spec: upgrades/mathematical_formulation_v2.md
Decisions locked 2026-06-21 by user. Math upgraded 2026-06-30.
"""

from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)

# =================================================================
# Category Weights — LOCKED 2026-06-21 by user
# =================================================================
CATEGORY_WEIGHTS: dict[str, float] = {
    "energy": 1.5,
    "financial": 1.4,
    "geopolitical": 1.4,
    "food": 1.3,
    "supply_chain": 1.3,
    "currency": 1.2,
    "economic": 1.0,
    "metals": 0.8,
}

# Locked denominator per v2 spec §3 — sum of all category weights = 9.9
# This is used as the fixed normalization base regardless of data availability.
LOCKED_DENOMINATOR = 9.9

# Stale data decay rates per category (α_cat, per hour)
# Fast-moving market categories decay faster to reflect higher uncertainty.
STALE_DECAY_RATES: dict[str, float] = {
    "energy": 0.02,
    "financial": 0.02,
    "geopolitical": 0.005,
    "food": 0.01,
    "supply_chain": 0.005,
    "currency": 0.02,
    "economic": 0.01,
    "metals": 0.01,
}

# Circuit breaker threshold: if combined weight of fully offline categories
# exceeds this, the system enters INDETERMINATE state (v2 spec §3).
CIRCUIT_BREAKER_THRESHOLD = 4.0

# =================================================================
# 5-Zone Interpretation (0-30 scale)
# =================================================================
INTERPRETATIONS: list[tuple[tuple[int, int], str]] = [
    ((0, 6), "normal"),
    ((6, 12), "monitor"),
    ((12, 20), "elevated"),
    ((20, 25), "alert"),
    ((25, 30), "critical"),
]


def _interpret(score: float) -> str:
    """Map a 0-30 score to a 5-zone label.

    Zone boundaries belong to the higher zone:
      normal   [0, 6)   — strictly less than 6
      monitor  [6, 12)  — 6 inclusive, less than 12
      elevated [12, 20) — 12 inclusive, less than 20
      alert    [20, 25) — 20 inclusive, less than 25
      critical [25, 30] — 25 inclusive, up to 30
    """
    for (lo, hi), label in INTERPRETATIONS:
        if hi == 30:
            if lo <= score <= hi:
                return label
        elif lo <= score < hi:
            return label
    return "critical" if score > 25 else "normal"


# =================================================================
# Non-Numeric Indicator Mappings
# =================================================================
NON_NUMERIC_MAPPINGS: dict[str, dict[str, float]] = {
    "hormuz_strait": {
        "normal": 0.0,
        "elevated": 0.3,
        "threatened": 0.7,
        "closure": 1.0,
    },
    "taiwan_strait_tension": {
        "normal": 0.0,
        "monitored": 0.2,
        "elevated": 0.6,
        "high": 1.0,
    },
    "russia_ukraine_conflict": {
        "normal": 0.0,
        "ongoing": 0.3,
        "escalation": 0.7,
        "major": 1.0,
    },
    "middle_east_conflict": {
        "normal": 0.0,
        "localized": 0.3,
        "regional": 0.7,
        "widespread": 1.0,
    },
    "china_taiwan_tension": {
        "normal": 0.0,
        "elevated": 0.6,
        "critical": 1.0,
    },
}


def score_non_numeric(value: str, indicator_slug: str) -> float:
    """Score a non-numeric (string/enum) indicator using explicit mappings."""
    mapping = NON_NUMERIC_MAPPINGS.get(indicator_slug, {})
    if not mapping:
        # Generic fallback: try extracting from status-like strings
        lowered = str(value).lower().strip()
        if lowered in ("normal", "stable", "low", "none"):
            return 0.0
        if lowered in ("breached", "elevated", "moderate", "activating"):
            return 0.5
        if lowered in ("critical", "high", "closure", "widespread", "major"):
            return 1.0
        return 0.0
    return mapping.get(str(value).lower().strip(), 0.0)


# =================================================================
# Gold MA Deviation Scoring — Q3 locked 2026-06-21
# =================================================================
GOLD_DEVIATION_THRESHOLDS = {
    "baseline_pct": 0.05,  # ±5% of MA = baseline (score 0)
    "breach_pct": 0.15,  # +15% above MA = upper breach
    "critical_pct": 0.25,  # +25% above MA = upper critical (cap at 1.0)
}


def score_gold_ma_deviation(
    value: float,
    ma_200: float | None,
    thresholds: dict[str, float] | None = None,
) -> tuple[float, dict[str, Any]]:
    """Score gold price based on % deviation from 200-day moving average.

    One-sided: below MA = score 0, only above MA is a signal.
    Per Q3 decision — replaces fixed $3000/$3500 triggers.

    Returns:
        (score_0_1, debug_info_dict)
    """
    if thresholds is None:
        thresholds = GOLD_DEVIATION_THRESHOLDS

    if ma_200 is None or ma_200 <= 0:
        return 0.0, {"method": "ma_deviation", "ma_200": ma_200, "deviation_pct": None, "error": "No MA available"}

    deviation = (value - ma_200) / ma_200

    debug = {
        "method": "ma_deviation",
        "ma_200": round(ma_200, 2),
        "deviation_pct": round(deviation * 100, 1),
        "value": value,
    }

    if deviation <= thresholds["baseline_pct"]:
        return 0.0, {**debug, "zone": "baseline"}
    elif deviation <= thresholds["breach_pct"]:
        breach_range = thresholds["breach_pct"] - thresholds["baseline_pct"]
        score = 0.5 * ((deviation - thresholds["baseline_pct"]) / breach_range) ** 2
        return round(score, 4), {**debug, "zone": "breach"}
    elif deviation <= thresholds["critical_pct"]:
        critical_range = thresholds["critical_pct"] - thresholds["breach_pct"]
        score = 0.5 + 0.5 * ((deviation - thresholds["breach_pct"]) / critical_range) ** 2
        return round(score, 4), {**debug, "zone": "critical"}
    else:
        return 1.0, {**debug, "zone": "catastrophic_capped"}


# =================================================================
# Numeric Indicator Scoring — Distance-From-Trigger
# =================================================================

def score_stale_decay(
    last_known_score: float,
    hours_stale: float,
    alpha: float,
) -> float:
    """Apply stale data decay per v2 spec §2.1.

    S_ind(t) = min(S_last + α_cat × t, 1.0)

    Drives uncertainty risk upward over time rather than holding stale values static.
    """
    return min(last_known_score + alpha * hours_stale, 1.0)


def score_numeric(
    value: float,
    baseline: float,
    trigger_breach: float,
    trigger_critical: float,
    is_inverted: bool = False,
    is_two_sided: bool = False,
    trigger_breach_lower: float | None = None,
    trigger_critical_lower: float | None = None,
) -> float:
    """Calculate 0-1 score for a numeric indicator using convexity exponent p=2.

    Per v2 spec §2.2: all live numeric indicators apply a squared power function
    (p=2) to flatten normal market noise and accelerate the score as values
    approach breach and critical thresholds.

    For normal indicators (higher = worse):
      - value <= baseline: score 0
      - baseline < value <= trigger_breach: 0.5 × ((x - Tbase)/(Tbreach - Tbase))²
      - trigger_breach < value <= trigger_critical: 0.5 + 0.5 × ((x - Tbreach)/(Tcrit - Tbreach))²
      - value > trigger_critical: capped at 1.0

    For inverted indicators (lower = worse): the logic is flipped internally.

    For two-sided indicators (both high and low are bad): uses the max
    distance from either the upper or lower breach thresholds.
    """
    if is_two_sided and trigger_breach_lower is not None:
        # Two-sided: treat each side as a one-sided indicator, take max.
        # Upper side: higher is worse (normal logic)
        center = (trigger_breach_lower + trigger_breach) / 2.0
        score_upper = score_numeric(
            value=value,
            baseline=center,
            trigger_breach=trigger_breach,
            trigger_critical=trigger_critical,
            is_inverted=False,
            is_two_sided=False,
        )
        # Lower side: lower is worse (inverted logic)
        score_lower = score_numeric(
            value=value,
            baseline=center,
            trigger_breach=trigger_breach_lower,
            trigger_critical=trigger_critical_lower if trigger_critical_lower is not None else trigger_breach_lower,
            is_inverted=True,
            is_two_sided=False,
        )
        return max(score_upper, score_lower)

    if is_inverted:
        # Inverted: lower is worse (v2 spec §2.2.B)
        if value >= baseline:
            return 0.0
        elif value >= trigger_breach:
            # Between baseline and breach
            denom = baseline - trigger_breach
            if denom <= 0:
                return 0.0
            return 0.5 * ((baseline - value) / denom) ** 2
        elif value >= trigger_critical:
            # Between breach and critical
            denom = trigger_breach - trigger_critical
            if denom <= 0:
                return 1.0
            return 0.5 + 0.5 * ((trigger_breach - value) / denom) ** 2
        else:
            # Below critical — cap at 1.0
            return 1.0

    # Normal case: higher is worse (v2 spec §2.2.A)
    if value <= baseline:
        return 0.0
    elif value <= trigger_breach:
        denom = trigger_breach - baseline
        if denom <= 0:
            return 0.0
        return 0.5 * ((value - baseline) / denom) ** 2
    elif value <= trigger_critical:
        denom = trigger_critical - trigger_breach
        if denom <= 0:
            return 1.0
        return 0.5 + 0.5 * ((value - trigger_breach) / denom) ** 2
    else:
        # Above critical — cap at 1.0
        return 1.0


# =================================================================
# Indicator Registry — All 30 Indicators
# =================================================================

class IndicatorConfig:
    """Configuration for a single crisis indicator."""

    def __init__(
        self,
        slug: str,
        name: str,
        category: str,
        value_type: str = "numeric",  # numeric, ma_deviation, enum
        unit: str = "",
        baseline: float | None = None,
        trigger_breach: float | None = None,
        trigger_critical: float | None = None,
        trigger_breach_lower: float | None = None,
        trigger_critical_lower: float | None = None,
        is_inverted: bool = False,
        is_two_sided: bool = False,
        # Gold MA-deviation specific
        ma_window: int = 200,
    ):
        self.slug = slug
        self.name = name
        self.category = category
        self.value_type = value_type
        self.unit = unit
        self.baseline = baseline
        self.trigger_breach = trigger_breach
        self.trigger_critical = trigger_critical
        self.trigger_breach_lower = trigger_breach_lower
        self.trigger_critical_lower = trigger_critical_lower
        self.is_inverted = is_inverted
        self.is_two_sided = is_two_sided
        self.ma_window = ma_window


# All 30 indicators defined per spec section 1
INDICATOR_REGISTRY: dict[str, IndicatorConfig] = {
    # ======== Energy (4 indicators, weight 1.5x) ========
    "brent_oil": IndicatorConfig(
        slug="brent_oil", name="Brent Oil Price", category="energy",
        unit="USD/barrel", baseline=75, trigger_breach=90, trigger_critical=110,
    ),
    "wti_oil": IndicatorConfig(
        slug="wti_oil", name="WTI Oil Price", category="energy",
        unit="USD/barrel", baseline=70, trigger_breach=85, trigger_critical=105,
    ),
    "eu_gas_storage": IndicatorConfig(
        slug="eu_gas_storage", name="EU Gas Storage", category="energy",
        unit="%", baseline=85, trigger_breach=70, trigger_critical=60,
        is_inverted=True,  # lower is worse
    ),
    "natgas_henry_hub": IndicatorConfig(
        slug="natgas_henry_hub", name="NatGas Henry Hub", category="energy",
        unit="USD/MMBtu", baseline=3.0, trigger_breach=4.5, trigger_critical=7.0,
    ),

    # ======== Food (4 indicators, weight 1.3x) ========
    "fao_food_price_index": IndicatorConfig(
        slug="fao_food_price_index", name="FAO Food Price Index", category="food",
        unit="index points", baseline=125, trigger_breach=140, trigger_critical=155,
    ),
    "wheat_futures": IndicatorConfig(
        slug="wheat_futures", name="Wheat Futures", category="food",
        unit="USD/bushel", baseline=5.5, trigger_breach=7.50, trigger_critical=9.00,
    ),
    "corn_futures": IndicatorConfig(
        slug="corn_futures", name="Corn Futures", category="food",
        unit="USD/bushel", baseline=4.0, trigger_breach=5.50, trigger_critical=7.00,
    ),
    "rice_price": IndicatorConfig(
        slug="rice_price", name="Rice Price", category="food",
        unit="USD/cwt", baseline=14, trigger_breach=16, trigger_critical=20,
    ),

    # ======== Economic (4 indicators, weight 1.0x) ========
    "us_ism_manufacturing": IndicatorConfig(
        slug="us_ism_manufacturing", name="US ISM Manufacturing", category="economic",
        unit="index", baseline=50, trigger_breach=47, trigger_critical=45,
        is_inverted=True,
    ),
    "china_caixin_pmi": IndicatorConfig(
        slug="china_caixin_pmi", name="China Caixin Manufacturing PMI", category="economic",
        unit="index", baseline=50, trigger_breach=48, trigger_critical=46,
        is_inverted=True,
    ),
    "eurozone_manufacturing_pmi": IndicatorConfig(
        slug="eurozone_manufacturing_pmi", name="Eurozone Manufacturing PMI", category="economic",
        unit="index", baseline=50, trigger_breach=47, trigger_critical=45,
        is_inverted=True,
    ),
    "us_jobless_claims": IndicatorConfig(
        slug="us_jobless_claims", name="US Initial Jobless Claims", category="economic",
        unit="thousands", baseline=230, trigger_breach=280, trigger_critical=320,
    ),

    # ======== Financial (4 indicators, weight 1.4x) ========
    "vix": IndicatorConfig(
        slug="vix", name="VIX Volatility Index", category="financial",
        unit="index points", baseline=15, trigger_breach=25, trigger_critical=35,
    ),
    "move_bond_volatility": IndicatorConfig(
        slug="move_bond_volatility", name="MOVE Bond Volatility", category="financial",
        unit="index points", baseline=90, trigger_breach=120, trigger_critical=150,
    ),
    "ted_spread": IndicatorConfig(
        slug="ted_spread", name="TED Spread", category="financial",
        unit="basis points", baseline=20, trigger_breach=50, trigger_critical=80,
    ),
    "credit_spread": IndicatorConfig(
        slug="credit_spread", name="Credit Spread (BBB-10Y Treasury)", category="financial",
        unit="basis points", baseline=120, trigger_breach=200, trigger_critical=300,
    ),

    # ======== Currency (3 indicators, weight 1.2x) ========
    "dxy_index": IndicatorConfig(
        slug="dxy_index", name="DXY Dollar Index", category="currency",
        unit="index", baseline=100,
        trigger_breach=105, trigger_critical=110,
        trigger_breach_lower=95, trigger_critical_lower=90,
        is_two_sided=True,
    ),
    "eur_usd": IndicatorConfig(
        slug="eur_usd", name="EUR/USD Rate", category="currency",
        unit="rate", baseline=1.10,
        trigger_breach=1.15, trigger_critical=1.20,  # upper: EUR too strong
        trigger_breach_lower=1.05, trigger_critical_lower=1.00,  # lower: EUR too weak
        is_two_sided=True,
    ),
    "usd_cny": IndicatorConfig(
        slug="usd_cny", name="USD/CNY Rate", category="currency",
        unit="rate", baseline=7.0, trigger_breach=7.2, trigger_critical=7.4,
    ),

    # ======== Metals (3 indicators, weight 0.8x) ========
    "gold_price": IndicatorConfig(
        slug="gold_price", name="Gold Price", category="metals",
        value_type="ma_deviation", unit="USD/troy oz",
    ),
    "copper_price": IndicatorConfig(
        slug="copper_price", name="Copper Price", category="metals",
        unit="USD/lb", baseline=6.0, trigger_breach=7.50, trigger_critical=9.00,
    ),
    "silver_price": IndicatorConfig(
        slug="silver_price", name="Silver Price", category="metals",
        unit="USD/troy oz", baseline=55, trigger_breach=65, trigger_critical=75,
    ),

    # ======== Supply Chain (4 indicators, weight 1.3x) ========
    "baltic_dry_index": IndicatorConfig(
        slug="baltic_dry_index", name="Baltic Dry Index", category="supply_chain",
        unit="index points", baseline=2500, trigger_breach=3200, trigger_critical=4000,
    ),
    "scfi": IndicatorConfig(
        slug="scfi", name="Shanghai Containerized Freight Index", category="supply_chain",
        unit="index points", baseline=2000, trigger_breach=3000, trigger_critical=4000,
    ),
    "hormuz_strait": IndicatorConfig(
        slug="hormuz_strait", name="Hormuz Strait Status", category="supply_chain",
        value_type="enum", unit="enum",
    ),
    "taiwan_strait_tension": IndicatorConfig(
        slug="taiwan_strait_tension", name="Taiwan Strait Tension", category="supply_chain",
        value_type="enum", unit="enum",
    ),

    # ======== Geopolitical (4 indicators, weight 1.4x) ========
    "russia_ukraine_conflict": IndicatorConfig(
        slug="russia_ukraine_conflict", name="Russia-Ukraine Conflict Level", category="geopolitical",
        value_type="enum", unit="enum",
    ),
    "middle_east_conflict": IndicatorConfig(
        slug="middle_east_conflict", name="Middle East Conflict Level", category="geopolitical",
        value_type="enum", unit="enum",
    ),
    "china_taiwan_tension": IndicatorConfig(
        slug="china_taiwan_tension", name="China-Taiwan Tension", category="geopolitical",
        value_type="enum", unit="enum",
    ),
    "global_terrorism_index": IndicatorConfig(
        slug="global_terrorism_index", name="Global Terrorism Index", category="geopolitical",
        unit="index", baseline=4.5, trigger_breach=6, trigger_critical=7.5,
    ),
}

# Legacy key mapping: maps old normalize.py slugs to spec indicator slugs.
# When normalize.py provides keys like 'brent_price', we resolve them to 'brent_oil'.
LEGACY_SLUG_MAP: dict[str, str] = {
    # normalize.py key → spec slug
    "brent_price": "brent_oil",
    "wti_price": "wti_oil",
    "eu_gas_storage_pct": "eu_gas_storage",
    "natgas_price": "natgas_henry_hub",
    "fao_monthly_change_pct": "fao_food_price_index",
    "caixin_pmi": "china_caixin_pmi",
    "dxy": "dxy_index",
    "gold_price": "gold_price",
    "vix": "vix",
    "hormuz_closure": "hormuz_strait",
    # Credit/financial — map old OAS to credit spread (best approximation)
    "ig_oas": "credit_spread",
    "hy_oas": "credit_spread",
    # EM currencies → no direct spec equivalent; skip (score 0)
}


def _resolve_slug(raw_key: str) -> str | None:
    """Resolve a raw normalize.py key to a spec indicator slug.

    Returns None if the indicator is not recognized (old system remnant).
    """
    # Direct match
    if raw_key in INDICATOR_REGISTRY:
        return raw_key
    # Legacy mapping
    if raw_key in LEGACY_SLUG_MAP:
        return LEGACY_SLUG_MAP[raw_key]
    # News-derived indicators: strip 'news_' prefix
    if raw_key.startswith("news_"):
        base = raw_key.removeprefix("news_")
        if base in INDICATOR_REGISTRY:
            return base
    return None


def _extract_scalar(raw_value: Any) -> float | None:
    """Extract a numeric scalar from potentially nested value."""
    if raw_value is None:
        return None
    if isinstance(raw_value, (int, float)):
        return float(raw_value)
    if isinstance(raw_value, dict):
        return raw_value.get("value")
    if isinstance(raw_value, str):
        try:
            return float(raw_value)
        except (ValueError, TypeError):
            return None
    return None


# =================================================================
# Main Entry Point
# =================================================================


def score_composite(
    indicators: dict[str, Any],
    gold_ma_200: float | None = None,
) -> dict[str, Any]:
    """Score all 30 indicators and return composite analysis.

    Uses two-layer aggregation per v2 spec §3:
      Layer 1: Intra-category normalized RSS — S_cat = √(Σ S²ᵢ / nₖ)
      Layer 2: Locked-denominator composite — C = round((Σ S_cat × W_cat / 9.9) × 30, 1)

    Also checks the circuit breaker: if combined weight of fully offline
    categories exceeds 4.0, returns INDETERMINATE state.

    Args:
        indicators: dict of indicator name → value pairs (from normalize.py).
                    Values can be numeric, string, or dicts (for news-derived flags).
        gold_ma_200: 200-day moving average for gold. If None, gold scores 0.

    Returns:
        {
            "composite": float,              # 0-30 composite score
            "interpretation": str,           # 5-zone label
            "dashboard_state": str,          # "ACTIVE" or "INDETERMINATE"
            "category_rss_scores": dict,     # {category: RSS score 0-1}
            "category_scores": dict,         # {category: weighted contribution}
            "per_indicator_scores": dict,    # {slug: raw_score}
            "indicator_details": dict,       # per-indicator details
            "available_count": int,
        }
    """
    # Collect per-indicator scores grouped by category
    category_indicator_scores: dict[str, list[float]] = {cat: [] for cat in CATEGORY_WEIGHTS}
    available_count: int = 0
    indicator_details: dict[str, dict[str, Any]] = {}

    for raw_key, raw_value in indicators.items():
        slug = _resolve_slug(raw_key)
        if slug is None:
            continue

        config = INDICATOR_REGISTRY[slug]

        # Score the indicator
        if config.value_type == "enum":
            str_value = str(raw_value) if not isinstance(raw_value, str) else raw_value
            raw_score = score_non_numeric(str_value, slug)
            debug_info = {"method": "enum", "raw_value": str_value}
        elif config.value_type == "ma_deviation":
            scalar = _extract_scalar(raw_value)
            if scalar is not None and scalar > 0:
                raw_score, debug_info = score_gold_ma_deviation(scalar, gold_ma_200)
            else:
                raw_score, debug_info = 0.0, {"method": "ma_deviation", "error": "No value or MA available"}
        else:
            scalar = _extract_scalar(raw_value)
            if scalar is not None and config.trigger_breach is not None and config.trigger_critical is not None:
                baseline = config.baseline if config.baseline is not None else config.trigger_breach * 0.7
                raw_score = score_numeric(
                    value=scalar,
                    baseline=baseline,
                    trigger_breach=config.trigger_breach,
                    trigger_critical=config.trigger_critical,
                    is_inverted=config.is_inverted,
                    is_two_sided=config.is_two_sided,
                    trigger_breach_lower=config.trigger_breach_lower,
                    trigger_critical_lower=config.trigger_critical_lower,
                )
                debug_info = {"method": "distance_from_trigger", "value": scalar, "baseline": baseline}
            else:
                raw_score, debug_info = 0.0, {"method": "numeric", "error": "No trigger config or value unavailable"}

        raw_score = max(0.0, min(1.0, raw_score))

        category_indicator_scores[config.category].append(raw_score)
        available_count += 1

        indicator_details[slug] = {
            "name": config.name,
            "category": config.category,
            "weight": CATEGORY_WEIGHTS.get(config.category, 1.0),
            "raw_score": round(raw_score, 4),
            "debug": debug_info,
        }

    # ── Layer 1: Intra-Category Normalized RSS ──────────────────────────
    # S_cat,k = √(Σ S²ᵢ / nₖ)  — per v2 spec §3
    category_rss_scores: dict[str, float] = {}
    for cat, scores in category_indicator_scores.items():
        if scores:
            sum_sq = sum(s ** 2 for s in scores)
            category_rss_scores[cat] = math.sqrt(sum_sq / len(scores))
        else:
            category_rss_scores[cat] = 0.0

    # ── Circuit Breaker Check ───────────────────────────────────────────
    # If combined weight of fully offline categories > 4.0 → INDETERMINATE
    offline_weight = sum(
        CATEGORY_WEIGHTS[cat]
        for cat, scores in category_indicator_scores.items()
        if not scores  # no indicators at all for this category
    )
    dashboard_state = "INDETERMINATE" if offline_weight > CIRCUIT_BREAKER_THRESHOLD else "ACTIVE"

    # ── Layer 2: Locked-Denominator Composite ───────────────────────────
    # C = round((Σ S_cat × W_cat / 9.9) × 30, 1)  — per v2 spec §3
    if dashboard_state == "INDETERMINATE":
        composite = 0.0
        interpretation = "indeterminate"
    else:
        weighted_sum = sum(
            category_rss_scores[cat] * CATEGORY_WEIGHTS[cat]
            for cat in CATEGORY_WEIGHTS
        )
        composite = round((weighted_sum / LOCKED_DENOMINATOR) * 30.0, 1)
        composite = max(0.0, min(30.0, composite))
        interpretation = _interpret(composite)

    # Category-level weighted contributions (for downstream consumers)
    category_scores: dict[str, float] = {
        cat: round(category_rss_scores[cat] * CATEGORY_WEIGHTS[cat], 4)
        for cat in CATEGORY_WEIGHTS
    }

    return {
        "composite": composite,
        "interpretation": interpretation,
        "dashboard_state": dashboard_state,
        "category_rss_scores": {cat: round(v, 4) for cat, v in category_rss_scores.items()},
        "category_scores": category_scores,
        "per_indicator_scores": {
            slug: details["raw_score"] for slug, details in indicator_details.items()
        },
        "indicator_details": indicator_details,
        "available_count": available_count,
        "total_indicators": len(INDICATOR_REGISTRY),
        "offline_category_weight": round(offline_weight, 2),
    }


# =================================================================
# Self-Check
# =================================================================

if __name__ == "__main__":
    # --- Scenario 1: All baseline (score should be 0) ---
    all_baseline: dict[str, Any] = {
        "brent_oil": 75, "wti_oil": 70, "eu_gas_storage": 85, "natgas_henry_hub": 3.0,
        "fao_food_price_index": 125, "wheat_futures": 5.5, "corn_futures": 4.0, "rice_price": 14,
        "us_ism_manufacturing": 50, "china_caixin_pmi": 50, "eurozone_manufacturing_pmi": 50,
        "us_jobless_claims": 230,
        "vix": 15, "move_bond_volatility": 90, "ted_spread": 20, "credit_spread": 120,
        "dxy_index": 100, "eur_usd": 1.10, "usd_cny": 7.0,
        "copper_price": 6.0, "silver_price": 55,
        "baltic_dry_index": 2500, "scfi": 2000,
        "global_terrorism_index": 4.5,
    }
    result = score_composite(all_baseline)
    assert result["composite"] == 0.0, f"Expected 0, got {result['composite']}"
    assert result["interpretation"] == "normal"
    assert result["dashboard_state"] == "ACTIVE"
    print(f"  PASS: All baseline → {result['composite']}/30 ({result['interpretation']})")

    # --- Scenario 2: All at breach (convexity p=2 → each scores 0.5²×0.5=0.125, not 0.5) ---
    # With p=2, at exactly breach threshold each indicator scores exactly 0.5
    # because (Tbreach - Tbase)/(Tbreach - Tbase) = 1, so 0.5 × 1² = 0.5
    all_breach: dict[str, Any] = {
        "brent_oil": 90, "wti_oil": 85, "eu_gas_storage": 70, "natgas_henry_hub": 4.5,
        "fao_food_price_index": 140, "wheat_futures": 7.5, "corn_futures": 5.5, "rice_price": 16,
        "us_ism_manufacturing": 47, "china_caixin_pmi": 48, "eurozone_manufacturing_pmi": 47,
        "us_jobless_claims": 280,
        "vix": 25, "move_bond_volatility": 120, "ted_spread": 50, "credit_spread": 200,
        "dxy_index": 105, "eur_usd": 1.05, "usd_cny": 7.2,
        "copper_price": 7.5, "silver_price": 65,
        "baltic_dry_index": 3200, "scfi": 3000,
        "global_terrorism_index": 6,
    }
    result = score_composite(all_breach)
    # At breach, each indicator scores 0.5 → RSS per category = 0.5
    # C = (Σ 0.5 × Wcat / 9.9) × 30 = (0.5 × 9.9 / 9.9) × 30 = 15
    assert 14.0 <= result["composite"] <= 16.0, f"Expected ~15, got {result['composite']}"
    assert result["interpretation"] == "elevated"
    print(f"  PASS: All breach → {result['composite']}/30 ({result['interpretation']})")

    # --- Scenario 3: All critical (score should be ~30) ---
    all_critical: dict[str, Any] = {
        "brent_oil": 110, "wti_oil": 105, "eu_gas_storage": 60, "natgas_henry_hub": 7.0,
        "fao_food_price_index": 155, "wheat_futures": 9.0, "corn_futures": 7.0, "rice_price": 20,
        "us_ism_manufacturing": 45, "china_caixin_pmi": 46, "eurozone_manufacturing_pmi": 45,
        "us_jobless_claims": 320,
        "vix": 35, "move_bond_volatility": 150, "ted_spread": 80, "credit_spread": 300,
        "dxy_index": 110, "eur_usd": 1.00, "usd_cny": 7.4,
        "copper_price": 9.0, "silver_price": 75,
        "baltic_dry_index": 4000, "scfi": 4000,
        "global_terrorism_index": 7.5,
    }
    result = score_composite(all_critical)
    assert 28.0 <= result["composite"] <= 30.0, f"Expected ~30, got {result['composite']}"
    assert result["interpretation"] == "critical"
    print(f"  PASS: All critical → {result['composite']}/30 ({result['interpretation']})")

    # --- Scenario 4: Convexity check — mid-zone should score 0.125 not 0.25 ---
    # Brent at $82.5 = midpoint of base(75)→breach(90)
    # v2: 0.5 × ((82.5-75)/(90-75))² = 0.5 × 0.5² = 0.5 × 0.25 = 0.125
    result = score_composite({"brent_oil": 82.5})
    brent_score = result["indicator_details"]["brent_oil"]["raw_score"]
    assert abs(brent_score - 0.125) < 0.01, f"Brent at midpoint should score ~0.125, got {brent_score}"
    print(f"  PASS: Convexity check — Brent mid-zone = {brent_score} (expected ~0.125)")

    # --- Scenario 5: RSS aggregation check ---
    # 1 critical (1.0) + 3 zero → RSS = √(1/4) = 0.5, not 0.25 (v1 average)
    result = score_composite({
        "brent_oil": 115,      # score = 1.0 (critical)
        "wti_oil": 70,         # score = 0.0 (baseline)
        "eu_gas_storage": 85,  # score = 0.0 (baseline)
        "natgas_henry_hub": 3.0,  # score = 0.0 (baseline)
    })
    energy_rss = result["category_rss_scores"]["energy"]
    assert abs(energy_rss - 0.5) < 0.01, f"Energy RSS should be ~0.5, got {energy_rss}"
    print(f"  PASS: RSS aggregation — 1 critical + 3 zero = energy RSS {energy_rss}")

    # --- Scenario 6: Sparse data (avoid circuit breaker) → locked denominator ---
    sparse: dict[str, Any] = {
        "brent_oil": 115,  # critical (energy)
        "vix": 40,         # critical (financial)
        "fao_food_price_index": 125, # baseline (food)
        "copper_price": 6.0, # baseline (metals)
        "dxy_index": 100, # baseline (currency)
    }
    result = score_composite(sparse)
    # With locked denominator:
    # energy RSS = 1.0, financial RSS = 1.0, food/metals/currency RSS = 0.0
    # C = ((1.0 × 1.5 + 1.0 × 1.4) / 9.9) × 30 = (2.9 / 9.9) × 30 ≈ 8.8
    assert 8.0 <= result["composite"] <= 9.0, f"Sparse score out of range: {result['composite']}"
    assert result["available_count"] == 5
    assert result["dashboard_state"] == "ACTIVE"
    print(f"  PASS: Sparse (avoid CB) → {result['composite']}/30 ({result['interpretation']})")

    # --- Scenario 7: Circuit breaker ---
    # Only 1 indicator in energy → 7 categories offline
    # Offline weight: 1.4+1.4+1.3+1.3+1.2+1.0+0.8 = 8.4 > 4.0 → INDETERMINATE
    result = score_composite({"brent_oil": 115})
    assert result["dashboard_state"] == "INDETERMINATE", f"Expected INDETERMINATE, got {result['dashboard_state']}"
    assert result["interpretation"] == "indeterminate"
    print(f"  PASS: Circuit breaker → {result['dashboard_state']}")

    # --- Scenario 8: Inverted logic (EU Gas) ---
    result = score_composite({"eu_gas_storage": 85})  # baseline → 0
    assert result["indicator_details"]["eu_gas_storage"]["raw_score"] == 0.0

    result = score_composite({"eu_gas_storage": 58.3})  # below critical
    details = result["indicator_details"]["eu_gas_storage"]
    assert details["raw_score"] > 0.9, f"EU Gas at 58.3% should be near critical, got {details['raw_score']}"
    print(f"  PASS: Inverted EU Gas at 58.3% → raw_score={details['raw_score']}")

    # --- Scenario 9: Gold MA deviation (convexity p=2 now) ---
    result = score_composite({"gold_price": 4172}, gold_ma_200=3300)
    details = result["indicator_details"]["gold_price"]
    assert details["raw_score"] == 1.0, f"Gold at +26.4% should be capped at 1.0, got {details['raw_score']}"
    assert details["debug"]["zone"] == "catastrophic_capped"
    print(f"  PASS: Gold MA deviation +26.4% → capped at {details['raw_score']}")

    result = score_composite({"gold_price": 3000}, gold_ma_200=3300)
    details = result["indicator_details"]["gold_price"]
    assert details["raw_score"] == 0.0, f"Gold below MA should score 0, got {details['raw_score']}"
    print(f"  PASS: Gold below MA → score 0")

    # --- Scenario 10: Two-sided indicator (DXY) ---
    result = score_composite({"dxy_index": 100})  # at center → 0
    assert result["indicator_details"]["dxy_index"]["raw_score"] == 0.0

    result = score_composite({"dxy_index": 108})  # above upper breach → scored
    dxy_score = result["indicator_details"]["dxy_index"]["raw_score"]
    assert dxy_score > 0.1, f"DXY at 108 should be elevated, got {dxy_score}"

    result = score_composite({"dxy_index": 92})  # below lower breach → scored
    dxy_score = result["indicator_details"]["dxy_index"]["raw_score"]
    assert dxy_score > 0.1, f"DXY at 92 should be elevated, got {dxy_score}"
    print(f"  PASS: Two-sided DXY scoring works")

    # --- Scenario 11: Legacy key mapping ---
    result = score_composite({"brent_price": 115})  # old normalize.py key
    assert "brent_oil" in result["indicator_details"], f"Legacy key brent_price not mapped"
    assert result["indicator_details"]["brent_oil"]["raw_score"] == 1.0
    print(f"  PASS: Legacy key mapping (brent_price → brent_oil)")

    # --- Scenario 12: Stale decay function ---
    assert score_stale_decay(0.3, 10, 0.02) == 0.5
    assert score_stale_decay(0.9, 20, 0.02) == 1.0  # capped at 1.0
    print(f"  PASS: Stale data decay function")

    print("\n=== ALL CHECKS PASSED ===")

