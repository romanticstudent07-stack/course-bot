"""apps/bot/bot/config.py — настройки бота из переменных окружения (.env).

Секреты и адреса — только из окружения: compose передаёт боту переменные явно
(environment в infra/docker-compose.dev.yml; env_file у бота нет с #71). Хардкодов нет.

Переменные: BOT_TOKEN (обязателен), WEBAPP_URL, LOG_LEVEL,
BOT_DATABASE_URL — DSN бота (coursebot_bot, роль app_bot; send-1b), формат
postgresql://… без +psycopg. Пусто → доставка outbox выключена, остальное как раньше.

Доступ по промокоду (bot-access-1, Р-2): WORK_GROUP_ID (id Рабочей группы),
ACCESS_ADMIN_TOPIC_ID (message_thread_id админ-темы), ACCESS_ADMIN_IDS (whitelist tg id
через запятую, временно до Б17), ACCESS_MAX_DENIES (по умолчанию 5, ≥ 1),
ACCESS_LOCK_HOURS (по умолчанию 24, ≥ 1). access_enabled = BOT_DATABASE_URL и три первые
заданы; иначе функция выключена (WARNING при старте — только имена переменных).
Неверный формат числа → ConfigError без значения.
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


ACCESS_REQUIRED_VARS = ("BOT_DATABASE_URL", "WORK_GROUP_ID", "ACCESS_ADMIN_TOPIC_ID", "ACCESS_ADMIN_IDS")


def _parse_int(env, name: str) -> int | None:
    """Целое из env (strip). Пусто → None. Не целое → ConfigError без значения."""
    raw = env.get(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"{name}: нужно целое число") from None


def _parse_positive(env, name: str, default: int) -> int:
    value = _parse_int(env, name)
    if value is None:
        return default
    if value < 1:
        raise ConfigError(f"{name}: нужно целое число ≥ 1")
    return value


def _parse_ids(env, name: str) -> frozenset[int]:
    """Список tg id через запятую. Пусто → пустое множество. Кривой элемент → ConfigError."""
    raw = env.get(name, "").strip()
    if not raw:
        return frozenset()
    ids = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            value = int(part)
        except ValueError:
            raise ConfigError(f"{name}: нужны целые числа через запятую") from None
        if value <= 0:
            raise ConfigError(f"{name}: id должны быть > 0")
        ids.add(value)
    return frozenset(ids)


@dataclass(frozen=True)
class BotConfig:
    bot_token: str = field(repr=False)
    webapp_url: str  # пусто или не-HTTPS → Menu Button не ставится, бот отвечает фолбэком
    log_level: str
    webhook_recheck_seconds: int = 60
    database_url: str = field(default="", repr=False)  # пусто → доставка outbox выключена
    work_group_id: int | None = None
    access_admin_topic_id: int | None = None
    access_admin_ids: frozenset[int] = frozenset()
    access_max_denies: int = 5
    access_lock_hours: int = 24

    @property
    def webapp_enabled(self) -> bool:
        return is_valid_webapp_url(self.webapp_url)

    def access_missing_vars(self) -> list[str]:
        """Имена незаданных переменных доступа (без значений)."""
        present = {
            "BOT_DATABASE_URL": bool(self.database_url),
            "WORK_GROUP_ID": self.work_group_id is not None,
            "ACCESS_ADMIN_TOPIC_ID": self.access_admin_topic_id is not None,
            "ACCESS_ADMIN_IDS": bool(self.access_admin_ids),
        }
        return [name for name in ACCESS_REQUIRED_VARS if not present[name]]

    @property
    def access_enabled(self) -> bool:
        return not self.access_missing_vars()

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
            work_group_id=_parse_int(env, "WORK_GROUP_ID"),
            access_admin_topic_id=_parse_int(env, "ACCESS_ADMIN_TOPIC_ID"),
            access_admin_ids=_parse_ids(env, "ACCESS_ADMIN_IDS"),
            access_max_denies=_parse_positive(env, "ACCESS_MAX_DENIES", 5),
            access_lock_hours=_parse_positive(env, "ACCESS_LOCK_HOURS", 24),
        )
