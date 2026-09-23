# Request path

## Version 8 (current)

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
