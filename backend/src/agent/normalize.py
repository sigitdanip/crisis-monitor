"""Normalization layer — converts fetcher output (list of dicts) into
the flat Dict[str, Any] format the agent graph expects.

Fetchers run in parallel via ThreadPoolExecutor to keep total fetch time
at max(slowest fetcher) instead of sum(all fetchers). This is critical
because yfinance calls have no built-in timeout and can take 10-30s each.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List
from src.fetchers.market import fetch_all_market
from src.fetchers.credit import fetch_all_credit
from src.fetchers.economic import fetch_all_economic
from src.fetchers.currencies import fetch_all_currencies
from src.fetchers.energy_storage import fetch_all_energy_storage
from src.fetchers.news import fetch_all_news
from src.fetchers.news_indicators import fetch_all_news_indicators


# News-derived indicator name → slug mapping
# The slug is used as the key in the indicators dict and must match
# entries in INDICATOR_META (indicator_narrator.py).
NEWS_SLUG_MAP: Dict[str, str] = {
    "Caixin PMI (News)": "news_caixin_pmi",
    "EU Gas Storage (News)": "news_eu_gas",
    "US SPR (News)": "news_us_spr",
    "Protest Countries (News)": "news_protest_countries",
}


def _to_lookup(fetched: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Convert list of {name, value, ...} to {name: value} lookup."""
    return {item["name"]: item.get("value") for item in fetched if item.get("value") is not None}


def _news_to_lookup(fetched: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Convert news-derived indicator results to slug → {value, narrative} dict.

    Each entry stores both the 0/1 flag value and the headline narrative,
    so downstream synthesis can use the narrative in LLM prompts.
    """
    result: Dict[str, Any] = {}
    for item in fetched:
        name = item.get("name", "")
        slug = NEWS_SLUG_MAP.get(name)
        if slug is None:
            continue
        value = item.get("value")
        narrative = item.get("narrative", "")
        if value is not None:
            result[slug] = {"value": value, "narrative": narrative}
    return result


def fetch_and_normalize():
    """Run all fetchers in parallel, normalize to flat dict for the agent graph.

    Returns a dict with keys matching what composite_scorer and dot_analyzers expect.
    """
    # Run all 7 fetchers in parallel threads — reduces total fetch time
    # from sum(all) to max(slowest). yfinance calls are the bottleneck.
    fetchers = {
        "market": fetch_all_market,
        "credit": fetch_all_credit,
        "economic": fetch_all_economic,
        "currencies": fetch_all_currencies,
        "energy": fetch_all_energy_storage,
        "news": fetch_all_news,
        "news_indicators": fetch_all_news_indicators,
    }

    results: Dict[str, List[Dict[str, Any]]] = {}
    with ThreadPoolExecutor(max_workers=7) as executor:
        futures = {executor.submit(fn): name for name, fn in fetchers.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception:
                # Graceful degradation — one failing fetcher doesn't block others.
                # The logger in each fetcher already logged the specific error.
                results[name] = []

    market = results.get("market", [])
    credit = results.get("credit", [])
    economic = results.get("economic", [])
    currencies = results.get("currencies", [])
    energy = results.get("energy", [])
    news_data = results.get("news", [])
    news_indicators = results.get("news_indicators", [])

    # Build flat lookup by indicator name
    m = _to_lookup(market)
    c = _to_lookup(credit)
    e = _to_lookup(economic)
    cur = _to_lookup(currencies)
    en = _to_lookup(energy)

    # Build news-derived indicator lookup (slug → {value, narrative})
    news_flags = _news_to_lookup(news_indicators)

    # Map to scorer-expected keys
    indicators = {
        # Energy
        "brent_price": m.get("Brent Crude"),
        "wti_price": m.get("WTI Crude"),
        "natgas_price": m.get("Natural Gas"),

        # Financial
        "dxy": m.get("DXY"),
        "gold_price": m.get("Gold"),
        "us_10y": m.get("US 10Y Yield"),
        "us_2y": m.get("US 2Y Yield"),
        "vix": m.get("VIX"),

        # Credit
        "ig_oas": c.get("US IG OAS"),
        "hy_oas": c.get("US HY OAS"),

        # Food
        "fao_monthly_change_pct": e.get("FAO Food Price Index"),
        "cme_grains_monthly_pct": e.get("CME Grains Index"),

        # China
        "caixin_pmi": cur.get("Caixin PMI"),

        # Debt
        "btp_bund_spread": c.get("BTP-Bund Spread"),

        # Energy storage
        "eu_gas_storage_pct": en.get("EU Gas Storage"),
        "us_spr_mbbl": en.get("US SPR"),

        # EM currencies
        "idr_breach": 1 if cur.get("IDR/USD") and cur["IDR/USD"] > 16500 else 0,
        "try_breach": 1 if cur.get("TRY/USD") and cur["TRY/USD"] > 35 else 0,
        "egp_breach": 1 if cur.get("EGP/USD") and cur["EGP/USD"] > 50 else 0,

        # Geopolitical / Political (from news-based LLM assessment — pass raw for now)
        "nato_fracture": 0,   # assessed by Agent 1
        "hormuz_closure": "",  # assessed by Agent 1
        "us_nato_withdrawal": 0,
        "protest_countries": 0,  # assessed by Agent 4
        "govt_crisis": 0,
        "china_property_default": 0,
        "cds_doubling": 0,
    }

    # Merge news-derived flag indicators (each stored as {value, narrative})
    indicators.update(news_flags)

    # News data — extract headline text from list-of-dict fetcher output
    news_headlines = [item.get("name", "") for item in news_data if item.get("name")]
    news_dicts = [{"title": h} for h in news_headlines]

    return indicators, news_dicts
