from __future__ import annotations

import uuid

from fastapi import Request

from aigateway.contracts import GuardrailPolicy, GuardrailPolicyUpdate, ValidationFailedError
from aigateway.gateway.deps import effective_tenant_id, require_auth, require_policy_role


def _requested_tenant(tenant_id: str | None) -> str | None:
    if tenant_id is None:
        return None
    try:
        uuid.UUID(tenant_id)
    except ValueError as exc:
        raise ValidationFailedError("invalid tenant id") from exc
    return tenant_id


async def handle_get_policy(request: Request, tenant_id: str | None) -> GuardrailPolicy:
    ctx = await require_auth(request)
    require_policy_role(ctx)
    effective = effective_tenant_id(ctx, _requested_tenant(tenant_id))
    return await request.app.state.guardrail_client.get_policy(effective)


async def handle_patch_policy(
    request: Request,
    body: GuardrailPolicyUpdate,
    tenant_id: str | None,
) -> GuardrailPolicy:
    ctx = await require_auth(request)
    require_policy_role(ctx)
    effective = effective_tenant_id(ctx, _requested_tenant(tenant_id))
    return await request.app.state.guardrail_client.patch_policy(effective, body)
