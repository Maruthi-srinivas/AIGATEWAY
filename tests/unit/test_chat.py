from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from aigateway.contracts import AuthContext
from aigateway.gateway.app import create_app
from aigateway.gateway.rate_limit import DeniedRateLimiter, UnavailableRateLimiter
from aigateway.gateway.repository import MemoryChatRepository
from tests.helpers import (
    DEFAULT_TENANT_ID,
    DEFAULT_USER_ID,
    OTHER_TENANT_ID,
    OTHER_USER_ID,
    FakeAuthClient,
    gateway_settings,
    unit_chat_deps,
)

AUTH = {"Authorization": "Bearer test"}


def _ctx(**kwargs) -> AuthContext:
    data = {
        "user_id": DEFAULT_USER_ID,
        "tenant_id": DEFAULT_TENANT_ID,
        "role": "app_user",
        "roles": ["app_user"],
        "auth_method": "jwt",
    }
    data.update(kwargs)
    if "roles" not in kwargs:
        data["roles"] = [data["role"]]
    return AuthContext(**data)


def _app(**kwargs):
    return create_app(gateway_settings(), **unit_chat_deps(**kwargs))


def test_viewer_cannot_chat() -> None:
    app = _app(auth_client=FakeAuthClient(context=_ctx(role="viewer")))
    with TestClient(app) as client:
        response = client.post("/v1/chat", json={"message": "hello"}, headers=AUTH)
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


def test_extra_fields_are_rejected() -> None:
    app = _app()
    with TestClient(app) as client:
        response = client.post(
            "/v1/chat",
            json={"message": "hello", "temperature": 0.2},
            headers=AUTH,
        )
    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
    assert "correlation_id" in response.json()


def test_payload_too_large() -> None:
    app = _app()
    with TestClient(app) as client:
        response = client.post(
            "/v1/chat",
            content=b"x" * 40000,
            headers={**AUTH, "Content-Type": "application/json"},
        )
    assert response.status_code == 400
    assert response.json()["code"] == "payload_too_large"


def test_continue_conversation() -> None:
    repo = MemoryChatRepository()
    app = _app(chat_repo=repo)
    with TestClient(app) as client:
        first = client.post("/v1/chat", json={"message": "hello"}, headers=AUTH)
        conv_id = first.json()["conversation_id"]
        second = client.post(
            "/v1/chat",
            json={"message": "again", "conversation_id": conv_id},
            headers=AUTH,
        )
    assert second.status_code == 200
    assert second.json()["conversation_id"] == conv_id
    assert len(repo.messages[uuid.UUID(conv_id)]) == 4


def test_unknown_conversation_is_404() -> None:
    app = _app()
    missing = str(uuid.uuid4())
    with TestClient(app) as client:
        response = client.post(
            "/v1/chat",
            json={"message": "hello", "conversation_id": missing},
            headers=AUTH,
        )
    assert response.status_code == 404
    assert response.json()["code"] == "conversation_not_found"


def test_same_tenant_non_owner_write_is_403() -> None:
    repo = MemoryChatRepository()
    owner_app = _app(chat_repo=repo)
    with TestClient(owner_app) as client:
        created = client.post("/v1/chat", json={"message": "hello"}, headers=AUTH)
    conv_id = created.json()["conversation_id"]
    other = _app(
        chat_repo=repo,
        auth_client=FakeAuthClient(context=_ctx(user_id=OTHER_USER_ID)),
    )
    with TestClient(other) as client:
        response = client.post(
            "/v1/chat",
            json={"message": "hijack", "conversation_id": conv_id},
            headers=AUTH,
        )
        listed = client.get("/v1/conversations", headers=AUTH)
        detail = client.get(f"/v1/conversations/{conv_id}", headers=AUTH)
    assert response.status_code == 403
    assert listed.json()["items"] == []
    assert detail.status_code == 403


def test_other_tenant_conversation_is_403() -> None:
    repo = MemoryChatRepository()
    owner_app = _app(chat_repo=repo)
    with TestClient(owner_app) as client:
        created = client.post("/v1/chat", json={"message": "hello"}, headers=AUTH)
    conv_id = created.json()["conversation_id"]
    outsider = _app(
        chat_repo=repo,
        auth_client=FakeAuthClient(context=_ctx(user_id=OTHER_USER_ID, tenant_id=OTHER_TENANT_ID)),
    )
    with TestClient(outsider) as client:
        response = client.post(
            "/v1/chat",
            json={"message": "hello", "conversation_id": conv_id},
            headers=AUTH,
        )
        detail = client.get(f"/v1/conversations/{conv_id}", headers=AUTH)
    assert response.status_code == 403
    assert detail.status_code == 403


def test_viewer_can_read_tenant_conversation() -> None:
    repo = MemoryChatRepository()
    owner_app = _app(chat_repo=repo)
    with TestClient(owner_app) as client:
        created = client.post("/v1/chat", json={"message": "hello"}, headers=AUTH)
    conv_id = created.json()["conversation_id"]
    viewer = _app(
        chat_repo=repo,
        auth_client=FakeAuthClient(context=_ctx(user_id=OTHER_USER_ID, role="viewer")),
    )
    with TestClient(viewer) as client:
        listed = client.get("/v1/conversations", headers=AUTH)
        detail = client.get(f"/v1/conversations/{conv_id}", headers=AUTH)
    assert listed.status_code == 200
    assert any(item["id"] == conv_id for item in listed.json()["items"])
    assert detail.status_code == 200
    assert detail.json()["messages"]


def test_non_admin_cannot_set_tenant_id() -> None:
    app = _app()
    with TestClient(app) as client:
        response = client.post(
            "/v1/chat",
            json={"message": "hello", "tenant_id": OTHER_TENANT_ID},
            headers=AUTH,
        )
    assert response.status_code == 403


def test_platform_admin_can_chat_into_other_tenant() -> None:
    admin = _ctx(role="platform_admin")
    app = _app(auth_client=FakeAuthClient(context=admin))
    with TestClient(app) as client:
        response = client.post(
            "/v1/chat",
            json={"message": "hello", "tenant_id": OTHER_TENANT_ID},
            headers=AUTH,
        )
        listed = client.get(
            "/v1/conversations",
            params={"tenant_id": OTHER_TENANT_ID},
            headers=AUTH,
        )
    assert response.status_code == 200
    assert listed.status_code == 200
    assert listed.json()["items"][0]["tenant_id"] == OTHER_TENANT_ID


def test_stream_emits_named_events() -> None:
    app = _app()
    with TestClient(app) as client:
        response = client.post(
            "/v1/chat",
            json={"message": "hello", "stream": True},
            headers=AUTH,
        )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    text = response.text
    assert "event: meta" in text
    assert "event: token" in text
    assert "event: done" in text
    assert "X-RateLimit-Limit" in response.headers


def test_rate_limited_returns_429_headers() -> None:
    app = _app(rate_limiter=DeniedRateLimiter())
    with TestClient(app) as client:
        response = client.post("/v1/chat", json={"message": "hello"}, headers=AUTH)
    assert response.status_code == 429
    assert response.json()["code"] == "rate_limited"
    assert "Retry-After" in response.headers
    assert "X-RateLimit-Limit" in response.headers


def test_redis_down_returns_503() -> None:
    app = _app(rate_limiter=UnavailableRateLimiter())
    with TestClient(app) as client:
        response = client.post("/v1/chat", json={"message": "hello"}, headers=AUTH)
    assert response.status_code == 503
    assert response.json()["code"] == "rate_limiter_unavailable"
