from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from aigateway.contracts import DocumentDetail, DocumentOut, RetrievedChunk
from aigateway.rag.models import Chunk, Document


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
        session.add(
            Chunk(
                document_id=doc.id,
                tenant_id=tenant_id,
                idx=index,
                content=content,
                embedding=embedding,
            )
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
    embedding: list[float],
    top_k: int,
    min_score: float,
) -> list[RetrievedChunk]:
    vector_literal = "[" + ",".join(str(float(value)) for value in embedding) + "]"
    result = await session.execute(
        text(
            """
            SELECT id, document_id, content,
                   1 - (embedding <=> CAST(:embedding AS vector)) AS score
            FROM chunks
            WHERE tenant_id = CAST(:tenant_id AS uuid)
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :top_k
            """
        ),
        {"embedding": vector_literal, "tenant_id": str(tenant_id), "top_k": top_k},
    )
    hits: list[RetrievedChunk] = []
    for row in result.mappings():
        score = float(row["score"] or 0)
        if score < min_score:
            continue
        hits.append(
            RetrievedChunk(
                chunk_id=str(row["id"]),
                document_id=str(row["document_id"]),
                content=row["content"],
                score=score,
            )
        )
    return hits
