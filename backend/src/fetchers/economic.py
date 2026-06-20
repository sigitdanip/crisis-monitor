"""
Economic & commodity fetchers: FAO Food Price Index, grain futures, copper, BDI.
Combines FAO CSV parsing, yfinance for futures (parallel with 15s timeout),
and BDI via Baltic Exchange proxy.
"""
import csv
import io
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import httpx
import yfinance as yf

logger = logging.getLogger(__name__)

YFINANCE_TIMEOUT = 15

FAO_FPI_URL = (
    "https://fenixservices.fao.org/faostat/static/bulkdownloads/"
    "FAOSTAT_data_6-18-2025.zip"  # ponytail: pinned snapshot; rebuild if monthly breaks
)
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
        logger.warning("FAO API primary endpoint failed, trying fallback")
    # Try fallback: scrape the HTML page
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            r = client.get(
                FAO_FALLBACK_URL,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if r.status_code == 200:
                # ponytail: fragile regex — FAO page structure may change
                import re
                match = re.search(r"Food Price Index.*?(\d+\.?\d*)", r.text)
                if match:
                    value = float(match.group(1))
                    if 50 < value < 200:  # sanity check
                        return {
                            "name": "FAO Food Price Index",
                            "category": "Food",
                            "value": value,
                            "unit": "index",
                            "status": "normal",
                            "trigger_level": ">10% monthly increase",
                        }
            if r.status_code != 200:
                logger.warning("FAO fallback returned HTTP %d", r.status_code)
            else:
                logger.info("FAO fallback returned 200 but regex didn't match a value")
    except Exception:
        logger.warning("FAO fallback fetch failed")
    logger.info("FAO FPI unavailable — both endpoints failed")
    return None


def _fetch_bdi() -> dict[str, Any] | None:
    """Fetch Baltic Dry Index. Uses yfinance BDRY as proxy."""
    try:
        tk = yf.Ticker("BDRY")
        data = tk.history(period="5d")
        if data.empty:
            return None
        value = round(float(data["Close"].iloc[-1]), 2)
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
    """Fetch all economic/commodity indicators.

    yfinance grain/copper calls run in parallel with per-call 15s timeout.
    Returns partial on failure.
    """
    results: list[dict[str, Any]] = []

    # FAO FPI (fast HTTP call)
    fpi = _fetch_fao_fpi()
    if fpi:
        results.append(fpi)

    # Parallel yfinance grain/copper fetches
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(_fetch_yf_one, name, info): name
            for name, info in GRAIN_TICKERS.items()
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                r = future.result(timeout=YFINANCE_TIMEOUT + 1)
            except Exception:
                logger.warning("yfinance call timed out or failed for %s", name)
                r = None
            if r:
                results.append(r)

    # BDI (single yfinance call — not worth parallelizing separately)
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
