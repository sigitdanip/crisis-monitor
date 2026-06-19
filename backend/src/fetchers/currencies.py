"""
EM currency & China fetchers.
Indicators: IDR, TRY, EGP, ARS, NGN, PKR vs USD; SHIBOR 1W; Caixin PMI.
Uses yfinance for FX pairs and httpx for scrapes. Graceful degradation.
"""
import logging
import re
from typing import Any

import httpx
import yfinance as yf

logger = logging.getLogger(__name__)

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


def _fetch_shibor() -> dict[str, Any] | None:
    """Fetch SHIBOR 1W from shibor.org via scrape."""
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(
                "https://www.shibor.org/shibor/web/html/shibor.html",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            r.raise_for_status()
            # ponytail: quick regex scrape; if site restructures, use API fallback
            match = re.search(r"1W[<>\s\w/]*?(\d+\.\d+)", r.text, re.IGNORECASE)
            if not match:
                match = re.search(r"隔夜.*?(\d+\.\d+).*?1W.*?(\d+\.\d+)", r.text)
                value = float(match.group(2)) if match else None
            else:
                value = float(match.group(1))
            if value is None:
                return None
            return {
                "name": "SHIBOR 1W",
                "category": "China",
                "value": value,
                "unit": "%",
                "status": "normal",
                "trigger_level": ">4.5% or sudden +100bps jump",
            }
    except Exception:
        logger.exception("SHIBOR scrape failed")
        return None


def _fetch_caixin_pmi() -> dict[str, Any] | None:
    """Fetch Caixin Manufacturing PMI via TradingEconomics scrape or proxy."""
    # ponytail: free scrape unreliable; return None rather than fake data
    # The composite scorer can mark this as 'unknown' until a reliable source is wired
    logger.info("Caixin PMI: no free API available — skipping")
    return None


def fetch_all_currencies() -> list[dict[str, Any]]:
    """Fetch all EM currency + China indicators. Returns partial on failure."""
    results: list[dict[str, Any]] = []

    for name, info in CURRENCY_PAIRS.items():
        r = _fetch_currency(name, info)
        if r:
            results.append(r)

    shibor = _fetch_shibor()
    if shibor:
        results.append(shibor)

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
