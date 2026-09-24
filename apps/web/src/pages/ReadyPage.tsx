import { useEffect, useState } from "react";

import { ApiError, getHealth, getReady, type ReadyBody } from "../api/client";
import { Guide } from "../components/Guide";

const CHECKS: { key: keyof ReadyBody; label: string; note: string }[] = [
  { key: "postgres", label: "Postgres", note: "conversations, identity, policy, vectors" },
  { key: "redis", label: "Redis", note: "token bucket and session cache" },
  { key: "auth", label: "Auth", note: "identity service health" },
  { key: "guardrails", label: "Guardrails", note: "input and output checks" },
  { key: "rag", label: "RAG", note: "retrieve and documents" },
  { key: "kafka", label: "Kafka", note: "broker reachable at ready time" },
];

export function ReadyPage() {
  const [health, setHealth] = useState<string>("…");
  const [ready, setReady] = useState<ReadyBody | null>(null);
  const [readyOk, setReadyOk] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setError(null);
    try {
      const healthBody = await getHealth();
      setHealth(healthBody.status);
      const readyResult = await getReady();
      setReady(readyResult.body);
      setReadyOk(readyResult.ok);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Ready check failed");
    }
  }

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 5000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <div className="page">
      <h1>Health and ready</h1>
      <Guide
        screen="Health means the gateway process is up. Ready means Postgres, Redis, auth, guardrails, RAG, and Kafka answered. Ready does not ping a live model. Green is up. Orange is down. Worker counts stay off this page because that route is internal."
        first="Press Check now, or wait. This page refreshes every five seconds."
      />
      <button type="button" onClick={() => void load()}>
        Check now
      </button>
      {error ? <p className="error">{error}</p> : null}
      <p>
        GET /v1/health: <strong>{health}</strong>
      </p>
      <p>
        GET /v1/ready: <strong>{readyOk === null ? "…" : readyOk ? "200" : "503"}</strong>
        {ready ? ` · ${ready.status}` : ""}
      </p>
      <ul className="check-list">
        {CHECKS.map((check) => {
          const up = ready ? Boolean(ready[check.key]) : null;
          return (
            <li key={check.key} className={up === null ? "" : up ? "up" : "down"}>
              <strong>{check.label}</strong>
              <span>{up === null ? "…" : up ? "up" : "down"}</span>
              <small>{check.note}</small>
            </li>
          );
        })}
      </ul>
      <p className="note">Worker counts stay off this page. That route is internal and is not on the gateway.</p>
    </div>
  );
}
