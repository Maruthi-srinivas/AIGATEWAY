from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import Response

from aigateway.auth.db import close_engine, init_engine, session_scope
from aigateway.auth.errors import register_exception_handlers
from aigateway.auth.middleware import CorrelationIdMiddleware
from aigateway.auth.routes_admin import router as admin_router
from aigateway.auth.routes_auth import router as auth_router
from aigateway.auth.routes_internal import router as internal_router
from aigateway.auth.seed import seed_if_needed
from aigateway.config import AuthSettings
from aigateway.telemetry import (
    get_logger,
    render_metrics,
    setup_logging,
    setup_telemetry,
    trace_request,
)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: AuthSettings = app.state.settings
    init_engine(settings.postgres_dsn)
    async with session_scope() as session:
        await seed_if_needed(session, settings)
    logger.info("auth service started")
    yield
    await close_engine()
    logger.info("auth service stopped")


def create_app(settings: AuthSettings) -> FastAPI:
    setup_logging(settings.service_name, settings.log_level)
    setup_telemetry(settings.service_name)
    app = FastAPI(
        title="AI Safety Gateway Auth",
        version="0.2.0",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.add_middleware(CorrelationIdMiddleware)
    app.middleware("http")(trace_request)
    register_exception_handlers(app)
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(internal_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.service_name}

    @app.get("/metrics")
    async def metrics() -> Response:
        body, content_type = render_metrics()
        return Response(content=body, media_type=content_type)

    return app
