# Agent and developer rules

This repository is a **Docker-only** monorepo. Follow these rules in every change.

## Scope

- Implement one roadmap version at a time ([12_VERSION_FEATURE_ROADMAP.md](12_VERSION_FEATURE_ROADMAP.md)).
- Current shipped slice is Version 3: auth, RBAC, tenancy, stub chat, rate limits, SSE, conversations.
- Do not add RAG logic, guardrail models, Kafka, Grafana, or Kubernetes until their version.

## Architecture

- Generate **interfaces before implementations**. Ports live in `packages/contracts`.
- The gateway **orchestrates** and is the only public port. Identity lives in `services/auth`.
- Gateway must not hold `JWT_SECRET` or user tables. Introspect with `INTERNAL_AUTH_TOKEN`.
- `packages/*` must not import `apps/*` or `services/*`.
- **Fail closed** on missing credentials, invalid tokens, and cross-tenant access (401/403).
- Chat rate limiter **fails closed** if Redis is down (503 `rate_limiter_unavailable`).
- Every query that is not `platform_admin` must filter `tenant_id = ctx.tenant_id`.
- Every log line should be JSON. Include correlation ID, and `user_id` / `tenant_id` when known.
- Never log raw passwords, refresh tokens, or full API keys (prefix only).

## Docker

- Do not document or require host installs of Python, uv, Postgres, Redis, or Kafka.
- App images use `infrastructure/docker/Dockerfile.app` with `PACKAGE` / `MODULE` / `HEALTH_PATH` args.
- After code changes, rebuild: `docker compose up --build -d`.
- Schema: Alembic in `services/auth` (identity) and `apps/gateway` (conversations). The `migrate` container runs auth then gateway `upgrade head`.
- Tests: `docker compose --profile test run --rm test`.
- Keep containers non-root, with HEALTHCHECK, and env-based config.

## API contracts

- Update OpenAPI when you add or change HTTP routes.
- `POST /v1/chat` is a **stub** (no provider). It requires auth, RBAC, and rate limits.
- `/v1/health` is liveness. `/v1/ready` checks Postgres, Redis, and auth.

## Docs and tests

- Update README, diagrams, and ADRs in the same change as behavior.
- Safety-critical behavior needs a test that would have caught a regression (especially tenant isolation).
- Do not commit `.env`, secrets, or generated venvs.
