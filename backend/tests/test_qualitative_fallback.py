"""Unit tests for qualitative_fallback service.

Covers:
- search_dot: DuckDuckGo search with mock
- synthesize_dot: LLM synthesis with mock
- circuit_breaker: trips after 5 consecutive failures
- zero_results_abstain: honest "no data" note when web search returns nothing
- run_qualitative_fallback: end-to-end integration
- _formulate_queries: query generation for each dot
- token cost tracking
- _reset_circuit / _record_failure / _record_success
"""

import sys
sys.path.insert(0, "/root/crisis-monitor/backend")

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.qualitative_fallback import (
    search_dot,
    synthesize_dot,
    run_qualitative_fallback,
    init_fallback_run,
    get_fallback_cost,
    _formulate_queries,
    _reset_circuit,
    _record_failure,
    _record_success,
    DOT_CONTEXT,
)


# ── Module-level state helpers ───────────────────────────────────────────

def _get_consecutive_failures() -> int:
    """Read the internal consecutive failure counter for test assertions."""
    import src.services.qualitative_fallback as qf
    return qf._CONSECUTIVE_FAILURES


def _is_circuit_open() -> bool:
    """Read the internal circuit breaker state for test assertions."""
    import src.services.qualitative_fallback as qf
    return qf._CIRCUIT_OPEN


# ── _formulate_queries ───────────────────────────────────────────────────


class TestFormulateQueries:
    """Query formulation for each dot."""

    def test_returns_3_queries_for_valid_dot(self):
        queries = _formulate_queries(2)
        assert len(queries) == 3
        assert all(isinstance(q, str) and len(q) > 10 for q in queries)

    def test_queries_contain_dot_theme(self):
        queries = _formulate_queries(3)
        combined = " ".join(queries).lower()
        assert "food" in combined
        assert "fao" in combined

    def test_unknown_dot_falls_back_to_generic(self):
        queries = _formulate_queries(99)
        assert len(queries) == 1
        assert "dot 99" in queries[0]


# ── Circuit breaker ──────────────────────────────────────────────────────


class TestCircuitBreaker:
    """Circuit breaker state machine."""

    def setup_method(self):
        _reset_circuit()

    def test_initial_state(self):
        assert _get_consecutive_failures() == 0
        assert not _is_circuit_open()

    def test_record_success_resets_counter(self):
        _record_failure()
        _record_failure()
        assert _get_consecutive_failures() == 2
        _record_success()
        assert _get_consecutive_failures() == 0

    def test_circuit_trips_after_3_failures(self):
        for _ in range(2):
            _record_failure()
        assert not _is_circuit_open()
        _record_failure()  # 3rd
        assert _is_circuit_open()

    def test_circuit_stays_open_after_more_failures(self):
        for _ in range(7):
            _record_failure()
        assert _is_circuit_open()
        assert _get_consecutive_failures() == 7


# ── search_dot ───────────────────────────────────────────────────────────


class TestSearchDot:
    """Web search with DuckDuckGo mock."""

    def setup_method(self):
        _reset_circuit()

    @pytest.mark.asyncio
    async def test_search_returns_deduplicated_results(self):
        """Results from DuckDuckGo are deduplicated by URL."""
        # Mock returns data in the format _search_duckduckgo produces
        # (with 'url' and 'snippet' keys, not raw 'href'/'body' from DDGS).
        mock_results = [
            {"title": "Oil prices surge", "url": "https://example.com/1", "snippet": "Oil up 5%"},
            {"title": "Oil prices surge (dup)", "url": "https://example.com/1", "snippet": "Duplicate URL"},
            {"title": "Energy crisis", "url": "https://example.com/2", "snippet": "Crisis deepens"},
        ]

        with patch("src.services.qualitative_fallback._search_duckduckgo",
                   new_callable=AsyncMock) as mock_search:
            mock_search.return_value = mock_results

            with patch("src.services.qualitative_fallback.validate_urls",
                       new_callable=AsyncMock) as mock_validate:
                # Return all URLs as alive
                async def _mock_validate(urls):
                    return {u: {"is_alive": True, "status_code": 200, "checked_at": "", "expires_at": "", "cached": True} for u in urls}
                mock_validate.side_effect = _mock_validate

                results, success = await search_dot(2)

            # Deduplicated: 2 unique URLs, 3 queries each returning 3 items
            assert success is True
            assert len(results) == 2
            urls = [r["url"] for r in results]
            assert urls == ["https://example.com/1", "https://example.com/2"]

    @pytest.mark.asyncio
    async def test_search_zero_results_is_not_failure(self):
        """Zero results from search is a valid outcome, not a failure."""
        with patch("src.services.qualitative_fallback._search_duckduckgo",
                   new_callable=AsyncMock) as mock_search:
            mock_search.return_value = []

            results, success = await search_dot(3)

            assert results == []
            assert success is False
            # Should NOT count as failure (success is False but counter not incremented)
            assert _get_consecutive_failures() == 0

    @pytest.mark.asyncio
    async def test_search_with_retry_succeeds_on_retry(self):
        """First attempt fails with exception, second succeeds."""
        call_count = [0]

        async def mock_search_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise ConnectionError("Network error")
            return [
                {"title": "Result", "url": "https://example.com/r", "snippet": "Body"}
            ]

        with patch("src.services.qualitative_fallback._search_duckduckgo",
                   new=AsyncMock(side_effect=mock_search_side_effect)) as mock_search:
            with patch("src.services.qualitative_fallback.validate_urls",
                       new_callable=AsyncMock) as mock_validate:
                async def _mock_validate(urls):
                    return {u: {"is_alive": True, "status_code": 200, "checked_at": "", "expires_at": "", "cached": True} for u in urls}
                mock_validate.side_effect = _mock_validate

                results, success = await search_dot(2)

            # Should have succeeded on retry
            assert success is True
            assert len(results) >= 1
            # Circuit should not be open (success on retry)
            assert not _is_circuit_open()

    @pytest.mark.asyncio
    async def test_circuit_open_skips_search(self):
        """When circuit breaker is open, search returns empty immediately."""
        # Force circuit open
        for _ in range(5):
            _record_failure()
        assert _is_circuit_open()

        with patch("src.services.qualitative_fallback._search_duckduckgo",
                   new_callable=AsyncMock) as mock_search:
            results, success = await search_dot(1)

            mock_search.assert_not_called()
            assert results == []
            assert success is False

    @pytest.mark.asyncio
    async def test_search_deduplicates_across_queries(self):
        """Same URL appearing across different queries is deduplicated."""
        results_q1 = [
            {"title": "A", "url": "https://x.com/a", "snippet": "Body A"},
            {"title": "B", "url": "https://x.com/b", "snippet": "Body B"},
        ]
        results_q2 = [
            {"title": "A again", "url": "https://x.com/a", "snippet": "Duplicate"},
            {"title": "C", "url": "https://x.com/c", "snippet": "Body C"},
        ]

        call_idx = [0]

        async def mock_search_side_effect(*args, **kwargs):
            call_idx[0] += 1
            if call_idx[0] == 1:
                return results_q1
            return results_q2

        with patch("src.services.qualitative_fallback._search_duckduckgo",
                   new=AsyncMock(side_effect=mock_search_side_effect)):
            with patch("src.services.qualitative_fallback.validate_urls",
                       new_callable=AsyncMock) as mock_validate:
                async def _mock_validate(urls):
                    return {u: {"is_alive": True, "status_code": 200, "checked_at": "", "expires_at": "", "cached": True} for u in urls}
                mock_validate.side_effect = _mock_validate

                results, success = await search_dot(2)

            urls = {r["url"] for r in results}
            assert urls == {"https://x.com/a", "https://x.com/b", "https://x.com/c"}
            assert len(results) == 3  # 3 unique URLs from 4 total results


# ── synthesize_dot ───────────────────────────────────────────────────────


class TestSynthesizeDot:
    """LLM synthesis of web search results."""

    @pytest.mark.asyncio
    async def test_zero_results_returns_honest_no_data_note(self):
        """When search returns nothing, synthesis is honest — no hallucination."""
        result = await synthesize_dot(3, [], "qualitative")

        assert result["no_data"] is True
        assert result["tokens_used"] == 0
        assert "no data sources returned" in result["synthesis"].lower()
        assert "Food Security" in result["synthesis"]

    @pytest.mark.asyncio
    async def test_synthesis_with_llm_success(self):
        """LLM returns a synthesis from search results."""
        search_results = [
            {
                "title": "Oil Prices Hit $95",
                "url": "https://example.com/oil",
                "snippet": "Brent crude reached $95 per barrel amid supply concerns.",
            },
            {
                "title": "Energy Markets Update",
                "url": "https://example.com/energy",
                "snippet": "Global energy markets face volatility as geopolitical tensions rise.",
            },
        ]

        mock_llm = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = (
            "Energy markets remain volatile with Brent crude reaching $95/barrel [1]. "
            "Geopolitical tensions continue to drive supply concerns across global markets [2]. "
            "EU gas storage levels have stabilized but remain below seasonal averages."
        )
        mock_llm.ainvoke = AsyncMock(return_value=mock_resp)

        with patch("src.services.qualitative_fallback.get_llm", return_value=mock_llm):
            with patch("src.services.qualitative_fallback.get_llm_content", return_value=mock_resp.content):
                with patch("src.services.qualitative_fallback.track_token_usage"):
                    result = await synthesize_dot(2, search_results, "mixed")

        assert result["no_data"] is False
        assert len(result["synthesis"]) > 50
        assert "energy" in result["synthesis"].lower()
        assert result["tokens_used"] >= 0

    @pytest.mark.asyncio
    async def test_synthesis_falls_back_on_llm_error(self):
        """When LLM call fails, fallback uses raw snippets."""
        search_results = [
            {
                "title": "Test Result",
                "url": "https://example.com/test",
                "snippet": "This is a test snippet from the web.",
            },
        ]

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("LLM unavailable"))

        with patch("src.services.qualitative_fallback.get_llm", return_value=mock_llm):
            result = await synthesize_dot(5, search_results, "qualitative")

        assert "test snippet" in result["synthesis"].lower()
        assert result["no_data"] is False
        assert result["tokens_used"] == 0

    @pytest.mark.asyncio
    async def test_synthesis_truncates_long_output(self):
        """Very long LLM output is truncated at sentence boundary."""
        search_results = [
            {
                "title": "Test",
                "url": "https://example.com/t",
                "snippet": "Test.",
            },
        ]

        # Generate content > 1200 chars
        long_content = ". ".join([f"Sentence {i} about the indicator" for i in range(80)])

        mock_llm = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = long_content
        mock_llm.ainvoke = AsyncMock(return_value=mock_resp)

        with patch("src.services.qualitative_fallback.get_llm", return_value=mock_llm):
            with patch("src.services.qualitative_fallback.get_llm_content", return_value=long_content):
                with patch("src.services.qualitative_fallback.track_token_usage"):
                    result = await synthesize_dot(1, search_results, "mixed")

        assert len(result["synthesis"]) <= 1300  # Allow some margin
        assert result["no_data"] is False


# ── run_qualitative_fallback ─────────────────────────────────────────────


class TestRunQualitativeFallback:
    """End-to-end qualitative fallback for a single dot."""

    @pytest.mark.asyncio
    async def test_returns_structured_result(self):
        """run_qualitative_fallback returns the expected dict shape."""
        mock_search_results = [
            {"title": "Test", "url": "https://x.com/t", "snippet": "Test snippet."}
        ]

        with patch("src.services.qualitative_fallback.search_dot",
                   new_callable=AsyncMock) as mock_search:
            mock_search.return_value = (mock_search_results, True)

            with patch("src.services.qualitative_fallback.synthesize_dot",
                       new_callable=AsyncMock) as mock_synth:
                mock_synth.return_value = {
                    "synthesis": "Test synthesis text.",
                    "tokens_used": 150,
                    "no_data": False,
                }

                with patch("src.services.qualitative_fallback._persist_sources"):
                    result = await run_qualitative_fallback(4, tier="mixed")

        assert "synthesis" in result
        assert "sources" in result
        assert "tokens_used" in result
        assert "search_success" in result
        assert "no_data" in result
        assert result["synthesis"] == "Test synthesis text."
        assert result["search_success"] is True
        assert result["no_data"] is False

    @pytest.mark.asyncio
    async def test_no_data_path(self):
        """When search returns nothing, the result reflects that."""
        with patch("src.services.qualitative_fallback.search_dot",
                   new_callable=AsyncMock) as mock_search:
            mock_search.return_value = ([], False)

            with patch("src.services.qualitative_fallback.synthesize_dot",
                       new_callable=AsyncMock) as mock_synth:
                mock_synth.return_value = {
                    "synthesis": "No data available.",
                    "tokens_used": 0,
                    "no_data": True,
                }

                with patch("src.services.qualitative_fallback._persist_sources"):
                    result = await run_qualitative_fallback(9, tier="qualitative")

        assert result["search_success"] is False
        assert result["no_data"] is True
        assert result["tokens_used"] == 0


# ── Token cost tracking ──────────────────────────────────────────────────


class TestTokenCost:
    """Token cost tracking for qualitative fallback."""

    def setup_method(self):
        _reset_circuit()
        from src.agent.llm import reset_token_cost
        reset_token_cost()

    def test_fallback_cost_zero_when_nothing_called(self):
        cost = get_fallback_cost()
        assert cost["total_tokens"] == 0
        assert cost["total_cost_estimate"] == 0.0

    def test_token_accumulation(self):
        from src.agent.llm import track_token_usage

        track_token_usage(1000)
        track_token_usage(500)

        cost = get_fallback_cost()
        assert cost["total_tokens"] == 1500
        assert cost["total_cost_estimate"] > 0


# ── DOT_CONTEXT completeness ─────────────────────────────────────────────


class TestDotContext:
    """Verify all 9 dots have context entries."""

    def test_all_dots_have_context(self):
        for dot_num in range(1, 10):
            ctx = DOT_CONTEXT.get(dot_num)
            assert ctx is not None, f"Dot {dot_num} missing context"
            assert "name" in ctx
            assert "theme" in ctx
            assert "key_indicators" in ctx
            assert len(ctx["name"]) > 0
            assert len(ctx["theme"]) > 0


# ── init_fallback_run ────────────────────────────────────────────────────


class TestInitFallbackRun:
    """Run initialization resets all state."""

    def test_resets_circuit_and_cost(self):
        # Dirty state
        for _ in range(6):
            _record_failure()
        assert _is_circuit_open()

        from src.agent.llm import track_token_usage, get_token_cost
        track_token_usage(5000)

        init_fallback_run()

        assert not _is_circuit_open()
        assert _get_consecutive_failures() == 0
        cost = get_token_cost()
        assert cost["total_tokens"] == 0
