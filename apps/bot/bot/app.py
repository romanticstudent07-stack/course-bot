"""apps/bot/bot/app.py — сборка Dispatcher и запуск (long polling).

Итерация 0-А: только long polling. Плюсы: не нужен входящий порт (правило IRONCLAD —
наружу ничего, кроме туннеля) и не нужен туннель, чтобы бот ответил на /start.

Webhook-режим НЕ реализован намеренно: по DIVISION.md приём Telegram Webhook — зона
backend (apps/api), а контракт передачи апдейтов api → bot в архитектуре не описан
(вопрос Автору в PR). Если в Telegram уже зарегистрирован webhook (infra/README.md,
шаг 8), getUpdates не работает — бот НЕ удаляет webhook сам, а пишет ошибку в лог
и периодически перепроверяет, пока webhook не снимут (deleteWebhook).

Воркер outbox (send-1b, bot/outbox.py): фоновая задача asyncio в том же процессе, тот же Bot
(своей сессии и прокси нет, Р-11). Стартует до wait_until_no_webhook — доставке webhook не мешает.
BOT_DATABASE_URL пуст → воркер не запускается (WARNING), бот работает как раньше.
Остановка (SIGTERM → start_polling завершается → finally): stop.set(), ждём воркер до 25 с
(текущая строка дописывается), затем cancel (возможный дубль — docstring bot/outbox.py);
потом закрываем сессию бота (start_polling вызывается с close_bot_session=False).

Доступ по промокоду (bot-access-1, bot/access_handlers.py): роутер подключается после /start,
только если config.access_enabled; иначе один WARNING с именами переменных (без значений).
При включённом доступе дефолтная Menu Button — стандартная: Mini App ставится персонально
только при granted (bot/handlers.py, bot/access_handlers.py).
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.types import MenuButtonDefault

from bot.config import BotConfig
from bot.handlers import build_router, menu_button

logger = logging.getLogger(__name__)

OUTBOX_STOP_TIMEOUT = 25


def build_dispatcher(config: BotConfig, connect=None) -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(build_router(config, connect))
    if config.access_enabled:
        from bot.access_handlers import build_access_router

        dp.include_router(build_access_router(config, connect))
    else:
        logger.warning(
            "Доступ по промокоду выключен: не заданы %s", ", ".join(config.access_missing_vars())
        )

    @dp.startup()
    async def _on_startup(bot: Bot) -> None:
        # Дефолтная Menu Button для всех приватных чатов бота.
        if config.access_enabled:
            await bot.set_chat_menu_button(menu_button=MenuButtonDefault())
            logger.info("Доступ по промокоду включён — Menu Button Mini App только после «Выдать»")
        elif config.webapp_enabled:
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


def start_outbox_worker(bot, config: BotConfig, stop: asyncio.Event) -> "asyncio.Task | None":
    """Запустить воркер outbox фоновой задачей; BOT_DATABASE_URL пуст → None."""
    if not config.database_url:
        logger.warning("BOT_DATABASE_URL пуст — доставка outbox выключена")
        return None
    from bot.outbox import run_worker

    return asyncio.create_task(run_worker(bot, config.database_url, stop), name="outbox")


async def stop_outbox_worker(task: "asyncio.Task | None", stop: asyncio.Event) -> None:
    stop.set()
    if task is None:
        return
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=OUTBOX_STOP_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning("outbox: воркер не остановился за %s с — cancel", OUTBOX_STOP_TIMEOUT)
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        logger.error("outbox: воркер завершился с ошибкой %s", type(exc).__name__)


async def run(config: BotConfig) -> None:
    bot = Bot(token=config.bot_token)
    stop = asyncio.Event()
    task = None
    try:
        task = start_outbox_worker(bot, config, stop)
        await wait_until_no_webhook(bot, config.webhook_recheck_seconds)
        dp = build_dispatcher(config)
        logger.info("Старт бота: long polling")
        # Сессию закрывает finally ниже — после остановки воркера outbox (он шлёт через неё же).
        await dp.start_polling(
            bot, allowed_updates=dp.resolve_used_update_types(), close_bot_session=False
        )
    finally:
        await stop_outbox_worker(task, stop)
        await bot.session.close()
