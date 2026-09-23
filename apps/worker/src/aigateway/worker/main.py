from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from aigateway.config import WorkerSettings
from aigateway.contracts import KAFKA_TOPICS
from aigateway.telemetry import get_logger, setup_logging
from aigateway.worker.consume import AnalyticsConsumer, authorized

settings = WorkerSettings()
setup_logging(settings.service_name, settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    consumer = AnalyticsConsumer(settings)
    app.state.consumer = consumer
    await consumer.start()
    logger.info("service started")
    yield
    await consumer.stop()
    logger.info("service stopped")


app = FastAPI(title=settings.service_name, version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.get("/internal/v1/counts")
async def counts(request: Request) -> JSONResponse:
    provided = request.headers.get("x-internal-token", "")
    if not authorized(provided, settings.internal_auth_token):
        return JSONResponse(status_code=401, content={"code": "unauthorized"})
    consumer: AnalyticsConsumer = request.app.state.consumer
    body = {topic: consumer.counts[topic] for topic in KAFKA_TOPICS}
    return JSONResponse({"counts": body})
