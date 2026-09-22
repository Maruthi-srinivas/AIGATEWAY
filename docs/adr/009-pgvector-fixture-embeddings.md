# ADR-009: pgvector on the shared Postgres with fixture hashed embeddings

- Status: Accepted
- Date: 2026-09-22
- Version: 5

## Context

Version 5 needs tenant-scoped retrieval without a sidecar vector database, without shipping embedding weights, and without an OpenAI key in Compose. Options were: pgvector on the existing Postgres, a dedicated vector service, or in-memory fixtures only.

## Decision

1. Switch Compose Postgres to **`pgvector/pgvector:pg16`**. RAG Alembic runs `CREATE EXTENSION IF NOT EXISTS vector` and stores `chunks.embedding vector(256)` with an HNSW cosine index.
2. **`services/rag` owns documents, chunks, embeddings, and search.** The gateway HTTP-calls `POST /internal/v1/retrieve` with `INTERNAL_AUTH_TOKEN`. Every query filters `tenant_id`. Unused `acl` and `classification` columns are stored for Version 6.
3. Compose defaults to **`EMBEDDING_MODE=fixture`**: whitespace tokens plus adjacent n-grams hashed into a unit **256-d** vector so overlapping wording retrieves. Live OpenAI-compatible embeddings (`POST /v1/embeddings`) run from the RAG container only, always with `dimensions: 256` so the column never changes. Missing live key fails closed on ingest and retrieve.
4. Chunking is character-based (**2048 / 256**), ingest cap **256 KiB** decoded text, max **200** chunks. Search is `top_k=8`, cosine, drop scores below `RAG_MIN_SCORE` (default **0.3**).
5. Existing `postgres:16` volumes do not contain the extension binary. Operators run **`docker compose down -v` once** (or use a fresh volume) after the image switch.

## Consequences

- One database, four Alembic histories (`rag_alembic_version` is the fourth).
- Compose tests need no embedding key. Seeded HR vs Eng markdown is enough to prove tenant isolation.
- Hybrid BM25, rerank, retrieval ACL, PDF ingest, and Kafka workers remain later versions.

## Alternatives rejected

- **Sidecar Qdrant/Weaviate**: another stateful service and another backup story for an MVP.
- **Always-on vendor embeddings**: Compose and air-gapped demos would need a key.
- **Change vector width later**: live and fixture would diverge; freezing 256-d avoids a rewrite.
- **In-memory-only retrieve**: would not survive container restarts or prove Postgres tenant filters.
