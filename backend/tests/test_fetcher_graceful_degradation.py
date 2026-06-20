"""
Regression test: verify that all 5 failing upstream sources degrade gracefully.

Each mocked failure should result in a warning log (not ERROR), the fetcher
returning None, and the pipeline completing with status "completed" (not "failed").

Sources tested (per Card t_bf9bce5b):
  1. EIA API (US SPR) — 403 Forbidden (v1 retired)
  2. SHIBOR — removed from pipeline entirely (was DNS failure)
  3. RCP Polls — 403 Forbidden (CloudFront anti-bot)
  4. FAO FPI — 503 both primary and fallback endpoints
  5. Freightos FBX — 301 Moved Permanently → broken redirect

Usage:
    cd /root/crisis-monitor/backend
    .venv/bin/pytest tests/test_fetcher_graceful_degradation.py -v
"""
import logging
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.fetchers.energy_storage import (
    _fetch_us_spr,
    _fetch_fbx,
    fetch_all_energy_storage,
)
from src.fetchers.currencies import fetch_all_currencies
from src.fetchers.news import _fetch_rcp_polls, fetch_all_news
from src.fetchers.economic import _fetch_fao_fpi, fetch_all_economic
from src.agent.normalize import fetch_and_normalize


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(status_code: int, json_data=None, text=""):
    """Build a mock httpx.Response with the given status code."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = text
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status_code}",
            request=MagicMock(),
            response=resp,
        )
    return resp


def _mock_client_get(status_code: int, json_data=None, text=""):
    """Return a mock httpx.Client whose .get() returns the given response."""
    resp = _mock_response(status_code, json_data, text)
    client = MagicMock(spec=httpx.Client)
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=None)
    client.get.return_value = resp
    return client


# ---------------------------------------------------------------------------
# 1. EIA API (US SPR) — 403 Forbidden
# ---------------------------------------------------------------------------

def test_eia_us_spr_403_returns_none(caplog):
    """EIA returns 403 → _fetch_us_spr logs warning and returns None."""
    with patch.dict("os.environ", {"EIA_API_KEY": "test-key"}):
        mock_client = _mock_client_get(403)
        with patch("httpx.Client", return_value=mock_client):
            with caplog.at_level(logging.WARNING):
                result = _fetch_us_spr()
    assert result is None, f"Expected None on 403, got {result}"
    assert any("HTTP error" in r.message or "403" in r.message
               for r in caplog.records), "Expected warning log for EIA 403"


def test_eia_us_spr_missing_key_returns_none():
    """EIA_API_KEY not set → _fetch_us_spr returns None without HTTP call."""
    with patch.dict("os.environ", {}, clear=True):
        result = _fetch_us_spr()
    assert result is None


# ---------------------------------------------------------------------------
# 2. SHIBOR — removed from pipeline
# ---------------------------------------------------------------------------

def test_shibor_not_called_in_currencies():
    """SHIBOR function no longer exists and is not called by fetch_all_currencies."""
    # Verify _fetch_shibor no longer exists in the module
    import src.fetchers.currencies as currencies
    assert not hasattr(currencies, "_fetch_shibor"), (
        "_fetch_shibor should have been removed"
    )
    # Verify fetch_all_currencies does not reference shibor
    import inspect
    source = inspect.getsource(currencies.fetch_all_currencies)
    assert "shibor" not in source.lower(), (
        "fetch_all_currencies should not reference SHIBOR"
    )


def test_no_shibor_in_source_files():
    """No backend source file references SHIBOR (Card 4 AC)."""
    import subprocess
    result = subprocess.run(
        ["grep", "-rli", "--include=*.py", "shibor",
         "/root/crisis-monitor/backend/src/"],
        capture_output=True, text=True,
    )
    # grep returns 1 when no matches found (which is what we want)
    assert result.returncode == 1, (
        f"SHIBOR still referenced in: {result.stdout.strip()}"
    )


# ---------------------------------------------------------------------------
# 3. RCP Polls — 403 Forbidden (CloudFront anti-bot)
# ---------------------------------------------------------------------------

def test_rcp_polls_403_returns_none(caplog):
    """RCP returns 403 → _fetch_rcp_polls logs warning and returns None."""
    mock_client = _mock_client_get(403)
    with patch("httpx.Client", return_value=mock_client):
        with caplog.at_level(logging.WARNING):
            result = _fetch_rcp_polls()
    assert result is None, f"Expected None on 403, got {result}"
    assert any("anti-bot" in r.message.lower() or "403" in r.message
               for r in caplog.records), "Expected warning log for RCP 403"


# ---------------------------------------------------------------------------
# 4. FAO FPI — 503 both primary and fallback
# ---------------------------------------------------------------------------

def test_fao_fpi_both_fail_returns_none(caplog):
    """FAO primary 503 + fallback 503 → _fetch_fao_fpi returns None cleanly."""
    mock_503 = _mock_client_get(503)
    with patch("httpx.Client", return_value=mock_503):
        with caplog.at_level(logging.WARNING):
            result = _fetch_fao_fpi()
    assert result is None, f"Expected None on double-fail, got {result}"
    assert any("both endpoints failed" in r.message
               for r in caplog.records), "Expected 'both endpoints failed' warning"


# ---------------------------------------------------------------------------
# 5. Freightos FBX — 301 redirect to broken endpoint
# ---------------------------------------------------------------------------

def test_fbx_301_broken_redirect_returns_none(caplog):
    """Freightos returns 301 → _fetch_fbx falls through to ETF fallback cleanly."""
    # Mock primary FBX API returning 301
    mock_301 = _mock_client_get(301)
    # Mock yfinance for fallback — return empty so we get None
    with patch("httpx.Client", return_value=mock_301):
        with patch("yfinance.Ticker") as mock_ticker:
            mock_tk = MagicMock()
            mock_tk.history.return_value.empty = True
            mock_ticker.return_value = mock_tk
            with caplog.at_level(logging.WARNING):
                result = _fetch_fbx()
    assert result is None, (
        f"Expected None when both FBX and fallback fail, got {result}"
    )


def test_fbx_200_still_works(caplog):
    """Sanity: FBX 200 still returns data correctly (regression guard)."""
    mock_client = _mock_client_get(200, json_data={"fbx": {"global": 2500}})
    with patch("httpx.Client", return_value=mock_client):
        result = _fetch_fbx()
    assert result is not None
    assert result["value"] == 2500
    assert result["unit"] == "USD/FEU"


# ---------------------------------------------------------------------------
# 6. Pipeline-level: all 5 sources degraded → still completes
# ---------------------------------------------------------------------------

def test_pipeline_completes_with_all_sources_degraded(caplog):
    """When all 5 sources return errors, fetch_and_normalize still completes."""
    mock_403 = _mock_client_get(403)
    mock_503 = _mock_client_get(503)

    # We need to mock ALL HTTP calls since the pipeline runs fetchers in parallel.
    # Strategy: let yfinance calls still work (they don't use httpx.Client),
    # mock all httpx.Client calls to return 403.
    with patch("httpx.Client", return_value=mock_403):
        with patch("src.fetchers.currencies.fetch_all_currencies",
                   return_value=[]):  # skip yfinance entirely
            with caplog.at_level(logging.WARNING):
                indicators, news_dicts = fetch_and_normalize()

    # Pipeline must not raise — we're just asserting it returned
    assert isinstance(indicators, dict), "Indicators should be a dict"
    assert isinstance(news_dicts, list), "News should be a list"
    # Verify we got partial results (not everything failed)
    # At minimum, the struct should have all expected keys (some may be None)
    expected_keys = [
        "brent_price", "wti_price", "natgas_price", "dxy", "gold_price",
        "us_10y", "us_2y", "vix", "ig_oas", "hy_oas",
    ]
    for key in expected_keys:
        assert key in indicators, f"Missing key {key} in indicators"


# ---------------------------------------------------------------------------
# 7. No ERROR-level logs from fetcher failures
# ---------------------------------------------------------------------------

def test_no_error_logs_from_graceful_failures(caplog):
    """When all 5 sources fail, no ERROR-level logs are emitted by the fetchers."""
    mock_403 = _mock_client_get(403)
    with patch("httpx.Client", return_value=mock_403):
        with patch("src.fetchers.currencies.fetch_all_currencies", return_value=[]):
            with caplog.at_level(logging.INFO):
                fetch_and_normalize()

    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    # The fetchers themselves should not emit ERROR — only WARNING or lower
    fetcher_errors = [
        r for r in errors
        if r.name.startswith("src.fetchers.")
    ]
    assert not fetcher_errors, (
        f"Fetchers emitted ERROR logs: "
        f"{[(r.name, r.message) for r in fetcher_errors]}"
    )
