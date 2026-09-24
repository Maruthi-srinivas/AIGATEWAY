import { parseSseChunk } from "./sse";
import { clearSession, getSession, saveSession, type Me, type Session } from "./session";

export function gatewayOrigin(): string {
  const configured = import.meta.env.VITE_GATEWAY_ORIGIN;
  return configured && configured.length > 0 ? configured.replace(/\/$/, "") : "http://localhost:8000";
}

export class ApiError extends Error {
  status: number;
  code: string;
  detail: string;
  correlationId: string | null;

  constructor(status: number, code: string, detail: string, correlationId: string | null) {
    super(detail);
    this.status = status;
    this.code = code;
    this.detail = detail;
    this.correlationId = correlationId;
  }
}

export type TokenUser = {
  id: string;
  tenant_id: string;
  email: string;
  role: string;
};

export type ChatResponse = {
  answer: string;
  citations: { document_id: string; chunk_id: string }[];
  confidence: number | null;
  groundedness: number | null;
  trace_id: string | null;
  conversation_id: string | null;
  message_id: string | null;
  guardrail_decisions: { decision: string; rule_id: string; score: number | null; reason: string | null }[];
  assessments: { stage: string; question_id: string; kind: string; score: number | null; choice: string | null }[];
  retrieval_debug: {
    hits: {
      chunk_id: string;
      document_id: string;
      vector_rank: number | null;
      bm25_rank: number | null;
      rrf_score: number;
      rerank_score: number;
      kept: boolean;
      drop_reason: string | null;
    }[];
  } | null;
};

export type ConversationSummary = {
  id: string;
  tenant_id: string;
  user_id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

export type ConversationDetail = ConversationSummary & {
  messages: { id: string; role: string; content: string; created_at: string; user_id: string | null }[];
};

export type DocumentOut = {
  id: string;
  tenant_id: string;
  title: string;
  classification: string | null;
  acl: string[];
  chunk_count: number;
  created_at: string;
  updated_at: string;
};

export type DocumentDetail = DocumentOut & { body: string };

export type GuardrailPolicy = {
  tenant_id: string;
  prompt_injection: boolean;
  jailbreak: boolean;
  moderation: boolean;
  token_limit: boolean;
  pii: boolean;
  pii_action: "redact" | "block";
  max_input_chars: number;
  jev_enabled: boolean;
  jev_injection_threshold: number;
  jev_jailbreak_threshold: number;
  jev_toxicity_threshold: number;
  jev_pii_threshold: number;
  jev_risk_threshold: number;
  jev_output_toxicity_threshold: number;
  jev_output_pii_threshold: number;
};

export type AuditRow = {
  id: string;
  tenant_id: string | null;
  actor_user_id: string | null;
  actor_key_prefix: string | null;
  action: string;
  resource: string;
  success: boolean;
  status_code: number;
  correlation_id: string | null;
  created_at: string;
};

export type ReadyBody = {
  status: string;
  postgres: boolean;
  redis: boolean;
  auth: boolean;
  guardrails: boolean;
  rag: boolean;
  kafka: boolean;
};

type JsonInit = {
  method?: string;
  body?: unknown;
  query?: Record<string, string | undefined>;
  auth?: boolean;
};

function meFromUser(user: TokenUser): Me {
  return {
    user_id: user.id,
    tenant_id: user.tenant_id,
    role: user.role,
    roles: [user.role],
    email: user.email,
    auth_method: "password",
  };
}

function applyAuth(headers: Headers, session: Session) {
  if (session.apiKey) {
    headers.set("X-API-Key", session.apiKey);
  } else if (session.accessToken) {
    headers.set("Authorization", `Bearer ${session.accessToken}`);
  }
}

async function toError(response: Response): Promise<ApiError> {
  let code = "http_error";
  let detail = response.statusText || "request failed";
  let correlationId: string | null = null;
  try {
    const body = (await response.json()) as { code?: string; detail?: string; correlation_id?: string };
    if (body.code) {
      code = body.code;
    }
    if (body.detail) {
      detail = body.detail;
    }
    if (body.correlation_id) {
      correlationId = body.correlation_id;
    }
  } catch {
    detail = response.statusText || "request failed";
  }
  return new ApiError(response.status, code, detail, correlationId);
}

async function refreshTokens(): Promise<boolean> {
  const session = getSession();
  if (!session.refreshToken || session.apiKey) {
    return false;
  }
  const response = await fetch(`${gatewayOrigin()}/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: session.refreshToken }),
  });
  if (!response.ok) {
    clearSession();
    return false;
  }
  const body = (await response.json()) as {
    access_token: string;
    refresh_token: string;
    user: TokenUser;
  };
  saveSession({
    accessToken: body.access_token,
    refreshToken: body.refresh_token,
    apiKey: null,
    me: meFromUser(body.user),
  });
  return true;
}

function withQuery(path: string, query?: Record<string, string | undefined>): string {
  if (!query) {
    return path;
  }
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value) {
      params.set(key, value);
    }
  }
  const text = params.toString();
  return text ? `${path}?${text}` : path;
}

async function raw(path: string, init: JsonInit, allowRefresh: boolean): Promise<Response> {
  const session = getSession();
  const headers = new Headers();
  if (init.auth !== false) {
    applyAuth(headers, session);
  }
  if (init.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  let response = await fetch(`${gatewayOrigin()}${withQuery(path, init.query)}`, {
    method: init.method ?? "GET",
    headers,
    body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
  });
  if (response.status === 401 && allowRefresh && init.auth !== false && !session.apiKey && session.refreshToken) {
    const refreshed = await refreshTokens();
    if (refreshed) {
      response = await raw(path, init, false);
    }
  }
  return response;
}

export async function api<T>(path: string, init: JsonInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await raw(path, init, true);
  } catch {
    throw new ApiError(0, "gateway_unreachable", `Gateway unreachable at ${gatewayOrigin()}`, null);
  }
  if (!response.ok) {
    throw await toError(response);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export async function login(email: string, password: string): Promise<void> {
  const response = await api<{ access_token: string; refresh_token: string; user: TokenUser }>("/v1/auth/login", {
    method: "POST",
    auth: false,
    body: { email, password },
  });
  saveSession({
    accessToken: response.access_token,
    refreshToken: response.refresh_token,
    apiKey: null,
    me: meFromUser(response.user),
  });
  const me = await api<Me>("/v1/me");
  saveSession({ ...getSession(), me });
}

export async function loginWithApiKey(apiKey: string): Promise<void> {
  saveSession({ accessToken: null, refreshToken: null, apiKey, me: null });
  try {
    const me = await api<Me>("/v1/me");
    saveSession({ accessToken: null, refreshToken: null, apiKey, me });
  } catch (error) {
    clearSession();
    throw error;
  }
}

export async function logout(): Promise<void> {
  const session = getSession();
  try {
    if (session.accessToken) {
      await api("/v1/auth/logout", {
        method: "POST",
        body: { refresh_token: session.refreshToken },
      });
    }
  } catch {
    /* local session still clears */
  } finally {
    clearSession();
  }
}

export async function getHealth(): Promise<{ status: string }> {
  return api("/v1/health", { auth: false });
}

export async function getReady(): Promise<{ ok: boolean; body: ReadyBody }> {
  let response: Response;
  try {
    response = await fetch(`${gatewayOrigin()}/v1/ready`);
  } catch {
    throw new ApiError(0, "gateway_unreachable", `Gateway unreachable at ${gatewayOrigin()}`, null);
  }
  const body = (await response.json()) as ReadyBody;
  return { ok: response.ok, body };
}

export type ChatRequestBody = {
  message: string;
  conversation_id?: string;
  stream?: boolean;
  tenant_id?: string;
  debug?: boolean;
};

export async function postChat(body: ChatRequestBody): Promise<ChatResponse> {
  return api<ChatResponse>("/v1/chat", { method: "POST", body });
}

export async function streamChat(
  body: ChatRequestBody,
  onToken: (text: string) => void,
): Promise<ChatResponse> {
  let response: Response;
  try {
    response = await raw("/v1/chat", { method: "POST", body: { ...body, stream: true } }, true);
  } catch {
    throw new ApiError(0, "gateway_unreachable", `Gateway unreachable at ${gatewayOrigin()}`, null);
  }
  if (!response.ok || !response.body) {
    throw await toError(response);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let rest = "";
  let donePayload: ChatResponse | null = null;
  while (true) {
    const chunk = await reader.read();
    if (chunk.done) {
      break;
    }
    const parsed = parseSseChunk(rest, decoder.decode(chunk.value, { stream: true }));
    rest = parsed.rest;
    for (const event of parsed.events) {
      const data = JSON.parse(event.data) as { text?: string };
      if (event.event === "token" && data.text) {
        onToken(data.text);
      }
      if (event.event === "done") {
        donePayload = JSON.parse(event.data) as ChatResponse;
      }
    }
  }
  if (!donePayload) {
    throw new ApiError(response.status, "stream_incomplete", "Stream ended before done", null);
  }
  return donePayload;
}
