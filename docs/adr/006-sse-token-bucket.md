# ADR-006: POST SSE streaming and fail-closed token buckets

- Status: Accepted
- Date: 2026-09-21
- Version: 3

## Context

Version 3 must expose a real `/v1/chat` contract: validated bodies, fair usage, conversation history, and streaming. The public API already authenticates with `Authorization` or `X-API-Key`. Redis is already required for readiness (ADR-002). Options that would change the demo surface: GET EventSource, WebSockets, NDJSON, fail-open rate limits, and storing chat history on the auth service.

## Decision

1. **POST `/v1/chat` with `stream: bool`.** `false` returns JSON `ChatResponse`. `true` returns **SSE** (`text/event-stream`) named events `meta`, `token`, `done`, and `error`. POST keeps JWT and API-key headers; browser `EventSource` is GET-only and cannot send them.
2. **Redis token buckets** (Lua) per tenant and per actor (user id or API-key prefix). All applicable buckets must pass. Burst is 2× the per-minute refill. Chat **fails closed** if Redis is down: `503 rate_limiter_unavailable`. Public ops routes stay unmetered.
3. **Conversations live in gateway Alembic** on the same Postgres instance, with a separate `gateway_alembic_version` table and **no FK** to `users`. Identity stays in `services/auth`. Redis caches the last 20 messages (24h TTL); Postgres is source of truth.
4. The model is still a **stub** (`StubLLMClient` / `LLMClient.stream`). Real providers wait for Version 5.

## Consequences

- Clients must use fetch/`curl -N` for SSE, not EventSource, unless they later add a cookie session.
- Two Alembic histories share one database; migrate runs auth then gateway.
- A Redis outage fails chat (safety) while `/v1/health` can still be 200 and `/v1/ready` is 503.
- HS256 auth and stub tokens are local-demo appropriate; RS256 and live LLMs are later ADRs.

## Alternatives rejected

- **GET EventSource**: cannot send `Authorization` without putting tokens in the query string.
- **WebSockets**: extra protocol for a stub; harder to document in OpenAPI for this slice.
- **NDJSON / OpenAI wire format**: fine later; named SSE events match the v3 product envelope.
- **Conversations in `services/auth`**: mixes chat history with identity data.
- **Fail-open rate limits**: availability over abuse protection; contradicts fail-closed tenancy.
