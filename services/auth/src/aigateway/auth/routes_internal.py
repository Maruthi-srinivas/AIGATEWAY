from __future__ import annotations

import secrets
import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from aigateway.auth.audit import write_audit
from aigateway.auth.db import get_session
from aigateway.auth.deps import get_settings
from aigateway.auth.identity import resolve_identity
from aigateway.auth.schemas import AuditWriteRequest, IntrospectRequest
from aigateway.config import AuthSettings
from aigateway.contracts import AuthenticationError

router = APIRouter(prefix="/internal/v1", tags=["internal"])


def require_internal(request: Request, settings: AuthSettings) -> None:
    provided = request.headers.get("x-internal-token", "")
    if not secrets.compare_digest(provided, settings.internal_auth_token):
        raise AuthenticationError("invalid internal token")


@router.post("/introspect")
async def introspect(
    body: IntrospectRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: AuthSettings = Depends(get_settings),
) -> dict:
    require_internal(request, settings)
    try:
        ctx = await resolve_identity(
            session,
            settings,
            authorization=body.authorization,
            api_key=body.api_key,
        )
    except AuthenticationError:
        await write_audit(
            session,
            action="auth.introspect",
            resource="/internal/v1/introspect",
            success=False,
            status_code=401,
            ip=request.client.host if request.client else None,
        )
        await session.commit()
        raise
    if ctx.auth_method == "api_key":
        await write_audit(
            session,
            action="auth.api_key_use",
            resource="/internal/v1/introspect",
            success=True,
            status_code=200,
            context=ctx,
        )
        await session.commit()
    else:
        await session.commit()
    return ctx.model_dump()


@router.post("/audit")
async def write_internal_audit(
    body: AuditWriteRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: AuthSettings = Depends(get_settings),
) -> dict[str, str]:
    require_internal(request, settings)
    tenant_id = uuid.UUID(body.tenant_id) if body.tenant_id else None
    actor_user_id = uuid.UUID(body.actor_user_id) if body.actor_user_id else None
    await write_audit(
        session,
        action=body.action,
        resource=body.resource,
        success=body.success,
        status_code=body.status_code,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        actor_key_prefix=body.actor_key_prefix,
        ip=request.client.host if request.client else None,
        metadata=body.metadata,
    )
    await session.commit()
    return {"status": "ok"}
