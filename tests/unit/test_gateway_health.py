from fastapi.testclient import TestClient

from aigateway.gateway.app import create_app
from tests.helpers import FakeAuthClient, gateway_settings, unit_chat_deps


async def _false() -> bool:
    return False


def test_health_is_ok_without_dependencies() -> None:
    app = create_app(
        gateway_settings(),
        check_postgres=_false,
        check_redis=_false,
        check_auth=_false,
        auth_client=FakeAuthClient(),
    )
    with TestClient(app) as client:
        response = client.get("/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "X-Correlation-ID" in response.headers


def test_health_echoes_correlation_id() -> None:
    app = create_app(gateway_settings(), auth_client=FakeAuthClient())
    with TestClient(app) as client:
        response = client.get("/v1/health", headers={"X-Correlation-ID": "trace-123"})
    assert response.headers["X-Correlation-ID"] == "trace-123"


def test_chat_requires_auth() -> None:
    app = create_app(gateway_settings(), auth_client=FakeAuthClient())
    with TestClient(app) as client:
        response = client.post("/v1/chat", json={"message": "hello"})
    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


def test_chat_returns_stub_when_authenticated() -> None:
    client_auth = FakeAuthClient()
    app = create_app(gateway_settings(), **unit_chat_deps(auth_client=client_auth))
    with TestClient(app) as client:
        response = client.post(
            "/v1/chat",
            json={"message": "hello"},
            headers={"Authorization": "Bearer test"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["answer"].startswith("Stub:")
    assert body["conversation_id"]
    assert "correlation_id" not in body
    assert client_auth.audits
    assert client_auth.audits[-1]["action"] == "chat.attempt"
    assert client_auth.audits[-1]["status_code"] == 200


def test_chat_validates_body_when_authenticated() -> None:
    app = create_app(gateway_settings(), **unit_chat_deps())
    with TestClient(app) as client:
        response = client.post("/v1/chat", json={}, headers={"Authorization": "Bearer test"})
    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
    assert "correlation_id" in response.json()
