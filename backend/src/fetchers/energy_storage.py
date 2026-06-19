"""
Energy storage & shipping fetchers.
Indicators: EU gas storage %, US SPR level, TTF gas price, Freightos Baltic Index.
Sources: GIE AGSI (agsi.gie.eu), EIA, yfinance, Freightos.
"""
import logging
import os
from typing import Any

import httpx
import yfinance as yf

logger = logging.getLogger(__name__)

AGSI_API = "https://agsi.gie.eu/api"
EIA_API = "https://api.eia.gov/v2"


def _fetch_eu_gas_storage() -> dict[str, Any] | None:
    """Fetch EU gas storage fill percentage from GIE AGSI."""
    try:
        with httpx.Client(timeout=15.0) as client:
            # GIE AGSI has a public API — no key required
            r = client.get(
                f"{AGSI_API}",
                params={
                    "country": "eu",
                    "date": "latest",
                },
                headers={"x-key": "anonymous"},
            )
            # ponytail: GIE changed API, try the data endpoint directly
            if r.status_code != 200:
                r2 = client.get(
                    f"{AGSI_API}/data",
                    params={
                        "facilities": "de",  # Germany as proxy for EU
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

            # ponytail: navigate nested AGSI response structure
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
            logger.warning("AGSI: unexpected response shape")
            return None
    except Exception:
        logger.exception("EU gas storage fetch failed")
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
                    "facets[series]": "WCSSTUS1",  # Weekly U.S. Ending Stocks of Crude Oil in SPR
                    "sort[0][column]": "period",
                    "sort[0][direction]": "desc",
                    "length": 1,
                },
            )
            r.raise_for_status()
            data = r.json()
            rows = data.get("response", {}).get("data", [])
            if rows:
                value = float(rows[0].get("value", 0))
                return {
                    "name": "US SPR Level",
                    "category": "Energy",
                    "value": value,
                    "unit": "million barrels",
                    "status": "normal",
                    "trigger_level": "<350 Mbbl",
                }
            return None
    except Exception:
        logger.exception("US SPR fetch failed")
        return None


def _fetch_ttf_gas() -> dict[str, Any] | None:
    """Fetch EU TTF natural gas price via yfinance."""
    # ponytail: TTF is on ICE, yfinance proxy
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
        logger.exception("TTF gas fetch failed")
        return None


def _fetch_fbx() -> dict[str, Any] | None:
    """Fetch Freightos Baltic Index (FBX) — global container freight."""
    try:
        # ponytail: Freightos has a public tracker; scrape or use ETF proxy
        # FBX=F ticker not available; use SONAR proxy or skip
        with httpx.Client(timeout=15.0) as client:
            r = client.get(
                "https://fbx.freightos.com/api/ticker",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if r.status_code == 200:
                data = r.json()
                value = float(data.get("fbx", {}).get("global", 0))
                if value > 0:
                    return {
                        "name": "Freightos Baltic Global",
                        "category": "Supply Chain",
                        "value": value,
                        "unit": "USD/FEU",
                        "status": "normal",
                        "trigger_level": ">5000 USD/FEU Asia-Europe",
                    }
    except Exception:
        logger.exception("FBX fetch failed")
    # ponytail: fallback — ETF proxy (BOAT) loosely tracks container rates
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
        pass
    return None


def fetch_all_energy_storage() -> list[dict[str, Any]]:
    """Fetch all energy storage & shipping indicators. Returns partial on failure."""
    results: list[dict[str, Any]] = []

    eu = _fetch_eu_gas_storage()
    if eu:
        results.append(eu)

    spr = _fetch_us_spr()
    if spr:
        results.append(spr)

    ttf = _fetch_ttf_gas()
    if ttf:
        results.append(ttf)

    fbx = _fetch_fbx()
    if fbx:
        results.append(fbx)

    logger.info("Fetched %d energy storage indicators", len(results))
    return results


def _demo() -> None:
    results = fetch_all_energy_storage()
    for r in results:
        print(f"  {r['name']}: {r['value']} {r['unit']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    _demo()
