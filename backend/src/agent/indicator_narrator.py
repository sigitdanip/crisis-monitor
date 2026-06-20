"""
Indicator Narrator — generates LLM-friendly natural language context for each indicator.

Replaces raw JSON dicts in agent prompts with concise, data-dense narrative strings.
One line per indicator: value + trend + trigger proximity + status.

ponytail: simple string formatting, no NLP. LLMs are better at consuming structured
natural language than raw JSON — this is a formatting layer, not an intelligence layer.
"""

from typing import Dict, Any, Optional


# ── Indicator metadata registry ──────────────────────────────────────────
# slug → {name, category, unit, trigger_desc, higher_is_worse, source}

INDICATOR_META: Dict[str, Dict[str, Any]] = {
    # Energy
    "brent_price":       {"name": "Brent Crude",      "category": "Energy",        "unit": "USD/bbl",   "trigger": ">100",   "higher_is_worse": True,  "source": "yfinance (BZ=F)"},
    "wti_price":         {"name": "WTI Crude",        "category": "Energy",        "unit": "USD/bbl",   "trigger": ">95",    "higher_is_worse": True,  "source": "yfinance (CL=F)"},
    "natgas_price":      {"name": "Natural Gas",      "category": "Energy",        "unit": "USD/MMBtu", "trigger": ">5",     "higher_is_worse": True,  "source": "yfinance (NG=F)"},
    # Financial
    "dxy":               {"name": "DXY",              "category": "Financial",     "unit": "index",     "trigger": "<95",    "higher_is_worse": False, "source": "yfinance (DX-Y.NYB)"},
    "gold_price":        {"name": "Gold",             "category": "Financial",     "unit": "USD/oz",    "trigger": ">3500",  "higher_is_worse": True,  "source": "yfinance (GC=F)"},
    "us_10y":            {"name": "US 10Y Yield",     "category": "Financial",     "unit": "%",         "trigger": ">5.5",   "higher_is_worse": True,  "source": "yfinance (^TNX)"},
    "us_2y":             {"name": "US 2Y Yield",      "category": "Financial",     "unit": "%",         "trigger": "inversion", "higher_is_worse": True, "source": "yfinance (2YY=F)"},
    "vix":               {"name": "VIX",              "category": "Financial",     "unit": "index",     "trigger": ">35",    "higher_is_worse": True,  "source": "CBOE / Yahoo (^VIX)"},
    # Credit
    "ig_oas":            {"name": "IG OAS",           "category": "Credit",        "unit": "bps",       "trigger": ">200",   "higher_is_worse": True,  "source": "FRED (BAMLC0A0CM)"},
    "hy_oas":            {"name": "HY OAS",           "category": "Credit",        "unit": "bps",       "trigger": ">600",   "higher_is_worse": True,  "source": "FRED (BAMLH0A0HYM2)"},
    # Food
    "fao_monthly_change_pct": {"name": "FAO FPI Change", "category": "Food",      "unit": "% MoM",     "trigger": ">10%",   "higher_is_worse": True,  "source": "FAO Food Price Index CSV"},
    "cme_grains_monthly_pct": {"name": "CME Grains Change","category": "Food",     "unit": "% MoM",     "trigger": ">10%",   "higher_is_worse": True,  "source": "yfinance (ZC=F, ZS=F, ZW=F)"},
    # China
    "caixin_pmi":        {"name": "Caixin PMI",       "category": "China",         "unit": "index",     "trigger": "<48",    "higher_is_worse": False, "source": "TradingEconomics / Caixin"},
    # Debt
    "btp_bund_spread":   {"name": "BTP-Bund Spread",  "category": "Debt",          "unit": "bps",       "trigger": ">250",   "higher_is_worse": True,  "source": "FRED / TradingEconomics"},
    # Energy storage
    "eu_gas_storage_pct":{"name": "EU Gas Storage",   "category": "Energy",        "unit": "%",         "trigger": "<60",    "higher_is_worse": False, "source": "GIE AGSI (agsi.gie.eu)"},
    "us_spr_mbbl":       {"name": "US SPR",           "category": "Energy",        "unit": "Mbbl",      "trigger": "<350",   "higher_is_worse": False, "source": "EIA Weekly Report"},
    # EM currencies (breach flags)
    "idr_breach":        {"name": "IDR Breach",       "category": "EM Currency",   "unit": "flag",      "trigger": ">16500", "higher_is_worse": True,  "source": "yfinance / Xe.com / OANDA"},
    "try_breach":        {"name": "TRY Breach",       "category": "EM Currency",   "unit": "flag",      "trigger": ">35",    "higher_is_worse": True,  "source": "yfinance / Xe.com / OANDA"},
    "egp_breach":        {"name": "EGP Breach",       "category": "EM Currency",   "unit": "flag",      "trigger": ">50",    "higher_is_worse": True,  "source": "yfinance / Xe.com / OANDA"},
    # Geopolitical (flags)
    "nato_fracture":     {"name": "NATO Fracture",    "category": "Geopolitical",  "unit": "flag",      "trigger": "≥1",     "higher_is_worse": True,  "source": "News + LLM assessment"},
    "us_nato_withdrawal":{"name": "US NATO Withdrawal","category": "Geopolitical", "unit": "flag",      "trigger": "≥1",     "higher_is_worse": True,  "source": "DoD announcements + News"},
    "cds_doubling":      {"name": "CDS Doubling",     "category": "Debt",          "unit": "flag",      "trigger": "≥1",     "higher_is_worse": True,  "source": "Investing.com / WorldGovernmentBonds"},
    "protest_countries": {"name": "Protest Countries","category": "Political",     "unit": "count",     "trigger": "≥2",     "higher_is_worse": True,  "source": "ACLED API / GDELT"},
    "govt_crisis":       {"name": "Govt Crisis",      "category": "Political",     "unit": "flag",      "trigger": "≥1",     "higher_is_worse": True,  "source": "ACLED / News + LLM"},
    "china_property_default": {"name": "China Property Default","category": "China","unit": "flag",     "trigger": "≥1",     "higher_is_worse": True,  "source": "News + LLM"},
    "hormuz_closure":    {"name": "Hormuz Closure",   "category": "Geopolitical",  "unit": "status",    "trigger": "closed", "higher_is_worse": True,  "source": "News + LLM (MarineTraffic/Kpler)"},
    # News-derived flag indicators (unit='flag', source='newsapi')
    "news_caixin_pmi":   {"name": "Caixin PMI (News)","category": "China",         "unit": "flag",      "trigger": "≥1",     "higher_is_worse": True,  "source": "newsapi"},
    "news_eu_gas":       {"name": "EU Gas Storage (News)","category": "Energy",    "unit": "flag",      "trigger": "≥1",     "higher_is_worse": True,  "source": "newsapi"},
    "news_us_spr":       {"name": "US SPR (News)",    "category": "Energy",        "unit": "flag",      "trigger": "≥1",     "higher_is_worse": True,  "source": "newsapi"},
    "news_protest_countries": {"name": "Protest Countries (News)","category": "Political","unit": "flag","trigger": "≥1","higher_is_worse": True, "source": "newsapi"},
}


def _parse_trigger_value(trigger_str: str) -> float | None:
    """Parse the numeric portion of a trigger string, stripping % and other suffixes."""
    if not trigger_str:
        return None
    raw = trigger_str[1:].strip() if trigger_str[0] in (">", "<", "≥") else trigger_str.strip()
    # Strip common suffixes
    for suffix in ("%", "bps", "MoM", "YoY"):
        if raw.endswith(suffix):
            raw = raw[:-len(suffix)].strip()
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None


def _is_news_flag(value) -> bool:
    """Return True if the value is a news-derived flag dict with {value, narrative}."""
    return isinstance(value, dict) and "value" in value and "narrative" in value


def _extract_scalar(value):
    """Extract the scalar value from a potentially nested news-flag dict.

    Returns the scalar (int, float, str, None) for all value types —
    plain scalars pass through unchanged, news-flag dicts return value['value'].
    """
    if _is_news_flag(value):
        return value["value"]
    return value


def _assess(value, meta: dict) -> str:
    """Return one-word assessment for frontend display.

    Returns lowercase statuses compatible with the frontend STATUS_COLORS:
      normal | elevated | critical | breached | unknown

    ponytail: trigger direction (>/</≥) is the source of truth — it already
    encodes whether exceeding or falling below the threshold is bad.
    """
    # Unwrap news-flag dict to get the scalar for assessment
    scalar = _extract_scalar(value)
    if scalar is None:
        return "unknown"
    trigger_str = meta.get("trigger", "")

    # Flag indicators: 0 = normal, 1+ = breached
    if meta.get("unit") == "flag":
        return "breached" if scalar else "normal"

    # String values (e.g. hormuz_closure)
    if isinstance(scalar, str):
        if not scalar:
            return "unknown"
        return "critical" if scalar.lower() == "closed" else "normal"

    # Numeric with trigger parsing
    threshold = _parse_trigger_value(trigger_str)
    if threshold is not None and isinstance(scalar, (int, float)):
        try:
            op = trigger_str[0] if trigger_str else ""
            if op == ">":
                return "critical" if scalar > threshold else "normal"
            elif op == "<":
                return "critical" if scalar < threshold else "normal"
            elif op == "≥":
                return "breached" if scalar >= threshold else "normal"
        except (ValueError, TypeError):
            pass

    return "normal"  # default when trigger can't be parsed 


def _trend_arrow(change) -> str:
    """↑ ↓ → for numeric change."""
    if change is None:
        return "→"
    if change > 0:
        return "↑"
    if change < 0:
        return "↓"
    return "→"


def narrate_one(slug: str, value, prev_value=None, meta_override: dict = None) -> str:
    """Narrate a single indicator in one line.

    Format for numeric:  Name = value unit (STATUS). Trigger: trigger_desc. Trend: arrow.
    Format for news flag: Name (news): narrative. Trigger: trigger_desc.
    Example: Brent Crude = $98.40/bbl (ELEVATED). Trigger: >100. Trend: ↑

    Args:
        slug: Indicator slug (key in INDICATOR_META).
        value: Current value, or news-flag dict {value, narrative}.
        prev_value: Previous value for trend direction.
        meta_override: Optional metadata override (for indicators not in registry).

    Returns:
        One-line narrative string.
    """
    meta = meta_override or INDICATOR_META.get(slug)
    if meta is None:
        return f"{slug}: {value} (no metadata)"

    name = meta["name"]
    unit = meta["unit"]
    status = _assess(value, meta)
    trigger = meta.get("trigger", "N/A")

    # News-derived flag: show narrative instead of numeric value
    if _is_news_flag(value):
        narrative = value.get("narrative") or "(no news)"
        narrative_short = narrative[:200]  # enforce 200-char cap per CHECKLIST.md
        return f"{name} (news): {narrative_short}. Trigger: {trigger}."

    # Compute trend if prev_value available
    scalar = _extract_scalar(value)
    trend = ""
    if prev_value is not None and isinstance(scalar, (int, float)) and isinstance(prev_value, (int, float)):
        change = scalar - prev_value
        trend = f" Change: {change:+.2f} {_trend_arrow(change)}."

    # Format value
    if isinstance(scalar, float):
        val_str = f"{scalar:.1f}"
    elif scalar is None:
        val_str = "N/A"
    elif isinstance(scalar, int):
        val_str = str(scalar)
    else:
        val_str = str(scalar)

    return f"{name} = {val_str} {unit} (status: {status}). Trigger: {trigger}.{trend}"


def narrate_all(indicators: Dict[str, Any], prev_indicators: Dict[str, Any] = None) -> str:
    """Narrate all indicators, grouped by category.

    Args:
        indicators: Flat dict of slug → value. Keys must match INDICATOR_META slugs.
        prev_indicators: Optional dict of previous values for trend computation.

    Returns:
        Formatted multi-line string with category headers.
    """
    if not indicators:
        return "(no indicator data)"

    prev = prev_indicators or {}

    # Group by category
    by_category: Dict[str, list] = {}
    for slug, value in indicators.items():
        meta = INDICATOR_META.get(slug)
        cat = meta["category"] if meta else "Other"
        by_category.setdefault(cat, []).append((slug, value))

    lines = []
    for cat in sorted(by_category):
        lines.append(f"## {cat}")
        for slug, value in by_category[cat]:
            prev_val = prev.get(slug) if prev else None
            lines.append(narrate_one(slug, value, prev_val))
        lines.append("")

    return "\n".join(lines)


def narrate_for_dots(indicators: Dict[str, Any], dot_slugs: list,
                     prev_indicators: Dict[str, Any] = None) -> str:
    """Narrate only indicators relevant to specific dots.

    Args:
        indicators: Flat dict of slug → value.
        dot_slugs: List of indicator slugs relevant to these dots.
        prev_indicators: Optional previous values.

    Returns:
        Formatted string with only the relevant indicators.
    """
    prev = prev_indicators or {}
    lines = []
    for slug in dot_slugs:
        if slug in indicators:
            value = indicators[slug]
            prev_val = prev.get(slug)
            lines.append(narrate_one(slug, value, prev_val))
    if not lines:
        return "(no relevant indicator data)"
    return "\n".join(lines)


# ── LLM Narration ────────────────────────────────────────────────────────
# ponytail: LLM call adds ~30s per pipeline run, batched in one API call.
# Falls back to empty dict on failure — downstream nodes unaffected.

NARRATOR_PROMPT = """You are a financial/geopolitical analyst writing brief context for crisis indicators.

For each indicator below, write ONE short sentence (max 20 words) explaining what the current value means in plain language. Focus on implications, not just description.

Each indicator is listed as: slug: display_name: value unit (STATUS). Trigger: threshold.
Use the SLUG (e.g. 'brent_price', 'vix', 'caixin_pmi') as the JSON key.

Indicators:
{indicators_text}

Return ONLY a JSON object mapping indicator slug to context string:
{{"brent_price": "context sentence", "vix": "context sentence", ...}}"""


async def generate_indicator_narratives(indicators: Dict[str, Any]) -> Dict[str, str]:
    """Generate 1-sentence plain-language narratives for each indicator via LLM.

    Args:
        indicators: Flat dict of indicator_slug -> value. Keys should match INDICATOR_META.

    Returns:
        Dict of indicator_slug -> narrative string. Empty dict on LLM failure.
    """
    if not indicators:
        return {}

    # Build context lines using existing narrate_one for structured input
    lines = []
    for slug, value in indicators.items():
        if isinstance(value, (int, float)):
            line = narrate_one(slug, value)
            lines.append(f"  {slug}: {line}")
        elif isinstance(value, str) and value:
            line = narrate_one(slug, value)
            lines.append(f"  {slug}: {line}")
        elif isinstance(value, dict) and "value" in value and "narrative" in value:
            # News-derived flag indicator — narrate_one already handles the dict format
            line = narrate_one(slug, value)
            lines.append(f"  {slug}: {line}")

    if not lines:
        return {}

    indicators_text = "\n".join(lines[:50])  # limit to 50 indicators per call

    try:
        from src.agent.llm import get_llm, extract_json, get_llm_content
        llm = get_llm(temperature=0.4)
        prompt = NARRATOR_PROMPT.replace("{indicators_text}", indicators_text)
        response = await llm.ainvoke(prompt)
        result = extract_json(get_llm_content(response))
        return result if isinstance(result, dict) else {}
    except Exception:
        return {}  # graceful degradation


# ── Source Attribution ───────────────────────────────────────────────────

# Dot → indicator slug mapping (which indicators inform each dot)
DOT_INDICATORS: Dict[str, list] = {
    "dot_1": ["nato_fracture", "us_nato_withdrawal", "dxy"],
    "dot_2": ["brent_price", "wti_price", "natgas_price", "eu_gas_storage_pct", "us_spr_mbbl", "hormuz_closure", "news_eu_gas", "news_us_spr"],
    "dot_3": ["fao_monthly_change_pct", "cme_grains_monthly_pct"],
    "dot_4": ["ig_oas", "hy_oas", "vix", "us_10y", "us_2y"],
    "dot_5": ["btp_bund_spread", "cds_doubling"],
    "dot_6": ["caixin_pmi", "china_property_default", "news_caixin_pmi"],
    "dot_7": ["protest_countries", "govt_crisis", "news_protest_countries"],
    "dot_8": ["brent_price", "hormuz_closure"],  # proxy: energy + trade chokepoints
    "dot_9": [],  # health — sourced from WHO + News (no numeric indicators in this pipeline)
    "em_currency": ["idr_breach", "try_breach", "egp_breach"],
}


def sources_for_dot(dot_key: str, indicators: Dict[str, Any]) -> str:
    """Return a summary of data sources that inform a specific dot.

    Maps dot keys ("dot_1" through "dot_9", "em_currency") to their
    relevant indicator slugs and yields a compact source attribution string.

    Args:
        dot_key: Dot identifier (e.g., "dot_1", "dot_4", "em_currency").
        indicators: Flat dict of slug → value for currently available data.

    Returns:
        Multi-line string listing indicator name, value, status, and source.
    """
    slugs = DOT_INDICATORS.get(dot_key, [])
    if not slugs:
        return f"  {dot_key}: no numeric indicator sources (news/LLM-driven)"

    lines = []
    for slug in slugs:
        meta = INDICATOR_META.get(slug, {})
        value = indicators.get(slug)
        status = _assess(value, meta) if value is not None else "UNKNOWN"
        source = meta.get("source", "unknown")
        name = meta.get("name", slug)
        if _is_news_flag(value):
            # News-derived flag: show narrative instead of numeric value
            narrative = value.get("narrative", "(no news)")
            narrative_short = narrative[:200]
            val_str = narrative_short
        elif isinstance(value, float):
            val_str = f"{value:.2f}"
        elif value is not None:
            val_str = str(value)
        else:
            val_str = "N/A"
        lines.append(f"  {name} = {val_str} ({status}) — {source}")

    return "\n".join(lines)


def sources_narrative(indicators: Dict[str, Any], dot_keys: list) -> str:
    """Generate a source attribution narrative for a set of dots.

    Used to inject into LLM prompts so the model can cite specific data sources
    in its output.

    Args:
        indicators: Flat dict of slug → value.
        dot_keys: List of dot keys to include (e.g., ["dot_1", "dot_2"]).

    Returns:
        Formatted multi-line string with source attributions grouped by dot.
    """
    lines = ["## Data Sources by Dot"]
    for dk in dot_keys:
        lines.append(f"\n### {dk}:")
        lines.append(sources_for_dot(dk, indicators))
    return "\n".join(lines)


def sources_list_for_dot(dot_key: str, indicators: Dict[str, Any]) -> list:
    """Return a structured list of source entries for a dot.

    Used to populate the `sources` field in dot analysis output.

    Args:
        dot_key: Dot identifier.
        indicators: Flat dict of slug → value.

    Returns:
        List of dicts with {indicator, value, status, source}.
    """
    slugs = DOT_INDICATORS.get(dot_key, [])
    result = []
    for slug in slugs:
        meta = INDICATOR_META.get(slug, {})
        value = indicators.get(slug)
        entry = {
            "indicator": meta.get("name", slug),
            "slug": slug,
            "source": meta.get("source", "unknown"),
        }
        if value is not None:
            entry["value"] = _extract_scalar(value)
            entry["status"] = _assess(value, meta)
            if _is_news_flag(value):
                entry["narrative"] = value["narrative"]
        result.append(entry)
    return result


# ── Self-check ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_indicators = {
        "brent_price": 98.40,
        "wti_price": 87.50,
        "vix": 22.3,
        "ig_oas": 180.0,
        "hy_oas": 450.0,
        "caixin_pmi": 47.5,
        "idr_breach": 0,
        "try_breach": 1,
        "nato_fracture": 1,
        "hormuz_closure": "",
        "protest_countries": 3,
        "govt_crisis": 1,
    }
    prev = {"brent_price": 95.10, "vix": 20.1}

    # Single indicator
    print("--- Single ---")
    print(narrate_one("brent_price", 98.40, 95.10))

    # Flag indicator
    print(narrate_one("try_breach", 1))

    # All indicators grouped
    print("\n--- All ---")
    print(narrate_all(test_indicators, prev))

    # Filtered for specific dots
    print("--- Dot 4 (Credit) ---")
    print(narrate_for_dots(test_indicators, ["ig_oas", "hy_oas", "vix"]))

    # Source attribution
    print("\n--- Source Attribution ---")
    print(sources_for_dot("dot_4", test_indicators))
    print("\n--- Sources Narrative ---")
    print(sources_narrative(test_indicators, ["dot_1", "dot_2"]))
    print("\n--- Sources List ---")
    for s in sources_list_for_dot("dot_4", test_indicators):
        print(f"  {s}")

    # Verify all known slugs have metadata
    missing = [s for s in test_indicators if s not in INDICATOR_META]
    assert not missing, f"Missing metadata for: {missing}"

    # Verify assessment logic (lowercase for frontend compatibility)
    assert _assess(98.40, INDICATOR_META["brent_price"]) == "normal"  # 98.40 < 100
    assert _assess(115, INDICATOR_META["brent_price"]) == "critical"  # 115 > 100
    assert _assess(47.5, INDICATOR_META["caixin_pmi"]) == "critical"  # 47.5 < 48
    assert _assess(1, INDICATOR_META["try_breach"]) == "breached"
    assert _assess(0, INDICATOR_META["try_breach"]) == "normal"
    # Percentage trigger parsing
    assert _assess(5.1, INDICATOR_META["fao_monthly_change_pct"]) == "normal"  # 5.1 < 10
    assert _assess(12.0, INDICATOR_META["fao_monthly_change_pct"]) == "critical"  # 12 > 10
    # Empty string / None
    assert _assess(None, INDICATOR_META["brent_price"]) == "unknown"
    assert _assess("", INDICATOR_META["hormuz_closure"]) == "unknown"

    # Verify source metadata on all pipeline slugs
    pipeline_slugs = [s for s in INDICATOR_META]
    for slug in pipeline_slugs:
        assert "source" in INDICATOR_META[slug], f"Missing source for {slug}"

    # Verify DOT_INDICATORS maps exist for all dot keys
    expected_dots = ["dot_1", "dot_2", "dot_3", "dot_4", "dot_5", "dot_6", "dot_7", "dot_8", "dot_9", "em_currency"]
    for dk in expected_dots:
        assert dk in DOT_INDICATORS, f"Missing DOT_INDICATORS entry for {dk}"

    # Verify sources_list_for_dot returns structured data
    src_list = sources_list_for_dot("dot_4", test_indicators)
    assert isinstance(src_list, list) and len(src_list) > 0
    for entry in src_list:
        assert "indicator" in entry
        assert "source" in entry

    print("\nAll checks passed.")
