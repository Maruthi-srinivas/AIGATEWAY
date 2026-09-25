# STRIDE

Each row points at a check that already exists. Version 12 does not add a new crypto path.

| Threat | What we rely on |
| --- | --- |
| Spoofing | Login and introspection reject a missing or invalid token (401). Gateway tests cover unauthenticated chat. |
| Tampering | Tenant filters and RBAC reject a body that names another tenant. `policy_hash` changes when the stored guardrail policy changes, so a cached answer misses. |
| Repudiation | Auth writes an audit row for security decisions. `DELETE /v1/audit` is not registered, so a client cannot remove rows. The unit test expects 405 or 404. |
| Information disclosure | Governance, evaluation, and audit reads are tenant-scoped. The live tenant-isolation tests and the summary test show another tenant's prompt is absent. Logs omit prompts, answers, and chunk text. |
| Denial of service | Chat rate limiting fails closed when Redis is down (503). Guardrails and RAG fail closed after 2 seconds. The gateway HPA only scales that Deployment from 1 to 2 replicas. |
| Elevation of privilege | RBAC tests reject an `app_user` on admin routes. A requester cannot approve their own export. A non-platform caller who passes another `tenant_id` gets 403. |
