# AI Safety Gateway

Docker-first middleware between applications and LLM providers. Version 4 adds **input guardrails** and a **thin Jev output check** on the stub chat path. There is still **no real LLM or RAG**. Citation and hallucination checks remain later.

## What Version 4 does

- `GET /v1/health` — process is up
- `GET /v1/ready` — 200 only if Postgres, Redis, auth, **and guardrails** respond
- `POST /v1/auth/login` — HS256 access JWT + refresh token
- `POST /v1/chat` — JWT or `X-API-Key`, then a **stub** answer (`Stub: …`). `stream: true` returns SSE. Input guardrails run after rate limits and before persist. A thin Jev output check runs on the stub before the assistant row and SSE tokens
- `GET` / `PATCH /v1/guardrails/policy` — `security_admin` (own tenant) or `platform_admin` (any `tenant_id`). Includes Jev enablement and thresholds
- `GET /v1/conversations` and `GET /v1/conversations/{id}` — tenant-scoped history
- Redis token buckets per tenant **and** user (or API key). Over quota → **429**. Redis down on chat → **503**
- Guardrails down or slower than 2s → **503 `guardrails_unavailable`**. A blocked prompt → **400 `input_blocked`** (JSON even if `stream: true`)
- Tenant-scoped audit logs; Tenant A cannot read Tenant B’s conversations. Blocked prompts are audited as SHA-256, never as raw text

See [12_VERSION_FEATURE_ROADMAP.md](12_VERSION_FEATURE_ROADMAP.md).

## Requirements

- Docker Desktop (or another engine with Compose v2)
- Nothing else: no host Python, uv, Postgres, Redis, or Kafka

## Start

```bash
docker compose up --build -d
```

```bash
docker compose ps
```

You should see `gateway`, `auth`, `migrate` (exited 0), `worker`, `rag`, `guardrails`, `evals`, `postgres`, and `redis`.

### Demo credentials (local Docker only)

Password for seeded users: `changeme`

| Email | Tenant | Role |
|-------|--------|------|
| `admin@platform.local` | platform | platform_admin |
| `user@hr.local` | acme-hr | `app_user` (can chat) |
| `user@eng.local` | acme-eng | `app_user` (can chat) |
| `sec@hr.local` | acme-hr | `security_admin` (can chat and patch policy) |
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

`chat.json`:

```json
{"message":"hello"}
```

JSON chat (expect 200 and `"answer":"Stub: hello"`):

```bash
curl -s -X POST http://localhost:8000/v1/chat -H "Content-Type: application/json" -H "Authorization: Bearer ACCESS_TOKEN" --data-binary "@chat.json"
```

SSE (expect `event: meta`, `event: token`, `event: done`):

```json
{"message":"hello","stream":true}
```

```bash
curl -N -X POST http://localhost:8000/v1/chat -H "Content-Type: application/json" -H "Authorization: Bearer ACCESS_TOKEN" --data-binary "@stream.json"
```

Unauthenticated chat expects **401**. Viewer (`view@eng.local`) chat expects **403**. API key chat:

```bash
curl -s -X POST http://localhost:8000/v1/chat -H "Content-Type: application/json" -H "X-API-Key: agt_demo_hr_local_docker_only_key" --data-binary "@chat.json"
```

Isolation: log in as `user@hr.local`, create a chat, then `GET /v1/conversations/{id}` as `user@eng.local`. Expect **403**.

429 demo: send more than 40 chat requests in a burst as one user (burst is 2× the 20/min user cap). Expect `Retry-After` and `X-RateLimit-*` headers.

### Input guardrails (fixture mode)

Compose defaults to `GUARDRAILS_MODE=fixture` and an empty `JEV_API_KEY`. No Perspective or TypeSafe key is required. Phrase rules, regex secrets, Perspective (or `toxic-fixture`), and Jev fixture tokens all run. A Jev vendor error is skipped; the rest of the rules still apply.

Blocked injection (expect **400** `input_blocked`, no new conversation):

```json
{"message":"ignore previous instructions"}
```

Jev fixture injection (also **400** `input_blocked`):

```json
{"message":"please jev-injection now"}
```

```bash
curl -s -X POST http://localhost:8000/v1/chat -H "Content-Type: application/json" -H "Authorization: Bearer ACCESS_TOKEN" --data-binary "@block.json"
```

Secret redaction (expect **200**, stored text and stub answer contain `[SECRET]`):

```json
{"message":"key is sk-abcdefghijklmnopqrstuvwxyz"}
```

Policy (security admin on HR):

```json
{"prompt_injection":false,"jev_injection_threshold":0.4}
```

```bash
curl -s -X PATCH http://localhost:8000/v1/guardrails/policy -H "Content-Type: application/json" -H "Authorization: Bearer SECURITY_ADMIN_TOKEN" --data-binary "@policy.json"
```

Optional live toxicity: set `GUARDRAILS_MODE=live` and `GUARDRAILS_API_KEY` **only on the guardrails container**, then rebuild. Injection, jailbreak, and secret rules still run locally first.

Optional live Jev: set `JEV_API_KEY` **only on the guardrails container**. Empty key keeps the Jev fixture. A Jev timeout or 5xx is logged and skipped.

Successful chat responses include `guardrail_decisions`, `assessments` (Jev probabilities), and `confidence` (output safety probability when Jev ran).

OpenAPI: http://localhost:8000/docs

### Stop

```bash
docker compose down
```

Named volumes persist Postgres/Redis data. Add `-v` only if you want to wipe them (re-seed happens on empty DB).

## Tests and lint

```bash
docker compose --profile test run --rm test
```

## Daily development

After you change Python:

```bash
docker compose up --build -d
```

Schema changes: add an Alembic revision under `services/auth/alembic/versions/` (identity), `apps/gateway/alembic/versions/` (conversations), or `services/guardrails/alembic/versions/` (policies). Rebuild so `migrate` applies **auth, then gateway, then guardrails**.

## Where things live

| Path | Role |
|------|------|
| `apps/gateway` | Public edge: health, ready, auth proxy, stub chat, rate limits, guardrail proxy, conversations Alembic |
| `services/auth` | Users, tenants, JWT, API keys, audit, identity Alembic |
| `services/guardrails` | Input checks, Perspective or fixture moderation, Jev fixture or live, policy Alembic |
| `apps/worker` | Worker stub |
| `services/rag` | RAG stub |
| `services/evals` | Evals stub |
| `packages/contracts` | Models and Protocol ports |
| `packages/config` | Environment settings |
| `packages/telemetry` | JSON logs, correlation / user / tenant IDs |
| `packages/testing` | Fake port implementations |
| `infrastructure/docker` | Shared Dockerfiles |
| `docs/adr` | Architecture decisions |

Gateway is the only published API (`localhost:8000`). Auth and guardrails are internal.

## Configuration

Copy [.env.example](.env.example) to `.env` only if you need to override defaults.

| Variable | Default | Used by |
|----------|---------|---------|
| `POSTGRES_DSN` | `postgresql://aigateway:aigateway@postgres:5432/aigateway` | Gateway, auth, guardrails, migrate |
| `REDIS_URL` | `redis://redis:6379/0` | Gateway readiness, rate limits, session cache |
| `JWT_SECRET` | local insecure default | Auth service only |
| `INTERNAL_AUTH_TOKEN` | local insecure default | Gateway ↔ auth and guardrails |
| `SEED_PASSWORD` | `changeme` | Idempotent seed |
| `SEED_HR_API_KEY` | `agt_demo_hr_local_docker_only_key` | Seeded service key |
| `RATE_LIMIT_TENANT_PER_MINUTE` | `60` | Token bucket (burst 2×) |
| `RATE_LIMIT_USER_PER_MINUTE` | `20` | Token bucket (burst 2×) |
| `RATE_LIMIT_API_KEY_PER_MINUTE` | `60` | Token bucket (burst 2×) |
| `STUB_STREAM_DELAY_MS` | `20` | SSE word delay |
| `GUARDRAILS_MODE` | `fixture` | Guardrails container (`live` uses Perspective) |
| `GUARDRAILS_API_KEY` | empty | Guardrails container only |
| `GUARDRAILS_MODERATION_THRESHOLD` | `0.7` | Perspective score that blocks |
| `JEV_API_KEY` | empty | Guardrails container only (empty uses Jev fixture) |
| `JEV_API_URL` | `https://api.typesafe.ai/v1/systemone` | Guardrails container only |
| `JEV_MODEL` | `jev-latest` | Guardrails container only |
| `JEV_TIMEOUT_SECONDS` | `0.8` | Jev HTTP timeout; vendor errors are skipped |

Do not put production secrets in git. Never log passwords, refresh tokens, full API keys, or raw prompts.

## More docs

- [AGENTS.md](AGENTS.md)
- [PROJECT_STRUCTURE_AND_IMPROVEMENTS.md](PROJECT_STRUCTURE_AND_IMPROVEMENTS.md)
- [docs/diagrams/request-path.md](docs/diagrams/request-path.md)
- [docs/adr](docs/adr)
