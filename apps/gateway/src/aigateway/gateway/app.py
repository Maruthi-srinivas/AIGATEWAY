from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, Response

from aigateway.config import GatewaySettings
from aigateway.contracts import (
    ChatRequest,
    ChatResponse,
    ConversationDetail,
    ConversationList,
    GuardrailPolicy,
    GuardrailPolicyUpdate,
)
from aigateway.gateway.auth_client import HttpAuthClient
from aigateway.gateway.chat import handle_chat, handle_get_conversation, handle_list_conversations
from aigateway.gateway.db import close_engine, init_engine
from aigateway.gateway.deps import require_auth
from aigateway.gateway.errors import register_exception_handlers
from aigateway.gateway.guardrail_client import HttpGuardrailClient
from aigateway.gateway.middleware import BodySizeLimitMiddleware, CorrelationIdMiddleware
from aigateway.gateway.policy import handle_get_policy, handle_patch_policy
from aigateway.gateway.rate_limit import RedisTokenBucket
from aigateway.gateway.readiness import ReadinessChecker
from aigateway.gateway.repository import SqlChatRepository
from aigateway.gateway.session_cache import SessionCache
from aigateway.gateway.stub_llm import StubLLMClient
from aigateway.telemetry import get_logger

logger = get_logger(__name__)

CheckFn = Callable[[], Awaitable[bool]]


def create_app(
    settings: GatewaySettings,
    *,
    check_postgres: CheckFn | None = None,
    check_redis: CheckFn | None = None,
    check_auth: CheckFn | None = None,
    check_guardrails: CheckFn | None = None,
    auth_client: HttpAuthClient | None = None,
    guardrail_client=None,
    rate_limiter=None,
    chat_repo=None,
    llm_client=None,
    session_cache: SessionCache | None = None,
    redis_client=None,
) -> FastAPI:
    checker = ReadinessChecker(
        settings,
        check_postgres=check_postgres,
        check_redis=check_redis,
        check_auth=check_auth,
        check_guardrails=check_guardrails,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        http_client = httpx.AsyncClient()
        app.state.http_client = http_client
        if app.state.auth_client is None:
            app.state.auth_client = HttpAuthClient(settings, http_client)
        if app.state.guardrail_client is None:
            app.state.guardrail_client = HttpGuardrailClient(settings, http_client)
        yield
        if app.state.redis is not None:
            await app.state.redis.aclose()
        await close_engine()
        await http_client.aclose()

    app = FastAPI(
        title="AI Safety Gateway",
        version="0.4.0",
        description="Docker-first middleware between applications and LLM providers.",
        lifespan=lifespan,
    )
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    register_exception_handlers(app)
    app.state.settings = settings
    app.state.checker = checker
    app.state.auth_client = auth_client
    app.state.guardrail_client = guardrail_client
    app.state.rate_limiter = rate_limiter
    app.state.chat_repo = chat_repo
    app.state.llm_client = llm_client
    app.state.session_cache = session_cache
    app.state.redis = redis_client

    async def ensure_runtime() -> None:
        if app.state.redis is None and app.state.rate_limiter is None:
            import redis.asyncio as redis

            app.state.redis = redis.from_url(settings.redis_url)
        if app.state.rate_limiter is None:
            app.state.rate_limiter = RedisTokenBucket(app.state.redis, settings)
        if app.state.chat_repo is None:
            init_engine(settings.postgres_dsn)
            app.state.chat_repo = SqlChatRepository()
        if app.state.session_cache is None:
            app.state.session_cache = SessionCache(
                app.state.redis,
                ttl_seconds=settings.session_cache_ttl_seconds,
                limit=settings.session_cache_message_limit,
            )
        if app.state.llm_client is None:
            app.state.llm_client = StubLLMClient(settings.stub_stream_delay_ms)

    app.state.ensure_runtime = ensure_runtime

    @app.get("/v1/health", tags=["ops"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/ready", tags=["ops"])
    async def ready() -> JSONResponse:
        status = await checker.check()
        body = {
            "status": "ok" if status.ok else "unready",
            "postgres": status.postgres,
            "redis": status.redis,
            "auth": status.auth,
            "guardrails": status.guardrails,
        }
        if not status.ok:
            logger.warning(
                "readiness failed postgres=%s redis=%s auth=%s guardrails=%s",
                status.postgres,
                status.redis,
                status.auth,
                status.guardrails,
            )
            return JSONResponse(status_code=503, content=body)
        return JSONResponse(status_code=200, content=body)

    @app.post(
        "/v1/chat",
        tags=["chat"],
        response_model=ChatResponse,
        responses={
            200: {"description": "Stub chat response"},
            400: {"description": "Invalid request"},
            401: {"description": "Unauthenticated"},
            403: {"description": "Forbidden"},
            404: {"description": "Conversation not found"},
            429: {"description": "Rate limited"},
            503: {"description": "Rate limiter or guardrails unavailable"},
        },
    )
    async def chat(request: Request, body: ChatRequest):
        return await handle_chat(request, body)

    @app.get("/v1/guardrails/policy", tags=["guardrails"])
    async def get_policy(request: Request, tenant_id: str | None = None) -> GuardrailPolicy:
        return await handle_get_policy(request, tenant_id)

    @app.patch("/v1/guardrails/policy", tags=["guardrails"])
    async def patch_policy(
        request: Request,
        body: GuardrailPolicyUpdate,
        tenant_id: str | None = None,
    ) -> GuardrailPolicy:
        return await handle_patch_policy(request, body, tenant_id)

    @app.get("/v1/conversations", tags=["chat"])
    async def list_conversations(
        request: Request,
        tenant_id: str | None = None,
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> ConversationList:
        return await handle_list_conversations(
            request, tenant_id=tenant_id, limit=limit, offset=offset
        )

    @app.get("/v1/conversations/{conversation_id}", tags=["chat"])
    async def get_conversation(request: Request, conversation_id: str) -> ConversationDetail:
        return await handle_get_conversation(request, conversation_id)

    async def proxy_to_auth(request: Request) -> Response:
        if request.url.path not in {"/v1/auth/login", "/v1/auth/refresh"}:
            await require_auth(request)
        return await app.state.auth_client.proxy(request)

    app.add_api_route(
        "/v1/auth/{path:path}",
        proxy_to_auth,
        methods=["GET", "POST", "PATCH", "DELETE"],
        tags=["auth"],
    )
    app.add_api_route(
        "/v1/admin/{path:path}",
        proxy_to_auth,
        methods=["GET", "POST", "PATCH", "DELETE"],
        tags=["admin"],
    )
    app.add_api_route("/v1/me", proxy_to_auth, methods=["GET"], tags=["auth"])
    app.add_api_route(
        "/v1/me/{path:path}",
        proxy_to_auth,
        methods=["GET", "POST", "DELETE"],
        tags=["auth"],
    )
    app.add_api_route("/v1/audit", proxy_to_auth, methods=["GET"], tags=["auth"])

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        components = schema.setdefault("components", {})
        schemes = components.setdefault("securitySchemes", {})
        schemes["BearerAuth"] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
        schemes["ApiKeyAuth"] = {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
        }
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
    return app
