"""Точка входа: python -m bot (см. apps/bot/Dockerfile)."""
from __future__ import annotations

import asyncio
import logging
import sys

from aiogram.exceptions import TelegramUnauthorizedError

from bot.app import run
from bot.config import BotConfig, ConfigError


def main() -> int:
    try:
        config = BotConfig.from_env()
    except ConfigError as exc:
        logging.basicConfig(level=logging.INFO)
        logging.getLogger("bot").error("Конфигурация: %s", exc)
        return 1

    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    try:
        asyncio.run(run(config))
    except TelegramUnauthorizedError:
        logging.getLogger("bot").error("Telegram отклонил BOT_TOKEN (Unauthorized) — проверьте .env")
        return 1
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
