# Architecture (implemented through Version 8)

Docker-first middleware between applications and LLM providers. The gateway is the only public port (`localhost:8000`). Auth, guardrails, RAG, and the analytics worker stay on the Compose network. OpenAPI version on the gateway is **0.7.0**.

This is what is running now. Grafana, Kubernetes, Prometheus, and golden-set faithfulness evals are later versions. `services/evals` is a health stub and is not on the request path.

Chat sequence detail lives in [request-path.md](request-path.md).

## Runtime

```mermaid
flowchart LR
    Client["Client apps"]

    subgraph edge ["Public"]
        Gateway["gateway :8000<br/>orchestrator"]
    end

    subgraph internal ["Internal services"]
        Auth["auth<br/>identity, JWT, audit"]
        Guard["guardrails<br/>input and output checks"]
        RAG["rag<br/>documents, hybrid search"]
        Worker["worker<br/>analytics consumer"]
        Evals["evals<br/>health stub only"]
    end

    subgraph data ["Data plane"]
        PG[("Postgres 16<br/>pgvector")]
        Redis[("Redis 7")]
        Kafka["Kafka 3.9<br/>KRaft, 1 broker"]
    end

    subgraph optional ["Optional live providers"]
        LLM["OpenAI-compatible<br/>chat completions"]
        Embed["OpenAI-compatible<br/>embeddings"]
        Perspective["Perspective<br/>moderation"]
        Jev["TypeSafe Jev"]
    end

    Client --> Gateway
    Gateway --> Auth
    Gateway --> Guard
    Gateway --> RAG
    Gateway --> PG
    Gateway --> Redis
    Gateway --> Kafka
    Gateway -.-> LLM
    Auth --> PG
    Guard --> PG
    Guard -.-> Perspective
    Guard -.-> Jev
    RAG --> PG
    RAG -.-> Embed
    Kafka --> Worker
    Worker --> Redis
    Worker --> Kafka
```

Solid arrows are always used. Dashed arrows are used only when that provider is switched from fixture to live. Compose defaults are fixture and keyless.

The `web` container (published on port 5173) is a static client, not a hop on this diagram. The browser loads the console from `web` and then calls only public `/v1` routes on `localhost:8000`. The gateway allows that browser origin through `CORS_ORIGINS` (default `http://localhost:5173`). The console does not receive `INTERNAL_AUTH_TOKEN` or any other service secret, and it does not call worker counts.

`migrate` runs once at startup: auth schema, then gateway, then guardrails, then rag. It exits 0 before the app containers serve traffic.

## What each container owns

| Container | Owns | Does not own |
|-----------|------|----------------|
| `gateway` | Chat orchestration, rate limits, conversations, citation checks, output secret redaction, SSE, Kafka publish, LLM calls | JWT secret, guardrail key, Jev key, embedding key, user tables |
| `auth` | Tenants, users, API keys, refresh tokens, audit log, HS256 tokens | Chat, documents, policies |
| `guardrails` | Input rules, per-tenant policy, Perspective or fixture moderation, Jev fixture or live, thin output check | Retrieval, generation |
| `rag` | Ingest, chunk, embed, hybrid retrieve, ACL, secret masking in chunk text | Generation |
| `worker` | Consume metadata events, count them, dead-letter after 3 retries | HTTP chat status |
| `evals` | `GET /health` only | Scoring. The gateway does not call it and does not publish `ai.evaluations` |
| `web` | Static explainer and playground for the public API | Internal routes, service secrets, generation, and a place on the request path |

Shared libraries (no service imports):

| Package | Role |
|---------|------|
| `packages/contracts` | Pydantic models and ports: `AuthProvider`, `Guardrail`, `Retriever`, `LLMClient`, `Evaluator` |
| `packages/config` | Environment settings |
| `packages/telemetry` | JSON logs with correlation id, and `user_id` / `tenant_id` when known |
| `packages/testing` | Fake port implementations |

`packages/*` does not import `apps/*` or `services/*`.

## Public API

Only the gateway is published. Login and refresh are proxied without a prior token. Every other `/v1/*` route requires a Bearer JWT or `X-API-Key`.

| Route | Who | Behind it |
|-------|-----|-----------|
| `GET /v1/health` | anyone | liveness |
| `GET /v1/ready` | anyone | Postgres, Redis, auth, guardrails, rag, and Kafka. Does not ping a live LLM |
| `POST /v1/auth/login`, `refresh`, `logout` | login and refresh are open | auth |
| `GET /v1/me`, `POST /v1/me/api-keys` | authenticated | auth |
| `GET /v1/audit` | tenant-scoped | auth `audit_logs` |
| `GET/POST/PATCH/DELETE /v1/admin/...` | platform admin | tenants, users, API keys |
| `POST /v1/chat` | chat roles; viewer is 403 | full pipeline below |
| `GET /v1/conversations` | tenant-scoped readers | gateway Postgres |
| `POST/GET/DELETE /v1/documents` | `security_admin` or `platform_admin` | rag |
| `GET/PATCH /v1/guardrails/policy` | `security_admin` or `platform_admin` | guardrails |

`platform_admin` may pass `tenant_id` to act in another tenant. Every other role is filtered to `ctx.tenant_id`.

Roles in the seed: `platform_admin`, `security_admin`, `app_user`, `viewer`, plus service-account API keys.

The worker exposes `GET /internal/v1/counts` with `X-Internal-Token`. That route is not on the gateway.

## Chat path

`POST /v1/chat` is the only generation path. RAG does not generate.

```mermaid
flowchart TD
    A["POST /v1/chat"] --> B["Introspect JWT or API key"]
    B --> R["Publish ai.requests"]
    R --> C{"Chat role?"}
    C -->|no| F403["403"]
    C -->|yes| D["Redis token bucket<br/>tenant and user or key"]
    D -->|over quota| F429["429"]
    D -->|Redis down| F503r["503 rate_limiter_unavailable"]
    D -->|allowed| E["Input guardrails<br/>2s timeout"]
    E -->|down| F503g["503 guardrails_unavailable"]
    E -->|block| F400["400 input_blocked<br/>no new conversation"]
    E -->|allow or redact| G{"Chitchat?"}
    G -->|yes| H["LLM without context"]
    G -->|no| I["RAG hybrid retrieve<br/>2s timeout"]
    I -->|down| F503rag["503 rag_unavailable"]
    I -->|no chunks| IDK["I don't know<br/>LLM not called"]
    I -->|hits| J["Grounded generate"]
    H --> K["Redact secrets"]
    J --> L["Drop unsupported sentences<br/>redact secret spans"]
    L --> M["Jev output check"]
    K --> M
    IDK --> M
    M -->|down| F503g
    M -->|ok| N["Store assistant message"]
    N --> O["200 JSON or SSE"]
    F403 --> P["Publish ai.responses<br/>and ai.security when blocked or redacted"]
    F429 --> P
    F503r --> P
    F503g --> P
    F400 --> P
    F503rag --> P
    O --> P
```

Publish timeout defaults to 0.5s. A broker error is logged and does not change the HTTP status. Streaming still generates the full answer, verifies it, runs the output check, then replays the final text as SSE (`meta`, `token`, `done`).

Inside RAG retrieve, in order:

1. Tenant filter.
2. Classification and ACL. Empty ACL means every role in the tenant. `confidential` is `security_admin` and `platform_admin`. `restricted` is `platform_admin` only.
3. Vector search and Postgres full-text search (`RAG_CANDIDATE_K`, default 32).
4. Reciprocal rank fusion (`k = 60`).
5. Secret masking (`sk-`, `agt_`, `password=`, AWS access-key ids become `[SECRET]`).
6. Token-overlap rerank, dedupe, then an 8000-character budget (`RAG_TOP_K` default 8).

Citation check: each answer sentence must share at least half of its tokens with one returned chunk. Unsupported sentences are dropped. If none remain, the same I-don't-know string is returned. `groundedness` is the share of checked sentences that were kept. It is `null` for chitchat and the no-chunk path. `debug: true` returns ranks and drop reasons for `security_admin` and `platform_admin` only, with no chunk text.

## Document ingest

```mermaid
flowchart LR
    Client["security_admin or platform_admin"] --> Gateway
    Gateway --> Auth["introspect"]
    Gateway --> RAG
    RAG --> Chunk["chunk text"]
    Chunk --> Embed["fixture hash embedding<br/>or live embeddings, 256 dims"]
    Embed --> PG[("documents + chunks<br/>vector column")]
```

Decoded text over 256 KiB is `400 payload_too_large`. Delete cascades chunks and vectors. The document body keeps the original secret. The text sent to the model is the masked chunk.

## Data

One Postgres database. Each service migrates its own tables.

```mermaid
flowchart TB
    subgraph auth_tables ["auth"]
        tenants
        users
        api_keys
        refresh_tokens
        audit_logs
    end
    subgraph gw_tables ["gateway"]
        conversations
        messages
    end
    subgraph gr_tables ["guardrails"]
        guardrail_policies
    end
    subgraph rag_tables ["rag"]
        documents
        chunks["chunks.embedding vector 256"]
    end
```

Redis keys:

| Key | Writer | Use |
|-----|--------|-----|
| `rl:tenant:{id}`, `rl:user:{id}`, `rl:key:{prefix}` | gateway | token buckets, burst 2× the per-minute limit |
| session cache | gateway | recent messages for a conversation |
| `kafka:event:{event_id}` | worker | lock, then skip a redelivery already counted |

Kafka topics, one partition, replication factor 1, created by the gateway on startup:

| Topic | Publisher | Payload |
|-------|-----------|---------|
| `ai.requests` | gateway, after auth | metadata only |
| `ai.responses` | gateway, when the HTTP status is decided | metadata only |
| `ai.security` | gateway, on input block, output block, `citation_unverified`, or output secret redaction | metadata only |
| `ai.evaluations` | nobody yet | topic exists so the worker can count it later |
| `*.dlq` | worker, after 3 failed attempts | the same event |

`ChatEvent` carries ids, status, latency, rule ids, citation count, and groundedness. It has no prompt, answer, chunk text, or secret span. The worker group is `aigateway-analytics`.

## Credentials

| Secret | Lives on |
|--------|----------|
| `JWT_SECRET` | auth |
| `GUARDRAILS_API_KEY` | guardrails |
| `JEV_API_KEY` | guardrails |
| `EMBEDDING_API_KEY` | rag |
| `OPENAI_API_KEY` | gateway |
| `INTERNAL_AUTH_TOKEN` | gateway, auth, guardrails, rag, worker |

Internal calls (introspect, audit, guardrail check, retrieve, ingest) send `X-Internal-Token`. Missing credentials, invalid tokens, and cross-tenant access fail closed (401 or 403).

| Dependency down | Chat result |
|-----------------|-------------|
| Redis | 503 `rate_limiter_unavailable` |
| Guardrails, or slower than 2s | 503 `guardrails_unavailable` |
| RAG, or slower than 2s | 503 `rag_unavailable` |
| Live LLM down, slower than 30s, or missing key/model | 503 `llm_unavailable` |
| Kafka at ready time | `/v1/ready` is 503 |
| Kafka after ready | chat status unchanged; event dropped |

Logs are JSON. They include the correlation id and, when known, `user_id` and `tenant_id`. They never include raw passwords, refresh tokens, full API keys, prompts, answers, dropped sentences, secret spans, document bodies, or chunk text.

## Not in this slice

- Evaluation scoring and publishing `ai.evaluations`
- Prometheus, Grafana, traces
- Kubernetes, multi-provider routing, MCP
- A second Kafka broker
