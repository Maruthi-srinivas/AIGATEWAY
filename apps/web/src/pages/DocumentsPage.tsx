import { useEffect, useState } from "react";

import { ApiError, api, type DocumentDetail, type DocumentOut } from "../api/client";
import { canGovern, useSession } from "../api/session";
import { Guide } from "../components/Guide";
import { AuthGate } from "./LoginPanel";

const CLASSIFICATIONS = ["", "public", "internal", "confidential", "restricted"] as const;
const ROLES = ["app_user", "viewer", "service_account", "security_admin", "platform_admin"] as const;

export function DocumentsPage() {
  return (
    <AuthGate>
      <Documents />
    </AuthGate>
  );
}

function Documents() {
  const session = useSession();
  const allowed = canGovern(session.me?.role);
  const [tenantId, setTenantId] = useState("");
  const [items, setItems] = useState<DocumentOut[]>([]);
  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [classification, setClassification] = useState("");
  const [acl, setAcl] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const query = { tenant_id: session.me?.role === "platform_admin" ? tenantId.trim() || undefined : undefined };

  async function load() {
    setError(null);
    try {
      const body = await api<{ items: DocumentOut[] }>("/v1/documents", { query });
      setItems(body.items);
    } catch (err) {
      setError(err instanceof ApiError ? `${err.status} ${err.code}: ${err.detail}` : "Could not list documents");
    }
  }

  useEffect(() => {
    if (allowed) {
      void load();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.me?.user_id, allowed]);

  async function ingest(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await api("/v1/documents", {
        method: "POST",
        query,
        body: {
          title,
          text,
          classification: classification || undefined,
          acl,
        },
      });
      setTitle("");
      setText("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? `${err.status} ${err.code}: ${err.detail}` : "Ingest failed");
    }
  }

  async function open(id: string) {
    setError(null);
    try {
      setDetail(await api<DocumentDetail>(`/v1/documents/${id}`, { query }));
    } catch (err) {
      setError(err instanceof ApiError ? `${err.status} ${err.code}: ${err.detail}` : "Could not open document");
    }
  }

  async function remove(id: string) {
    setError(null);
    try {
      await api(`/v1/documents/${id}`, { method: "DELETE", query });
      if (detail?.id === id) {
        setDetail(null);
      }
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? `${err.status} ${err.code}: ${err.detail}` : "Delete failed");
    }
  }

  if (!allowed) {
    return (
      <div className="page">
        <h1>Documents</h1>
        <Guide
          screen="Ingest is limited to security_admin and platform_admin."
          first="Sign in as sec@hr.local or admin@platform.local."
        />
        <p className="error">This role is {session.me?.role}. It cannot ingest or delete documents.</p>
      </div>
    );
  }

  return (
    <div className="page">
      <h1>Documents</h1>
      <Guide
        screen="Empty ACL means every role in the tenant. confidential is security_admin and platform_admin. restricted is platform_admin only. The stored body can keep a secret. The model sees the masked chunk."
        first="Type a title and text, then press Ingest. Only security_admin and platform_admin can do this."
      />
      {session.me?.role === "platform_admin" ? (
        <label>
          tenant_id
          <input value={tenantId} onChange={(event) => setTenantId(event.target.value)} />
        </label>
      ) : null}
      <form onSubmit={(event) => void ingest(event)} className="stack">
        <label>
          Title
          <input value={title} onChange={(event) => setTitle(event.target.value)} />
        </label>
        <label>
          Text
          <textarea value={text} onChange={(event) => setText(event.target.value)} rows={5} />
        </label>
        <label>
          Classification
          <select value={classification} onChange={(event) => setClassification(event.target.value)}>
            {CLASSIFICATIONS.map((item) => (
              <option key={item || "default"} value={item}>
                {item || "default"}
              </option>
            ))}
          </select>
        </label>
        <fieldset>
          <legend>ACL roles (empty means every role in the tenant)</legend>
          {ROLES.map((role) => (
            <label key={role} className="check">
              <input
                type="checkbox"
                checked={acl.includes(role)}
                onChange={(event) =>
                  setAcl((current) => (event.target.checked ? [...current, role] : current.filter((item) => item !== role)))
                }
              />
              {role}
            </label>
          ))}
        </fieldset>
        <button type="submit" disabled={title.trim().length === 0 || text.trim().length === 0}>
          Ingest
        </button>
      </form>
      <button type="button" className="secondary" onClick={() => void load()}>
        Refresh list
      </button>
      {error ? <p className="error">{error}</p> : null}
      <ul className="plain-list">
        {items.map((item) => (
          <li key={item.id}>
            <button type="button" onClick={() => void open(item.id)}>
              {item.title}
              <small>
                {item.classification ?? "unclassified"} · {item.chunk_count} chunks · {item.id}
              </small>
            </button>
            <button type="button" className="secondary" onClick={() => void remove(item.id)}>
              Delete
            </button>
          </li>
        ))}
      </ul>
      {detail ? (
        <section className="panel">
          <h2>{detail.title}</h2>
          <p className="note">Stored body from GET /v1/documents. This is not the masked chunk text the model sees.</p>
          <pre>{detail.body}</pre>
        </section>
      ) : null}
    </div>
  );
}
