from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from aigateway.config import ServiceSettings
from aigateway.telemetry import get_logger, setup_logging

settings = ServiceSettings()
setup_logging(settings.service_name, settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    logger.info("service started")
    yield
    logger.info("service stopped")


app = FastAPI(title=settings.service_name, version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}
