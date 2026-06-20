"""
News-derived indicator fetchers.

Qualitative 0/1 flags derived from NewsAPI headlines for indicators
that lack a free structured-data source:

- fetch_news_caixin_pmi()       → Caixin PMI sentiment from China econ headlines
- fetch_news_eu_gas()            → EU gas storage narrative from energy headlines
- fetch_news_us_spr()            → US SPR drawdown signals from oil reserve headlines
- fetch_news_protest_countries() → Protest/demonstration flags from unrest headlines

Each function makes exactly 1 NewsAPI call, runs with a 5-second timeout,
and returns a dict with a 0/1 flag value, a narrative of the top 3 headlines,
and a source='newsapi' attribution. Returns None on timeout/error (graceful
degradation — the pipeline never crashes on a single fetcher failure).

NewsAPI free tier: 100 requests/day. These 4 functions = 4 requests/day total.
"""
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

NEWSAPI_URL = "https://newsapi.org/v2/everything"
TIMEOUT = 5.0
NARRATIVE_SEPARATOR = " | "
NARRATIVE_MAX_CHARS = 200
HEADLINE_COUNT = 3


def _newsapi_key() -> str | None:
    """Return NEWS_API_KEY from environment, or None if not set."""
    key = os.environ.get("NEWS_API_KEY")
    if not key:
        logger.info("NEWS_API_KEY not set — skipping news-derived indicator")
    return key


def _from_date() -> str:
    """Return ISO-format date 7 days ago (NewsAPI free tier uses this for recency)."""
    return (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")


def _fetch_newsapi_indicator(
    query: str,
    name: str,
    category: str,
    trigger_words: list[str],
) -> dict[str, Any] | None:
    """Generic NewsAPI fetcher for a single indicator.

    Args:
        query: NewsAPI search query string (topic keywords).
        name: Human-readable indicator name.
        category: Indicator category (e.g. 'China', 'Energy', 'Political').
        trigger_words: List of lowercase trigger phrases. If any appear in
                       the title or description of a recent article, value=1.

    Returns:
        Dict with keys: name, category, value (0 or 1), unit, narrative,
        source, status — or None on failure/timeout.
    """
    api_key = _newsapi_key()
    if not api_key:
        return None

    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            r = client.get(
                NEWSAPI_URL,
                params={
                    "q": query,
                    "apiKey": api_key,
                    "from": _from_date(),
                    "pageSize": HEADLINE_COUNT,
                    "sortBy": "publishedAt",
                    "language": "en",
                },
            )
            r.raise_for_status()
            articles = r.json().get("articles", [])
    except httpx.TimeoutException:
        logger.warning("NewsAPI timeout for indicator '%s' (query: %s)", name, query)
        return None
    except Exception:
        logger.exception("NewsAPI error for indicator '%s' (query: %s)", name, query)
        return None

    # Build narrative from top headlines
    headlines: list[str] = []
    for art in articles:
        title = (art.get("title") or "").strip()
        if title:
            headlines.append(title)

    narrative_raw = NARRATIVE_SEPARATOR.join(headlines[:HEADLINE_COUNT])
    narrative = narrative_raw[:NARRATIVE_MAX_CHARS]

    # Check for trigger words in title + description (case-insensitive)
    triggered = False
    for art in articles:
        text = (
            (art.get("title") or "")
            + " "
            + (art.get("description") or "")
        ).lower()
        if any(tw in text for tw in trigger_words):
            triggered = True
            break

    value = 1 if triggered else 0
    status = "breached" if triggered else "normal"

    logger.info(
        "News-derived indicator '%s': value=%d, headlines=%d, triggered=%s",
        name,
        value,
        len(headlines),
        triggered,
    )

    return {
        "name": name,
        "category": category,
        "value": value,
        "unit": "flag",
        "narrative": narrative,
        "source": "newsapi",
        "status": status,
    }


# ---- Public fetcher functions (one per indicator) ----

def fetch_news_caixin_pmi() -> dict[str, Any] | None:
    """Caixin PMI sentiment from China manufacturing/economic headlines."""
    return _fetch_newsapi_indicator(
        query='"Caixin PMI" OR "China manufacturing" OR "China PMI"',
        name="Caixin PMI (News)",
        category="China",
        trigger_words=["contraction", "pmi", "factory activity", "manufacturing index"],
    )


def fetch_news_eu_gas() -> dict[str, Any] | None:
    """EU gas storage narrative from energy security headlines."""
    return _fetch_newsapi_indicator(
        query='"EU gas storage" OR "European gas reserves" OR "EU energy crisis"',
        name="EU Gas Storage (News)",
        category="Energy",
        trigger_words=["gas storage", "gas reserves", "eu energy security"],
    )


def fetch_news_us_spr() -> dict[str, Any] | None:
    """US SPR drawdown signals from strategic petroleum reserve headlines."""
    return _fetch_newsapi_indicator(
        query='"Strategic Petroleum Reserve" OR "SPR release" OR "US oil reserves"',
        name="US SPR (News)",
        category="Energy",
        trigger_words=["strategic petroleum reserve", "spr release", "oil reserves"],
    )


def fetch_news_protest_countries() -> dict[str, Any] | None:
    """Protest/demonstration flags from global unrest headlines."""
    return _fetch_newsapi_indicator(
        query="protest OR demonstration OR unrest OR riots",
        name="Protest Countries (News)",
        category="Political",
        trigger_words=["protest", "demonstration", "unrest", "riots"],
    )


# ---- Aggregator ----

def fetch_all_news_indicators() -> list[dict[str, Any]]:
    """Fetch all 4 news-derived indicators.

    Each function runs independently. Failures/timeouts are logged and
    produce None, which is filtered out. The pipeline never crashes
    on a single fetcher failure — returns partial results.

    Returns:
        List of 0–4 indicator dicts.
    """
    fetchers = [
        fetch_news_caixin_pmi,
        fetch_news_eu_gas,
        fetch_news_us_spr,
        fetch_news_protest_countries,
    ]
    results: list[dict[str, Any]] = []
    for fn in fetchers:
        try:
            result = fn()
            if result is not None:
                results.append(result)
        except Exception:
            logger.exception("Unexpected error in %s", fn.__name__)
    logger.info("Fetched %d/%d news-derived indicators", len(results), len(fetchers))
    return results


# ---- Demo / self-check ----

def _demo() -> None:
    """Quick self-check: prints fetched indicators."""
    results = fetch_all_news_indicators()
    if not results:
        print("  (no indicators — NEWS_API_KEY may be unset or API down)")
        return
    for r in results:
        flag = r["narrative"][:80] if r["narrative"] else "(no headlines)"
        print(f"  {r['name']}: value={r['value']} status={r['status']} — {flag}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    _demo()
