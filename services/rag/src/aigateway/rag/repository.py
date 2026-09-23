from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from aigateway.contracts import DocumentDetail, DocumentOut, RetrieveResult
from aigateway.rag.hybrid import (
    RankedHit,
    apply_char_budget,
    build_result,
    dedupe,
    fuse_rrf,
    mask_secrets,
    rerank,
)
from aigateway.rag.models import Chunk, Document
from aigateway.telemetry import get_logger

logger = get_logger(__name__)

_POLICY = """
(
  COALESCE(d.classification, 'public') IN ('public', 'internal')
  OR (d.classification = 'confidential' AND :role IN ('security_admin', 'platform_admin'))
  OR (
    d.classification IS NOT NULL
    AND d.classification NOT IN ('public', 'internal', 'confidential')
    AND :role = 'platform_admin'
  )
)
AND (
  COALESCE(jsonb_array_length(d.acl), 0) = 0
  OR d.acl @> jsonb_build_array(CAST(:role AS text))
)
"""


def _out(row: Document, chunk_count: int) -> DocumentOut:
    return DocumentOut(
        id=str(row.id),
        tenant_id=str(row.tenant_id),
        title=row.title,
        classification=row.classification,
        acl=list(row.acl or []),
        chunk_count=chunk_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def create_document(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID | None,
    title: str,
    body: str,
    classification: str | None,
    acl: list[str],
    chunks: list[tuple[str, list[float]]],
) -> DocumentOut:
    now = datetime.now(UTC)
    doc = Document(
        tenant_id=tenant_id,
        title=title,
        body=body,
        classification=classification,
        acl=acl,
        created_by=created_by,
        created_at=now,
        updated_at=now,
    )
    session.add(doc)
    await session.flush()
    for index, (content, embedding) in enumerate(chunks):
        vector_literal = "[" + ",".join(str(float(value)) for value in embedding) + "]"
        await session.execute(
            text(
                """
                INSERT INTO chunks (
                    id, document_id, tenant_id, idx, content, embedding, search_vector
                )
                VALUES (
                    CAST(:id AS uuid),
                    CAST(:document_id AS uuid),
                    CAST(:tenant_id AS uuid),
                    :idx,
                    :content,
                    CAST(:embedding AS vector),
                    to_tsvector('simple', :search_text)
                )
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "document_id": str(doc.id),
                "tenant_id": str(tenant_id),
                "idx": index,
                "content": content,
                "embedding": vector_literal,
                "search_text": f"{title} {content}",
            },
        )
    await session.commit()
    await session.refresh(doc)
    return _out(doc, len(chunks))


async def list_documents(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    limit: int,
    offset: int,
) -> tuple[list[DocumentOut], int]:
    count = await session.scalar(
        select(func.count()).select_from(Document).where(Document.tenant_id == tenant_id)
    )
    rows = (
        (
            await session.execute(
                select(Document)
                .where(Document.tenant_id == tenant_id)
                .order_by(Document.updated_at.desc())
                .offset(offset)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    counts = {
        row.document_id: row.n
        for row in (
            await session.execute(
                select(Chunk.document_id, func.count().label("n"))
                .where(Chunk.tenant_id == tenant_id)
                .group_by(Chunk.document_id)
            )
        ).all()
    }
    return [_out(row, int(counts.get(row.id, 0))) for row in rows], int(count or 0)


async def get_document(
    session: AsyncSession, tenant_id: uuid.UUID, document_id: uuid.UUID
) -> DocumentDetail | None:
    row = await session.get(Document, document_id)
    if row is None or row.tenant_id != tenant_id:
        return None
    chunk_count = await session.scalar(
        select(func.count()).select_from(Chunk).where(Chunk.document_id == row.id)
    )
    base = _out(row, int(chunk_count or 0))
    return DocumentDetail(**base.model_dump(), body=row.body)


async def delete_document(
    session: AsyncSession, tenant_id: uuid.UUID, document_id: uuid.UUID
) -> bool:
    row = await session.get(Document, document_id)
    if row is None or row.tenant_id != tenant_id:
        return False
    await session.execute(delete(Document).where(Document.id == document_id))
    await session.commit()
    return True


async def search_chunks(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    role: str,
    embedding: list[float],
    query: str,
    top_k: int,
    candidate_k: int,
    min_score: float,
    max_chars: int,
    debug: bool,
) -> RetrieveResult:
    vector_rows = await _vector_hits(
        session,
        tenant_id=tenant_id,
        role=role,
        embedding=embedding,
        candidate_k=candidate_k,
        min_score=min_score,
    )
    bm25_rows = await _bm25_hits(
        session,
        tenant_id=tenant_id,
        role=role,
        query=query,
        candidate_k=candidate_k,
    )
    by_id = {row["id"]: row for row in (*vector_rows, *bm25_rows)}
    fused = fuse_rrf(
        [row["id"] for row in vector_rows],
        [row["id"] for row in bm25_rows],
    )[:candidate_k]
    ranked = [
        RankedHit(
            chunk_id=chunk_id,
            document_id=str(by_id[chunk_id]["document_id"]),
            content=mask_secrets(by_id[chunk_id]["content"]),
            vector_rank=vector_rank,
            bm25_rank=bm25_rank,
            rrf_score=rrf_score,
        )
        for chunk_id, rrf_score, vector_rank, bm25_rank in fused
    ]
    ordered = rerank(query, ranked)
    shortlisted = ordered[:top_k]
    dropped = [(hit, "rerank_cut") for hit in ordered[top_k:]]
    unique, dupes = dedupe(shortlisted)
    kept, over_budget = apply_char_budget(unique, max_chars)
    chunks, debug_payload, drop_count = build_result(
        kept,
        [*dropped, *dupes, *over_budget],
        include_debug=debug,
    )
    logger.info(
        "rag retrieve hits=%s dropped=%s tenant_id=%s",
        len(chunks),
        drop_count,
        tenant_id,
    )
    return RetrieveResult(chunks=chunks, debug=debug_payload)


async def _vector_hits(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    role: str,
    embedding: list[float],
    candidate_k: int,
    min_score: float,
) -> list[dict]:
    vector_literal = "[" + ",".join(str(float(value)) for value in embedding) + "]"
    result = await session.execute(
        text(
            f"""
            SELECT c.id::text AS id, c.document_id::text AS document_id, c.content,
                   1 - (c.embedding <=> CAST(:embedding AS vector)) AS score
            FROM chunks AS c
            JOIN documents AS d ON d.id = c.document_id
            WHERE c.tenant_id = CAST(:tenant_id AS uuid)
              AND {_POLICY}
              AND (1 - (c.embedding <=> CAST(:embedding AS vector))) >= :min_score
            ORDER BY c.embedding <=> CAST(:embedding AS vector)
            LIMIT :candidate_k
            """
        ),
        {
            "embedding": vector_literal,
            "tenant_id": str(tenant_id),
            "role": role,
            "min_score": min_score,
            "candidate_k": candidate_k,
        },
    )
    return [dict(row) for row in result.mappings()]


async def _bm25_hits(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    role: str,
    query: str,
    candidate_k: int,
) -> list[dict]:
    result = await session.execute(
        text(
            f"""
            SELECT c.id::text AS id, c.document_id::text AS document_id, c.content,
                   ts_rank(c.search_vector, plainto_tsquery('simple', :query)) AS score
            FROM chunks AS c
            JOIN documents AS d ON d.id = c.document_id
            WHERE c.tenant_id = CAST(:tenant_id AS uuid)
              AND {_POLICY}
              AND c.search_vector @@ plainto_tsquery('simple', :query)
            ORDER BY score DESC
            LIMIT :candidate_k
            """
        ),
        {
            "query": query,
            "tenant_id": str(tenant_id),
            "role": role,
            "candidate_k": candidate_k,
        },
    )
    return [dict(row) for row in result.mappings()]
