"""
Market data fetchers using yfinance.
Indicators: Brent crude, WTI, natural gas, DXY, gold, US 10Y, US 2Y, VIX.

Each yfinance call runs with a 15s per-call timeout via ThreadPoolExecutor
because yfinance has no built-in timeout and history() can hang 30s+.
"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import yfinance as yf

logger = logging.getLogger(__name__)

# Per-ticker timeout for yfinance calls (seconds).
YFINANCE_TIMEOUT = 15

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
    """Fetch all 8 market indicators in parallel with per-call 15s timeout.

    Graceful degradation: returns partial on failure or timeout.
    """
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(_fetch_one, name, info): name
            for name, info in TICKERS.items()
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                result = future.result(timeout=YFINANCE_TIMEOUT + 1)
            except Exception:
                logger.warning("yfinance call timed out or failed for %s", name)
                result = None
            if result:
                results.append(result)
    logger.info("Fetched %d/%d market indicators", len(results), len(TICKERS))
    return results


# Gold 200-day Moving Average cache
_gold_ma_cache: dict[str, float | None] = {"value": None, "fetched_at": 0.0}


def fetch_gold_200d_ma(ticker_symbol: str = "GC=F") -> float | None:
    """Fetch 200-day moving average for gold from yfinance.

    Cached — only re-fetches if the value was never fetched.
    MA changes slowly (1 data point per trading day), so this is safe
    across multiple pipeline runs in the same process.

    Returns:
        Mean of last 200 days' closing prices, or None on failure.
    """
    import time as _time

    now = _time.time()
    if _gold_ma_cache["value"] is not None and (now - _gold_ma_cache["fetched_at"]) < 3600:
        return _gold_ma_cache["value"]

    try:
        tk = yf.Ticker(ticker_symbol)
        data = tk.history(period="200d")
        if data.empty or len(data) < 10:
            logger.warning("Gold MA: insufficient data (%d rows) from yfinance", len(data))
            return None
        ma = float(data["Close"].mean())
        _gold_ma_cache["value"] = round(ma, 2)
        _gold_ma_cache["fetched_at"] = now
        logger.info("Gold 200-day MA: %.2f (from %d trading days)", ma, len(data))
        return ma
    except Exception:
        logger.exception("Failed to fetch gold 200-day MA")
        return None


def _demo() -> None:
    """Quick self-check: prints first 3 indicators."""
    results = fetch_all_market()
    assert len(results) >= 1, f"Expected at least 1 indicator, got {len(results)}"
    for r in results[:3]:
        print(f"  {r['name']}: {r['value']} {r['unit']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    _demo()
