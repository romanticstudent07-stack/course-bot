"""apps/bot/bot/handlers.py — обработчики команд.

Итерация 0-А: только /start в приватном чате → приветствие + Menu Button на WEBAPP_URL.

SEAM-PATCH-1: бот НЕ создаёт участника и не пишет в tg_user_registry — точка
создания pid только first-launch Mini App (ADD3 INV-AGE-GATE-BEFORE-PID).
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    Message,
    WebAppInfo,
)

from bot import texts
from bot.config import BotConfig

logger = logging.getLogger(__name__)


def webapp_keyboard(webapp_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.MINIAPP_BUTTON, web_app=WebAppInfo(url=webapp_url))]
        ]
    )


def menu_button(webapp_url: str) -> MenuButtonWebApp:
    return MenuButtonWebApp(text=texts.MINIAPP_BUTTON, web_app=WebAppInfo(url=webapp_url))


def build_router(config: BotConfig) -> Router:
    router = Router(name="start")

    @router.message(CommandStart(), F.chat.type == "private")
    async def on_start(message: Message) -> None:
        if not config.webapp_enabled:
            # WEBAPP_URL пуст или не HTTPS — Menu Button ставить некуда.
            # Нейтральный текст без совета «обновите Telegram» — он здесь не к месту.
            # TODO(Итерация 1): перенести в text_registry.
            await message.answer(texts.MINIAPP_NOT_CONNECTED)
            return

        # Menu Button персонально для этого чата (дублирует дефолтную, выставленную
        # при старте, — на случай, если у пользователя закэширована старая).
        try:
            await message.bot.set_chat_menu_button(
                chat_id=message.chat.id, menu_button=menu_button(config.webapp_url)
            )
        except Exception:  # noqa: BLE001 — сбой кнопки не должен ронять приветствие
            logger.exception("set_chat_menu_button failed for chat_id=%s", message.chat.id)

        await message.answer(
            f"{texts.START_WELCOME}\n\n{texts.FALLBACK_UPDATE_TELEGRAM}",
            reply_markup=webapp_keyboard(config.webapp_url),
        )

    return router
