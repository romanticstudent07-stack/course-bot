"""apps/bot/bot/app.py — сборка Dispatcher и запуск (long polling).

Итерация 0-А: только long polling. Плюсы: не нужен входящий порт (правило IRONCLAD —
наружу ничего, кроме туннеля) и не нужен туннель, чтобы бот ответил на /start.

Webhook-режим НЕ реализован намеренно: по DIVISION.md приём Telegram Webhook — зона
backend (apps/api), а контракт передачи апдейтов api → bot в архитектуре не описан
(вопрос Автору в PR). Если в Telegram уже зарегистрирован webhook (infra/README.md,
шаг 8), getUpdates не работает — бот НЕ удаляет webhook сам, а пишет ошибку в лог
и периодически перепроверяет, пока webhook не снимут (deleteWebhook).
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.types import MenuButtonDefault

from bot.config import BotConfig
from bot.handlers import build_router, menu_button

logger = logging.getLogger(__name__)


def build_dispatcher(config: BotConfig) -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(build_router(config))

    @dp.startup()
    async def _on_startup(bot: Bot) -> None:
        # Дефолтная Menu Button для всех приватных чатов бота.
        if config.webapp_enabled:
            await bot.set_chat_menu_button(menu_button=menu_button(config.webapp_url))
            logger.info("Menu Button → WEBAPP_URL установлена")
        else:
            await bot.set_chat_menu_button(menu_button=MenuButtonDefault())
            logger.warning("WEBAPP_URL пуст или не HTTPS — Menu Button сброшена на стандартную")

    return dp


async def wait_until_no_webhook(bot: Bot, recheck_seconds: int) -> None:
    """Ждёт, пока у бота не останется зарегистрированного webhook."""
    while True:
        info = await bot.get_webhook_info()
        if not info.url:
            return
        logger.error(
            "В Telegram зарегистрирован webhook — long polling невозможен. "
            "Бот его НЕ удаляет автоматически. Снимите webhook (deleteWebhook) "
            "или дождитесь решения по webhook-режиму. Перепроверка через %s с.",
            recheck_seconds,
        )
        await asyncio.sleep(recheck_seconds)


async def run(config: BotConfig) -> None:
    bot = Bot(token=config.bot_token)
    try:
        await wait_until_no_webhook(bot, config.webhook_recheck_seconds)
        dp = build_dispatcher(config)
        logger.info("Старт бота: long polling")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
