from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aigateway.auth.audit import write_audit
from aigateway.auth.db import get_session
from aigateway.auth.deps import get_auth_context, require_roles, tenant_scope
from aigateway.auth.models import ApiKey, Tenant, User
from aigateway.auth.schemas import (
    ApiKeyOut,
    CreateApiKeyRequest,
    CreateTenantRequest,
    CreateUserRequest,
    PatchUserRequest,
    TenantOut,
    UserOut,
)
from aigateway.auth.security import ROLES, api_key_prefix, hash_secret, new_api_key
from aigateway.contracts import AuthContext, AuthorizationError

router = APIRouter(prefix="/v1/admin", tags=["admin"])


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("/tenants")
async def list_tenants(
    ctx: AuthContext = Depends(require_roles("platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> list[TenantOut]:
    result = await session.execute(select(Tenant).order_by(Tenant.slug))
    return [TenantOut.model_validate(row) for row in result.scalars()]


@router.post("/tenants")
async def create_tenant(
    body: CreateTenantRequest,
    request: Request,
    ctx: AuthContext = Depends(require_roles("platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> TenantOut:
    tenant = Tenant(slug=body.slug, name=body.name)
    session.add(tenant)
    await session.flush()
    await write_audit(
        session,
        action="tenant.create",
        resource=f"/v1/admin/tenants/{tenant.id}",
        success=True,
        status_code=200,
        context=ctx,
        ip=_ip(request),
    )
    await session.commit()
    await session.refresh(tenant)
    return TenantOut.model_validate(tenant)


@router.get("/users")
async def list_users(
    tenant_id: str | None = None,
    ctx: AuthContext = Depends(require_roles("platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> list[UserOut]:
    stmt = select(User)
    if tenant_id:
        stmt = stmt.where(User.tenant_id == uuid.UUID(tenant_id))
    result = await session.execute(stmt.order_by(User.email))
    return [UserOut.model_validate(row) for row in result.scalars()]


@router.post("/users")
async def create_user(
    body: CreateUserRequest,
    request: Request,
    ctx: AuthContext = Depends(require_roles("platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> UserOut:
    if body.role not in ROLES:
        raise AuthorizationError("invalid role")
    user = User(
        tenant_id=body.tenant_id,
        email=body.email,
        password_hash=hash_secret(body.password),
        role=body.role,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    await write_audit(
        session,
        action="user.create",
        resource=f"/v1/admin/users/{user.id}",
        success=True,
        status_code=200,
        context=ctx,
        ip=_ip(request),
    )
    await session.commit()
    await session.refresh(user)
    return UserOut.model_validate(user)


@router.patch("/users/{user_id}")
async def patch_user(
    user_id: uuid.UUID,
    body: PatchUserRequest,
    request: Request,
    ctx: AuthContext = Depends(require_roles("platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> UserOut:
    user = await session.get(User, user_id)
    if user is None:
        raise AuthorizationError("user not found")
    if body.role is not None:
        if body.role not in ROLES:
            raise AuthorizationError("invalid role")
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.password is not None:
        user.password_hash = hash_secret(body.password)
    await write_audit(
        session,
        action="user.patch",
        resource=f"/v1/admin/users/{user.id}",
        success=True,
        status_code=200,
        context=ctx,
        ip=_ip(request),
    )
    await session.commit()
    await session.refresh(user)
    return UserOut.model_validate(user)


@router.get("/api-keys")
async def list_api_keys(
    request: Request,
    tenant_id: str | None = None,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> list[ApiKeyOut]:
    if ctx.role not in {"platform_admin", "security_admin"}:
        await write_audit(
            session,
            action="apikey.list",
            resource="/v1/admin/api-keys",
            success=False,
            status_code=403,
            context=ctx,
            ip=_ip(request),
        )
        await session.commit()
        raise AuthorizationError()
    try:
        scoped = tenant_scope(ctx, tenant_id)
    except AuthorizationError:
        await write_audit(
            session,
            action="apikey.list",
            resource="/v1/admin/api-keys",
            success=False,
            status_code=403,
            context=ctx,
            ip=_ip(request),
            metadata={"requested_tenant_id": tenant_id},
        )
        await session.commit()
        raise
    stmt = select(ApiKey)
    if ctx.role != "platform_admin" or tenant_id:
        stmt = stmt.where(ApiKey.tenant_id == uuid.UUID(scoped))
    elif ctx.role == "platform_admin" and not tenant_id:
        pass
    result = await session.execute(stmt.order_by(ApiKey.created_at.desc()))
    return [ApiKeyOut.model_validate(row) for row in result.scalars()]


@router.post("/api-keys")
async def admin_create_api_key(
    body: CreateApiKeyRequest,
    request: Request,
    ctx: AuthContext = Depends(require_roles("platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    tenant = body.tenant_id or uuid.UUID(ctx.tenant_id)
    role = body.role or "service_account"
    if role not in ROLES:
        raise AuthorizationError("invalid role")
    key = new_api_key()
    row = ApiKey(
        tenant_id=tenant,
        name=body.name,
        prefix=api_key_prefix(key),
        key_hash=hash_secret(key),
        role=role,
    )
    session.add(row)
    await session.flush()
    await write_audit(
        session,
        action="apikey.create",
        resource=f"/v1/admin/api-keys/{row.id}",
        success=True,
        status_code=200,
        context=ctx,
        ip=_ip(request),
    )
    await session.commit()
    return {
        "id": str(row.id),
        "name": row.name,
        "prefix": row.prefix,
        "key": key,
        "role": row.role,
        "tenant_id": str(row.tenant_id),
    }


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: uuid.UUID,
    request: Request,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    if ctx.role not in {"platform_admin", "security_admin"}:
        raise AuthorizationError()
    row = await session.get(ApiKey, key_id)
    if row is None:
        raise AuthorizationError("api key not found")
    if ctx.role != "platform_admin" and str(row.tenant_id) != ctx.tenant_id:
        await write_audit(
            session,
            action="apikey.revoke",
            resource=f"/v1/admin/api-keys/{key_id}",
            success=False,
            status_code=403,
            context=ctx,
            ip=_ip(request),
        )
        await session.commit()
        raise AuthorizationError("cross-tenant access denied")
    row.revoked_at = datetime.now(UTC)
    await write_audit(
        session,
        action="apikey.revoke",
        resource=f"/v1/admin/api-keys/{key_id}",
        success=True,
        status_code=200,
        context=ctx,
        ip=_ip(request),
    )
    await session.commit()
    return {"status": "revoked"}
