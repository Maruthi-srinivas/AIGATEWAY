from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from aigateway.auth.db import get_session
from aigateway.auth.identity import resolve_identity
from aigateway.auth.security import PLATFORM_ROLE
from aigateway.config import AuthSettings
from aigateway.contracts import AuthContext, AuthorizationError


def get_settings(request: Request) -> AuthSettings:
    return request.app.state.settings


async def get_auth_context(
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: AuthSettings = Depends(get_settings),
) -> AuthContext:
    return await resolve_identity(
        session,
        settings,
        authorization=request.headers.get("authorization"),
        api_key=request.headers.get("x-api-key"),
    )


def require_roles(*roles: str):
    async def _inner(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
        allowed = set(roles)
        if ctx.role not in allowed and not allowed.intersection(ctx.roles):
            raise AuthorizationError()
        return ctx

    return _inner


def tenant_scope(ctx: AuthContext, requested_tenant_id: str | None) -> str:
    if ctx.role == PLATFORM_ROLE:
        return requested_tenant_id or ctx.tenant_id
    if requested_tenant_id and requested_tenant_id != ctx.tenant_id:
        raise AuthorizationError("cross-tenant access denied")
    return ctx.tenant_id
