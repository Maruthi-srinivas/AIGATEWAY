import { useEffect, useState } from "react";

import { ApiError, api, type ConversationDetail, type ConversationSummary } from "../api/client";
import { useSession } from "../api/session";
import { Guide } from "../components/Guide";
import { AuthGate } from "./LoginPanel";

export function ConversationsPage() {
  return (
    <AuthGate>
      <Conversations />
    </AuthGate>
  );
}

function Conversations() {
  const session = useSession();
  const [tenantId, setTenantId] = useState("");
  const [items, setItems] = useState<ConversationSummary[]>([]);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setError(null);
    try {
      const body = await api<{ items: ConversationSummary[] }>("/v1/conversations", {
        query: { tenant_id: session.me?.role === "platform_admin" ? tenantId.trim() || undefined : undefined },
      });
      setItems(body.items);
    } catch (err) {
      setError(err instanceof ApiError ? `${err.status} ${err.code}: ${err.detail}` : "Could not list conversations");
    }
  }

  useEffect(() => {
    void load();
    // Reload when the signed-in user changes. tenantId is applied by the button.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.me?.user_id]);

  async function open(id: string) {
    setError(null);
    try {
      setDetail(await api<ConversationDetail>(`/v1/conversations/${id}`));
    } catch (err) {
      setError(err instanceof ApiError ? `${err.status} ${err.code}: ${err.detail}` : "Could not open conversation");
    }
  }

  return (
    <div className="page">
      <h1>Conversations</h1>
      <Guide
        screen="History is limited to your tenant. A platform admin may type another tenant id. The messages are the ones the API returned to you, not hidden chunk text."
        first="Press Refresh, then open a conversation."
      />
      {session.me?.role === "platform_admin" ? (
        <label>
          tenant_id
          <input value={tenantId} onChange={(event) => setTenantId(event.target.value)} />
        </label>
      ) : null}
      <button type="button" onClick={() => void load()}>
        Refresh
      </button>
      {error ? <p className="error">{error}</p> : null}
      <div className="workspace">
        <ul className="plain-list">
          {items.length === 0 ? <li>No conversations yet.</li> : null}
          {items.map((item) => (
            <li key={item.id}>
              <button type="button" onClick={() => void open(item.id)}>
                {item.title || item.id}
                <small>{item.id}</small>
              </button>
            </li>
          ))}
        </ul>
        <section className="panel">
          {detail ? (
            <>
              <h2>{detail.title}</h2>
              {detail.messages.map((message) => (
                <article key={message.id}>
                  <strong>{message.role}</strong>
                  <p>{message.content}</p>
                </article>
              ))}
            </>
          ) : (
            <p className="note">Open a conversation to read its messages.</p>
          )}
        </section>
      </div>
    </div>
  );
}
