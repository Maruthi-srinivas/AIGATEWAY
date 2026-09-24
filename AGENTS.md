# Agent and developer rules

This repository is a **Docker-only** monorepo. Follow these rules in every change.

## Scope

- Implement one roadmap version at a time ([12_VERSION_FEATURE_ROADMAP.md](12_VERSION_FEATURE_ROADMAP.md)).
- Current shipped slice is Version 9: auth, RBAC, tenancy, chat orchestration, rate limits, SSE, conversations, input guardrails, a thin Jev output check, tenant-scoped pgvector RAG, one OpenAI-compatible LLM adapter, **hybrid BM25 + vector retrieval**, **retrieval ACL / secret masking**, **sentence-level citation verification** with output secret redaction, a **metadata-only Kafka event backbone** with an analytics worker, and **Prometheus, Grafana, and Tempo**.
- Do not add Kubernetes until its version. Golden-set faithfulness evals remain Version 10.

## Architecture

- Generate **interfaces before implementations**. Ports live in `packages/contracts`.
- The gateway **orchestrates** and is the only public port. Identity lives in `services/auth`. Input checks live in `services/guardrails`. Documents, chunks, embeddings, and vector search live in `services/rag`. RAG does not generate.
- Gateway must not hold `JWT_SECRET`, `GUARDRAILS_API_KEY`, `JEV_API_KEY`, `EMBEDDING_API_KEY`, or user tables. The LLM key may live on the gateway. Introspect, guardrail, and RAG checks use `INTERNAL_AUTH_TOKEN`.
- `packages/*` must not import `apps/*` or `services/*`.
- `apps/web` is a static client of the public gateway. It must not call internal routes or hold service secrets. Its image is `infrastructure/docker/Dockerfile.web`, not `Dockerfile.app`.
- **Fail closed** on missing credentials, invalid tokens, and cross-tenant access (401/403).
- Chat rate limiter **fails closed** if Redis is down (503 `rate_limiter_unavailable`).
- Input guardrails **fail closed** if the service is down or slower than 2s (503 `guardrails_unavailable`).
- RAG retrieve **fails closed** if the service is down or slower than 2s (503 `rag_unavailable`).
- Live LLM **fails closed** if the provider is down, slower than 30s, or the key/model is missing (503 `llm_unavailable`). Fixture mode stays keyless.
- Every query that is not `platform_admin` must filter `tenant_id = ctx.tenant_id`.
- Every log line should be JSON. Include correlation ID, and `user_id` / `tenant_id` when known.
- Never log raw passwords, refresh tokens, full API keys (prefix only), raw prompts, model answers, dropped sentences, secret spans, document bodies, or chunk text. Kafka event payloads and trace spans follow the same rule.

## Docker

- Do not document or require host installs of Python, uv, Postgres, Redis, or Kafka.
- App images use `infrastructure/docker/Dockerfile.app` with `PACKAGE` / `MODULE` / `HEALTH_PATH` args. The console image is the exception: `infrastructure/docker/Dockerfile.web`.
- After code changes, rebuild: `docker compose up --build -d`.
- Schema: Alembic in `services/auth` (identity), `apps/gateway` (conversations), `services/guardrails` (policies), and `services/rag` (documents/chunks). The `migrate` container runs auth, then gateway, then guardrails, then rag `upgrade head`.
- Postgres image is `pgvector/pgvector:pg16`. Existing `postgres:16` volumes lack the extension binary; run `docker compose down -v` once after that switch.
- Tests: `docker compose --profile test run --rm test`.
- Keep containers non-root, with HEALTHCHECK, and env-based config.

## API contracts

- Update OpenAPI when you add or change HTTP routes.
- `POST /v1/chat` requires auth, RBAC, rate limits, input guardrails, hybrid retrieve (unless chitchat), grounded generate, sentence citation checks, output secret redaction, and a thin Jev output check. FastAPI version is **0.8.0**.
- `/v1/health` is liveness. `/v1/ready` checks Postgres, Redis, auth, guardrails, rag, and kafka. Ready does not ping a live LLM, Prometheus, Tempo, or Grafana. Chat publish and trace export stay best-effort.

## Docs and tests

- Update README, diagrams, and ADRs in the same change as behavior.
- Safety-critical behavior needs a test that would have caught a regression (especially tenant isolation).
- Do not commit `.env`, secrets, or generated venvs.
