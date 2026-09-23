from __future__ import annotations

import re

from aigateway.contracts import Citation, RetrievedChunk

I_DONT_KNOW = "I don't know based on the available documents."
_TOKEN = re.compile(r"[a-z0-9]+")
_SECRETS = (
    re.compile(r"sk-[A-Za-z0-9]{10,}"),
    re.compile(r"agt_[A-Za-z0-9_-]{8,}"),
    re.compile(r"(?i)password=\S+"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
)


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


def mask_secrets(text: str) -> str:
    masked = text
    for pattern in _SECRETS:
        masked = pattern.sub("[SECRET]", masked)
    return masked


def split_sentences(text: str) -> list[str]:
    sentences: list[str] = []
    start = 0
    index = 0
    while index < len(text):
        char = text[index]
        if char in "!?":
            sentences.append(text[start : index + 1])
            start = _skip_space(text, index + 1)
            index = start
            continue
        if char == "." and not _decimal_point(text, index):
            sentences.append(text[start : index + 1])
            start = _skip_space(text, index + 1)
            index = start
            continue
        index += 1
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return [item.strip() for item in sentences if item.strip()]


def verify_answer(
    answer: str,
    chunks: list[RetrievedChunk],
) -> tuple[str, list[Citation], float, int]:
    """Redact secrets, drop unsupported sentences, and cite supporting chunks."""
    masked = mask_secrets(answer)
    prepared = [(chunk, set(_tokens(chunk.content))) for chunk in chunks]
    kept: list[tuple[str, list[str]]] = []
    checked = 0
    supported = 0
    for sentence in split_sentences(masked):
        tokens = _tokens(sentence)
        if not tokens:
            continue
        checked += 1
        claim = sentence != I_DONT_KNOW
        if claim and not any(_supported(tokens, words) for _, words in prepared):
            continue
        kept.append((sentence, tokens if claim else []))
        supported += 1
    dropped = checked - supported
    if checked == 0 or supported == 0:
        return I_DONT_KNOW, [], 0.0, dropped
    needed = {
        chunk.chunk_id
        for sentence, tokens in kept
        if tokens
        for chunk, words in prepared
        if _supported(tokens, words)
    }
    cited = [
        Citation(document_id=chunk.document_id, chunk_id=chunk.chunk_id)
        for chunk, _words in prepared
        if chunk.chunk_id in needed
    ]
    text = " ".join(sentence for sentence, _claim in kept)
    return text, cited, supported / checked, dropped


def _skip_space(text: str, index: int) -> int:
    while index < len(text) and text[index].isspace():
        index += 1
    return index


def _decimal_point(text: str, index: int) -> bool:
    return (
        index > 0
        and index + 1 < len(text)
        and text[index - 1].isdigit()
        and text[index + 1].isdigit()
    )


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _supported(claim: list[str], chunk: set[str]) -> bool:
    if not claim:
        return False
    hits = sum(1 for token in claim if token in chunk)
    return hits / len(claim) >= 0.5
