"""
Market data fetchers using yfinance.
Indicators: Brent crude, WTI, natural gas, DXY, gold, US 10Y, US 2Y, VIX.
"""
import logging
from typing import Any

import yfinance as yf

logger = logging.getLogger(__name__)

# ponytail: global lock — yfinance downloads are sequential per module;
# parallel fetch across modules via LangGraph is the scaling path.
TICKERS: dict[str, dict[str, Any]] = {
    "Brent Crude":    {"ticker": "BZ=F",   "category": "Energy",        "unit": "USD/bbl",    "trigger_level": ">100 for 1 week"},
    "WTI Crude":      {"ticker": "CL=F",   "category": "Energy",        "unit": "USD/bbl",    "trigger_level": ">95 for 1 week"},
    "Natural Gas":    {"ticker": "NG=F",   "category": "Energy",        "unit": "USD/MMBtu",  "trigger_level": ">5"},
    "DXY":            {"ticker": "DX-Y.NYB", "category": "Financial",   "unit": "index",      "trigger_level": "<95 AND >3% 2-week drop"},
    "Gold":           {"ticker": "GC=F",   "category": "Financial",     "unit": "USD/oz",     "trigger_level": ">3500 or >15% monthly"},
    "US 10Y Yield":   {"ticker": "^TNX",   "category": "Financial",     "unit": "%",          "trigger_level": ">5.5"},
    "US 2Y Yield":    {"ticker": "2YY=F",  "category": "Financial",     "unit": "%",          "trigger_level": "inversion vs 10Y"},
    "VIX":            {"ticker": "^VIX",   "category": "Financial",     "unit": "index",      "trigger_level": ">35"},
}


def _fetch_one(name: str, info: dict[str, Any]) -> dict[str, Any] | None:
    """Fetch a single indicator via yfinance. Returns None on failure."""
    try:
        tk = yf.Ticker(info["ticker"])
        data = tk.history(period="2d")
        if data.empty:
            logger.warning("yfinance returned no data for %s (%s)", name, info["ticker"])
            return None
        value = round(float(data["Close"].iloc[-1]), 2)
        prev = round(float(data["Close"].iloc[0]), 2) if len(data) > 1 else None
        change = round(value - prev, 2) if prev else None
        return {
            "name": name,
            "category": info["category"],
            "value": value,
            "unit": info["unit"],
            "status": "normal",  # scored later by composite_scorer
            "trigger_level": info["trigger_level"],
            "change": change,
        }
    except Exception:
        logger.exception("Failed to fetch %s via yfinance", name)
        return None


def fetch_all_market() -> list[dict[str, Any]]:
    """Fetch all 8 market indicators. Graceful degradation: returns partial on failure."""
    results: list[dict[str, Any]] = []
    for name, info in TICKERS.items():
        result = _fetch_one(name, info)
        if result:
            results.append(result)
    logger.info("Fetched %d/%d market indicators", len(results), len(TICKERS))
    return results


def _demo() -> None:
    """Quick self-check: prints first 3 indicators."""
    results = fetch_all_market()
    assert len(results) >= 1, f"Expected at least 1 indicator, got {len(results)}"
    for r in results[:3]:
        print(f"  {r['name']}: {r['value']} {r['unit']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    _demo()
