from fastapi.testclient import TestClient

from aigateway.gateway.app import create_app
from tests.helpers import FakeAuthClient, gateway_settings


def test_openapi_contains_version_5_paths() -> None:
    app = create_app(gateway_settings(), auth_client=FakeAuthClient())
    with TestClient(app) as client:
        spec = client.get("/openapi.json").json()
    paths = spec["paths"]
    assert "/v1/health" in paths
    assert "/v1/ready" in paths
    assert "/v1/metrics" in paths
    assert "/v1/evaluate" in paths
    assert "/v1/approvals/{approval_id}" in paths
    assert "/v1/governance" in paths
    assert "/v1/chat" in paths
    assert "/v1/conversations" in paths
    assert "/v1/conversations/{conversation_id}" in paths
    assert "/v1/guardrails/policy" in paths
    assert "/v1/documents" in paths
    assert "/v1/documents/{document_id}" in paths
    assert "get" in paths["/v1/guardrails/policy"]
    assert "patch" in paths["/v1/guardrails/policy"]
    assert "post" in paths["/v1/documents"]
    assert any(p.startswith("/v1/auth") for p in paths)
    assert "post" in paths["/v1/chat"]
    assert "get" in paths["/v1/conversations"]
    assert spec["info"]["version"] == "0.10.0"
    schemes = spec["components"]["securitySchemes"]
    assert "BearerAuth" in schemes
    assert "ApiKeyAuth" in schemes
    policy = spec["components"]["schemas"]["GuardrailPolicy"]["properties"]
    assert "jev_enabled" in policy
    assert "jev_injection_threshold" in policy
    chat = spec["components"]["schemas"]["ChatResponse"]["properties"]
    assert "assessments" in chat
    assert "confidence" in chat
    assert "groundedness" in chat
    assert "provider" in chat
    assert "model" in chat
    assert "approval_id" in chat
    assert "estimated_cost" not in chat
    assert "faithfulness" not in chat
