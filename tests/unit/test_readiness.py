from fastapi.testclient import TestClient

from aigateway.gateway.app import create_app
from tests.helpers import FakeAuthClient, gateway_settings


async def _true() -> bool:
    return True


async def _false() -> bool:
    return False


def test_ready_ok_when_dependencies_pass() -> None:
    app = create_app(
        gateway_settings(),
        check_postgres=_true,
        check_redis=_true,
        check_auth=_true,
        check_guardrails=_true,
        check_rag=_true,
        auth_client=FakeAuthClient(),
    )
    with TestClient(app) as client:
        response = client.get("/v1/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "postgres": True,
        "redis": True,
        "auth": True,
        "guardrails": True,
        "rag": True,
    }


def test_ready_503_when_redis_down() -> None:
    app = create_app(
        gateway_settings(),
        check_postgres=_true,
        check_redis=_false,
        check_auth=_true,
        check_guardrails=_true,
        check_rag=_true,
        auth_client=FakeAuthClient(),
    )
    with TestClient(app) as client:
        response = client.get("/v1/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unready"
    assert body["postgres"] is True
    assert body["redis"] is False


def test_ready_503_when_postgres_down() -> None:
    app = create_app(
        gateway_settings(),
        check_postgres=_false,
        check_redis=_true,
        check_auth=_true,
        check_guardrails=_true,
        check_rag=_true,
        auth_client=FakeAuthClient(),
    )
    with TestClient(app) as client:
        response = client.get("/v1/ready")
    assert response.status_code == 503
    assert response.json()["postgres"] is False


def test_ready_503_when_auth_down() -> None:
    app = create_app(
        gateway_settings(),
        check_postgres=_true,
        check_redis=_true,
        check_auth=_false,
        check_guardrails=_true,
        check_rag=_true,
        auth_client=FakeAuthClient(),
    )
    with TestClient(app) as client:
        response = client.get("/v1/ready")
    assert response.status_code == 503
    assert response.json()["auth"] is False


def test_ready_503_when_guardrails_down() -> None:
    app = create_app(
        gateway_settings(),
        check_postgres=_true,
        check_redis=_true,
        check_auth=_true,
        check_guardrails=_false,
        check_rag=_true,
        auth_client=FakeAuthClient(),
    )
    with TestClient(app) as client:
        response = client.get("/v1/ready")
    assert response.status_code == 503
    assert response.json()["guardrails"] is False


def test_ready_503_when_rag_down() -> None:
    app = create_app(
        gateway_settings(),
        check_postgres=_true,
        check_redis=_true,
        check_auth=_true,
        check_guardrails=_true,
        check_rag=_false,
        auth_client=FakeAuthClient(),
    )
    with TestClient(app) as client:
        response = client.get("/v1/ready")
    assert response.status_code == 503
    assert response.json()["rag"] is False
