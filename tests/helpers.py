from fastapi.responses import JSONResponse
from starlette.requests import Request

from aigateway.config import GatewaySettings
from aigateway.contracts import AuthContext
from aigateway.gateway.rate_limit import AllowAllRateLimiter
from aigateway.gateway.repository import MemoryChatRepository
from aigateway.gateway.session_cache import SessionCache
from aigateway.testing import FakeAuthProvider, FakeGuardrail, FakeLLMClient, FakeRetriever

DEFAULT_USER_ID = "11111111-1111-1111-1111-111111111111"
DEFAULT_TENANT_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
OTHER_USER_ID = "22222222-2222-2222-2222-222222222222"
OTHER_TENANT_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


class FakeAuthClient:
    def __init__(self, fail: bool = False, context: AuthContext | None = None) -> None:
        self.provider = FakeAuthProvider(context=context, fail=fail)
        self.audits: list[dict] = []

    async def authenticate(self, **kwargs):
        return await self.provider.authenticate(**kwargs)

    async def write_audit(self, payload: dict) -> None:
        self.audits.append(payload)

    async def proxy(self, request: Request) -> JSONResponse:
        return JSONResponse({"proxied": request.url.path})


def gateway_settings() -> GatewaySettings:
    return GatewaySettings(
        postgres_dsn="postgresql://aigateway:aigateway@localhost:5432/aigateway",
        redis_url="redis://localhost:6379/0",
        auth_base_url="http://auth.example",
        guardrails_base_url="http://guardrails.example",
        rag_base_url="http://rag.example",
        internal_auth_token="test-internal",
        stub_stream_delay_ms=0,
    )


def unit_chat_deps(**kwargs):
    return {
        "auth_client": kwargs.get("auth_client", FakeAuthClient()),
        "rate_limiter": kwargs.get("rate_limiter", AllowAllRateLimiter()),
        "chat_repo": kwargs.get("chat_repo", MemoryChatRepository()),
        "llm_client": kwargs.get("llm_client", FakeLLMClient()),
        "guardrail_client": kwargs.get("guardrail_client", FakeGuardrail()),
        "rag_client": kwargs.get("rag_client", FakeRetriever()),
        "session_cache": kwargs.get("session_cache", SessionCache(None, ttl_seconds=60, limit=20)),
    }
