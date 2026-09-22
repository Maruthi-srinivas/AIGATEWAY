# ADR-010: OpenAI-compatible LLM on the gateway with fixture default

- Status: Accepted
- Date: 2026-09-22
- Version: 5

## Context

Version 5 must generate an answer after retrieve. Options were: put the provider adapter in `services/rag`, keep the Version 4 stub forever, or add an OpenAI-compatible client on the gateway. Compose still has to pass without a vendor key. Streaming tokens from the vendor before the Jev output check would leak un-checked text.

## Decision

1. **`LLMClient` lives on the gateway.** RAG retrieves; it does not generate. The public route stays `POST /v1/chat`.
2. Compose defaults to **`LLM_MODE=fixture`**. The fixture echoes CONTEXT when a grounded system prompt is present, otherwise `Stub: …` (chitchat).
3. **`LLM_MODE=live`** calls OpenAI-compatible `POST /v1/chat/completions` with `OPENAI_BASE_URL`, `OPENAI_API_KEY`, and `LLM_MODEL` on the **gateway only**. Missing live key or model is **503 `llm_unavailable`**, not a stub fallback. Timeout is **30s**.
4. After retrieve, the gateway prepends a system message: answer only from CONTEXT; if missing, say you don't know. Citations are **all chunks inserted into the prompt** (`document_id` + `chunk_id`). No claim parser (Version 7).
5. Chitchat (a small greeting/thanks list) skips retrieve and still calls generate with empty citations. No chunks above min score **does not call the LLM**; the gateway persists and returns `I don't know based on the available documents.`
6. Streaming is still **generate fully → Jev output check → SSE replay**. Live token streaming from the vendor is deferred until output checks can be incremental.

## Consequences

- Docker demos work without an OpenAI key.
- Switching to live is an env change on the gateway container. The embedding key stays on RAG.
- Clients can trust that SSE `token` events already passed the thin output check.
- Full hallucination, citation verification, and multi-provider routing remain later versions.

## Alternatives rejected

- **Generate inside RAG**: mixes retrieval storage with provider secrets and makes the public chat path harder to audit.
- **Fail open to the stub when live key is missing**: would hide misconfiguration and look like a successful model call.
- **True SSE from the vendor in this slice**: would emit tokens before Jev output toxicity/PII checks.
