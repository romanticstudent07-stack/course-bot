"""apps/bot/bot/access_handlers.py — роутер доступа по промокоду (bot-access-1, Р-2).

- Личка: текст (не команда) от пользователя без доступа → заявка в админ-тему (bot/access.py);
  не текст и команды, кроме /start, → SEND_TEXT. /start — bot/handlers.py.
- Кнопки «acc:g:<id>» / «acc:d:<id>»: только из админ-темы (WORK_GROUP_ID + ACCESS_ADMIN_TOPIC_ID)
  и от ACCESS_ADMIN_IDS; иначе answerCallbackQuery без текста + лог.
- Команды /access_grant и /access_deny (Command учитывает @BotName): только из темы и от whitelist,
  иначе игнор + лог; без reply → REPLY_REQUIRED; reply не на заявку бота → REQUEST_NOT_FOUND.
- После COMMIT: заявке в теме дописывается итог и снимаются кнопки; пользователю — ответ.
  Ошибки Telegram после COMMIT только логируются: решение уже записано.
Роутер подключается, только если config.access_enabled (bot/app.py).
Логи: без кодового слова, имени, username и tg_user_id.
"""
from __future__ import annotations

import html
import logging
from datetime import datetime, timezone

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot import access, texts
from bot.config import BotConfig
from bot.handlers import menu_button, webapp_keyboard

logger = logging.getLogger(__name__)

IGNORE = "ignore"
REPLY_REQUIRED = "reply_required"
OK = "ok"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def command_precheck(config: BotConfig, message: Message) -> str:
    """Фильтр команд Панели: IGNORE (чужой чат/тема/не whitelist), REPLY_REQUIRED или OK."""
    user_id = message.from_user.id if message.from_user else None
    if not access.is_admin_context(config, message.chat.id, message.message_thread_id, user_id):
        return IGNORE
    reply = message.reply_to_message
    # В теме форума каждое сообщение формально — reply на её первое сообщение (id = thread_id).
    if reply is None or reply.message_id == message.message_thread_id:
        return REPLY_REQUIRED
    return OK


async def grant_menu(bot: Bot, config: BotConfig, tg_user_id: int) -> None:
    """Меню-кнопка Mini App — только при granted."""
    if not config.webapp_enabled:
        return
    try:
        await bot.set_chat_menu_button(chat_id=tg_user_id, menu_button=menu_button(config.webapp_url))
    except Exception as exc:  # noqa: BLE001
        logger.warning("access: menu button не поставлена (%s)", type(exc).__name__)


async def after_commit(bot: Bot, config: BotConfig, decision: access.Decision, chat_id: int,
                       message_id: int, original_html: str, now: datetime) -> None:
    """Итог в теме + ответ пользователю. Ошибки Telegram — только в лог."""
    note = access.admin_note_for(decision, config.access_max_denies, now)
    if note is None:
        return
    try:
        await bot.edit_message_text(
            chat_id=chat_id, message_id=message_id, text=f"{original_html}\n\n{html.escape(note)}",
            parse_mode="HTML", reply_markup=None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("access: заявка в теме не обновлена (%s)", type(exc).__name__)
    user_text = access.user_text_for_decision(decision, config.access_max_denies)
    markup = None
    if decision.kind == access.GRANTED:
        await grant_menu(bot, config, decision.tg_user_id)
        if config.webapp_enabled:
            markup = webapp_keyboard(config.webapp_url)
    try:
        await bot.send_message(chat_id=decision.tg_user_id, text=user_text, reply_markup=markup)
    except Exception as exc:  # noqa: BLE001
        logger.warning("access: пользователю не отправлено (%s)", type(exc).__name__)


def build_access_router(config: BotConfig, connect=None) -> Router:
    """connect(dsn) → psycopg.AsyncConnection; подменяется в тестах."""
    router = Router(name="access")
    connect = connect or access.connect

    async def _with_conn(fn):
        conn = await connect(config.database_url)
        try:
            return await fn(conn)
        finally:
            await conn.close()

    # --- Админ-тема: кнопки ---
    @router.callback_query(F.data.startswith(f"{access.CALLBACK_PREFIX}:"))
    async def on_button(callback: CallbackQuery) -> None:
        msg = callback.message
        parsed = access.parse_callback(callback.data)
        chat_id = msg.chat.id if msg else None
        thread_id = getattr(msg, "message_thread_id", None) if msg else None
        if parsed is None or not access.is_admin_context(config, chat_id, thread_id, callback.from_user.id):
            logger.warning("access: кнопка вне темы или не из whitelist — игнор")
            await callback.answer()
            return
        action, tg_user_id = parsed
        now = _now()
        try:
            decision = await _with_conn(lambda c: access.decide(
                c, config, action, tg_user_id, msg.message_id, callback.from_user.id, now))
        except Exception as exc:  # noqa: BLE001
            logger.error("access: решение не записано (%s)", type(exc).__name__)
            await callback.answer(texts.ACCESS_TRY_LATER)
            return
        await after_commit(callback.bot, config, decision, msg.chat.id, msg.message_id,
                           getattr(msg, "html_text", "") or "", now)
        try:
            await callback.answer(access.admin_reply_for(decision))
        except Exception as exc:  # noqa: BLE001
            logger.warning("access: answerCallbackQuery (%s)", type(exc).__name__)

    # --- Админ-тема: команды ---
    async def _on_command(message: Message, action: str) -> None:
        check = command_precheck(config, message)
        if check == IGNORE:
            logger.warning("access: команда вне темы или не из whitelist — игнор")
            return
        if check == REPLY_REQUIRED:
            await message.reply(texts.ACCESS_REPLY_REQUIRED)
            return
        reply = message.reply_to_message
        now = _now()

        async def run(conn):
            tg_user_id = await access.find_by_message(conn, reply.message_id)
            if tg_user_id is None:
                return access.Decision(access.NOT_FOUND)
            return await access.decide(conn, config, action, tg_user_id, reply.message_id,
                                       message.from_user.id, now)

        try:
            decision = await _with_conn(run)
        except Exception as exc:  # noqa: BLE001
            logger.error("access: решение не записано (%s)", type(exc).__name__)
            await message.reply(texts.ACCESS_TRY_LATER)
            return
        await after_commit(message.bot, config, decision, message.chat.id, reply.message_id,
                           reply.html_text or "", now)
        answer = access.admin_reply_for(decision)
        if answer:
            try:
                await message.reply(answer)
            except Exception as exc:  # noqa: BLE001
                logger.warning("access: ответ админу не отправлен (%s)", type(exc).__name__)

    @router.message(Command("access_grant"), F.chat.type.in_({"group", "supergroup"}))
    async def on_grant(message: Message) -> None:
        await _on_command(message, access.GRANT)

    @router.message(Command("access_deny"), F.chat.type.in_({"group", "supergroup"}))
    async def on_deny(message: Message) -> None:
        await _on_command(message, access.DENY)

    # --- Личка: всё, кроме /start (его ловит bot/handlers.py раньше) ---
    @router.message(F.chat.type == "private")
    async def on_private(message: Message) -> None:
        if message.from_user is None:
            return
        uid = message.from_user.id
        now = _now()
        is_word = bool(message.text) and not message.text.startswith("/")
        try:
            if is_word:
                who = access.user_label(uid, message.from_user.first_name, message.from_user.last_name,
                                        message.from_user.username)
                kind, until = await _with_conn(lambda c: access.submit_request(
                    c, message.bot, config, uid, message.text, who, now))
            else:  # не текст или команда: granted → ничего, иначе SEND_TEXT (раздел 7)
                verdict = await _with_conn(lambda c: access.read_state(c, uid, now))
                kind, until = (access.NOTHING if verdict.kind == access.NOTHING else access.SEND_TEXT), None
        except Exception as exc:  # noqa: BLE001
            logger.error("access: ошибка обработки (%s)", type(exc).__name__)
            kind, until = access.TRY_LATER, None
        text = access.user_text_for(kind, until)
        if text:
            await message.answer(text)

    return router
