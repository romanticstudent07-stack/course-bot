"""apps/bot/bot/revive_handlers.py — роутер /revive (bot-revive-1).

- /revive [М.Д] (reply на пост бота), /revive #NNNNNN [М.Д] — только в Рабочей группе (тема любая)
  и только от ACCESS_ADMIN_IDS; иначе игнор + лог без вызовов Bot API и БД (как /life).
- Шаг 1 — предпросмотр без записи и без замка (revive.preview): отказ → текст отказа; иначе
  REVIVE_PREVIEW с кнопками [Подтвердить] «rvb:y:<номер>:<м>:<д>:<op>» и [Отмена] «rvb:n».
  lives_returned в callback не кладётся — на шаге 2 считается заново под замком.
- Шаг 2 — кнопка: те же проверки чата и whitelist, не прошли → answerCallbackQuery без текста + лог.
  Предпросмотр старше 1 ч → REVIVE_STALE, в БД не ходить. Иначе revive.apply в одной транзакции;
  итог дописывается к предпросмотру, кнопки снимаются. Только при DONE, после COMMIT —
  bot.send_message участнику (REVIVE_USER); ошибка Telegram — WARNING с именем класса.
- Ошибка БД → REVIVE_TRY_LATER.
Роутер ловит только Command("revive") в группе и callback «rvb:…»; личку не ловит.
Подключается в bot/app.py в ветке config.card_enabled сразу после /life.
Логи: без tg_user_id, pid, short_no, target — только код результата.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from bot import access, card, life, revive, texts
from bot.config import BotConfig

logger = logging.getLogger(__name__)


def build_revive_router(config: BotConfig, connect=None) -> Router:
    """connect(dsn) → psycopg.AsyncConnection; подменяется в тестах."""
    router = Router(name="revive")
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
            logger.warning("revive: ответ не отправлен (%s)", type(exc).__name__)

    async def _answer(callback: CallbackQuery, text: str | None = None) -> None:
        try:
            await callback.answer(text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("revive: answerCallbackQuery (%s)", type(exc).__name__)

    async def _finish(callback: CallbackQuery, note: str) -> None:
        """Дописать итог к предпросмотру и снять кнопки; ошибка Telegram — только лог."""
        msg = callback.message
        text = getattr(msg, "text", None) or ""
        try:
            await callback.bot.edit_message_text(chat_id=msg.chat.id, message_id=msg.message_id,
                                                 text=f"{text}\n\n{note}" if text else note, reply_markup=None)
        except Exception as exc:  # noqa: BLE001
            logger.warning("revive: предпросмотр не изменён (%s)", type(exc).__name__)

    def _target(message: Message, command: CommandObject):
        code, short_no, module_no, day_no = revive.parse_args(command.args)
        if code != "ok" or short_no is not None:
            return code, short_no, module_no, day_no
        reply = message.reply_to_message
        # В теме форума каждое сообщение формально — reply на её первое сообщение (id = thread_id).
        if reply is None or reply.message_id == message.message_thread_id:
            return revive.USAGE, None, None, None
        if reply.from_user is None or reply.from_user.id != message.bot.id:
            return revive.NOT_FOUND, None, None, None
        short_no = card.number_from_reply(reply)
        if short_no is None:
            return revive.NOT_FOUND, None, None, None
        return "ok", short_no, module_no, day_no

    @router.message(F.chat.type.in_({"group", "supergroup"}), Command("revive"))
    async def on_revive(message: Message, command: CommandObject) -> None:
        user_id = message.from_user.id if message.from_user else None
        if not _allowed(message.chat.id, user_id):
            logger.warning("revive: команда вне Рабочей группы или не из whitelist — игнор")
            return
        code, short_no, module_no, day_no = _target(message, command)
        if code != "ok":
            logger.info("revive: предпросмотр (%s)", code)
            await _reply(message, revive.TEXT_FOR[code])
            return
        try:
            result = await _with_conn(lambda c: revive.preview(c, short_no, module_no, day_no))
        except Exception as exc:  # noqa: BLE001
            logger.error("revive: предпросмотр не собран (%s)", type(exc).__name__)
            await _reply(message, texts.REVIVE_TRY_LATER)
            return
        if result.code is not None:
            logger.info("revive: предпросмотр (%s)", result.code)
            await _reply(message, revive.TEXT_FOR[result.code])
            return
        logger.info("revive: предпросмотр (ok)")
        s, m, d = result.position
        ts, tm, td = result.target
        text = texts.REVIVE_PREVIEW.format(num=f"{short_no:06d}", s=s, m=m, d=d, ts=ts, tm=tm, td=td,
                                           returned=result.returned, after=revive.lives_after(result.returned))
        await _reply(message, text, revive.preview_keyboard(short_no, tm, td, life.new_op()))

    @router.callback_query(F.data.startswith(f"{revive.CALLBACK_PREFIX}:"))
    async def on_button(callback: CallbackQuery) -> None:
        msg = callback.message
        chat_id = msg.chat.id if msg else None
        parsed = revive.parse_callback(callback.data)
        if parsed is None or not _allowed(chat_id, callback.from_user.id):
            logger.warning("revive: кнопка вне Рабочей группы или не из whitelist — игнор")
            await _answer(callback)
            return
        action, short_no, module_no, day_no, op = parsed
        if action == revive.CANCEL:
            logger.info("revive: отменено")
            await _finish(callback, texts.REVIVE_CANCELLED)
            await _answer(callback)
            return
        date = access.aware(getattr(msg, "date", None))
        if date is None or datetime.now(timezone.utc) - date > timedelta(seconds=life.STALE_SECONDS):
            logger.info("revive: предпросмотр устарел")
            await _finish(callback, texts.REVIVE_STALE)
            await _answer(callback)
            return
        try:
            result = await _with_conn(lambda c: revive.apply(c, short_no, module_no, day_no, op))
        except Exception as exc:  # noqa: BLE001
            logger.error("revive: событие не записано (%s)", type(exc).__name__)
            await _answer(callback, texts.REVIVE_TRY_LATER)
            return
        logger.info("revive: подтверждение (%s)", result.code)
        await _finish(callback, revive.TEXT_FOR[result.code])
        await _answer(callback)
        if result.code == revive.DONE and result.tg_user_id is not None:
            try:
                await callback.bot.send_message(result.tg_user_id, texts.REVIVE_USER)
            except Exception as exc:  # noqa: BLE001
                logger.warning("revive: участнику не отправлено (%s)", type(exc).__name__)

    return router
