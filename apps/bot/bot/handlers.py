"""apps/bot/bot/handlers.py — обработчики команд.

Итерация 0-А: только /start в приватном чате → приветствие + Menu Button на WEBAPP_URL.

SEAM-PATCH-1: бот НЕ создаёт участника и не пишет в tg_user_registry — точка
создания pid только first-launch Mini App (ADD3 INV-AGE-GATE-BEFORE-PID).

bot-access-1 (Р-2): при config.access_enabled /start сначала смотрит access_grants
(bot/access.py, только чтение): granted → как раньше; pending → PENDING; пауза → LOCKED;
иначе → PROMPT. /start — не заявка и не попытка. Меню-кнопку Mini App ставит только при
granted или выключенной функции. Ошибка БД → TRY_LATER.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

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


def build_router(config: BotConfig, connect=None) -> Router:
    """connect(dsn) → psycopg.AsyncConnection (для доступа); подменяется в тестах."""
    router = Router(name="start")

    async def access_reply(message: Message) -> str | None:
        """Текст для /start без доступа; None — доступ есть, обычное приветствие."""
        from bot import access

        now = datetime.now(timezone.utc)
        try:
            conn = await (connect or access.connect)(config.database_url)
            try:
                verdict = await access.read_state(conn, message.from_user.id, now)
            finally:
                await conn.close()
        except Exception as exc:  # noqa: BLE001
            logger.error("access: /start — ошибка БД (%s)", type(exc).__name__)
            return texts.ACCESS_TRY_LATER
        if verdict.kind == access.NOTHING:
            return None
        if verdict.kind in (access.PENDING, access.LOCKED):
            return access.user_text_for(verdict.kind, verdict.locked_until)
        return texts.ACCESS_PROMPT

    @router.message(CommandStart(), F.chat.type == "private")
    async def on_start(message: Message) -> None:
        if config.access_enabled and message.from_user is not None:
            text = await access_reply(message)
            if text is not None:
                await message.answer(text)
                return

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
