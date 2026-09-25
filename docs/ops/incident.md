# Security incident

Treat a leaked `JWT_SECRET` or `INTERNAL_AUTH_TOKEN` as an incident.

1. Put the new value in the Compose env file or in the Kubernetes Secret. Replace the old value. Do not leave both values configured. The process accepts one secret and does not check a previous one.
2. Restart the containers or roll the pods that read that value. Auth reads `JWT_SECRET`. Auth, the gateway, guardrails, RAG, evals, and the worker read `INTERNAL_AUTH_TOKEN`.
3. Existing access tokens and API keys signed with the old JWT secret stop working. Users log in again.
4. Confirm `/v1/ready` is healthy and that a chat with a new token succeeds.

There is no rotation API. `DELETE /v1/audit` does not remove audit rows.
