# ADR-018: Operations manifests and cost summary

## Status

Accepted. Version 12.

## Context

Compose already runs the stack and the tests. Operators asked for a cluster install, a threat map, and a cost total that does not expose prompts. A Helm chart, a cluster inside CI, a key-rotation API, signed prompts, and an audit hash chain were considered and left out.

## Decision

1. Kubernetes is plain YAML under `infrastructure/k8s`, namespace `aigateway`. One Deployment per Compose service. Postgres, Redis, and Kafka stay single-replica. An Ingress sends `/v1` to the gateway. The gateway Deployment uses a rolling update and an HPA from 1 to 2 replicas. Other apps stay at 1 replica.
2. CI keeps `docker compose --profile test`. A second job runs kubeconform against the manifests. CI does not start a cluster. A golden-set score under 0.95 does not fail the build.
3. `JWT_SECRET` and `INTERNAL_AUTH_TOKEN` are placeholders in a Secret. Non-secret settings are a ConfigMap. A unit scan fails on a real-looking provider key and allows the fixture prefixes already in the repo.
4. STRIDE is a map to tests and logs that already exist. `DELETE /v1/audit` is not implemented. Rotation is a runbook: change the env value and roll the pods. The process does not accept a second secret at runtime.
5. `GET /v1/governance/summary` sums estimated cost and request count by model for the caller tenant. `security_admin` and `platform_admin` may read it. A non-platform caller who names another tenant gets 403. The body has no prompt or answer. A read failure is 503 `governance_unavailable`.
6. Prometheus counter `aigateway_estimated_cost_dollars_total` is labeled by model only. Grafana has one panel for it. There is no new page in `apps/web`.
7. Gateway OpenAPI is 0.11.0. `ChatResponse` is unchanged.

## Consequences

Compose remains the path that tests run. The manifests are a second install that kubeconform can check without a cluster. Cost is visible by model, and a tenant admin cannot read another tenant's totals.
