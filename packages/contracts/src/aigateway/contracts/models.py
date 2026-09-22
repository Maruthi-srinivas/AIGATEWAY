from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AuthContext(BaseModel):
    user_id: str
    tenant_id: str
    role: str = "app_user"
    roles: list[str] = Field(default_factory=list)
    email: str | None = None
    key_prefix: str | None = None
    auth_method: Literal["jwt", "api_key"] = "jwt"


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = None
    stream: bool = False
    tenant_id: str | None = None

    @field_validator("conversation_id", "tenant_id")
    @classmethod
    def _uuid_if_present(cls, value: str | None) -> str | None:
        if value is None:
            return value
        uuid.UUID(value)
        return value


class Citation(BaseModel):
    document_id: str
    chunk_id: str


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    confidence: float | None = None
    trace_id: str | None = None
    conversation_id: str | None = None
    message_id: str | None = None


class ConversationSummary(BaseModel):
    id: str
    tenant_id: str
    user_id: str
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationList(BaseModel):
    items: list[ConversationSummary]
    offset: int
    limit: int


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime
    user_id: str | None = None


class ConversationDetail(ConversationSummary):
    messages: list[MessageOut] = Field(default_factory=list)


class GuardrailDecision(BaseModel):
    decision: Literal["allow", "redact", "block"]
    rule_id: str
    score: float | None = None
    reason: str | None = None


class RetrievedChunk(BaseModel):
    chunk_id: str
    document_id: str
    content: str
    score: float = 0.0


class EvaluationResult(BaseModel):
    faithfulness: float | None = None
    context_recall: float | None = None
    context_precision: float | None = None
    answer_correctness: float | None = None
    latency_ms: float | None = None
