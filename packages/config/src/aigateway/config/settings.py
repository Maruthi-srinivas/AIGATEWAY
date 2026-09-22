from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServiceSettings(BaseSettings):
    """Settings shared by every process. Extra env vars are ignored."""

    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    service_name: str = "app"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000


class GatewaySettings(ServiceSettings):
    """Gateway process settings. Postgres, Redis, and auth URL are required."""

    service_name: str = "gateway"
    postgres_dsn: str
    redis_url: str
    auth_base_url: str
    internal_auth_token: str
    postgres_connect_timeout: float = Field(default=2.0, ge=0.1)
    redis_connect_timeout: float = Field(default=2.0, ge=0.1)
    auth_timeout: float = Field(default=5.0, ge=0.1)
    rate_limit_tenant_per_minute: int = Field(default=60, ge=1)
    rate_limit_user_per_minute: int = Field(default=20, ge=1)
    rate_limit_api_key_per_minute: int = Field(default=60, ge=1)
    stub_stream_delay_ms: float = Field(default=20.0, ge=0)
    chat_body_max_bytes: int = Field(default=32768, ge=1024)
    chat_message_max_chars: int = Field(default=8000, ge=1)
    session_cache_ttl_seconds: int = Field(default=86400, ge=60)
    session_cache_message_limit: int = Field(default=20, ge=1)
    guardrails_base_url: str
    guardrails_timeout: float = Field(default=2.0, ge=0.1)


class AuthSettings(ServiceSettings):
    """Auth service settings. JWT secret never lives on the gateway."""

    service_name: str = "auth"
    postgres_dsn: str
    jwt_secret: str
    internal_auth_token: str
    jwt_algorithm: str = "HS256"
    access_ttl_seconds: int = Field(default=3600, ge=60)
    refresh_ttl_seconds: int = Field(default=604800, ge=60)
    seed_enabled: bool = True
    seed_password: str = "changeme"
    seed_hr_api_key: str = "agt_demo_hr_local_docker_only_key"
    seed_eng_api_key: str = "agt_demo_eng_local_docker_only_key"


class GuardrailsSettings(ServiceSettings):
    """Guardrails process settings. Vendor keys never live on the gateway."""

    service_name: str = "guardrails"
    postgres_dsn: str
    internal_auth_token: str
    guardrails_mode: str = "fixture"
    guardrails_api_url: str = "https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze"
    guardrails_api_key: str = ""
    guardrails_moderation_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    guardrails_timeout_seconds: float = Field(default=2.0, ge=0.1)
    postgres_connect_timeout: float = Field(default=2.0, ge=0.1)
