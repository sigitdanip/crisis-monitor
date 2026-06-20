"""X-Crisis-Token authentication dependency for trigger endpoints.

Fail-closed: if CRISIS_TRIGGER_TOKEN is not set in the environment,
the endpoint returns HTTP 503 (lockdown mode) regardless of the
client's header value.

Design note (ponytail rule): simplest auth wins. A single Bearer-style
header comparison — no OAuth, no JWT, no session management.
"""

import logging
import os
from typing import Optional

from fastapi import Header, HTTPException, Request

logger = logging.getLogger("crisis_monitor.auth")

# Header name used for trigger endpoint authentication
AUTH_HEADER = "X-Crisis-Token"


def _get_expected_token() -> Optional[str]:
    """Return the expected token from env, or None if unset (fail-closed)."""
    token = os.environ.get("CRISIS_TRIGGER_TOKEN")
    if token:
        return token.strip()
    return None


async def verify_crisis_token(
    request: Request,
    x_crisis_token: Optional[str] = Header(None, alias=AUTH_HEADER),
) -> str:
    """FastAPI dependency: validate the X-Crisis-Token header.

    Behavior:
      - Token unset in env → HTTP 503 (service unavailable, fail-closed).
      - Missing header → HTTP 401.
      - Wrong header → HTTP 401.
      - Match → returns the token (unused; satisfies dependency injection).

    Raises:
        HTTPException(401) on missing/wrong token.
        HTTPException(503) on unconfigured token.
    """
    expected = _get_expected_token()

    if expected is None:
        logger.error(
            "CRISIS_TRIGGER_TOKEN unset, trigger endpoint locked request_id=%s",
            getattr(request.state, "request_id", "unknown"),
        )
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Trigger endpoint locked",
                "code": "TOKEN_UNCONFIGURED",
                "request_id": getattr(request.state, "request_id", "unknown"),
            },
        )

    if not x_crisis_token:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "Missing X-Crisis-Token header",
                "code": "UNAUTHORIZED",
                "request_id": getattr(request.state, "request_id", "unknown"),
            },
        )

    if x_crisis_token != expected:
        logger.warning(
            "Invalid X-Crisis-Token attempt request_id=%s",
            getattr(request.state, "request_id", "unknown"),
        )
        raise HTTPException(
            status_code=401,
            detail={
                "error": "Invalid X-Crisis-Token",
                "code": "UNAUTHORIZED",
                "request_id": getattr(request.state, "request_id", "unknown"),
            },
        )

    return x_crisis_token
