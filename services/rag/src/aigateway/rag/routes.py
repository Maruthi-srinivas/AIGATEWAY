from __future__ import annotations

import secrets
import uuid

import httpx
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from aigateway.config import RagSettings
from aigateway.contracts import (
    AuthenticationError,
    DocumentDetail,
    DocumentIngest,
    DocumentList,
    DocumentNotFoundError,
    DocumentOut,
    PayloadTooLargeError,
    RetrieveResult,
    ValidationFailedError,
)
from aigateway.rag.chunking import CHUNK_SIZE, MAX_CHUNKS, MAX_TEXT_BYTES, chunk_text
from aigateway.rag.db import get_session
from aigateway.rag.embeddings import embed_text
from aigateway.rag.repository import (
    create_document,
    delete_document,
    get_document,
    list_documents,
    search_chunks,
)
from aigateway.telemetry import get_logger, tenant_id_var

logger = get_logger(__name__)

router = APIRouter(prefix="/internal/v1", tags=["internal"])


def _uuid(value: str, label: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ValidationFailedError(f"invalid {label}") from exc


class RetrieveRequest(BaseModel):
    tenant_id: str
    query: str = Field(min_length=1)
    top_k: int | None = None


def require_internal(request: Request, settings: RagSettings) -> None:
    provided = request.headers.get("x-internal-token", "")
    if not secrets.compare_digest(provided, settings.internal_auth_token):
        raise AuthenticationError("invalid internal token")


def get_settings(request: Request) -> RagSettings:
    return request.app.state.settings


def get_http(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


@router.post("/retrieve")
async def retrieve(
    body: RetrieveRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: RagSettings = Depends(get_settings),
    client: httpx.AsyncClient = Depends(get_http),
) -> RetrieveResult:
    require_internal(request, settings)
    tenant_token = tenant_id_var.set(body.tenant_id)
    try:
        embedding = await embed_text(body.query, settings, client=client)
        chunks = await search_chunks(
            session,
            tenant_id=_uuid(body.tenant_id, "tenant id"),
            embedding=embedding,
            top_k=body.top_k or settings.rag_top_k,
            min_score=settings.rag_min_score,
        )
    finally:
        tenant_id_var.reset(tenant_token)
    logger.info(
        "rag retrieve hits=%s tenant_id=%s",
        len(chunks),
        body.tenant_id,
    )
    return RetrieveResult(chunks=chunks)


@router.post("/documents")
async def ingest(
    body: DocumentIngest,
    request: Request,
    tenant_id: str,
    created_by: str | None = None,
    session: AsyncSession = Depends(get_session),
    settings: RagSettings = Depends(get_settings),
    client: httpx.AsyncClient = Depends(get_http),
) -> DocumentOut:
    require_internal(request, settings)
    encoded = body.text.encode("utf-8")
    if len(encoded) > MAX_TEXT_BYTES:
        raise PayloadTooLargeError("document text too large")
    parts = chunk_text(body.text)
    if (
        len(body.text) > CHUNK_SIZE
        and len(parts) >= MAX_CHUNKS
        and len(body.text) > CHUNK_SIZE * MAX_CHUNKS
    ):
        raise ValidationFailedError("document produced too many chunks")
    embedded: list[tuple[str, list[float]]] = []
    for part in parts:
        embedded.append((part, await embed_text(part, settings, client=client)))
    actor = _uuid(created_by, "created_by") if created_by else None
    result = await create_document(
        session,
        tenant_id=_uuid(tenant_id, "tenant id"),
        created_by=actor,
        title=body.title,
        body=body.text,
        classification=body.classification,
        acl=body.acl,
        chunks=embedded,
    )
    logger.info(
        "rag ingest document_id=%s tenant_id=%s chunk_count=%s",
        result.id,
        tenant_id,
        result.chunk_count,
    )
    return result


@router.get("/documents")
async def list_docs(
    request: Request,
    tenant_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    settings: RagSettings = Depends(get_settings),
) -> DocumentList:
    require_internal(request, settings)
    items, _total = await list_documents(
        session, _uuid(tenant_id, "tenant id"), limit=limit, offset=offset
    )
    return DocumentList(items=items, offset=offset, limit=limit)


@router.get("/documents/{document_id}")
async def read_doc(
    document_id: str,
    request: Request,
    tenant_id: str,
    session: AsyncSession = Depends(get_session),
    settings: RagSettings = Depends(get_settings),
) -> DocumentDetail:
    require_internal(request, settings)
    row = await get_document(
        session, _uuid(tenant_id, "tenant id"), _uuid(document_id, "document id")
    )
    if row is None:
        raise DocumentNotFoundError()
    return row


@router.delete("/documents/{document_id}")
async def remove_doc(
    document_id: str,
    request: Request,
    tenant_id: str,
    session: AsyncSession = Depends(get_session),
    settings: RagSettings = Depends(get_settings),
) -> dict[str, str]:
    require_internal(request, settings)
    ok = await delete_document(
        session, _uuid(tenant_id, "tenant id"), _uuid(document_id, "document id")
    )
    if not ok:
        raise DocumentNotFoundError()
    logger.info("rag delete document_id=%s tenant_id=%s", document_id, tenant_id)
    return {"status": "ok"}
