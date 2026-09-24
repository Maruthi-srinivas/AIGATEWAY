from fastapi.testclient import TestClient

from aigateway.config import GatewaySettings
from aigateway.gateway.app import create_app
from tests.helpers import FakeAuthClient, gateway_settings

ALLOWED = "http://localhost:5173"


def _client(settings: GatewaySettings) -> TestClient:
    app = create_app(settings, auth_client=FakeAuthClient())
    return TestClient(app)


def test_cors_allows_configured_origin() -> None:
    with _client(gateway_settings()) as client:
        response = client.get("/v1/health", headers={"Origin": ALLOWED})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED
    assert response.headers.get("access-control-allow-credentials") is None


def test_cors_preflight_allows_auth_headers() -> None:
    with _client(gateway_settings()) as client:
        response = client.options(
            "/v1/chat",
            headers={
                "Origin": ALLOWED,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type,x-api-key",
            },
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED
    allowed_headers = response.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed_headers
    assert "content-type" in allowed_headers
    assert "x-api-key" in allowed_headers


def test_cors_rejects_unlisted_origin() -> None:
    with _client(gateway_settings()) as client:
        response = client.get("/v1/health", headers={"Origin": "https://evil.example"})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_cors_rejects_every_origin_when_unset() -> None:
    settings = gateway_settings()
    settings = GatewaySettings(
        postgres_dsn=settings.postgres_dsn,
        redis_url=settings.redis_url,
        auth_base_url=settings.auth_base_url,
        guardrails_base_url=settings.guardrails_base_url,
        rag_base_url=settings.rag_base_url,
        internal_auth_token=settings.internal_auth_token,
        cors_origins="",
    )
    with _client(settings) as client:
        response = client.get("/v1/health", headers={"Origin": ALLOWED})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
