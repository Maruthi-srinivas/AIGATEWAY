from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from collections.abc import AsyncIterator

from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse

from aigateway.contracts import (
    AuthContext,
    AuthorizationError,
    ChatEvent,
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
    LlmUnavailableError,
    MessageOut,
    RagUnavailableError,
    RateLimitedError,
    RateLimiterUnavailableError,
    ValidationFailedError,
)
from aigateway.gateway.classify import is_chitchat
from aigateway.gateway.deps import effective_tenant_id, require_auth, require_chat_role
from aigateway.gateway.grounding import (
    I_DONT_KNOW,
    grounded_messages,
    mask_secrets,
    verify_answer,
)
from aigateway.gateway.rate_limit import RateLimitResult
from aigateway.gateway.repository import (
    ConversationRecord,
    MessageRecord,
    can_read,
    is_owner,
)
from aigateway.gateway.sse import sse_event, with_heartbeat
from aigateway.telemetry import correlation_id_var, get_logger, span

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
    *,
    groundedness: float | None,
    dropped: int,
) -> tuple[str, list[GuardrailDecision], list[JevAssessment], float | None]:
    blocked = outbound.decision == "block"
    answer = OUTPUT_REFUSAL if blocked else raw_answer
    decisions = [*inbound.decisions, *outbound.decisions]
    if dropped > 0:
        decisions.append(
            GuardrailDecision(
                decision="redact",
                rule_id="citation_unverified",
                score=groundedness,
                reason=f"dropped={dropped}",
            )
        )
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
    await _emit_chat_result(request, ctx, status_code=status_code)


def _security_rule_ids(decisions: list[GuardrailDecision], secret_redacted: bool) -> list[str]:
    rules = [item.rule_id for item in decisions if item.decision in {"block", "redact"}]
    if secret_redacted and "pii" not in rules:
        rules.append("pii")
    return rules


def _chat_event(
    request: Request,
    ctx: AuthContext | None,
    *,
    topic: str,
    status_code: int | None,
    metrics: dict,
) -> ChatEvent:
    started = getattr(request.state, "chat_started", None)
    latency_ms = None
    if started is not None and status_code is not None:
        latency_ms = (time.perf_counter() - started) * 1000
    return ChatEvent(
        event_id=str(uuid.uuid4()),
        correlation_id=correlation_id_var.get(),
        tenant_id=ctx.tenant_id if ctx else None,
        user_id=ctx.user_id if ctx else None,
        topic=topic,
        status_code=status_code,
        latency_ms=latency_ms,
        rule_ids=list(metrics.get("rule_ids") or []),
        citation_count=metrics.get("citation_count"),
        groundedness=metrics.get("groundedness"),
    )


async def _publish_event(request: Request, event: ChatEvent) -> None:
    publisher = getattr(request.app.state, "event_publisher", None)
    if publisher is None:
        return
    try:
        await publisher.publish(event)
    except Exception:
        logger.warning("kafka publish failed topic=%s", event.topic)


async def _emit_chat_result(
    request: Request,
    ctx: AuthContext | None,
    *,
    status_code: int,
) -> None:
    metrics = getattr(request.state, "chat_metrics", None) or {}
    await _publish_event(
        request,
        _chat_event(request, ctx, topic="ai.responses", status_code=status_code, metrics=metrics),
    )
    if metrics.get("rule_ids"):
        await _publish_event(
            request,
            _chat_event(
                request,
                ctx,
                topic="ai.security",
                status_code=status_code,
                metrics=metrics,
            ),
        )


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
    with span("auth"):
        ctx = await require_auth(request)
    request.state.chat_started = time.perf_counter()
    await _publish_event(
        request,
        _chat_event(request, ctx, topic="ai.requests", status_code=None, metrics={}),
    )
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
    if body.debug and ctx.role not in {"security_admin", "platform_admin"}:
        await audit_chat(request, ctx, status_code=403, success=False)
        raise AuthorizationError("retrieval debug is forbidden")
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
    cached = None
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
        history_rows = []
        cached = await request.app.state.session_cache.get(tenant_id, str(conversation.id))
        if not cached:
            history_rows = await request.app.state.chat_repo.list_messages(
                conversation.id,
                limit=request.app.state.settings.session_cache_message_limit,
            )

    if cached:
        texts = [GuardrailText(role=item["role"], content=item["content"]) for item in cached]
    else:
        texts = [GuardrailText(role=row.role, content=row.content) for row in history_rows]
    texts.append(GuardrailText(role="user", content=body.message))
    try:
        with span("guardrails"):
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
        request.state.chat_metrics = {
            "rule_ids": [
                item.rule_id for item in check.decisions if item.decision in {"block", "redact"}
            ],
            "citation_count": 0,
            "groundedness": None,
        }
        await _emit_chat_result(request, ctx, status_code=400)
        request.state.metrics_outcome = "blocked"
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
    citations = []
    retrieval_debug = None
    groundedness = None
    unsupported_count = 0
    secret_redacted = False
    llm_messages = history
    if is_chitchat(masked_user):
        generated = await _generate(request, ctx, llm_messages)
        raw_answer = mask_secrets(generated)
        secret_redacted = raw_answer != generated
    else:
        try:
            with span("retrieve"):
                retrieved = await request.app.state.rag_client.retrieve(
                    tenant_id=tenant_id,
                    query=masked_user,
                    role=ctx.role,
                    debug=body.debug,
                )
        except RagUnavailableError as exc:
            await audit_chat(request, ctx, status_code=503, success=False)
            raise exc
        retrieval_debug = retrieved.debug
        if not retrieved.chunks:
            raw_answer = mask_secrets(I_DONT_KNOW)
        else:
            llm_messages, _ = grounded_messages(history, retrieved.chunks)
            generated = await _generate(request, ctx, llm_messages)
            with span("citation"):
                (
                    raw_answer,
                    citations,
                    groundedness,
                    unsupported_count,
                    secret_redacted,
                ) = verify_answer(generated, retrieved.chunks)
    try:
        with span("guardrails"):
            outbound = await request.app.state.guardrail_client.check_output(
                tenant_id=tenant_id,
                texts=[GuardrailText(role="assistant", content=raw_answer)],
            )
    except GuardrailsUnavailableError as exc:
        await audit_chat(request, ctx, status_code=503, success=False)
        raise exc
    answer, decisions, assessments, confidence = _merge_checks(
        check,
        outbound,
        raw_answer,
        groundedness=groundedness,
        dropped=unsupported_count,
    )
    if outbound.decision == "block":
        citations = []
        request.state.metrics_outcome = "blocked"
    elif secret_redacted or unsupported_count:
        request.state.metrics_outcome = "redacted"
    else:
        request.state.metrics_outcome = "allowed"
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
    request.state.chat_metrics = {
        "rule_ids": _security_rule_ids(decisions, secret_redacted),
        "citation_count": len(citations),
        "groundedness": groundedness,
    }
    await audit_chat(
        request,
        ctx,
        status_code=200,
        success=True,
        metadata={
            "conversation_id": str(conversation.id),
            "output_blocked": outbound.decision == "block",
            "groundedness": groundedness,
            "unsupported_count": unsupported_count,
        },
    )
    payload = ChatResponse(
        answer=answer,
        citations=citations,
        confidence=confidence,
        groundedness=groundedness,
        trace_id=cid,
        conversation_id=str(conversation.id),
        message_id=str(assistant.id),
        guardrail_decisions=decisions,
        assessments=assessments,
        retrieval_debug=retrieval_debug,
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


async def _generate(request: Request, ctx: AuthContext, messages: list[dict[str, str]]) -> str:
    try:
        with span("generate"):
            return await request.app.state.llm_client.generate(messages)
    except LlmUnavailableError as exc:
        await audit_chat(request, ctx, status_code=503, success=False)
        raise exc


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
