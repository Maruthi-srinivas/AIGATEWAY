# ADR-012: Retrieval ACL and secret masking inside RAG

- Status: Accepted
- Date: 2026-09-23
- Version: 6

## Context

Version 5 stores `classification` and `acl` but every tenant member can retrieve every tenant chunk. A secret written into a document would be copied into the model prompt. Filtering in the gateway would mean denied chunk text had already left RAG.

## Decision

1. `POST /internal/v1/retrieve` takes the caller **role**. SQL always filters `tenant_id` plus classification and acl. `acl` is an allow-list of roles; `[]` means every role in the tenant. Null, `public`, and `internal` are visible to every tenant role. `confidential` is `security_admin` and `platform_admin`. `restricted` and unknown labels are `platform_admin` only. Both gates apply. `platform_admin` may target another tenant and still obeys that tenant's rules.
2. Secret spans (`sk-`, `agt_`, `password=`, AWS-style keys) are replaced with `[SECRET]` on the text returned to the gateway. Stored body and chunk content stay intact.
3. Policy-denied rows are absent from the retrieve payload, citations, logs, and debug. Debug is `ChatRequest.debug` for `security_admin` and `platform_admin` only. Anyone else gets **403**. Debug carries ranks, scores, and drop reasons (`rerank_cut`, `dedupe`, `char_budget`) and never chunk text.
4. If every hit is filtered out, the gateway keeps the Version 5 I-don't-know path and does not call the LLM.

## Consequences

- Unauthorized chunk text does not cross the RAG boundary.
- Admins can still read the raw document through `/v1/documents/{id}`.
- Citation verification of model claims remains Version 7.

## Alternatives rejected

- **Filter in the gateway:** denied text would already be in the HTTP response from RAG.
- **Rewrite secrets at ingest:** operators could not see the original span, and a later policy change could not unmask it.
- **List denied ids in debug:** that tells a caller which hidden documents exist.
