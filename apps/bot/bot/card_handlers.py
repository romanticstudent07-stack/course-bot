"""apps/bot/bot/card_handlers.py — роутер карточки участника (bot-i3-1).

- /card #NNNNNN или /card ответом (reply) на пост бота — в Рабочей группе (тема любая),
  только от ACCESS_ADMIN_IDS; иначе игнор + лог без вызовов Bot API и БД.
- Кнопка «card:<номер>» (ставит bot-i3-2): только из Рабочей группы и от whitelist;
  иначе answerCallbackQuery без текста + лог.
- Карточка (bot/card.py) уходит только в WORK_GROUP_ID, тему CARDS_TOPIC_ID; до отправки — аудит.
  Успех: на /card — ничего; на кнопку — CARD_SENT. Ошибка БД или отправки — CARD_TRY_LATER.
- Номер из reply без кнопки — только строка-подпись GROUP_WHO целиком (card.number_from_reply).
- Номер — до 19 цифр; больше bigint → как нет номера (CARD_ASK_ID / CARD_NOT_FOUND).
- Все ответы на /card — через _reply: сбой Telegram → WARNING с именем класса, обработчик не падает.
Роутер ловит только Command("card") и callback «card:…»; личку не ловит.
Подключается, только если config.card_enabled (bot/app.py).
Логи: без tg_user_id, pid, short_no и текста карточки.
"""
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from bot import access, card, texts
from bot.config import BotConfig

logger = logging.getLogger(__name__)


def build_card_router(config: BotConfig, connect=None) -> Router:
    """connect(dsn) → psycopg.AsyncConnection; подменяется в тестах."""
    router = Router(name="card")
    connect = connect or access.connect

    async def _with_conn(fn):
        conn = await connect(config.database_url)
        try:
            return await fn(conn)
        finally:
            await conn.close()

    def _allowed(chat_id: int | None, user_id: int | None) -> bool:
        return chat_id == config.work_group_id and user_id in config.access_admin_ids

    async def _reply(message: Message, text: str) -> None:
        """Ответ на /card; ошибка Telegram — только WARNING с именем класса."""
        try:
            await message.reply(text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("card: ответ не отправлен (%s)", type(exc).__name__)

    async def _deliver(bot: Bot, short_no: int, actor_id: int) -> str | None:
        """Собрать, записать аудит, отправить. None — успех, иначе текст ответа."""
        try:
            text = await _with_conn(lambda c: card.load_and_audit(c, short_no, str(actor_id)))
        except Exception as exc:  # noqa: BLE001
            logger.error("card: карточка не собрана (%s)", type(exc).__name__)
            return texts.CARD_TRY_LATER
        if text is None:
            return texts.CARD_NOT_FOUND
        try:
            await bot.send_message(chat_id=config.work_group_id, message_thread_id=config.cards_topic_id,
                                   text=text, parse_mode="HTML")
        except Exception as exc:  # noqa: BLE001
            logger.warning("card: карточка не отправлена (%s)", type(exc).__name__)
            return texts.CARD_TRY_LATER
        logger.info("card: карточка отправлена")
        return None

    @router.message(F.chat.type.in_({"group", "supergroup"}), Command("card"))
    async def on_card(message: Message, command: CommandObject) -> None:
        user_id = message.from_user.id if message.from_user else None
        if not _allowed(message.chat.id, user_id):
            logger.warning("card: команда вне Рабочей группы или не из whitelist — игнор")
            return
        if command.args:
            short_no = card.parse_arg(command.args)
            if short_no is None:
                await _reply(message, texts.CARD_ASK_ID)
                return
        else:
            reply = message.reply_to_message
            # В теме форума каждое сообщение формально — reply на её первое сообщение (id = thread_id).
            if reply is None or reply.message_id == message.message_thread_id:
                await _reply(message, texts.CARD_ASK_ID)
                return
            if reply.from_user is None or reply.from_user.id != message.bot.id:
                await _reply(message, texts.CARD_NOT_FOUND)
                return
            short_no = card.number_from_reply(reply)
            if short_no is None:
                await _reply(message, texts.CARD_NOT_FOUND)
                return
        answer = await _deliver(message.bot, short_no, user_id)
        if answer:
            await _reply(message, answer)

    @router.callback_query(F.data.startswith(f"{card.CALLBACK_PREFIX}:"))
    async def on_button(callback: CallbackQuery) -> None:
        msg = callback.message
        chat_id = msg.chat.id if msg else None
        short_no = card.parse_callback(callback.data)
        if short_no is None or not _allowed(chat_id, callback.from_user.id):
            logger.warning("card: кнопка вне Рабочей группы или не из whitelist — игнор")
            await callback.answer()
            return
        answer = await _deliver(callback.bot, short_no, callback.from_user.id)
        try:
            await callback.answer(answer or texts.CARD_SENT)
        except Exception as exc:  # noqa: BLE001
            logger.warning("card: answerCallbackQuery (%s)", type(exc).__name__)

    return router
