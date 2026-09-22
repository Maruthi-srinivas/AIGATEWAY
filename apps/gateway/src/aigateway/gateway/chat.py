from __future__ import annotations

import asyncio
import hashlib
import uuid
from collections.abc import AsyncIterator

from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse

from aigateway.contracts import (
    AuthContext,
    AuthorizationError,
    ChatRequest,
    ChatResponse,
    ConversationDetail,
    ConversationList,
    ConversationNotFoundError,
    ConversationSummary,
    GuardrailCheckResult,
    GuardrailDecision,
    GuardrailsUnavailableError,
    GuardrailText,
    InputBlockedError,
    JevAssessment,
    MessageOut,
    RateLimitedError,
    RateLimiterUnavailableError,
    ValidationFailedError,
)
from aigateway.gateway.deps import effective_tenant_id, require_auth, require_chat_role
from aigateway.gateway.rate_limit import RateLimitResult
from aigateway.gateway.repository import (
    ConversationRecord,
    MessageRecord,
    can_read,
    is_owner,
)
from aigateway.gateway.sse import sse_event, with_heartbeat
from aigateway.telemetry import correlation_id_var, get_logger

logger = get_logger(__name__)

CHAT_ROLES_READ = {"app_user", "service_account", "security_admin", "platform_admin", "viewer"}
OUTPUT_REFUSAL = "The assistant response was blocked by output guardrails."


def _output_confidence(assessments: list[JevAssessment]) -> float | None:
    for item in assessments:
        if item.stage == "output" and item.question_id == "safety" and item.score is not None:
            return item.score
    return None


def _merge_checks(
    inbound: GuardrailCheckResult,
    outbound: GuardrailCheckResult,
    raw_answer: str,
) -> tuple[str, list[GuardrailDecision], list[JevAssessment], float | None]:
    answer = OUTPUT_REFUSAL if outbound.decision == "block" else raw_answer
    decisions = [*inbound.decisions, *outbound.decisions]
    assessments = [*inbound.assessments, *outbound.assessments]
    return answer, decisions, assessments, _output_confidence(assessments)


async def _tokens_from_text(text: str, delay_ms: float) -> AsyncIterator[str]:
    words = text.split()
    if not words:
        return
    for index, word in enumerate(words):
        if delay_ms:
            await asyncio.sleep(delay_ms / 1000)
        chunk = word if index == len(words) - 1 else f"{word} "
        yield sse_event("token", {"text": chunk})


async def audit_chat(
    request: Request,
    ctx: AuthContext | None,
    *,
    status_code: int,
    success: bool,
    metadata: dict | None = None,
) -> None:
    payload = {
        "action": "chat.attempt",
        "resource": "/v1/chat",
        "success": success,
        "status_code": status_code,
        "actor_user_id": ctx.user_id if ctx else None,
        "tenant_id": ctx.tenant_id if ctx else None,
        "actor_key_prefix": ctx.key_prefix if ctx else None,
        "metadata": metadata or {},
    }
    await request.app.state.auth_client.write_audit(payload)


async def consume_limit(request: Request, ctx: AuthContext, tenant_id: str) -> RateLimitResult:
    await request.app.state.ensure_runtime()
    try:
        return await request.app.state.rate_limiter.consume(ctx, tenant_id=tenant_id)
    except RateLimitedError:
        raise
    except RateLimiterUnavailableError:
        raise


def _summary(row: ConversationRecord) -> ConversationSummary:
    return ConversationSummary(
        id=str(row.id),
        tenant_id=str(row.tenant_id),
        user_id=str(row.user_id),
        title=row.title,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _message_out(row: MessageRecord) -> MessageOut:
    return MessageOut(
        id=str(row.id),
        role=row.role,
        content=row.content,
        created_at=row.created_at,
        user_id=str(row.user_id) if row.user_id else None,
    )


async def resolve_write_conversation(
    request: Request,
    ctx: AuthContext,
    *,
    tenant_id: str,
    conversation_id: str | None,
    title: str,
) -> ConversationRecord:
    repo = request.app.state.chat_repo
    if conversation_id is None:
        return await repo.create_conversation(
            tenant_id=uuid.UUID(tenant_id),
            ctx=ctx,
            title=title,
        )
    record = await repo.get_conversation(uuid.UUID(conversation_id))
    if record is None:
        raise ConversationNotFoundError()
    if str(record.tenant_id) != tenant_id:
        raise AuthorizationError("cross-tenant access is forbidden")
    if not is_owner(record, ctx):
        raise AuthorizationError("conversation access is forbidden")
    return record


async def handle_chat(request: Request, body: ChatRequest) -> JSONResponse | StreamingResponse:
    ctx = await require_auth(request)
    settings = request.app.state.settings
    if len(body.message) > settings.chat_message_max_chars:
        await audit_chat(request, ctx, status_code=400, success=False)
        raise ValidationFailedError("message too long")
    try:
        tenant_id = effective_tenant_id(ctx, body.tenant_id)
        require_chat_role(ctx)
    except AuthorizationError:
        await audit_chat(
            request,
            ctx,
            status_code=403,
            success=False,
            metadata={"conversation_id": body.conversation_id},
        )
        raise
    try:
        limit = await consume_limit(request, ctx, tenant_id)
    except RateLimitedError as exc:
        await audit_chat(request, ctx, status_code=429, success=False)
        raise exc
    except RateLimiterUnavailableError as exc:
        await audit_chat(request, ctx, status_code=503, success=False)
        raise exc

    conversation: ConversationRecord | None = None
    history_rows: list[MessageRecord] = []
    if body.conversation_id:
        try:
            conversation = await resolve_write_conversation(
                request,
                ctx,
                tenant_id=tenant_id,
                conversation_id=body.conversation_id,
                title=body.message,
            )
        except ConversationNotFoundError:
            await audit_chat(
                request,
                ctx,
                status_code=404,
                success=False,
                metadata={"conversation_id": body.conversation_id},
            )
            raise
        except AuthorizationError:
            await audit_chat(
                request,
                ctx,
                status_code=403,
                success=False,
                metadata={"conversation_id": body.conversation_id},
            )
            raise
        history_rows = await request.app.state.chat_repo.list_messages(
            conversation.id,
            limit=request.app.state.settings.session_cache_message_limit,
        )

    texts = [GuardrailText(role=row.role, content=row.content) for row in history_rows]
    texts.append(GuardrailText(role="user", content=body.message))
    try:
        check = await request.app.state.guardrail_client.check_input(
            tenant_id=tenant_id,
            texts=texts,
        )
    except GuardrailsUnavailableError as exc:
        await audit_chat(request, ctx, status_code=503, success=False)
        raise exc

    if check.decision == "block":
        digest = hashlib.sha256(body.message.encode("utf-8")).hexdigest()
        await request.app.state.auth_client.write_audit(
            {
                "action": "guardrail.input",
                "resource": "/v1/chat",
                "success": False,
                "status_code": 400,
                "actor_user_id": ctx.user_id,
                "tenant_id": tenant_id,
                "actor_key_prefix": ctx.key_prefix,
                "metadata": {
                    "prompt_sha256": digest,
                    "conversation_id": body.conversation_id,
                    "decisions": [item.model_dump() for item in check.decisions],
                },
            }
        )
        raise InputBlockedError(decisions=check.decisions)

    masked_user = check.texts[-1].content if check.texts else body.message
    if conversation is None:
        conversation = await request.app.state.chat_repo.create_conversation(
            tenant_id=uuid.UUID(tenant_id),
            ctx=ctx,
            title=masked_user,
        )
    user_message = await request.app.state.chat_repo.add_message(
        conversation_id=conversation.id,
        tenant_id=uuid.UUID(tenant_id),
        user_id=uuid.UUID(ctx.user_id),
        role="user",
        content=masked_user,
    )
    history = [{"role": item.role, "content": item.content} for item in check.texts]
    cid = correlation_id_var.get()
    raw_answer = await request.app.state.llm_client.generate(history)
    try:
        outbound = await request.app.state.guardrail_client.check_output(
            tenant_id=tenant_id,
            texts=[GuardrailText(role="assistant", content=raw_answer)],
        )
    except GuardrailsUnavailableError as exc:
        await audit_chat(request, ctx, status_code=503, success=False)
        raise exc
    answer, decisions, assessments, confidence = _merge_checks(check, outbound, raw_answer)
    assistant = await request.app.state.chat_repo.add_message(
        conversation_id=conversation.id,
        tenant_id=uuid.UUID(tenant_id),
        user_id=None,
        role="assistant",
        content=answer,
    )
    await request.app.state.session_cache.set(
        tenant_id,
        str(conversation.id),
        [*history, {"role": "assistant", "content": answer}],
    )
    await audit_chat(
        request,
        ctx,
        status_code=200,
        success=True,
        metadata={
            "conversation_id": str(conversation.id),
            "output_blocked": outbound.decision == "block",
        },
    )
    payload = ChatResponse(
        answer=answer,
        citations=[],
        confidence=confidence,
        trace_id=cid,
        conversation_id=str(conversation.id),
        message_id=str(assistant.id),
        guardrail_decisions=decisions,
        assessments=assessments,
    )
    if body.stream:
        return StreamingResponse(
            _stream_answer(
                request,
                conversation=conversation,
                user_message=user_message,
                answer=answer,
                payload=payload,
                correlation_id=cid,
            ),
            media_type="text/event-stream",
            headers=limit.headers(),
        )
    return JSONResponse(payload.model_dump(), headers=limit.headers())


async def _stream_answer(
    request: Request,
    *,
    conversation: ConversationRecord,
    user_message: MessageRecord,
    answer: str,
    payload: ChatResponse,
    correlation_id: str | None,
) -> AsyncIterator[str]:
    yield sse_event(
        "meta",
        {
            "conversation_id": str(conversation.id),
            "message_id": str(user_message.id),
            "correlation_id": correlation_id,
        },
    )

    async def tokens() -> AsyncIterator[str]:
        delay = request.app.state.settings.stub_stream_delay_ms
        async for event in _tokens_from_text(answer, delay):
            yield event

    try:
        async for chunk in with_heartbeat(tokens()):
            yield chunk
        yield sse_event("done", payload.model_dump())
    except GeneratorExit:
        logger.info("chat stream disconnected conversation_id=%s", conversation.id)
        return


async def handle_list_conversations(
    request: Request,
    *,
    tenant_id: str | None,
    limit: int,
    offset: int,
) -> ConversationList:
    ctx = await require_auth(request)
    if ctx.role not in CHAT_ROLES_READ:
        raise AuthorizationError()
    if tenant_id:
        try:
            uuid.UUID(tenant_id)
        except ValueError as exc:
            raise ValidationFailedError("invalid tenant id") from exc
    try:
        effective = effective_tenant_id(ctx, tenant_id)
    except AuthorizationError:
        await request.app.state.auth_client.write_audit(
            {
                "action": "conversation.list",
                "resource": "/v1/conversations",
                "success": False,
                "status_code": 403,
                "actor_user_id": ctx.user_id,
                "tenant_id": ctx.tenant_id,
                "actor_key_prefix": ctx.key_prefix,
            }
        )
        raise
    try:
        await consume_limit(request, ctx, effective)
    except RateLimitedError:
        raise
    except RateLimiterUnavailableError:
        raise
    rows = await request.app.state.chat_repo.list_conversations(
        tenant_id=uuid.UUID(effective),
        ctx=ctx,
        limit=limit,
        offset=offset,
    )
    return ConversationList(items=[_summary(row) for row in rows], offset=offset, limit=limit)


async def handle_get_conversation(request: Request, conversation_id: str) -> ConversationDetail:
    ctx = await require_auth(request)
    if ctx.role not in CHAT_ROLES_READ:
        raise AuthorizationError()
    try:
        uuid.UUID(conversation_id)
    except ValueError as exc:
        raise ValidationFailedError("invalid conversation id") from exc
    requested_tenant = request.query_params.get("tenant_id")
    if requested_tenant:
        try:
            uuid.UUID(requested_tenant)
        except ValueError as exc:
            raise ValidationFailedError("invalid tenant id") from exc
    tenant_id = effective_tenant_id(ctx, requested_tenant)
    try:
        await consume_limit(request, ctx, tenant_id)
    except (RateLimitedError, RateLimiterUnavailableError):
        raise
    record = await request.app.state.chat_repo.get_conversation(uuid.UUID(conversation_id))
    if record is None:
        await request.app.state.auth_client.write_audit(
            {
                "action": "conversation.read",
                "resource": f"/v1/conversations/{conversation_id}",
                "success": False,
                "status_code": 404,
                "actor_user_id": ctx.user_id,
                "tenant_id": ctx.tenant_id,
                "actor_key_prefix": ctx.key_prefix,
            }
        )
        raise ConversationNotFoundError()
    if not can_read(record, ctx, tenant_id=tenant_id):
        await request.app.state.auth_client.write_audit(
            {
                "action": "conversation.read",
                "resource": f"/v1/conversations/{conversation_id}",
                "success": False,
                "status_code": 403,
                "actor_user_id": ctx.user_id,
                "tenant_id": ctx.tenant_id,
                "actor_key_prefix": ctx.key_prefix,
            }
        )
        raise AuthorizationError("conversation access is forbidden")
    messages = await request.app.state.chat_repo.list_messages(record.id)
    return ConversationDetail(
        **_summary(record).model_dump(),
        messages=[_message_out(row) for row in messages],
    )
