"""Alerts engine — watches indicator scores and writes alert rows using v1.2 format.

Evaluates each of the 30 indicators against the composite scorer output,
detects NORMAL→BREACHED and BREACHED→CRITICAL transitions, and writes
alert rows to the `alerts` table with the v1.2 format template.

Format (spec section 9, locked 2026-06-21):
    [{category}] {name} = {raw_value} [{flag}] (+x/1.0)

Cooldown: 24h de-dup by category + indicator + flag.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.db.database import get_db
from src.agent.composite_scorer_v2 import (
    INDICATOR_REGISTRY,
    CATEGORY_WEIGHTS,
    score_gold_ma_deviation,
)

logger = logging.getLogger(__name__)

# ── Flag determination ───────────────────────────────────────────────────────

FLAG_SEVERITY: dict[str, int] = {"NORMAL": 0, "BREACHED": 1, "CRITICAL": 2}
SEVERITY_FLAG: dict[int, str] = {v: k for k, v in FLAG_SEVERITY.items()}


def determine_flag(raw_score: float) -> str:
    """Map a 0-1 raw score to NORMAL / BREACHED / CRITICAL.

    NORMAL   → score = 0    (at or below baseline)
    BREACHED → 0 < score < 1
    CRITICAL → score = 1    (at or above trigger_critical, capped)
    """
    if raw_score <= 0.0:
        return "NORMAL"
    elif raw_score < 1.0:
        return "BREACHED"
    else:
        return "CRITICAL"


def _flag_severity(flag: str) -> int:
    return FLAG_SEVERITY.get(flag, 0)


# ── Alert message formatting ─────────────────────────────────────────────────


def _format_numeric(
    category: str,
    name: str,
    value: float | None,
    unit: str,
    flag: str,
    raw_score: float,
    indicator: str,
    debug_info: dict[str, Any],
    gold_ma_200: float | None = None,
) -> str:
    """Format alert message for a numeric indicator."""
    # Build the base: [{category}] {name} = {value}{unit} [{flag}]
    value_str: str
    if value is not None:
        # Round for display — integers for large numbers, 1dp for small
        if abs(value) >= 100:
            value_str = f"{value:,.0f}"
        elif abs(value) >= 10:
            value_str = f"{value:.1f}"
        else:
            value_str = f"{value:.2f}"
    else:
        value_str = "N/A"

    # Prepend currency symbols where appropriate
    if indicator in ("gold_price", "silver_price"):
        value_str = f"${value_str}"
    elif indicator in ("brent_oil", "wti_oil", "natgas_henry_hub",
                       "wheat_futures", "corn_futures", "rice_price"):
        value_str = f"${value_str}"
    elif indicator == "copper_price":
        value_str = f"${value_str}"

    unit_suffix = f" {unit}" if unit and unit not in ("usd_per_oz", "usd_per_barrel", "usd_per_mmbtu",
                                                       "usd_per_bushel", "usd_per_cwt", "usd_per_lb") else ""
    # Simplify unit labels for display
    unit_display = _simplify_unit(unit)

    if indicator == "gold_price" and debug_info.get("method") == "ma_deviation":
        # Gold special format: Gold = $4172 (+12% above 200d MA $3726) [CRITICAL]
        ma = debug_info.get("ma_200")
        deviation_pct = debug_info.get("deviation_pct")
        if ma is not None and deviation_pct is not None:
            direction = "above" if deviation_pct >= 0 else "below"
            message = (
                f"[{category}] {name} = {value_str} "
                f"(+{deviation_pct}% {direction} 200d MA ${ma:,.0f}) [{flag}]"
            )
        else:
            message = f"[{category}] {name} = {value_str} [{flag}]"
    else:
        message = f"[{category}] {name} = {value_str}{unit_display} [{flag}]"

    # Composite contribution for non-normal
    if flag != "NORMAL":
        message += f" (+{raw_score:.2f}/1.0)"

    return message


def _format_non_numeric(
    category: str,
    name: str,
    enum_value: str,
    flag: str,
    raw_score: float,
) -> str:
    """Format alert message for a non-numeric (enum) indicator."""
    display_value = enum_value.replace("_", " ").title()
    message = f"[{category}] {name} = {display_value} [{flag}]"
    if flag != "NORMAL":
        message += f" (+{raw_score:.2f}/1.0)"
    return message


def _simplify_unit(unit: str) -> str:
    """Simplify indicator unit strings for display in alert messages."""
    # Map human-readable unit strings (from IndicatorConfig) to compact display forms.
    # Units that are redundant with the indicator name become empty.
    mapping: dict[str, str] = {
        # Energy
        "USD/barrel": " USD/barrel",
        "USD/MMBtu": " USD/MMBtu",
        # Food
        "USD/bushel": " USD/bushel",
        "USD/cwt": " USD/cwt",
        # Metals
        "USD/troy oz": " USD/oz",
        "USD/lb": " USD/lb",
        # Financial / Supply Chain
        "index points": "",  # redundant with "Index" in name
        "basis points": " bp",
        # Other
        "index": "",          # redundant
        "thousands": "K",
        "rate": "",
        "enum": "",
        "%": "%",
    }
    simplified = mapping.get(unit, f" {unit}")
    return simplified


def format_alert_message(
    slug: str,
    indicator_details: dict[str, Any],
    flag: str,
    raw_score: float,
    raw_value: Any = None,
    gold_ma_200: float | None = None,
) -> str:
    """Format a single alert message according to the v1.2 template.

    Args:
        slug: Indicator slug (e.g. 'brent_oil', 'hormuz_strait')
        indicator_details: Details dict from composite scorer result
        flag: NORMAL, BREACHED, or CRITICAL
        raw_score: 0-1 raw score
        raw_value: The raw indicator value (numeric or string)
        gold_ma_200: 200-day gold MA (for ma_deviation indicators)

    Returns:
        Formatted alert message string.
    """
    category = indicator_details.get("category", "unknown")
    name = indicator_details.get("name", slug)
    debug_info = indicator_details.get("debug", {})

    config = INDICATOR_REGISTRY.get(slug)
    value_type = config.value_type if config else "numeric"

    if value_type == "enum":
        enum_value = str(raw_value) if raw_value is not None else "unknown"
        return _format_non_numeric(category, name, enum_value, flag, raw_score)
    else:
        scalar = None
        if isinstance(raw_value, (int, float)):
            scalar = float(raw_value)
        elif isinstance(raw_value, dict):
            scalar = raw_value.get("value")

        return _format_numeric(
            category=category,
            name=name,
            value=scalar,
            unit=config.unit if config else "",
            flag=flag,
            raw_score=raw_score,
            indicator=slug,
            debug_info=debug_info,
            gold_ma_200=gold_ma_200,
        )


# ── Transition detection & cooldown ──────────────────────────────────────────


def _get_previous_flag(conn, indicator: str) -> str | None:
    """Get the most recent alert flag for an indicator from the alerts table."""
    row = conn.execute(
        "SELECT message FROM alerts WHERE indicator = ? ORDER BY triggered_at DESC LIMIT 1",
        (indicator,),
    ).fetchone()
    if row is None:
        return None
    message = row["message"]
    # Extract flag from message: look for [FLAG] pattern at end before optional (+x/1.0)
    import re
    match = re.search(r"\[(NORMAL|BREACHED|CRITICAL)\](?:\s*\(\+[\d.]+/1\.0\))?$", message)
    if match:
        return match.group(1)
    return None


def _is_duplicate(conn, category: str, indicator: str, flag: str, within_hours: int = 24) -> bool:
    """Check if an alert with same category+indicator+flag was fired within N hours."""
    row = conn.execute(
        """SELECT id FROM alerts
           WHERE category = ? AND indicator = ? AND message LIKE ?
           AND triggered_at > datetime('now', ?)
           LIMIT 1""",
        (category, indicator, f"%[{flag}]%", f"-{within_hours} hours"),
    ).fetchone()
    return row is not None


# ── Main evaluation ──────────────────────────────────────────────────────────


def evaluate_alerts(
    composite_result: dict[str, Any],
    indicators: dict[str, Any],
    gold_ma_200: float | None = None,
) -> list[dict[str, Any]]:
    """Evaluate all indicators and return alert dicts for new transitions.

    Only fires when an indicator transitions to a higher-severity flag
    (NORMAL→BREACHED or BREACHED→CRITICAL). 24h cooldown prevents
    duplicate alerts for the same category+indicator+flag.

    Args:
        composite_result: Output from score_composite() containing
            per_indicator_scores and indicator_details.
        indicators: Raw indicator dict (name → value pairs).
        gold_ma_200: 200-day gold MA for enriched gold alert messages.

    Returns:
        List of alert dicts: {category, indicator, message}.
        Caller is responsible for writing to the alerts table.
    """
    per_indicator_scores: dict[str, float] = composite_result.get("per_indicator_scores", {})
    indicator_details: dict[str, dict[str, Any]] = composite_result.get("indicator_details", {})

    if not per_indicator_scores:
        logger.warning("No per_indicator_scores in composite result — nothing to alert on")
        return []

    conn = get_db()
    alerts_to_insert: list[dict[str, Any]] = []

    try:
        for slug, raw_score in per_indicator_scores.items():
            details = indicator_details.get(slug, {})
            current_flag = determine_flag(raw_score)
            previous_flag = _get_previous_flag(conn, slug)

            # Determine if we should fire
            should_fire = False
            if previous_flag is None:
                # First run — fire for any non-NORMAL indicator
                if current_flag != "NORMAL":
                    should_fire = True
            else:
                current_sev = _flag_severity(current_flag)
                previous_sev = _flag_severity(previous_flag)
                if current_sev > previous_sev:
                    should_fire = True

            if not should_fire:
                continue

            # Cooldown check
            category = details.get("category", "unknown")
            if _is_duplicate(conn, category, slug, current_flag):
                logger.debug("Cooldown: skipping %s/%s/%s", category, slug, current_flag)
                continue

            # Get raw value for formatting
            raw_value = indicators.get(slug)
            # Try legacy keys
            if raw_value is None:
                from src.agent.composite_scorer_v2 import LEGACY_SLUG_MAP
                for legacy_key, mapped_slug in LEGACY_SLUG_MAP.items():
                    if mapped_slug == slug and legacy_key in indicators:
                        raw_value = indicators[legacy_key]
                        break

            message = format_alert_message(
                slug=slug,
                indicator_details=details,
                flag=current_flag,
                raw_score=raw_score,
                raw_value=raw_value,
                gold_ma_200=gold_ma_200,
            )

            alerts_to_insert.append({
                "category": category,
                "indicator": slug,
                "message": message,
            })

            logger.info(
                "Alert: %s transition %s→%s — %s",
                slug,
                previous_flag or "NONE",
                current_flag,
                message,
            )
    finally:
        conn.close()

    return alerts_to_insert


def insert_alerts(alerts: list[dict[str, Any]]) -> int:
    """Insert alert rows into the alerts table.

    Returns the number of rows inserted.
    """
    if not alerts:
        return 0

    conn = get_db()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    inserted = 0
    try:
        for alert in alerts:
            conn.execute(
                """INSERT INTO alerts (category, indicator, message, triggered_at, acknowledged)
                   VALUES (?, ?, ?, ?, 0)""",
                (alert["category"], alert["indicator"], alert["message"], now),
            )
            inserted += 1
        conn.commit()
        logger.info("Inserted %d alert rows", inserted)
    except Exception:
        logger.exception("Failed to insert alerts")
        conn.rollback()
        raise
    finally:
        conn.close()

    return inserted


# ── Integration helper ───────────────────────────────────────────────────────


def run_alerts(
    composite_result: dict[str, Any],
    indicators: dict[str, Any],
    gold_ma_200: float | None = None,
) -> int:
    """Evaluate + insert alerts in one call. Returns count of alerts inserted.

    This is the main integration point for pipeline graph nodes.
    """
    alerts = evaluate_alerts(composite_result, indicators, gold_ma_200=gold_ma_200)
    return insert_alerts(alerts)
