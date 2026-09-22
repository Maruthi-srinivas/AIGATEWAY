from __future__ import annotations

CHUNK_SIZE = 2048
CHUNK_OVERLAP = 256
MAX_CHUNKS = 200
MAX_TEXT_BYTES = 262144


def chunk_text(text: str, *, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    if len(text) <= size:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
        if len(chunks) >= MAX_CHUNKS:
            break
    return chunks
