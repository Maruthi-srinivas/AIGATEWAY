# ADR-008: Jev as a calibrated scorer with fail-open vendor calls

- Status: Accepted
- Date: 2026-09-22
- Version: 4 (thin output slice)

## Context

TypeSafe Jev returns typed probabilities, not chat tokens. Version 4 already fails closed when `services/guardrails` is down, and when live Perspective fails. Phrase rules and regex PII remain the local baseline. A Jev outage should not take the whole chat path down, but it also must not silently replace ADR-007.

## Decision

1. Jev lives only in `services/guardrails`. The TypeSafe key (`JEV_API_KEY`) never sits on the gateway. The public check contract stays `GuardrailCheckResult`, extended with `assessments`.
2. Empty `JEV_API_KEY` uses a deterministic fixture (`jev-injection`, `jev-jailbreak`, `jev-toxic`, `jev-pii`, `jev-risk`, `jev-refuse`). Compose and CI stay offline.
3. When a key is set, the adapter calls `POST https://api.typesafe.ai/v1/systemone` with a 0.8s timeout. HTTP errors, timeouts, and malformed JSON are **logged and skipped**. Phrase rules, regex PII, and Perspective still run. Perspective still fails closed.
4. Guardrails process down or slower than the gateway’s 2s budget is still **503 `guardrails_unavailable`**.
5. Tenant policy holds `jev_enabled` and per-question thresholds (default 0.7). Jev PII only **blocks** when `pii_action=block`; redaction still uses regex.
6. After the stub answer, the gateway calls `POST /internal/v1/check-output`. Toxicity or PII above threshold replaces the stub with a fixed refusal. `ChatResponse.confidence` is the output safety probability when Jev ran. The route choice is reported and not acted on.
7. SSE buffers the stub, runs the output check, then streams the allowed text so clients never see blocked tokens.

## Consequences

- Docker demos work without a TypeSafe key.
- A Jev outage degrades to local rules; it does not fail open the rest of the guardrail path.
- This is not full Version 7: no citation mapping, no hallucination rewrite, no RAG-grounded verification.

## Alternatives rejected

- **Treat Jev as `LLMClient`**: wrong port; Jev does not generate strings.
- **Fail closed on Jev vendor errors**: would 503 every chat whenever TypeSafe is slow, even though local rules still work.
- **Put the TypeSafe key on the gateway**: repeats the ADR-007 rejection of vendor keys on the public edge.
