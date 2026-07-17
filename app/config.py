from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_nested_delimiter="__")

    redis_url: str = "redis://localhost:6379/0"

    # Matches conversation-orchestrator's existing in-process session TTL
    # (Session__TtlMinutes=30), so moving session state here doesn't change
    # how long a conversation stays "active" from a caller's point of view.
    session_ttl_seconds: int = 1800

    # Host port 27018, not 27017: this machine also has a native mongod.exe Windows service
    # bound to 127.0.0.1:27017, which Windows prioritizes over Docker's port mapping (see
    # docker-compose.yml's mongodb service comment) - 27017 here would silently connect to
    # that unrelated, much older MongoDB instead of the one this service actually uses.
    mongodb_uri: str = "mongodb://conversational_ai_app:conversational_ai_app@localhost:27018/conversational_ai"
    mongodb_database: str = "conversational_ai"

    otel_otlp_endpoint: str = "http://localhost:4317"


def get_settings() -> Settings:
    return Settings()
