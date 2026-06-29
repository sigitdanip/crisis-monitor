"""
Tier Classifier — determines per-dot data completeness tier.

Classifies each of the 9 crisis dots as LIVE, MIXED, or QUALITATIVE
based on the proportion of its indicators that have live data_status values.

Threshold logic (user-locked, not configurable in v1):
  - LIVE:        live_ratio >= 0.80 (at least 80% of indicators are live)
  - MIXED:       0.50 <= live_ratio < 0.80
  - QUALITATIVE: live_ratio < 0.50

live_ratio = count(data_status='live') / count(data_status in ('live','stale','unavailable'))

Design:
  Pure function — no side effects, no DB writes, no logging. The persistence step
  lives in pipeline_runner.py. Importable by normalize.py, alerts, newsletter_generator,
  and any other consumer that needs data-quality tiering.

  DOT_INDICATORS mapping is imported from indicator_narrator to ensure a single
  source of truth for dot → indicator relationships.
"""

from typing import Dict, Any, Optional

from src.agent.indicator_narrator import DOT_INDICATORS

# ── Thresholds ────────────────────────────────────────────────────────────
# User-locked per v1 spec — not configurable.

LIVE_THRESHOLD = 0.80
MIXED_THRESHOLD = 0.50  # everything below this is QUALITATIVE

# Valid data_status values that count as "available" (denominator of live_ratio).
# Indicators with data_status outside this set (e.g. missing key) are excluded.
COUNTABLE_STATUSES = frozenset({"live", "stale", "unavailable"})


def _detect_data_status(value: Any) -> Optional[str]:
    """Extract data_status from an indicator value.

    Handles both the structured format (dict with data_status key) introduced
    by the data_status refactor and the legacy flat-scalar format.

    Args:
        value: Indicator value — may be a scalar (int, float, None, str),
               a structured dict {value, data_status, ...}, or a news-flag
               dict {value, narrative}.

    Returns:
        'live', 'stale', 'unavailable', or None if undetectable.
    """
    if isinstance(value, dict):
        # Structured format: {'value': ..., 'data_status': 'live', ...}
        if "data_status" in value:
            return value["data_status"]
        # News-flag dict: {'value': 0/1, 'narrative': '...'}
        # News-derived indicators are always 'live' when present (they represent
        # a successful news scan that either found or didn't find relevant articles).
        if "value" in value:
            return "live"
        return None

    # Legacy flat format: scalar values are treated as 'live' if not None,
    # 'unavailable' if None.
    if value is None:
        return "unavailable"
    # Empty string (e.g. hormuz_closure default) — treat as unavailable
    if isinstance(value, str) and value == "":
        return "unavailable"
    return "live"


def _indicators_for_dot(dot_number: int) -> list[str]:
    """Get the indicator slugs for a dot number.

    Args:
        dot_number: 1-9.

    Returns:
        List of indicator slugs, or empty list for dot_9 (health — no indicators).
    """
    dot_key = f"dot_{dot_number}"
    return DOT_INDICATORS.get(dot_key, [])


def _dot_for_indicator(indicator_slug: str) -> int | None:
    """Find which dot (1-9) an indicator belongs to.

    Returns None if the indicator is not found in any dot.
    """
    for dot_key, slugs in DOT_INDICATORS.items():
        if indicator_slug in slugs:
            return int(dot_key.split("_")[-1])
    return None


def classify_dot(
    dot_number: int,
    indicators: Dict[str, Any],
    fetcher_health: Optional[Dict[str, Any]] = None,
) -> str:
    """Classify a single dot's data completeness tier.

    Args:
        dot_number: Dot number 1-9.
        indicators: Flat dict of slug → indicator value. Values may be structured
                    dicts (with data_status) or flat scalars.
        fetcher_health: Optional fetcher_health snapshot. Reserved for future use
                        (e.g. boosting confidence when a fetcher is known-down).

    Returns:
        'live', 'mixed', or 'qualitative'.
    """
    slugs = _indicators_for_dot(dot_number)

    # Dot 9 (Health) has no numeric indicators — always qualitative.
    if not slugs:
        return "qualitative"

    live_count = 0
    countable_count = 0

    for slug in slugs:
        value = indicators.get(slug)
        data_status = _detect_data_status(value)

        if data_status in COUNTABLE_STATUSES:
            countable_count += 1
            if data_status == "live":
                live_count += 1

    # All indicators were excluded (e.g. missing from indicators dict entirely).
    # This is an edge case — treat as qualitative.
    if countable_count == 0:
        return "qualitative"

    live_ratio = live_count / countable_count

    if live_ratio >= LIVE_THRESHOLD:
        return "live"
    elif live_ratio >= MIXED_THRESHOLD:
        return "mixed"
    else:
        return "qualitative"


def classify_dots(
    indicators: Dict[str, Any],
    fetcher_health: Optional[Dict[str, Any]] = None,
) -> Dict[int, str]:
    """Classify all 9 dots' data completeness tiers.

    Args:
        indicators: Flat dict of slug → indicator value. Values may be structured
                    dicts (with data_status) or flat scalars.
        fetcher_health: Optional fetcher_health snapshot (from the fetcher_health
                        table or normalize.py). Not currently used for calculation
                        but accepted for forward compatibility.

    Returns:
        Dict mapping dot number (1-9) to tier string:
        {1: 'live', 2: 'mixed', 3: 'qualitative', ...}
    """
    result: Dict[int, str] = {}
    for dot_number in range(1, 10):
        result[dot_number] = classify_dot(dot_number, indicators, fetcher_health)
    return result


def overall_tier(tiers: Dict[int, str]) -> str:
    """Compute the overall tier as the worst tier across all 9 dots.

    The overall tier is stored in pipeline_runs.overall_tier to give a
    single quick-to-query signal of data pipeline health.

    Args:
        tiers: Dict mapping dot_number → tier, as returned by classify_dots().

    Returns:
        'live', 'mixed', or 'qualitative' — the worst tier found.
    """
    tier_rank = {"qualitative": 0, "mixed": 1, "live": 2}
    worst = "live"
    worst_rank = tier_rank["live"]
    for tier in tiers.values():
        rank = tier_rank.get(tier, 2)  # unknown tiers treated as best (live)
        if rank < worst_rank:
            worst_rank = rank
            worst = tier
    return worst


def classify_with_health(
    indicators: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """Classify per-indicator tiers with dot and tier metadata for alert gating.

    Unlike classify_dots() which returns dot_number → tier, this returns
    indicator_slug → {tier, dot_number} suitable for per-indicator alert
    gating decisions.

    Keys are indexed by BOTH legacy slugs (from normalize.py) and spec slugs
    (from composite_scorer_v2) so that consumers using either naming scheme
    can look up tier information.

    Args:
        indicators: Flat dict of slug → indicator value (same as classify_dots).

    Returns:
        Dict mapping indicator_slug to {tier: str, dot_number: int | None}.
        Indicators not in any dot are excluded.
    """
    from src.agent.composite_scorer_v2 import LEGACY_SLUG_MAP, INDICATOR_REGISTRY

    # Compute dot tiers first
    dot_tiers = classify_dots(indicators)

    # Build reverse map: spec slug → legacy slug
    spec_to_legacy: dict[str, str] = {}
    for legacy, spec in LEGACY_SLUG_MAP.items():
        spec_to_legacy[spec] = legacy

    result: Dict[str, Dict[str, Any]] = {}
    for dot_number in range(1, 10):
        tier = dot_tiers.get(dot_number, "live")
        for slug in _indicators_for_dot(dot_number):
            entry = {"tier": tier, "dot_number": dot_number}
            result[slug] = entry
            # Also index by spec slug if this is a legacy slug
            spec_slug = LEGACY_SLUG_MAP.get(slug)
            if spec_slug and spec_slug != slug:
                result[spec_slug] = entry

    return result
