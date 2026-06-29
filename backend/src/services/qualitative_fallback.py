"""
Qualitative Fallback — DuckDuckGo web search + LLM synthesis.

When tier_classifier returns MIXED or QUALITATIVE for a dot, this service
fills the data gap with recent web search results synthesized by LLM.
Never hallucinates — every dot gets either live data or honest web-sourced
qualitative backup.

Phases per dot:
  1. Formulate 3-5 search queries from dot context + indicator names.
  2. Execute DuckDuckGo searches (2 retries, 10s timeout, circuit breaker).
  3. Validate result URLs via url_validator (drops dead URLs).
  4. Persist valid sources to qualitative_sources table.
  5. LLM synthesis of web results into a 150-250 word narrative summary.

Circuit breaker: 3 consecutive failures → skip DDG for 1 hour.
Rate limiting: max 2 queries/sec with staggered delays.
"""

import asyncio
import logging
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from src.agent.llm import (
    get_llm,
    get_llm_content,
    get_token_cost,
    reset_token_cost,
    track_token_usage,
)
from src.db.database import get_db
from src.services.url_validator import validate_urls

logger = logging.getLogger("crisis_monitor.qualitative_fallback")

# ── Constants ──────────────────────────────────────────────────────────────

CIRCUIT_TIMEOUT_SECONDS = 3_600  # 1 hour
MAX_CONSECUTIVE_FAILURES = 3
SEARCH_TIMEOUT = 10.0          # seconds per search query
MAX_SEARCH_RESULTS = 8         # results per query
TOP_RESULTS = 10               # max total results after deduplication
RATE_LIMIT_DELAY_BASE = 0.5    # seconds between queries
MAX_QUERY_RETRIES = 2          # retries after initial attempt

# ── Jinja2 template ────────────────────────────────────────────────────────

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "prompts"
_JINJA_ENV = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=False)

# ── Dot names for search query formulation ─────────────────────────────────
# Maps dot_number (1-9) to human-readable context used in search queries.

DOT_CONTEXT: dict[int, dict[str, str]] = {
    1: {
        "name": "Geopolitical Stability",
        "theme": "NATO unity cohesion transatlantic alliance",
        "key_indicators": "NATO fracture, US NATO withdrawal, DXY",
    },
    2: {
        "name": "Energy Security",
        "theme": "oil gas energy prices supply disruptions",
        "key_indicators": "Brent crude oil, WTI, natural gas, EU gas storage, US SPR, Hormuz Strait",
    },
    3: {
        "name": "Food Security",
        "theme": "food prices FAO food index grain prices agriculture",
        "key_indicators": "FAO Food Price Index, CME grains, wheat corn soybeans",
    },
    4: {
        "name": "Financial Markets",
        "theme": "credit spreads volatility financial stress",
        "key_indicators": "IG OAS, HY OAS, VIX, US 10Y yield, US 2Y yield",
    },
    5: {
        "name": "Sovereign Debt Contagion",
        "theme": "sovereign debt crisis emerging markets default risk",
        "key_indicators": "BTP-Bund spread, CDS doubling, EM currency stress",
    },
    6: {
        "name": "China Economy",
        "theme": "China economy property sector manufacturing PMI",
        "key_indicators": "Caixin PMI, China property defaults, economic slowdown",
    },
    7: {
        "name": "Political Instability",
        "theme": "protests government crisis political instability unrest",
        "key_indicators": "protest countries count, government crisis flag, civil unrest",
    },
    8: {
        "name": "Trade Chokepoints",
        "theme": "shipping trade routes maritime chokepoints Hormuz",
        "key_indicators": "Hormuz closure risk, Brent crude, shipping disruptions",
    },
    9: {
        "name": "Global Health",
        "theme": "pandemic outbreak WHO disease global health emergency",
        "key_indicators": "WHO risk assessment, disease outbreaks, health emergencies",
    },
}

# ── Circuit breaker ────────────────────────────────────────────────────────

_CONSECUTIVE_FAILURES: int = 0
_CIRCUIT_OPEN: bool = False
_CIRCUIT_OPENED_AT: float | None = None  # monotonic timestamp when circuit tripped

# Per-run deduplication: URLs already seen for a dot.
_seen_urls: set[str] = set()


def _reset_circuit() -> None:
    """Reset circuit breaker state for a new pipeline run."""
    global _CONSECUTIVE_FAILURES, _CIRCUIT_OPEN, _CIRCUIT_OPENED_AT, _seen_urls
    _CONSECUTIVE_FAILURES = 0
    _CIRCUIT_OPEN = False
    _CIRCUIT_OPENED_AT = None
    _seen_urls = set()


def _record_failure() -> None:
    """Record a search failure; trip circuit breaker if threshold reached."""
    global _CONSECUTIVE_FAILURES, _CIRCUIT_OPEN, _CIRCUIT_OPENED_AT
    _CONSECUTIVE_FAILURES += 1
    if _CONSECUTIVE_FAILURES >= MAX_CONSECUTIVE_FAILURES and not _CIRCUIT_OPEN:
        _CIRCUIT_OPEN = True
        _CIRCUIT_OPENED_AT = time.monotonic()
        logger.error(
            "Circuit breaker OPEN after %d consecutive search failures — "
            "skipping DuckDuckGo for 1 hour",
            _CONSECUTIVE_FAILURES,
        )


def _record_success() -> None:
    """Reset consecutive failure counter on a successful search."""
    global _CONSECUTIVE_FAILURES
    _CONSECUTIVE_FAILURES = 0


def _check_circuit() -> bool:
    """Check if circuit breaker allows searches.

    Returns True if circuit is CLOSED (searches allowed).
    If circuit has been open for > 1 hour, auto-resets it.

    Returns:
        True when searches are allowed.
    """
    global _CIRCUIT_OPEN, _CIRCUIT_OPENED_AT, _CONSECUTIVE_FAILURES

    if not _CIRCUIT_OPEN:
        return True

    # Time-based auto-reset: reopen after 1 hour
    if _CIRCUIT_OPENED_AT is not None:
        elapsed = time.monotonic() - _CIRCUIT_OPENED_AT
        if elapsed >= CIRCUIT_TIMEOUT_SECONDS:
            logger.info(
                "Circuit breaker auto-reset after %.0f seconds (1h timeout)",
                elapsed,
            )
            _CIRCUIT_OPEN = False
            _CIRCUIT_OPENED_AT = None
            _CONSECUTIVE_FAILURES = 0
            return True

    return False


# ── Query formulation ──────────────────────────────────────────────────────


def _formulate_queries(
    dot_number: int,
    dot_context: dict[str, Any] | None = None,
) -> list[str]:
    """Build 3-5 search queries for a dot based on its context.

    Each query targets a different angle. When dot_context is provided,
    additional queries are generated from the context's name/context keys.

    Args:
        dot_number: Dot 1-9.
        dot_context: Optional additional context dict (e.g. from tier classifier
                     or indicator narratives). Keys used: 'name', 'context'.

    Returns:
        List of 3-5 query strings.
    """
    ctx = DOT_CONTEXT.get(dot_number)
    extra_terms = ""

    # Incorporate dynamic context when available
    if dot_context:
        name_override = dot_context.get("name", "")
        context_note = dot_context.get("context", "")
        if name_override:
            extra_terms = name_override
        if context_note:
            # Take first ~100 chars of context for query enrichment
            short_ctx = context_note[:100].strip()
            extra_terms = f"{extra_terms} {short_ctx}".strip()

    if ctx is None:
        base = f"global crisis indicators dot {dot_number} latest developments"
        if extra_terms:
            return [
                f"{extra_terms} latest news developments 2026",
                base,
            ]
        return [base]

    name = ctx["name"]
    theme = ctx["theme"]
    indicators = ctx["key_indicators"]

    # Build 3 base queries
    queries = [
        f"{theme} latest news developments 2026",
        f"{name} current status risk assessment 2026",
        f"{indicators} recent data trends 2026",
    ]

    # Add dynamic-context-derived queries when available
    if extra_terms and extra_terms != name:
        queries.append(f"{extra_terms} latest developments 2026")
    if dot_context and dot_context.get("context"):
        # Generate a focused query from the context snippet
        queries.append(f"{name} {dot_context['context'][:80].strip()}")

    # Cap at 5 queries
    return queries[:5]


# ── Web search ─────────────────────────────────────────────────────────────


async def _search_duckduckgo(query: str, max_results: int = MAX_SEARCH_RESULTS) -> list[dict[str, str]]:
    """Execute a single DuckDuckGo search with a 10-second timeout.

    Uses the duckduckgo-search package (free, no API key required).
    Runs the synchronous DDGS client in a thread to avoid blocking the event loop.

    Args:
        query: Search query string.
        max_results: Max results to return (default 8).

    Returns:
        List of dicts with 'title', 'url', 'snippet' keys.

    Raises:
        asyncio.TimeoutError: If the search exceeds SEARCH_TIMEOUT seconds.
        Exception: Any error from the DDGS client.
    """
    def _sync_search() -> list[dict[str, str]]:
        from duckduckgo_search import DDGS

        results: list[dict[str, str]] = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                })
        return results

    return await asyncio.wait_for(
        asyncio.to_thread(_sync_search),
        timeout=SEARCH_TIMEOUT,
    )


async def _validate_and_filter_results(
    results: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Validate result URLs via url_validator and drop dead ones.

    Runs all URLs through validate_urls() which performs async HTTP HEAD
    checks with 24-hour caching. Only results with is_alive=True are kept.

    Args:
        results: Search result dicts with 'url' key.

    Returns:
        Filtered list containing only results with validated live URLs.
    """
    if not results:
        return []

    urls = [r["url"] for r in results if r.get("url")]
    if not urls:
        return []

    try:
        validation_map = await validate_urls(urls)
    except Exception:
        logger.warning("URL validation failed — keeping all results", exc_info=True)
        return results  # Best-effort: keep all results if validation fails

    valid_results: list[dict[str, str]] = []
    for r in results:
        url = r.get("url", "")
        if not url:
            continue
        v = validation_map.get(url)
        if v is not None and v.get("is_alive"):
            valid_results.append(r)
        elif v is None:
            # URL not in validation results (shouldn't happen) — keep it
            valid_results.append(r)
        else:
            logger.debug("Dropping dead URL from qualitative results: %s", url)

    return valid_results


async def search_dot(
    dot_number: int,
    dot_context: dict[str, Any] | None = None,
) -> tuple[list[dict[str, str]], bool]:
    """Search DuckDuckGo for a dot with retry logic and circuit breaker.

    Formulates 3-5 queries, executes them with rate limiting (2 qps max),
    validates result URLs via url_validator, and deduplicates by URL.

    Retry logic: 2 retries per query (3 total attempts) with exponential
    backoff (2s, 4s).
    Circuit breaker: after 3 consecutive failures, skip all DDG searches
    for 1 hour. Auto-resets after the cooldown period.

    Args:
        dot_number: Dot 1-9.
        dot_context: Optional additional context for query formulation.

    Returns:
        Tuple of (results_list, search_success) where:
        - results_list: deduplicated search results with title/url/snippet
        - search_success: True if at least one live result was found
    """
    if not _check_circuit():
        logger.warning(
            "Circuit breaker is OPEN — skipping web search for dot %d", dot_number
        )
        return [], False

    queries = _formulate_queries(dot_number, dot_context)
    all_results: list[dict[str, str]] = []
    any_success = False

    for qi, query in enumerate(queries):
        # Rate limiting: max 2 queries/second with staggered delay.
        if qi > 0:
            delay = RATE_LIMIT_DELAY_BASE + random.uniform(0, 0.3)
            await asyncio.sleep(delay)

        last_exc: Exception | None = None

        for attempt in range(1, MAX_QUERY_RETRIES + 2):  # initial + 2 retries = 3 total
            try:
                raw_results = await _search_duckduckgo(query, max_results=MAX_SEARCH_RESULTS)

                # Validate URLs before accepting results
                validated_results = await _validate_and_filter_results(raw_results)

                if validated_results:
                    any_success = True
                    _record_success()
                    for r in validated_results:
                        url = r.get("url", "")
                        if url and url not in _seen_urls:
                            _seen_urls.add(url)
                            all_results.append(r)
                    logger.info(
                        "Dot %d query %d: %d live results from %d raw (attempt %d)",
                        dot_number, qi + 1, len(validated_results), len(raw_results), attempt,
                    )
                    break  # success — don't retry this query
                elif raw_results:
                    # Raw results returned but all URLs were dead
                    _record_success()
                    logger.info(
                        "Dot %d query %d: %d raw results, 0 live URLs (attempt %d)",
                        dot_number, qi + 1, len(raw_results), attempt,
                    )
                    break  # valid outcome — search worked, URLs just dead
                else:
                    # Zero results — valid "no data" outcome
                    _record_success()
                    logger.info(
                        "Dot %d query %d: 0 results (attempt %d)",
                        dot_number, qi + 1, attempt,
                    )
                    break

            except asyncio.TimeoutError:
                last_exc = TimeoutError(f"DDG search timed out after {SEARCH_TIMEOUT}s")
                if attempt <= MAX_QUERY_RETRIES:
                    delay_s = 2 ** attempt  # 2s, 4s
                    logger.warning(
                        "Dot %d query %d timeout attempt %d/%d, retrying in %.1fs",
                        dot_number, qi + 1, attempt, MAX_QUERY_RETRIES + 1, delay_s,
                    )
                    await asyncio.sleep(delay_s)
                else:
                    logger.error(
                        "Dot %d query %d exhausted all attempts (timeout): %s",
                        dot_number, qi + 1, last_exc,
                    )
                    _record_failure()

            except Exception as exc:
                last_exc = exc
                if attempt <= MAX_QUERY_RETRIES:
                    delay_s = 2 ** attempt  # 2s, 4s
                    logger.warning(
                        "Dot %d query %d attempt %d/%d failed, retrying in %.1fs: %s",
                        dot_number, qi + 1, attempt, MAX_QUERY_RETRIES + 1, delay_s, exc,
                    )
                    await asyncio.sleep(delay_s)
                else:
                    logger.error(
                        "Dot %d query %d exhausted %d attempts: %s",
                        dot_number, qi + 1, MAX_QUERY_RETRIES + 1, exc,
                    )
                    _record_failure()

    # Limit results to top-N across all queries
    if len(all_results) > TOP_RESULTS:
        all_results = all_results[:TOP_RESULTS]

    return all_results, any_success


# ── LLM synthesis ──────────────────────────────────────────────────────────


async def synthesize_dot(
    dot_number: int,
    search_results: list[dict[str, str]],
    tier: str,
    context_note: str = "",
) -> dict[str, Any]:
    """Synthesize web search results into a narrative summary via LLM.

    When search results are empty, returns an honest "no data" note
    rather than letting the LLM infer from training data.

    Uses the Jinja2 template at prompts/qualitative_synthesis.j2 for
    prompt construction, falling back to inline prompt if template fails.

    Args:
        dot_number: Dot 1-9.
        search_results: List of search result dicts with title/url/snippet.
        tier: The data completeness tier — 'mixed' or 'qualitative'.
        context_note: Optional additional context about the data gap.

    Returns:
        Dict with 'synthesis' (str), 'tokens_used' (int), 'no_data' (bool).
    """
    ctx = DOT_CONTEXT.get(dot_number, {})
    dot_name = ctx.get("name", f"Dot {dot_number}")

    if not search_results:
        return {
            "synthesis": (
                f"No data sources returned for the last 7 days — "
                f"no assessment possible for {dot_name} (Dot {dot_number})."
            ),
            "tokens_used": 0,
            "no_data": True,
        }

    # Build compact search results text for the prompt
    sources_text_parts: list[str] = []
    for i, r in enumerate(search_results, 1):
        title = r.get("title", "Untitled")
        url = r.get("url", "")
        snippet = r.get("snippet", "")
        sources_text_parts.append(
            f"[{i}] {title}\n    URL: {url}\n    {snippet}"
        )
    sources_text = "\n\n".join(sources_text_parts)

    # Render prompt via Jinja2 template
    try:
        template = _JINJA_ENV.get_template("qualitative_synthesis.j2")
        prompt = template.render(
            dot_name=dot_name,
            dot_number=dot_number,
            tier=tier.upper(),
            sources_text=sources_text,
            context_note=context_note or "",
        )
    except Exception:
        logger.warning("Jinja2 template render failed, using inline prompt")
        # Fallback inline prompt
        context_line = f"\nCONTEXT: {context_note}\n" if context_note else ""
        prompt = (
            f"You are a crisis-monitor analyst. Synthesize the following web search\n"
            f'results into a concise, factual 150-250 word narrative about the current\n'
            f'status of the "{dot_name}" indicator (Dot {dot_number}).\n'
            f"\n"
            f"Rules:\n"
            f"- Base your synthesis ONLY on the search results provided below.\n"
            f"- Do NOT infer or add facts from your training data.\n"
            f"- If the results are insufficient, say so honestly.\n"
            f"- Cite source numbers [N] inline where you reference specific facts.\n"
            f"- Write in plain, professional English suitable for a daily newsletter.\n"
            f"- Do NOT use markdown formatting — plain text only.\n"
            f"\n"
            f"TIER: {tier.upper()}\n"
            f"{context_line}\n"
            f"SEARCH RESULTS:\n{sources_text}\n\n"
            f"SYNTHESIS:"
        )

    # Call LLM
    try:
        llm = get_llm(temperature=0.3, timeout=60)
        resp = await llm.ainvoke(prompt)
        content = get_llm_content(resp)

        # Track estimated tokens
        estimated_tokens = (len(prompt) + len(content)) // 4
        track_token_usage(estimated_tokens)

        # Clean up content — strip markdown fences
        content = content.strip()
        if content.startswith("```"):
            nl = content.find("\n")
            if nl > 0:
                content = content[nl + 1:]
            if content.endswith("```"):
                content = content[:-3].strip()

        # Truncate to roughly 150-250 words (~1200 chars max)
        if len(content) > 1200:
            trunc = content[:1200]
            last_period = max(trunc.rfind("."), trunc.rfind("!"), trunc.rfind("?"))
            if last_period > 800:
                content = content[:last_period + 1]

        return {
            "synthesis": content,
            "tokens_used": estimated_tokens,
            "no_data": False,
        }
    except Exception as exc:
        logger.error("LLM synthesis failed for dot %d: %s", dot_number, exc)
        # Fallback: construct a minimal summary from result snippets
        fallback_parts = []
        for r in search_results[:3]:
            snippet = r.get("snippet", "")
            if snippet:
                fallback_parts.append(f"- {snippet[:200]}")
        fallback = (
            f"LLM synthesis unavailable for {dot_name}. "
            f"Raw search snippets (up to 3):\n" + "\n".join(fallback_parts)
            if fallback_parts
            else f"LLM synthesis and web search failed for {dot_name}."
        )
        return {
            "synthesis": fallback,
            "tokens_used": 0,
            "no_data": len(fallback_parts) == 0,
        }


# ── Main entry points ──────────────────────────────────────────────────────


async def synthesize_dot_qualitative(
    dot_number: int,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convenience function: run qualitative fallback for a single dot.

    This is the primary API matching the AC signature:
        synthesize_dot_qualitative(7, {'tier': 'qualitative', 'name': '...', 'context': '...'})
        → returns synthesized text

    Args:
        dot_number: Dot 1-9.
        context: Dict with optional keys:
            - 'tier': Data completeness tier (default 'qualitative').
            - 'name': Override dot name for query formulation.
            - 'context': Narrative context about the data gap.

    Returns:
        Dict with keys: synthesis, sources, tokens_used, search_success, no_data.
    """
    if context is None:
        context = {}

    tier = context.get("tier", "qualitative")
    context_note = context.get("context", "")

    return await run_qualitative_fallback(
        dot_number=dot_number,
        dot_context=context,
        tier=tier,
        context_note=context_note,
    )


async def run_qualitative_fallback(
    dot_number: int,
    dot_context: dict[str, Any] | None = None,
    tier: str = "qualitative",
    context_note: str = "",
) -> dict[str, Any]:
    """Run qualitative fallback for a single dot: search + synthesize.

    This is the main entry point called by pipeline_runner for each
    MIXED or QUALITATIVE dot.

    Args:
        dot_number: Dot 1-9.
        dot_context: Optional additional context dict for query formulation
                     and synthesis. Keys: 'name', 'context'.
        tier: The data completeness tier — 'mixed' or 'qualitative'.
        context_note: Optional narrative about the data gap for LLM prompt.

    Returns:
        Dict with:
        - 'synthesis' (str): Narrative summary of web findings.
        - 'sources' (list): Search result dicts used.
        - 'tokens_used' (int): Estimated tokens consumed.
        - 'search_success' (bool): Whether web search returned results.
        - 'no_data' (bool): True when no data was available at all.
    """
    # Phase 1: Web search
    search_results, search_success = await search_dot(dot_number, dot_context)

    # Phase 2: LLM synthesis
    synthesis = await synthesize_dot(
        dot_number, search_results, tier, context_note=context_note,
    )

    # Phase 3: Persist sources to DB
    _persist_sources(dot_number, search_results)

    return {
        "synthesis": synthesis["synthesis"],
        "sources": search_results,
        "tokens_used": synthesis.get("tokens_used", 0),
        "search_success": search_success,
        "no_data": synthesis.get("no_data", not search_success),
    }


def _persist_sources(dot_number: int, search_results: list[dict[str, str]]) -> None:
    """Save search results to the qualitative_sources table.

    Args:
        dot_number: Dot number this search was for.
        search_results: List of validated search result dicts.
    """
    if not search_results:
        return
    try:
        conn = get_db()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        for r in search_results:
            conn.execute(
                """INSERT INTO qualitative_sources
                   (dot_number, query, source_url, source_title, snippet,
                    retrieved_at, source_type)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    dot_number,
                    "DuckDuckGo qualitative fallback",
                    r.get("url", ""),
                    r.get("title", ""),
                    r.get("snippet", ""),
                    now,
                    "duckduckgo",
                ),
            )
        conn.commit()
        conn.close()
        logger.debug(
            "Persisted %d sources for dot %d to qualitative_sources",
            len(search_results), dot_number,
        )
    except Exception:
        logger.warning(
            "Failed to persist qualitative sources for dot %d", dot_number,
            exc_info=True,
        )


# ── Run-level helpers ──────────────────────────────────────────────────────


def init_fallback_run() -> None:
    """Initialize qualitative fallback state for a new pipeline run.

    Resets the circuit breaker, seen URLs, and token cost counters.
    Call this at the start of each pipeline execution.
    """
    _reset_circuit()
    reset_token_cost()
    logger.info("Qualitative fallback initialized for new pipeline run")


def get_fallback_cost() -> dict[str, Any]:
    """Get cumulative token cost for qualitative fallback LLM calls.

    Returns:
        Dict with 'total_tokens' and 'total_cost_estimate'.
    """
    return get_token_cost()
