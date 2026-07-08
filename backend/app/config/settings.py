"""Application settings loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _env_files() -> tuple[str, ...]:
    """Prefer project-root .env, then local .env."""
    here = Path(__file__).resolve()
    root_env = here.parents[3] / ".env"  # Evolution_AI/.env
    local_env = Path.cwd() / ".env"
    files: list[str] = []
    for path in (root_env, local_env):
        if path.exists() and str(path) not in files:
            files.append(str(path))
    return tuple(files) or (".env",)


class Settings(BaseSettings):
    """Central configuration for the WhatsApp AI Assistant."""

    model_config = SettingsConfigDict(
        env_file=_env_files(),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "WhatsApp AI Assistant"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    cors_origins: str = "*"
    internal_api_key: str = "change-me-internal-api-key"
    webhook_secret: str = "change-me-webhook-secret"

    # OpenRouter
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4o-mini"
    openrouter_vision_model: str = "openai/gpt-4o-mini"
    openrouter_audio_model: str = "openai/gpt-4o-audio-preview"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_temperature: float = 0.7
    openrouter_max_tokens: int = 2048
    openrouter_site_url: str = "https://localhost"
    openrouter_app_name: str = "WhatsApp-AI-Assistant"

    # Database / Redis
    database_url: str = "postgresql+asyncpg://whatsapp:whatsapp@localhost:5432/whatsapp_ai"
    redis_url: str = "redis://localhost:6379/0"
    redis_memory_ttl: int = 86400
    memory_window_size: int = 40
    message_debounce_seconds: float = 1.5

    # Evolution
    evolution_url: str = "http://localhost:8080"
    evolution_api_key: str = "change-me-evolution-api-key"
    instance_name: str = "whatsapp-ai"
    webhook_url: str = "http://localhost:8000/webhook"
    auto_create_instance: bool = True

    # AI behaviour
    system_prompt: str = (
        "You are a helpful WhatsApp assistant. Answer naturally, concisely, "
        "and keep conversation context. Never invent facts about the business; "
        "use tools or knowledge when unsure."
    )
    knowledge_dir: str = "app/prompts/knowledge"
    rate_limit_per_minute: int = 60
    max_user_message_length: int = 8000
    max_tool_rounds: int = 5

    @field_validator("openrouter_temperature")
    @classmethod
    def validate_temperature(cls, value: float) -> float:
        if not 0.0 <= value <= 2.0:
            raise ValueError("OPENROUTER_TEMPERATURE must be between 0 and 2")
        return value

    @property
    def cors_origin_list(self) -> List[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()

# Final environment presets tuned
