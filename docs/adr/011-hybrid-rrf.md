# ADR-011: Postgres full-text plus reciprocal rank fusion

- Status: Accepted
- Date: 2026-09-23
- Version: 6

## Context

Version 5 retrieval is vector-only. Rare keywords lose to chunks that share many hashed n-grams. A second search engine would add a Compose service. A learned reranker would add weights or an API key, and Compose stays keyless.

## Decision

1. BM25 is Postgres `tsvector` + `ts_rank` on **document title and chunk content**, using the **`simple`** dictionary so tokens are not stemmed away. A GIN index backs the column. No new container.
2. The vector leg and the BM25 leg each return up to `RAG_CANDIDATE_K` (32) rows. Vector hits below `RAG_MIN_SCORE` (cosine 0.3) are dropped **before** fusion. The fused score is **not** compared to 0.3.
3. Fusion is reciprocal rank with `k=60`. A fixture token-overlap rerank then orders the fused list. The prompt keeps `RAG_TOP_K` (8) after that, then drops duplicate normalized text and stops at `RAG_CONTEXT_MAX_CHARS` (8000).
4. The whole pipeline stays inside `services/rag`. The gateway still calls retrieve and generates.

## Consequences

- A lexical golden query can outrank a vector distractor without an embedding-model change.
- `simple` matching is literal. English stemming is not available in this slice.
- Hybrid BM25 is in. Cross-encoders, OpenSearch, and query rewriting are not.

## Alternatives rejected

- **OpenSearch:** another stateful service for an MVP that already has Postgres.
- **Apply 0.3 to the fused score:** RRF scores are tiny, so every lexical-only hit would disappear.
- **Ship a cross-encoder:** image size and a key, which Version 5 already deferred.
