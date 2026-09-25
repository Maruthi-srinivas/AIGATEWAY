# Failure

Compose is the default. These notes also apply to the Kubernetes manifests.

| Symptom | Check |
| --- | --- |
| Chat returns 503 `rate_limiter_unavailable` | Redis is down or unreachable. Chat stays closed until Redis answers. |
| Chat returns 503 `guardrails_unavailable` or `rag_unavailable` | That service is down or slower than 2 seconds. |
| Chat returns 503 `llm_unavailable` | Fixture mode should not do this. In live mode the chosen provider key is missing, the provider is down, or it exceeded 30 seconds. The other provider is not called. |
| `POST /v1/evaluate` returns 503 `evals_unavailable` | The evals service is down. Chat itself still succeeds. `/v1/ready` does not check evals. |
| `GET /v1/governance/summary` returns 503 `governance_unavailable` | The governance query failed. Chat writes stay best-effort. |
| `/v1/ready` is not 200 | Postgres, Redis, auth, guardrails, rag, or kafka failed. Ready does not ping a live LLM, Prometheus, Tempo, or Grafana. |
| Pods stay unready after a fresh apply | The `migrate` Job must finish before auth, gateway, guardrails, rag, and evals can use the schema. |
