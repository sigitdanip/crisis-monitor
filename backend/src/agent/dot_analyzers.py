"""Dot Analyzer LLM Agents — 5 specialized agents for crisis dot analysis.

Agents 1-5 analyze their assigned dots using indicators + composite score + news.
Each returns a structured dict with status, summary, key_signals, and sources.

sources is a brief paragraph (max 100 words) citing specific indicators,
news headlines, and data points that informed the assessment.
"""
import json
import logging
from typing import Dict, Any, List
from src.agent.llm import call_llm_with_retry
from src.agent.indicator_narrator import narrate_all, sources_narrative, sources_for_dot, _get_data_status, DOT_INDICATORS

logger = logging.getLogger(__name__)


# ============================================================
# Category Score Formatting — V2: per-agent category context
# ============================================================

def _format_category_scores(category_scores: dict, relevant_cats: list) -> str:
    """Format relevant category scores into a concise context string.

    Each category score is a weighted sum of its indicators (0 to weight×count).
    The total composite is the normalized 0-30 score.

    Args:
        category_scores: Dict of {category_name: weighted_sum}.
        relevant_cats: List of category keys relevant to this agent's dots.

    Returns:
        Formatted multi-line string for prompt injection.
    """
    lines = []
    for cat in relevant_cats:
        score = category_scores.get(cat, 0.0)
        label = cat.replace("_", " ").title()
        lines.append(f"  {label}: {score:.2f}")
    total = sum(category_scores.values())
    lines.append(f"  (Total weighted sum: {total:.2f} across {len(category_scores)} categories)")
    return "\n".join(lines)


# ============================================================
# Data Status — Unavailable Ratio per Dot
# ============================================================

def _dot_unavailable_ratio(dot_keys: list, indicators: Dict[str, Any]) -> dict:
    """Compute the fraction of mapped indicators that are unavailable per dot.

    Returns a dict of {dot_key: (unavailable_count, total_slugs, ratio)}.
    When >=50% of a dot's mapped indicators are unavailable, the dot should
    be marked status='unavailable' rather than 'dormant'.
    """
    result = {}
    for dk in dot_keys:
        slugs = DOT_INDICATORS.get(dk, [])
        if not slugs:
            result[dk] = (0, 0, 0.0)
            continue
        unavailable = 0
        for slug in slugs:
            val = indicators.get(slug)
            ds = _get_data_status(val) if val is not None else "unavailable"
            if ds == "unavailable":
                unavailable += 1
        ratio = unavailable / len(slugs) if slugs else 0.0
        result[dk] = (unavailable, len(slugs), ratio)
    return result


def _dot_unavailable_context(dot_keys: list, indicators: Dict[str, Any]) -> str:
    """Generate a data_status summary for prompt injection.

    Returns a string like:
      DOT DATA STATUS:
        dot_1: 2/3 unavailable (67%) — STATUS FORCED TO 'unavailable'
        dot_2: 1/8 unavailable (12%)
    """
    ratios = _dot_unavailable_ratio(dot_keys, indicators)
    lines = ["DOT DATA STATUS (data availability per dot):"]
    for dk in dot_keys:
        unavail, total, ratio = ratios.get(dk, (0, 0, 0.0))
        if total == 0:
            lines.append(f"  {dk}: no mapped indicators")
        elif ratio >= 0.5:
            lines.append(f"  {dk}: {unavail}/{total} indicators unavailable ({ratio*100:.0f}%) — STATUS FORCED TO 'unavailable'")
        else:
            lines.append(f"  {dk}: {unavail}/{total} indicators unavailable ({ratio*100:.0f}%)")
    return "\n".join(lines)


# ============================================================
# Tier-Aware Prompt Hardening — abstention + source-gating
# ============================================================

# Exact abstention string required by AC — must be checked in tests.
ABSTENTION_STRING = "No data sources returned for the last 7 days — no assessment possible."

TIER_RANK = {"live": 3, "mixed": 2, "qualitative": 1}


def _build_tier_instructions(tier: str) -> str:
    """Build tier-specific guardrail instructions for the prompt header.

    The instruction block is prepended to every dot analysis prompt and
    gates what the LLM is allowed to do based on data completeness.

    Args:
        tier: One of 'live', 'mixed', 'qualitative' — the most restrictive
              tier among the dots being analyzed in this prompt.

    Returns:
        A compact instruction string (~50-100 tokens) added to the prompt.
    """
    if tier == "live":
        return (
            "TIER: LIVE — Full quantitative data available. "
            "Analyze normally using the provided indicators and news."
        )
    elif tier == "mixed":
        return (
            "TIER: MIXED — Some quantitative data exists but gaps are present. "
            "Use quantitative indicators where available. "
            "Fill gaps ONLY from the QUALITATIVE SOURCES section below. "
            "Flag each statement with its source: [quantitative] or [web_source]. "
            "CRITICAL: If data is missing, do NOT infer from general training. "
            "Use only the provided sources."
        )
    elif tier == "qualitative":
        return (
            "TIER: QUALITATIVE — No reliable quantitative data. "
            "Use ONLY the QUALITATIVE SOURCES section below. "
            "Do NOT reference or infer from general training data. "
            "If no web sources are provided, you MUST output the exact "
            "abstention message for each dot."
        )
    return ""


def _build_qualitative_sources_text(sources: list) -> str:
    """Build a compact text block from qualitative web search sources.

    Args:
        sources: List of source dicts, each with {url, title, snippet, source_type}.

    Returns:
        Formatted string for prompt injection, or an empty-sources notice.
    """
    if not sources:
        return "QUALITATIVE SOURCES: None available."

    lines = ["QUALITATIVE SOURCES (web search results, use ONLY these):"]
    for i, src in enumerate(sources, 1):
        lines.append(
            f"  [{i}] {src.get('title', 'Untitled')} — {src.get('url', '')}"
        )
        snippet = src.get("snippet", "")
        if snippet:
            lines.append(f"      {snippet[:300]}")
        lines.append(f"      source_type: {src.get('source_type', 'web')}")
    return "\n".join(lines)


def _build_dot_tier_block(tiers: dict, dot_keys: list) -> str:
    """Build a DATA TIER block showing each dot's tier classification.

    This is injected into every agent prompt so the LLM knows which dots
    have reliable data and which require abstention or limited reasoning.

    Args:
        tiers: Dict mapping dot_key -> tier ('live'/'mixed'/'qualitative').
        dot_keys: List of dot keys to include in the block.

    Returns:
        Multi-line string like:
          DATA TIER (per dot):
            dot_1: live
            dot_2: mixed
    """
    lines = ["DATA TIER (per dot):"]
    for dk in dot_keys:
        t = tiers.get(dk, "live")
        lines.append(f"  {dk}: {t}")
    return "\n".join(lines)


def _make_abstention(dot_key: str, extra_fields: dict | None = None) -> dict:
    """Return the deterministic abstention response for a dot.

    When tier=QUALITATIVE and zero web sources are available, the LLM
    is not called — this hardcoded dict is returned directly.

    Args:
        dot_key: Dot identifier (e.g. 'dot_1', 'em_currency').
        extra_fields: Dict of agent-specific field defaults to include
                      in the response (e.g. nato_outlook, hormuz_risk).

    Returns:
        Dict with status='unavailable', the exact abstention summary string,
        and any extra_fields merged in.
    """
    result = {
        "status": "unavailable",
        "summary": ABSTENTION_STRING,
        "key_signals": ["no data sources available"],
        "sources": ABSTENTION_STRING,
    }
    if extra_fields:
        result.update(extra_fields)
    return result


def _effective_tier(tiers: dict, dot_keys: list) -> str:
    """Compute the most restrictive tier across a set of dots.

    Args:
        tiers: Dict mapping dot_key -> tier string (e.g. {'dot_1': 'live', ...}).
        dot_keys: List of dot keys to consider.

    Returns:
        The most restrictive tier: 'qualitative' > 'mixed' > 'live'.
    """
    worst = "live"
    worst_rank = TIER_RANK["live"]
    for dk in dot_keys:
        t = tiers.get(dk, "live")
        rank = TIER_RANK.get(t, 3)
        if rank < worst_rank:
            worst_rank = rank
            worst = t
    return worst


def _preprocess_dots(
    dot_keys: list,
    tiers: dict,
    qualitative_sources: dict | None,
) -> tuple:
    """Split dots into abstaining (no LLM needed) and active (LLM required).

    A dot abstains when tier=QUALITATIVE AND zero sources are available.
    In that case the LLM has nothing to work with and would hallucinate —
    so we short-circuit with a deterministic abstention response.

    Args:
        dot_keys: List of dot keys this agent handles.
        tiers: Dict mapping dot_key -> tier.
        qualitative_sources: Dict mapping dot_key -> list of source dicts
                             (or None/empty for no sources).

    Returns:
        Tuple of (abstentions: dict, active_dots: list, effective_tier: str).
        abstentions maps dot_key -> pre-built abstention response dict.
        active_dots is the subset of dot_keys that need LLM analysis.
        effective_tier is the most restrictive tier among active_dots.
    """
    abstentions = {}
    active_dots = []

    for dk in dot_keys:
        t = tiers.get(dk, "live")
        qs = qualitative_sources.get(dk) if qualitative_sources else None
        qs = qs if isinstance(qs, list) and len(qs) > 0 else []

        if t == "qualitative" and not qs:
            abstentions[dk] = _make_abstention(dk)
        else:
            active_dots.append(dk)

    eff_tier = _effective_tier(tiers, active_dots) if active_dots else "live"
    return abstentions, active_dots, eff_tier


def _collect_qualitative_sources(
    dot_keys: list, qualitative_sources: dict | None
) -> list:
    """Collect all qualitative sources across the given dots, deduplicated by URL.

    Skips URLs that are cached in url_cache with status_code != 200 (dead URLs).
    URLs not yet validated (no cache entry) are included — they get their
    benefit of the doubt on first encounter.

    Args:
        dot_keys: List of dot keys to collect sources for.
        qualitative_sources: Dict mapping dot_key -> list of source dicts.

    Returns:
        Deduplicated list of source dicts across all specified dots,
        excluding URLs known to be dead from url_cache.
    """
    seen = set()
    collected = []

    # Pre-load dead URL set from url_cache (best-effort)
    dead_urls: set[str] = set()
    try:
        from src.db.database import get_db

        conn = get_db()
        # Only check URLs cached within the last 24h
        import time

        cutoff = time.time() - 86_400
        cutoff_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(cutoff))
        rows = conn.execute(
            "SELECT url FROM url_cache "
            "WHERE checked_at >= ? AND (status_code IS NULL OR status_code < 200 OR status_code >= 300)",
            (cutoff_iso,),
        ).fetchall()
        dead_urls = {row["url"] for row in rows}
        conn.close()
    except Exception:
        # DB unavailable — don't filter, include all sources
        pass

    for dk in dot_keys:
        qs = qualitative_sources.get(dk) if qualitative_sources else None
        if not qs or not isinstance(qs, list):
            continue
        for src in qs:
            url = src.get("url", "")
            if not url:
                continue
            if url in seen:
                continue
            # Skip URLs known to be dead from url_cache
            if url in dead_urls:
                continue
            seen.add(url)
            collected.append(src)
    return collected


# ============================================================
# Agent 1: GEOPOLITICAL — Dots 1 (NATO) + 2 (Hormuz/Energy)
# ============================================================

AGENT1_PROMPT = """{tier_instructions}

{dot_tier_info}

You are a geopolitical risk analyst specializing in NATO alliance stability and global energy security.

Analyze the following indicators and news for Dot 1 (NATO Alliance Cohesion) and Dot 2 (Strait of Hormuz / Energy Security).

INDICATORS:
{indicators_narrative}

COMPOSITE SCORE: {composite}/30 ({interpretation})

{qualitative_sources}

{dot_data_status}

DATA SOURCES:
{sources_narrative}

NEWS HEADLINES:
{news_json}

Return a JSON object with this exact structure:
{{
  "dot_1": {{
    "status": "dormant|activating|active|critical|unavailable",
    "summary": "2-3 sentence assessment of NATO alliance state",
    "key_signals": ["signal 1", "signal 2", "signal 3"],
    "nato_outlook": "unified|fracturing|withdrawing",
    "nato_confidence": 0.0-1.0,
    "sources": "1-2 sentence paragraph citing which specific indicators (by name and value), news headlines, and data origins most informed this NATO assessment. Reference the DATA SOURCES section. Max 100 words."
  }},
  "dot_2": {{
    "status": "dormant|activating|active|critical|unavailable",
    "summary": "2-3 sentence energy security assessment",
    "key_signals": ["signal 1", "signal 2"],
    "hormuz_risk": "low|elevated|high|closed",
    "energy_price_outlook": "stable|rising|spiking",
    "sources": "1-2 sentence paragraph citing which specific indicators (by name and value), news headlines, and data origins most informed this energy security assessment. Reference the DATA SOURCES section. Max 100 words."
  }}
}}

Rules:
- status: "dormant" if no concerning signals, "activating" if early warnings, "active" if clear danger, "critical" if crisis unfolding
- status "unavailable": use when DOT DATA STATUS says STATUS FORCED TO 'unavailable' for that dot (>=50% of mapped indicators have no data)
- Indicators with data_status=unavailable lack real data — they should NOT be treated as "normal/calm"
- Be specific with numbers and dates from the indicators
- sources: write a concise paragraph naming the specific indicators, their current values, and data origins that most drove your assessment. Cite news headlines by topic when they influenced the judgment.
- Only use information present in the data provided
- TIER RULE: If a dot's tier is 'qualitative' (see DATA TIER above), you MUST output status='unavailable' — do NOT infer from general training data or fabricate assessment signals
- TIER RULE: If a dot's tier is 'mixed' (see DATA TIER above), ONLY reason about indicators with data_status='live'; mark unavailable indicators as [DATA UNAVAILABLE] in the assessment"""


async def analyze_geopolitical(
    indicators: Dict[str, Any],
    composite: Dict[str, Any],
    news: List[Dict[str, str]] | None = None,
    tiers: dict | None = None,
    qualitative_sources: dict | None = None,
) -> Dict[str, Any]:
    """Agent 1: Geopolitical — Dots 1 (NATO) + 2 (Hormuz/Energy).

    Args:
        indicators: Flat dict of indicator slug -> value.
        composite: Composite scoring result dict.
        news: Optional list of news headline dicts.
        tiers: Dict mapping dot_key -> tier ('live'/'mixed'/'qualitative').
        qualitative_sources: Dict mapping dot_key -> list of
            {{url, title, snippet, source_type}} dicts from web search.
    """
    tiers = tiers or {}
    qualitative_sources = qualitative_sources or {}

    dot_keys = ["dot_1", "dot_2"]

    # Pre-process: check for abstaining dots (QUALITATIVE + zero sources).
    abstentions, active_dots, effective_tier = _preprocess_dots(
        dot_keys, tiers, qualitative_sources
    )

    # If all dots abstain, return abstention responses directly — no LLM call.
    if not active_dots:
        return abstentions

    # Build tier instructions based on the most restrictive active tier.
    tier_instructions = _build_tier_instructions(effective_tier)

    # Collect qualitative sources across active dots (deduplicated).
    qs_list = _collect_qualitative_sources(active_dots, qualitative_sources)
    qs_text = _build_qualitative_sources_text(qs_list)

    prompt = AGENT1_PROMPT.format(
        tier_instructions=tier_instructions,
        dot_tier_info=_build_dot_tier_block(tiers, dot_keys),
        indicators_narrative=narrate_all(indicators),
        composite=composite["composite"],
        interpretation=composite["interpretation"],
        qualitative_sources=qs_text,
        dot_data_status=_dot_unavailable_context(dot_keys, indicators),
        sources_narrative=sources_narrative(indicators, dot_keys),
        news_json=json.dumps(news or [], indent=2),
    )

    # For QUALITATIVE tier with sources, use temperature=0 for determinism.
    temp = 0.0 if effective_tier == "qualitative" else 0.3
    result, _ = await call_llm_with_retry(prompt, temperature=temp)

    # Merge LLM results with pre-built abstentions.
    if result:
        result.update(abstentions)
        return result
    fallback = _fallback("geopolitical", indicators, tiers=tiers)
    fallback.update(abstentions)
    return fallback


# ============================================================
# Agent 2: FOOD & DEBT — Dots 3 (Food/Fertilizer) + 5 (Sovereign Debt)
# ============================================================

AGENT2_PROMPT = """{tier_instructions}

{dot_tier_info}

You are a food security and sovereign debt analyst.

Analyze the following indicators and news for Dot 3 (Food & Fertilizer Crisis) and Dot 5 (Sovereign Debt Stress).

INDICATORS:
{indicators_narrative}

COMPOSITE SCORE: {composite}/30 ({interpretation})

{qualitative_sources}

{dot_data_status}

DATA SOURCES:
{sources_narrative}

NEWS HEADLINES:
{news_json}

Return a JSON object with this exact structure:
{{
  "dot_3": {{
    "status": "dormant|activating|active|critical|unavailable",
    "summary": "2-3 sentence food/fertilizer assessment",
    "key_signals": ["signal 1", "signal 2", "signal 3"],
    "fao_trend": "falling|stable|rising|spiking",
    "grain_price_risk": "low|elevated|high",
    "sources": "1-2 sentence paragraph citing which specific indicators (by name and value), news headlines, and data origins most informed this food security assessment. Reference the DATA SOURCES section. Max 100 words."
  }},
  "dot_5": {{
    "status": "dormant|activating|active|critical|unavailable",
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
- status "unavailable": use when DOT DATA STATUS says STATUS FORCED TO 'unavailable' for that dot (>=50% of mapped indicators have no data)
- Indicators with data_status=unavailable lack real data — they should NOT be treated as "normal/calm"
- sources: write a concise paragraph naming the specific indicators, their current values, and data origins that most drove your assessment. Cite news headlines by topic when they influenced the judgment.
- Indicators with numeric values and a status (e.g. "status: normal") have live data — never call them unavailable/N/A.
- Only use information present in the data provided
- TIER RULE: If a dot's tier is 'qualitative' (see DATA TIER above), you MUST output status='unavailable' — do NOT infer from general training data or fabricate assessment signals
- TIER RULE: If a dot's tier is 'mixed' (see DATA TIER above), ONLY reason about indicators with data_status='live'; mark unavailable indicators as [DATA UNAVAILABLE] in the assessment"""


async def analyze_food_debt(
    indicators: Dict[str, Any],
    composite: Dict[str, Any],
    news: List[Dict[str, str]] | None = None,
    tiers: dict | None = None,
    qualitative_sources: dict | None = None,
) -> Dict[str, Any]:
    """Agent 2: Food & Debt — Dots 3 (Food) + 5 (Sovereign Debt)."""
    tiers = tiers or {}
    qualitative_sources = qualitative_sources or {}

    dot_keys = ["dot_3", "dot_5"]

    abstentions, active_dots, effective_tier = _preprocess_dots(
        dot_keys, tiers, qualitative_sources
    )
    if not active_dots:
        return abstentions

    tier_instructions = _build_tier_instructions(effective_tier)
    qs_list = _collect_qualitative_sources(active_dots, qualitative_sources)
    qs_text = _build_qualitative_sources_text(qs_list)

    prompt = AGENT2_PROMPT.format(
        tier_instructions=tier_instructions,
        dot_tier_info=_build_dot_tier_block(tiers, dot_keys),
        indicators_narrative=narrate_all(indicators),
        composite=composite["composite"],
        interpretation=composite["interpretation"],
        qualitative_sources=qs_text,
        dot_data_status=_dot_unavailable_context(dot_keys, indicators),
        sources_narrative=sources_narrative(indicators, dot_keys),
        news_json=json.dumps(news or [], indent=2),
    )

    temp = 0.0 if effective_tier == "qualitative" else 0.3
    result, _ = await call_llm_with_retry(prompt, temperature=temp)
    if not result:
        logger.warning("Agent 2 (food_debt) extract_json returned empty dict")
        fallback = _fallback("food_debt", indicators, tiers=tiers)
        fallback.update(abstentions)
        return fallback
    result.update(abstentions)
    return result


# ============================================================
# Agent 3: FINANCIAL & EM — Dot 4 (Credit/Financial) + EM Currency stress
# ============================================================

AGENT3_PROMPT = """{tier_instructions}

{dot_tier_info}

You are a financial markets and emerging markets analyst.

Analyze the following indicators for Dot 4 (Financial/Credit Stress) and EM Currency stability.

INDICATORS:
{indicators_narrative}

COMPOSITE SCORE: {composite}/30 ({interpretation})

{qualitative_sources}

{dot_data_status}

DATA SOURCES:
{sources_narrative}

NEWS HEADLINES:
{news_json}

Return a JSON object with this exact structure:
{{
  "dot_4": {{
    "status": "dormant|activating|active|critical|unavailable",
    "summary": "2-3 sentence credit market assessment",
    "key_signals": ["signal 1", "signal 2", "signal 3"],
    "credit_spread_outlook": "tightening|stable|widening|stressed",
    "volatility_regime": "low|elevated|high|crisis",
    "sources": "1-2 sentence paragraph citing which specific indicators (by name and value), news headlines, and data origins most informed this credit market assessment. Reference the DATA SOURCES section. Max 100 words."
  }},
  "em_currency": {{
    "status": "dormant|activating|active|critical|unavailable",
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
- status "unavailable": use when DOT DATA STATUS says STATUS FORCED TO 'unavailable' for that dot (>=50% of mapped indicators have no data)
- Indicators with data_status=unavailable lack real data — they should NOT be treated as "normal/calm"
- Use VIX, MOVE, VVIX, SOFR-OIS, cross-currency basis for credit assessment
- sources: write a concise paragraph naming the specific indicators, their current values, and data origins that most drove your assessment. Cite news headlines by topic when they influenced the judgment.
- Indicators with numeric values and a status (e.g. "status: normal") have live data — never call them unavailable/N/A.
- Only use information present in the data provided
- TIER RULE: If a dot's tier is 'qualitative' (see DATA TIER above), you MUST output status='unavailable' — do NOT infer from general training data or fabricate assessment signals
- TIER RULE: If a dot's tier is 'mixed' (see DATA TIER above), ONLY reason about indicators with data_status='live'; mark unavailable indicators as [DATA UNAVAILABLE] in the assessment"""


async def analyze_financial_em(
    indicators: Dict[str, Any],
    composite: Dict[str, Any],
    news: List[Dict[str, str]] | None = None,
    tiers: dict | None = None,
    qualitative_sources: dict | None = None,
) -> Dict[str, Any]:
    """Agent 3: Financial & EM — Dot 4 (Credit) + EM Currency stress."""
    tiers = tiers or {}
    qualitative_sources = qualitative_sources or {}

    dot_keys = ["dot_4", "em_currency"]

    abstentions, active_dots, effective_tier = _preprocess_dots(
        dot_keys, tiers, qualitative_sources
    )
    if not active_dots:
        return abstentions

    tier_instructions = _build_tier_instructions(effective_tier)
    qs_list = _collect_qualitative_sources(active_dots, qualitative_sources)
    qs_text = _build_qualitative_sources_text(qs_list)

    prompt = AGENT3_PROMPT.format(
        tier_instructions=tier_instructions,
        dot_tier_info=_build_dot_tier_block(tiers, dot_keys),
        indicators_narrative=narrate_all(indicators),
        composite=composite["composite"],
        interpretation=composite["interpretation"],
        qualitative_sources=qs_text,
        dot_data_status=_dot_unavailable_context(dot_keys, indicators),
        sources_narrative=sources_narrative(indicators, dot_keys),
        news_json=json.dumps(news or [], indent=2),
    )

    temp = 0.0 if effective_tier == "qualitative" else 0.3
    result, _ = await call_llm_with_retry(prompt, temperature=temp)
    if not result:
        logger.warning("Agent 3 (financial_em) extract_json returned empty dict")
        fallback = _fallback("financial_em", indicators, tiers=tiers)
        fallback.update(abstentions)
        return fallback
    result.update(abstentions)
    return result


# ============================================================
# Agent 4: CHINA & POLITICAL — Dots 6 (China) + 7 (Political) + 8 (Supply Chain)
# ============================================================

AGENT4_PROMPT = """{tier_instructions}

{dot_tier_info}

You are a China economy and global political risk analyst.

Analyze the following indicators for Dot 6 (China Economic Stress), Dot 7 (Political/Social Unrest), and Dot 8 (Supply Chain Disruption).

INDICATORS:
{indicators_narrative}

COMPOSITE SCORE: {composite}/30 ({interpretation})

{qualitative_sources}

{dot_data_status}

DATA SOURCES:
{sources_narrative}

NEWS HEADLINES:
{news_json}

Return a JSON object with this exact structure:
{{
  "dot_6": {{
    "status": "dormant|activating|active|critical|unavailable",
    "summary": "2-3 sentence China economic assessment",
    "key_signals": ["signal 1", "signal 2", "signal 3"],
    "pmi_outlook": "expanding|contracting|recession",
    "property_sector_risk": "low|elevated|high|crisis",
    "sources": "1-2 sentence paragraph citing which specific indicators (by name and value), news headlines, and data origins most informed this China economic assessment. Reference the DATA SOURCES section. Max 100 words."
  }},
  "dot_7": {{
    "status": "dormant|activating|active|critical|unavailable",
    "summary": "2-3 sentence political/social unrest assessment",
    "key_signals": ["signal 1", "signal 2", "signal 3"],
    "protest_scale": "isolated|rising|widespread",
    "government_stability": "stable|pressured|fragile",
    "sources": "1-2 sentence paragraph citing which specific indicators (by name and value), news headlines, and data origins most informed this political risk assessment. Reference the DATA SOURCES section. Max 100 words."
  }},
  "dot_8": {{
    "status": "dormant|activating|active|critical|unavailable",
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
- status "unavailable": use when DOT DATA STATUS says STATUS FORCED TO 'unavailable' for that dot (>=50% of mapped indicators have no data)
- Indicators with data_status=unavailable lack real data — they should NOT be treated as "normal/calm"
- sources: write a concise paragraph naming the specific indicators, their current values, and data origins that most drove your assessment. Cite news headlines by topic when they influenced the judgment.
- Only use information present in the data provided
- TIER RULE: If a dot's tier is 'qualitative' (see DATA TIER above), you MUST output status='unavailable' — do NOT infer from general training data or fabricate assessment signals
- TIER RULE: If a dot's tier is 'mixed' (see DATA TIER above), ONLY reason about indicators with data_status='live'; mark unavailable indicators as [DATA UNAVAILABLE] in the assessment"""


async def analyze_china_political(
    indicators: Dict[str, Any],
    composite: Dict[str, Any],
    news: List[Dict[str, str]] | None = None,
    tiers: dict | None = None,
    qualitative_sources: dict | None = None,
) -> Dict[str, Any]:
    """Agent 4: China & Political — Dots 6 (China) + 7 (Political) + 8 (Supply Chain)."""
    tiers = tiers or {}
    qualitative_sources = qualitative_sources or {}

    dot_keys = ["dot_6", "dot_7", "dot_8"]

    abstentions, active_dots, effective_tier = _preprocess_dots(
        dot_keys, tiers, qualitative_sources
    )
    if not active_dots:
        return abstentions

    tier_instructions = _build_tier_instructions(effective_tier)
    qs_list = _collect_qualitative_sources(active_dots, qualitative_sources)
    qs_text = _build_qualitative_sources_text(qs_list)

    prompt = AGENT4_PROMPT.format(
        tier_instructions=tier_instructions,
        dot_tier_info=_build_dot_tier_block(tiers, dot_keys),
        indicators_narrative=narrate_all(indicators),
        composite=composite["composite"],
        interpretation=composite["interpretation"],
        qualitative_sources=qs_text,
        dot_data_status=_dot_unavailable_context(dot_keys, indicators),
        sources_narrative=sources_narrative(indicators, dot_keys),
        news_json=json.dumps(news or [], indent=2),
    )

    temp = 0.0 if effective_tier == "qualitative" else 0.3
    result, _ = await call_llm_with_retry(prompt, temperature=temp)
    if result:
        result.update(abstentions)
        return result
    fallback = _fallback("china_political", indicators, tiers=tiers)
    fallback.update(abstentions)
    return fallback


# ============================================================
# Agent 5: HEALTH — Dot 9 (Hantavirus/Pandemic)
# ============================================================

AGENT5_PROMPT = """{tier_instructions}

{dot_tier_info}

You are a global health security analyst specializing in emerging infectious diseases.

Analyze the following indicators for Dot 9 (Health Security — Hantavirus & Pandemic Risk).

INDICATORS:
{indicators_narrative}

COMPOSITE SCORE: {composite}/30 ({interpretation})

{qualitative_sources}

{dot_data_status}

DATA SOURCES:
{sources_narrative}

NEWS HEADLINES:
{news_json}

Return a JSON object with this exact structure:
{{
  "dot_9": {{
    "status": "dormant|activating|active|critical|unavailable",
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
- status "unavailable": use when DOT DATA STATUS says STATUS FORCED TO 'unavailable' (>=50% of mapped indicators have no data). Note: Dot 9 has no numeric indicators — it's news/LLM-driven. Use 'dormant' if no concerning news, not 'unavailable'.
- Indicators with data_status=unavailable lack real data — they should NOT be treated as "normal/calm"
- sources: write a concise paragraph naming the specific indicators, their current values, and data origins that most drove your assessment. Cite news headlines by topic when they influenced the judgment.
- Only use information present in the data provided
- TIER RULE: If a dot's tier is 'qualitative' (see DATA TIER above), you MUST output status='unavailable' — do NOT infer from general training data or fabricate assessment signals
- TIER RULE: If a dot's tier is 'mixed' (see DATA TIER above), ONLY reason about indicators with data_status='live'; mark unavailable indicators as [DATA UNAVAILABLE] in the assessment"""


async def analyze_health(
    indicators: Dict[str, Any],
    composite: Dict[str, Any],
    news: List[Dict[str, str]] | None = None,
    tiers: dict | None = None,
    qualitative_sources: dict | None = None,
) -> Dict[str, Any]:
    """Agent 5: Health — Dot 9 (Hantavirus/Pandemic)."""
    tiers = tiers or {}
    qualitative_sources = qualitative_sources or {}

    dot_keys = ["dot_9"]

    abstentions, active_dots, effective_tier = _preprocess_dots(
        dot_keys, tiers, qualitative_sources
    )
    if not active_dots:
        return abstentions

    tier_instructions = _build_tier_instructions(effective_tier)
    qs_list = _collect_qualitative_sources(active_dots, qualitative_sources)
    qs_text = _build_qualitative_sources_text(qs_list)

    prompt = AGENT5_PROMPT.format(
        tier_instructions=tier_instructions,
        dot_tier_info=_build_dot_tier_block(tiers, dot_keys),
        indicators_narrative=narrate_all(indicators),
        composite=composite["composite"],
        interpretation=composite["interpretation"],
        qualitative_sources=qs_text,
        dot_data_status=_dot_unavailable_context(dot_keys, indicators),
        sources_narrative=sources_narrative(indicators, dot_keys),
        news_json=json.dumps(news or [], indent=2),
    )

    temp = 0.0 if effective_tier == "qualitative" else 0.3
    result, _ = await call_llm_with_retry(prompt, temperature=temp)
    if result:
        result.update(abstentions)
        return result
    fallback = _fallback("health", indicators, tiers=tiers)
    fallback.update(abstentions)
    return fallback


# ============================================================
# Fallback — graceful degradation when LLM returns bad JSON
# ============================================================

def _sources_text_for_dot(dot_key: str, indicators: Dict[str, Any]) -> str:
    """Generate a brief plain-language sources paragraph for a dot from indicator metadata.

    Used by the fallback path when the LLM is unavailable — synthesises
    a 1-2 sentence attribution from the indicator registry.
    Returns empty string when no indicators are mapped to the dot.
    """
    from src.agent.indicator_narrator import DOT_INDICATORS, INDICATOR_META, _is_news_flag, _is_structured_value, _extract_scalar, _get_data_status

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
        ds = _get_data_status(value) if value is not None else "unavailable"

        if ds == "unavailable":
            parts.append(f"{name} (unavailable)")
            continue
        if _is_news_flag(value):
            # News-derived flag: show narrative instead of numeric value
            narrative = value.get("narrative", "(no news)")
            narrative_short = narrative[:200]
            parts.append(f"{name} (news: {narrative_short})")
        elif _is_structured_value(value):
            scalar = _extract_scalar(value)
            if scalar is not None:
                if isinstance(scalar, float):
                    parts.append(f"{name} = {scalar:.1f}")
                elif isinstance(scalar, int):
                    parts.append(f"{name} = {scalar}")
                else:
                    parts.append(f"{name} = {scalar}")
            else:
                parts.append(f"{name} (unavailable)")
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
    from src.agent.indicator_narrator import DOT_INDICATORS, INDICATOR_META, _is_news_flag, _is_structured_value, _extract_scalar, _assess, _get_data_status

    slugs = DOT_INDICATORS.get(dot_key, [])
    if not slugs:
        return ["no indicator data mapped to this dot"]

    signals = []
    for slug in slugs:
        meta = INDICATOR_META.get(slug, {})
        name = meta.get("name", slug)
        value = indicators.get(slug)
        ds = _get_data_status(value) if value is not None else "unavailable"

        if ds == "unavailable":
            signals.append(f"{name}: unavailable")
            continue
        if value is None:
            signals.append(f"{name}: unavailable")
            continue
        if _is_news_flag(value):
            narrative = value.get("narrative", "")[:100]
            signals.append(f"{name}: {narrative}" if narrative else f"{name}: news flag present (no narrative)")
        elif _is_structured_value(value):
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


def _fallback(agent_name: str, indicators: Dict[str, Any] = None, tiers: dict = None) -> Dict[str, Any]:
    """Return a safe fallback dict when LLM output can't be parsed.

    sources field is a brief text paragraph derived from indicator metadata;
    empty string when no metadata is available for the dot.

    Args:
        agent_name: One of 'geopolitical', 'food_debt', 'financial_em',
                   'china_political', 'health'.
        indicators: Flat dict of indicator slug -> value.
        tiers: Dict mapping dot_key -> tier ('live'/'mixed'/'qualitative').
               Defaults to 'live' for any missing key.
    """
    indicators = indicators or {}
    tiers = tiers or {}
    base = {
        "status": "dormant",
        "summary": f"LLM analysis unavailable for {agent_name} — using fallback",
        "key_signals": ["data unavailable"],
    }

    def build_dot(dot_key: str) -> dict:
        """Build a dot dict with real key_signals from indicator data."""
        return {**base, "key_signals": _build_key_signals(dot_key, indicators),
                "tier": tiers.get(dot_key, "live")}

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
