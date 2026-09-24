from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from time import perf_counter

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Status, StatusCode

from aigateway.telemetry.logging import get_logger

logger = get_logger(__name__)

SpanHook = Callable[[str], None]
_span_hook: SpanHook | None = None
_configured = False


def setup_telemetry(service_name: str) -> None:
    """Export OTLP traces when the endpoint is set. Otherwise tracing stays a no-op."""
    global _configured
    if _configured:
        return
    _configured = True
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not endpoint:
        return
    try:
        provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
    except Exception:
        logger.warning("otel exporter unavailable")


def set_span_hook(hook: SpanHook | None) -> None:
    global _span_hook
    _span_hook = hook


@contextmanager
def span(name: str) -> Iterator[None]:
    """A named span with latency only. Export failures are logged and swallowed."""
    started = perf_counter()
    tracer = trace.get_tracer("aigateway")
    try:
        context_manager = tracer.start_as_current_span(name)
        current = context_manager.__enter__()
    except Exception:
        logger.warning("trace export failed span=%s", name)
        yield
        return
    try:
        yield
    except Exception:
        _mark_error(current)
        raise
    finally:
        try:
            current.set_attribute("latency_ms", (perf_counter() - started) * 1000)
            if _span_hook is not None:
                _span_hook(name)
        except Exception:
            logger.warning("trace export failed span=%s", name)
        try:
            context_manager.__exit__(None, None, None)
        except Exception:
            logger.warning("trace export failed span=%s", name)


def _mark_error(current: object) -> None:
    try:
        current.set_status(Status(StatusCode.ERROR))  # type: ignore[attr-defined]
    except Exception:
        logger.warning("trace status failed")


async def trace_request(request: object, call_next):
    _ = request
    with span("http.server"):
        return await call_next(request)
