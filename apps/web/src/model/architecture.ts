export type ColumnId = "client" | "public" | "internal" | "data" | "optional" | "later";

export type ArchNode = {
  id: string;
  title: string;
  column: ColumnId;
  ghost: boolean;
  stub: boolean;
  dashed: boolean;
  onRequestPath: boolean;
  plain: string;
  developer: string;
  owns: string;
  doesNotOwn: string;
  container?: string;
  code?: string;
};

export type ArchEdge = {
  from: string;
  to: string;
  style: "solid" | "dashed";
  label: string;
};

export type ChatStep = {
  id: string;
  title: string;
  plain: string;
  developer: string;
  nodeIds: string[];
};

export type SampleMetadata = {
  status: number;
  code: string | null;
  groundedness: number | null;
  citationCount: number | null;
  ruleIds: string[];
  kafkaTopics: string[];
};

export type Scenario = {
  id: string;
  title: string;
  summary: string;
  steps: string[];
  metadata: SampleMetadata;
};

export type FailureCase = {
  id: string;
  title: string;
  status: number;
  code: string;
  plain: string;
  developer: string;
  nodeIds: string[];
};

export const columns: { id: ColumnId; title: string }[] = [
  { id: "client", title: "Caller" },
  { id: "public", title: "Public" },
  { id: "internal", title: "Internal" },
  { id: "data", title: "Data" },
  { id: "optional", title: "Optional live" },
  { id: "later", title: "Later" },
];

export const nodes: ArchNode[] = [
  {
    id: "client",
    title: "Client",
    column: "client",
    ghost: false,
    stub: false,
    dashed: false,
    onRequestPath: true,
    plain: "Anything that calls the gateway: this console, curl, or another app. It never talks to auth, RAG, or the database directly.",
    developer: "Browser calls http://localhost:8000. The console container only serves static files. Tokens stay in sessionStorage.",
    owns: "The caller's own session.",
    doesNotOwn: "Internal tokens, service secrets, or a private route into RAG.",
    code: "apps/web",
  },
  {
    id: "gateway",
    title: "Gateway :8000",
    column: "public",
    ghost: false,
    stub: false,
    dashed: false,
    onRequestPath: true,
    plain: "The only public door. It checks who you are, limits traffic, asks for safety checks, fetches documents when the question needs them, and returns the answer.",
    developer:
      "Orchestrator in apps/gateway. Holds the LLM key only. Does not hold JWT_SECRET, guardrail keys, the embedding key, or user tables. OpenAPI version 0.7.0.",
    owns: "Chat orchestration, rate limits, conversations, citation checks, output secret redaction, SSE, and Kafka publish.",
    doesNotOwn: "Identity tables, guardrail policy storage, document chunks, or generation inside RAG.",
    container: "gateway",
    code: "apps/gateway",
  },
  {
    id: "auth",
    title: "Auth",
    column: "internal",
    ghost: false,
    stub: false,
    dashed: false,
    onRequestPath: true,
    plain: "Knows tenants, users, and API keys. Login and refresh are the only calls that do not already have a token.",
    developer:
      "services/auth issues HS256 access tokens. Introspection uses X-Internal-Token. The gateway proxies /v1/auth, /v1/me, /v1/audit, and /v1/admin.",
    owns: "Tenants, users, API keys, refresh tokens, and the audit log.",
    doesNotOwn: "Chat, documents, or guardrail policy.",
    container: "auth",
    code: "services/auth",
  },
  {
    id: "guardrails",
    title: "Guardrails",
    column: "internal",
    ghost: false,
    stub: false,
    dashed: false,
    onRequestPath: true,
    plain: "Checks the incoming text and, later, the outgoing answer. If this service is down or slower than 2 seconds, chat stops.",
    developer:
      "services/guardrails. Input and output checks. Perspective and TypeSafe Jev are fixture unless switched to live. Timeout is 2s.",
    owns: "Input rules, per-tenant policy, and the thin output check.",
    doesNotOwn: "Retrieval or generation.",
    container: "guardrails",
    code: "services/guardrails",
  },
  {
    id: "rag",
    title: "RAG",
    column: "internal",
    ghost: false,
    stub: false,
    dashed: false,
    onRequestPath: true,
    plain: "Stores documents and finds the passages that may support an answer. It does not write the answer.",
    developer:
      "services/rag. Tenant filter, classification and ACL, vector search plus Postgres full text, reciprocal rank fusion, secret masking, rerank, then an 8000-character budget.",
    owns: "Ingest, chunks, embeddings, hybrid retrieve, ACL, and masking in chunk text.",
    doesNotOwn: "The final answer. Generation stays on the gateway.",
    container: "rag",
    code: "services/rag",
  },
  {
    id: "worker",
    title: "Worker",
    column: "internal",
    ghost: false,
    stub: false,
    dashed: false,
    onRequestPath: false,
    plain: "Reads metadata events after the HTTP response is already decided. It counts them. It does not change chat.",
    developer:
      "apps/worker group aigateway-analytics. Three retries, then a dead-letter topic. Redis key kafka:event:{event_id} skips a redelivery already counted. GET /internal/v1/counts is not on the gateway, so this console does not show counts.",
    owns: "Consuming metadata events and dead-lettering after 3 failures.",
    doesNotOwn: "HTTP chat status or prompt text.",
    container: "worker",
    code: "apps/worker",
  },
  {
    id: "evals",
    title: "Evals",
    column: "internal",
    ghost: false,
    stub: true,
    dashed: false,
    onRequestPath: false,
    plain: "A health check only. The gateway does not call it, and nobody publishes evaluation events yet.",
    developer: "services/evals exposes GET /health. Topic ai.evaluations exists so the worker can count it later. Scoring is a later version.",
    owns: "A liveness response.",
    doesNotOwn: "Faithfulness scores or a place on the chat path.",
    container: "evals",
    code: "services/evals",
  },
  {
    id: "postgres",
    title: "Postgres",
    column: "data",
    ghost: false,
    stub: false,
    dashed: false,
    onRequestPath: true,
    plain: "One database. Each service migrates its own tables. Vectors live next to the document chunks.",
    developer:
      "pgvector/pgvector:pg16. Auth tables, gateway conversations and messages, guardrail_policies, documents, and chunks.embedding vector(256).",
    owns: "Durable identity, chat history, policy, and documents.",
    doesNotOwn: "Rate-limit counters or the Kafka log.",
    container: "postgres",
    code: "alembic in auth, gateway, guardrails, and rag",
  },
  {
    id: "redis",
    title: "Redis",
    column: "data",
    ghost: false,
    stub: false,
    dashed: false,
    onRequestPath: true,
    plain: "Short-lived counters. If Redis is down, chat refuses to run rather than skipping the limit.",
    developer:
      "Token buckets rl:tenant, rl:user, and rl:key, burst 2× the per-minute limit. Session cache of recent messages. Worker lock kafka:event:{event_id}.",
    owns: "Rate limits, a short conversation cache, and the event-id lock.",
    doesNotOwn: "Users or documents.",
    container: "redis",
  },
  {
    id: "kafka",
    title: "Kafka",
    column: "data",
    ghost: false,
    stub: false,
    dashed: false,
    onRequestPath: false,
    plain: "A side channel for metadata. A broker error after the stack is ready does not change the HTTP status of chat.",
    developer:
      "One KRaft broker. Topics ai.requests, ai.responses, ai.security, ai.evaluations, plus a .dlq topic for each. Payloads have ids, status, latency, rule ids, citation count, and groundedness. No prompt, answer, or chunk text. Publish timeout 0.5s.",
    owns: "The metadata event log.",
    doesNotOwn: "The answer returned to the caller.",
    container: "kafka",
  },
  {
    id: "llm",
    title: "Chat model",
    column: "optional",
    ghost: false,
    stub: false,
    dashed: true,
    onRequestPath: false,
    plain: "Compose defaults to a keyless fixture inside the gateway. A live OpenAI-compatible model is used only when that switch is turned on.",
    developer:
      "LLM_MODE=fixture by default. Live calls use OPENAI_API_KEY on the gateway, timeout 30s. Missing key, timeout, or a down provider returns 503 llm_unavailable.",
    owns: "Token generation when live mode is on.",
    doesNotOwn: "Auth, retrieval, or the decision to keep a sentence.",
    code: "apps/gateway LLM client",
  },
  {
    id: "embed",
    title: "Embeddings",
    column: "optional",
    ghost: false,
    stub: false,
    dashed: true,
    onRequestPath: false,
    plain: "Document ingest embeds each chunk. The default is a fixture hash, not a live embedding API.",
    developer: "EMBEDDING_MODE=fixture, 256 dimensions. The embedding key lives on RAG, not the gateway.",
    owns: "Vectors for chunks when live embeddings are on.",
    doesNotOwn: "The chat answer.",
    code: "services/rag",
  },
  {
    id: "perspective",
    title: "Perspective",
    column: "optional",
    ghost: false,
    stub: false,
    dashed: true,
    onRequestPath: false,
    plain: "Optional moderation vendor. Fixture mode does not call it.",
    developer: "GUARDRAILS_API_KEY stays on the guardrails service.",
    owns: "A live moderation score when that mode is on.",
    doesNotOwn: "The gateway process.",
    code: "services/guardrails",
  },
  {
    id: "jev",
    title: "TypeSafe Jev",
    column: "optional",
    ghost: false,
    stub: false,
    dashed: true,
    onRequestPath: false,
    plain: "Optional calibrated scorer for input and the thin output check. Fixture mode stays on the guardrails service.",
    developer: "JEV_API_KEY stays on guardrails. The gateway asks guardrails to run the output check. It does not hold the Jev key.",
    owns: "A live score when Jev is switched on.",
    doesNotOwn: "Retrieval.",
    code: "services/guardrails",
  },
  {
    id: "eval_scoring",
    title: "Eval scoring",
    column: "later",
    ghost: true,
    stub: false,
    dashed: true,
    onRequestPath: false,
    plain: "Not in this slice. Golden-set faithfulness scores are a later version.",
    developer: "Do not publish ai.evaluations from the gateway yet. services/evals is only a health stub.",
    owns: "Nothing in Version 8.",
    doesNotOwn: "The running chat path.",
  },
  {
    id: "prometheus",
    title: "Prometheus",
    column: "later",
    ghost: true,
    stub: false,
    dashed: true,
    onRequestPath: false,
    plain: "Not in this slice. Metrics come later.",
    developer: "No scrape endpoint is part of this console.",
    owns: "Nothing in Version 8.",
    doesNotOwn: "The running chat path.",
  },
  {
    id: "grafana",
    title: "Grafana",
    column: "later",
    ghost: true,
    stub: false,
    dashed: true,
    onRequestPath: false,
    plain: "Not in this slice. Dashboards come later.",
    developer: "This console is a developer explainer, not the enterprise dashboard.",
    owns: "Nothing in Version 8.",
    doesNotOwn: "The running chat path.",
  },
  {
    id: "kubernetes",
    title: "Kubernetes",
    column: "later",
    ghost: true,
    stub: false,
    dashed: true,
    onRequestPath: false,
    plain: "Not in this slice. The prototype runs on Docker Compose.",
    developer: "Do not add cluster manifests in this change.",
    owns: "Nothing in Version 8.",
    doesNotOwn: "The running chat path.",
  },
  {
    id: "multi_provider",
    title: "Multi-provider routing",
    column: "later",
    ghost: true,
    stub: false,
    dashed: true,
    onRequestPath: false,
    plain: "Not in this slice. One OpenAI-compatible adapter is enough for now.",
    developer: "LLM routing across providers is a later version.",
    owns: "Nothing in Version 8.",
    doesNotOwn: "The running chat path.",
  },
];

export const edges: ArchEdge[] = [
  { from: "client", to: "gateway", style: "solid", label: "public /v1 only" },
  { from: "gateway", to: "auth", style: "solid", label: "introspect and audit" },
  { from: "gateway", to: "guardrails", style: "solid", label: "input and output checks" },
  { from: "gateway", to: "rag", style: "solid", label: "retrieve and documents" },
  { from: "gateway", to: "postgres", style: "solid", label: "conversations" },
  { from: "gateway", to: "redis", style: "solid", label: "token bucket" },
  { from: "gateway", to: "kafka", style: "solid", label: "metadata publish" },
  { from: "auth", to: "postgres", style: "solid", label: "identity" },
  { from: "guardrails", to: "postgres", style: "solid", label: "policy" },
  { from: "rag", to: "postgres", style: "solid", label: "documents and vectors" },
  { from: "kafka", to: "worker", style: "solid", label: "consume" },
  { from: "worker", to: "redis", style: "solid", label: "event lock" },
  { from: "gateway", to: "llm", style: "dashed", label: "live chat only" },
  { from: "rag", to: "embed", style: "dashed", label: "live embeddings only" },
  { from: "guardrails", to: "perspective", style: "dashed", label: "live moderation only" },
  { from: "guardrails", to: "jev", style: "dashed", label: "live Jev only" },
];

export const chatSteps: ChatStep[] = [
  {
    id: "post",
    title: "POST /v1/chat",
    plain: "The caller sends one message to the gateway. That is the only generation path.",
    developer: "Body is ChatRequest: message, optional conversation_id, stream, tenant_id, debug. Extra fields are rejected.",
    nodeIds: ["client", "gateway"],
  },
  {
    id: "introspect",
    title: "Introspect",
    plain: "The gateway asks auth whether the bearer token or API key is valid.",
    developer: "POST /internal/v1/introspect with X-Internal-Token. Missing or invalid credentials fail closed with 401.",
    nodeIds: ["gateway", "auth"],
  },
  {
    id: "request_event",
    title: "Publish ai.requests",
    plain: "After auth succeeds, one metadata event is written. It does not contain the message.",
    developer: "ChatEvent carries ids only at this point. Publish timeout is 0.5s. A broker error is logged and does not change the HTTP status.",
    nodeIds: ["gateway", "kafka"],
  },
  {
    id: "role",
    title: "Chat role",
    plain: "Viewers can read history. They cannot start a chat. Other chat roles continue.",
    developer: "require_chat_role. viewer is 403. platform_admin may pass tenant_id. Every other role is pinned to its own tenant.",
    nodeIds: ["gateway"],
  },
  {
    id: "role_denied",
    title: "403 forbidden",
    plain: "The role cannot chat, or the conversation belongs to someone else. No model call.",
    developer: "ai.responses is published. ai.security is not, because this is not a block or redact rule.",
    nodeIds: ["gateway", "auth", "kafka"],
  },
  {
    id: "rate_limit",
    title: "Rate limit",
    plain: "Redis counts this tenant and this user or API key. Under the limit, the request continues.",
    developer: "Token bucket. Burst is 2× the per-minute limit. Keys rl:tenant:{id}, rl:user:{id}, rl:key:{prefix}.",
    nodeIds: ["gateway", "redis"],
  },
  {
    id: "rate_limited",
    title: "429 over quota",
    plain: "Too many calls in the window. Chat stops here.",
    developer: "RateLimitedError. Retry-After and X-RateLimit-* headers. ai.responses follows. No security event.",
    nodeIds: ["gateway", "redis", "kafka"],
  },
  {
    id: "rate_unavailable",
    title: "503 rate limiter down",
    plain: "Redis cannot be reached, so the limit cannot be enforced. Chat refuses.",
    developer: "503 rate_limiter_unavailable. Fail closed. The request does not continue to guardrails.",
    nodeIds: ["gateway", "redis"],
  },
  {
    id: "input_check",
    title: "Input guardrails",
    plain: "The text is checked before any document search or answer. Allow and redact continue. A block stops the chat.",
    developer: "POST /internal/v1/check. Timeout 2s. A block writes an audit record with a SHA-256 of the message, not the message itself, and does not create a conversation.",
    nodeIds: ["gateway", "guardrails"],
  },
  {
    id: "input_blocked",
    title: "400 input blocked",
    plain: "A rule rejected the message. There is no new conversation and no model call.",
    developer: "400 input_blocked. rule ids go on ai.responses and ai.security. groundedness is null.",
    nodeIds: ["gateway", "guardrails", "kafka"],
  },
  {
    id: "chitchat",
    title: "Chitchat",
    plain: "A greeting skips document search. The fixture answer is produced on the gateway.",
    developer: "Classifier treats greetings as chitchat. LLMClient.generate runs without retrieved context. groundedness stays null.",
    nodeIds: ["gateway"],
  },
  {
    id: "retrieve",
    title: "Hybrid retrieve",
    plain: "RAG searches this tenant's documents the caller is allowed to see, then returns passages to the gateway.",
    developer:
      "Order: tenant filter, classification and ACL, vector plus full text (candidate k 32), reciprocal rank fusion k=60, secret masking, token-overlap rerank, dedupe, 8000-character budget, top k 8.",
    nodeIds: ["gateway", "rag", "postgres"],
  },
  {
    id: "retrieve_unavailable",
    title: "503 RAG down",
    plain: "Search did not answer in time. Chat stops instead of answering from the model alone.",
    developer: "503 rag_unavailable when RAG is down or slower than 2s.",
    nodeIds: ["gateway", "rag"],
  },
  {
    id: "no_chunks",
    title: "No supporting passages",
    plain: "Nothing scored high enough. The fixed I-don't-know sentence is stored. The model is not called.",
    developer: "HTTP 200, citations empty, groundedness null. Same sentence used when every generated sentence fails the citation check, except that path sets groundedness to 0.",
    nodeIds: ["gateway", "rag", "postgres"],
  },
  {
    id: "generate",
    title: "Grounded generate",
    plain: "The gateway asks the model to answer from the passages RAG returned. In the default Compose setup that model is a fixture inside the gateway.",
    developer: "LLMClient.generate with the masked chunks. The live provider edge stays dashed unless LLM_MODE is live.",
    nodeIds: ["gateway"],
  },
  {
    id: "llm_unavailable",
    title: "503 model down",
    plain: "The live model is missing, slow, or unreachable. Fixture mode does not take this branch.",
    developer: "503 llm_unavailable. Timeout 30s. Ready does not ping this provider.",
    nodeIds: ["gateway", "llm"],
  },
  {
    id: "citation",
    title: "Citation check",
    plain: "Each sentence must share at least half its words with one returned passage. Sentences that fail are dropped.",
    developer:
      "groundedness is the share of checked sentences that were kept. If none remain, the I-don't-know sentence is returned and groundedness is 0. debug:true adds ranks and drop reasons for security_admin and platform_admin only, with no chunk text.",
    nodeIds: ["gateway"],
  },
  {
    id: "secret_redact",
    title: "Redact secret spans",
    plain: "Spans that look like secrets in the answer are replaced before the caller sees them.",
    developer: "Patterns such as key prefixes and password assignments become [SECRET]. A redaction adds rule id pii and an ai.security event. The span itself is not logged.",
    nodeIds: ["gateway"],
  },
  {
    id: "jev",
    title: "Output check",
    plain: "Guardrails looks at the finished answer. If that check cannot run, chat fails closed.",
    developer: "POST /internal/v1/check-output. Same 2s budget as input. Fixture Jev stays on the guardrails service.",
    nodeIds: ["gateway", "guardrails"],
  },
  {
    id: "guardrails_unavailable",
    title: "503 guardrails down",
    plain: "The safety check did not answer in time, on the way in or on the way out. Chat stops.",
    developer: "503 guardrails_unavailable.",
    nodeIds: ["gateway", "guardrails"],
  },
  {
    id: "store",
    title: "Store the answer",
    plain: "The user message and the assistant message are saved for this tenant.",
    developer: "gateway tables conversations and messages. A short copy also lands in the Redis session cache.",
    nodeIds: ["gateway", "postgres", "redis"],
  },
  {
    id: "http_ok",
    title: "200 JSON or SSE",
    plain: "The caller receives the answer, citation ids, and groundedness. Streaming still finishes the checks first, then replays the text.",
    developer: "SSE events are meta, token, then done. Citations are on done. Chunk text is not in the payload.",
    nodeIds: ["client", "gateway"],
  },
  {
    id: "response_event",
    title: "Publish ai.responses",
    plain: "When the HTTP status is decided, one metadata event records that status.",
    developer: "ChatEvent: status, latency, rule ids, citation count, groundedness. No prompt or answer.",
    nodeIds: ["gateway", "kafka", "worker"],
  },
  {
    id: "security_event",
    title: "Publish ai.security",
    plain: "A second metadata event is added when a rule blocked or redacted something.",
    developer: "Emitted when chat_metrics.rule_ids is non-empty: input block, output block, citation_unverified, or output secret redaction.",
    nodeIds: ["gateway", "kafka", "worker"],
  },
];

const stepIndex = new Map(chatSteps.map((step) => [step.id, step]));

export function stepsFor(ids: string[]): ChatStep[] {
  return ids.map((id) => {
    const step = stepIndex.get(id);
    if (!step) {
      throw new Error(`unknown chat step ${id}`);
    }
    return step;
  });
}

export const scenarios: Scenario[] = [
  {
    id: "grounded",
    title: "Grounded answer",
    summary: "A knowledge question finds passages, the fixture answer is checked sentence by sentence, and citation ids come back.",
    steps: ["post", "introspect", "request_event", "role", "rate_limit", "input_check", "retrieve", "generate", "citation", "jev", "store", "http_ok", "response_event"],
    metadata: {
      status: 200,
      code: null,
      groundedness: 1,
      citationCount: 1,
      ruleIds: [],
      kafkaTopics: ["ai.requests", "ai.responses"],
    },
  },
  {
    id: "chitchat",
    title: "Greeting",
    summary: "A greeting skips retrieval. groundedness stays empty because no sentence was checked against a passage.",
    steps: ["post", "introspect", "request_event", "role", "rate_limit", "input_check", "chitchat", "secret_redact", "jev", "store", "http_ok", "response_event"],
    metadata: {
      status: 200,
      code: null,
      groundedness: null,
      citationCount: 0,
      ruleIds: [],
      kafkaTopics: ["ai.requests", "ai.responses"],
    },
  },
  {
    id: "viewer",
    title: "Viewer cannot chat",
    summary: "A read-only role is rejected after auth. No retrieval and no model call.",
    steps: ["post", "introspect", "request_event", "role_denied"],
    metadata: {
      status: 403,
      code: "forbidden",
      groundedness: null,
      citationCount: null,
      ruleIds: [],
      kafkaTopics: ["ai.requests", "ai.responses"],
    },
  },
  {
    id: "input_block",
    title: "Input blocked",
    summary: "A guardrail rule rejects the message. No conversation row is created.",
    steps: ["post", "introspect", "request_event", "role", "rate_limit", "input_blocked", "security_event"],
    metadata: {
      status: 400,
      code: "input_blocked",
      groundedness: null,
      citationCount: 0,
      ruleIds: ["prompt_injection"],
      kafkaTopics: ["ai.requests", "ai.responses", "ai.security"],
    },
  },
  {
    id: "no_chunks",
    title: "Nothing retrieved",
    summary: "Search returns no passage above the score floor. The model is not called.",
    steps: ["post", "introspect", "request_event", "role", "rate_limit", "input_check", "no_chunks", "jev", "store", "http_ok", "response_event"],
    metadata: {
      status: 200,
      code: null,
      groundedness: null,
      citationCount: 0,
      ruleIds: [],
      kafkaTopics: ["ai.requests", "ai.responses"],
    },
  },
  {
    id: "secret",
    title: "Secret redacted in the answer",
    summary: "A secret-shaped span in the answer is replaced. The sample shows rule ids only, not the span.",
    steps: ["post", "introspect", "request_event", "role", "rate_limit", "input_check", "retrieve", "generate", "secret_redact", "citation", "jev", "store", "http_ok", "response_event", "security_event"],
    metadata: {
      status: 200,
      code: null,
      groundedness: 1,
      citationCount: 1,
      ruleIds: ["pii"],
      kafkaTopics: ["ai.requests", "ai.responses", "ai.security"],
    },
  },
  {
    id: "redis_down",
    title: "Redis down",
    summary: "The rate limiter cannot run, so chat stops before guardrails.",
    steps: ["post", "introspect", "request_event", "role", "rate_unavailable", "response_event"],
    metadata: {
      status: 503,
      code: "rate_limiter_unavailable",
      groundedness: null,
      citationCount: null,
      ruleIds: [],
      kafkaTopics: ["ai.requests", "ai.responses"],
    },
  },
  {
    id: "guardrails_down",
    title: "Guardrails down",
    summary: "The input check does not return within 2 seconds.",
    steps: ["post", "introspect", "request_event", "role", "rate_limit", "guardrails_unavailable", "response_event"],
    metadata: {
      status: 503,
      code: "guardrails_unavailable",
      groundedness: null,
      citationCount: null,
      ruleIds: [],
      kafkaTopics: ["ai.requests", "ai.responses"],
    },
  },
  {
    id: "rag_down",
    title: "RAG down",
    summary: "A knowledge question cannot be searched in time, so the model is not used as a fallback.",
    steps: ["post", "introspect", "request_event", "role", "rate_limit", "input_check", "retrieve_unavailable", "response_event"],
    metadata: {
      status: 503,
      code: "rag_unavailable",
      groundedness: null,
      citationCount: null,
      ruleIds: [],
      kafkaTopics: ["ai.requests", "ai.responses"],
    },
  },
  {
    id: "llm_down",
    title: "Live model down",
    summary: "Only the live provider takes this branch. The keyless fixture does not.",
    steps: ["post", "introspect", "request_event", "role", "rate_limit", "input_check", "retrieve", "llm_unavailable", "response_event"],
    metadata: {
      status: 503,
      code: "llm_unavailable",
      groundedness: null,
      citationCount: null,
      ruleIds: [],
      kafkaTopics: ["ai.requests", "ai.responses"],
    },
  },
];

export const failures: FailureCase[] = [
  {
    id: "unauthenticated",
    title: "Missing or invalid token",
    status: 401,
    code: "unauthenticated",
    plain: "Chat never starts. No request event is published, because auth did not succeed.",
    developer: "require_auth fails closed before ai.requests.",
    nodeIds: ["client", "gateway", "auth"],
  },
  {
    id: "forbidden",
    title: "Wrong role or other tenant",
    status: 403,
    code: "forbidden",
    plain: "A viewer cannot chat. A user cannot read another tenant's rows. platform_admin is the role that may pass tenant_id.",
    developer: "Every query that is not platform_admin filters tenant_id to the caller.",
    nodeIds: ["gateway", "auth"],
  },
  {
    id: "rate_limited",
    title: "Over quota",
    status: 429,
    code: "rate_limited",
    plain: "The token bucket for this tenant and actor is empty.",
    developer: "Headers Retry-After, X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset.",
    nodeIds: ["gateway", "redis"],
  },
  {
    id: "input_blocked",
    title: "Input blocked",
    status: 400,
    code: "input_blocked",
    plain: "A guardrail rule rejected the message. No new conversation.",
    developer: "Audit stores a SHA-256, not the message. ai.security carries rule ids.",
    nodeIds: ["gateway", "guardrails"],
  },
  {
    id: "redis_down",
    title: "Redis down",
    status: 503,
    code: "rate_limiter_unavailable",
    plain: "Chat fails closed when the limiter cannot run.",
    developer: "Does not skip the limit and continue.",
    nodeIds: ["gateway", "redis"],
  },
  {
    id: "guardrails_down",
    title: "Guardrails down or slower than 2s",
    status: 503,
    code: "guardrails_unavailable",
    plain: "Input or output check missed the deadline.",
    developer: "Same code for both stages.",
    nodeIds: ["gateway", "guardrails"],
  },
  {
    id: "rag_down",
    title: "RAG down or slower than 2s",
    status: 503,
    code: "rag_unavailable",
    plain: "Knowledge questions do not fall through to an ungrounded model call.",
    developer: "Chitchat does not call RAG, so this branch is for retrieval.",
    nodeIds: ["gateway", "rag"],
  },
  {
    id: "llm_down",
    title: "Live model down, slow, or unconfigured",
    status: 503,
    code: "llm_unavailable",
    plain: "Fixture mode stays keyless and does not take this path.",
    developer: "Timeout 30s. GET /v1/ready does not ping the model.",
    nodeIds: ["gateway", "llm"],
  },
  {
    id: "ready_kafka",
    title: "Kafka down at ready time",
    status: 503,
    code: "unready",
    plain: "GET /v1/ready is 503 until Postgres, Redis, auth, guardrails, RAG, and Kafka all answer.",
    developer: "Ready does not ping a live LLM. After ready has passed, a later broker error does not change chat status.",
    nodeIds: ["gateway", "kafka"],
  },
  {
    id: "kafka_later",
    title: "Kafka error after ready",
    status: 200,
    code: "publish_dropped",
    plain: "The HTTP status the caller already earned stays the same. The metadata event is dropped and logged.",
    developer: "Publish timeout 0.5s. Chat is best-effort on the broker after ready.",
    nodeIds: ["gateway", "kafka"],
  },
];

export function nodeById(id: string): ArchNode | undefined {
  return nodes.find((node) => node.id === id);
}
