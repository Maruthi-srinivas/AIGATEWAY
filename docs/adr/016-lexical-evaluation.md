# ADR-016: Lexical evaluation and one retrieval retry

## Status

Accepted. Version 10.

## Context

Chat already returns groundedness. Version 10 needs a golden-set report, a stored score row, and a small self-heal when a retrieved answer is weakly grounded. A judge model, a second LLM, and a failure when the mean is under 95% are out of scope.

## Decision

1. Scores are lexical. Faithfulness is groundedness. The exact sentence `I don't know based on the available documents.` scores 1.0 when groundedness is null. Context recall is the share of expected terms found in any chunk. Context precision is the share of chunks that contain an expected term. Answer correctness is the share of expected terms found in the answer. Empty expected terms leave recall, precision, and correctness null.
2. The golden set is `services/evals/golden/hr.json`. Cases have `question` and `expected_terms` only.
3. `POST /v1/evaluate` is `security_admin` or `platform_admin`. The gateway runs each question through `POST /v1/chat` for the caller tenant and stores the run in `services/evals`.
4. The report includes `target_faithfulness: 0.95` and `met_target`. The Compose test fails when a case errors or faithfulness is missing. A mean under 0.95 does not fail the test.
5. After a knowledge chat, the gateway best-effort stores one row and publishes one `ai.evaluations` event. Payloads and rows have no prompt, answer, or chunk text. Chitchat does not publish. Chat still succeeds if evals is down. `POST /v1/evaluate` returns 503 `evals_unavailable` when evals is down. `/v1/ready` does not check evals.
6. If chunks were retrieved and groundedness is under 0.5, retrieve once more with stopwords removed. Keep the better groundedness. There is no second LLM and no reranker swap. The no-chunk path does not retry. A row that stays under 0.5 with chunks is `review`.
7. The answer cache key is tenant, role, policy hash, and SHA256 of the normalized query. It stores the final redacted answer and citations. Blocks, debug requests, and streams are not cached. A hit still runs the output guardrail check. Ingest and delete clear that tenant's keys so a removed document is not cited from cache.
8. Optional feedback on `POST /v1/evaluate` is `up` or `down`.
9. Alembic for evals uses `evals_alembic_version` and runs after RAG. Gateway OpenAPI is 0.9.0. `ChatResponse` does not gain score fields.

## Consequences

Online scoring and the golden report share one scorer. A weak live model can miss the 95% line without breaking CI. Redis or evals being down changes cache hits and stored rows, not the chat HTTP status.
