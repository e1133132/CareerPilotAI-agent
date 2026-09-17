from __future__ import annotations

import logging
import time
import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from observability.context import reset_request_id, set_request_id
from observability.metrics import metrics_store

logger = logging.getLogger(__name__)


class RequestMetricsMiddleware(BaseHTTPMiddleware):
    """Records per-request latency and attaches X-Request-Id for log correlation."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = (request.headers.get("x-request-id") or "").strip() or uuid.uuid4().hex[:16]
        token = set_request_id(request_id)
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-Id"] = request_id
            return response
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            path = request.url.path
            metrics_store.record_request(path=path, status_code=status_code, duration_ms=duration_ms)
            logger.info(
                "http_request path=%s status=%s duration_ms=%s",
                path,
                status_code,
                duration_ms,
                extra={"path": path, "status_code": status_code, "duration_ms": duration_ms},
            )
            reset_request_id(token)
