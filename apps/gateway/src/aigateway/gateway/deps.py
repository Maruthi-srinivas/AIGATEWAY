from __future__ import annotations

from fastapi import Request

from aigateway.contracts import AuthContext, AuthorizationError
from aigateway.telemetry import tenant_id_var, user_id_var

CHAT_ROLES = {"app_user", "service_account", "security_admin", "platform_admin"}
POLICY_ROLES = {"security_admin", "platform_admin"}
PLATFORM_ADMIN = "platform_admin"


async def require_auth(request: Request) -> AuthContext:
    provider = request.app.state.auth_client
    ctx = await provider.authenticate(
        authorization=request.headers.get("authorization"),
        api_key=request.headers.get("x-api-key"),
    )
    request.state.auth = ctx
    request.state.user_token = user_id_var.set(ctx.user_id)
    request.state.tenant_token = tenant_id_var.set(ctx.tenant_id)
    return ctx


def require_chat_role(ctx: AuthContext) -> None:
    if ctx.role not in CHAT_ROLES:
        raise AuthorizationError("chat is not allowed for this role")


def require_policy_role(ctx: AuthContext) -> None:
    if ctx.role not in POLICY_ROLES:
        raise AuthorizationError("policy access is forbidden")


def effective_tenant_id(ctx: AuthContext, requested: str | None) -> str:
    if requested is None:
        return ctx.tenant_id
    if ctx.role != PLATFORM_ADMIN:
        raise AuthorizationError("tenant impersonation is forbidden")
    return requested
