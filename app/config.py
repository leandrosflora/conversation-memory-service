from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_nested_delimiter="__")

    redis_url: str = "redis://localhost:6379/0"
    session_ttl_seconds: int = 1800

    mongodb_uri: str = "mongodb://conversational_ai_app:conversational_ai_app@localhost:27018/conversational_ai"
    mongodb_database: str = "conversational_ai"
    otel_otlp_endpoint: str = "http://localhost:4317"

    internal_auth_enabled: bool = True
    internal_auth_issuer: str = "conversational-ai-platform"
    internal_auth_service_name: str = "conversation-memory-service"
    internal_auth_signing_key: str = ""
    internal_auth_token_ttl_seconds: int = 300


def get_settings() -> Settings:
    return Settings()
