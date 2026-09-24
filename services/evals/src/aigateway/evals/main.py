from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from aigateway.config import EvalsSettings
from aigateway.contracts import AuthenticationError
from aigateway.evals.db import close_engine, init_engine
from aigateway.evals.routes import router
from aigateway.telemetry import (
    correlation_id_var,
    get_logger,
    render_metrics,
    setup_logging,
    setup_telemetry,
    trace_request,
)

settings = EvalsSettings()
setup_logging(settings.service_name, settings.log_level)
setup_telemetry(settings.service_name)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_engine(settings.postgres_dsn)
    logger.info("service started")
    yield
    await close_engine()
    logger.info("service stopped")


app = FastAPI(title=settings.service_name, version="0.1.0", lifespan=lifespan)
app.state.settings = settings
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
