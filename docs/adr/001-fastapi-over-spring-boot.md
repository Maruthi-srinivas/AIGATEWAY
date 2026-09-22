# ADR-001: FastAPI over Spring Boot

- Status: Accepted
- Date: 2026-09-21
- Version: 1

## Context

The gateway is a Python-centric AI platform (RAG, evals, guardrails, LangGraph later). We needed an HTTP framework that is native to that ecosystem, ships OpenAPI for free, and runs cleanly in slim Docker images.

## Decision

Use **FastAPI** (ASGI, Pydantic v2, Uvicorn) for the gateway and for Version 1 stub services.

## Consequences

- Shared Pydantic models in `packages/contracts` map 1:1 to request/response bodies.
- Async I/O fits Redis, Postgres, and future streaming.
- Hiring/interview narrative matches the SAS (Python AI stack), not a JVM gateway.
- High-throughput JVM patterns (Netty, Spring WebFlux) are out of scope unless latency evidence later demands a rewrite.

## Alternatives rejected

- **Spring Boot**: stronger enterprise HTTP pedigree, but splits the repo into two languages and fights LangGraph/eval libraries.
- **Flask / Django**: weaker async and OpenAPI story for this API-gateway shape.
