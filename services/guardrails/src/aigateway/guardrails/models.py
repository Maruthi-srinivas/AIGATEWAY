from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TenantPolicy(Base):
    __tablename__ = "guardrail_policies"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    prompt_injection: Mapped[bool] = mapped_column(Boolean, default=True)
    jailbreak: Mapped[bool] = mapped_column(Boolean, default=True)
    moderation: Mapped[bool] = mapped_column(Boolean, default=True)
    token_limit: Mapped[bool] = mapped_column(Boolean, default=True)
    pii: Mapped[bool] = mapped_column(Boolean, default=True)
    pii_action: Mapped[str] = mapped_column(String(16), default="redact")
    max_input_chars: Mapped[int] = mapped_column(Integer, default=4000)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
