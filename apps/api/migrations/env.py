"""apps/api/migrations/env.py — Alembic env, DSN из переменных окружения.

Не хардкодит DSN. Берёт значения из ENV, чтобы одна и та же миграция
работала и в compose-сети (host=db), и с локальной машины (host=127.0.0.1).
DSN нигде не печатается (в нём пароль).
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers=False: миграция, запущенная из процесса приложения/тестов,
    # не должна глушить уже созданные логгеры приложения.
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def _build_dsn() -> str:
    """Собирает DSN из переменных окружения.

    Приоритет:
    1. MIGRATIONS_DATABASE_URL (непустая) — DSN владельца схемы для миграций (B-3a-1):
       приложение ходит под ролями с минимальными GRANT, а миграции — под владельцем.
    2. DATABASE_URL (полный DSN, если задан).
    3. Компоненты POSTGRES_HOST_INTERNAL/POSTGRES_USER/POSTGRES_PASSWORD/... .
    Пустая MIGRATIONS_DATABASE_URL равносильна незаданной.
    """
    dsn = os.environ.get("MIGRATIONS_DATABASE_URL")
    if dsn:
        return dsn

    dsn = os.environ.get("DATABASE_URL")
    if dsn:
        return dsn

    host = os.environ.get("POSTGRES_HOST_INTERNAL") or os.environ.get("POSTGRES_HOST", "db")
    port = os.environ.get("POSTGRES_PORT_INTERNAL", "5432")
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    db = os.environ["POSTGRES_DB"]
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"


config.set_main_option("sqlalchemy.url", _build_dsn())

# apps/api в sys.path: alembic запускается и из apps/api (CI), и из /app (контейнер).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import models  # noqa: F401 — регистрирует модели в Base.metadata
from app.db.base import Base

# Метаданные моделей. Схему по-прежнему создают ТОЛЬКО ручные миграции
# (0001 — дословно из db-schema.sql); autogenerate — лишь подсказка.
# Совпадение моделей с живой схемой проверяет tests/test_db_models.py.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
