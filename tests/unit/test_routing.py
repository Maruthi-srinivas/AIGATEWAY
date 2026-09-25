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


async def test_summary_groups_models_and_skips_other_tenant() -> None:
    store = MemoryGovernance()
    await store.record(
        tenant_id="tenant-a",
        correlation_id="a1",
        provider="fixture-a",
        model="fixture-cheap",
        route="cheap",
        estimated_cost=0.0001,
        approval_status=None,
    )
    await store.record(
        tenant_id="tenant-a",
        correlation_id="a2",
        provider="fixture-b",
        model="fixture-capable",
        route="capable",
        estimated_cost=0.001,
        approval_status=None,
    )
    await store.record(
        tenant_id="tenant-b",
        correlation_id="b1",
        provider="fixture-a",
        model="fixture-cheap",
        route="cheap",
        estimated_cost=9.0,
        approval_status=None,
    )
    summary = await store.summary("tenant-a")
    by_model = {item.model: item for item in summary.models}
    assert set(by_model) == {"fixture-cheap", "fixture-capable"}
    assert by_model["fixture-cheap"].requests == 1
    assert by_model["fixture-capable"].estimated_cost == 0.001
    assert summary.total_requests == 2
    assert abs(summary.total_estimated_cost - 0.0011) < 1e-9


def test_summary_hides_the_prompt_and_rejects_app_user() -> None:
    class Flip(FakeGuardrail):
        def __init__(self) -> None:
            super().__init__()
            self.seen = 0

        async def check_input(self, *, tenant_id: str, texts: list) -> GuardrailCheckResult:
            result = await super().check_input(tenant_id=tenant_id, texts=texts)
            self.seen += 1
            preference = "capable" if self.seen > 1 else "cheap"
            return result.model_copy(update={"route_preference": preference})

    auth = FakeAuthClient(context=_ctx())
    app = _app(guardrail_client=Flip(), auth_client=auth)
    with TestClient(app) as client:
        denied = client.get("/v1/governance/summary", headers=AUTH)
        assert denied.status_code == 403
        auth.provider.context = _ctx(role="security_admin")
        first = client.post("/v1/chat", json={"message": "payroll question"}, headers=AUTH)
        second = client.post("/v1/chat", json={"message": "payroll question"}, headers=AUTH)
        assert first.status_code == 200
        assert second.status_code == 200
        summary = client.get("/v1/governance/summary", headers=AUTH)
        other = client.get(
            "/v1/governance/summary",
            params={"tenant_id": "00000000-0000-0000-0000-000000000099"},
            headers=AUTH,
        )
    assert summary.status_code == 200, summary.text
    models = {item["model"] for item in summary.json()["models"]}
    assert models == {"fixture-cheap", "fixture-capable"}
    assert "payroll question" not in summary.text
    assert other.status_code == 403


def test_delete_audit_is_rejected() -> None:
    app = _app()
    with TestClient(app) as client:
        response = client.delete("/v1/audit")
    assert response.status_code in {404, 405}
