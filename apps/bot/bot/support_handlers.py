"""apps/bot/bot/support_handlers.py — ответ Автора на вопрос поддержки (bot-sup-1, Р-19).

Только Рабочая группа (WORK_GROUP_ID), только 8 тем поддержки (BotConfig.support_thread_ids),
только ACCESS_ADMIN_IDS; чужим колбэкам — answerCallbackQuery без текста + WARNING.
- «✉️ Ответить» (sup:r:N) → промпт SUPPORT_PROMPT ответом на пост, ForceReply (без selective).
- Ответ админа reply на промпт бота → предпросмотр SUPPORT_PREVIEW + «\\n\\n» + текст, без parse_mode,
  кнопки «Отправить» (sup:s:N) / «Отмена» (sup:x:N). Вся проверка — в фильтре: чужие сообщения
  группы роутер не глотает.
- «Отправить»: N колбэка = N заголовка предпросмотра → SUPPORT_Q → PARTICIPANT; стёрт или нет —
  участнику ничего, «Не доставлено» (I4 P455). Иначе снять кнопки («message is not modified» —
  второе нажатие, стоп) → личка участнику от имени бота → «Доставлено» / «Не доставлено».
- «Отмена» — снять кнопки, участнику ничего.
Состояния в памяти нет: N — из callback_data и первой строки своих сообщений (bot/support.py).
Подключается, только если config.support_enabled (bot/app.py).
Логи: только имя класса ошибки. Никогда: tg_user_id, pid, short_no, N, тексты вопроса и ответа.
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, ForceReply, Message

from bot import access, support, texts
from bot.config import BotConfig

logger = logging.getLogger(__name__)

MAX_ANSWER_LEN = 2000


def build_support_router(config: BotConfig, connect=None) -> Router:
    """connect(dsn) → psycopg.AsyncConnection; подменяется в тестах."""
    router = Router(name="support")
    connect = connect or access.connect

    def _allowed(chat_id, thread_id, user_id) -> bool:
        return (
            chat_id == config.work_group_id
            and thread_id in config.support_thread_ids()
            and user_id in config.access_admin_ids
        )

    async def _safe(what: str, coro) -> bool:
        """Вызов Bot API; ошибка — WARNING с именем класса. True — успех."""
        try:
            await coro
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("support: %s (%s)", what, type(exc).__name__)
            return False

    async def _answer(callback: CallbackQuery, text: str | None = None) -> None:
        await _safe("answerCallbackQuery", callback.answer(text) if text else callback.answer())

    async def _load(n: int):
        """SUPPORT_Q(N) → PARTICIPANT(pid) → (tg_user_id, tombstoned_at) или None. Ошибка БД пробрасывается."""
        conn = await connect(config.database_url)
        try:
            cur = await conn.execute(support.SUPPORT_Q, (n,))
            question = await cur.fetchone()
            if question is None:
                return None
            cur = await conn.execute(support.PARTICIPANT, (question[0],))
            return await cur.fetchone()
        finally:
            await conn.close()

    def _is_admin_reply(message: Message) -> bool:
        """Фильтр: reply админа в теме поддержки на промпт ✉️ этого бота."""
        chat = getattr(message, "chat", None)
        if chat is None or chat.type not in ("group", "supergroup"):
            return False
        user = getattr(message, "from_user", None)
        if not _allowed(chat.id, message.message_thread_id, user.id if user else None):
            return False
        reply = message.reply_to_message
        # В теме форума каждое сообщение формально — reply на её первое сообщение (id = thread_id).
        if reply is None or reply.message_id == message.message_thread_id:
            return False
        if reply.from_user is None or reply.from_user.id != message.bot.id:
            return False
        return support.n_from_prompt(reply.text) is not None

    @router.message(_is_admin_reply)
    async def on_answer(message: Message) -> None:
        n = support.n_from_prompt(message.reply_to_message.text)
        if not message.text:
            await _safe("ответ не отправлен", message.reply(texts.SUPPORT_SEND_TEXT))
            return
        if len(message.text) > MAX_ANSWER_LEN:
            await _safe("ответ не отправлен", message.reply(texts.SUPPORT_TOO_LONG))
            return
        await _safe(
            "предпросмотр не отправлен",
            message.reply(texts.SUPPORT_PREVIEW.format(n=n) + "\n\n" + message.text,
                          reply_markup=support.preview_markup(n)),
        )

    @router.callback_query(F.data.startswith(f"{support.CALLBACK_PREFIX}:"))
    async def on_button(callback: CallbackQuery) -> None:
        msg = callback.message
        chat_id = msg.chat.id if msg else None
        thread_id = getattr(msg, "message_thread_id", None) if msg else None
        if not _allowed(chat_id, thread_id, callback.from_user.id):
            logger.warning("support: кнопка вне темы поддержки или не из whitelist — игнор")
            await _answer(callback)
            return
        parsed = support.parse_callback(callback.data)
        if parsed is None:
            logger.warning("support: кривой callback — игнор")
            await _answer(callback)
            return
        action, n = parsed
        if action == support.ACTION_REPLY:
            await _safe("промпт не отправлен",
                        msg.reply(texts.SUPPORT_PROMPT.format(n=n), reply_markup=ForceReply()))
            await _answer(callback)
            return
        bot = callback.bot
        if action == support.ACTION_CANCEL:
            await _safe("кнопки не сняты",
                        bot.edit_message_reply_markup(chat_id=chat_id, message_id=msg.message_id,
                                                      reply_markup=None))
            await _answer(callback)
            return
        # Отправить.
        preview = support.n_from_preview(getattr(msg, "text", None))
        if preview is None or preview[0] != n:
            logger.warning("support: предпросмотр не совпал с кнопкой — игнор")
            await _answer(callback)
            return
        body = preview[1]
        try:
            participant = await _load(n)
        except Exception as exc:  # noqa: BLE001
            logger.error("support: БД недоступна (%s)", type(exc).__name__)
            await _answer(callback, texts.SUPPORT_TRY_LATER)
            return
        if participant is None or participant[1] is not None:
            logger.info("support: участник не найден или стёрт — не доставлено")
            await _safe("предпросмотр не изменён",
                        bot.edit_message_text(chat_id=chat_id, message_id=msg.message_id,
                                              text=texts.SUPPORT_NOT_DELIVERED.format(n=n) + "\n\n" + body,
                                              reply_markup=None))
            await _answer(callback)
            return
        try:
            await bot.edit_message_reply_markup(chat_id=chat_id, message_id=msg.message_id, reply_markup=None)
        except TelegramBadRequest as exc:
            if "message is not modified" in (exc.message or "").lower():
                logger.info("support: повторное нажатие «Отправить» — игнор")
            else:
                logger.warning("support: кнопки не сняты (%s)", type(exc).__name__)
            await _answer(callback)
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("support: кнопки не сняты (%s)", type(exc).__name__)
            await _answer(callback)
            return
        sent = await _safe("ответ участнику не отправлен",
                           bot.send_message(chat_id=participant[0],
                                            text=texts.SUPPORT_ANSWER_PREFIX + "\n\n" + body))
        header = texts.SUPPORT_DELIVERED if sent else texts.SUPPORT_NOT_DELIVERED
        await _safe("предпросмотр не изменён",
                    bot.edit_message_text(chat_id=chat_id, message_id=msg.message_id,
                                          text=header.format(n=n) + "\n\n" + body))
        if sent:
            logger.info("support: ответ доставлен")
        await _answer(callback)

    return router
