# Request path

## Version 5 (current)

The gateway is the only public port. After input guardrails, it classifies the latest user message. Greetings skip retrieve. Knowledge questions call `services/rag` with a tenant filter, then `LLMClient.generate` with a grounded prompt. Empty retrieve hits return a fixed I-don't-know string without calling the LLM. Streaming still generates fully, runs the Jev output check, then SSE-replays tokens. Citations on JSON and on `done` are every chunk inserted into the prompt.

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
                        Gateway->>Guardrails: POST /internal/v1/check-output
                        Gateway->>Postgres: assistant message
                        Gateway-->>Client: 200 JSON or SSE with citations
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
    Gateway->>Kafka: request response security eval events
```
