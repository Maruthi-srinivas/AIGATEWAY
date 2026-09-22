# ADR-004: PostgreSQL over MongoDB

- Status: Accepted
- Date: 2026-09-21
- Version: 1

## Context

Users, conversations, documents, evaluations, and audit logs need transactions, constraints, and (later) tenant isolation on every row. Version 1 only health-checks Postgres; the schema arrives in later versions.

## Decision

Use **PostgreSQL 16** as the system of record. MongoDB is not the primary store.

## Consequences

- Relational integrity and SQL audit queries match a safety/governance product.
- Later versions can add `pgvector` in the same database if we want fewer moving parts, or a sidecar vector store without abandoning SQL for policies.
- Gateway requires `POSTGRES_DSN` and fails `/v1/ready` if the database is down.

## Alternatives rejected

- **MongoDB**: flexible documents, weaker default story for RBAC joins and transactional audit.
- **SQLite**: fine for a demo, not for multi-service Docker and future replicas.
