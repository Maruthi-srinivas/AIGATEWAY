from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class UserOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    role: str
    is_active: bool

    model_config = {"from_attributes": True}


class TenantOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class CreateTenantRequest(BaseModel):
    slug: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=200)


class CreateUserRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
    role: str
    tenant_id: uuid.UUID


class PatchUserRequest(BaseModel):
    role: str | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8)


class CreateApiKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    role: str | None = None
    tenant_id: uuid.UUID | None = None


class ApiKeyCreated(BaseModel):
    id: uuid.UUID
    name: str
    prefix: str
    key: str
    role: str
    tenant_id: uuid.UUID


class ApiKeyOut(BaseModel):
    id: uuid.UUID
    name: str
    prefix: str
    role: str
    tenant_id: uuid.UUID
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None

    model_config = {"from_attributes": True}


class AuditOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID | None
    actor_user_id: uuid.UUID | None
    actor_key_prefix: str | None
    action: str
    resource: str
    success: bool
    status_code: int
    correlation_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class IntrospectRequest(BaseModel):
    authorization: str | None = None
    api_key: str | None = None


class AuditWriteRequest(BaseModel):
    action: str
    resource: str
    success: bool
    status_code: int
    actor_user_id: str | None = None
    tenant_id: str | None = None
    actor_key_prefix: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LogoutRequest(BaseModel):
    refresh_token: str | None = None
