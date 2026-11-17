"""apps/bot/bot/restart_handlers.py — кнопки рестарта «rst:g:<short_no>» / «rst:d:<short_no>» (bot-restart-1).

- Принимаются только из админ-темы (WORK_GROUP_ID + ACCESS_ADMIN_TOPIC_ID) и от ACCESS_ADMIN_IDS;
  иначе answerCallbackQuery без текста + лог, БД не вызывается.
- Заявка старше 48 ч (restart.STALE_HOURS, по дате сообщения; ровно 48 ч — действует) → в БД не ходить,
  в теме RESTART_STALE, кнопки снимаются, участнику ничего (bot-restart-2).
- Решение — bot/restart.py: decide (одна транзакция). Ошибка БД → answer RESTART_TRY_LATER.
- После COMMIT: к заявке дописывается итог, кнопки снимаются; участнику — RESTART_GRANTED /
  RESTART_DENIED. Отказ (muted, erased, нет block_lives, не найден) — только в теме, участнику ничего.
  Уже решено → в тему RESTART_ALREADY с итогом, кнопки снимаются.
  Ошибки Telegram после COMMIT только логируются: решение уже записано.
Роутер подключается в bot/app.py в ветке config.access_enabled; своего WARNING не пишет.
Ловит только callback «rst:…»; личку не ловит (заявка — on_private в bot/access_handlers.py).
Логи: без кодового слова, tg_user_id, pid, номера.
"""
from __future__ import annotations

import html
import logging
from datetime import datetime, timezone

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

from bot import access, restart, texts
from bot.config import BotConfig

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def after_commit(bot: Bot, config: BotConfig, result: restart.Result, chat_id: int,
                       message_id: int, original_html: str, now: datetime) -> None:
    """Итог в теме + ответ участнику. Ошибки Telegram — только в лог."""
    if result.kind == restart.ALREADY:
        try:
            await bot.send_message(chat_id=chat_id, message_thread_id=config.access_admin_topic_id,
                                   text=restart.already_text(result.ref))
        except Exception as exc:  # noqa: BLE001
            logger.warning("restart: ответ в тему не отправлен (%s)", type(exc).__name__)
        try:
            await bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)
        except Exception as exc:  # noqa: BLE001
            logger.warning("restart: кнопки заявки не сняты (%s)", type(exc).__name__)
        return
    note = restart.admin_note_for(result, now)
    if note is not None:
        try:
            await bot.edit_message_text(
                chat_id=chat_id, message_id=message_id, text=f"{original_html}\n\n{html.escape(note)}",
                parse_mode="HTML", reply_markup=None,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("restart: заявка в теме не обновлена (%s)", type(exc).__name__)
    user_text = restart.user_text_for_result(result)
    if user_text is None or result.tg_user_id is None:
        return
    try:
        await bot.send_message(chat_id=result.tg_user_id, text=user_text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("restart: участнику не отправлено (%s)", type(exc).__name__)


def build_restart_router(config: BotConfig, connect=None) -> Router:
    """connect(dsn) → psycopg.AsyncConnection; подменяется в тестах."""
    router = Router(name="restart")
    connect = connect or access.connect

    @router.callback_query(F.data.startswith(f"{restart.CALLBACK_PREFIX}:"))
    async def on_button(callback: CallbackQuery) -> None:
        msg = callback.message
        parsed = restart.parse_callback(callback.data)
        chat_id = msg.chat.id if msg else None
        thread_id = getattr(msg, "message_thread_id", None) if msg else None
        if parsed is None or not access.is_admin_context(config, chat_id, thread_id, callback.from_user.id):
            logger.warning("restart: кнопка вне темы или не из whitelist — игнор")
            await callback.answer()
            return
        action, short_no = parsed
        now = _now()
        if restart.is_stale(getattr(msg, "date", None), now):
            logger.info("restart: заявка устарела")
            await after_commit(callback.bot, config, restart.Result(restart.STALE), msg.chat.id,
                               msg.message_id, getattr(msg, "html_text", "") or "", now)
            try:
                await callback.answer()
            except Exception as exc:  # noqa: BLE001
                logger.warning("restart: answerCallbackQuery (%s)", type(exc).__name__)
            return
        try:
            conn = await connect(config.database_url)
            try:
                result = await restart.decide(conn, action, short_no, msg.message_id)
            finally:
                await conn.close()
        except Exception as exc:  # noqa: BLE001
            logger.error("restart: решение не записано (%s)", type(exc).__name__)
            await callback.answer(texts.RESTART_TRY_LATER)
            return
        await after_commit(callback.bot, config, result, msg.chat.id, msg.message_id,
                           getattr(msg, "html_text", "") or "", now)
        try:
            await callback.answer()
        except Exception as exc:  # noqa: BLE001
            logger.warning("restart: answerCallbackQuery (%s)", type(exc).__name__)

    return router
