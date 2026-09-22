# AI Safety Gateway

Docker-first middleware between applications and LLM providers. Version 3 adds a stub chat API with validation, Redis token-bucket rate limits, conversation persistence, and POST SSE streaming. There is still **no real LLM, RAG, or guardrail model**.

## What Version 3 does

- `GET /v1/health` — process is up
- `GET /v1/ready` — 200 only if Postgres, Redis, **and the auth service** respond
- `POST /v1/auth/login` — HS256 access JWT + refresh token
- `POST /v1/chat` — JWT or `X-API-Key`, then a **stub** answer (`Stub: …`). `stream: true` returns SSE
- `GET /v1/conversations` and `GET /v1/conversations/{id}` — tenant-scoped history
- Redis token buckets per tenant **and** user (or API key). Over quota → **429**. Redis down on chat → **503**
- Tenant-scoped audit logs; Tenant A cannot read Tenant B’s conversations

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
| `sec@hr.local` | acme-hr | `security_admin` (can chat) |
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

Schema changes: add an Alembic revision under `services/auth/alembic/versions/` (identity) or `apps/gateway/alembic/versions/` (conversations). Rebuild so `migrate` applies **auth then gateway**.

## Where things live

| Path | Role |
|------|------|
| `apps/gateway` | Public edge: health, ready, auth proxy, stub chat, rate limits, conversations Alembic |
| `services/auth` | Users, tenants, JWT, API keys, audit, identity Alembic |
| `apps/worker` | Worker stub |
| `services/rag` | RAG stub |
| `services/guardrails` | Guardrails stub |
| `services/evals` | Evals stub |
| `packages/contracts` | Models and Protocol ports |
| `packages/config` | Environment settings |
| `packages/telemetry` | JSON logs, correlation / user / tenant IDs |
| `packages/testing` | Fake port implementations |
| `infrastructure/docker` | Shared Dockerfiles |
| `docs/adr` | Architecture decisions |

Gateway is the only published API (`localhost:8000`). Auth is internal.

## Configuration

Copy [.env.example](.env.example) to `.env` only if you need to override defaults.

| Variable | Default | Used by |
|----------|---------|---------|
| `POSTGRES_DSN` | `postgresql://aigateway:aigateway@postgres:5432/aigateway` | Gateway, auth, migrate |
| `REDIS_URL` | `redis://redis:6379/0` | Gateway readiness, rate limits, session cache |
| `JWT_SECRET` | local insecure default | Auth service only |
| `INTERNAL_AUTH_TOKEN` | local insecure default | Gateway ↔ auth introspect |
| `SEED_PASSWORD` | `changeme` | Idempotent seed |
| `SEED_HR_API_KEY` | `agt_demo_hr_local_docker_only_key` | Seeded service key |
| `RATE_LIMIT_TENANT_PER_MINUTE` | `60` | Token bucket (burst 2×) |
| `RATE_LIMIT_USER_PER_MINUTE` | `20` | Token bucket (burst 2×) |
| `RATE_LIMIT_API_KEY_PER_MINUTE` | `60` | Token bucket (burst 2×) |
| `STUB_STREAM_DELAY_MS` | `20` | SSE word delay |

Do not put production secrets in git. Never log passwords, refresh tokens, or full API keys.

## More docs

- [AGENTS.md](AGENTS.md)
- [PROJECT_STRUCTURE_AND_IMPROVEMENTS.md](PROJECT_STRUCTURE_AND_IMPROVEMENTS.md)
- [docs/diagrams/request-path.md](docs/diagrams/request-path.md)
- [docs/adr](docs/adr)
