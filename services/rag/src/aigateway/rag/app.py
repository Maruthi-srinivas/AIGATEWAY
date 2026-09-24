from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from aigateway.config import RagSettings
from aigateway.contracts import (
    AuthenticationError,
    DocumentNotFoundError,
    PayloadTooLargeError,
    RagUnavailableError,
    ValidationFailedError,
)
from aigateway.rag.db import close_engine, init_engine, session_scope
from aigateway.rag.middleware import CorrelationIdMiddleware
from aigateway.rag.routes import router
from aigateway.rag.seed import seed_if_needed
from aigateway.telemetry import (
    correlation_id_var,
    get_logger,
    render_metrics,
    setup_logging,
    setup_telemetry,
    trace_request,
)

logger = get_logger(__name__)


def _error(exc) -> JSONResponse:
    payload = {"code": exc.code, "detail": exc.detail}
    cid = correlation_id_var.get()
    if cid:
        payload["correlation_id"] = cid
    return JSONResponse(status_code=exc.status_code, content=payload)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: RagSettings = app.state.settings
    init_engine(settings.postgres_dsn)
    app.state.http_client = httpx.AsyncClient()
    async with session_scope() as session:
        await seed_if_needed(session, settings, http_client=app.state.http_client)
    logger.info("rag service started mode=%s", settings.embedding_mode)
    yield
    await app.state.http_client.aclose()
    await close_engine()
    logger.info("rag service stopped")


def create_app(settings: RagSettings) -> FastAPI:
    setup_logging(settings.service_name, settings.log_level)
    setup_telemetry(settings.service_name)
    app = FastAPI(
        title="AI Safety Gateway RAG",
        version="0.5.0",
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
        return _error(exc)

    @app.exception_handler(ValidationFailedError)
    async def _validation(request: Request, exc: ValidationFailedError) -> JSONResponse:
        _ = request
        return _error(exc)

    @app.exception_handler(PayloadTooLargeError)
    async def _too_large(request: Request, exc: PayloadTooLargeError) -> JSONResponse:
        _ = request
        return _error(exc)

    @app.exception_handler(DocumentNotFoundError)
    async def _not_found(request: Request, exc: DocumentNotFoundError) -> JSONResponse:
        _ = request
        return _error(exc)

    @app.exception_handler(RagUnavailableError)
    async def _unavailable(request: Request, exc: RagUnavailableError) -> JSONResponse:
        _ = request
        return _error(exc)

    return app
