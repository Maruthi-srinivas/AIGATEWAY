from fastapi.testclient import TestClient

from aigateway.contracts import AuthorizationError, GuardrailCheckResult
from aigateway.gateway.governance import MemoryGovernance
from aigateway.gateway.routing import select_route
from aigateway.gateway.tools import APPROVAL_APPROVED, APPROVAL_PENDING
from aigateway.testing import FakeGuardrail, FakeLLMClient
from tests.helpers import OTHER_USER_ID, FakeAuthClient
from tests.unit.test_chat import AUTH, ScriptedLLM, _app, _ctx


def test_select_route_prefers_the_policy_class() -> None:
    cheap = select_route(["fixture-cheap", "fixture-capable"], "cheap")
    capable = select_route(["fixture-capable", "fixture-cheap"], "capable")
    assert cheap.model == "fixture-cheap"
    assert cheap.provider == "fixture-a"
    assert capable.model == "fixture-capable"
    assert capable.provider == "fixture-b"
    assert cheap.estimated_cost < capable.estimated_cost


def test_empty_allowlist_is_forbidden() -> None:
    try:
        select_route([], "cheap")
    except AuthorizationError as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("expected forbidden")


def test_chat_uses_capable_route() -> None:
    class Capable(FakeGuardrail):
        async def check_input(self, *, tenant_id: str, texts: list) -> GuardrailCheckResult:
            result = await super().check_input(tenant_id=tenant_id, texts=texts)
            return result.model_copy(update={"route_preference": "capable"})

    app = _app(guardrail_client=Capable())
    with TestClient(app) as client:
        response = client.post("/v1/chat", json={"message": "hello"}, headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "fixture-b"
    assert body["model"] == "fixture-capable"
    assert body["approval_id"] is None


def test_disallowed_model_is_403() -> None:
    blocked = GuardrailCheckResult(
        decision="allow",
        decisions=[],
        texts=[],
        model_allowlist=[],
    )
    app = _app(guardrail_client=FakeGuardrail(result=blocked))
    with TestClient(app) as client:
        response = client.post("/v1/chat", json={"message": "hello"}, headers=AUTH)
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


def test_export_waits_for_someone_else() -> None:
    llm = FakeLLMClient()
    auth = FakeAuthClient(context=_ctx())
    app = _app(llm_client=llm, auth_client=auth)
    with TestClient(app) as client:
        opened = client.post(
            "/v1/chat",
            json={"message": "export the directory", "tool": "export_directory"},
            headers=AUTH,
        )
        assert opened.status_code == 200
        body = opened.json()
        assert body["approval_id"]
        assert body["answer"] == APPROVAL_PENDING
        assert body["citations"] == []
        assert llm.calls == []
        own = client.post(
            f"/v1/approvals/{body['approval_id']}",
            json={"decision": "approve"},
            headers=AUTH,
        )
        assert own.status_code == 403
        auth.provider.context = _ctx(role="security_admin", user_id=OTHER_USER_ID)
        decided = client.post(
            f"/v1/approvals/{body['approval_id']}",
            json={"decision": "approve"},
            headers=AUTH,
        )
    assert decided.status_code == 200
    assert decided.json()["detail"] == APPROVAL_APPROVED
    assert decided.json()["status"] == "approved"
    assert llm.calls == []


def test_lookup_off_allowlist_is_403() -> None:
    blocked = GuardrailCheckResult(
        decision="allow",
        decisions=[],
        texts=[],
        tool_allowlist=[],
    )
    app = _app(guardrail_client=FakeGuardrail(result=blocked))
    with TestClient(app) as client:
        response = client.post(
            "/v1/chat",
            json={"message": "leave", "tool": "lookup_leave"},
            headers=AUTH,
        )
    assert response.status_code == 403


class RaisingGovernance(MemoryGovernance):
    async def record(self, **kwargs) -> None:
        _ = kwargs
        raise RuntimeError("governance down")


def test_governance_write_failure_keeps_chat_status() -> None:
    app = _app(governance=RaisingGovernance(), llm_client=ScriptedLLM("Stub: hello"))
    with TestClient(app) as client:
        response = client.post("/v1/chat", json={"message": "hello"}, headers=AUTH)
    assert response.status_code == 200
