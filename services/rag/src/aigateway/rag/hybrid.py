from __future__ import annotations

import re
from dataclasses import dataclass

from aigateway.contracts import RetrievalDebug, RetrievalDebugHit, RetrievedChunk

RRF_K = 60
_TOKEN = re.compile(r"[a-z0-9]+")
_SECRETS = (
    re.compile(r"sk-[A-Za-z0-9]{10,}"),
    re.compile(r"agt_[A-Za-z0-9_-]{8,}"),
    re.compile(r"(?i)password=\S+"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
)


@dataclass
class RankedHit:
    chunk_id: str
    document_id: str
    content: str
    vector_rank: int | None = None
    bm25_rank: int | None = None
    rrf_score: float = 0.0
    rerank_score: float = 0.0


def fuse_rrf(
    vector_ids: list[str],
    bm25_ids: list[str],
    *,
    k: int = RRF_K,
) -> list[tuple[str, float, int | None, int | None]]:
    """Return ids ordered by reciprocal rank fusion, best first."""
    scores: dict[str, dict] = {}
    for rank, chunk_id in enumerate(vector_ids, start=1):
        row = scores.setdefault(chunk_id, {"rrf": 0.0, "vector_rank": None, "bm25_rank": None})
        row["vector_rank"] = rank
        row["rrf"] += 1.0 / (k + rank)
    for rank, chunk_id in enumerate(bm25_ids, start=1):
        row = scores.setdefault(chunk_id, {"rrf": 0.0, "vector_rank": None, "bm25_rank": None})
        row["bm25_rank"] = rank
        row["rrf"] += 1.0 / (k + rank)
    ordered = sorted(scores, key=lambda chunk_id: scores[chunk_id]["rrf"], reverse=True)
    return [
        (
            chunk_id,
            scores[chunk_id]["rrf"],
            scores[chunk_id]["vector_rank"],
            scores[chunk_id]["bm25_rank"],
        )
        for chunk_id in ordered
    ]


def mask_secrets(text: str) -> str:
    masked = text
    for pattern in _SECRETS:
        masked = pattern.sub("[SECRET]", masked)
    return masked


def token_overlap(query: str, content: str) -> float:
    tokens = _TOKEN.findall(query.lower())
    if not tokens:
        return 0.0
    present = set(_TOKEN.findall(content.lower()))
    return sum(1 for token in tokens if token in present) / len(tokens)


def rerank(query: str, hits: list[RankedHit]) -> list[RankedHit]:
    for hit in hits:
        hit.rerank_score = token_overlap(query, hit.content)
    return sorted(hits, key=lambda hit: (hit.rerank_score, hit.rrf_score), reverse=True)


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def dedupe(hits: list[RankedHit]) -> tuple[list[RankedHit], list[tuple[RankedHit, str]]]:
    kept: list[RankedHit] = []
    dropped: list[tuple[RankedHit, str]] = []
    seen: dict[str, RankedHit] = {}
    for hit in hits:
        key = _norm(hit.content)
        previous = seen.get(key)
        if previous is None:
            seen[key] = hit
            kept.append(hit)
            continue
        if hit.rerank_score > previous.rerank_score:
            kept.remove(previous)
            dropped.append((previous, "dedupe"))
            seen[key] = hit
            kept.append(hit)
        else:
            dropped.append((hit, "dedupe"))
    return kept, dropped


def apply_char_budget(
    hits: list[RankedHit], max_chars: int
) -> tuple[list[RankedHit], list[tuple[RankedHit, str]]]:
    kept: list[RankedHit] = []
    dropped: list[tuple[RankedHit, str]] = []
    used = 0
    for index, hit in enumerate(hits):
        if kept and used + len(hit.content) > max_chars:
            dropped.extend((item, "char_budget") for item in hits[index:])
            break
        kept.append(hit)
        used += len(hit.content)
    return kept, dropped


def build_result(
    kept: list[RankedHit],
    dropped: list[tuple[RankedHit, str]],
    *,
    include_debug: bool,
) -> tuple[list[RetrievedChunk], RetrievalDebug | None, int]:
    chunks = [
        RetrievedChunk(
            chunk_id=hit.chunk_id,
            document_id=hit.document_id,
            content=hit.content,
            score=hit.rerank_score,
        )
        for hit in kept
    ]
    drop_count = len(dropped)
    if not include_debug:
        return chunks, None, drop_count
    hits = [_debug_hit(hit, kept=True, drop_reason=None) for hit in kept] + [
        _debug_hit(hit, kept=False, drop_reason=reason) for hit, reason in dropped
    ]
    return chunks, RetrievalDebug(hits=hits), drop_count


def _debug_hit(hit: RankedHit, *, kept: bool, drop_reason: str | None) -> RetrievalDebugHit:
    return RetrievalDebugHit(
        chunk_id=hit.chunk_id,
        document_id=hit.document_id,
        vector_rank=hit.vector_rank,
        bm25_rank=hit.bm25_rank,
        rrf_score=hit.rrf_score,
        rerank_score=hit.rerank_score,
        kept=kept,
        drop_reason=drop_reason,
    )
