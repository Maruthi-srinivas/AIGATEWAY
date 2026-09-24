from pydantic import Field, field_validator
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
    rag_base_url: str
    rag_timeout: float = Field(default=2.0, ge=0.1)
    document_body_max_bytes: int = Field(default=278528, ge=1024)
    llm_mode: str = "fixture"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = ""
    llm_model: str = ""
    llm_timeout_seconds: float = Field(default=30.0, ge=0.1)
    kafka_bootstrap_servers: str = ""
    kafka_publish_timeout_seconds: float = Field(default=0.5, ge=0.1)
    evals_base_url: str = ""
    evals_timeout_seconds: float = Field(default=2.0, ge=0.1)
    cors_origins: str = "http://localhost:5173"

    @field_validator("cors_origins")
    @classmethod
    def _explicit_cors_origins(cls, value: str) -> str:
        parts = [part.strip() for part in value.split(",") if part.strip()]
        if "*" in parts:
            raise ValueError("CORS_ORIGINS must list explicit origins")
        return ",".join(parts)

    def cors_origin_list(self) -> list[str]:
        if not self.cors_origins:
            return []
        return [part.strip() for part in self.cors_origins.split(",") if part.strip()]


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
    jev_api_key: str = ""
    jev_api_url: str = "https://api.typesafe.ai/v1/systemone"
    jev_model: str = "jev-latest"
    jev_timeout_seconds: float = Field(default=0.8, ge=0.1)


class RagSettings(ServiceSettings):
    """RAG process settings. Embedding keys never live on the gateway."""

    service_name: str = "rag"
    postgres_dsn: str
    internal_auth_token: str
    embedding_mode: str = "fixture"
    embedding_api_url: str = "https://api.openai.com/v1/embeddings"
    embedding_api_key: str = ""
    embedding_model: str = ""
    rag_min_score: float = Field(default=0.3, ge=0.0, le=1.0)
    rag_top_k: int = Field(default=8, ge=1, le=32)
    rag_candidate_k: int = Field(default=32, ge=1, le=64)
    rag_context_max_chars: int = Field(default=8000, ge=1)
    rag_timeout_seconds: float = Field(default=2.0, ge=0.1)
    postgres_connect_timeout: float = Field(default=2.0, ge=0.1)
    seed_enabled: bool = True


class EvalsSettings(ServiceSettings):
    """Evaluation store. Scores stay numeric. Prompt and answer text are not stored."""

    service_name: str = "evals"
    postgres_dsn: str
    internal_auth_token: str
    postgres_connect_timeout: float = Field(default=2.0, ge=0.1)


class WorkerSettings(ServiceSettings):
    """Worker process settings. Consumes Kafka and locks event ids in Redis."""

    service_name: str = "worker"
    redis_url: str
    internal_auth_token: str
    kafka_bootstrap_servers: str = "kafka:9092"
    kafka_event_lock_seconds: int = Field(default=30, ge=1)
    kafka_event_done_seconds: int = Field(default=86400, ge=1)
