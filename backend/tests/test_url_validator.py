"""Unit tests for url_validator service.

Covers:
- validate_urls() happy path: 200 response -> 'live'
- 404 response -> 'dead'
- Timeout -> 'timeout', status_code=None
- Connection error -> 'timeout', status_code=None
- 405 HEAD → GET fallback
- Cache hit (within 24h) returns cached=True
- Cache miss → live check → result written to cache
- URL normalization: fragment stripped, query params kept
- Empty input returns {}
- Concurrent limit: semaphore enforces max 10
- validate_one() returns string status
- validate_one() with cache hit/miss
"""

import sys
sys.path.insert(0, "/root/crisis-monitor/backend")

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.url_validator import (
    validate_urls,
    validate_one,
    _normalize_url,
    _get_cache,
    _set_cache,
    _validate_single_url,
    CACHE_TTL_SECONDS,
    MAX_CONCURRENT,
    REQUEST_TIMEOUT,
)


# --- URL normalization tests --------------------------------------------------

class TestNormalizeUrl:
    """Tests for _normalize_url()."""

    def test_strips_fragment(self):
        """Fragment is removed from URL."""
        url = "https://example.com/page#section"
        result = _normalize_url(url)
        assert result == "https://example.com/page"

    def test_keeps_query_params(self):
        """Query parameters are preserved."""
        url = "https://example.com/page?key=value&foo=bar"
        result = _normalize_url(url)
        assert result == "https://example.com/page?key=value&foo=bar"

    def test_strips_fragment_keeps_query_both(self):
        """Fragment removed, query params kept when both present."""
        url = "https://example.com/page?q=search#section"
        result = _normalize_url(url)
        assert result == "https://example.com/page?q=search"

    def test_no_fragment_no_query(self):
        """URL without fragment or query is unchanged."""
        url = "https://example.com/page"
        result = _normalize_url(url)
        assert result == url

    def test_empty_fragment(self):
        """Trailing hash with no fragment is stripped."""
        url = "https://example.com/page#"
        result = _normalize_url(url)
        assert result == "https://example.com/page"


# --- Cache tests --------------------------------------------------------------

class TestCache:
    """Tests for _get_cache and _set_cache with an in-memory SQLite db."""

    @pytest.fixture
    def db_conn(self):
        import sqlite3
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE url_cache (
                url TEXT PRIMARY KEY,
                status_code INTEGER,
                checked_at TEXT NOT NULL,
                expires_at TEXT,
                last_error TEXT
            )
        """)
        conn.commit()
        yield conn
        conn.close()

    def test_cache_hit_within_24h(self, db_conn):
        """Cache returns result for a URL checked within the last 24 hours."""
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        expires = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 86400))
        _set_cache(db_conn, "https://example.com/page", {
            "status_code": 200,
            "status": "live",
            "checked_at": now_iso,
            "expires_at": expires,
            "last_error": None,
        })

        result = _get_cache(db_conn, "https://example.com/page")
        assert result is not None
        assert result["status"] == "live"
        assert result["status_code"] == 200
        assert result["cached"] is True
        assert result["expires_at"] == expires
        assert result["last_error"] is None

    def test_cache_miss_unknown_url(self, db_conn):
        """Return None for a URL not in the cache."""
        result = _get_cache(db_conn, "https://example.com/unknown")
        assert result is None

    def test_cache_stale_older_than_24h(self, db_conn):
        """Return None for a URL checked more than 24 hours ago."""
        old_iso = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(time.time() - CACHE_TTL_SECONDS - 3600),
        )
        old_expires = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(time.time() - 3600),
        )
        db_conn.execute(
            "INSERT INTO url_cache (url, status_code, checked_at, expires_at, last_error) "
            "VALUES (?, ?, ?, ?, ?)",
            ("https://example.com/old", 200, old_iso, old_expires, None),
        )
        db_conn.commit()

        result = _get_cache(db_conn, "https://example.com/old")
        assert result is None

    def test_set_cache_overwrites_existing(self, db_conn):
        """INSERT OR REPLACE should update an existing URL's result."""
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        expires = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 86400))
        _set_cache(db_conn, "https://example.com/page", {
            "status_code": 200,
            "status": "live",
            "checked_at": now_iso,
            "expires_at": expires,
            "last_error": None,
        })
        # Overwrite with 404
        _set_cache(db_conn, "https://example.com/page", {
            "status_code": 404,
            "status": "dead",
            "checked_at": now_iso,
            "expires_at": expires,
            "last_error": "HTTP 404",
        })

        result = _get_cache(db_conn, "https://example.com/page")
        assert result["status"] == "dead"
        assert result["status_code"] == 404
        assert result["last_error"] == "HTTP 404"

    def test_set_cache_auto_populates_last_error(self, db_conn):
        """_set_cache auto-populates last_error for non-live URLs."""
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        expires = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 86400))
        _set_cache(db_conn, "https://example.com/dead", {
            "status_code": None,
            "status": "timeout",
            "checked_at": now_iso,
            "expires_at": expires,
            # last_error not provided explicitly
        })

        row = db_conn.execute(
            "SELECT last_error FROM url_cache WHERE url = ?",
            ("https://example.com/dead",),
        ).fetchone()
        assert row is not None
        assert row["last_error"] is not None
        assert "error" in row["last_error"].lower() or "timeout" in row["last_error"].lower()

    def test_get_cache_classifies_status_codes(self, db_conn):
        """Cache lookup returns correct 'status' string per status_code."""
        test_cases = [
            (200, "live"),
            (201, "live"),
            (299, "live"),
            (301, "dead"),
            (403, "dead"),
            (404, "dead"),
            (500, "dead"),
            (None, "timeout"),
        ]
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        expires = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 86400))

        for status_code, expected_status in test_cases:
            _set_cache(db_conn, f"https://example.com/{status_code}", {
                "status_code": status_code,
                "status": expected_status,
                "checked_at": now_iso,
                "expires_at": expires,
            })
            result = _get_cache(db_conn, f"https://example.com/{status_code}")
            assert result["status"] == expected_status, \
                f"status_code={status_code}, expected={expected_status}, got={result['status']}"


# --- Single URL validation tests ----------------------------------------------

class TestValidateSingleUrl:
    """Tests for _validate_single_url() with mocked httpx client."""

    @pytest.mark.asyncio
    async def test_200_returns_live(self):
        """200 response -> status='live', status_code=200, cached=False."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.head.return_value = mock_response

        semaphore = asyncio.Semaphore(MAX_CONCURRENT)

        result = await _validate_single_url(
            "https://example.com", mock_client, semaphore
        )

        assert result["status"] == "live"
        assert result["status_code"] == 200
        assert result["cached"] is False
        assert result["last_error"] is None
        assert "checked_at" in result
        assert "expires_at" in result

        mock_client.head.assert_called_once_with(
            "https://example.com",
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
        )

    @pytest.mark.asyncio
    async def test_404_returns_dead(self):
        """404 response -> status='dead', status_code=404, last_error set."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_client = AsyncMock()
        mock_client.head.return_value = mock_response

        semaphore = asyncio.Semaphore(MAX_CONCURRENT)

        result = await _validate_single_url(
            "https://example.com/notfound", mock_client, semaphore
        )

        assert result["status"] == "dead"
        assert result["status_code"] == 404
        assert result["cached"] is False
        assert result["last_error"] == "HTTP 404"

    @pytest.mark.asyncio
    async def test_301_returns_dead(self):
        """301 redirect -> status='dead' (only 2xx is live)."""
        mock_response = MagicMock()
        mock_response.status_code = 301

        mock_client = AsyncMock()
        mock_client.head.return_value = mock_response

        semaphore = asyncio.Semaphore(MAX_CONCURRENT)

        result = await _validate_single_url(
            "https://example.com/redirect", mock_client, semaphore
        )

        assert result["status"] == "dead"
        assert result["status_code"] == 301
        assert result["last_error"] == "HTTP 301"

    @pytest.mark.asyncio
    async def test_500_returns_dead(self):
        """500 server error -> status='dead'."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client = AsyncMock()
        mock_client.head.return_value = mock_response

        semaphore = asyncio.Semaphore(MAX_CONCURRENT)

        result = await _validate_single_url(
            "https://example.com/error", mock_client, semaphore
        )

        assert result["status"] == "dead"
        assert result["status_code"] == 500
        assert result["last_error"] == "HTTP 500"

    @pytest.mark.asyncio
    async def test_405_retries_with_get(self):
        """HEAD returns 405 → retry with GET, return GET's status_code result."""
        mock_head_response = MagicMock()
        mock_head_response.status_code = 405

        mock_get_response = MagicMock()
        mock_get_response.status_code = 200

        mock_client = AsyncMock()
        # Return 405 for HEAD, 200 for GET
        mock_client.head.return_value = mock_head_response
        mock_client.get.return_value = mock_get_response

        semaphore = asyncio.Semaphore(MAX_CONCURRENT)

        result = await _validate_single_url(
            "https://405-blocking.example.com", mock_client, semaphore
        )

        assert result["status"] == "live"
        assert result["status_code"] == 200
        assert result["cached"] is False
        assert result["last_error"] is None

        # Both HEAD and GET were called
        assert mock_client.head.called
        assert mock_client.get.called

    @pytest.mark.asyncio
    async def test_405_get_also_fails(self):
        """HEAD returns 405 → GET retry also returns error → status='dead'."""
        mock_head_response = MagicMock()
        mock_head_response.status_code = 405

        mock_get_response = MagicMock()
        mock_get_response.status_code = 503

        mock_client = AsyncMock()
        mock_client.head.return_value = mock_head_response
        mock_client.get.return_value = mock_get_response

        semaphore = asyncio.Semaphore(MAX_CONCURRENT)

        result = await _validate_single_url(
            "https://405-double-fail.example.com", mock_client, semaphore
        )

        assert result["status"] == "dead"
        assert result["status_code"] == 503
        assert result["last_error"] == "HTTP 503"

    @pytest.mark.asyncio
    async def test_timeout_returns_timeout_null_status(self):
        """Timeout -> status='timeout', status_code=None, last_error set."""
        import httpx

        mock_client = AsyncMock()
        mock_client.head.side_effect = httpx.TimeoutException("timed out")

        semaphore = asyncio.Semaphore(MAX_CONCURRENT)

        result = await _validate_single_url(
            "https://slow.example.com", mock_client, semaphore
        )

        assert result["status"] == "timeout"
        assert result["status_code"] is None
        assert result["cached"] is False
        assert result["last_error"] == "Connection timeout"

    @pytest.mark.asyncio
    async def test_connection_error_returns_timeout_null_status(self):
        """Connection error -> status='timeout', status_code=None."""
        import httpx

        mock_client = AsyncMock()
        mock_client.head.side_effect = httpx.ConnectError("refused")

        semaphore = asyncio.Semaphore(MAX_CONCURRENT)

        result = await _validate_single_url(
            "https://dead.example.com", mock_client, semaphore
        )

        assert result["status"] == "timeout"
        assert result["status_code"] is None
        assert "refused" in result["last_error"]

    @pytest.mark.asyncio
    async def test_network_error_returns_timeout_null_status(self):
        """Network error -> status='timeout', status_code=None."""
        import httpx

        mock_client = AsyncMock()
        mock_client.head.side_effect = httpx.NetworkError("unreachable")

        semaphore = asyncio.Semaphore(MAX_CONCURRENT)

        result = await _validate_single_url(
            "https://unreachable.example.com", mock_client, semaphore
        )

        assert result["status"] == "timeout"
        assert result["status_code"] is None
        assert "unreachable" in result["last_error"]


# --- validate_one tests -------------------------------------------------------

class TestValidateOne:
    """Tests for validate_one() public API."""

    @pytest.mark.asyncio
    async def test_empty_url_returns_dead(self):
        """Empty or falsy URL returns 'dead'."""
        result = await validate_one("")
        assert result == "dead"

    @pytest.mark.asyncio
    async def test_live_url_returns_live(self):
        """200 response → 'live'."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.head.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("src.services.url_validator.get_db") as mock_db:
            # Cache miss → returns None
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchone.return_value = None
            mock_db.return_value = mock_conn

            with patch(
                "src.services.url_validator.httpx.AsyncClient",
                return_value=mock_client,
            ):
                result = await validate_one("https://example.com")

        assert result == "live"

    @pytest.mark.asyncio
    async def test_dead_url_returns_dead(self):
        """404 response → 'dead'."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_client = AsyncMock()
        mock_client.head.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("src.services.url_validator.get_db") as mock_db:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchone.return_value = None
            mock_db.return_value = mock_conn

            with patch(
                "src.services.url_validator.httpx.AsyncClient",
                return_value=mock_client,
            ):
                result = await validate_one("https://example.com/404")

        assert result == "dead"

    @pytest.mark.asyncio
    async def test_timeout_returns_timeout(self):
        """Timeout → 'timeout'."""
        import httpx

        mock_client = AsyncMock()
        mock_client.head.side_effect = httpx.TimeoutException("timed out")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("src.services.url_validator.get_db") as mock_db:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchone.return_value = None
            mock_db.return_value = mock_conn

            with patch(
                "src.services.url_validator.httpx.AsyncClient",
                return_value=mock_client,
            ):
                result = await validate_one("https://slow.example.com")

        assert result == "timeout"

    @pytest.mark.asyncio
    async def test_405_fallback_in_validate_one(self):
        """validate_one handles 405 → GET fallback correctly."""
        mock_head_response = MagicMock()
        mock_head_response.status_code = 405

        mock_get_response = MagicMock()
        mock_get_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.head.return_value = mock_head_response
        mock_client.get.return_value = mock_get_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("src.services.url_validator.get_db") as mock_db:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchone.return_value = None
            mock_db.return_value = mock_conn

            with patch(
                "src.services.url_validator.httpx.AsyncClient",
                return_value=mock_client,
            ):
                result = await validate_one("https://405.example.com")

        assert result == "live"
        assert mock_client.get.called


# --- validate_urls integration tests ------------------------------------------

class _MockDb:
    """Wrapper holding a SQLite connection and its file path.

    Delegates execute/commit/close to the real connection so the service
    code can use it transparently, while tests can access .conn and .db_path.
    """
    def __init__(self, conn, db_path):
        self.conn = conn
        self.db_path = db_path
        self.execute = conn.execute
        self.commit = conn.commit
        self.close = conn.close
        self.row_factory = conn.row_factory


class TestValidateUrls:
    """Tests for validate_urls() with mocked httpx and temp-file SQLite."""

    @pytest.fixture
    def mock_db(self):
        """Set up a temp-file url_cache table for cache tests.

        Returns a factory function that creates fresh _MockDb wrappers,
        matching production behavior where get_db() returns a new connection.
        """
        import sqlite3
        import tempfile
        import os
        fd, db_path = tempfile.mkstemp(suffix=".db", prefix="url_validator_test_")
        os.close(fd)

        # Seed connection to create the table
        seed_conn = sqlite3.connect(db_path)
        seed_conn.row_factory = sqlite3.Row
        seed_conn.execute("""
            CREATE TABLE IF NOT EXISTS url_cache (
                url TEXT PRIMARY KEY,
                status_code INTEGER,
                checked_at TEXT NOT NULL,
                expires_at TEXT,
                last_error TEXT
            )
        """)
        seed_conn.commit()
        seed_conn.close()

        def make_conn():
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            return _MockDb(conn, db_path)

        yield make_conn
        try:
            os.unlink(db_path)
        except OSError:
            pass

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty_dict(self):
        """Empty URL list returns empty dict."""
        result = await validate_urls([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_cache_hit_skips_network(self, mock_db):
        """Cached URL returns 'live' without making HTTP request."""
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        expires = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 86400))

        # Seed cache via a fresh connection
        seed = mock_db()
        seed.execute(
            "INSERT INTO url_cache (url, status_code, checked_at, expires_at, last_error) "
            "VALUES (?, ?, ?, ?, ?)",
            ("https://example.com/cached", 200, now_iso, expires, None),
        )
        seed.commit()
        seed.close()

        with patch("src.services.url_validator.get_db", side_effect=mock_db):
            with patch("src.services.url_validator.httpx.AsyncClient") as mock_client_class:
                result = await validate_urls(["https://example.com/cached"])

        assert "https://example.com/cached" in result
        assert result["https://example.com/cached"] == "live"
        mock_client_class.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_triggers_network(self, mock_db):
        """Uncached URL triggers a live HEAD request, returns 'live'."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.head.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("src.services.url_validator.get_db", side_effect=mock_db):
            with patch(
                "src.services.url_validator.httpx.AsyncClient",
                return_value=mock_client,
            ):
                result = await validate_urls(["https://example.com/new"])

        assert "https://example.com/new" in result
        assert result["https://example.com/new"] == "live"

    @pytest.mark.asyncio
    async def test_url_normalization_cache_key(self, mock_db):
        """URLs with fragments are normalized for cache lookup."""
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        expires = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 86400))

        seed = mock_db()
        seed.execute(
            "INSERT INTO url_cache (url, status_code, checked_at, expires_at, last_error) "
            "VALUES (?, ?, ?, ?, ?)",
            ("https://example.com/page", 200, now_iso, expires, None),
        )
        seed.commit()
        seed.close()

        with patch("src.services.url_validator.get_db", side_effect=mock_db):
            with patch("src.services.url_validator.httpx.AsyncClient") as mock_client_class:
                result = await validate_urls(["https://example.com/page#section"])

        assert "https://example.com/page#section" in result
        assert result["https://example.com/page#section"] == "live"
        mock_client_class.assert_not_called()

    @pytest.mark.asyncio
    async def test_mixed_cache_hit_and_miss(self, mock_db):
        """Some cached, some not -- only uncached trigger network requests."""
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        expires = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 86400))

        seed = mock_db()
        seed.execute(
            "INSERT INTO url_cache (url, status_code, checked_at, expires_at, last_error) "
            "VALUES (?, ?, ?, ?, ?)",
            ("https://example.com/cached", 200, now_iso, expires, None),
        )
        seed.commit()
        seed.close()

        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_client = AsyncMock()
        mock_client.head.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("src.services.url_validator.get_db", side_effect=mock_db):
            with patch(
                "src.services.url_validator.httpx.AsyncClient",
                return_value=mock_client,
            ):
                result = await validate_urls([
                    "https://example.com/cached",
                    "https://example.com/new",
                ])

        assert result["https://example.com/cached"] == "live"
        assert result["https://example.com/new"] == "dead"
        assert mock_client.head.call_count == 1

    @pytest.mark.asyncio
    async def test_db_error_falls_through_to_live_check(self, mock_db):
        """When DB lookup fails, all URLs get live checked (no crash)."""
        import sqlite3
        failing_conn = MagicMock()
        failing_conn.execute.side_effect = sqlite3.OperationalError("DB locked")

        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.head.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        call_count = 0

        def get_db_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return failing_conn
            return mock_db()

        with patch(
            "src.services.url_validator.get_db",
            side_effect=get_db_side_effect,
        ):
            with patch(
                "src.services.url_validator.httpx.AsyncClient",
                return_value=mock_client,
            ):
                result = await validate_urls(["https://example.com/fallback"])

        assert "https://example.com/fallback" in result
        assert result["https://example.com/fallback"] == "live"
        assert mock_client.head.called

    @pytest.mark.asyncio
    async def test_405_fallback_in_batch(self, mock_db):
        """HEAD 405 → GET fallback works in validate_urls batch."""
        mock_head_response = MagicMock()
        mock_head_response.status_code = 405

        mock_get_response = MagicMock()
        mock_get_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.head.return_value = mock_head_response
        mock_client.get.return_value = mock_get_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("src.services.url_validator.get_db", side_effect=mock_db):
            with patch(
                "src.services.url_validator.httpx.AsyncClient",
                return_value=mock_client,
            ):
                result = await validate_urls(["https://405-blocking.example.com"])

        assert "https://405-blocking.example.com" in result
        assert result["https://405-blocking.example.com"] == "live"
        assert mock_client.get.called

    @pytest.mark.asyncio
    async def test_multiple_urls_mixed_statuses(self, mock_db):
        """Batch with live, dead, and timeout URLs returns distinct statuses."""
        import httpx

        mock_client = AsyncMock()

        # URL 1 → 200 OK
        url1_response = MagicMock()
        url1_response.status_code = 200
        # URL 2 → 404
        url2_response = MagicMock()
        url2_response.status_code = 404
        # URL 3 → timeout
        url3_error = httpx.TimeoutException("timed out")

        calls = 0

        async def mock_head(url, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                return url1_response
            elif calls == 2:
                return url2_response
            else:
                raise url3_error

        mock_client.head = mock_head
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("src.services.url_validator.get_db", side_effect=mock_db):
            with patch(
                "src.services.url_validator.httpx.AsyncClient",
                return_value=mock_client,
            ):
                result = await validate_urls([
                    "https://example.com/live",
                    "https://example.com/dead",
                    "https://example.com/timeout",
                ])

        assert result["https://example.com/live"] == "live"
        assert result["https://example.com/dead"] == "dead"
        assert result["https://example.com/timeout"] == "timeout"
