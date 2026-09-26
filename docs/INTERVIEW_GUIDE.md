# AI Safety Gateway — interview guide

Use this as the spoken version of the repo. Version 12 is what is shipped. Compose is how you run and test it. Kubernetes is an optional install path beside Compose, not a replacement.

## 30-second pitch

This is Docker-first middleware between applications and LLM providers. One public gateway standardizes authentication, role checks, rate limits, input and output safety checks, tenant-scoped document retrieval, grounded answers with citations, evaluation, audit, and cost reporting. Every product team does not rebuild those controls.

The gateway orchestrates. It is the only public HTTP port. Auth, guardrails, RAG, evals, and the analytics worker stay internal. RAG retrieves. It does not generate. The gateway is the only service that calls the language model.

## What problem it solves

An application that calls an LLM directly has to invent, over and over:

- who the caller is, which tenant they belong to, and what they are allowed to do
- how much they can call
- whether the prompt is an injection, a secret, or toxic
- which documents they may see
- whether the answer is actually supported by those documents
- whether a secret leaked into the answer
- an audit trail that does not store the raw prompt
- a way to measure quality and estimated cost without putting user text on a bus

The gateway is that shared layer. Clients talk only to `POST /v1/chat` and the other public `/v1` routes.

## How the code is organized

| Path | Owns |
|------|------|
| `apps/gateway` | Public API, chat orchestration, rate limits, conversations, citation checks, output secret redaction, SSE, Kafka publish, LLM calls, governance rows |
| `services/auth` | Tenants, users, password hashes, API keys, refresh tokens, audit log, HS256 access tokens |
| `services/guardrails` | Input rules, per-tenant policy, fixture or live moderation, Jev scores, thin output check |
| `services/rag` | Ingest, chunk, embed, hybrid search, classification, ACL, secret masking inside chunk text |
| `services/evals` | Golden set, lexical scores, numeric evaluation rows |
| `apps/worker` | Kafka consumer: counts metadata events, dead-letters after retries |
| `apps/web` | Static explainer and playground. Not on the request path |
| `packages/contracts` | Pydantic models and ports (`AuthProvider`, `Guardrail`, `Retriever`, `LLMClient`, `Evaluator`) |
| `packages/config` | Environment settings |
| `packages/telemetry` | JSON logs with correlation id |
| `packages/testing` | Fake port implementations |
| `infrastructure/docker` | Shared Dockerfiles |
| `infrastructure/k8s` | Plain Kubernetes manifests. No Helm |

`packages/*` does not import `apps/*` or `services/*`. Interfaces live in contracts before implementations.

One Postgres database (`pgvector/pgvector:pg16`). Each service migrates its own tables through Alembic. The `migrate` container runs **auth, then gateway, then guardrails, then rag, then evals**, then exits 0.

## Who may call what

Seeded local users (password `changeme`):

| Email | Tenant | Role | Can do |
|-------|--------|------|--------|
| `admin@platform.local` | platform | `platform_admin` | Everything, including another tenant when they pass `tenant_id` |
| `sec@hr.local` | acme-hr | `security_admin` | Chat, ingest, policy, evaluate, approvals, governance |
| `user@hr.local` | acme-hr | `app_user` | Chat |
| `user@eng.local` | acme-eng | `app_user` | Chat in Engineering only |
| `view@eng.local` | acme-eng | `viewer` | Read conversations. Chat is 403 |

Demo HR API key: `agt_demo_hr_local_docker_only_key`. Send it as `X-API-Key`. Humans send `Authorization: Bearer`.

Every query that is not `platform_admin` filters `tenant_id` to the caller’s tenant. A non-platform caller who names another `tenant_id` gets 403.

## Credentials and why they are split

| Secret | Lives only on |
|--------|----------------|
| `JWT_SECRET` | auth |
| `GUARDRAILS_API_KEY`, `JEV_API_KEY` | guardrails |
| `EMBEDDING_API_KEY` | rag |
| `OPENAI_API_KEY` and provider B key | gateway |
| `INTERNAL_AUTH_TOKEN` | gateway, auth, guardrails, rag, worker |

Internal calls send `X-Internal-Token`. The browser console never receives that token. Leaking the gateway image is not enough to mint JWTs or read the embedding key. Missing credentials, bad tokens, and cross-tenant access fail closed (401 or 403).

Compose defaults are fixture and keyless: `GUARDRAILS_MODE=fixture`, `EMBEDDING_MODE=fixture`, `LLM_MODE=fixture`. Live mode is opt-in and fails closed if the key or model is missing. There is no silent fallback from a live provider to a stub.

---

## Workflow 1 — login and identity

1. Client calls `POST /v1/auth/login` on the gateway. No prior token.
2. Gateway proxies to auth.
3. Auth checks the Argon2id password hash in Postgres.
4. Auth returns an HS256 access JWT and an opaque refresh token. The refresh token is stored hashed and rotated on use.
5. Later requests hit the gateway. The gateway calls `POST /internal/v1/introspect` on auth. Auth returns an `AuthContext`: user, tenant, role, and optional API-key prefix.
6. Gateway never holds `JWT_SECRET` and never reads the user table.

Logout and refresh are also proxied. `GET /v1/me` and API-key creation require a valid identity. Admin routes under `/v1/admin` are `platform_admin`.

Audit rows are append-only. There is no delete route, so a client cannot erase them. Audit metadata stores a SHA-256 of a blocked prompt, not the prompt.

## Workflow 2 — `POST /v1/chat` (the main path)

This is the only generation path. Order matters. Say it in this order in an interview.

1. **Introspect** the JWT or API key. Missing or invalid → 401.
2. **Publish** one metadata event to `ai.requests` (best-effort, 0.5s timeout).
3. **Authorize the role.** `viewer` cannot chat → 403. `debug: true` is only `security_admin` and `platform_admin` → otherwise 403.
4. **Rate limit** with Redis token buckets for the tenant and for the user or API key. Over quota → 429. Redis down → 503 `rate_limiter_unavailable`. Burst is twice the per-minute limit. Defaults: tenant 60/min, user 20/min, API key 60/min.
5. **Input guardrails**, 2 second timeout. Down or slow → 503 `guardrails_unavailable`. Decision `block` → 400 `input_blocked`. No new conversation is created. The audit row stores the prompt hash and rule decisions.
6. **Route.** Read the tenant policy allowlist and `route_preference` (`cheap` or `capable`). Pick the first allowlisted model in that class. Empty or non-matching allowlist → 403. The gateway calls only that provider. It does not fail over to the other one.
7. **Tool allowlist.** Optional `tool` must be on the policy. Off the list → 403.
8. **Persist the user turn** using the redacted text if guardrails redacted a secret. A new conversation is created only after the input check passes.
9. **Branch:**
   - `export_directory`: write a pending approval, skip the LLM, return HTTP 200 with `approval_id`. Nothing is exported.
   - `lookup_leave`: return fixture leave text. No LLM.
   - **Chitchat** (a greeting): call the LLM with no retrieved context.
   - **Knowledge:** look up the answer cache, otherwise retrieve and generate (workflow 3).
10. **Output check** (Jev toxicity / PII / confidence), same 2 second fail-closed timeout. A block replaces the answer with a refusal and clears citations.
11. **Store** the assistant message and refresh the Redis session cache for that conversation.
12. **Best-effort side effects:** numeric evaluation row and one `ai.evaluations` event (skipped for chitchat and tools), governance row with estimated cost, Prometheus cost counter. Failures here do not change the HTTP status.
13. **Respond** JSON, or SSE if `stream: true`.
14. **Publish** `ai.responses`. If the attempt was an input block, output block, citation redact, or output secret redaction, also publish `ai.security`.

Streaming does not token-stream the raw model. The gateway finishes generation, citation checks, and the output check, then replays the final text as `event: meta`, `event: token`, `event: done`. Citations are on `done`.

`ChatResponse` includes `answer`, `citations`, `confidence` (Jev safety score), `groundedness`, `trace_id` (the correlation id), `conversation_id`, `message_id`, guardrail decisions, optional retrieval debug, `provider`, `model`, and `approval_id`. It does **not** include `estimated_cost`. Cost is on the governance read, not the chat body.

## Workflow 3 — knowledge answer, retrieval, and citations

Used when the message is not chitchat and not a tool.

**Answer cache (Redis).** Key is tenant, role, guardrail policy hash, and SHA-256 of the normalized query. Hits skip retrieve and the LLM. Blocks, `debug: true`, and streams are not cached. A hit still runs the output guardrail check. A stored answer is written only when groundedness is at least 0.5, the output check did not block, and the request was a normal non-stream knowledge chat. Ingest and delete clear that tenant’s cached answers.

**Retrieve** (`POST /internal/v1/retrieve` on RAG, 2 second timeout). Down or slow → 503 `rag_unavailable`. Inside RAG, in order:

1. Filter `tenant_id`.
2. Classification and ACL.
3. Vector search and Postgres full-text search. Each leg returns up to `RAG_CANDIDATE_K` (32). Vector hits below cosine `RAG_MIN_SCORE` (0.3) are dropped **before** fusion. The fused score is not compared to 0.3, because reciprocal-rank scores are tiny and a lexical-only hit would vanish.
4. Reciprocal rank fusion with `k = 60`.
5. Mask secrets in the chunk text sent onward: `sk-`, `agt_`, `password=`, and AWS-style key ids become `[SECRET]`. The stored document body keeps the original secret.
6. Token-overlap rerank, drop duplicate normalized text, keep `RAG_TOP_K` (8), stop at 8000 characters.

**No chunks above the minimum score:** HTTP 200, answer exactly `I don't know based on the available documents.`, `citations: []`, `groundedness: null`. The LLM is not called.

**Hits:** gateway calls `LLMClient.generate` with those chunks. Fixture mode emits one sentence per chunk so a keyless demo stays supported. Live mode uses an OpenAI-compatible Chat Completions API, 30 second timeout. Down, slow, or missing key/model → 503 `llm_unavailable`.

**Citation check (on the gateway, after generate):**

1. Redact the same secret patterns in the answer to `[SECRET]`.
2. Split sentences on `.` `!` `?`. A period between digits stays inside the sentence.
3. A sentence is supported when at least half of its `[a-z0-9]+` tokens appear in one returned chunk. The exact I-don’t-know sentence is supported without a chunk. Sentences with no tokens are ignored.
4. Drop unsupported sentences. They are not stored, streamed, or logged. The audit records `dropped=N` and `groundedness`.
5. If nothing remains, return the I-don’t-know string, empty citations, `groundedness: 0`.
6. Otherwise citations are only the chunks that support a kept sentence, in prompt order. `groundedness` is supported sentences divided by sentences checked.
7. Chitchat and the no-chunk path skip this check. `groundedness` is null.

**One retrieval retry.** If chunks came back and groundedness is under 0.5, retrieve once more with stopwords removed. Keep the better groundedness. The no-chunk path does not retry. There is no second LLM call for the retry itself beyond generating from the better context. A row that stays under 0.5 with chunks is marked `review` in evaluation.

`debug: true` returns ranks and drop reasons. It never returns chunk text, and it hides policy-denied rows.

## Workflow 4 — document ingest

`POST`, `GET`, and `DELETE /v1/documents` are `security_admin` (own tenant) or `platform_admin` (any tenant via `tenant_id`). `app_user` gets 403.

1. Gateway introspects, then proxies to RAG.
2. RAG chunks the text, embeds it, and stores `documents` and `chunks`.
3. Fixture embeddings are a deterministic hash into 256 dimensions. Live embeddings call an OpenAI-compatible API with `dimensions: 256` so the column never changes. The gateway never sees the embedding key.
4. Decoded text over 256 KiB → 400 `payload_too_large`.
5. DELETE cascades chunks and vectors and clears that tenant’s answer cache.

Classification and ACL on ingest:

| Classification | Who can retrieve it |
|----------------|---------------------|
| null, `public`, `internal` | every role in the tenant |
| `confidential` | `security_admin` and `platform_admin` |
| `restricted` | `platform_admin` only |

`acl` is a list of role names. Empty ACL means every role in the tenant. A non-empty ACL must also include the caller’s role. Retrieval applies tenant, role, classification, and ACL inside RAG, so an unauthorized chunk never reaches the prompt.

## Workflow 5 — guardrail policy

`GET` and `PATCH /v1/guardrails/policy` use the same admin roles. The policy holds:

- which input checks are on
- `route_preference`: `cheap` or `capable`
- `model_allowlist` and `tool_allowlist`
- `strictness`
- `retention_days` (stored only; nothing is deleted by it)

`strict` turns Jev on and uses threshold 0.3 **for that check**. It does not rewrite the saved thresholds.

Input decisions are `allow`, `redact`, or `block`, each with a rule id, score, and reason. Fixture mode blocks known injection strings such as `ignore previous instructions` without a Perspective or TypeSafe key. A secret in the user text (`sk-...`) is redacted to `[SECRET]` before it is stored or sent onward.

Jev, when the key is empty, is a fixture calibrated scorer (injection, jailbreak, toxicity, PII, risk, route). A live key lives only on the guardrails container. Citation and hallucination checks are **not** Jev. Those are the lexical sentence check on the gateway.

## Workflow 6 — tools and human approval

The model does not invent tool calls. The client sets `tool` on `POST /v1/chat`.

| Tool | Behavior |
|------|----------|
| `lookup_leave` | Fixture leave text. No LLM. |
| `export_directory` | Inserts an approval row, skips the LLM, HTTP 200 with `approval_id`. Status stays pending. |

`POST /v1/approvals/{id}` is `security_admin` for that tenant or `platform_admin`. The requester cannot approve their own request. Approve or deny does not call the LLM and does not perform the export. This is one high-risk tool with a human gate, not a general tool runtime.

## Workflow 7 — evaluation

Golden set: `services/evals/golden/hr.json`. Eight Acme HR leave questions and two I-don’t-know questions. Each case has a question and expected terms. There is no expected answer paragraph.

`POST /v1/evaluate` is `security_admin` or `platform_admin`. The gateway runs those questions through the normal chat path and stores the run. The report includes `target_faithfulness` 0.95 and `met_target`. A mean under 0.95 is recorded and does **not** fail Compose tests or CI. A case error or a missing faithfulness score does fail the suite.

Scores are lexical, not a judge model:

- Faithfulness is groundedness. The exact I-don’t-know sentence scores 1.0 when groundedness is null.
- Context recall: share of expected terms found in any chunk.
- Context precision: share of chunks that contain an expected term.
- Answer correctness: share of expected terms found in the answer.

After a normal knowledge chat, the gateway best-effort writes one numeric row and publishes one `ai.evaluations` event. No prompt, answer, or chunk text. Chitchat and tools skip this. Chat still returns 200 if evals is down. `POST /v1/evaluate` returns 503 `evals_unavailable` when evals is down. `/v1/ready` does not check evals.

Optional `feedback` on evaluate is `up` or `down`. It is not a chat field.

## Workflow 8 — governance and cost

A static price table supplies `estimated_cost` for the chosen model. Tool calls record cost 0.

- `GET /v1/governance?correlation_id=` returns provider, model, route, estimated cost, and approval status for **that tenant**. No prompt or answer. Another tenant’s id is an empty list. Read failure → 503 `governance_unavailable`. The write during chat is best-effort.
- `GET /v1/governance/summary` is `security_admin` and `platform_admin`. It sums `estimated_cost` and request count by model for that tenant. A non-platform caller who passes another `tenant_id` gets 403.
- Prometheus counter `aigateway_estimated_cost_dollars_total` is labeled by model only. No user id or tenant id on the metric. Grafana has an estimated-cost panel.

`/v1/ready` does not ping LLM providers.

## Workflow 9 — events, metrics, traces

**Kafka.** One KRaft broker, no ZooKeeper. Topics: `ai.requests`, `ai.responses`, `ai.security`, `ai.evaluations`, each with a `.dlq`. One partition, replication factor 1. The gateway creates them on startup.

Payloads are metadata: event id, correlation id, tenant, user, status, latency, rule ids, citation count, groundedness, and similar fields. Never a prompt, answer, chunk, document body, or secret span. The correlation id is also the `X-Correlation-ID` header.

Publish timeout defaults to 0.5 seconds. A broker error is logged. Chat HTTP status stays whatever the pipeline already decided.

`/v1/ready` is 200 only if Postgres, Redis, auth, guardrails, rag, **and Kafka** respond. It does not ping a live LLM, Prometheus, Tempo, Grafana, or evals.

**Worker** group `aigateway-analytics` counts those four topics. A message is retried 3 times, then written to that topic’s dead-letter queue. Redis key `kafka:event:{event_id}` skips a redelivery that was already counted. `GET /internal/v1/counts` on the worker requires `X-Internal-Token`. It is not a gateway route. Killing the worker does not change chat HTTP status.

**Prometheus** scrapes gateway, auth, guardrails, RAG, and the worker. `GET /v1/metrics` on the gateway is unauthenticated Prometheus text. Labels are route, method, status, and outcome. No user id, tenant id, prompt, or answer.

**Grafana** is on port 3000 as an anonymous Viewer. Dashboards: latency (with a 2 second line), safety blocks, RAG misses, and estimated cost.

**Tempo** receives traces over OTLP. Export is best-effort. A trace failure does not change chat status.

**Audit read:** `GET /v1/audit?correlation_id=` returns that tenant’s matching rows. Another tenant’s id returns an empty list.

## Workflow 10 — conversations

`GET /v1/conversations` and `GET /v1/conversations/{id}` are tenant-scoped. Tenant A cannot read Tenant B’s conversations or documents. Continuing a chat requires the conversation to belong to the caller’s tenant. History for the next turn comes from the Redis session cache, or from Postgres messages if the cache misses. The stored user text is the redacted text.

## Workflow 11 — Kubernetes (Version 12)

Compose remains the default and is still required for tests. Manifests in `infrastructure/k8s` are plain YAML. There is no Helm chart.

- Namespace `aigateway`.
- Images are built locally and tagged `aigateway/<service>:local`.
- Run the `migrate` Job and wait for it before app Deployments.
- Postgres, Redis, and Kafka stay single-replica.
- Ingress sends `/v1` only to the gateway.
- The gateway Deployment rolls and has an HPA from 1 to 2 replicas. Every other app stays at 1 replica.
- CI checks manifests with kubeconform. That fails a bad manifest. It does not prove pods start (there is no kind cluster in CI).

## Failure behavior (memorize this table)

| Dependency | What the client sees |
|------------|----------------------|
| Bad or missing token | 401 |
| Wrong role, other tenant, tool or model not allowed, debug forbidden | 403 |
| Input guardrail block | 400 `input_blocked`, no new conversation |
| Over quota | 429 |
| Redis down on chat | 503 `rate_limiter_unavailable` |
| Guardrails down or slower than 2s | 503 `guardrails_unavailable` |
| RAG down or slower than 2s | 503 `rag_unavailable` |
| Live LLM down, slower than 30s, or missing key/model | 503 `llm_unavailable` |
| No supporting chunks | 200 and the fixed I-don’t-know string |
| Evals down during chat | chat still 200; evaluate route is 503 `evals_unavailable` |
| Kafka down at ready time | `/v1/ready` is 503 |
| Kafka down after ready, or worker down | chat status unchanged; event may be dropped |
| Governance write fails | chat status unchanged |
| Governance read fails | 503 `governance_unavailable` |

Logs are JSON and include correlation id, plus `user_id` and `tenant_id` when known. They never include raw passwords, refresh tokens, full API keys (prefix only), raw prompts, model answers, dropped sentences, secret spans, document bodies, or chunk text. Kafka payloads, traces, evaluation rows, and governance rows follow the same rule.

## What each version added

| Version | You should be able to say |
|---------|---------------------------|
| 1 | Compose skeleton, health, JSON logs, ports in contracts, four ADRs (FastAPI, Redis, Kafka, Postgres) |
| 2 | Auth service, HS256, API keys, RBAC, tenants, audit. Gateway introspects |
| 3 | Chat contract, validation, Redis rate limits, SSE, conversations, correlation ids, stable error codes. Answers were still stubs |
| 4 | Input guardrails: injection, jailbreak, length, moderation, PII, per-tenant policy, Jev fixture |
| 5 | Documents, chunks, pgvector, grounded generation, citations, I-don’t-know when nothing is retrieved |
| 6 | Hybrid BM25 + vector, RRF, rerank, ACL, classification, secret masking, debug ranks |
| 7 | Sentence-level citation verification, output secret redaction, thin Jev output check, fail-closed timeouts |
| 8 | Metadata Kafka events, worker counts, dead-letter queue, ready checks Kafka |
| 9 | Prometheus, Grafana, Tempo, correlation id on audit reads |
| 10 | Lexical golden-set eval, one retrieval retry, tenant answer cache |
| 11 | Two providers, cheap/capable routing, two tools, human approval, governance read |
| 12 | Plain Kubernetes manifests, tenant cost summary, cost metric |

OpenAPI on the gateway is **0.11.0**.

## Design choices you will be asked to defend

- **FastAPI, not Spring Boot.** One language across gateway and services, async HTTP, OpenAPI from the same models. The team constraint was a Python monorepo.
- **Redis, not Memcached.** Token buckets, session cache, answer cache, and the Kafka idempotency key need richer values and TTLs than a pure cache.
- **Kafka, not RabbitMQ.** A log of metadata events that a worker can replay and dead-letter. One broker in KRaft is enough for the demo. Replication factor 1 is an explicit single-node tradeoff.
- **Postgres + pgvector, not MongoDB or a separate search cluster.** Tenancy, conversations, documents, and vectors stay in one database the migrate job already runs. BM25 is `tsvector` with the `simple` dictionary so tokens are not stemmed away. OpenSearch was rejected because it is another stateful service.
- **Auth in its own service, HS256.** The gateway must not hold `JWT_SECRET`. HS256 is enough for one shared secret in a Docker demo. RS256 and an identity provider are a later step. Every request pays an introspect hop on purpose.
- **Interfaces in `packages/contracts`.** Tests can fake `LLMClient` and `Retriever` without booting providers. Packages cannot import services, so the dependency direction stays one way.
- **Fail closed on safety dependencies, fail open on telemetry.** Redis, guardrails, and RAG being down must not let a prompt through. Kafka, Tempo, evals-on-chat, and the governance write must not turn a finished answer into a 503.
- **Lexical citations, not a judge model.** A second model needs a key and breaks the keyless Compose rule. The cost is that a true paraphrase can be dropped. That is accepted.
- **RRF `k=60`, and do not threshold the fused score at 0.3.** The 0.3 cutoff is cosine similarity. RRF scores are ranks. Applying 0.3 after fusion would delete lexical-only hits.
- **Fixture embeddings are hashed 256-d vectors.** Demos and CI do not need an embedding key. Live mode sends `dimensions: 256` so the column matches.
- **Two OpenAI-compatible providers, no failover.** Predictable cost and an explicit allowlist. A capable-route outage stays 503 rather than silently spending or answering on the cheap model.
- **Metadata-only events.** The bus is for counts and correlation, not a second copy of user content.
- **Plain Kubernetes YAML.** Readable and checkable with kubeconform. Helm values were out of scope. The gateway is the only Deployment with an HPA, and only from 1 to 2 replicas.
- **95% faithfulness is a target, not a CI gate.** A weak fixture or a wording change should be visible on the report. A crash or a missing score should still fail the suite.

## What is intentionally not built

Say this if they ask “what would you do next?” Do not pretend these exist.

- No Helm, no multi-broker Kafka, no second availability zone.
- No RS256, OIDC, or JWKS. Key rotation is a process restart. Two secrets are not accepted at once.
- No real MCP server. Tools are two named fixtures.
- Approving `export_directory` does not export data.
- `retention_days` is stored and not enforced.
- No judge-model evaluation, no cross-encoder reranker, no query rewriting, no English stemming (`simple` dictionary).
- No prompt or answer text in logs, Kafka, traces, eval rows, or governance.
- The web console does not show worker counts or a cost page.
- Audit rows are append-only and are not a hash chain.
- `/v1/ready` does not prove the LLM provider is up.
- kubeconform does not prove the cluster actually starts.

## A story you can tell out loud

“Acme HR and Acme Engineering share one gateway. An HR employee asks how many PTO days they get. I introspect their JWT, rate-limit them, and run injection checks. The prompt is a knowledge question, so RAG searches only Acme HR chunks that their role may see, fuses vector and keyword ranks, and masks any secret in the chunk. The model answers from that context. I drop any sentence that does not overlap a chunk, redact secrets in the answer, and run a toxicity check. They get citations and a groundedness score. Engineering asking the same question must not see HR document ids. If they paste an API key, we store `[SECRET]`. If they say ‘ignore previous instructions’, we return 400 and do not open a conversation. If they ask to export the directory, we do not export. We store an approval and a different admin has to decide it. Operators can ask what that request cost, by correlation id, without us having stored the question.”

---

## Interview questions and answers

### Product and architecture

**Q1. What is this project in one sentence?**  
A Docker-first gateway that sits between applications and LLM providers and enforces identity, tenancy, rate limits, guardrails, tenant-scoped retrieval, grounded answers, and metadata-only audit, so each app does not rebuild that stack.

**Q2. Why is the gateway the only public port?**  
Callers get one contract and one place for auth, limits, and policy. Auth, guardrails, RAG, evals, and the worker are not exposed. The Kubernetes Ingress forwards only `/v1` to the gateway. The web console is a static client of that same public API.

**Q3. Why doesn’t RAG generate the answer?**  
Retrieval and generation have different secrets, timeouts, and failure modes. RAG holds document text and the embedding key. The gateway holds the LLM key and is accountable for the citation check. Mixing them would let a retrieval bug become a generation path that skips the gateway’s output checks.

**Q4. Why are interfaces in `packages/contracts` before implementations?**  
Ports (`AuthProvider`, `Guardrail`, `Retriever`, `LLMClient`, `Evaluator`) let the gateway depend on behavior, not on a concrete vendor. Tests use fakes. Packages are forbidden from importing apps or services, so the graph cannot cycle.

**Q5. What does the gateway refuse to store or know?**  
`JWT_SECRET`, guardrail and Jev keys, the embedding key, and the user tables. It may hold the LLM key because it is the component that calls the model.

**Q6. How do services authenticate to each other?**  
`X-Internal-Token` equal to `INTERNAL_AUTH_TOKEN`. Introspect, guardrail check, retrieve, and ingest all use it. The browser never receives it.

**Q7. Why HS256 in a separate auth service?**  
One shared secret is enough for a single-operator demo, and that secret stays off the gateway, so a leaked edge container cannot mint tokens. Refresh tokens are opaque and Argon2id-hashed, rotated on use. The tradeoff is an introspect call on every protected request. RS256 and an external identity provider are the enterprise follow-up.

**Q8. How does multi-tenancy work?**  
Every authenticated context has a `tenant_id`. Non-platform queries filter to that id. `platform_admin` may pass `tenant_id` to act in another tenant. Conversations, documents, chunks, audit reads, evaluation rows, and governance reads are all tenant-scoped. Tenant A asking an HR question must not receive HR document ids.

**Q9. What are the roles?**  
`platform_admin` (any tenant), `security_admin` (policy, ingest, evaluate, approvals, governance for their tenant), `app_user` (chat), `viewer` (read conversations, chat forbidden), plus service accounts via API keys.

**Q10. Why fail closed sometimes and best-effort other times?**  
Safety dependencies gate the answer: Redis, guardrails, RAG, and a live LLM. If they are down, returning a model answer would skip a control. Telemetry and analytics do not gate the answer: Kafka publish, traces, online eval, and the governance write. A broker outage must not look like a model failure to the client. Readiness is stricter than chat: `/v1/ready` includes Kafka so you do not send traffic to an instance that cannot emit events, but a later publish failure still returns the chat status you already decided.

### Chat pipeline

**Q11. Walk through `POST /v1/chat`.**  
Introspect, publish a request event, check the chat role, consume the rate limit, run input guardrails, select the cheap or capable route, enforce the tool allowlist, store the redacted user message, then either create an approval, return fixture tool text, generate chitchat, or retrieve and generate. Then run the output check, store the assistant message, best-effort eval and governance, and return JSON or SSE. Response and security events publish beside that result.

**Q12. Why is the conversation created only after input guardrails?**  
A blocked injection should not create a conversation. The 400 path audits a hash of the prompt and the rule decisions, and stops.

**Q13. What is chitchat versus a knowledge question?**  
A greeting skips retrieval and the sentence-level citation check. `groundedness` is null. A knowledge question always goes through RAG unless it is served from the answer cache or it is a tool.

**Q14. What happens when nothing relevant is retrieved?**  
HTTP 200 with exactly `I don't know based on the available documents.`, empty citations, and null groundedness. The LLM is not called, so the model cannot invent an answer. The same string is used when every generated sentence fails the citation check; in that case groundedness is 0.

**Q15. Why can a blocked request be 400 while a missing-document request is 200?**  
400 means the user input violated policy. 200 with I-don’t-know means the system behaved correctly and refused to guess. Conflating them would make clients retry policy violations or treat a safe abstention as an outage.

**Q16. Explain groundedness versus confidence.**  
Groundedness is the share of checked sentences that overlapped a retrieved chunk. It is null for chitchat and the no-chunk path, and 0 when every sentence was dropped. Confidence is the Jev safety score. They measure different things: support versus safety.

**Q17. Why is streaming not live token streaming?**  
Citation verification and the output check need the full answer. Streaming tokens first would show a sentence you later have to retract. The gateway generates, verifies, checks, then replays `meta`, `token`, and `done`.

**Q18. What is cached, and what is not?**  
The answer cache key is tenant, role, policy hash, and the SHA-256 of the normalized query. It stores the final redacted answer, citations, and groundedness. Not cached: blocks, debug, streams, chitchat, tools, output blocks, and answers under 0.5 groundedness. A cache hit still runs the output check. Ingest and delete wipe that tenant’s keys. The policy hash means a policy change misses old answers. There is also a short session cache of recent messages per conversation.

**Q19. Why retry retrieval only once, and only under 0.5 groundedness?**  
Stopword noise can hide a lexical match. One extra retrieve with stopwords removed is cheap and bounded. The no-chunk I-don’t-know path does not retry, because there is nothing to repair. A second retry or a second model would add latency and cost without a new safety property.

**Q20. Why doesn’t `ChatResponse` include cost?**  
Cost is an operator concern. Putting it on every chat response couples clients to pricing. Governance and the Prometheus counter carry it. The chat body gained `provider`, `model`, and `approval_id` in Version 11 and stopped there.

### Retrieval and citations

**Q21. Why hybrid search instead of vectors only?**  
Hashed or semantic vectors miss rare exact terms (policy numbers, product names). Postgres full-text (`tsvector` / `ts_rank`, `simple` dictionary, GIN index) supplies the lexical leg. Vectors supply the semantic leg. No extra search container.

**Q22. How does reciprocal rank fusion work here?**  
Each leg returns up to 32 candidates. A document’s fused score sums `1 / (60 + rank)` across legs it appears in. `k = 60` is the standard constant that keeps one high rank from dominating. Vector hits below cosine 0.3 are removed before fusion. The fused score is not compared to 0.3.

**Q23. Why not threshold the fused score at 0.3?**  
0.3 is a cosine cutoff. RRF scores are on the order of `1/60`. Applying 0.3 after fusion would drop every lexical-only hit.

**Q24. What happens after fusion?**  
Secrets in chunk text are masked. A fixture token-overlap rerank orders the list. Duplicates are removed. At most 8 chunks remain, and the prompt stops at 8000 characters.

**Q25. How do you stop a user from seeing another tenant’s or another role’s documents?**  
The filter runs inside RAG before any chunk is returned: tenant id, classification, and ACL. `confidential` is security and platform admins. `restricted` is platform admin only. Empty ACL means every role in that tenant. A non-empty ACL must include the caller. Debug output omits policy-denied rows and never includes chunk text. Tests cover HR versus Engineering isolation.

**Q26. Where are secrets removed?**  
Three places. Input guardrails can redact the user message before it is stored. RAG masks secrets in chunk text before the prompt is built, while the document row keeps the original. The gateway masks the model answer before citation checking and storage. Patterns include `sk-`, `agt_`, `password=`, and AWS-style access key ids. Dropped sentences and secret spans are not logged.

**Q27. How does citation verification work, and what is its weakness?**  
After secret redaction, each sentence must share at least half its alphanumeric tokens with one retrieved chunk. Unsupported sentences are dropped. Citations mean “this chunk supports a kept sentence,” not “this chunk was in the prompt.” The weakness is lexical overlap: a correct paraphrase can be dropped, and a sentence that copies tokens without being logically faithful can be kept. A judge model was rejected because it needs another API key and breaks keyless Compose.

**Q28. What does fixture mode prove?**  
It proves the control path without vendor keys: auth, limits, guardrails, hybrid retrieve, citation overlap, redaction, events, and evals. Fixture generation emits one sentence per retrieved chunk, using that chunk’s text, so the citation check passes for real seeded facts. It does not prove live model quality.

### Guardrails, tools, and routing

**Q29. What input checks exist?**  
Prompt injection, jailbreak, length limits, toxicity or abuse (fixture, or Perspective when live), PII handling, and Jev scores for injection, jailbreak, toxicity, PII, risk, and route. Each check returns allow, redact, or block. Policy can turn checks on or off per tenant.

**Q30. What does `strict` do?**  
For that request, Jev is forced on and thresholds are 0.3. The numbers saved on the policy row are not rewritten.

**Q31. Why two providers with no failover?**  
Tenants choose cheap or capable through policy, and an allowlist constrains which models may run. The gateway calls only the chosen provider. Failing over would hide an outage and could bill the other model against policy. Missing key, timeout, or provider error is 503 `llm_unavailable`. Live cheap uses the OpenAI-compatible settings. Live capable uses `PROVIDER_B_*`. Fixture names are `fixture-a` / `fixture-cheap` and `fixture-b` / `fixture-capable`.

**Q32. How do tools work?**  
The client names `lookup_leave` or `export_directory`. The model does not choose tools. A tool off the allowlist is 403. Leave lookup returns fixture text. Directory export stores a pending approval and skips the LLM. A different admin approves or denies. The requester cannot decide their own row. The decision does not call the model and does not export anything. This is a human gate for one high-risk action.

**Q33. What is the output check?**  
A thin Jev check for toxicity, PII, and confidence on the assistant text, after citation rewriting. If guardrails is down, chat fails closed. If the decision is block, citations are cleared and the client gets the refusal. `confidence` on the response comes from this safety score.

### Data, events, and operations

**Q34. Why one Postgres for every service?**  
Tenancy and joins stay simple, pgvector avoids a second datastore, and one migrate job orders schemas. Each service owns its tables via its own Alembic history: identity, conversations and approvals, policies, documents and chunks, evaluation rows. They do not share application code.

**Q35. What is in Redis?**  
Rate-limit token buckets (`rl:tenant`, `rl:user`, `rl:key`), the conversation session cache, the answer cache, and `kafka:event:{event_id}` so the worker does not double-count a redelivery.

**Q36. What do Kafka events contain?**  
Ids, status, latency, rule ids, citation count, groundedness, and the correlation id. They do not contain prompts, answers, chunks, or secrets. Topics are requests, responses, security, and evaluations, plus a dead-letter topic each. Security events fire for input block, output block, citation redact, or output secret redaction.

**Q37. What does the worker do if processing fails?**  
It retries three times, then produces to that topic’s `.dlq` and commits the offset. The Redis lock is taken when processing starts and kept after success. If the process crashes before success, the TTL can expire so a retry is allowed. Counts are on an internal route, not the public gateway.

**Q38. What does `/v1/health` versus `/v1/ready` mean?**  
Health means the process is up. Ready means Postgres, Redis, auth, guardrails, rag, and Kafka answered. Ready does not call the LLM, Prometheus, Tempo, Grafana, or evals. Chat can still succeed if evals is down. Evaluate cannot.

**Q39. What do you monitor?**  
Prometheus histograms and counters labeled by route, method, status, and outcome, plus a cost counter labeled by model. Grafana shows latency against a 2 second line, safety blocks, RAG misses, and estimated cost. Tempo holds traces. Labels deliberately omit user and tenant so metrics are not a second user store. `GET /v1/metrics` is unauthenticated text; do not put secrets in it.

**Q40. How do you trace one user request?**  
The correlation id is on logs, the `X-Correlation-ID` header, the chat `trace_id`, Kafka events, and the audit query `GET /v1/audit?correlation_id=`. Governance can be read by that same id. You still will not see the prompt text. That is intentional.

**Q41. How does Kubernetes differ from Compose?**  
Same images and the same gateway contract. Manifests are plain YAML in namespace `aigateway`. Migrate is a Job that must finish first. Data stores stay single-replica. Only the gateway scales, and only from 1 to 2 replicas. Ingress is the only public entry. Tests still run with Compose. CI validates YAML with kubeconform and does not start a cluster.

**Q42. How is cost computed?**  
A static price table on the selected model, stored on the governance row and added to `aigateway_estimated_cost_dollars_total{model=...}`. Tools cost 0. The summary endpoint aggregates by model for the caller’s tenant. It is an estimate for operators, not a bill from the provider.

### Testing, security, and tradeoffs

**Q43. How do you test this without API keys?**  
`docker compose --profile test run --rm test` uses fixture guardrails, fixture embeddings, and fixture LLM. Seeded HR facts have expected terms. Isolation tests assert Engineering cannot cite HR documents. Auth tests assert 401 and 403. A faithfulness mean under 0.95 is reported and does not fail CI. A missing score or a case error does.

**Q44. How would you describe the threat model?**  
Spoofing: invalid tokens are 401. Tampering: tenant filters and RBAC, and the policy hash busts stale cache entries. Repudiation: append-only audit, no delete route. Information disclosure: tenant-scoped reads, no prompts in logs or events. Denial of service: rate limits fail closed, 2 second budgets on guardrails and RAG, gateway HPA capped at 2. Elevation: app users cannot hit admin routes, and a requester cannot approve their own export.

**Q45. What would break tenant isolation?**  
Forgetting `tenant_id` on a query, trusting a `tenant_id` from a non-platform body, returning debug chunks for denied documents, caching an answer without role and tenant in the key, or logging chunk text. The cache key includes tenant, role, and policy hash specifically so those mixes cannot leak.

**Q46. Why is the 95% faithfulness target not a failing test?**  
The golden set is a quality signal. Fixture wording and lexical overlap move the number without meaning the safety path crashed. CI fails when the pipeline errors or a score is absent. Operators read `met_target` on the report.

**Q47. What are the sharp edges you would mention yourself?**  
Single Kafka broker and replication factor 1. Single-replica Postgres and Redis on Kubernetes. Lexical citations drop paraphrases. `retention_days` does nothing. Approval does not execute the export. Key rotation requires a restart. Audit is not tamper-evident. Ready does not check the LLM. Metrics are public text. The console is not an operator UI for cost or worker counts.

**Q48. What would you build next, in order?**  
First, RS256 or OIDC so the gateway still never sees a signing key, with JWKS. Second, enforce retention and a real delete story that also clears caches, vectors, and governance. Third, make approval actually perform a constrained export after a second person approves, with its own audit event. Fourth, a real reranker or query rewrite only after the lexical citation weakness shows up in the golden set. Fifth, more than one Kafka replica once the metadata contract is stable. I would not start with Helm or a second vendor SDK.

**Q49. Why FastAPI, Redis, Kafka, and Postgres?**  
FastAPI gives one async Python stack and OpenAPI from the same models as the code. Redis gives atomic-ish counters, TTLs, and small JSON values for limits and caches. Kafka gives a durable ordered log and dead-letter topics for analytics that must not block chat. Postgres gives transactional tenant data and pgvector so documents and identities are not split across databases. Each ADR records the rejected option: Spring Boot, Memcached, RabbitMQ, MongoDB.

**Q50. What should I demo if I only have five minutes?**  
Health and ready. Login as `user@hr.local`. Ask the PTO question and show citations and groundedness 1. Ask a nonsense question and show I-don’t-know without a model hallucination. Send `ignore previous instructions` and show 400. Login as `user@eng.local`, ask the same PTO question, and show no HR document ids. If there is time, `export_directory` returns `approval_id` and the same user cannot approve it.

---

## Numbers worth remembering

| Item | Value |
|------|--------|
| Gateway OpenAPI | 0.11.0 |
| Guardrails and RAG timeout | 2 seconds |
| LLM timeout | 30 seconds |
| Kafka publish timeout | 0.5 seconds |
| Rate limits | tenant 60/min, user 20/min, API key 60/min, burst 2× |
| Retrieval window | 32 candidates per leg, cosine floor 0.3, RRF k=60, top 8, 8000 characters |
| Citation rule | at least half the sentence tokens in one chunk |
| Retry | one retrieve if groundedness &lt; 0.5 and chunks existed |
| Cache write threshold | groundedness ≥ 0.5 |
| Faithfulness target | 0.95, reported, not a CI failure |
| Embedding size | 256 |
| Ingest limit | 256 KiB decoded text |
| Worker retries | 3, then DLQ |
| Gateway HPA | 1 to 2 replicas |
| I-don’t-know string | `I don't know based on the available documents.` |
