from __future__ import annotations

import uuid

from fastapi import Request

from aigateway.contracts import (
    ApprovalDecision,
    ApprovalNotFoundError,
    ApprovalRecord,
    AuthorizationError,
    GovernanceRecord,
    GovernanceUnavailableError,
    ValidationFailedError,
)
from aigateway.gateway.deps import effective_tenant_id, require_auth
from aigateway.gateway.tools import APPROVAL_APPROVED, APPROVAL_DENIED

APPROVE_ROLES = frozenset({"security_admin", "platform_admin"})
_DETAILS = {"approved": APPROVAL_APPROVED, "denied": APPROVAL_DENIED}


async def handle_decide(
    request: Request,
    approval_id: str,
    body: ApprovalDecision,
) -> ApprovalRecord:
    ctx = await require_auth(request)
    if ctx.role not in APPROVE_ROLES:
        raise AuthorizationError("approval is forbidden")
    try:
        uuid.UUID(approval_id)
    except ValueError as exc:
        raise ValidationFailedError("invalid approval id") from exc
    row = await request.app.state.governance.get_approval(approval_id)
    if ctx.role != "platform_admin" and row.tenant_id != ctx.tenant_id:
        raise ApprovalNotFoundError()
    if row.requester_user_id == ctx.user_id:
        raise AuthorizationError("cannot approve own request")
    if row.status != "pending":
        raise ValidationFailedError("approval is already decided")
    status = "approved" if body.decision == "approve" else "denied"
    updated = await request.app.state.governance.decide(
        approval_id,
        status=status,
        decided_by=ctx.user_id,
    )
    return ApprovalRecord(
        id=updated.id,
        status=updated.status,  # type: ignore[arg-type]
        tool=updated.tool,
        detail=_DETAILS[status],
    )


async def handle_governance(
    request: Request,
    *,
    correlation_id: str | None,
    tenant_id: str | None,
) -> list[GovernanceRecord]:
    ctx = await require_auth(request)
    if ctx.role not in APPROVE_ROLES:
        raise AuthorizationError("governance is forbidden")
    if not correlation_id:
        raise ValidationFailedError("correlation id is required")
    effective = effective_tenant_id(ctx, tenant_id)
    try:
        return await request.app.state.governance.list_governance(
            tenant_id=effective,
            correlation_id=correlation_id,
        )
    except GovernanceUnavailableError:
        raise
    except Exception as exc:
        raise GovernanceUnavailableError() from exc
