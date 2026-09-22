from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select, update

from aigateway.contracts import AuthContext
from aigateway.gateway.db import session_scope
from aigateway.gateway.models import Conversation, Message


@dataclass
class ConversationRecord:
    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    created_by_key_prefix: str | None
    title: str
    created_at: datetime
    updated_at: datetime


@dataclass
class MessageRecord:
    id: uuid.UUID
    conversation_id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID | None
    role: str
    content: str
    created_at: datetime


def _title(message: str) -> str:
    text = " ".join(message.split())
    return text[:80] if text else "conversation"


def is_owner(record: ConversationRecord, ctx: AuthContext) -> bool:
    if ctx.auth_method == "api_key" and ctx.key_prefix:
        return record.created_by_key_prefix == ctx.key_prefix
    return str(record.user_id) == ctx.user_id


def can_read(record: ConversationRecord, ctx: AuthContext, *, tenant_id: str) -> bool:
    if str(record.tenant_id) != tenant_id:
        return False
    if ctx.role in {"viewer", "platform_admin"}:
        return True
    return is_owner(record, ctx)


class ChatRepository:
    async def create_conversation(
        self,
        *,
        tenant_id: uuid.UUID,
        ctx: AuthContext,
        title: str,
    ) -> ConversationRecord: ...

    async def get_conversation(self, conversation_id: uuid.UUID) -> ConversationRecord | None: ...

    async def list_conversations(
        self,
        *,
        tenant_id: uuid.UUID,
        ctx: AuthContext,
        limit: int,
        offset: int,
    ) -> list[ConversationRecord]: ...

    async def add_message(
        self,
        *,
        conversation_id: uuid.UUID,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID | None,
        role: str,
        content: str,
    ) -> MessageRecord: ...

    async def list_messages(
        self,
        conversation_id: uuid.UUID,
        *,
        limit: int | None = None,
    ) -> list[MessageRecord]: ...

    async def touch(self, conversation_id: uuid.UUID) -> None: ...


class SqlChatRepository(ChatRepository):
    def __init__(self, session_factory=session_scope) -> None:
        self._session_factory = session_factory

    async def create_conversation(
        self,
        *,
        tenant_id: uuid.UUID,
        ctx: AuthContext,
        title: str,
    ) -> ConversationRecord:
        async with self._session_factory() as session:
            row = Conversation(
                tenant_id=tenant_id,
                user_id=uuid.UUID(ctx.user_id),
                created_by_key_prefix=ctx.key_prefix if ctx.auth_method == "api_key" else None,
                title=_title(title),
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return _conv(row)

    async def get_conversation(self, conversation_id: uuid.UUID) -> ConversationRecord | None:
        async with self._session_factory() as session:
            row = await session.get(Conversation, conversation_id)
            return _conv(row) if row else None

    async def list_conversations(
        self,
        *,
        tenant_id: uuid.UUID,
        ctx: AuthContext,
        limit: int,
        offset: int,
    ) -> list[ConversationRecord]:
        async with self._session_factory() as session:
            stmt = (
                select(Conversation)
                .where(Conversation.tenant_id == tenant_id)
                .order_by(Conversation.updated_at.desc())
                .offset(offset)
                .limit(limit)
            )
            stmt = _scope_list(stmt, ctx)
            result = await session.execute(stmt)
            return [_conv(row) for row in result.scalars().all()]

    async def add_message(
        self,
        *,
        conversation_id: uuid.UUID,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID | None,
        role: str,
        content: str,
    ) -> MessageRecord:
        async with self._session_factory() as session:
            row = Message(
                conversation_id=conversation_id,
                tenant_id=tenant_id,
                user_id=user_id,
                role=role,
                content=content,
            )
            session.add(row)
            await session.execute(
                update(Conversation)
                .where(Conversation.id == conversation_id)
                .values(updated_at=datetime.now(UTC))
            )
            await session.commit()
            await session.refresh(row)
            return _msg(row)

    async def list_messages(
        self,
        conversation_id: uuid.UUID,
        *,
        limit: int | None = None,
    ) -> list[MessageRecord]:
        async with self._session_factory() as session:
            if limit is None:
                stmt = (
                    select(Message)
                    .where(Message.conversation_id == conversation_id)
                    .order_by(Message.created_at.asc())
                )
                result = await session.execute(stmt)
                return [_msg(row) for row in result.scalars().all()]
            stmt = (
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            rows = [_msg(row) for row in result.scalars().all()]
            rows.reverse()
            return rows

    async def touch(self, conversation_id: uuid.UUID) -> None:
        async with self._session_factory() as session:
            await session.execute(
                update(Conversation)
                .where(Conversation.id == conversation_id)
                .values(updated_at=datetime.now(UTC))
            )
            await session.commit()


@dataclass
class MemoryChatRepository(ChatRepository):
    conversations: dict[uuid.UUID, ConversationRecord] = field(default_factory=dict)
    messages: dict[uuid.UUID, list[MessageRecord]] = field(default_factory=dict)

    async def create_conversation(
        self,
        *,
        tenant_id: uuid.UUID,
        ctx: AuthContext,
        title: str,
    ) -> ConversationRecord:
        now = datetime.now(UTC)
        record = ConversationRecord(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=uuid.UUID(ctx.user_id),
            created_by_key_prefix=ctx.key_prefix if ctx.auth_method == "api_key" else None,
            title=_title(title),
            created_at=now,
            updated_at=now,
        )
        self.conversations[record.id] = record
        self.messages[record.id] = []
        return record

    async def get_conversation(self, conversation_id: uuid.UUID) -> ConversationRecord | None:
        return self.conversations.get(conversation_id)

    async def list_conversations(
        self,
        *,
        tenant_id: uuid.UUID,
        ctx: AuthContext,
        limit: int,
        offset: int,
    ) -> list[ConversationRecord]:
        rows = [row for row in self.conversations.values() if row.tenant_id == tenant_id]
        if ctx.role not in {"viewer", "platform_admin"}:
            if ctx.auth_method == "api_key" and ctx.key_prefix:
                rows = [row for row in rows if row.created_by_key_prefix == ctx.key_prefix]
            else:
                rows = [row for row in rows if str(row.user_id) == ctx.user_id]
        rows.sort(key=lambda row: row.updated_at, reverse=True)
        return rows[offset : offset + limit]

    async def add_message(
        self,
        *,
        conversation_id: uuid.UUID,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID | None,
        role: str,
        content: str,
    ) -> MessageRecord:
        now = datetime.now(UTC)
        record = MessageRecord(
            id=uuid.uuid4(),
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            user_id=user_id,
            role=role,
            content=content,
            created_at=now,
        )
        self.messages.setdefault(conversation_id, []).append(record)
        conv = self.conversations[conversation_id]
        self.conversations[conversation_id] = ConversationRecord(
            id=conv.id,
            tenant_id=conv.tenant_id,
            user_id=conv.user_id,
            created_by_key_prefix=conv.created_by_key_prefix,
            title=conv.title,
            created_at=conv.created_at,
            updated_at=now,
        )
        return record

    async def list_messages(
        self,
        conversation_id: uuid.UUID,
        *,
        limit: int | None = None,
    ) -> list[MessageRecord]:
        rows = list(self.messages.get(conversation_id, []))
        if limit is not None:
            return rows[-limit:]
        return rows

    async def touch(self, conversation_id: uuid.UUID) -> None:
        conv = self.conversations[conversation_id]
        self.conversations[conversation_id] = ConversationRecord(
            id=conv.id,
            tenant_id=conv.tenant_id,
            user_id=conv.user_id,
            created_by_key_prefix=conv.created_by_key_prefix,
            title=conv.title,
            created_at=conv.created_at,
            updated_at=datetime.now(UTC),
        )


def _conv(row: Conversation) -> ConversationRecord:
    return ConversationRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        user_id=row.user_id,
        created_by_key_prefix=row.created_by_key_prefix,
        title=row.title,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _msg(row: Message) -> MessageRecord:
    return MessageRecord(
        id=row.id,
        conversation_id=row.conversation_id,
        tenant_id=row.tenant_id,
        user_id=row.user_id,
        role=row.role,
        content=row.content,
        created_at=row.created_at,
    )


def _scope_list(stmt, ctx: AuthContext):
    if ctx.role in {"viewer", "platform_admin"}:
        return stmt
    if ctx.auth_method == "api_key" and ctx.key_prefix:
        return stmt.where(Conversation.created_by_key_prefix == ctx.key_prefix)
    return stmt.where(Conversation.user_id == uuid.UUID(ctx.user_id))
