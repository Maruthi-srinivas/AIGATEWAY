import pytest
from pydantic import ValidationError

from aigateway.config import GatewaySettings, GuardrailsSettings, RagSettings, ServiceSettings


def test_service_settings_defaults() -> None:
    settings = ServiceSettings()
    assert settings.port == 8000
    assert settings.host == "0.0.0.0"
    assert settings.log_level == "INFO"


def test_gateway_settings_require_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("AUTH_BASE_URL", raising=False)
    monkeypatch.delenv("GUARDRAILS_BASE_URL", raising=False)
    monkeypatch.delenv("RAG_BASE_URL", raising=False)
    monkeypatch.delenv("INTERNAL_AUTH_TOKEN", raising=False)
    with pytest.raises(ValidationError):
        GatewaySettings(_env_file=None)


def test_gateway_settings_from_kwargs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SERVICE_NAME", raising=False)
    settings = GatewaySettings(
        postgres_dsn="postgresql://example",
        redis_url="redis://example",
        auth_base_url="http://auth:8000",
        guardrails_base_url="http://guardrails:8000",
        rag_base_url="http://rag:8000",
        internal_auth_token="secret",
    )
    assert settings.service_name == "gateway"
    assert settings.postgres_dsn == "postgresql://example"
    assert settings.auth_base_url == "http://auth:8000"
    assert settings.guardrails_base_url == "http://guardrails:8000"
    assert settings.rag_base_url == "http://rag:8000"


def test_guardrails_settings_default_to_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SERVICE_NAME", raising=False)
    monkeypatch.delenv("GUARDRAILS_MODE", raising=False)
    settings = GuardrailsSettings(
        postgres_dsn="postgresql://example",
        internal_auth_token="secret",
    )
    assert settings.service_name == "guardrails"
    assert settings.guardrails_mode == "fixture"
    assert settings.guardrails_moderation_threshold == 0.7
    assert settings.guardrails_timeout_seconds == 2.0
    assert settings.jev_api_key == ""
    assert settings.jev_model == "jev-latest"
    assert settings.jev_timeout_seconds == 0.8


def test_rag_settings_default_to_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SERVICE_NAME", raising=False)
    monkeypatch.delenv("EMBEDDING_MODE", raising=False)
    settings = RagSettings(
        postgres_dsn="postgresql://example",
        internal_auth_token="secret",
    )
    assert settings.service_name == "rag"
    assert settings.embedding_mode == "fixture"
    assert settings.rag_min_score == 0.3
    assert settings.rag_top_k == 8
