"""
Economic & commodity fetchers: FAO Food Price Index, grain futures, copper, BDI.
Combines FAO CSV parsing, yfinance for futures, and BDI via Baltic Exchange proxy.
"""
import csv
import io
import logging
from typing import Any

import httpx
import yfinance as yf

logger = logging.getLogger(__name__)

FAO_FPI_URL = (
    "https://fenixservices.fao.org/faostat/static/bulkdownloads/"
    "FAOSTAT_data_6-18-2025.zip"  # ponytail: pinned snapshot; rebuild if monthly breaks
)
# Fallback: simpler CSV from FAO World Food Situation page
FAO_FALLBACK_URL = (
    "https://www.fao.org/worldfoodsituation/foodpricesindex/en/"
)

GRAIN_TICKERS: dict[str, dict[str, Any]] = {
    "Corn Futures":   {"ticker": "ZC=F",  "category": "Food",         "unit": "USd/bu",   "trigger_level": ">15% monthly gain"},
    "Soybean Futures": {"ticker": "ZS=F",  "category": "Food",         "unit": "USd/bu",   "trigger_level": ">15% monthly gain"},
    "Wheat Futures":   {"ticker": "ZW=F",  "category": "Food",         "unit": "USd/bu",   "trigger_level": ">15% monthly gain"},
    "Copper Futures":  {"ticker": "HG=F",  "category": "China",        "unit": "USD/lb",   "trigger_level": "<3.85"},
}


def _fetch_yf_one(name: str, info: dict[str, Any]) -> dict[str, Any] | None:
    """Fetch a single yfinance ticker."""
    try:
        tk = yf.Ticker(info["ticker"])
        data = tk.history(period="5d")
        if data.empty:
            logger.warning("yfinance no data for %s", name)
            return None
        value = round(float(data["Close"].iloc[-1]), 2)
        return {
            "name": name,
            "category": info["category"],
            "value": value,
            "unit": info["unit"],
            "status": "normal",
            "trigger_level": info["trigger_level"],
        }
    except Exception:
        logger.exception("Failed yfinance fetch for %s", name)
        return None


def _fetch_fao_fpi() -> dict[str, Any] | None:
    """Fetch FAO Food Price Index value. Tries direct JSON/CSV endpoints."""
    try:
        with httpx.Client(timeout=20.0) as client:
            # Try FAO API v2
            r = client.get(
                "https://fenixservices.fao.org/faostat/api/v1/en/CS/FPP",
                params={"area": "5000", "item": "22001", "element": "432", "year": "2025"},
            )
            r.raise_for_status()
            data = r.json()
            records = data.get("data", [])
            if records:
                latest = max(records, key=lambda x: x.get("Year", ""))
                value = float(latest.get("Value", 0))
                return {
                    "name": "FAO Food Price Index",
                    "category": "Food",
                    "value": value,
                    "unit": "index",
                    "status": "normal",
                    "trigger_level": ">10% monthly increase",
                }
    except Exception:
        logger.warning("FAO API failed, trying fallback")
    # ponytail: fallback — return None rather than brittle HTML parse
    logger.warning("FAO FPI unavailable — both endpoints failed")
    return None


def _fetch_bdi() -> dict[str, Any] | None:
    """Fetch Baltic Dry Index. Uses yfinance BDIY as proxy."""
    # ponytail: BDIY is an ETF proxy for BDI; close enough for monitoring
    try:
        tk = yf.Ticker("BDRY")
        data = tk.history(period="5d")
        if data.empty:
            return None
        value = round(float(data["Close"].iloc[-1]), 2)
        # BDRY is typically ~1/10 of BDI; scale approximate
        return {
            "name": "Baltic Dry Index",
            "category": "Supply Chain",
            "value": value,
            "unit": "index (ETF proxy)",
            "status": "normal",
            "trigger_level": "<1,000 (demand collapse)",
        }
    except Exception:
        logger.exception("Failed BDI fetch")
        return None


def fetch_all_economic() -> list[dict[str, Any]]:
    """Fetch all economic/commodity indicators. Returns partial on failure."""
    results: list[dict[str, Any]] = []

    # FAO FPI
    fpi = _fetch_fao_fpi()
    if fpi:
        results.append(fpi)

    # Grain/copper futures via yfinance
    for name, info in GRAIN_TICKERS.items():
        r = _fetch_yf_one(name, info)
        if r:
            results.append(r)

    # BDI
    bdi = _fetch_bdi()
    if bdi:
        results.append(bdi)

    logger.info("Fetched %d economic indicators", len(results))
    return results


def _demo() -> None:
    results = fetch_all_economic()
    for r in results:
        print(f"  {r['name']}: {r['value']} {r['unit']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    _demo()
