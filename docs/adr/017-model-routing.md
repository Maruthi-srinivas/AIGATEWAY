# ADR-017: Model routing, fixture tools, and approval

## Status

Accepted. Version 11.

## Context

One tenant policy already controls guardrails. Version 11 needs two providers, a cheap or capable choice, one high-risk tool that waits for a person, and a governance read that does not store the prompt. Kubernetes, a real MCP server, and a second vendor SDK stay out.

## Decision

1. Providers are `fixture-a` (model `fixture-cheap`) and `fixture-b` (model `fixture-capable`). Fixture mode is keyless. Live mode uses the existing OpenAI-compatible settings for the cheap model and `PROVIDER_B_BASE_URL`, `PROVIDER_B_API_KEY`, and `PROVIDER_B_MODEL` for the capable model.
2. The gateway picks the first allowlisted model whose class matches `route_preference`. It does not probe latency and does not fail over to the other provider. An empty or non-matching allowlist is 403. A missing key, timeout, or provider error for the chosen route is 503 `llm_unavailable`.
3. `strictness`, `route_preference`, allowlists, and `retention_days` live on the guardrail policy. `strict` forces Jev on and sets thresholds to 0.3 for that check. The saved thresholds stay as written. `retention_days` is not enforced.
4. `POST /v1/chat` accepts optional `tool`: `lookup_leave` or `export_directory`. The model does not invent tool calls. `lookup_leave` returns fixture leave text. `export_directory` stores an approval row, skips the LLM, and returns HTTP 200 with `approval_id`.
5. `POST /v1/approvals/{id}` is `security_admin` for that tenant or `platform_admin`. The requester cannot decide their own row. Approve or deny does not call the LLM.
6. A static price table supplies `estimated_cost` on the governance row. `ChatResponse` gains `provider`, `model`, and `approval_id` only.
7. `GET /v1/governance?correlation_id=` is tenant-scoped metadata. A write failure does not change the chat status. A read failure is 503 `governance_unavailable`. Another tenant's correlation id returns an empty list. `/v1/ready` does not ping providers.
8. Gateway OpenAPI is 0.10.0.

## Consequences

HR can prefer the capable fixture while Engineering prefers the cheap one, using the same chat route. A high-risk export waits in Postgres until a different admin decides it. Governance can name the provider without storing what the user asked.
