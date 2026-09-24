import { useState } from "react";

import {
  ApiError,
  postChat,
  streamChat,
  type ChatResponse,
} from "../api/client";
import { canChat, canGovern, useSession } from "../api/session";
import { Guide, toneForHttp } from "../components/Guide";
import { inferChat } from "../model/infer";
import { AuthGate } from "./LoginPanel";

function ruleIds(response: ChatResponse): string[] {
  return response.guardrail_decisions.filter((item) => item.decision === "block" || item.decision === "redact").map((item) => item.rule_id);
}

export function ChatPage() {
  return (
    <AuthGate>
      <ChatConsole />
    </AuthGate>
  );
}

function ChatConsole() {
  const session = useSession();
  const role = session.me?.role;
  const allowed = canChat(role);
  const [message, setMessage] = useState("How many paid time off days per year does Acme HR give?");
  const [stream, setStream] = useState(false);
  const [debug, setDebug] = useState(false);
  const [tenantId, setTenantId] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [liveText, setLiveText] = useState("");
  const [result, setResult] = useState<ChatResponse | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!allowed) {
      return;
    }
    setPending(true);
    setError(null);
    setResult(null);
    setLiveText("");
    const body = {
      message,
      stream,
      conversation_id: conversationId ?? undefined,
      tenant_id: role === "platform_admin" && tenantId.trim() ? tenantId.trim() : undefined,
      debug: canGovern(role) && debug ? true : undefined,
    };
    try {
      const response = stream
        ? await streamChat(body, (text) => setLiveText((current) => current + text))
        : await postChat(body);
      setResult(response);
      setLiveText(response.answer);
      if (response.conversation_id) {
        setConversationId(response.conversation_id);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError(0, "client_error", "Chat failed", null));
    } finally {
      setPending(false);
    }
  }

  const inference = error
    ? inferChat({ status: error.status, code: error.code })
    : result
      ? inferChat({
          status: 200,
          answer: result.answer,
          groundedness: result.groundedness,
          citationCount: result.citations.length,
          ruleIds: ruleIds(result),
        })
      : null;

  return (
    <div className="page">
      <h1>Chat</h1>
      <Guide
        screen="This sends one message to the public gateway. Viewers can read history and cannot chat. A green result means the call finished. Red means the role or a rule stopped it. Orange means a dependency did not answer."
        first={allowed ? "Press Send. Use Stream if you want the answer replayed as tokens after the checks finish." : "This role cannot chat. Open Conversations, or sign in as an app user."}
      />
      {allowed ? null : (
        <p className="error">This role can read conversations and cannot call POST /v1/chat. Expect 403 if you bypass the form.</p>
      )}
      <form onSubmit={(event) => void onSubmit(event)} className="stack">
        <label>
          Message
          <span className="hint">Signed in as {session.me?.email ?? role}. Role {role}. Calls only POST /v1/chat.</span>
          <textarea value={message} onChange={(event) => setMessage(event.target.value)} rows={4} />
        </label>
        <label className="check">
          <input type="checkbox" checked={stream} onChange={(event) => setStream(event.target.checked)} />
          Stream (SSE). The server still finishes checks, then replays tokens.
        </label>
        {canGovern(role) ? (
          <label className="check">
            <input type="checkbox" checked={debug} onChange={(event) => setDebug(event.target.checked)} />
            debug: true — ranks and drop reasons, no chunk text
          </label>
        ) : null}
        {role === "platform_admin" ? (
          <label>
            tenant_id (optional, other tenant)
            <input value={tenantId} onChange={(event) => setTenantId(event.target.value)} placeholder="uuid" />
          </label>
        ) : null}
        <div className="row">
          <button type="submit" disabled={pending || !allowed || message.trim().length === 0}>
            Send
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() => {
              setConversationId(null);
              setResult(null);
              setLiveText("");
              setError(null);
            }}
          >
            New conversation
          </button>
        </div>
        {conversationId ? <p className="note">Continuing conversation {conversationId}</p> : null}
      </form>
      {error ? (
        <p className={`banner tone-${toneForHttp(error.status, error.code)}`}>
          {error.status} {error.code}: {error.detail}
          {error.correlationId ? ` · ${error.correlationId}` : ""}
        </p>
      ) : null}
      {liveText || result ? (
        <section className="panel">
          <h2>Answer</h2>
          <p className="answer">{liveText || result?.answer}</p>
          <p className="note">Chunk text is not in this response. Citation ids are the only document pointers returned.</p>
          {result ? (
            <>
              <dl>
                <dt>Groundedness</dt>
                <dd>{result.groundedness === null ? "null" : result.groundedness}</dd>
                <dt>Confidence</dt>
                <dd>{result.confidence === null ? "null" : result.confidence}</dd>
                <dt>Trace</dt>
                <dd>{result.trace_id ?? "—"}</dd>
              </dl>
              <h3>Citations</h3>
              {result.citations.length === 0 ? <p>None</p> : (
                <ul>
                  {result.citations.map((item) => (
                    <li key={item.chunk_id}>
                      document {item.document_id} · chunk {item.chunk_id}
                    </li>
                  ))}
                </ul>
              )}
              <h3>Guardrail decisions</h3>
              {result.guardrail_decisions.length === 0 ? <p>None</p> : (
                <ul>
                  {result.guardrail_decisions.map((item) => (
                    <li key={`${item.rule_id}-${item.decision}`}>
                      {item.rule_id}: {item.decision}
                      {item.score === null ? "" : ` (${item.score})`}
                    </li>
                  ))}
                </ul>
              )}
              {result.retrieval_debug ? (
                <>
                  <h3>Retrieval debug</h3>
                  <ul>
                    {result.retrieval_debug.hits.map((hit) => (
                      <li key={hit.chunk_id}>
                        {hit.kept ? "kept" : "dropped"}
                        {hit.drop_reason ? ` · ${hit.drop_reason}` : ""} · vector {hit.vector_rank ?? "—"} · bm25{" "}
                        {hit.bm25_rank ?? "—"} · chunk {hit.chunk_id}
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}
            </>
          ) : null}
        </section>
      ) : null}
      {inference ? <p className="note">{inference.summary}</p> : null}
    </div>
  );
}
