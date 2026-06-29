"""
Credit spread fetchers via FRED API.
Indicators: US IG OAS, US HY OAS, BTP-Bund Spread (Italy 10Y - Germany 10Y).
Requires FRED_API_KEY env var. Graceful degradation if missing.
"""
import logging
import os

import httpx

logger = logging.getLogger(__name__)

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

SERIES: dict[str, dict[str, str]] = {
    "US IG OAS": {
        "series_id": "BAMLC0A0CM",
        "category": "Financial",
        "unit": "bps",
        "trigger_level": ">200 bps",
    },
    "US HY OAS": {
        "series_id": "BAMLH0A0HYM2",
        "category": "Financial",
        "unit": "bps",
        "trigger_level": ">600 bps",
    },
}

# BTP-Bund Spread: Italy 10Y - Germany 10Y (in bps, via FRED)
BTP_SERIES = {
    "Italy 10Y": "IRLTLT01ITM156N",
    "Germany 10Y": "IRLTLT01DEM156N",
}


def _fetch_one(
    client: httpx.Client, name: str, info: dict[str, str], api_key: str
) -> dict | None:
    """Fetch latest observation for a FRED series."""
    try:
        r = client.get(
            FRED_BASE,
            params={
                "series_id": info["series_id"],
                "api_key": api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 1,
            },
            timeout=15.0,
        )
        r.raise_for_status()
        data = r.json()
        obs = data.get("observations", [])
        if not obs:
            logger.warning("No FRED observations for %s", name)
            return None
        value_str = obs[0].get("value", "")
        if not value_str or value_str == ".":
            return None
        return {
            "name": name,
            "category": info["category"],
            "value": float(value_str),
            "unit": info["unit"],
            "status": "normal",
            "trigger_level": info["trigger_level"],
            "source": f"FRED:{info['series_id']}",
        }
    except Exception:
        logger.warning("Failed to fetch FRED series %s", info["series_id"], exc_info=True)
        return None


def _fetch_btp_bund(client: httpx.Client, api_key: str) -> dict | None:
    """Fetch BTP-Bund spread = Italy 10Y - Germany 10Y via FRED."""
    try:
        values = {}
        for name, series_id in BTP_SERIES.items():
            r = client.get(
                FRED_BASE,
                params={
                    "series_id": series_id,
                    "api_key": api_key,
                    "file_type": "json",
                    "sort_order": "desc",
                    "limit": 1,
                },
                timeout=15.0,
            )
            r.raise_for_status()
            data = r.json()
            obs = data.get("observations", [])
            if not obs:
                logger.warning("No FRED observations for %s (%s)", name, series_id)
                return None
            value_str = obs[0].get("value", "")
            if not value_str or value_str == ".":
                return None
            values[name] = float(value_str)

        italy = values.get("Italy 10Y")
        germany = values.get("Germany 10Y")
        if italy is None or germany is None:
            return None
        # Spread in bps: both FRED series are already in percent; difference * 100
        spread = round((italy - germany) * 100, 1)
        return {
            "name": "BTP-Bund Spread",
            "category": "Debt",
            "value": spread,
            "unit": "bps",
            "status": "normal",
            "trigger_level": ">250 bps",
            "source": "FRED:IRLTLT01ITM156N/IRLTLT01DEM156N",
        }
    except Exception:
        logger.warning("Failed to compute BTP-Bund spread", exc_info=True)
        return None


def fetch_all_credit() -> list[dict]:
    """Fetch credit spread indicators via FRED. Returns partial on failure."""
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        logger.warning("FRED_API_KEY not set — skipping credit fetches")
        return []

    results: list[dict] = []
    with httpx.Client() as client:
        for name, info in SERIES.items():
            result = _fetch_one(client, name, info, api_key)
            if result:
                results.append(result)
        # BTP-Bund spread
        btp = _fetch_btp_bund(client, api_key)
        if btp:
            results.append(btp)
    logger.info("Fetched %d/%d credit indicators", len(results), len(SERIES) + 1)
    return results


def _demo() -> None:
    key = os.environ.get("FRED_API_KEY")
    if not key:
        print("FRED_API_KEY not set — demo skipped")
        return
    results = fetch_all_credit()
    for r in results:
        print(f"  {r['name']}: {r['value']} {r['unit']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    _demo()
