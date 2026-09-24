# Request path

## Version 10 (current)

The gateway is the only public port. `POST /v1/chat` still returns the Version 7 response. Before retrieve, the gateway looks up a Redis answer for the tenant, role, guardrail policy hash, and normalized query. A miss that comes back with groundedness under 0.5 retries retrieve once with stopwords removed and keeps the better answer. After a knowledge chat, the gateway stores numeric scores and publishes one `ai.evaluations` event. Both are best-effort. Chitchat does not. `POST /v1/evaluate` is a separate call for `security_admin` and `platform_admin`. It runs the checked-in HR golden set through chat and returns a report. A mean faithfulness under 0.95 is recorded and does not fail the suite.

```mermaid
sequenceDiagram
    participant Client
    participant Gateway
    participant RAG
    participant Evals
    participant Kafka
    Client->>Gateway: POST /v1/chat
    Gateway->>Gateway: cache lookup
    alt cache miss and weak grounding
        Gateway->>RAG: retrieve original query
        Gateway->>RAG: one retry without stopwords
    end
    Gateway-->>Client: existing ChatResponse
    Gateway->>Evals: score row, best effort
    Gateway->>Kafka: ai.evaluations metadata
```

## Version 9

The gateway is the only public port. Chat, retrieval, citation checks, and Kafka publishes are unchanged from Version 8. After the HTTP status is chosen, the gateway exports a trace to Tempo and records a Prometheus observation. Both are best-effort. A failure there does not change the status returned to the client. Prometheus scrapes `GET /v1/metrics` and the internal `/metrics` routes. Grafana reads Prometheus and Tempo. `GET /v1/audit?correlation_id=` returns the caller's tenant rows for that id.

```mermaid
sequenceDiagram
    participant Client
    participant Gateway
    participant Tempo
    participant Prometheus
    participant Grafana
    Client->>Gateway: POST /v1/chat
    Gateway->>Tempo: spans, best effort
    Gateway-->>Client: existing HTTP status
    Prometheus->>Gateway: scrape GET /v1/metrics
    Grafana->>Prometheus: latency, blocks, RAG misses
```

## Version 8

The gateway is the only public port. After auth it publishes one `ai.requests` metadata event. Input guardrails, hybrid retrieve, grounded generate, secret redaction, citation verification, and the Jev output check are unchanged from Version 7. When the HTTP status is decided, the gateway publishes one `ai.responses` event and, for a block or redact, one `ai.security` event. Those publishes sit beside the HTTP response. A broker timeout or error is logged and does not change the status returned to the client. The worker consumes `ai.requests`, `ai.responses`, `ai.security`, and `ai.evaluations` in group `aigateway-analytics`. The gateway does not publish evaluation events. Payloads have no prompt, answer, chunk text, or secret span.

```mermaid
sequenceDiagram
    participant Client
    participant Gateway
    participant Kafka
    participant Worker
    Client->>Gateway: POST /v1/chat
    Gateway->>Kafka: ai.requests metadata
    Gateway-->>Client: existing HTTP status
    Gateway->>Kafka: ai.responses and maybe ai.security
    Worker->>Kafka: consume group aigateway-analytics
    Worker->>Worker: Redis event lock then count
```

## Version 7

The gateway is the only public port. After input guardrails, it classifies the latest user message. Greetings skip retrieve. Knowledge questions call `services/rag` with the caller role. RAG runs a tenant filter, classification and acl checks, vector search, Postgres full-text search, reciprocal rank fusion, secret masking, a fixture rerank, dedupe, and an 8000-character budget. The gateway then calls `LLMClient.generate` with the chunks RAG returned. Each answer sentence must share at least half of its tokens with one of those chunks. Unsupported sentences are dropped. If none remain, the fixed I-don't-know string is returned. Secret spans in the answer are replaced with `[SECRET]` before that check. Empty retrieve hits return the same string without calling the LLM, and chitchat skips the sentence check. `groundedness` is the share of checked sentences that were kept. Streaming still generates fully, verifies, runs the Jev output check, then SSE-replays the final text. Citations on JSON and on `done` are the chunks that support a kept sentence. `debug: true` adds ranks and drop reasons for `security_admin` and `platform_admin` only, with no chunk text and no policy-denied rows.

```mermaid
sequenceDiagram
    participant Client
    participant Gateway
    participant Auth
    participant Redis
    participant Guardrails
    participant RAG
    participant LLM
    participant Postgres
    Client->>Gateway: GET /v1/health
    Gateway-->>Client: 200 ok
    Client->>Gateway: GET /v1/ready
    Gateway->>Postgres: SELECT 1
    Gateway->>Redis: PING
    Gateway->>Auth: GET /health
    Gateway->>Guardrails: GET /health
    Gateway->>RAG: GET /health
    Gateway-->>Client: 200 or 503
    Client->>Gateway: POST /v1/auth/login
    Gateway->>Auth: proxy login
    Auth->>Postgres: verify password hash
    Auth-->>Gateway: access plus refresh
    Gateway-->>Client: tokens
    Client->>Gateway: POST /v1/chat plus Bearer or X-API-Key
    Gateway->>Auth: POST /internal/v1/introspect
    Auth-->>Gateway: AuthContext
    Gateway->>Redis: token bucket tenant and actor
    alt over quota
        Gateway-->>Client: 429
    else Redis down
        Gateway-->>Client: 503
    else allowed
        Gateway->>Guardrails: POST /internal/v1/check
        alt guardrails down
            Gateway-->>Client: 503 guardrails_unavailable
        else any rule blocks
            Gateway->>Auth: audit SHA-256 plus decisions
            Gateway-->>Client: 400 input_blocked
        else allow or redact
            Gateway->>Postgres: insert conversation and user message
            alt chitchat
                Gateway->>LLM: generate without context
            else knowledge
                Gateway->>RAG: POST /internal/v1/retrieve
                alt RAG down
                    Gateway-->>Client: 503 rag_unavailable
                else no chunks above min_score
                    Gateway->>Postgres: I-do-not-know assistant
                    Gateway-->>Client: 200 citations empty
                else hits
                    Gateway->>LLM: grounded generate
                    alt LLM down
                        Gateway-->>Client: 503 llm_unavailable
                    else ok
                        Gateway->>Gateway: redact secrets and drop unsupported sentences
                        Gateway->>Guardrails: POST /internal/v1/check-output
                        Gateway->>Postgres: assistant message
                        Gateway-->>Client: 200 JSON or SSE with supporting citations
                    end
                end
            end
        end
    end
```

## Target pipeline (later versions)

```mermaid
sequenceDiagram
    participant Client
    participant Gateway
    participant Guardrails
    participant Retriever
    participant LLM
    participant Kafka
    Client->>Gateway: POST /v1/chat
    Gateway->>Gateway: Auth and rate limit
    Gateway->>Guardrails: Input checks
    Gateway->>Retriever: Hybrid search plus retrieval policy
    Gateway->>LLM: Grounded generate
    Gateway->>Guardrails: Output verification
    Gateway-->>Client: Answer citations confidence
    Gateway->>Kafka: request response security events
```
