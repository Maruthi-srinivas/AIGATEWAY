from __future__ import annotations

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from aigateway.contracts import (
    ApprovalNotFoundError,
    AuthenticationError,
    AuthorizationError,
    ConversationNotFoundError,
    DocumentNotFoundError,
    EvalsUnavailableError,
    GovernanceUnavailableError,
    GuardrailsUnavailableError,
    InputBlockedError,
    LlmUnavailableError,
    PayloadTooLargeError,
    RagUnavailableError,
    RateLimitedError,
    RateLimiterUnavailableError,
    ValidationFailedError,
)
from aigateway.telemetry import correlation_id_var


def error_body(code: str, detail: str) -> dict:
    payload: dict = {"code": code, "detail": detail}
    cid = correlation_id_var.get()
    if cid:
        payload["correlation_id"] = cid
    return payload


def json_error(
    status_code: int,
    code: str,
    detail: str,
    *,
    headers: dict[str, str] | None = None,
    extra: dict | None = None,
) -> JSONResponse:
    content = error_body(code, detail)
    if extra:
        content.update(extra)
    return JSONResponse(
        status_code=status_code,
        content=content,
        headers=headers,
    )


def rate_limit_headers(exc: RateLimitedError) -> dict[str, str]:
    return {
        "Retry-After": str(max(1, exc.retry_after)),
        "X-RateLimit-Limit": str(exc.limit),
        "X-RateLimit-Remaining": str(exc.remaining),
        "X-RateLimit-Reset": str(exc.reset_at),
    }


def register_exception_handlers(app) -> None:
    @app.exception_handler(ApprovalNotFoundError)
    async def _approval_missing(_, exc: ApprovalNotFoundError) -> JSONResponse:
        return json_error(exc.status_code, exc.code, exc.detail)

    @app.exception_handler(AuthenticationError)
    async def _unauthenticated(_, exc: AuthenticationError) -> JSONResponse:
        return json_error(exc.status_code, exc.code, exc.detail)

    @app.exception_handler(AuthorizationError)
    async def _forbidden(_, exc: AuthorizationError) -> JSONResponse:
        return json_error(exc.status_code, exc.code, exc.detail)

    @app.exception_handler(ValidationFailedError)
    async def _validation(_, exc: ValidationFailedError) -> JSONResponse:
        return json_error(exc.status_code, exc.code, exc.detail)

    @app.exception_handler(PayloadTooLargeError)
    async def _too_large(_, exc: PayloadTooLargeError) -> JSONResponse:
        return json_error(exc.status_code, exc.code, exc.detail)

    @app.exception_handler(ConversationNotFoundError)
    async def _not_found(_, exc: ConversationNotFoundError) -> JSONResponse:
        return json_error(exc.status_code, exc.code, exc.detail)

    @app.exception_handler(DocumentNotFoundError)
    async def _doc_not_found(_, exc: DocumentNotFoundError) -> JSONResponse:
        return json_error(exc.status_code, exc.code, exc.detail)

    @app.exception_handler(RateLimitedError)
    async def _rate_limited(_, exc: RateLimitedError) -> JSONResponse:
        return json_error(
            exc.status_code,
            exc.code,
            exc.detail,
            headers=rate_limit_headers(exc),
        )

    @app.exception_handler(RateLimiterUnavailableError)
    async def _rl_down(_, exc: RateLimiterUnavailableError) -> JSONResponse:
        return json_error(exc.status_code, exc.code, exc.detail)

    @app.exception_handler(InputBlockedError)
    async def _input_blocked(_, exc: InputBlockedError) -> JSONResponse:
        decisions = [
            item.model_dump() if hasattr(item, "model_dump") else item for item in exc.decisions
        ]
        return json_error(
            exc.status_code,
            exc.code,
            exc.detail,
            extra={"guardrail_decisions": decisions},
        )

    @app.exception_handler(GuardrailsUnavailableError)
    async def _guardrails_down(_, exc: GuardrailsUnavailableError) -> JSONResponse:
        return json_error(exc.status_code, exc.code, exc.detail)

    @app.exception_handler(RagUnavailableError)
    async def _rag_down(_, exc: RagUnavailableError) -> JSONResponse:
        return json_error(exc.status_code, exc.code, exc.detail)

    @app.exception_handler(LlmUnavailableError)
    async def _llm_down(_, exc: LlmUnavailableError) -> JSONResponse:
        return json_error(exc.status_code, exc.code, exc.detail)

    @app.exception_handler(GovernanceUnavailableError)
    async def _governance_down(_, exc: GovernanceUnavailableError) -> JSONResponse:
        return json_error(exc.status_code, exc.code, exc.detail)

    @app.exception_handler(EvalsUnavailableError)
    async def _evals_down(_, exc: EvalsUnavailableError) -> JSONResponse:
        return json_error(exc.status_code, exc.code, exc.detail)

    @app.exception_handler(RequestValidationError)
    async def _request_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        _ = request, exc
        return json_error(400, "validation_error", "invalid request")
