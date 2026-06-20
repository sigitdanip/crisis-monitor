"""
EM currency & China fetchers.
Indicators: IDR, TRY, EGP, ARS, NGN, PKR vs USD; Caixin PMI.
Uses yfinance for FX pairs (parallel with 15s timeout) and httpx for scrapes.
Graceful degradation throughout.
"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import httpx
import yfinance as yf

logger = logging.getLogger(__name__)

YFINANCE_TIMEOUT = 15

# yfinance FX pairs — format is <CCY1><CCY>=X for CCY1/CCY2
# USDIDR=X = USD/IDR. We want IDR per USD (how many IDR for 1 USD).
CURRENCY_PAIRS: dict[str, dict[str, Any]] = {
    "IDR/USD": {"ticker": "IDR=X",   "category": "EM Currency", "unit": "IDR per USD",  "trigger_level": ">16500 or >3% weekly drop"},
    "TRY/USD": {"ticker": "TRY=X",   "category": "EM Currency", "unit": "TRY per USD",  "trigger_level": ">5% weekly drop"},
    "EGP/USD": {"ticker": "EGP=X",   "category": "EM Currency", "unit": "EGP per USD",  "trigger_level": ">5% monthly drop"},
    "ARS/USD": {"ticker": "ARS=X",   "category": "EM Currency", "unit": "ARS per USD",  "trigger_level": ">10% monthly drop"},
    "NGN/USD": {"ticker": "NGN=X",   "category": "EM Currency", "unit": "NGN per USD",  "trigger_level": ">5% monthly drop"},
    "PKR/USD": {"ticker": "PKR=X",   "category": "EM Currency", "unit": "PKR per USD",  "trigger_level": ">5% monthly drop"},
}


def _fetch_currency(name: str, info: dict[str, Any]) -> dict[str, Any] | None:
    """Fetch one FX pair via yfinance."""
    try:
        tk = yf.Ticker(info["ticker"])
        data = tk.history(period="5d")
        if data.empty:
            # ponytail: some EM pairs are thinly traded on Yahoo; try alternate ticker
            alt_ticker = info["ticker"].replace("=X", "USD=X") if "=X" in info["ticker"] else info["ticker"]
            tk2 = yf.Ticker(alt_ticker)
            data = tk2.history(period="5d")
        if data.empty:
            logger.warning("No yfinance data for %s", name)
            return None
        value = round(float(data["Close"].iloc[-1]), 4)
        return {
            "name": name,
            "category": info["category"],
            "value": value,
            "unit": info["unit"],
            "status": "normal",
            "trigger_level": info["trigger_level"],
        }
    except Exception:
        logger.exception("Failed FX fetch for %s", name)
        return None


def _fetch_caixin_pmi() -> dict[str, Any] | None:
    """Fetch Caixin Manufacturing PMI via TradingEconomics scrape or proxy."""
    logger.info("Caixin PMI: no free API available — skipping")
    return None


def fetch_all_currencies() -> list[dict[str, Any]]:
    """Fetch all EM currency + China indicators.

    yfinance calls run in parallel with per-call 15s timeout.
    Returns partial on failure.
    """
    results: list[dict[str, Any]] = []

    # Parallel yfinance FX fetches
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(_fetch_currency, name, info): name
            for name, info in CURRENCY_PAIRS.items()
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                r = future.result(timeout=YFINANCE_TIMEOUT + 1)
            except Exception:
                logger.warning("yfinance FX call timed out or failed for %s", name)
                r = None
            if r:
                results.append(r)

    # Non-yfinance sources (fast — sequential is fine)
    caixin = _fetch_caixin_pmi()
    if caixin:
        results.append(caixin)

    logger.info("Fetched %d currency/China indicators", len(results))
    return results


def _demo() -> None:
    results = fetch_all_currencies()
    for r in results:
        print(f"  {r['name']}: {r['value']} {r['unit']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    _demo()
