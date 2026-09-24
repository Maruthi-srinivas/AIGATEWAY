from __future__ import annotations

import uuid

from fastapi import Request

from aigateway.contracts import (
    DocumentDetail,
    DocumentIngest,
    DocumentList,
    ValidationFailedError,
)
from aigateway.gateway.deps import effective_tenant_id, require_auth, require_policy_role


async def _drop_answer_cache(request: Request, tenant_id: str) -> None:
    cache = getattr(request.app.state, "answer_cache", None)
    if cache is not None:
        await cache.invalidate_tenant(tenant_id)


def _requested_tenant(tenant_id: str | None) -> str | None:
    if tenant_id is None:
        return None
    try:
        uuid.UUID(tenant_id)
    except ValueError as exc:
        raise ValidationFailedError("invalid tenant id") from exc
    return tenant_id


async def handle_ingest(request: Request, body: DocumentIngest, tenant_id: str | None):
    ctx = await require_auth(request)
    require_policy_role(ctx)
    effective = effective_tenant_id(ctx, _requested_tenant(tenant_id))
    created = await request.app.state.rag_client.ingest(effective, body, ctx.user_id)
    await _drop_answer_cache(request, effective)
    return created


async def handle_list_documents(
    request: Request,
    *,
    tenant_id: str | None,
    limit: int,
    offset: int,
) -> DocumentList:
    ctx = await require_auth(request)
    require_policy_role(ctx)
    effective = effective_tenant_id(ctx, _requested_tenant(tenant_id))
    return await request.app.state.rag_client.list_documents(effective, limit=limit, offset=offset)


async def handle_get_document(
    request: Request, document_id: str, tenant_id: str | None
) -> DocumentDetail:
    ctx = await require_auth(request)
    require_policy_role(ctx)
    try:
        uuid.UUID(document_id)
    except ValueError as exc:
        raise ValidationFailedError("invalid document id") from exc
    effective = effective_tenant_id(ctx, _requested_tenant(tenant_id))
    return await request.app.state.rag_client.get_document(effective, document_id)


async def handle_delete_document(
    request: Request, document_id: str, tenant_id: str | None
) -> dict[str, str]:
    ctx = await require_auth(request)
    require_policy_role(ctx)
    try:
        uuid.UUID(document_id)
    except ValueError as exc:
        raise ValidationFailedError("invalid document id") from exc
    effective = effective_tenant_id(ctx, _requested_tenant(tenant_id))
    await request.app.state.rag_client.delete_document(effective, document_id)
    await _drop_answer_cache(request, effective)
    return {"status": "ok"}
