"""Request/response logging middleware."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.utils.logging import redact

logger = logging.getLogger("app.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        start = time.perf_counter()
        response: Response | None = None
        try:
            response = await call_next(request)
            return response
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            status_code = response.status_code if response is not None else 500
            path = redact(str(request.url.path))
            logger.info(
                "request_id=%s method=%s path=%s status=%s duration_ms=%.1f client=%s",
                request_id,
                request.method,
                path,
                status_code,
                duration_ms,
                request.client.host if request.client else "-",
            )
            if response is not None:
                response.headers["X-Request-ID"] = request_id

# Logging volume tuning
