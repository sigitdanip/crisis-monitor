"""Dot Analyzer LLM Agents — 5 specialized agents for crisis dot analysis.

Agents 1-5 analyze their assigned dots using indicators + composite score + news.
Each returns a structured dict with status, summary, key_signals, and sources.

sources is a brief paragraph (max 100 words) citing specific indicators,
news headlines, and data points that informed the assessment.
"""
import json
import logging
from typing import Dict, Any, List
from src.agent.llm import get_llm, extract_json, get_llm_content
from src.agent.indicator_narrator import narrate_all, sources_narrative, sources_for_dot

logger = logging.getLogger(__name__)

# ============================================================
# Agent 1: GEOPOLITICAL — Dots 1 (NATO) + 2 (Hormuz/Energy)
# ============================================================

AGENT1_PROMPT = """You are a geopolitical risk analyst specializing in NATO alliance stability and global energy security.

Analyze the following indicators and news for Dot 1 (NATO Alliance Cohesion) and Dot 2 (Strait of Hormuz / Energy Security).

INDICATORS:
{indicators_narrative}

COMPOSITE SCORE: {composite}/16 ({interpretation})

DATA SOURCES:
{sources_narrative}

NEWS HEADLINES:
{news_json}

Return a JSON object with this exact structure:
{{
  "dot_1": {{
    "status": "dormant|activating|active|critical",
    "summary": "2-3 sentence assessment of NATO alliance state",
    "key_signals": ["signal 1", "signal 2", "signal 3"],
    "nato_outlook": "unified|fracturing|withdrawing",
    "nato_confidence": 0.0-1.0,
    "sources": "1-2 sentence paragraph citing which specific indicators (by name and value), news headlines, and data origins most informed this NATO assessment. Reference the DATA SOURCES section. Max 100 words."
  }},
  "dot_2": {{
    "status": "dormant|activating|active|critical",
    "summary": "2-3 sentence energy security assessment",
    "key_signals": ["signal 1", "signal 2"],
    "hormuz_risk": "low|elevated|high|closed",
    "energy_price_outlook": "stable|rising|spiking",
    "sources": "1-2 sentence paragraph citing which specific indicators (by name and value), news headlines, and data origins most informed this energy security assessment. Reference the DATA SOURCES section. Max 100 words."
  }}
}}

Rules:
- status: "dormant" if no concerning signals, "activating" if early warnings, "active" if clear danger, "critical" if crisis unfolding
- Be specific with numbers and dates from the indicators
- sources: write a concise paragraph naming the specific indicators, their current values, and data origins that most drove your assessment. Cite news headlines by topic when they influenced the judgment.
- Only use information present in the data provided"""


async def analyze_geopolitical(
    indicators: Dict[str, Any],
    composite: Dict[str, Any],
    news: List[Dict[str, str]] | None = None,
) -> Dict[str, Any]:
    """Agent 1: Geopolitical — Dots 1 (NATO) + 2 (Hormuz/Energy)."""
    llm = get_llm(temperature=0.3)
    prompt = AGENT1_PROMPT.format(
        indicators_narrative=narrate_all(indicators),
        composite=composite["composite"],
        interpretation=composite["interpretation"],
        sources_narrative=sources_narrative(indicators, ["dot_1", "dot_2"]),
        news_json=json.dumps(news or [], indent=2),
    )
    resp = await llm.ainvoke(prompt)
    result = extract_json(get_llm_content(resp))
    return result if result else _fallback("geopolitical", indicators)


# ============================================================
# Agent 2: FOOD & DEBT — Dots 3 (Food/Fertilizer) + 5 (Sovereign Debt)
# ============================================================

AGENT2_PROMPT = """You are a food security and sovereign debt analyst.

Analyze the following indicators and news for Dot 3 (Food & Fertilizer Crisis) and Dot 5 (Sovereign Debt Stress).

INDICATORS:
{indicators_narrative}

COMPOSITE SCORE: {composite}/16 ({interpretation})

DATA SOURCES:
{sources_narrative}

NEWS HEADLINES:
{news_json}

Return a JSON object with this exact structure:
{{
  "dot_3": {{
    "status": "dormant|activating|active|critical",
    "summary": "2-3 sentence food/fertilizer assessment",
    "key_signals": ["signal 1", "signal 2", "signal 3"],
    "fao_trend": "falling|stable|rising|spiking",
    "grain_price_risk": "low|elevated|high",
    "sources": "1-2 sentence paragraph citing which specific indicators (by name and value), news headlines, and data origins most informed this food security assessment. Reference the DATA SOURCES section. Max 100 words."
  }},
  "dot_5": {{
    "status": "dormant|activating|active|critical",
    "summary": "2-3 sentence sovereign debt assessment",
    "key_signals": ["signal 1", "signal 2", "signal 3"],
    "most_vulnerable": "country name or 'none'",
    "contagion_risk": "low|moderate|high",
    "sources": "1-2 sentence paragraph citing which specific indicators (by name and value), news headlines, and data origins most informed this sovereign debt assessment. Reference the DATA SOURCES section. Max 100 words."
  }}
}}

Rules:
- Dot 3 status: "critical" if FAO spiking AND grains surging; "active" if either
- Dot 5 status: "critical" if CDS doubling in any G20; "active" if BTP-Bund > 300 or JGB > 2.5%
- sources: write a concise paragraph naming the specific indicators, their current values, and data origins that most drove your assessment. Cite news headlines by topic when they influenced the judgment.
- Indicators with numeric values and a status (e.g. "status: normal") have live data — never call them unavailable/N/A.
- Only use information present in the data provided"""


async def analyze_food_debt(
    indicators: Dict[str, Any],
    composite: Dict[str, Any],
    news: List[Dict[str, str]] | None = None,
) -> Dict[str, Any]:
    """Agent 2: Food & Debt — Dots 3 (Food) + 5 (Sovereign Debt)."""
    llm = get_llm(temperature=0.3)
    prompt = AGENT2_PROMPT.format(
        indicators_narrative=narrate_all(indicators),
        composite=composite["composite"],
        interpretation=composite["interpretation"],
        sources_narrative=sources_narrative(indicators, ["dot_3", "dot_5"]),
        news_json=json.dumps(news or [], indent=2),
    )
    resp = await llm.ainvoke(prompt)
    content = get_llm_content(resp)
    result = extract_json(content)
    if not result:
        logger.warning("Agent 2 (food_debt) extract_json failed on %d chars: %.300s", len(content), content)
        return _fallback("food_debt", indicators)
    return result


# ============================================================
# Agent 3: FINANCIAL & EM — Dot 4 (Credit/Financial) + EM Currency stress
# ============================================================

AGENT3_PROMPT = """You are a financial markets and emerging markets analyst.

Analyze the following indicators for Dot 4 (Financial/Credit Stress) and EM Currency stability.

INDICATORS:
{indicators_narrative}

COMPOSITE SCORE: {composite}/16 ({interpretation})

DATA SOURCES:
{sources_narrative}

NEWS HEADLINES:
{news_json}

Return a JSON object with this exact structure:
{{
  "dot_4": {{
    "status": "dormant|activating|active|critical",
    "summary": "2-3 sentence credit market assessment",
    "key_signals": ["signal 1", "signal 2", "signal 3"],
    "credit_spread_outlook": "tightening|stable|widening|stressed",
    "volatility_regime": "low|elevated|high|crisis",
    "sources": "1-2 sentence paragraph citing which specific indicators (by name and value), news headlines, and data origins most informed this credit market assessment. Reference the DATA SOURCES section. Max 100 words."
  }},
  "em_currency": {{
    "status": "dormant|activating|active|critical",
    "summary": "2-3 sentence EM currency assessment",
    "key_signals": ["signal 1", "signal 2", "signal 3"],
    "currencies_under_pressure": ["list", "of", "currency", "codes"],
    "contagion_risk": "low|moderate|high",
    "sources": "1-2 sentence paragraph citing which specific indicators (by name and value), news headlines, and data origins most informed this EM currency assessment. Reference the DATA SOURCES section. Max 100 words."
  }}
}}

Rules:
- Dot 4 status: "critical" if IG > 200 AND HY > 600; "active" if either; "activating" if VIX > 35 or MOVE > 140
- EM status: "critical" if 3+ currencies breaching; "active" if 1-2 breaching
- Use VIX, MOVE, VVIX, SOFR-OIS, cross-currency basis for credit assessment
- sources: write a concise paragraph naming the specific indicators, their current values, and data origins that most drove your assessment. Cite news headlines by topic when they influenced the judgment.
- Indicators with numeric values and a status (e.g. "status: normal") have live data — never call them unavailable/N/A.
- Only use information present in the data provided"""


async def analyze_financial_em(
    indicators: Dict[str, Any],
    composite: Dict[str, Any],
    news: List[Dict[str, str]] | None = None,
) -> Dict[str, Any]:
    """Agent 3: Financial & EM — Dot 4 (Credit) + EM Currency stress."""
    llm = get_llm(temperature=0.3)
    prompt = AGENT3_PROMPT.format(
        indicators_narrative=narrate_all(indicators),
        composite=composite["composite"],
        interpretation=composite["interpretation"],
        sources_narrative=sources_narrative(indicators, ["dot_4", "em_currency"]),
        news_json=json.dumps(news or [], indent=2),
    )
    resp = await llm.ainvoke(prompt)
    content = get_llm_content(resp)
    result = extract_json(content)
    if not result:
        logger.warning("Agent 3 (financial_em) extract_json failed on %d chars: %.300s", len(content), content)
        return _fallback("financial_em", indicators)
    return result


# ============================================================
# Agent 4: CHINA & POLITICAL — Dots 6 (China) + 7 (Political) + 8 (Supply Chain)
# ============================================================

AGENT4_PROMPT = """You are a China economy and global political risk analyst.

Analyze the following indicators for Dot 6 (China Economic Stress), Dot 7 (Political/Social Unrest), and Dot 8 (Supply Chain Disruption).

INDICATORS:
{indicators_narrative}

COMPOSITE SCORE: {composite}/16 ({interpretation})

DATA SOURCES:
{sources_narrative}

NEWS HEADLINES:
{news_json}

Return a JSON object with this exact structure:
{{
  "dot_6": {{
    "status": "dormant|activating|active|critical",
    "summary": "2-3 sentence China economic assessment",
    "key_signals": ["signal 1", "signal 2", "signal 3"],
    "pmi_outlook": "expanding|contracting|recession",
    "property_sector_risk": "low|elevated|high|crisis",
    "sources": "1-2 sentence paragraph citing which specific indicators (by name and value), news headlines, and data origins most informed this China economic assessment. Reference the DATA SOURCES section. Max 100 words."
  }},
  "dot_7": {{
    "status": "dormant|activating|active|critical",
    "summary": "2-3 sentence political/social unrest assessment",
    "key_signals": ["signal 1", "signal 2", "signal 3"],
    "protest_scale": "isolated|rising|widespread",
    "government_stability": "stable|pressured|fragile",
    "sources": "1-2 sentence paragraph citing which specific indicators (by name and value), news headlines, and data origins most informed this political risk assessment. Reference the DATA SOURCES section. Max 100 words."
  }},
  "dot_8": {{
    "status": "dormant|activating|active|critical",
    "summary": "2-3 sentence supply chain assessment",
    "key_signals": ["signal 1", "signal 2"],
    "shipping_risk": "low|elevated|high|disrupted",
    "trade_chokepoint_status": "open|restricted|closed",
    "sources": "1-2 sentence paragraph citing which specific indicators (by name and value), news headlines, and data origins most informed this supply chain assessment. Reference the DATA SOURCES section. Max 100 words."
  }}
}}

Rules:
- Dot 6 status: "critical" if Caixin < 48 AND property default; "active" if Caixin < 50
- Dot 7 status: "critical" if 3+ countries protests + govt crisis; "active" if 2+ countries
- Dot 8 status: "critical" if Suez closed OR BDI < 1000; "active" if FBX > $5,000 or BDI falling
- sources: write a concise paragraph naming the specific indicators, their current values, and data origins that most drove your assessment. Cite news headlines by topic when they influenced the judgment.
- Only use information present in the data provided"""


async def analyze_china_political(
    indicators: Dict[str, Any],
    composite: Dict[str, Any],
    news: List[Dict[str, str]] | None = None,
) -> Dict[str, Any]:
    """Agent 4: China & Political — Dots 6 (China) + 7 (Political) + 8 (Supply Chain)."""
    llm = get_llm(temperature=0.3)
    prompt = AGENT4_PROMPT.format(
        indicators_narrative=narrate_all(indicators),
        composite=composite["composite"],
        interpretation=composite["interpretation"],
        sources_narrative=sources_narrative(indicators, ["dot_6", "dot_7", "dot_8"]),
        news_json=json.dumps(news or [], indent=2),
    )
    resp = await llm.ainvoke(prompt)
    result = extract_json(get_llm_content(resp))
    return result if result else _fallback("china_political", indicators)


# ============================================================
# Agent 5: HEALTH — Dot 9 (Hantavirus/Pandemic)
# ============================================================

AGENT5_PROMPT = """You are a global health security analyst specializing in emerging infectious diseases.

Analyze the following indicators for Dot 9 (Health Security — Hantavirus & Pandemic Risk).

INDICATORS:
{indicators_narrative}

COMPOSITE SCORE: {composite}/16 ({interpretation})

DATA SOURCES:
{sources_narrative}

NEWS HEADLINES:
{news_json}

Return a JSON object with this exact structure:
{{
  "dot_9": {{
    "status": "dormant|activating|active|critical",
    "summary": "2-3 sentence health security assessment",
    "key_signals": ["signal 1", "signal 2", "signal 3"],
    "who_risk_level": "low|moderate|high|very_high",
    "human_transmission": "none|suspected|confirmed",
    "geographic_spread": "localized|regional|multi_continent",
    "government_response": "none|monitoring|advisory|quarantine",
    "sources": "1-2 sentence paragraph citing which specific indicators (by name and value), news headlines, and data origins most informed this health security assessment. Reference the DATA SOURCES section. Max 100 words."
  }}
}}

Rules:
- status: "critical" if human-to-human confirmed + multi-continent spread
- status: "active" if WHO risk "moderate" or higher
- status: "activating" if sustained case increase
- sources: write a concise paragraph naming the specific indicators, their current values, and data origins that most drove your assessment. Cite news headlines by topic when they influenced the judgment.
- Only use information present in the data provided"""


async def analyze_health(
    indicators: Dict[str, Any],
    composite: Dict[str, Any],
    news: List[Dict[str, str]] | None = None,
) -> Dict[str, Any]:
    """Agent 5: Health — Dot 9 (Hantavirus/Pandemic)."""
    llm = get_llm(temperature=0.3)
    prompt = AGENT5_PROMPT.format(
        indicators_narrative=narrate_all(indicators),
        composite=composite["composite"],
        interpretation=composite["interpretation"],
        sources_narrative=sources_narrative(indicators, ["dot_9"]),
        news_json=json.dumps(news or [], indent=2),
    )
    resp = await llm.ainvoke(prompt)
    result = extract_json(get_llm_content(resp))
    return result if result else _fallback("health", indicators)


# ============================================================
# Fallback — graceful degradation when LLM returns bad JSON
# ============================================================

def _sources_text_for_dot(dot_key: str, indicators: Dict[str, Any]) -> str:
    """Generate a brief plain-language sources paragraph for a dot from indicator metadata.

    Used by the fallback path when the LLM is unavailable — synthesises
    a 1-2 sentence attribution from the indicator registry.
    Returns empty string when no indicators are mapped to the dot.
    """
    from src.agent.indicator_narrator import DOT_INDICATORS, INDICATOR_META, _is_news_flag

    slugs = DOT_INDICATORS.get(dot_key, [])
    if not slugs:
        return ""

    parts = []
    sources_set = set()
    for slug in slugs:
        meta = INDICATOR_META.get(slug, {})
        name = meta.get("name", slug)
        src = meta.get("source", "data feed")
        sources_set.add(src)
        value = indicators.get(slug)
        if _is_news_flag(value):
            # News-derived flag: show narrative instead of numeric value
            narrative = value.get("narrative", "(no news)")
            narrative_short = narrative[:200]
            parts.append(f"{name} (news: {narrative_short})")
        elif value is not None:
            if isinstance(value, float):
                parts.append(f"{name} = {value:.1f}")
            elif isinstance(value, int):
                parts.append(f"{name} = {value}")
            else:
                parts.append(f"{name} = {value}")
        else:
            parts.append(f"{name} (unavailable)")

    if not parts:
        return ""

    sources_str = ", ".join(parts)
    src_list = ", ".join(sorted(sources_set))
    return f"Assessment based on: {sources_str}. Sourced from {src_list}."


def _build_key_signals(dot_key: str, indicators: Dict[str, Any]) -> list:
    """Build meaningful key_signals from real indicator data instead of 'data unavailable'.

    Reads indicator values and metadata to produce a short list of descriptive
    signal strings — one per indicator mapped to the dot.
    """
    from src.agent.indicator_narrator import DOT_INDICATORS, INDICATOR_META, _is_news_flag, _extract_scalar, _assess

    slugs = DOT_INDICATORS.get(dot_key, [])
    if not slugs:
        return ["no indicator data mapped to this dot"]

    signals = []
    for slug in slugs:
        meta = INDICATOR_META.get(slug, {})
        name = meta.get("name", slug)
        value = indicators.get(slug)
        if value is None:
            signals.append(f"{name}: unavailable")
            continue
        if _is_news_flag(value):
            narrative = value.get("narrative", "")[:100]
            signals.append(f"{name}: {narrative}" if narrative else f"{name}: news flag present (no narrative)")
        else:
            scalar = _extract_scalar(value)
            status = _assess(value, meta)
            unit = meta.get("unit", "")
            if isinstance(scalar, float):
                signals.append(f"{name} = {scalar:.1f} {unit} ({status})")
            elif isinstance(scalar, int):
                signals.append(f"{name} = {scalar} {unit} ({status})")
            elif scalar is not None:
                signals.append(f"{name} = {scalar} {unit} ({status})")
            else:
                signals.append(f"{name}: data unavailable")
    return signals


def _fallback(agent_name: str, indicators: Dict[str, Any] = None) -> Dict[str, Any]:
    """Return a safe fallback dict when LLM output can't be parsed.

    sources field is a brief text paragraph derived from indicator metadata;
    empty string when no metadata is available for the dot.
    """
    indicators = indicators or {}
    base = {
        "status": "dormant",
        "summary": f"LLM analysis unavailable for {agent_name} — using fallback",
        "key_signals": ["data unavailable"],
    }

    def build_dot(dot_key: str) -> dict:
        """Build a dot dict with real key_signals from indicator data."""
        return {**base, "key_signals": _build_key_signals(dot_key, indicators)}

    def src(dot_key: str) -> str:
        """Get sources text paragraph for a dot from indicator metadata."""
        return _sources_text_for_dot(dot_key, indicators)

    if agent_name == "geopolitical":
        return {
            "dot_1": {**build_dot("dot_1"), "nato_outlook": "unified", "nato_confidence": 0.5, "sources": src("dot_1")},
            "dot_2": {**build_dot("dot_2"), "hormuz_risk": "low", "energy_price_outlook": "stable", "sources": src("dot_2")},
        }
    if agent_name == "food_debt":
        return {
            "dot_3": {**build_dot("dot_3"), "fao_trend": "stable", "grain_price_risk": "low", "sources": src("dot_3")},
            "dot_5": {**build_dot("dot_5"), "most_vulnerable": "none", "contagion_risk": "low", "sources": src("dot_5")},
        }
    if agent_name == "financial_em":
        return {
            "dot_4": {**build_dot("dot_4"), "credit_spread_outlook": "stable", "volatility_regime": "low", "sources": src("dot_4")},
            "em_currency": {**build_dot("em_currency"), "currencies_under_pressure": [], "contagion_risk": "low", "sources": src("em_currency")},
        }
    if agent_name == "china_political":
        return {
            "dot_6": {**build_dot("dot_6"), "pmi_outlook": "expanding", "property_sector_risk": "low", "sources": src("dot_6")},
            "dot_7": {**build_dot("dot_7"), "protest_scale": "isolated", "government_stability": "stable", "sources": src("dot_7")},
            "dot_8": {**build_dot("dot_8"), "shipping_risk": "low", "trade_chokepoint_status": "open", "sources": src("dot_8")},
        }
    # health
    return {
        "dot_9": {
            **build_dot("dot_9"),
            "who_risk_level": "low",
            "human_transmission": "none",
            "geographic_spread": "localized",
            "government_response": "none",
            "sources": src("dot_9"),
        },
    }


# Self-check
if __name__ == "__main__":
    # Verify fallback returns valid structure with sources text for each agent
    test_indicators = {
        "brent_price": 82.5, "vix": 18.2, "ig_oas": 142, "hy_oas": 420,
        "caixin_pmi": 50.8, "try_breach": 0, "protest_countries": 1,
        "nato_fracture": 1, "fao_monthly_change_pct": 3.2,
    }
    for name in ("geopolitical", "food_debt", "financial_em", "china_political", "health"):
        fb = _fallback(name, test_indicators)
        assert isinstance(fb, dict) and len(fb) > 0, f"{name} fallback failed"
        # Verify sources field present on every dot as a string
        for key, val in fb.items():
            assert isinstance(val, dict), f"{name}.{key} not a dict"
            assert "sources" in val, f"{name}.{key} missing sources"
            assert isinstance(val["sources"], str), f"{name}.{key}.sources not a string: {type(val['sources'])}"
    print("dot_analyzers fallback OK — 5 agents defined with source attribution (paragraph format)")
