"""apps/bot/bot/config.py — настройки бота из переменных окружения (.env).

Секреты и адреса — только из окружения: compose передаёт боту переменные явно
(environment в infra/docker-compose.dev.yml; env_file у бота нет с #71). Хардкодов нет.

Переменные: BOT_TOKEN (обязателен), WEBAPP_URL, LOG_LEVEL,
BOT_DATABASE_URL — DSN бота (coursebot_bot, роль app_bot; send-1b), формат
postgresql://… без +psycopg. Пусто → доставка outbox выключена, остальное как раньше.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import urlparse


class ConfigError(RuntimeError):
    """Неверная или неполная конфигурация — бот не стартует."""


def is_valid_webapp_url(url: str) -> bool:
    """Telegram принимает для WebApp только HTTPS-ссылки."""
    parsed = urlparse(url)
    return parsed.scheme == "https" and bool(parsed.netloc)


DSN_PREFIXES = ("postgresql://", "postgres://")


def parse_database_url(env) -> str:
    """BOT_DATABASE_URL (strip). Пусто → "". Чужой формат → ConfigError без значения."""
    dsn = env.get("BOT_DATABASE_URL", "").strip()
    if dsn and not dsn.startswith(DSN_PREFIXES):
        raise ConfigError("BOT_DATABASE_URL: нужен формат postgresql://… без +psycopg")
    return dsn


@dataclass(frozen=True)
class BotConfig:
    bot_token: str = field(repr=False)
    webapp_url: str  # пусто или не-HTTPS → Menu Button не ставится, бот отвечает фолбэком
    log_level: str
    webhook_recheck_seconds: int = 60
    database_url: str = field(default="", repr=False)  # пусто → доставка outbox выключена

    @property
    def webapp_enabled(self) -> bool:
        return is_valid_webapp_url(self.webapp_url)

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "BotConfig":
        env = dict(os.environ if env is None else env)

        token = env.get("BOT_TOKEN", "").strip()
        if not token:
            raise ConfigError("BOT_TOKEN не задан (см. .env.example)")

        return cls(
            bot_token=token,
            webapp_url=env.get("WEBAPP_URL", "").strip(),
            log_level=env.get("LOG_LEVEL", "INFO").strip().upper() or "INFO",
            database_url=parse_database_url(env),
        )
