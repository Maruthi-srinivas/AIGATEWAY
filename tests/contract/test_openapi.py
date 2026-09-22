from fastapi.testclient import TestClient

from aigateway.gateway.app import create_app
from tests.helpers import FakeAuthClient, gateway_settings


def test_openapi_contains_version_3_paths() -> None:
    app = create_app(gateway_settings(), auth_client=FakeAuthClient())
    with TestClient(app) as client:
        spec = client.get("/openapi.json").json()
    paths = spec["paths"]
    assert "/v1/health" in paths
    assert "/v1/ready" in paths
    assert "/v1/chat" in paths
    assert "/v1/conversations" in paths
    assert "/v1/conversations/{conversation_id}" in paths
    assert any(p.startswith("/v1/auth") for p in paths)
    assert "post" in paths["/v1/chat"]
    assert "get" in paths["/v1/conversations"]
    schemes = spec["components"]["securitySchemes"]
    assert "BearerAuth" in schemes
    assert "ApiKeyAuth" in schemes
