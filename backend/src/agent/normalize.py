"""Normalization layer — converts fetcher output (list of dicts) into
the flat Dict[str, Any] format the agent graph expects."""

from typing import Dict, Any, List
from src.fetchers.market import fetch_all_market
from src.fetchers.credit import fetch_all_credit
from src.fetchers.economic import fetch_all_economic
from src.fetchers.currencies import fetch_all_currencies
from src.fetchers.energy_storage import fetch_all_energy_storage
from src.fetchers.news import fetch_all_news


def _to_lookup(fetched: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Convert list of {name, value, ...} to {name: value} lookup."""
    return {item["name"]: item.get("value") for item in fetched if item.get("value") is not None}


def fetch_and_normalize():
    """Run all fetchers, normalize to flat dict for the agent graph.
    
    Returns a dict with keys matching what composite_scorer and dot_analyzers expect.
    """
    # Run all fetchers (all sync)
    market = fetch_all_market()
    credit = fetch_all_credit()
    economic = fetch_all_economic()
    currencies = fetch_all_currencies()
    energy = fetch_all_energy_storage()
    news_data = fetch_all_news()

    # Build flat lookup by indicator name
    m = _to_lookup(market)
    c = _to_lookup(credit)
    e = _to_lookup(economic)
    cur = _to_lookup(currencies)
    en = _to_lookup(energy)

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
        "ig_oas": c.get("IG OAS"),
        "hy_oas": c.get("HY OAS"),

        # Food
        "fao_monthly_change_pct": e.get("FAO Food Price Index"),
        "cme_grains_monthly_pct": e.get("CME Grains Index"),

        # China
        "caixin_pmi": cur.get("Caixin PMI"),
        "shibor_1w": cur.get("SHIBOR 1W"),

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

    # News data — extract headline text from list-of-dict fetcher output
    news_headlines = [item.get("name", "") for item in news_data if item.get("name")]
    news_dicts = [{"title": h} for h in news_headlines]

    return indicators, news_dicts
