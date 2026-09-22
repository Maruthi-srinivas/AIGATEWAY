# AI Safety Gateway — 12-Version Feature Roadmap

This roadmap expands the PRD’s three milestones (V1 Secure Gateway, V2 Observability & Evals, V3 Enterprise) into **12 shippable versions**. Each version should be independently demoable, Docker-runnable, and documented before the next one starts.

**Product in one sentence:** a Docker-first middleware between applications and LLM providers that standardizes auth, guardrails, RAG, evaluation, observability, and policy so every AI app does not rebuild those concerns.

**Request path every version must preserve:**

```
Client → Gateway → Auth → Rate Limit → Input Guardrails
       → Retriever (+ Retrieval Guardrails) → LLM
       → Output Verification → Response (+ eval / audit logging)
```

**PRD mapping**

| PRD phase | Versions | Goal |
|-----------|----------|------|
| V1 — Secure AI Gateway with RAG and guardrails | 1–7 | Working, safe chat path with RAG |
| V2 — Observability and automated evaluations | 8–10 | Events, traces, metrics, evals, self-healing |
| V3 — Enterprise routing, MCP, multi-tenancy | 11–12 | Scale, governance, Kubernetes, cost control |

---

## Version 1 — Foundation and Project Skeleton

**Goal:** A developer can clone the repo, run one Docker Compose command, and hit a living gateway with health checks. No LLM calls yet.

**Why first:** The architecture is Docker-first. If the skeleton is wrong, every later service will fight the layout.

### Features

- Monorepo layout matching the SAS:
  - `apps/gateway`
  - `apps/worker` (stub)
  - `services/rag` (stub)
  - `services/guardrails` (stub)
  - `services/evals` (stub)
  - `infrastructure/docker`
  - `docs`
  - `tests`
- FastAPI gateway skeleton with `GET /v1/health`
- Environment-based configuration (no secrets in code)
- Structured JSON logging
- Production-safe defaults (timeouts, non-root containers, healthchecks)
- Interfaces-before-implementations for core ports:
  - `AuthProvider`
  - `Guardrail`
  - `Retriever`
  - `LLMClient`
  - `Evaluator`
- Root README: how to start, stop, and verify
- Architecture Decision Records folder with the four SAS ADRs started:
  - FastAPI over Spring Boot
  - Redis over Memcached
  - Kafka over RabbitMQ
  - PostgreSQL over MongoDB

### Done when

- `docker compose up` starts gateway + Postgres + Redis (Kafka can wait until Version 8)
- `/v1/health` returns healthy
- A new developer can map “where does X live?” from the README in under 5 minutes

### Out of scope

Auth, RAG, guardrails, Kafka, Grafana.

---

## Version 2 — Authentication, Authorization, and Tenancy Basics

**Goal:** Nothing reaches an LLM (or even the chat handler) without a verified identity, a role, and a tenant.

### Features

- JWT verification
- API key authentication for service-to-service callers
- RBAC roles (example: `platform_admin`, `security_admin`, `app_user`, `viewer`)
- Tenant isolation at the request context level (`tenant_id` on every authenticated request)
- Audit logs for login, key use, auth failures, and permission denials
- PostgreSQL tables: `users`, `api_keys`, `audit_logs`
- Reject unauthenticated and cross-tenant requests by default

### Done when

- Chat and admin endpoints require JWT or API key
- A user from Tenant A cannot read Tenant B’s audit records
- Auth failures are written to `audit_logs`

### Out of scope

Document RBAC filtering (that is Version 6). Multi-org policy UI (Version 11).

---

## Version 3 — Gateway Core: Chat API, Validation, Rate Limits, Streaming

**Goal:** The gateway behaves like an API gateway for LLM traffic: validated requests, fair usage, streaming, and correlation IDs.

### Features

- `POST /v1/chat` contract (OpenAPI)
- Request validation (schema, payload size, required fields)
- Redis rate limiting per user, API key, and tenant
- Redis session / conversation store hook
- Streaming responses (SSE or chunked)
- Correlation IDs on every request and log line
- PostgreSQL `conversations` and `messages` tables
- Error model: stable codes for 400 / 401 / 403 / 429 / 503

### Done when

- A valid client can open a conversation and stream a **stub** response
- Excess traffic is rate-limited without crashing the gateway
- Every log line carries `correlation_id`, `tenant_id`, and `user_id`

### Out of scope

Real RAG and real LLM provider calls can still be stubbed. Guardrails land next.

---

## Version 4 — Input Guardrails

**Goal:** Unsafe prompts never reach retrieval or the model.

### Features (`services/guardrails`)

- Prompt-injection detection
- Jailbreak detection
- Token / context-window limits
- Content moderation (toxicity, abuse)
- Input PII detection (flag or block, configurable)
- Per-tenant policy flags (enable/disable each check)
- Structured guardrail result: `allow | redact | block`, rule id, score, reason
- Security event emission (in-process until Kafka in Version 8)

### Done when

- Known injection / jailbreak fixtures are blocked
- Over-long prompts are rejected before retrieval
- Blocked requests still produce an audit record

### Out of scope

Output hallucination checks (Version 7). Retrieval RBAC (Version 6).

---

## Version 5 — Document Store and RAG Pipeline (MVP)

**Goal:** Grounded answers from tenant-owned documents using a real retriever and one LLM provider.

### Features (`services/rag`)

- PostgreSQL `documents` and `chunks` (plus vector store — pgvector or a Compose sidecar)
- Document ingest API or worker job: chunk, embed, store metadata (`tenant_id`, `acl`, `classification`)
- Query classification (chitchat vs knowledge vs blocked)
- Vector search MVP
- Grounded generation: answer only from retrieved context
- Provider-agnostic `LLMClient` interface with **one** working adapter (for example OpenAI-compatible)
- Citations in the response payload (document id + chunk id)

### Done when

- Ingest a small corpus, ask a question, get an answer with citations
- Questions with no supporting chunks return a safe “I don’t know” rather than invention
- A second provider can be added later by implementing the same interface

### Out of scope

Hybrid BM25 + rerank (Version 6). Multi-provider routing (Version 11).

---

## Version 6 — Hybrid Retrieval and Retrieval Guardrails

**Goal:** Retrieval is high-quality **and** policy-safe. Unauthorized chunks never reach the LLM.

### Features

- Hybrid search: BM25 + vector
- Reranking
- Context filtering (dedupe, relevance threshold, max tokens)
- Retrieval guardrails:
  - RBAC filtering
  - Tenant filtering
  - Secret removal from chunks
  - Sensitive-chunk filtering (legal / HR / classified)
- Zero unauthorized document exposure as a hard invariant
- Retrieval debug payload for engineers (behind a flag)

### Done when

- Hybrid search beats vector-only on a small golden set
- A user without access never sees restricted chunks in traces or answers
- Secrets in source docs are stripped before prompt construction

---

## Version 7 — Output Guardrails (PRD V1 complete)

**Goal:** The user only sees answers that are cited, non-leaking, and honest about uncertainty. This completes PRD V1.

### Features

- Hallucination / unsupported-claim detection
- Citation verification (every factual claim maps to a retrieved chunk)
- Output PII redaction
- Confidence scoring
- Block or rewrite when verification fails
- Final response envelope: answer, citations, confidence, guardrail decisions

### Done when

- Answers without citations are rejected or rewritten
- PII in model output is redacted
- Success metrics can start being measured: groundedness, hallucination rate

### PRD V1 exit

Secure gateway + RAG + input / retrieval / output guardrails is live in Docker Compose.

---

## Version 8 — Kafka, Workers, and Event Backbone (start of PRD V2)

**Goal:** Request handling stays fast; analytics, evals, and security processing happen asynchronously.

### Features (`apps/worker`)

- Kafka in Docker Compose
- Topics:
  - `ai.requests`
  - `ai.responses`
  - `ai.security`
  - `ai.evaluations`
- Gateway publishes after each stage; workers consume
- Analytics consumer stub (counts, latency histograms into Prometheus later)
- Retry / dead-letter handling
- Redis distributed locks where workers must not double-process

### Done when

- A chat request produces request, response, and (if needed) security events
- Killing a worker does not lose the HTTP response to the client
- Topics and consumer groups are documented

---

## Version 9 — Observability Platform

**Goal:** Anyone can answer “what happened to this request?” and “is the gateway healthy?” without SSH.

### Features

- OpenTelemetry traces across gateway, guardrails, RAG, LLM, worker
- Prometheus metrics: QPS, errors, P95 latency, guardrail block rate, cache hit rate
- Grafana dashboards
- Correlation IDs propagated through Kafka headers
- `GET /v1/metrics`
- Latency tracking toward the SAS target: **P95 under 2 seconds**
- Full audit trail queryable by `correlation_id`

### Done when

- Grafana shows live traffic after `docker compose up`
- A single correlation ID reconstructs the full path
- Dashboards exist for latency, safety blocks, and RAG miss rate

---

## Version 10 — Evaluation Framework and Self-Healing

**Goal:** Quality is measured before release and repaired at runtime when retrieval is weak. This completes PRD V2.

### Features (`services/evals`)

- Golden datasets
- Metrics: faithfulness, context recall, context precision, answer correctness, latency
- `POST /v1/evaluate`
- Offline eval in CI (quality gates)
- Online scoring from production traces + optional user feedback
- PostgreSQL `evaluations` table
- Self-healing pipeline:
  - Retry with more context
  - Rewrite query
  - Change reranker
  - Escalate failures (flag for human review)
- Semantic cache in Redis for repeated questions (safe cache keys: tenant + policy version + query embedding)

### Done when

- A golden set must pass before a build is considered releasable
- Low-faithfulness answers trigger retry/rewrite rather than silent failure
- Faithfulness target from SAS (**above 95%** on the golden set) is tracked, even if not yet met

### PRD V2 exit

Observability, automated evals, and a first self-healing loop are in production-shaped Compose.

---

## Version 11 — Multi-Tenancy, Model Routing, MCP, and Human Approval

**Goal:** One gateway serves HR, Engineering, Legal, and Support with org-level policies, cost-aware routing, and tool use. This starts PRD V3.

### Features

- Organization-level policies (model allowlists, retention, guardrail strictness)
- Dynamic model routing by cost, latency, and capability
- At least two live LLM providers behind the same interface
- MCP tool integrations with allowlists and sandboxing
- Human approval workflows for high-risk actions (legal send, production change, PII export)
- Cost tracking per tenant / model / route
- Governance APIs: who asked what, which policy applied, which model answered

### Done when

- Two tenants can have different models and guardrail strictness
- A high-risk tool call waits for approval
- Routing prefers cheaper/faster models when quality budget allows

### Out of scope

Full Kubernetes production (Version 12). Polished enterprise dashboard UI can be API-first here.

---

## Version 12 — Kubernetes, Security Hardening, and Governance Product

**Goal:** Enterprise-ready operations: scale-out, threat-model controls, and a governance surface. This completes PRD V3.

### Features

- Kubernetes manifests / Helm:
  - Ingress
  - Autoscaling
  - Rolling updates
  - Secrets and ConfigMaps
- CI/CD: GitHub Actions, container builds, tests, quality gates
- Threat-model hardening (STRIDE from SAS):
  - Spoofing — strong auth, key rotation
  - Tampering — signed payloads / integrity of prompts and policies
  - Repudiation — immutable audit logs
  - Information disclosure — tenant isolation tests, secret scanning
  - DoS — rate limits, timeouts, bulkheads
  - Privilege escalation — RBAC tests, least privilege
- Enterprise governance dashboard (or a solid Grafana + admin API equivalent)
- Cost optimization reports
- Runbooks: failure scenarios, scaling, security incidents
- Interview / ops pack: tradeoffs, scaling questions, failure modes (from SAS)

### Done when

- The stack deploys to a local Kubernetes (kind/k3d) as well as Compose
- CI blocks merges that fail tests or eval gates
- STRIDE controls are listed with the test or log that proves each one
- A new engineer can operate, debug, and explain the system from docs alone

---

## Cross-cutting rules (every version)

These are SAS acceptance criteria and apply to **all 12 versions**, not only the first:

1. Docker-compatible; no “install Postgres/Redis/Kafka on the host”
2. Health checks on every service
3. Structured logging
4. Environment-based configuration
5. Production-safe defaults
6. Interfaces before implementations
7. Service boundaries preserved (`gateway` does not contain RAG internals)
8. README / docs updated in the same version as the code
9. Tests for the version’s happy path and the safety-critical failure path

## Suggested sequencing for coding agents

From the SAS kickstart guide, adapted to this 12-version plan:

1. Generate gateway skeleton (Version 1)
2. Generate auth (Version 2)
3. Generate gateway request path (Version 3)
4. Generate guardrail service — input, then retrieval, then output (Versions 4, 6, 7)
5. Generate RAG service (Versions 5–6)
6. Generate worker + Kafka (Version 8)
7. Generate evals (Version 10)
8. Generate infrastructure (Compose from v1, Kubernetes in v12)
9. Generate tests continuously — not as a final dump

## Feature index (where each SAS/PRD item lands)

| Capability | Version |
|------------|---------|
| Repo, Docker, health, config, interfaces | 1 |
| JWT, API keys, RBAC, tenant context, auth audit | 2 |
| `/v1/chat`, validation, rate limit, streaming | 3 |
| Input guardrails (injection, jailbreak, toxicity, token limits) | 4 |
| Documents, vector RAG, grounded generation, one LLM adapter | 5 |
| Hybrid search, rerank, retrieval RBAC / tenant / secrets | 6 |
| Output hallucination, citations, PII, confidence | 7 |
| Kafka topics, workers, analytics consumers | 8 |
| OpenTelemetry, Prometheus, Grafana, correlation IDs | 9 |
| Golden evals, faithfulness/recall, self-healing, semantic cache | 10 |
| Multi-tenancy policies, model routing, MCP, human approval, cost | 11 |
| Kubernetes, CI/CD, STRIDE hardening, governance dashboards | 12 |
