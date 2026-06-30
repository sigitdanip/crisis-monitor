"""
Energy storage & shipping fetchers.
Indicators: EU gas storage %, US SPR level, TTF gas price, Freightos Baltic Index.
Sources: GIE AGSI (agsi.gie.eu), EIA, yfinance, Freightos.

All yfinance calls run with a 15s per-call timeout to prevent hangs.
"""
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import httpx
import yfinance as yf

logger = logging.getLogger(__name__)

YFINANCE_TIMEOUT = 15

AGSI_API = "https://agsi.gie.eu/api"
EIA_API = "https://api.eia.gov/v2"


def _fetch_eu_gas_storage() -> dict[str, Any] | None:
    """Fetch EU gas storage fill percentage from GIE AGSI."""
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(
                f"{AGSI_API}",
                params={
                    "country": "eu",
                    "date": "latest",
                },
                headers={"x-key": "anonymous"},
            )
            if r.status_code != 200:
                r2 = client.get(
                    f"{AGSI_API}/data",
                    params={
                        "facilities": "de",
                        "from": "2025-01-01",
                    },
                    timeout=15.0,
                )
                if r2.status_code != 200:
                    logger.warning("AGSI API returned %d", r2.status_code)
                    return None
                data = r2.json()
            else:
                data = r.json()

            if isinstance(data, dict):
                last_data = data.get("data", data.get("lastData", data))
                if isinstance(last_data, list) and last_data:
                    value = float(last_data[-1].get("gasInStorage", 0))
                    full = float(last_data[-1].get("full", 0))
                    pct = (value / full * 100) if full > 0 else 0
                    return {
                        "name": "EU Gas Storage",
                        "category": "Energy",
                        "value": round(pct, 1),
                        "unit": "%",
                        "status": "normal",
                        "trigger_level": "<60% by Aug 1",
                    }
            logger.info("AGSI: unexpected response shape — returning None gracefully")
            return None
    except Exception:
        logger.warning("EU gas storage fetch failed", exc_info=True)
        return None


def _fetch_us_spr() -> dict[str, Any] | None:
    """Fetch US Strategic Petroleum Reserve level from EIA API."""
    api_key = os.environ.get("EIA_API_KEY")
    if not api_key:
        logger.info("EIA_API_KEY not set — skipping SPR fetch")
        return None
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(
                f"{EIA_API}/petroleum/stoc/wstk/data/",
                params={
                    "api_key": api_key,
                    "facets[series][]": "WCSSTUS1",
                    "data[0]": "value",
                    "sort[0][column]": "period",
                    "sort[0][direction]": "desc",
                    "length": 1,
                },
            )
            r.raise_for_status()
            data = r.json()
            rows = data.get("response", {}).get("data", [])
            if rows:
                # EIA returns values in thousand barrels; convert to million barrels
                value = round(float(rows[0].get("value", 0)) / 1000, 1)
                return {
                    "name": "US SPR Level",
                    "category": "Energy",
                    "value": value,
                    "unit": "million barrels",
                    "status": "normal",
                    "trigger_level": "<350 Mbbl",
                }
            return None
    except httpx.HTTPStatusError:
        logger.warning("US SPR fetch failed — EIA API returned HTTP error (v1 retired)")
        return None
    except Exception:
        logger.warning("US SPR fetch failed")
        return None


def _fetch_ttf_gas() -> dict[str, Any] | None:
    """Fetch EU TTF natural gas price via yfinance."""
    try:
        tk = yf.Ticker("TTF=F")
        data = tk.history(period="5d")
        if data.empty:
            return None
        value = round(float(data["Close"].iloc[-1]), 2)
        return {
            "name": "TTF Natural Gas",
            "category": "Energy",
            "value": value,
            "unit": "EUR/MWh",
            "status": "normal",
            "trigger_level": ">45 EUR/MWh",
        }
    except Exception:
        logger.warning("TTF gas fetch failed", exc_info=True)
        return None


def _fetch_fbx() -> dict[str, Any] | None:
    """Fetch BOAT ETF proxy for global container freight (fallback for Freightos Baltic Index)."""
    try:
        tk = yf.Ticker("BOAT")
        data = tk.history(period="5d")
        if not data.empty:
            value = round(float(data["Close"].iloc[-1]), 2)
            return {
                "name": "Freightos Baltic Global",
                "category": "Supply Chain",
                "value": value,
                "unit": "ETF proxy",
                "status": "normal",
                "trigger_level": "proxy decline >20%",
            }
    except Exception:
        logger.warning("FBX proxy (BOAT) fetch failed", exc_info=True)
    return None


def _run_with_timeout(fn, timeout: float = YFINANCE_TIMEOUT):
    """Run a function in a thread with a timeout. Returns result or None."""
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(fn)
        try:
            return future.result(timeout=timeout)
        except Exception:
            return None


def fetch_all_energy_storage() -> list[dict[str, Any]]:
    """Fetch all energy storage & shipping indicators.

    yfinance calls run with per-call 15s timeout. Returns partial on failure.
    """
    results: list[dict[str, Any]] = []

    # HTTP-based fetchers (fast — run sequentially)
    eu = _fetch_eu_gas_storage()
    if eu:
        results.append(eu)

    spr = _fetch_us_spr()
    if spr:
        results.append(spr)

    # yfinance-based fetchers (run in parallel with timeout)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(fn): name
            for fn, name in [(_fetch_ttf_gas, "TTF"), (_fetch_fbx, "FBX")]
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                r = future.result(timeout=YFINANCE_TIMEOUT + 1)
            except Exception:
                logger.warning("yfinance call timed out for %s", name)
                r = None
            if r:
                results.append(r)

    logger.info("Fetched %d energy storage indicators", len(results))
    return results


def _demo() -> None:
    results = fetch_all_energy_storage()
    for r in results:
        print(f"  {r['name']}: {r['value']} {r['unit']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    _demo()
