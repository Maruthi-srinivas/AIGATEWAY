# ADR-007: Dedicated guardrails service with fixture-default Perspective

- Status: Accepted
- Date: 2026-09-22
- Version: 4

## Context

Version 4 must block or mask unsafe prompts before the stub LLM runs. Options were: keep rules inside the gateway, ship model weights in the image, call a vendor API from the edge, or run a dedicated `services/guardrails` process. Compose demos also need to pass without a Google API key.

## Decision

1. The **gateway HTTP-calls `services/guardrails`** after auth, RBAC, and rate limiting, and **before any chat row is written**. The public edge stays the only published port; the vendor key never lives on the gateway.
2. **Toxicity uses Google Perspective** (`comments:analyze`) when `GUARDRAILS_MODE=live`. Compose and tests default to **`fixture`**, which blocks the literal token `toxic-fixture`. Prompt injection, jailbreak, secret patterns, and `max_input_chars` are **local even in live mode** and run before the vendor call.
3. PII in this slice is **secrets only** (`sk-`, `agt_`, `password=`, AWS-style keys). Default action is **redact** to `[SECRET]`. Any `block` wins over redact over allow; the full decision list is returned on JSON and on the SSE `done` event.
4. A block is **HTTP 400 `input_blocked`** (JSON even if `stream: true`). The raw prompt is **not stored**. Audit metadata keeps a **SHA-256** of the raw prompt plus `rule_id`s. Guardrails down or slower than **2s** is **503 `guardrails_unavailable`**. `/v1/ready` includes the guardrails `/health` check.
5. Per-tenant flags live in Postgres via **guardrails Alembic** (`guardrails_alembic_version`). Missing rows use defaults: all flags on, `pii_action=redact`, `max_input_chars=4000`. `security_admin` patches their tenant; `platform_admin` may pass `tenant_id`.

## Consequences

- Unsafe prompts never reach the stub. A block does not create a conversation or a user message.
- Local Docker needs no Perspective key. Switching to live is an env change on the guardrails container only (`GUARDRAILS_MODE=live` plus `GUARDRAILS_API_KEY`).
- Three Alembic histories share one database; migrate runs auth, then gateway, then guardrails.
- Output checks, email/phone/SSN/card detectors, retrieval, and Kafka security events remain later versions.

## Alternatives rejected

- **Rules inside the gateway**: couples the public edge to vendor keys and policy schema; harder to fail the check independently.
- **Always-on Perspective**: Compose tests and air-gapped demos would need a key and a network path to Google.
- **Fail-open when guardrails is down**: would let unsafe prompts through, which contradicts fail-closed tenancy and rate limits.
- **Store raw blocked prompts for forensics**: secret spans and jailbreak text would land in logs and message tables.
