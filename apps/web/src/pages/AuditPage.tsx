import { useEffect, useState } from "react";

import { ApiError, api, type AuditRow } from "../api/client";
import { useSession } from "../api/session";
import { Guide } from "../components/Guide";
import { AuthGate } from "./LoginPanel";

export function AuditPage() {
  return (
    <AuthGate>
      <Audit />
    </AuthGate>
  );
}

function Audit() {
  const session = useSession();
  const [tenantId, setTenantId] = useState("");
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setError(null);
    try {
      setRows(
        await api<AuditRow[]>("/v1/audit", {
          query: { tenant_id: session.me?.role === "platform_admin" ? tenantId.trim() || undefined : undefined },
        }),
      );
    } catch (err) {
      setError(err instanceof ApiError ? `${err.status} ${err.code}: ${err.detail}` : "Could not read audit");
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.me?.user_id]);

  return (
    <div className="page">
      <h1>Audit</h1>
      <Guide
        screen="This list is metadata: action, resource, status, and correlation id. Prompts, answers, and secrets are not here. Everyone sees only their tenant, unless you are platform admin and pass a tenant id."
        first="Press Refresh and read the newest action."
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
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>When</th>
              <th>Action</th>
              <th>Resource</th>
              <th>Status</th>
              <th>Success</th>
              <th>Correlation</th>
              <th>Key prefix</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>{row.created_at}</td>
                <td>{row.action}</td>
                <td>{row.resource}</td>
                <td>{row.status_code}</td>
                <td>{row.success ? "yes" : "no"}</td>
                <td>{row.correlation_id ?? "—"}</td>
                <td>{row.actor_key_prefix ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
