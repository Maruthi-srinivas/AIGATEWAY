# ADR-013: Lexical citation checks on the gateway

- Status: Accepted
- Date: 2026-09-23
- Version: 7

## Context

Version 6 citations are every chunk inserted into the prompt. A model can still state a fact that none of those chunks support, and a live answer can repeat a secret that retrieval already masked. A judge model would need another API key. Compose stays fixture.

## Decision

1. After generate, the gateway redacts `sk-`, `agt_`, `password=`, and AWS-style keys to `[SECRET]`, then splits the answer into sentences on `.` `!` `?`. A period between digits stays in the sentence.
2. A sentence is supported when at least half of its `[a-z0-9]+` tokens occur in one retrieved chunk. The exact I-don't-know string is supported without a chunk. Sentences with no tokens are ignored.
3. Unsupported sentences are dropped. If none remain, the response is the existing I-don't-know string, `citations: []`, and `groundedness: 0`. Otherwise citations are the supporting chunks in prompt order. `groundedness` is supported sentences divided by sentences checked. `confidence` stays the Jev safety score.
4. Chitchat and the no-chunk path skip the sentence check. `groundedness` is null. Both still redact secrets and run the Jev output check. A Jev block replaces the answer with the output refusal and clears citations.
5. A redact decision `citation_unverified` records `dropped=N` only. The dropped sentence is not stored, streamed, or logged. Audit metadata stores `groundedness` and `unsupported_count`.
6. Fixture mode emits one sentence per retrieved chunk, using that chunk's text, so a keyless answer stays supported. SSE generates fully, then replays the rewritten text.

## Consequences

- Users do not see an unsupported sentence or a raw secret span from the model.
- Citations mean "this chunk supports a kept sentence," not "this chunk was in the prompt."
- Overlap is lexical. A true paraphrase can be dropped. Faithfulness evals stay Version 10.

## Alternatives rejected

- **A second LLM as judge:** needs a key and fails the keyless compose rule.
- **Refuse the whole answer when any sentence fails:** a supported fact would be discarded with the bad sentence.
- **Keep Version 6 citations:** the client could not tell which chunks the visible answer used.
