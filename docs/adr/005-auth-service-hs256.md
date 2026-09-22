# ADR-005: Dedicated auth service and HS256 JWTs

- Status: Accepted
- Date: 2026-09-21
- Version: 2

## Context

Version 2 must authenticate humans (JWT) and services (API keys), isolate tenants, and keep an audit trail. Options were: put all of that in `apps/gateway`, extract a library only, or run a dedicated auth process.

The SAS kickstart guide said to generate an auth service. The public API should remain a single gateway port for Docker demos.

## Decision

1. Run **`services/auth`** as its own container. It owns users, tenants, password hashes, API keys, refresh tokens, audit rows, and JWT issuance.
2. The **gateway** is the only host-published HTTP API. It proxies `/v1/auth/*`, `/v1/admin/*`, `/v1/me`, `/v1/audit` and calls `POST /internal/v1/introspect` (protected by `INTERNAL_AUTH_TOKEN`) for every protected edge route.
3. Access tokens are **HS256** with `JWT_SECRET` only on the auth service. Refresh tokens are opaque, Argon2id-hashed, rotated on use.
4. Schema changes go through **Alembic**; a one-shot `migrate` Compose service runs `upgrade head` before auth/gateway start.

## Consequences

- Gateway images do not contain the JWT secret or user tables; leaking the edge container is not enough to mint tokens.
- Every authenticated request pays an introspect hop (acceptable at Version 2 QPS; cache later if needed).
- HS256 is enough for a single-secret Docker demo. Enterprise/OIDC with RS256/JWKS is a later ADR.
- Operators must treat `JWT_SECRET` and `INTERNAL_AUTH_TOKEN` as production secrets; Compose defaults are local-only.

## Alternatives rejected

- **Auth inside the gateway**: simpler hop count, mixes HTTP edge with identity data, harder to fail closed independently.
- **Library-only `packages/auth` with no container**: still couples user DB access to the gateway process.
- **RS256 from day one**: extra key distribution for little demo benefit.
