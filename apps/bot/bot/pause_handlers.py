"""apps/bot/bot/pause_handlers.py — кнопки ✅/✖ карточки заявки паузы (bot-pause-1, §7).

- Роутер ловит только callback «pse:…»; разбор строго ^pse:(a|r):(\\d{1,18})$.
  Не разобралось → answerCallbackQuery без текста + лог, без БД.
- Сообщение не из WORK_GROUP_ID или пользователь не в ACCESS_ADMIN_IDS → answerCallbackQuery без
  текста + лог, без БД (как в revive_handlers).
- Иначе pause.decide в одной транзакции; итог дописывается к карточке, кнопки снимаются.
  При TRY_LATER (ошибка БД) кнопки остаются, текст — во всплывающем ответе.
- Участнику кнопка ничего не шлёт: уведомляет только наблюдатель (bot/pause_watch.py).
Подключается в bot/app.py в ветке config.access_enabled сразу перед роутером доступа.
Логи: без tg_user_id, pid, short_no — только код результата.
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot import access, pause
from bot.config import BotConfig

logger = logging.getLogger(__name__)


def build_pause_router(config: BotConfig, connect=None) -> Router:
    """connect(dsn) → psycopg.AsyncConnection; подменяется в тестах."""
    router = Router(name="pause")
    connect = connect or access.connect

    async def _answer(callback: CallbackQuery, text: str | None = None) -> None:
        try:
            await callback.answer(text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("pause: answerCallbackQuery (%s)", type(exc).__name__)

    async def _finish(callback: CallbackQuery, note: str) -> None:
        """Дописать итог к карточке и снять кнопки; ошибка Telegram — только лог."""
        msg = callback.message
        text = getattr(msg, "text", None) or ""
        try:
            await callback.bot.edit_message_text(chat_id=msg.chat.id, message_id=msg.message_id,
                                                 text=f"{text}\n\n{note}" if text else note, reply_markup=None)
        except Exception as exc:  # noqa: BLE001
            logger.warning("pause: карточка не изменена (%s)", type(exc).__name__)

    @router.callback_query(F.data.startswith(f"{pause.CALLBACK_PREFIX}:"))
    async def on_button(callback: CallbackQuery) -> None:
        msg = callback.message
        chat_id = msg.chat.id if msg else None
        parsed = pause.parse_callback(callback.data)
        if parsed is None:
            logger.warning("pause: кнопка не разобрана — игнор")
            await _answer(callback)
            return
        if chat_id != config.work_group_id or callback.from_user.id not in config.access_admin_ids:
            logger.warning("pause: кнопка вне Рабочей группы или не из whitelist — игнор")
            await _answer(callback)
            return
        approve, pause_id = parsed
        try:
            conn = await connect(config.database_url)
        except Exception as exc:  # noqa: BLE001
            logger.error("pause: нет соединения с БД (%s)", type(exc).__name__)
            code = pause.TRY_LATER
        else:
            try:
                code = await pause.decide(conn, pause_id, approve)
            finally:
                await conn.close()
        logger.info("pause: решение (%s)", code)
        if code == pause.TRY_LATER:
            await _answer(callback, pause.TEXT_FOR[pause.TRY_LATER])
            return
        await _finish(callback, pause.TEXT_FOR[code])
        await _answer(callback)

    return router

