from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

REGISTRY = CollectorRegistry()

HTTP_REQUESTS = Counter(
    "aigateway_http_requests_total",
    "HTTP requests by route, status, and outcome.",
    ["route", "method", "status", "outcome"],
    registry=REGISTRY,
)
HTTP_LATENCY = Histogram(
    "aigateway_http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["route", "method", "status", "outcome"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
    registry=REGISTRY,
)
SESSION_CACHE = Counter(
    "aigateway_session_cache_total",
    "Session cache lookups.",
    ["outcome"],
    registry=REGISTRY,
)
RAG_RETRIEVE = Counter(
    "aigateway_rag_retrieve_total",
    "RAG retrieve results.",
    ["outcome"],
    registry=REGISTRY,
)
ESTIMATED_COST = Counter(
    "aigateway_estimated_cost_dollars_total",
    "Estimated model cost in dollars. Labeled by model only.",
    ["model"],
    registry=REGISTRY,
)


def observe_http(route: str, method: str, status: int, outcome: str, elapsed: float) -> None:
    labels = {
        "route": route,
        "method": method,
        "status": str(status),
        "outcome": outcome,
    }
    HTTP_REQUESTS.labels(**labels).inc()
    HTTP_LATENCY.labels(**labels).observe(elapsed)


def observe_session_cache(outcome: str) -> None:
    SESSION_CACHE.labels(outcome=outcome).inc()


def observe_rag(outcome: str) -> None:
    RAG_RETRIEVE.labels(outcome=outcome).inc()


def observe_cost(model: str, amount: float) -> None:
    if amount <= 0:
        return
    ESTIMATED_COST.labels(model=model or "unknown").inc(amount)


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


def sample_value(metric_name: str, **labels: str) -> float:
    total = 0.0
    for metric in REGISTRY.collect():
        if metric.name != metric_name:
            continue
        for sample in metric.samples:
            if sample.name != metric_name and not sample.name.endswith("_count"):
                continue
            if sample.name.endswith("_created"):
                continue
            if all(sample.labels.get(key) == value for key, value in labels.items()):
                total += sample.value
    return total
