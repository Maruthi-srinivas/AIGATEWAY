# Request path

## Version 4 (current)

The gateway is the only public port. Auth issues JWTs. After rate limits, the gateway calls `services/guardrails` for input checks (phrase rules, Perspective or fixture, and Jev). Chat is still a stub LLM. After the stub, the gateway calls guardrails again for a thin output check. Unsafe prompts never reach the stub. Unsafe stub text is replaced with a refusal before persist and SSE tokens.

```mermaid
sequenceDiagram
    participant Client
    participant Gateway
    participant Auth
    participant Redis
    participant Guardrails
    participant Postgres
    Client->>Gateway: GET /v1/health
    Gateway-->>Client: 200 ok
    Client->>Gateway: GET /v1/ready
    Gateway->>Postgres: SELECT 1
    Gateway->>Redis: PING
    Gateway->>Auth: GET /health
    Gateway->>Guardrails: GET /health
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
            Gateway->>Gateway: stub generate
            Gateway->>Guardrails: POST /internal/v1/check-output
            alt output check down
                Gateway-->>Client: 503 guardrails_unavailable
            else output blocks
                Gateway->>Postgres: insert refusal
                Gateway-->>Client: 200 JSON or SSE with assessments
            else allow
                Gateway->>Postgres: insert assistant message
                Gateway-->>Client: 200 JSON or SSE with decisions and assessments
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
