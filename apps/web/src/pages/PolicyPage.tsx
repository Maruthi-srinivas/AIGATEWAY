import { useEffect, useState } from "react";

import { ApiError, api, type GuardrailPolicy } from "../api/client";
import { canGovern, useSession } from "../api/session";
import { Guide } from "../components/Guide";
import { AuthGate } from "./LoginPanel";

const FLAGS = [
  ["prompt_injection", "Prompt injection"],
  ["jailbreak", "Jailbreak"],
  ["moderation", "Moderation"],
  ["token_limit", "Token limit"],
  ["pii", "PII"],
  ["jev_enabled", "Jev"],
] as const;

const THRESHOLDS = [
  ["jev_injection_threshold", "Injection"],
  ["jev_jailbreak_threshold", "Jailbreak"],
  ["jev_toxicity_threshold", "Toxicity"],
  ["jev_pii_threshold", "PII"],
  ["jev_risk_threshold", "Risk"],
  ["jev_output_toxicity_threshold", "Output toxicity"],
  ["jev_output_pii_threshold", "Output PII"],
] as const;

export function PolicyPage() {
  return (
    <AuthGate>
      <Policy />
    </AuthGate>
  );
}

function Policy() {
  const session = useSession();
  const allowed = canGovern(session.me?.role);
  const [tenantId, setTenantId] = useState("");
  const [policy, setPolicy] = useState<GuardrailPolicy | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const query = { tenant_id: session.me?.role === "platform_admin" ? tenantId.trim() || undefined : undefined };

  async function load() {
    setError(null);
    setSaved(false);
    try {
      setPolicy(await api<GuardrailPolicy>("/v1/guardrails/policy", { query }));
    } catch (err) {
      setError(err instanceof ApiError ? `${err.status} ${err.code}: ${err.detail}` : "Could not load policy");
    }
  }

  useEffect(() => {
    if (allowed) {
      void load();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allowed, session.me?.user_id]);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!policy) {
      return;
    }
    setError(null);
    setSaved(false);
    const { tenant_id, ...body } = policy;
    void tenant_id;
    try {
      setPolicy(await api<GuardrailPolicy>("/v1/guardrails/policy", { method: "PATCH", query, body }));
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiError ? `${err.status} ${err.code}: ${err.detail}` : "Could not save policy");
    }
  }

  if (!allowed) {
    return (
      <div className="page">
        <h1>Guardrail policy</h1>
        <Guide
          screen="Policy edits require security_admin or platform_admin."
          first="Sign in as sec@hr.local or the platform admin."
        />
        <p className="error">This role is {session.me?.role} and cannot change policy.</p>
      </div>
    );
  }

  return (
    <div className="page">
      <h1>Guardrail policy</h1>
      <Guide
        screen="These switches live on the guardrails service, one set per tenant. The gateway does not store this table. Saving sends a PATCH that only those two roles may call."
        first="Change a switch, then press Save policy."
      />
      {session.me?.role === "platform_admin" ? (
        <div className="row">
          <label>
            tenant_id
            <input value={tenantId} onChange={(event) => setTenantId(event.target.value)} />
          </label>
          <button type="button" onClick={() => void load()}>
            Load
          </button>
        </div>
      ) : null}
      {error ? <p className="error">{error}</p> : null}
      {policy ? (
        <form onSubmit={(event) => void save(event)} className="stack">
          <p className="note">Tenant {policy.tenant_id}</p>
          {FLAGS.map(([key, label]) => (
            <label key={key} className="check">
              <input
                type="checkbox"
                checked={policy[key]}
                onChange={(event) => setPolicy({ ...policy, [key]: event.target.checked })}
              />
              {label}
            </label>
          ))}
          <label>
            PII action
            <select
              value={policy.pii_action}
              onChange={(event) => setPolicy({ ...policy, pii_action: event.target.value as "redact" | "block" })}
            >
              <option value="redact">redact</option>
              <option value="block">block</option>
            </select>
          </label>
          <label>
            Max input characters
            <input
              type="number"
              min={1}
              max={8000}
              value={policy.max_input_chars}
              onChange={(event) => setPolicy({ ...policy, max_input_chars: Number(event.target.value) })}
            />
          </label>
          <fieldset>
            <legend>Jev thresholds</legend>
            {THRESHOLDS.map(([key, label]) => (
              <label key={key}>
                {label}
                <input
                  type="number"
                  min={0}
                  max={1}
                  step={0.05}
                  value={policy[key]}
                  onChange={(event) => setPolicy({ ...policy, [key]: Number(event.target.value) })}
                />
              </label>
            ))}
          </fieldset>
          <button type="submit">Save policy</button>
          {saved ? <p className="note">Saved.</p> : null}
        </form>
      ) : null}
    </div>
  );
}
