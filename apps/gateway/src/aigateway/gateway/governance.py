from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select

from aigateway.contracts import ApprovalNotFoundError, GovernanceRecord
from aigateway.gateway.db import session_scope
from aigateway.gateway.models import Approval, GovernanceEvent


@dataclass
class ApprovalRow:
    id: str
    tenant_id: str
    requester_user_id: str
    correlation_id: str | None
    tool: str
    status: str
    decided_by: str | None = None


@dataclass
class MemoryGovernance:
    approvals: dict[str, ApprovalRow] = field(default_factory=dict)
    events: list[GovernanceRecord] = field(default_factory=list)
    tenants: dict[str, str] = field(default_factory=dict)

    async def create_approval(
        self,
        *,
        tenant_id: str,
        requester_user_id: str,
        correlation_id: str | None,
        tool: str,
    ) -> ApprovalRow:
        row = ApprovalRow(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            requester_user_id=requester_user_id,
            correlation_id=correlation_id,
            tool=tool,
            status="pending",
        )
        self.approvals[row.id] = row
        return row

    async def get_approval(self, approval_id: str) -> ApprovalRow:
        row = self.approvals.get(approval_id)
        if row is None:
            raise ApprovalNotFoundError()
        return row

    async def decide(self, approval_id: str, *, status: str, decided_by: str) -> ApprovalRow:
        row = await self.get_approval(approval_id)
        row.status = status
        row.decided_by = decided_by
        return row

    async def record(
        self,
        *,
        tenant_id: str,
        correlation_id: str | None,
        provider: str | None,
        model: str | None,
        route: str | None,
        estimated_cost: float | None,
        approval_status: str | None,
    ) -> None:
        self.tenants[correlation_id or ""] = tenant_id
        self.events.append(
            GovernanceRecord(
                correlation_id=correlation_id,
                provider=provider,
                model=model,
                route=route,
                estimated_cost=estimated_cost,
                approval_status=approval_status,
            )
        )

    async def list_governance(
        self,
        *,
        tenant_id: str,
        correlation_id: str | None,
    ) -> list[GovernanceRecord]:
        rows = []
        for item in reversed(self.events):
            owner = self.tenants.get(item.correlation_id or "")
            if owner != tenant_id:
                continue
            if correlation_id and item.correlation_id != correlation_id:
                continue
            rows.append(item)
        return rows[:50]


class SqlGovernance:
    async def create_approval(
        self,
        *,
        tenant_id: str,
        requester_user_id: str,
        correlation_id: str | None,
        tool: str,
    ) -> ApprovalRow:
        async with session_scope() as session:
            row = Approval(
                tenant_id=uuid.UUID(tenant_id),
                requester_user_id=uuid.UUID(requester_user_id),
                correlation_id=correlation_id,
                tool=tool,
                status="pending",
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return _approval(row)

    async def get_approval(self, approval_id: str) -> ApprovalRow:
        async with session_scope() as session:
            row = await session.get(Approval, uuid.UUID(approval_id))
            if row is None:
                raise ApprovalNotFoundError()
            return _approval(row)

    async def decide(self, approval_id: str, *, status: str, decided_by: str) -> ApprovalRow:
        async with session_scope() as session:
            row = await session.get(Approval, uuid.UUID(approval_id))
            if row is None:
                raise ApprovalNotFoundError()
            row.status = status
            row.decided_by = uuid.UUID(decided_by)
            row.decided_at = datetime.now(UTC)
            await session.commit()
            await session.refresh(row)
            return _approval(row)

    async def record(
        self,
        *,
        tenant_id: str,
        correlation_id: str | None,
        provider: str | None,
        model: str | None,
        route: str | None,
        estimated_cost: float | None,
        approval_status: str | None,
    ) -> None:
        async with session_scope() as session:
            session.add(
                GovernanceEvent(
                    tenant_id=uuid.UUID(tenant_id),
                    correlation_id=correlation_id,
                    provider=provider,
                    model=model,
                    route=route,
                    estimated_cost=estimated_cost,
                    approval_status=approval_status,
                )
            )
            await session.commit()

    async def list_governance(
        self,
        *,
        tenant_id: str,
        correlation_id: str | None,
    ) -> list[GovernanceRecord]:
        async with session_scope() as session:
            stmt = select(GovernanceEvent).where(GovernanceEvent.tenant_id == uuid.UUID(tenant_id))
            if correlation_id:
                stmt = stmt.where(GovernanceEvent.correlation_id == correlation_id)
            stmt = stmt.order_by(GovernanceEvent.created_at.desc()).limit(50)
            result = await session.execute(stmt)
            return [
                GovernanceRecord(
                    correlation_id=row.correlation_id,
                    provider=row.provider,
                    model=row.model,
                    route=row.route,
                    estimated_cost=row.estimated_cost,
                    approval_status=row.approval_status,
                )
                for row in result.scalars()
            ]


def _approval(row: Approval) -> ApprovalRow:
    return ApprovalRow(
        id=str(row.id),
        tenant_id=str(row.tenant_id),
        requester_user_id=str(row.requester_user_id),
        correlation_id=row.correlation_id,
        tool=row.tool,
        status=row.status,
        decided_by=str(row.decided_by) if row.decided_by else None,
    )
