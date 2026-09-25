# Scaling

Compose runs one replica of each service. That is the tested path.

On Kubernetes only the gateway Deployment scales. Its HPA allows 1 to 2 replicas and the update strategy is a rolling update. Auth, guardrails, RAG, evals, the worker, and the web console stay at 1 replica. Postgres, Redis, and Kafka stay single-replica. Do not add a second database or broker node in this install.

The gateway needs a CPU request so the HPA can compute utilization. Other Deployments do not have an autoscaler.
