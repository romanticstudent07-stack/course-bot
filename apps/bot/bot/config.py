"""apps/bot/bot/config.py — настройки бота из переменных окружения (.env).

Секреты и адреса — только из окружения (compose: env_file ../.env). Хардкодов нет.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse


class ConfigError(RuntimeError):
    """Неверная или неполная конфигурация — бот не стартует."""


def is_valid_webapp_url(url: str) -> bool:
    """Telegram принимает для WebApp только HTTPS-ссылки."""
    parsed = urlparse(url)
    return parsed.scheme == "https" and bool(parsed.netloc)


@dataclass(frozen=True)
class BotConfig:
    bot_token: str
    webapp_url: str  # пусто или не-HTTPS → Menu Button не ставится, бот отвечает фолбэком
    log_level: str
    webhook_recheck_seconds: int = 60

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
        )
