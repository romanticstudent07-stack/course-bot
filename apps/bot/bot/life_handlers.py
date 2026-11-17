"""apps/bot/bot/life_handlers.py — роутер /life +N | -N (bot-life-1).

- /life +N (reply на пост бота), /life #NNNNNN +N | -N — только в Рабочей группе (тема любая)
  и только от ACCESS_ADMIN_IDS; иначе игнор + лог без вызовов Bot API и БД (как /card).
- Шаг 1 — предпросмотр без записи (life.preview): отказ → текст отказа; иначе LIFE_PREVIEW
  с кнопками [Подтвердить] «life:y:<номер>:<±N>:<op>» и [Отмена] «life:n».
- Шаг 2 — кнопка: те же проверки чата и whitelist, не прошли → answerCallbackQuery без текста + лог.
  Предпросмотр старше 1 ч → LIFE_STALE, в БД не ходить. Иначе life.apply в одной транзакции;
  итог дописывается к предпросмотру, кнопки снимаются. Участнику — ничего.
- Ошибка БД → LIFE_TRY_LATER. Ошибка Telegram — только WARNING с именем класса.
Роутер ловит только Command("life") в группе и callback «life:…»; личку не ловит.
Подключается в bot/app.py в ветке config.card_enabled (рядом с /card).
Логи: без tg_user_id, pid, short_no — только код результата.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from bot import access, card, life, texts
from bot.config import BotConfig

logger = logging.getLogger(__name__)


def build_life_router(config: BotConfig, connect=None) -> Router:
    """connect(dsn) → psycopg.AsyncConnection; подменяется в тестах."""
    router = Router(name="life")
    connect = connect or access.connect

    async def _with_conn(fn):
        conn = await connect(config.database_url)
        try:
            return await fn(conn)
        finally:
            await conn.close()

    def _allowed(chat_id: int | None, user_id: int | None) -> bool:
        return chat_id == config.work_group_id and user_id in config.access_admin_ids

    async def _reply(message: Message, text: str, reply_markup=None) -> None:
        try:
            await message.reply(text, reply_markup=reply_markup)
        except Exception as exc:  # noqa: BLE001
            logger.warning("life: ответ не отправлен (%s)", type(exc).__name__)

    async def _answer(callback: CallbackQuery, text: str | None = None) -> None:
        try:
            await callback.answer(text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("life: answerCallbackQuery (%s)", type(exc).__name__)

    async def _finish(callback: CallbackQuery, note: str) -> None:
        """Дописать итог к предпросмотру и снять кнопки; ошибка Telegram — только лог."""
        msg = callback.message
        text = getattr(msg, "text", None) or ""
        try:
            await callback.bot.edit_message_text(chat_id=msg.chat.id, message_id=msg.message_id,
                                                 text=f"{text}\n\n{note}" if text else note, reply_markup=None)
        except Exception as exc:  # noqa: BLE001
            logger.warning("life: предпросмотр не изменён (%s)", type(exc).__name__)

    def _target(message: Message, command: CommandObject) -> tuple[str, int | None, int | None]:
        code, short_no, delta = life.parse_args(command.args)
        if code != "ok" or short_no is not None:
            return code, short_no, delta
        reply = message.reply_to_message
        # В теме форума каждое сообщение формально — reply на её первое сообщение (id = thread_id).
        if reply is None or reply.message_id == message.message_thread_id:
            return life.USAGE, None, None
        if reply.from_user is None or reply.from_user.id != message.bot.id:
            return life.NOT_FOUND, None, None
        short_no = card.number_from_reply(reply)
        if short_no is None:
            return life.NOT_FOUND, None, None
        return "ok", short_no, delta

    @router.message(F.chat.type.in_({"group", "supergroup"}), Command("life"))
    async def on_life(message: Message, command: CommandObject) -> None:
        user_id = message.from_user.id if message.from_user else None
        if not _allowed(message.chat.id, user_id):
            logger.warning("life: команда вне Рабочей группы или не из whitelist — игнор")
            return
        code, short_no, delta = _target(message, command)
        if code != "ok":
            logger.info("life: предпросмотр (%s)", code)
            await _reply(message, life.TEXT_FOR[code])
            return
        try:
            refusal, lives = await _with_conn(lambda c: life.preview(c, short_no, delta))
        except Exception as exc:  # noqa: BLE001
            logger.error("life: предпросмотр не собран (%s)", type(exc).__name__)
            await _reply(message, texts.LIFE_TRY_LATER)
            return
        if refusal is not None:
            logger.info("life: предпросмотр (%s)", refusal)
            await _reply(message, life.TEXT_FOR[refusal])
            return
        logger.info("life: предпросмотр (ok)")
        text = texts.LIFE_PREVIEW.format(num=f"{short_no:06d}", before=lives, after=lives + delta)
        await _reply(message, text, life.preview_keyboard(short_no, delta, life.new_op()))

    @router.callback_query(F.data.startswith(f"{life.CALLBACK_PREFIX}:"))
    async def on_button(callback: CallbackQuery) -> None:
        msg = callback.message
        chat_id = msg.chat.id if msg else None
        parsed = life.parse_callback(callback.data)
        if parsed is None or not _allowed(chat_id, callback.from_user.id):
            logger.warning("life: кнопка вне Рабочей группы или не из whitelist — игнор")
            await _answer(callback)
            return
        action, short_no, delta, op = parsed
        if action == life.CANCEL:
            logger.info("life: отменено")
            await _finish(callback, texts.LIFE_CANCELLED)
            await _answer(callback)
            return
        date = access.aware(getattr(msg, "date", None))
        if date is None or datetime.now(timezone.utc) - date > timedelta(seconds=life.STALE_SECONDS):
            logger.info("life: предпросмотр устарел")
            await _finish(callback, texts.LIFE_STALE)
            await _answer(callback)
            return
        try:
            code = await _with_conn(lambda c: life.apply(c, short_no, delta, op))
        except Exception as exc:  # noqa: BLE001
            logger.error("life: событие не записано (%s)", type(exc).__name__)
            await _answer(callback, texts.LIFE_TRY_LATER)
            return
        logger.info("life: подтверждение (%s)", code)
        await _finish(callback, life.TEXT_FOR[code])
        await _answer(callback)

    return router
