# ADR-002: Redis over Memcached

- Status: Accepted
- Date: 2026-09-21
- Version: 1

## Context

The SAS needs rate limiting, a session store, distributed locks, and (later) semantic cache. Version 1 only uses Redis for readiness, but the choice must not change when those features land.

## Decision

Run **Redis 7** in Docker Compose as the shared in-memory store.

## Consequences

- One service covers counters, locks, session keys, and later vector-ish or embedding cache keys.
- Redis URL is required gateway config (`REDIS_URL`).
- Operators must treat Redis as a safety boundary: cache keys will include tenant and policy version when caching is added.

## Alternatives rejected

- **Memcached**: simpler KV, no native locks or rich data types for rate-limit windows.
- **In-process memory**: cannot share limits across gateway replicas.
