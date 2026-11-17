"""apps/bot/bot/restart.py — рестарт по промокоду (bot-restart-1, Р-20, Р-2): SQL, eligible, ключи.

Участник с block_lives пишет боту промокод → заявка в админ-тему Рабочей группы
(кнопки [Выдать рестарт] / [Запретить]) → на «Выдать» бот пишет событие restart_paid
в participant_events; снимает block_lives и выдаёт день 1 модуля 1 текущего Этапа проектор (v6).

Вариант В (ШТАБ 17.11): access_grants и гейт Р-2 здесь не трогаются; заявка живёт только как
сообщение в теме, callback несёт short_no. Одна заявка в сутки — ключ restart_req:{pid}:{дата МСК}.
Фаза muted или erased → restart_paid не пишется (проектор v6 фазу не проверяет).
participant_state, outbox, access_grants бот здесь не пишет. RETURNING не используется.

Права app_bot (0009, 0011, 0013, 0018) — SQL ниже использует только их:
    tg_user_registry (pid, tg_user_id, tombstoned_at, short_no) — SELECT
    participant_state (lifecycle_phase, status_flags, stage_no) — SELECT
    idempotency_keys — INSERT (key, kind, result_ref), SELECT (key, result_ref)
    participant_events — INSERT (pid, kind, payload, actor, actor_role)
Замок participant:pid и has_flag — из bot/life.py. Только параметры %s.
Кодовое слово в БД не хранится (только в сообщении темы) и в лог не пишется.
Логи: без кодового слова, tg_user_id, pid, short_no — только код результата.
"""
from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass
from datetime import datetime

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from psycopg.types.json import Jsonb

from bot import texts
from bot.access import MSK, fmt_msk
from bot.life import LOCK, has_flag

logger = logging.getLogger(__name__)

# --- SQL ---
FIND_BY_TG = "SELECT pid, short_no FROM tg_user_registry WHERE tg_user_id = %s AND tombstoned_at IS NULL"
FIND_BY_SHORT = "SELECT pid, tg_user_id FROM tg_user_registry WHERE short_no = %s AND tombstoned_at IS NULL"
STATE = "SELECT lifecycle_phase, status_flags, stage_no FROM participant_state WHERE pid = %s"
REQUEST_KEY = (
    "INSERT INTO idempotency_keys (key, kind, result_ref) VALUES (%s, 'restart_req', NULL) "
    "ON CONFLICT (key) DO NOTHING"
)
DECISION_KEY = (
    "INSERT INTO idempotency_keys (key, kind, result_ref) VALUES (%s, 'restart', %s) "
    "ON CONFLICT (key) DO NOTHING"
)
RESULT = "SELECT result_ref FROM idempotency_keys WHERE key = %s"
EVENT = (
    "INSERT INTO participant_events (pid, kind, payload, actor, actor_role) "
    "VALUES (%s, 'restart_paid', %s, 'bot', 'owner')"
)

CALLBACK_PREFIX = "rst"
GRANT, DENY = "g", "d"
BIGINT_MAX = 9223372036854775807
REF_GRANTED, REF_DENIED = "granted", "denied"

# --- Коды заявки ---
NOTHING = "nothing"            # не eligible → тишина, как раньше
SENT = "sent"
ALREADY_TODAY = "already_today"
TRY_LATER = "try_later"

# --- Коды решения ---
DONE = "done"
DENIED = "denied"
ALREADY = "already"
REFUSED_STATE = "refused_state"
REFUSED_PHASE = "refused_phase"

_CALLBACK_RE = re.compile(rf"{CALLBACK_PREFIX}:([{GRANT}{DENY}]):(\d{{1,19}})")


@dataclass(frozen=True)
class Result:
    kind: str                      # DONE | DENIED | ALREADY | REFUSED_STATE | REFUSED_PHASE
    tg_user_id: int | None = None
    ref: str | None = None         # для ALREADY: result_ref записанного решения


def eligible(phase, flags, stage_no) -> bool:
    """block_lives, stage_no задан и фаза не muted / erased."""
    return has_flag(flags, "block_lives") and stage_no is not None and phase not in ("muted", "erased")


def refusal(phase, flags, stage_no) -> str | None:
    """Повторная проверка под замком (rst:g): код отказа или None. phase None — строки нет."""
    if phase is None:
        return REFUSED_STATE
    if phase in ("muted", "erased"):
        return REFUSED_PHASE
    if not has_flag(flags, "block_lives") or stage_no is None:
        return REFUSED_STATE
    return None


def request_key(pid, now: datetime) -> str:
    """restart_req:{pid}:{YYYY-MM-DD по Europe/Moscow}."""
    return f"restart_req:{pid}:{now.astimezone(MSK).date().isoformat()}"


def decision_key(pid, admin_message_id: int) -> str:
    return f"restart:{pid}:{admin_message_id}"


def callback_data(action: str, short_no: int) -> str:
    return f"{CALLBACK_PREFIX}:{action}:{short_no}"


def admin_keyboard(short_no: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=texts.RESTART_BUTTON_GRANT, callback_data=callback_data(GRANT, short_no)),
        InlineKeyboardButton(text=texts.RESTART_BUTTON_DENY, callback_data=callback_data(DENY, short_no)),
    ]])


def parse_callback(data: str | None) -> tuple[str, int] | None:
    """«rst:g:<short_no>» / «rst:d:<short_no>» → (действие, short_no); чужое → None."""
    m = _CALLBACK_RE.fullmatch(data or "")
    if m is None:
        return None
    short_no = int(m.group(2))
    if not 0 < short_no <= BIGINT_MAX:
        return None
    return m.group(1), short_no


def request_text(short_no: int, stage_no, word: str) -> str:
    """HTML; слово экранировано."""
    return texts.RESTART_REQUEST.format(num=f"{short_no:06d}", stage=html.escape(str(stage_no)),
                                        word=html.escape(word))


def user_text_for(code: str) -> str | None:
    """Ответ участнику на заявку; None — тишина."""
    return {
        SENT: texts.RESTART_REQUEST_SENT,
        ALREADY_TODAY: texts.RESTART_ALREADY_TODAY,
        TRY_LATER: texts.RESTART_TRY_LATER,
    }.get(code)


def admin_note_for(result: Result, now: datetime) -> str | None:
    """Итог, дописываемый к заявке в теме (ALREADY — отдельным сообщением в тему)."""
    if result.kind == DONE:
        return texts.RESTART_DONE.format(time=fmt_msk(now))
    if result.kind == DENIED:
        return texts.RESTART_DENIED_ADMIN.format(time=fmt_msk(now))
    if result.kind == REFUSED_PHASE:
        return texts.RESTART_REFUSED_PHASE
    if result.kind == REFUSED_STATE:
        return texts.RESTART_REFUSED_STATE
    return None


def already_text(ref: str | None) -> str:
    label = {REF_GRANTED: texts.RESTART_RESULT_GRANTED, REF_DENIED: texts.RESTART_RESULT_DENIED}.get(ref, "—")
    return texts.RESTART_ALREADY.format(result=label)


def user_text_for_result(result: Result) -> str | None:
    """Участнику после решения; при отказах и ALREADY — ничего."""
    return {DONE: texts.RESTART_GRANTED, DENIED: texts.RESTART_DENIED}.get(result.kind)


# --- БД ---

class _SendFailed(Exception):
    """Отправка в тему не удалась → ROLLBACK."""


class _Refused(Exception):
    """Отказ внутри транзакции → откат (ключ не пишется)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


async def submit_request(conn, bot, config, tg_user_id: int, word_text: str, now: datetime) -> str:
    """Текст при вердикте доступа NOTHING → код заявки. Запись — одна транзакция."""
    cur = await conn.execute(FIND_BY_TG, (tg_user_id,))
    found = await cur.fetchone()
    if found is None:
        return NOTHING
    pid, short_no = found
    cur = await conn.execute(STATE, (pid,))
    state = await cur.fetchone()
    if state is None or not eligible(*state):
        return NOTHING
    stage_no = state[2]
    try:
        async with conn.transaction():
            await conn.execute(LOCK, (str(pid),))
            cur = await conn.execute(REQUEST_KEY, (request_key(pid, now),))
            if cur.rowcount == 0:
                return ALREADY_TODAY
            try:
                await bot.send_message(
                    chat_id=config.work_group_id,
                    message_thread_id=config.access_admin_topic_id,
                    text=request_text(short_no, stage_no, (word_text or "").strip()),
                    parse_mode="HTML",
                    reply_markup=admin_keyboard(short_no),
                )
            except Exception as exc:  # noqa: BLE001 — любая ошибка Telegram → откат
                logger.warning("restart: заявка не отправлена в тему (%s)", type(exc).__name__)
                raise _SendFailed from None
    except _SendFailed:
        return TRY_LATER
    logger.info("restart: заявка отправлена в тему")
    return SENT


async def decide(conn, action: str, short_no: int, admin_message_id: int) -> Result:
    """Решение по кнопке rst в одной транзакции. Отказ → откат, ключ не пишется."""
    try:
        async with conn.transaction():
            cur = await conn.execute(FIND_BY_SHORT, (short_no,))
            found = await cur.fetchone()
            if found is None:
                raise _Refused(REFUSED_STATE)
            pid, tg_user_id = found
            await conn.execute(LOCK, (str(pid),))
            key = decision_key(pid, admin_message_id)
            ref = REF_GRANTED if action == GRANT else REF_DENIED
            cur = await conn.execute(DECISION_KEY, (key, ref))
            if cur.rowcount == 0:
                cur = await conn.execute(RESULT, (key,))
                row = await cur.fetchone()
                return Result(ALREADY, tg_user_id, None if row is None else row[0])
            if action != GRANT:
                result = Result(DENIED, tg_user_id)
            else:
                cur = await conn.execute(STATE, (pid,))
                state = await cur.fetchone()
                code = refusal(*(state if state is not None else (None, None, None)))
                if code is not None:
                    raise _Refused(code)
                await conn.execute(EVENT, (pid, Jsonb({"admin_message_id": admin_message_id})))
                result = Result(DONE, tg_user_id)
    except _Refused as refused:
        logger.info("restart: отказ (%s)", refused.code)
        return Result(refused.code)
    logger.info("restart: решение записано (%s)", result.kind)
    return result
