from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from aigateway.gateway.errors import json_error
from aigateway.telemetry import correlation_id_var, observe_http

CORRELATION_HEADER = "X-Correlation-ID"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        correlation_id = request.headers.get(CORRELATION_HEADER) or str(uuid.uuid4())
        token = correlation_id_var.set(correlation_id)
        try:
            response = await call_next(request)
            response.headers[CORRELATION_HEADER] = correlation_id
            return response
        finally:
            correlation_id_var.reset(token)


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        settings = request.app.state.settings
        chat_max = getattr(settings, "chat_body_max_bytes", 32768)
        doc_max = getattr(settings, "document_body_max_bytes", 278528)
        max_bytes = doc_max if request.url.path.startswith("/v1/documents") else chat_max
        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit() and int(content_length) > max_bytes:
            return json_error(400, "payload_too_large", "payload too large")
        if request.url.path == "/v1/chat" and request.method == "POST":
            body = await request.body()
            if len(body) > max_bytes:
                return json_error(400, "payload_too_large", "payload too large")
        return await call_next(request)


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            route_obj = request.scope.get("route")
            route = getattr(route_obj, "path", None) or "unmatched"
            outcome = getattr(request.state, "metrics_outcome", None)
            if outcome is None:
                outcome = "allowed" if status < 400 else "error"
            observe_http(route, request.method, status, outcome, time.perf_counter() - started)
