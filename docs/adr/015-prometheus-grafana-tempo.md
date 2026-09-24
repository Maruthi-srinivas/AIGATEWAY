# ADR-015: Prometheus, Grafana, and Tempo

- Status: Accepted
- Date: 2026-09-24
- Version: 9

## Context

Operators need latency, safety-block, and RAG-miss views, and one correlation id that finds the audit path. Version 8 already puts that id on the Kafka JSON body and in the audit row. A metrics or trace outage must not change a chat status. Prompts, answers, and chunk text stay off the bus and out of logs.

## Decision

1. Prometheus scrapes the gateway at `GET /v1/metrics` and auth, guardrails, RAG, and the worker at `GET /metrics`. The text is unauthenticated. Labels are `route`, `method`, `status`, and `outcome` only.
2. Histograms include a 2 second bucket. The latency dashboard draws a 2 second line. A slow chat does not fail readiness or the test suite.
3. The session-cache counter records hit, miss, and error. There is no RAG result cache. RAG retrieve records hit, miss, and error.
4. OpenTelemetry exports OTLP to Grafana Tempo when `OTEL_EXPORTER_OTLP_ENDPOINT` is set. An empty endpoint leaves tracing as a no-op. Spans carry a name, a status, and numeric latency. They do not carry prompts, answers, chunks, or secrets.
5. Gateway, auth, guardrails, RAG, and the worker export spans. The LLM call is a gateway client span.
6. Produce sets the Kafka header `X-Correlation-ID` and keeps `correlation_id` in the JSON body. The worker copies the header onto the consume span.
7. `GET /v1/audit` accepts `correlation_id` and still filters `tenant_id` to the caller. A cross-tenant id returns an empty list.
8. Grafana is published on port 3000 with anonymous Viewer access. Datasources and the three dashboards are provisioned from the repo.
9. `/v1/ready` does not check Prometheus, Tempo, or Grafana. Gateway OpenAPI is 0.8.0.

## Consequences

- `docker compose up` shows live dashboards without a manual import.
- Killing Tempo or Prometheus leaves chat on its existing status.
- Tenant-level metric labels stay out, so series do not grow with every tenant.

## Alternatives rejected

- **Fail chat or readiness when Grafana is down:** the client would see an operator problem as a model failure.
- **Put the prompt on the span:** Tempo would hold user text and secrets.
- **Push OpenTelemetry metrics through a collector:** a direct Prometheus scrape is enough for this slice.
- **A RAG cache just to show a hit rate:** the session cache is the cache that already exists.
