"""apps/api/app/config.py — настройки из переменных окружения.

Все URL, порты, хосты и секреты — только из .env (compose: env_file ../.env).
В коде нет ни одного реального значения секрета или адреса окружения.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    # --- HTTP ---
    app_host: str = "0.0.0.0"  # внутри контейнера; публикация наружу — 127.0.0.1 (compose)
    app_port: int = 8080
    log_level: str = "INFO"

    # --- Telegram ---
    bot_token: SecretStr = SecretStr("")
    webhook_secret: SecretStr = SecretStr("")
    webapp_url: str = ""

    # --- PostgreSQL (внутри compose: host=db) ---
    database_url: str | None = None
    postgres_host_internal: str = "db"
    postgres_port_internal: int = 5432
    postgres_db: str = ""
    postgres_user: str = ""
    postgres_password: SecretStr = SecretStr("")

    # --- Redis ---
    redis_url: str = ""

    # --- S3 (Garage в dev) ---
    s3_endpoint: str = ""
    s3_region: str = ""
    s3_bucket_photos: str = ""

    # --- initData (AGENTS.md): TTL auth_date, 24 ч стандарт, 1 ч для чувствительных ---
    init_data_max_age_seconds: int = Field(default=86400, ge=1)
    init_data_sensitive_max_age_seconds: int = Field(default=3600, ge=1)

    # --- Часовой пояс (SERVER-IRONCLAD.md) ---
    server_timezone: str = "Europe/Moscow"

    def sqlalchemy_dsn(self) -> str:
        """DSN для SQLAlchemy/psycopg. Та же логика, что в migrations/env.py."""
        if self.database_url:
            return self.database_url
        password = self.postgres_password.get_secret_value()
        return (
            f"postgresql+psycopg://{self.postgres_user}:{password}"
            f"@{self.postgres_host_internal}:{self.postgres_port_internal}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
