# AI Safety Gateway — Structure, Developer Experience, and Where to Improve

This document is for upcoming developers (and coding agents). It answers three questions:

1. How should we structure the repo so the system stays understandable as it grows?
2. How do we make day-to-day development easy?
3. Where is the current PRD / architecture spec thin, and how should we strengthen the product?

It complements `12_VERSION_FEATURE_ROADMAP.md`. The roadmap says *what* to build in which version. This file says *how* to build it so the next person is not lost.

---

## 1. What “good structure” means for this project

The gateway is not a chatbot. It is a **platform**: auth, policy, retrieval, generation, evaluation, and ops. If those concerns mix in one FastAPI file, the project becomes hard to test, hard to hire into, and hard to demo.

Structure here means:

- A new engineer can find the code for a request stage in one directory
- A coding agent can implement one service without rewriting another
- Safety rules are data/policy, not scattered `if` statements
- Local run is one command; CI is the same command in a container
- Contracts (APIs, events, interfaces) are documented and versioned before implementations

The SAS already points in this direction. We should treat it as a **directory and boundary spec**, then add the engineering practices it does not spell out.

---

## 2. Recommended repository layout

Keep the SAS layout, and make it slightly more explicit so people do not invent a second pattern.

```text
AIGATEWAY/
├── apps/
│   ├── gateway/                 # HTTP edge: auth, rate limit, routing, streaming
│   └── worker/                  # Kafka consumers, ingest, eval jobs, retries
├── services/
│   ├── rag/                     # retrieve, rerank, context assembly
│   ├── guardrails/              # input / retrieval / output checks
│   └── evals/                   # golden sets, scorers, quality gates
├── packages/                    # shared libraries (not services)
│   ├── contracts/               # OpenAPI, JSON Schema, event schemas
│   ├── config/                  # typed settings, env loading
│   ├── telemetry/               # logging, tracing, metrics helpers
│   └── testing/                 # fixtures, fake LLM, fake retriever
├── infrastructure/
│   ├── docker/                  # compose files, Dockerfiles, local overlays
│   └── k8s/                     # later: Helm / manifests
├── docs/
│   ├── adr/                     # architecture decision records
│   ├── runbooks/
│   └── diagrams/
├── tests/
│   ├── unit/
│   ├── contract/
│   ├── integration/             # docker-compose based
│   └── eval/                    # golden dataset runs
├── .github/workflows/
├── Makefile                     # or justfile: make up / test / eval / lint
├── README.md
├── AGENTS.md                    # rules for coding agents
└── 12_VERSION_FEATURE_ROADMAP.md
```

### Why `packages/` is worth adding

The SAS lists apps and services but not shared code. Without a `packages` layer, people will copy JWT parsing, correlation IDs, and Pydantic models into every service. Shared **libraries** are fine. Shared **god modules** that import RAG from the gateway are not.

Rule: `packages/*` must not import `apps/*` or `services/*`. Dependencies point inward to contracts, not sideways across services.

---

## 3. Hard service boundaries (do not blur these)

| Component | Owns | Must not own |
|-----------|------|----------------|
| `apps/gateway` | HTTP, authn/authz context, rate limit, orchestration, streaming | Chunking, embeddings, prompt-injection model weights |
| `services/guardrails` | Allow / redact / block decisions | Talking to the LLM provider for generation |
| `services/rag` | Search, rerank, context window | User JWT validation |
| `services/evals` | Scoring and golden datasets | Serving production chat |
| `apps/worker` | Async side effects | Synchronous user-facing HTTP |

Gateway **orchestrates** the pipeline. It should call interfaces, not reimplement RAG.

This matches the SAS instruction: generate interfaces before implementations and preserve service boundaries.

---

## 4. Make the system easy to understand

### 4.1 One request story, kept current

Put a single sequence diagram in `docs/diagrams/request-path.md` (Mermaid is enough):

```text
Client → Gateway (auth, rate limit)
      → Input Guardrails
      → Retriever + Retrieval Guardrails
      → LLM
      → Output Guardrails
      → Response
      → Kafka (request/response/security/eval)
```

Every version that changes the path must update this diagram in the same PR.

### 4.2 Contracts first

Before coding a version, freeze:

- OpenAPI for `/v1/chat`, `/v1/evaluate`, `/v1/health`, `/v1/metrics`
- Event schemas for `ai.requests`, `ai.responses`, `ai.security`, `ai.evaluations`
- Guardrail result schema: `decision`, `rule_id`, `score`, `reason`
- Chat response envelope: `answer`, `citations`, `confidence`, `trace_id`

Store these in `packages/contracts`. Implementations implement the contract; they do not invent parallel JSON.

### 4.3 Architecture Decision Records

The SAS already chose FastAPI, Redis, Kafka, PostgreSQL. Write each as a short ADR:

- Context
- Decision
- Consequences
- Alternatives rejected

Add new ADRs when we pick: vector store (pgvector vs Qdrant), embedding model, reranker, LangGraph vs plain pipeline, SSE vs websocket.

ADRs stop the next developer from relitigating solved questions in Slack.

### 4.4 README that matches reality

Root README should only contain:

1. What the product is (two paragraphs)
2. Architecture picture
3. `make up` / `make test`
4. How to send the first authenticated chat request
5. Where to go next (`docs/`, roadmap, ADRs)

Deep pages live under `docs/`. Do not dump the entire SAS into the README.

### 4.5 Code that explains itself

- Name stages after the pipeline: `input_guardrails`, `retrieve`, `generate`, `verify_output`
- One module per guardrail rule, registered in a catalog (plugin list)
- Correlation ID, tenant ID, user ID on every log
- No silent defaults that change safety (fail closed on missing policy)

### 4.6 A glossary

Short `docs/GLOSSARY.md`: groundedness, faithfulness, context recall, tenant, citation, MCP, golden dataset, semantic cache. Incoming AI engineers and backend engineers do not share vocabulary.

---

## 5. Make development easy for the next person

### 5.1 Docker-first, with Compose profiles

SAS rule: no local Postgres, Redis, or Kafka installs.

Use profiles so Version 1 does not force Kafka on everyone:

```text
make up              # gateway + postgres + redis
make up-full         # + kafka + prometheus + grafana
make test            # unit + contract
make test-integration
make eval            # golden dataset
```

One `.env.example`, never a personal `.env` in git.

### 5.2 Fake providers for the inner loop

LLM calls and embedding calls are slow, costly, and flaky. Ship:

- `FakeLLMClient` (deterministic answers + citations)
- `FakeRetriever`
- Recorded HTTP fixtures for real-provider tests (opt-in)

Default `make test` must pass **offline**. Real-provider tests run in CI nightly or behind a flag.

### 5.3 Seed data

A Compose `seed` job should load:

- Two tenants (HR vs Engineering)
- Users with different roles
- A tiny document corpus with one **forbidden** document
- A golden eval subset of ~20 questions

This is how people demo “zero unauthorized document exposure” without building a UI first.

### 5.4 Testing pyramid that matches a safety product

| Layer | What it proves | When it runs |
|-------|----------------|--------------|
| Unit | One guardrail, one ranker, one RBAC filter | Every commit |
| Contract | OpenAPI and event schemas | Every commit |
| Integration | Compose path: auth → chat → audit | PR |
| Eval | Faithfulness / recall on golden set | PR quality gate from Version 10 |
| Threat | Tenant isolation, injection fixtures, rate-limit DoS | PR for safety-critical paths |

Safety tests are not optional extras. A retrieval bug is a data leak.

### 5.5 Tooling that keeps PRs small

- Ruff / formatter / mypy (or equivalent) in CI
- Pre-commit optional, CI mandatory
- Conventional commits or a short prefix: `feat(gateway)`, `fix(rag)`, `docs`
- Version label in the changelog matching the 12-version roadmap

### 5.6 Agent / human onboarding files

Add `AGENTS.md` (and optionally `.cursor/rules`) with:

- Generate interfaces before implementations
- Do not put RAG code in the gateway
- Fail closed on auth and retrieval filters
- Update docs and OpenAPI in the same change
- Never commit secrets

The SAS “Cursor AI Kickstart Guide” belongs here, pointed at the 12 versions, not as a one-shot “generate everything.”

### 5.7 Observability from Version 3, not only Version 9

Even before Grafana, every service should log JSON and accept a correlation ID. Version 9 then *visualizes* what already exists. If we wait until Version 9 to add IDs, we will retrofit every handler.

---

## 6. Where the current spec is thin (and how to make the project better)

The PRD and SAS are a strong **product outline**. They are not yet an implementation spec. If we generate code only from those PDFs, we will get repeated health-check boilerplate and underspecified safety logic. Tighten the following.

### 6.1 Replace chapter boilerplate with real design

Almost every SAS page repeats the same acceptance criteria. Keep those as **global non-functional requirements**, then write per-chapter:

- Inputs / outputs
- Failure modes
- Data owned
- Tests that prove it

Otherwise agents regenerate the same skeleton 31 times.

### 6.2 Specify the data model

SAS lists tables: users, conversations, evaluations, documents, audit logs. Add:

- Primary keys, tenant columns, indexes
- Chunk schema (embedding, ACL, classification, source URI)
- Policy tables (guardrail flags per tenant)
- Retention and PII handling for logs
- What is *not* stored (raw prompts with secrets, if that is the policy)

A safety gateway without a careful audit schema cannot prove “full audit trail.”

### 6.3 Specify error and policy behavior

Today we know checks exist (injection, jailbreak, PII). We do not know:

- Block vs redact vs warn
- Who can override
- Whether streaming can emit tokens before output verification completes (usually it should not, or it must be able to retract)
- Confidence threshold to refuse

Encode this as a policy document and as JSON config, not as buried constants.

### 6.4 Make RAG quality operational, not magical

“Hybrid search + rerank + 95% faithfulness” needs:

- A real golden dataset (HR / eng / legal / support questions)
- A definition of faithfulness we can compute
- A baseline (vector-only) so hybrid search has a comparison
- Evaluation in CI so quality cannot silently regress

Without that, the eval service is a folder name.

### 6.5 Self-healing needs a budget

Retry with more context, rewrite query, change reranker, escalate — all increase latency and cost. Cap them:

- Max extra retrieval rounds
- Max added tokens
- Max extra milliseconds toward the P95 < 2s goal
- Escalation destination (queue, Slack, ticket)

Otherwise self-healing will miss the latency SLO.

### 6.6 Semantic cache is a safety feature, not only a speed feature

Cache keys must include tenant, role, policy version, and model. Caching answers across tenants is an information-disclosure bug. Document this in the threat model before Redis caching ships (Version 10).

### 6.7 Multi-tenancy should be designed in Version 2, even if org UI is Version 11

If `tenant_id` is not on every row and every cache key from the start, Version 11 becomes a rewrite. Isolation is a data-model concern, not a dashboard concern.

### 6.8 Provider-agnostic routing needs a real adapter layer

“Support multiple LLM providers” fails if OpenAI types leak into RAG. Keep:

- `LLMClient.generate(messages, tools, stream)`
- Provider-specific code only under `adapters/`
- Routing policy outside adapters (cost, latency, capability tags)

### 6.9 MCP and human approval are high-risk

Tools can send email, query DBs, or change tickets. Better than a generic “MCP integration”:

- Allowlist of tools per tenant
- Argument schema validation
- Side-effect tools require approval
- Full tool-call audit (name, args, decision, approver)

This is where the project looks like a platform instead of a wrapper.

### 6.10 Threat model should drive tests, not slides

SAS lists STRIDE. Pair each item with an automated test or control:

| Threat | Control | Proof |
|--------|---------|--------|
| Spoofing | JWT/API key, key rotation | Auth tests |
| Tampering | Signed/versioned policies | Policy hash on audit log |
| Repudiation | Immutable audit logs | Append-only or WORM-style table |
| Information disclosure | Tenant + RBAC retrieval filters | Cross-tenant retrieval tests |
| DoS | Rate limit, timeouts, body limits | Load test / 429 tests |
| Privilege escalation | RBAC, no admin in user tokens | Role tests |

### 6.11 Product surfaces the PRD under-describes

Worth adding when we want this to feel complete:

- Admin API or thin UI for API keys, policies, and audit search (security teams will not read Kafka)
- Developer portal / OpenAPI “Try it” against local Compose
- Budget alerts (cost per tenant)
- Prompt/version registry so RAG prompts are not edited only in code
- Document ingestion connectors (S3, Confluence, Git) — even one connector beats a SQL insert demo
- Local model option (Ollama) so development works without cloud keys
- Privacy mode: strip PII before the prompt leaves the VPC
- Feature flags so Version 11 routing can ship dark

### 6.12 Interview and hiring value

The PRD calls this out: the project should demonstrate backend engineering, distributed systems, AI safety, RAG, and observability. Make that visible:

- `docs/TRADEOFFS.md` — why Kafka, why not a bigger monolith
- Runbooks for “LLM provider is down”, “faithfulness dropped”, “Kafka lag”
- A 15-minute demo script: inject a jailbreak, leak attempt, then a grounded HR question

That helps future developers *and* anyone presenting the system.

---

## 7. Working agreements (short enough to remember)

1. **Interfaces before implementations.**
2. **Fail closed** on auth, tenant filters, and missing policy.
3. **Contracts live in `packages/contracts`**, not copied into services.
4. **One version at a time** from the 12-version roadmap; do not skip isolation to “get RAG working.”
5. **Docs, OpenAPI, and tests ship with the feature.**
6. **Offline tests are the default**; paid LLM calls are opt-in.
7. **Every log has a correlation ID.**
8. **No secrets in git, images, or client-side config.**
9. **Gateway orchestrates; services decide.**
10. **If a change can leak a document, add a test that would have caught it.**

---

## 8. Suggested first week (before heavy feature work)

1. Create the repo skeleton (Version 1) exactly as in section 2.
2. Write `packages/contracts` stubs for chat + health.
3. Write ADR-001 to ADR-004 (stack choices).
4. Draw the request-path diagram.
5. Add `AGENTS.md`, `.env.example`, and `make up`.
6. Only then start Version 2 (auth).

Skipping this week is how the project becomes a single FastAPI app with a `utils.py` that nobody wants to touch.

---

## 9. Success for this document

Upcoming developers are unblocked if they can answer:

- Where does my change go?
- What is in / out of this version?
- How do I run it without installing databases?
- How do I prove I did not leak another tenant’s documents?
- What is frozen (contracts, ADRs) vs what is still open?

If those answers live in the repo, not in someone’s head, the project is structured enough to grow.
