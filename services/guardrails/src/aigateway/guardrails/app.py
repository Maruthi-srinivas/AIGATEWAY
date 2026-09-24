from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from aigateway.config import GuardrailsSettings
from aigateway.contracts import AuthenticationError, GuardrailsUnavailableError
from aigateway.guardrails.db import close_engine, init_engine
from aigateway.guardrails.middleware import CorrelationIdMiddleware
from aigateway.guardrails.routes import router
from aigateway.telemetry import (
    correlation_id_var,
    get_logger,
    render_metrics,
    setup_logging,
    setup_telemetry,
    trace_request,
)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: GuardrailsSettings = app.state.settings
    init_engine(settings.postgres_dsn)
    app.state.http_client = httpx.AsyncClient()
    logger.info("guardrails service started mode=%s", settings.guardrails_mode)
    yield
    await app.state.http_client.aclose()
    await close_engine()
    logger.info("guardrails service stopped")


def create_app(settings: GuardrailsSettings) -> FastAPI:
    setup_logging(settings.service_name, settings.log_level)
    setup_telemetry(settings.service_name)
    app = FastAPI(
        title="AI Safety Gateway Guardrails",
        version="0.4.0",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.add_middleware(CorrelationIdMiddleware)
    app.middleware("http")(trace_request)
    app.include_router(router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.service_name}

    @app.get("/metrics")
    async def metrics() -> Response:
        body, content_type = render_metrics()
        return Response(content=body, media_type=content_type)

    @app.exception_handler(AuthenticationError)
    async def _unauthenticated(request: Request, exc: AuthenticationError) -> JSONResponse:
        _ = request
        payload = {"code": exc.code, "detail": exc.detail}
        cid = correlation_id_var.get()
        if cid:
            payload["correlation_id"] = cid
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(GuardrailsUnavailableError)
    async def _unavailable(request: Request, exc: GuardrailsUnavailableError) -> JSONResponse:
        _ = request
        payload = {"code": exc.code, "detail": exc.detail}
        cid = correlation_id_var.get()
        if cid:
            payload["correlation_id"] = cid
        return JSONResponse(status_code=exc.status_code, content=payload)

    return app
