# AI Safety Gateway

Docker-first middleware between applications and LLM providers. Version 9 adds Prometheus, Grafana, and Tempo beside the chat path. Citation checks and metadata-only Kafka events stay in place. Compose stays keyless (`EMBEDDING_MODE=fixture`, `LLM_MODE=fixture`).

## What Version 9 does

- Prometheus scrapes the gateway, auth, guardrails, RAG, and the worker. `GET /v1/metrics` on the gateway is unauthenticated Prometheus text. Labels are route, method, status, and outcome. No user id, tenant id, prompt, or answer.
- Grafana is on [http://localhost:3000](http://localhost:3000) as an anonymous Viewer. Three dashboards are provisioned: latency with a 2 second line, safety blocks, and RAG misses.
- Traces go to Tempo over OTLP. Export is best-effort. Chat and `/v1/ready` do not call Prometheus, Tempo, or Grafana.
- Kafka events keep `correlation_id` in the JSON body and also set the `X-Correlation-ID` header.
- `GET /v1/audit?correlation_id=` returns that tenant's matching rows. Another tenant's id returns an empty list.
- Gateway OpenAPI is **0.8.0**.

## What Version 8 does

- One KRaft `apache/kafka` broker. Topics: `ai.requests`, `ai.responses`, `ai.security`, `ai.evaluations`, plus a `.dlq` topic for each. One partition and replication factor 1. The gateway creates them on startup and does not publish evaluation events.
- After auth, one request event. When the HTTP status is decided, one response event. A security event is added for an input block, an output block, a `citation_unverified` redact, or an output secret redaction.
- Payloads are metadata: ids, status, latency, rule ids, citation count, groundedness. No prompt, answer, chunk text, or secret span.
- Publish timeout defaults to 0.5s. A broker error is logged and the chat HTTP status stays the same.
- `GET /v1/ready` is 200 only if Postgres, Redis, auth, guardrails, rag, **and kafka** respond. Ready does not ping a live LLM.
- The worker group `aigateway-analytics` counts those four topics. A message is retried 3 times, then written to that topic's dead-letter queue. Redis key `kafka:event:{event_id}` skips a redelivery that was already counted.
- `GET /internal/v1/counts` on the worker requires `X-Internal-Token`. It is not a gateway route.

## What Version 7 does

- `GET /v1/health` — process is up
- `GET /v1/ready` — 200 only if Postgres, Redis, auth, guardrails, rag, and kafka respond
- `POST /v1/auth/login` — HS256 access JWT + refresh token
- `POST /v1/chat` — JWT or `X-API-Key`, then hybrid retrieve (unless chitchat) and a grounded generate. Retrieval applies tenant, role, classification, and acl inside RAG, masks secrets in chunk text, reranks, and stops at 8000 characters. The gateway then drops any answer sentence that is not supported by one of those chunks, redacts secret spans in the answer, and returns `groundedness`. `debug: true` is only for `security_admin` and `platform_admin`
- `POST` / `GET` / `DELETE /v1/documents` — `security_admin` (own tenant) or `platform_admin` (any `tenant_id`). JSON `{title, text}`
- `GET` / `PATCH /v1/guardrails/policy` — same policy roles as Version 4
- `GET /v1/conversations` and `GET /v1/conversations/{id}` — tenant-scoped history
- Redis token buckets per tenant **and** user (or API key). Over quota → **429**. Redis down on chat → **503**
- Guardrails down or slower than 2s → **503 `guardrails_unavailable`**. RAG down or slower than 2s → **503 `rag_unavailable`**. Live LLM down, timeout, or missing key → **503 `llm_unavailable`**
- No retrieved chunks above `RAG_MIN_SCORE` → HTTP **200** with `I don't know based on the available documents.` and `citations: []` (LLM is not called). The same string is returned when every generated sentence fails the citation check. `groundedness` is `0` in that case, and `null` for chitchat and the no-chunk path
- Tenant-scoped audit logs; Tenant A cannot read Tenant B’s conversations or documents

See [12_VERSION_FEATURE_ROADMAP.md](12_VERSION_FEATURE_ROADMAP.md).

## Requirements

- Docker Desktop (or another engine with Compose v2)
- Nothing else: no host Python, uv, Postgres, Redis, or Kafka

## Start

Postgres is now `pgvector/pgvector:pg16`. If you already ran Version 4, wipe the old volume once so the `vector` extension binary exists:

```bash
docker compose down -v
docker compose up --build -d
```

```bash
docker compose ps
```

You should see `gateway`, `web`, `auth`, `migrate` (exited 0), `worker`, `kafka`, `prometheus`, `grafana`, `tempo`, `rag`, `guardrails`, `evals`, `postgres`, and `redis`.

### Console

Open [http://localhost:5173](http://localhost:5173). That container serves a static explainer and playground. The browser calls the public gateway at `http://localhost:8000` only. The console is not on the request path, does not receive internal tokens, and does not show worker counts.

### Demo credentials (local Docker only)

Password for seeded users: `changeme`

| Email | Tenant | Role |
|-------|--------|------|
| `admin@platform.local` | platform | platform_admin |
| `user@hr.local` | acme-hr | `app_user` (can chat) |
| `user@eng.local` | acme-eng | `app_user` (can chat) |
| `sec@hr.local` | acme-hr | `security_admin` (can chat, ingest, and patch policy) |
| `view@eng.local` | acme-eng | `viewer` (read conversations only) |

Demo API key (HR service account): `agt_demo_hr_local_docker_only_key`

### Verify

PowerShell: write JSON bodies to files if quoting is painful.

```bash
curl -s http://localhost:8000/v1/health
curl -s http://localhost:8000/v1/ready
curl -s -X POST http://localhost:8000/v1/auth/login -H "Content-Type: application/json" --data-binary "@login.json"
```

`login.json`:

```json
{"email":"user@hr.local","password":"changeme"}
```

Chitchat (expect 200, `"Stub: hello"`, empty citations):

```json
{"message":"hello"}
```

```bash
curl -s -X POST http://localhost:8000/v1/chat -H "Content-Type: application/json" -H "Authorization: Bearer ACCESS_TOKEN" --data-binary "@chat.json"
```

### Grounded chat

Seeded HR fact (expect 200, a grounded answer, `groundedness` of 1, and `citations` for the chunks that support the answer):

```json
{"message":"How many paid time off days per year does Acme HR give?"}
```

```bash
curl -s -X POST http://localhost:8000/v1/chat -H "Content-Type: application/json" -H "Authorization: Bearer ACCESS_TOKEN" --data-binary "@pto.json"
```

I-don't-know (expect 200, the fixed string, `citations: []`):

```json
{"message":"What is the purple zebra onboarding stipend zzxqwv?"}
```

SSE (expect `event: meta`, `event: token`, `event: done` with citations on `done`):

```json
{"message":"How many paid time off days per year does Acme HR give?","stream":true}
```

```bash
curl -N -X POST http://localhost:8000/v1/chat -H "Content-Type: application/json" -H "Authorization: Bearer ACCESS_TOKEN" --data-binary "@stream.json"
```

Unauthenticated chat expects **401**. Viewer (`view@eng.local`) chat expects **403**. Isolation: the same PTO question as `user@eng.local` must not cite HR document ids.

### Ingest

Security admin on HR:

```json
{"title":"HR unique","text":"The winter bonus is two extra days of leave."}
```

```bash
curl -s -X POST http://localhost:8000/v1/documents -H "Content-Type: application/json" -H "Authorization: Bearer SECURITY_ADMIN_TOKEN" --data-binary "@doc.json"
```

`app_user` ingest expects **403**. Platform admin may pass `?tenant_id=` to ingest into another tenant. Decoded text over 256 KiB expects **400** `payload_too_large`. DELETE cascades chunks and vectors.

### Classification, acl, and debug

Ingest may set `classification` (`public`, `internal`, `confidential`, `restricted`) and `acl` (role names). An empty `acl` means every role in the tenant. Null, `public`, and `internal` are visible to every tenant role. `confidential` is `security_admin` and `platform_admin`. `restricted` is `platform_admin` only. A non-empty `acl` must also include the caller role.

```json
{"title":"Confidential","text":"The bonus pool is confidential.","classification":"confidential","acl":["security_admin"]}
```

Debug (`security_admin` or `platform_admin` only) returns ranks and drop reasons, never chunk text. Other roles get **403**.

```json
{"message":"How many paid time off days per year does Acme HR give?","debug":true}
```

A secret stored in a document (`sk-...`) stays in the document body. The text sent to the model has `[SECRET]` instead.

### Input guardrails (fixture mode)

Compose defaults to `GUARDRAILS_MODE=fixture` and an empty `JEV_API_KEY`. No Perspective or TypeSafe key is required.

Blocked injection (expect **400** `input_blocked`, no new conversation):

```json
{"message":"ignore previous instructions"}
```

Secret redaction (expect **200**, stored user text contains `[SECRET]`; a non-chitchat redacted prompt with no matching chunks returns the I-don't-know string):

```json
{"message":"key is sk-abcdefghijklmnopqrstuvwxyz"}
```

Optional live toxicity: set `GUARDRAILS_MODE=live` and `GUARDRAILS_API_KEY` **only on the guardrails container**, then rebuild.

Optional live Jev: set `JEV_API_KEY` **only on the guardrails container**. Empty key keeps the Jev fixture.

### Optional live embeddings and LLM

Keep Compose on fixture unless you have keys. Keys stay on the owning container:

- Embeddings: `EMBEDDING_MODE=live`, `EMBEDDING_API_KEY`, `EMBEDDING_API_URL`, `EMBEDDING_MODEL` on **rag** only. Requests send `dimensions: 256` so the column never changes.
- LLM: `LLM_MODE=live`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `LLM_MODEL` on **gateway** only. Missing live key is **503** `llm_unavailable`, not a stub fallback.

The gateway never receives the embedding key. RAG never receives the LLM key.

OpenAPI: http://localhost:8000/docs

### Stop

```bash
docker compose down
```

Named volumes persist Postgres/Redis data. Add `-v` only if you want to wipe them (re-seed happens on empty DB). Switching from `postgres:16` to `pgvector/pgvector:pg16` requires `docker compose down -v` once.

## Tests and lint

```bash
docker compose --profile test run --rm test
```

## Daily development

After you change Python:

```bash
docker compose up --build -d
```

Schema changes: add an Alembic revision under `services/auth/alembic/versions/` (identity), `apps/gateway/alembic/versions/` (conversations), `services/guardrails/alembic/versions/` (policies), or `services/rag/alembic/versions/` (documents and chunks). Rebuild so `migrate` applies **auth, then gateway, then guardrails, then rag**.

## Where things live

| Path | Role |
|------|------|
| `apps/gateway` | Public edge: health, ready, auth proxy, chat orchestration, document proxy, rate limits, conversations Alembic |
| `services/auth` | Users, tenants, JWT, API keys, audit, identity Alembic |
| `services/guardrails` | Input checks, Perspective or fixture moderation, Jev fixture or live, policy Alembic |
| `services/rag` | Documents, chunks, fixture or live embeddings, vector retrieve, RAG Alembic |
| `apps/worker` | Worker stub |
| `services/evals` | Evals stub |
| `packages/contracts` | Models and Protocol ports |
| `packages/config` | Environment settings |
| `packages/telemetry` | JSON logs, correlation / user / tenant IDs |
| `packages/testing` | Fake port implementations |
| `infrastructure/docker` | Shared Dockerfiles |
| `docs/adr` | Architecture decisions |

Gateway is the only published API (`localhost:8000`). Auth, guardrails, and rag are internal.

## Configuration

Copy [.env.example](.env.example) to `.env` only if you need to override defaults.

| Variable | Default | Used by |
|----------|---------|---------|
| `POSTGRES_DSN` | `postgresql://aigateway:aigateway@postgres:5432/aigateway` | Gateway, auth, guardrails, rag, migrate |
| `REDIS_URL` | `redis://redis:6379/0` | Gateway readiness, rate limits, session cache |
| `JWT_SECRET` | local insecure default | Auth service only |
| `INTERNAL_AUTH_TOKEN` | local insecure default | Gateway ↔ auth, guardrails, and rag |
| `SEED_PASSWORD` | `changeme` | Idempotent identity seed |
| `SEED_HR_API_KEY` | `agt_demo_hr_local_docker_only_key` | Seeded service key |
| `RATE_LIMIT_TENANT_PER_MINUTE` | `60` | Token bucket (burst 2×) |
| `RATE_LIMIT_USER_PER_MINUTE` | `20` | Token bucket (burst 2×) |
| `RATE_LIMIT_API_KEY_PER_MINUTE` | `60` | Token bucket (burst 2×) |
| `STUB_STREAM_DELAY_MS` | `20` | SSE word delay |
| `GUARDRAILS_MODE` | `fixture` | Guardrails container (`live` uses Perspective) |
| `GUARDRAILS_API_KEY` | empty | Guardrails container only |
| `JEV_API_KEY` | empty | Guardrails container only (empty uses Jev fixture) |
| `EMBEDDING_MODE` | `fixture` | RAG container (`live` uses OpenAI-compatible embeddings) |
| `EMBEDDING_API_KEY` | empty | RAG container only |
| `EMBEDDING_API_URL` | `https://api.openai.com/v1/embeddings` | RAG container only |
| `EMBEDDING_MODEL` | empty | Required only when `EMBEDDING_MODE=live` |
| `RAG_MIN_SCORE` | `0.3` | Drop retrieve hits below this cosine |
| `RAG_TOP_K` | `8` | Chunks kept after rerank, before the character budget |
| `RAG_CANDIDATE_K` | `32` | Vector and BM25 candidate window |
| `RAG_CONTEXT_MAX_CHARS` | `8000` | Prompt context budget after rerank |
| `LLM_MODE` | `fixture` | Gateway (`live` uses OpenAI-compatible Chat Completions) |
| `OPENAI_API_KEY` | empty | Gateway only |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Gateway only |
| `LLM_MODEL` | empty | Required only when `LLM_MODE=live` |
| `LLM_TIMEOUT_SECONDS` | `30` | Gateway LLM HTTP timeout |

Do not put production secrets in git. Never log passwords, refresh tokens, full API keys, raw prompts, document bodies, or chunk text.

## More docs

- [AGENTS.md](AGENTS.md)
- [PROJECT_STRUCTURE_AND_IMPROVEMENTS.md](PROJECT_STRUCTURE_AND_IMPROVEMENTS.md)
- [docs/diagrams/architecture.md](docs/diagrams/architecture.md)
- [docs/diagrams/request-path.md](docs/diagrams/request-path.md)
- [docs/adr](docs/adr)
