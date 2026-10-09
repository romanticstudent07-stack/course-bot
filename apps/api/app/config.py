"""apps/api/app/config.py — настройки из переменных окружения.

Все URL, порты, хосты и секреты — только из переменных окружения: у api — env_file ../.env
(compose); у проектора после B-3a-3 env_file нет — только переменные из environment compose.
В коде нет ни одного реального значения секрета или адреса окружения.

DSN по процессам (B-3, D-13). Пустая переменная = не задана:
  - API: DATABASE_URL → POSTGRES_* — sqlalchemy_dsn();
  - проектор: PROJECTOR_DATABASE_URL → DATABASE_URL → POSTGRES_* — projector_dsn();
  - загрузчик текстов (python -m app.texts load):
    MIGRATIONS_DATABASE_URL → DATABASE_URL → POSTGRES_* — migrations_dsn();
  - alembic (migrations/env.py): та же цепочка, что у migrations_dsn(), своя реализация.
DSN, пароль и имя пользователя БД не пишутся в лог и не печатаются.
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
    # Проектор (роль app_projector, миграция 0006). Не задан → DATABASE_URL → POSTGRES_*.
    projector_database_url: str | None = None
    # Загрузчик текстов и alembic (владелец). Не задан → DATABASE_URL → POSTGRES_*.
    migrations_database_url: str | None = None
    postgres_host_internal: str = "db"
    postgres_port_internal: int = 5432
    postgres_db: str = ""
    postgres_user: str = ""
    postgres_password: SecretStr = SecretStr("")

    # --- Redis ---
    redis_url: str = ""

    # --- Rate-limit /miniapp/v1/** (B-1, app/rate_limit.py) ---
    # Не больше N запросов в минуту на один tg_user_id (решение Автора 5Б, Б14 R328).
    rate_limit_per_minute: int = Field(60, ge=1)
    # Таймаут соединения и ответа Redis: дольше — fail-open (запрос проходит, WARNING).
    rate_limit_redis_timeout_seconds: float = 0.2

    # --- S3 (Garage в dev) ---
    s3_endpoint: str = ""
    s3_region: str = ""
    s3_bucket_photos: str = ""

    # --- initData: свежесть auth_date (app/telegram_init_data.py) ---
    # TTL по умолчанию 86400 (24 ч) — решение Автора (PR 1a), по источникам:
    #   - build/miniapp-api-contract.yaml → securitySchemes.TelegramInitData: 24 ч;
    #   - build/miniapp-security-checklist.md §2: «ориентир — 3600»;
    #   - 14-data-durability.md §14.13 / INV-B14-INITDATA-TTL / R325: 300 (write) / 3600 (read)
    #     при наличии session_jwt.
    # Противоречие источников — docs/DEFECTS-FOUND.md, D-9 (решение Автора к проду).
    init_data_max_age_seconds: int = Field(default=86400, ge=1)
    # Для /refund, /erasure_* — будущие итерации (сейчас не используется).
    init_data_sensitive_max_age_seconds: int = Field(default=3600, ge=1)
    # Допуск на расхождение часов: auth_date > now + skew → отказ (решение Автора, PR 1a).
    init_data_future_skew_seconds: int = Field(default=60, ge=0)

    # --- Часовой пояс (SERVER-IRONCLAD.md) ---
    server_timezone: str = "Europe/Moscow"

    def sqlalchemy_dsn(self) -> str:
        """DSN API: DATABASE_URL → POSTGRES_*. Та же логика, что в migrations/env.py."""
        if self.database_url:
            return self.database_url
        password = self.postgres_password.get_secret_value()
        return (
            f"postgresql+psycopg://{self.postgres_user}:{password}"
            f"@{self.postgres_host_internal}:{self.postgres_port_internal}/{self.postgres_db}"
        )

    def projector_dsn(self) -> str:
        """DSN проектора: PROJECTOR_DATABASE_URL → DATABASE_URL → POSTGRES_*."""
        return self.projector_database_url or self.sqlalchemy_dsn()

    def migrations_dsn(self) -> str:
        """DSN загрузчика текстов: MIGRATIONS_DATABASE_URL → DATABASE_URL → POSTGRES_*."""
        return self.migrations_database_url or self.sqlalchemy_dsn()


@lru_cache
def get_settings() -> Settings:
    return Settings()
