from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_nested_delimiter="__")

    redis_url: str = "redis://localhost:6379/0"

    # Matches conversation-orchestrator's existing in-process session TTL
    # (Session__TtlMinutes=30), so moving session state here doesn't change
    # how long a conversation stays "active" from a caller's point of view.
    session_ttl_seconds: int = 1800

    mongodb_uri: str = "mongodb://conversational_ai_app:conversational_ai_app@localhost:27017/conversational_ai"
    mongodb_database: str = "conversational_ai"

    otel_otlp_endpoint: str = "http://localhost:4317"


def get_settings() -> Settings:
    return Settings()
