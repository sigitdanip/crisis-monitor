"""
URL Validator — async HEAD check + 24h cache for citation liveness.

Checks whether a list of URLs are alive via async HTTP HEAD requests
(with GET fallback when HEAD returns 405). Results are cached in
SQLite (url_cache table) for 24 hours — same URL re-checked within that
window returns the cached result without a network request.

Public API:
    validate_one(url) -> 'live' | 'dead' | 'timeout'
    validate_urls(urls) -> {url: 'live' | 'dead' | 'timeout'}

Used by:
- pipeline_runner: validate DuckDuckGo-sourced URLs after qualitative fallback
- newsletter generator: validate all citations before rendering
- dot_analyzers: skip dead URLs when populating sources

Design: pure async utility. No domain logic. No API keys. Best-effort
cache — DB failure means fall through to live check (never crash).
"""

import asyncio
import logging
import sqlite3
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

from src.db.database import get_db

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────

CACHE_TTL_SECONDS = 86_400  # 24 hours
REQUEST_TIMEOUT = 10.0      # seconds per URL
MAX_CONCURRENT = 10         # max simultaneous HEAD/GET requests


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _expires_iso() -> str:
    """Return expiry timestamp = now + 24h as ISO 8601 string."""
    expires = datetime.now(timezone.utc).timestamp() + CACHE_TTL_SECONDS
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(expires))


def _normalize_url(url: str) -> str:
    """Normalize a URL for cache lookup: strip fragment, keep query params.

    Args:
        url: Raw URL string.

    Returns:
        Normalized URL string with fragment removed.
    """
    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(url)
    # Strip fragment, keep scheme, netloc, path, params, query
    normalized = urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        parsed.query,
        "",  # fragment stripped
    ))
    return normalized


def _get_cache(conn: sqlite3.Connection, url: str) -> Optional[dict]:
    """Check the url_cache table for a recent (<=24h) validation.

    A cached result is valid when checked_at is within the last 24 hours.

    Args:
        conn: SQLite connection.
        url: Normalized URL string.

    Returns:
        Dict with keys status (str: 'live'|'dead'|'timeout'), status_code,
        checked_at, expires_at, last_error, cached=True, or None if no
        valid cache entry exists.
    """
    cutoff = time.time() - CACHE_TTL_SECONDS
    cutoff_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(cutoff))

    row = conn.execute(
        "SELECT url, status_code, checked_at, expires_at, last_error "
        "FROM url_cache "
        "WHERE url = ? AND checked_at >= ?",
        (url, cutoff_iso),
    ).fetchone()

    if row is None:
        return None

    status_code = row["status_code"]

    # Classify liveness from status_code
    if status_code is not None and 200 <= status_code < 300:
        status = "live"
    elif status_code is not None:
        status = "dead"
    else:
        status = "timeout"

    return {
        "status": status,
        "status_code": status_code,
        "checked_at": row["checked_at"],
        "expires_at": row["expires_at"],
        "last_error": row["last_error"],
        "cached": True,
    }


def _set_cache(conn: sqlite3.Connection, url: str, result: dict) -> None:
    """Write or update a URL validation result in the url_cache table.

    Uses INSERT OR REPLACE to handle both new URLs and re-checks.

    Args:
        conn: SQLite connection.
        url: Normalized URL string.
        result: Dict with keys status_code, status, checked_at,
                and optionally last_error, expires_at.
    """
    status_code = result.get("status_code")
    status = result.get("status", "timeout")
    checked_at = result.get("checked_at", _now_iso())
    expires_at = result.get("expires_at", _expires_iso())
    last_error = result.get("last_error")

    # Auto-populate last_error from status when not explicitly set
    if last_error is None and status != "live":
        if status_code is None:
            last_error = "Connection timeout or network error"
        else:
            last_error = f"HTTP {status_code}"

    conn.execute(
        "INSERT OR REPLACE INTO url_cache "
        "(url, status_code, checked_at, expires_at, last_error) "
        "VALUES (?, ?, ?, ?, ?)",
        (url, status_code, checked_at, expires_at, last_error),
    )
    conn.commit()


async def _validate_single_url(
    url: str,
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
) -> dict:
    """Validate a single URL via async HEAD request, with GET fallback on 405.

    Many servers return 405 Method Not Allowed for HEAD requests; this
    function detects that and retries with GET to get a meaningful status.

    Args:
        url: Normalized URL to check.
        client: Shared httpx.AsyncClient instance.
        semaphore: Concurrency-limiting semaphore.

    Returns:
        Dict with keys: status (str: 'live'|'dead'|'timeout'),
        status_code (int or None), checked_at, expires_at, last_error,
        cached (bool).
    """
    checked_at = _now_iso()
    expires_at = _expires_iso()

    async with semaphore:
        try:
            # Attempt HEAD first
            response = await client.head(
                url,
                timeout=REQUEST_TIMEOUT,
                follow_redirects=True,
            )

            # 405 Method Not Allowed → retry with GET
            if response.status_code == 405:
                logger.debug(
                    "HEAD returned 405 for %s, retrying with GET", url
                )
                response = await client.get(
                    url,
                    timeout=REQUEST_TIMEOUT,
                    follow_redirects=True,
                )

            status_code = response.status_code
            status = "live" if 200 <= status_code < 300 else "dead"

            return {
                "status": status,
                "status_code": status_code,
                "checked_at": checked_at,
                "expires_at": expires_at,
                "last_error": None if status == "live" else f"HTTP {status_code}",
                "cached": False,
            }

        except httpx.TimeoutException:
            logger.debug("Timeout checking URL: %s", url)
            return {
                "status": "timeout",
                "status_code": None,
                "checked_at": checked_at,
                "expires_at": expires_at,
                "last_error": "Connection timeout",
                "cached": False,
            }

        except (httpx.ConnectError, httpx.NetworkError) as e:
            logger.debug("Connection error checking URL %s: %s", url, e)
            return {
                "status": "timeout",
                "status_code": None,
                "checked_at": checked_at,
                "expires_at": expires_at,
                "last_error": str(e)[:200],
                "cached": False,
            }


async def validate_one(url: str) -> str:
    """Validate a single URL and return its liveness status.

    Uses HEAD first, falls back to GET if HEAD returns 405.
    10-second timeout per request. Results are cached for 24h
    — subsequent calls within that window return the cached result.

    Args:
        url: URL string to validate.

    Returns:
        One of 'live' (HTTP 2xx), 'dead' (HTTP non-2xx), or
        'timeout' (timeout, DNS failure, connection error).
    """
    if not url:
        return "dead"

    normalized = _normalize_url(url)

    # Check cache first
    try:
        conn = get_db()
        cached = _get_cache(conn, normalized)
        conn.close()

        if cached is not None:
            return cached["status"]
    except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
        logger.debug("Cache lookup failed for validate_one: %s", e)

    # Live check
    semaphore = asyncio.Semaphore(1)
    async with httpx.AsyncClient() as client:
        result = await _validate_single_url(normalized, client, semaphore)

    # Write to cache (best-effort)
    try:
        conn = get_db()
        _set_cache(conn, normalized, result)
        conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
        logger.debug("Cache write failed for validate_one: %s", e)

    return result["status"]


async def validate_urls(urls: list[str]) -> dict[str, str]:
    """Validate a list of URLs for liveness with 24-hour caching.

    Performs async HTTP HEAD requests (max 10 concurrent, 10s timeout each),
    with GET fallback when HEAD returns 405. Checks cache first — any URL
    validated within the last 24 hours returns its cached result without
    a network request.

    Args:
        urls: List of raw URL strings to validate.

    Returns:
        Dict mapping each original URL to its liveness status:
        {url: 'live' | 'dead' | 'timeout'}

        - 'live': HTTP 2xx response received
        - 'dead': HTTP non-2xx response received (404, 500, etc.)
        - 'timeout': timeout, DNS failure, SSL error, connection error
    """
    if not urls:
        return {}

    # Build mapping: normalized URL → original URL (for cache lookup + final keys)
    normalized_map: dict[str, str] = {}
    for raw_url in urls:
        normalized = _normalize_url(raw_url)
        # Store mapping; if multiple URLs normalize to the same key,
        # the last one wins (all get same result via cache)
        normalized_map[normalized] = raw_url

    results: dict[str, str] = {}

    # Phase 1: check cache for all URLs
    uncached: list[str] = []  # normalized URLs needing live check

    try:
        conn = get_db()
        for normalized_url, original_url in normalized_map.items():
            cached = _get_cache(conn, normalized_url)
            if cached is not None:
                results[original_url] = cached["status"]
            else:
                uncached.append(normalized_url)
        conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
        logger.warning(
            "Cache lookup failed (DB error): %s — falling through to live checks", e
        )
        # DB error: treat all as uncached
        uncached = list(normalized_map.keys())

    # Phase 2: live check for uncached URLs
    if uncached:
        semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        async with httpx.AsyncClient() as client:
            tasks = [
                _validate_single_url(url, client, semaphore)
                for url in uncached
            ]
            live_results = await asyncio.gather(*tasks)

        # Map live results back to original URLs and write cache
        try:
            conn = get_db()
            for normalized_url, result in zip(uncached, live_results):
                original_url = normalized_map[normalized_url]
                results[original_url] = result["status"]
                # Write to cache (best-effort)
                try:
                    _set_cache(conn, normalized_url, result)
                except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
                    logger.debug("Cache write failed for %s: %s", normalized_url, e)
            conn.close()
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
            logger.warning("Cache write failed (DB error): %s", e)
            # Results are already in the dict — just can't persist

    return results
