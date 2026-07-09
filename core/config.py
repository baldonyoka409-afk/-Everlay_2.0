"""
Configuration management using pydantic-settings.
"""
from functools import lru_cache
from typing import Optional, List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # OpenRouter API Configuration
    openrouter_api_key: str = Field(..., validation_alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1", validation_alias="OPENROUTER_BASE_URL"
    )
    openrouter_default_model: str = Field(
        default="openai/gpt-4o-mini", validation_alias="OPENROUTER_DEFAULT_MODEL"
    )
    openrouter_http_referer: Optional[str] = Field(
        default=None, validation_alias="OPENROUTER_HTTP_REFERER"
    )
    openrouter_x_title: Optional[str] = Field(
        default=None, validation_alias="OPENROUTER_X_TITLE"
    )

    # Telegram Bot Configuration
    telegram_bot_token: str = Field(..., validation_alias="TELEGRAM_BOT_TOKEN")
    telegram_allowed_users: List[int] = Field(
        default_factory=list, validation_alias="TELEGRAM_ALLOWED_USERS"
    )

    @field_validator("telegram_allowed_users", mode="before")
    @classmethod
    def parse_allowed_users(cls, v):
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        if isinstance(v, int):
            return [v]
        return v

    # Agent Configuration
    agent_default_temperature: float = Field(
        default=0.7, validation_alias="AGENT_DEFAULT_TEMPERATURE"
    )
    agent_default_max_tokens: int = Field(
        default=4096, validation_alias="AGENT_DEFAULT_MAX_TOKENS"
    )
    agent_timeout_seconds: int = Field(
        default=120, validation_alias="AGENT_TIMEOUT_SECONDS"
    )
    agent_default_system_prompt: str = Field(
        default="You are a helpful AI assistant.", validation_alias="AGENT_DEFAULT_SYSTEM_PROMPT"
    )

    # Logging
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    log_format: str = Field(default="json", validation_alias="LOG_FORMAT")
    log_file: str = Field(default="logs/agents.log", validation_alias="LOG_FILE")
    log_max_bytes: int = Field(default=10485760, validation_alias="LOG_MAX_BYTES")
    log_backup_count: int = Field(default=5, validation_alias="LOG_BACKUP_COUNT")

    # Application
    app_env: str = Field(default="development", validation_alias="APP_ENV")
    app_debug: bool = Field(default=True, validation_alias="APP_DEBUG")
    app_host: str = Field(default="0.0.0.0", validation_alias="APP_HOST")
    app_port: int = Field(default=8000, validation_alias="APP_PORT")

    # Database
    database_url: str = Field(default="sqlite:///./everlay.db", validation_alias="DATABASE_URL")

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")

    # Web Interface
    web_host: str = Field(default="0.0.0.0", validation_alias="WEB_HOST")
    web_port: int = Field(default=8000, validation_alias="WEB_PORT")
    web_secret_key: str = Field(..., validation_alias="WEB_SECRET_KEY")
    web_cors_origins: List[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:8000"],
        validation_alias="WEB_CORS_ORIGINS"
    )

    # Agent Defaults
    default_agent_model: str = Field(default="openai/gpt-4o-mini", validation_alias="DEFAULT_AGENT_MODEL")
    default_agent_temperature: float = Field(default=0.7, validation_alias="DEFAULT_AGENT_TEMPERATURE")
    default_agent_max_tokens: int = Field(default=4096, validation_alias="DEFAULT_AGENT_MAX_TOKENS")
    max_conversation_history: int = Field(default=50, validation_alias="MAX_CONVERSATION_HISTORY")


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# For backwards compatibility
settings = get_settings()