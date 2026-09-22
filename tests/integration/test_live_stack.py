from __future__ import annotations

import os
import uuid

import httpx
import pytest

pytestmark = pytest.mark.integration

GATEWAY_URL = os.getenv("GATEWAY_URL")
WORKER_URL = os.getenv("WORKER_URL")
RAG_URL = os.getenv("RAG_URL")
GUARDRAILS_URL = os.getenv("GUARDRAILS_URL")
EVALS_URL = os.getenv("EVALS_URL")
SEED_PASSWORD = os.getenv("SEED_PASSWORD", "changeme")
SEED_HR_API_KEY = os.getenv("SEED_HR_API_KEY", "agt_demo_hr_local_docker_only_key")

skip_without_stack = pytest.mark.skipif(
    not GATEWAY_URL,
    reason="GATEWAY_URL is unset; live Compose stack is not available",
)


def _login(email: str) -> dict:
    response = httpx.post(
        f"{GATEWAY_URL}/v1/auth/login",
        json={"email": email, "password": SEED_PASSWORD},
        timeout=10.0,
    )
    assert response.status_code == 200, response.text
    return response.json()


@skip_without_stack
def test_live_gateway_health() -> None:
    response = httpx.get(f"{GATEWAY_URL}/v1/health", timeout=5.0)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@skip_without_stack
def test_live_gateway_ready() -> None:
    response = httpx.get(f"{GATEWAY_URL}/v1/ready", timeout=5.0)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["postgres"] is True
    assert body["redis"] is True
    assert body["auth"] is True


@skip_without_stack
def test_live_chat_unauthenticated() -> None:
    response = httpx.post(f"{GATEWAY_URL}/v1/chat", json={"message": "hello"}, timeout=5.0)
    assert response.status_code == 401


@skip_without_stack
def test_live_chat_authenticated_stub() -> None:
    tokens = _login("user@hr.local")
    response = httpx.post(
        f"{GATEWAY_URL}/v1/chat",
        json={"message": "hello"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        timeout=5.0,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["answer"].startswith("Stub:")
    assert body["conversation_id"]
    listed = httpx.get(
        f"{GATEWAY_URL}/v1/conversations",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        timeout=5.0,
    )
    assert listed.status_code == 200
    assert any(item["id"] == body["conversation_id"] for item in listed.json()["items"])


@skip_without_stack
def test_live_bad_password_is_401() -> None:
    response = httpx.post(
        f"{GATEWAY_URL}/v1/auth/login",
        json={"email": "user@hr.local", "password": "wrong-password"},
        timeout=5.0,
    )
    assert response.status_code == 401


@skip_without_stack
def test_live_refresh_rotation() -> None:
    tokens = _login("user@hr.local")
    first = httpx.post(
        f"{GATEWAY_URL}/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
        timeout=5.0,
    )
    assert first.status_code == 200
    reused = httpx.post(
        f"{GATEWAY_URL}/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
        timeout=5.0,
    )
    assert reused.status_code == 401


@skip_without_stack
def test_live_tenant_isolation_on_audit() -> None:
    hr = _login("user@hr.local")
    eng = _login("user@eng.local")
    eng_tenant = eng["user"]["tenant_id"]
    response = httpx.get(
        f"{GATEWAY_URL}/v1/audit",
        params={"tenant_id": eng_tenant},
        headers={"Authorization": f"Bearer {hr['access_token']}"},
        timeout=5.0,
    )
    assert response.status_code == 403


@skip_without_stack
def test_live_viewer_cannot_create_users() -> None:
    tokens = _login("view@eng.local")
    eng_tenant = tokens["user"]["tenant_id"]
    response = httpx.post(
        f"{GATEWAY_URL}/v1/admin/users",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={
            "email": "new@eng.local",
            "password": "password1",
            "role": "app_user",
            "tenant_id": eng_tenant,
        },
        timeout=5.0,
    )
    assert response.status_code == 403


@skip_without_stack
def test_live_platform_admin_creates_tenant() -> None:
    tokens = _login("admin@platform.local")
    slug = f"demo-{uuid.uuid4().hex[:8]}"
    response = httpx.post(
        f"{GATEWAY_URL}/v1/admin/tenants",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"slug": slug, "name": "Demo Created"},
        timeout=5.0,
    )
    assert response.status_code == 200
    tenant_id = response.json()["id"]
    user = httpx.post(
        f"{GATEWAY_URL}/v1/admin/users",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={
            "email": f"created-{uuid.uuid4().hex[:8]}@demo.local",
            "password": "password1",
            "role": "app_user",
            "tenant_id": tenant_id,
        },
        timeout=5.0,
    )
    assert user.status_code == 200


@skip_without_stack
def test_live_api_key_auth() -> None:
    response = httpx.post(
        f"{GATEWAY_URL}/v1/chat",
        json={"message": "hello"},
        headers={"X-API-Key": SEED_HR_API_KEY},
        timeout=5.0,
    )
    assert response.status_code == 200
    me = httpx.get(
        f"{GATEWAY_URL}/v1/me",
        headers={"X-API-Key": SEED_HR_API_KEY},
        timeout=5.0,
    )
    assert me.status_code == 200
    assert me.json()["role"] == "service_account"


@skip_without_stack
def test_live_viewer_cannot_chat() -> None:
    tokens = _login("view@eng.local")
    response = httpx.post(
        f"{GATEWAY_URL}/v1/chat",
        json={"message": "hello"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        timeout=5.0,
    )
    assert response.status_code == 403


@skip_without_stack
def test_live_tenant_isolation_on_conversations() -> None:
    hr = _login("user@hr.local")
    eng = _login("user@eng.local")
    created = httpx.post(
        f"{GATEWAY_URL}/v1/chat",
        json={"message": "secret-hr"},
        headers={"Authorization": f"Bearer {hr['access_token']}"},
        timeout=5.0,
    )
    assert created.status_code == 200
    conv_id = created.json()["conversation_id"]
    leaked = httpx.get(
        f"{GATEWAY_URL}/v1/conversations/{conv_id}",
        headers={"Authorization": f"Bearer {eng['access_token']}"},
        timeout=5.0,
    )
    assert leaked.status_code == 403


@skip_without_stack
def test_live_chat_stream() -> None:
    tokens = _login("user@hr.local")
    response = httpx.post(
        f"{GATEWAY_URL}/v1/chat",
        json={"message": "stream please", "stream": True},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        timeout=10.0,
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert "event: meta" in response.text
    assert "event: done" in response.text


@skip_without_stack
def test_live_chat_rejects_unknown_fields() -> None:
    tokens = _login("user@hr.local")
    response = httpx.post(
        f"{GATEWAY_URL}/v1/chat",
        json={"message": "hello", "model": "gpt"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        timeout=5.0,
    )
    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"


@pytest.mark.skipif(not WORKER_URL, reason="WORKER_URL is unset")
def test_live_worker_health() -> None:
    response = httpx.get(f"{WORKER_URL}/health", timeout=5.0)
    assert response.status_code == 200
    assert response.json()["service"] == "worker"


@pytest.mark.skipif(not RAG_URL, reason="RAG_URL is unset")
def test_live_rag_health() -> None:
    response = httpx.get(f"{RAG_URL}/health", timeout=5.0)
    assert response.status_code == 200
    assert response.json()["service"] == "rag"


@pytest.mark.skipif(not GUARDRAILS_URL, reason="GUARDRAILS_URL is unset")
def test_live_guardrails_health() -> None:
    response = httpx.get(f"{GUARDRAILS_URL}/health", timeout=5.0)
    assert response.status_code == 200
    assert response.json()["service"] == "guardrails"


@pytest.mark.skipif(not EVALS_URL, reason="EVALS_URL is unset")
def test_live_evals_health() -> None:
    response = httpx.get(f"{EVALS_URL}/health", timeout=5.0)
    assert response.status_code == 200
    assert response.json()["service"] == "evals"
