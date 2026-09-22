import pytest
from pydantic import ValidationError

from aigateway.config import GatewaySettings, ServiceSettings


def test_service_settings_defaults() -> None:
    settings = ServiceSettings()
    assert settings.port == 8000
    assert settings.host == "0.0.0.0"
    assert settings.log_level == "INFO"


def test_gateway_settings_require_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("AUTH_BASE_URL", raising=False)
    monkeypatch.delenv("INTERNAL_AUTH_TOKEN", raising=False)
    with pytest.raises(ValidationError):
        GatewaySettings(_env_file=None)


def test_gateway_settings_from_kwargs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SERVICE_NAME", raising=False)
    settings = GatewaySettings(
        postgres_dsn="postgresql://example",
        redis_url="redis://example",
        auth_base_url="http://auth:8000",
        internal_auth_token="secret",
    )
    assert settings.service_name == "gateway"
    assert settings.postgres_dsn == "postgresql://example"
    assert settings.auth_base_url == "http://auth:8000"
