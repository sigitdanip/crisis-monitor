"""
Unit tests for news_indicators.py.

Validates:
- Each of 4 fetcher functions returns correct shape when NewsAPI responds
- Trigger word matching (case-insensitive) correctly sets value=0 or value=1
- Narrative is top 3 headlines, ' | ' separated, max 200 chars
- Graceful degradation: returns None on httpx.TimeoutException
- Graceful degradation: returns None when NEWS_API_KEY is unset
- fetch_all_news_indicators() aggregates partial results
- Module is importable via src.fetchers.__init__
"""
import os
import sys

import pytest
import respx
import httpx

sys.path.insert(0, "/root/crisis-monitor/backend")

from src.fetchers.news_indicators import (
    fetch_news_caixin_pmi,
    fetch_news_eu_gas,
    fetch_news_us_spr,
    fetch_news_protest_countries,
    fetch_all_news_indicators,
    _fetch_newsapi_indicator,
    _from_date,
)


# ---- Helpers ----

def _newsapi_response(articles: list[dict]) -> httpx.Response:
    """Build a mock NewsAPI JSON response with the given articles."""
    return httpx.Response(
        200,
        json={
            "status": "ok",
            "totalResults": len(articles),
            "articles": articles,
        },
    )


def _article(title: str, description: str = "") -> dict:
    """Shorthand for a NewsAPI article dict."""
    return {
        "title": title,
        "description": description,
        "url": f"https://example.com/{title[:20]}",
        "source": {"name": "Test Source"},
        "publishedAt": "2026-06-18T00:00:00Z",
    }


@pytest.fixture(autouse=True)
def _set_api_key(monkeypatch):
    """Ensure NEWS_API_KEY is set for all tests that call the API."""
    monkeypatch.setenv("NEWS_API_KEY", "test-key-12345")


# ---- Shape / return value tests ----

def test_caixin_pmi_triggered(respx_mock):
    """Caixin PMI returns value=1 when trigger words appear in headlines."""
    respx_mock.get("https://newsapi.org/v2/everything").mock(
        return_value=_newsapi_response([
            _article("China factory activity contracts sharply in June"),
            _article("Caixin PMI falls below 50, signaling contraction"),
            _article("Global markets steady amid mixed data"),
        ])
    )
    result = fetch_news_caixin_pmi()
    assert result is not None
    assert result["name"] == "Caixin PMI (News)"
    assert result["category"] == "China"
    assert result["value"] == 1
    assert result["unit"] == "flag"
    assert result["status"] == "breached"
    assert result["source"] == "newsapi"
    assert " | " in result["narrative"]
    assert len(result["narrative"]) <= 200


def test_caixin_pmi_not_triggered(respx_mock):
    """Caixin PMI returns value=0 when no trigger words match."""
    respx_mock.get("https://newsapi.org/v2/everything").mock(
        return_value=_newsapi_response([
            _article("Chinese stocks rally on stimulus hopes"),
            _article("Asian markets end week higher"),
            _article("Trade data shows modest improvement"),
        ])
    )
    result = fetch_news_caixin_pmi()
    assert result is not None
    assert result["value"] == 0
    assert result["status"] == "normal"


def test_eu_gas_triggered(respx_mock):
    """EU Gas returns value=1 when gas storage trigger words appear."""
    respx_mock.get("https://newsapi.org/v2/everything").mock(
        return_value=_newsapi_response([
            _article("EU gas storage levels reach critical low"),
            _article("European energy security in focus as winter approaches"),
            _article("LNG imports surge to offset declining reserves"),
        ])
    )
    result = fetch_news_eu_gas()
    assert result is not None
    assert result["value"] == 1
    assert result["status"] == "breached"
    assert "EU Gas Storage (News)" in result["name"]


def test_us_spr_not_triggered(respx_mock):
    """US SPR returns value=0 when headlines are unrelated."""
    respx_mock.get("https://newsapi.org/v2/everything").mock(
        return_value=_newsapi_response([
            _article("Oil prices steady as OPEC+ holds output"),
            _article("Renewable energy investment reaches new high"),
            _article("Global shipping routes face weather disruptions"),
        ])
    )
    result = fetch_news_us_spr()
    assert result is not None
    assert result["value"] == 0
    assert result["status"] == "normal"


def test_protest_countries_triggered(respx_mock):
    """Protest Countries returns value=1 when unrest keywords match."""
    respx_mock.get("https://newsapi.org/v2/everything").mock(
        return_value=_newsapi_response([
            _article("Massive protests erupt in capital over austerity measures"),
            _article("Demonstrations spread across multiple cities"),
            _article("Government declares state of emergency amid riots"),
        ])
    )
    result = fetch_news_protest_countries()
    assert result is not None
    assert result["value"] == 1
    assert result["status"] == "breached"


# ---- Trigger word matching: case-insensitive ----

def test_trigger_words_case_insensitive(respx_mock):
    """Trigger words match regardless of case (upper, lower, mixed)."""
    respx_mock.get("https://newsapi.org/v2/everything").mock(
        return_value=_newsapi_response([
            _article("PMI data shows CONTRACTION in manufacturing"),
            _article("Factory Activity slows across the region"),
        ])
    )
    result = fetch_news_caixin_pmi()
    assert result is not None
    assert result["value"] == 1, "Should match trigger words case-insensitively"


# ---- Narrative tests ----

def test_narrative_top_3_headlines(respx_mock):
    """Narrative concatenates top 3 headlines with ' | ' separator."""
    respx_mock.get("https://newsapi.org/v2/everything").mock(
        return_value=_newsapi_response([
            _article("Headline One"),
            _article("Headline Two"),
            _article("Headline Three"),
            _article("Headline Four — should not appear"),
        ])
    )
    result = fetch_news_eu_gas()
    assert result is not None
    parts = result["narrative"].split(" | ")
    assert len(parts) == 3
    assert parts[0] == "Headline One"
    assert parts[1] == "Headline Two"
    assert parts[2] == "Headline Three"
    assert "Headline Four" not in result["narrative"]


def test_narrative_truncated_at_200_chars(respx_mock):
    """Narrative is truncated to 200 characters max."""
    long_title = "A" * 120
    respx_mock.get("https://newsapi.org/v2/everything").mock(
        return_value=_newsapi_response([
            _article(long_title),
            _article(long_title),
            _article(long_title),
        ])
    )
    result = fetch_news_us_spr()
    assert result is not None
    assert len(result["narrative"]) <= 200


def test_narrative_handles_empty_articles(respx_mock):
    """Narrative is empty string when NewsAPI returns no articles."""
    respx_mock.get("https://newsapi.org/v2/everything").mock(
        return_value=_newsapi_response([])
    )
    result = fetch_news_protest_countries()
    assert result is not None
    assert result["narrative"] == ""
    assert result["value"] == 0


def test_narrative_handles_none_title(respx_mock):
    """Articles with null titles are skipped, not included in narrative."""
    respx_mock.get("https://newsapi.org/v2/everything").mock(
        return_value=_newsapi_response([
            {"title": None, "description": "desc", "url": "", "source": {}, "publishedAt": ""},
            _article("Valid Title"),
        ])
    )
    result = fetch_news_eu_gas()
    assert result is not None
    assert " | " not in result["narrative"]  # single headline, no separator
    assert result["narrative"] == "Valid Title"


# ---- Graceful degradation ----

def test_returns_none_on_timeout(respx_mock):
    """Fetcher returns None (not an exception) on httpx.TimeoutException."""
    respx_mock.get("https://newsapi.org/v2/everything").mock(
        side_effect=httpx.TimeoutException("timed out")
    )
    result = fetch_news_caixin_pmi()
    assert result is None


def test_returns_none_on_http_error(respx_mock):
    """Fetcher returns None on HTTP 500 errors."""
    respx_mock.get("https://newsapi.org/v2/everything").mock(
        return_value=httpx.Response(500)
    )
    result = fetch_news_eu_gas()
    assert result is None


def test_returns_none_when_no_api_key(monkeypatch):
    """Fetcher returns None when NEWS_API_KEY is unset (no API call made)."""
    monkeypatch.delenv("NEWS_API_KEY", raising=False)
    result = fetch_news_us_spr()
    assert result is None


# ---- Aggregator tests ----

def test_fetch_all_aggregates_partial(respx_mock):
    """fetch_all_news_indicators() returns partial results when some fail."""
    # Mock: first two succeed, third times out, fourth succeeds
    route = respx_mock.get("https://newsapi.org/v2/everything")

    call_count = [0]

    def _side_effect(request):
        call_count[0] += 1
        if call_count[0] == 3:  # us_spr call #3 -> timeout
            raise httpx.TimeoutException("timeout")
        return _newsapi_response([
            _article(f"Result for call {call_count[0]}"),
        ])

    route.mock(side_effect=_side_effect)

    results = fetch_all_news_indicators()
    assert len(results) == 3  # one timed out
    names = [r["name"] for r in results]
    assert "Caixin PMI (News)" in names
    assert "EU Gas Storage (News)" in names
    assert "US SPR (News)" not in names
    assert "Protest Countries (News)" in names


def test_fetch_all_handles_all_failures(respx_mock):
    """fetch_all_news_indicators() returns empty list when all fetchers fail."""
    respx_mock.get("https://newsapi.org/v2/everything").mock(
        side_effect=httpx.TimeoutException("all timed out")
    )
    results = fetch_all_news_indicators()
    assert results == []


# ---- Module importability via __init__ ----

def test_importable_via_init():
    """Module is importable through src.fetchers package."""
    from src.fetchers import fetch_all_news_indicators as fn
    from src.fetchers import ALL_FETCHERS

    assert fn is fetch_all_news_indicators
    names_in_fetchers = [name for name, _ in ALL_FETCHERS]
    assert "news_indicators" in names_in_fetchers


# ---- _from_date helper ----

def test_from_date_format():
    """_from_date() returns ISO date in YYYY-MM-DD format, 7 days ago."""
    date_str = _from_date()
    parts = date_str.split("-")
    assert len(parts) == 3
    assert len(parts[0]) == 4  # year
    assert 1 <= int(parts[1]) <= 12  # month
    assert 1 <= int(parts[2]) <= 31  # day
