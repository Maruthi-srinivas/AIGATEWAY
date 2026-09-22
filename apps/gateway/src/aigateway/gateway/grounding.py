from __future__ import annotations

from aigateway.contracts import Citation, RetrievedChunk

I_DONT_KNOW = "I don't know based on the available documents."


def grounded_messages(
    history: list[dict[str, str]],
    chunks: list[RetrievedChunk],
) -> tuple[list[dict[str, str]], list[Citation]]:
    lines: list[str] = []
    citations: list[Citation] = []
    for index, chunk in enumerate(chunks, start=1):
        lines.append(f"[{index}] document_id={chunk.document_id} chunk_id={chunk.chunk_id}")
        lines.append(chunk.content)
        citations.append(Citation(document_id=chunk.document_id, chunk_id=chunk.chunk_id))
    system = (
        "You are a grounded assistant. Answer only from CONTEXT. "
        "If the answer is not in CONTEXT, say you don't know.\n\nCONTEXT:\n" + "\n".join(lines)
    )
    return [{"role": "system", "content": system}, *history], citations
