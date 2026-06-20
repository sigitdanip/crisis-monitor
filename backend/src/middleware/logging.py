"""Structured request logging middleware with X-Request-ID injection."""

import time
import uuid
import logging
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("crisis_monitor.middleware")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Adds X-Request-ID to every response and logs each request with timing.

    - Generates a server-side UUID if client did not provide X-Request-ID.
    - Logs: request_id, method, path, status_code, latency_ms, user_agent.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        # Attach to request state so exception handlers can access it
        request.state.request_id = request_id

        t0 = time.time()
        response = await call_next(request)
        latency_ms = round((time.time() - t0) * 1000, 1)

        response.headers["X-Request-ID"] = request_id
        response.headers["Access-Control-Expose-Headers"] = "X-Request-ID"

        logger.info(
            "request_id=%s method=%s path=%s status=%d latency_ms=%s user_agent=%s",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            latency_ms,
            request.headers.get("user-agent", ""),
        )
        return response
