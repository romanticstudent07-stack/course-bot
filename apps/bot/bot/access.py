"""apps/bot/bot/access.py — доступ по промокоду (bot-access-1, Р-2): SQL, переходы, чистые функции.

Поток: человек без доступа пишет боту кодовое слово → заявка в админ-тему Рабочей группы
(кнопки [Выдать доступ] / [Запретить]) → Автор решает кнопкой или командой
/access_grant, /access_deny (reply на заявку) → флажок в access_grants (миграция 0010).

Права app_bot (0010, PRIVILEGES) — SQL ниже использует только их:
    SELECT (tg_user_id, status, deny_count, locked_until, admin_message_id, requested_at,
            decided_at, decided_by)
    INSERT (tg_user_id, status, deny_count, locked_until, admin_message_id, requested_at, created_via)
    UPDATE (status, deny_count, locked_until, admin_message_id, requested_at, decided_at,
            decided_by, updated_at)
created_at и created_via не читаются. Только параметры %s.

Гонки: новая заявка — pg_advisory_xact_lock(hashtextextended('access_grants:' || id, 0)) (строки
может ещё не быть, FOR UPDATE нечего держать) + SELECT … FOR UPDATE; решение — SELECT … FOR UPDATE,
deny — условный UPDATE (status = 'pending' AND admin_message_id). Одна задача — одна транзакция.

Кодовое слово в БД не хранится (только в сообщении темы) и в лог не пишется. Имя, username и
tg_user_id в лог не пишутся. «Сейчас» передаётся параметром (UTC); время для людей — МСК.

Строка = последняя заявка + последнее решение: новая заявка (UPSERT_REQUEST) decided_at / decided_by
не сбрасывает. Соединение — lock_timeout 10s: ожидание блокировки дольше → исключение → TRY_LATER.
"""
from __future__ import annotations

import html
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import psycopg
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import texts

logger = logging.getLogger(__name__)

MSK = ZoneInfo("Europe/Moscow")
WORD_MAX_LEN = 64
CONNECT_TIMEOUT = 10
LOCK_TIMEOUT = "10s"
CALLBACK_PREFIX = "acc"
GRANT, DENY = "g", "d"

# --- SQL ---
LOCK = "SELECT pg_advisory_xact_lock(hashtextextended('access_grants:' || %s::text, 0))"
STATE = "SELECT status, deny_count, locked_until, admin_message_id FROM access_grants WHERE tg_user_id = %s"
STATE_FOR_UPDATE = STATE + " FOR UPDATE"
FIND_BY_MESSAGE = "SELECT tg_user_id FROM access_grants WHERE admin_message_id = %s"
UPSERT_REQUEST = (
    "INSERT INTO access_grants (tg_user_id, status, admin_message_id, requested_at, "
    "deny_count, locked_until, created_via) "
    "VALUES (%s, 'pending', %s, %s, %s, NULL, 'bot_promo') "
    "ON CONFLICT (tg_user_id) DO UPDATE SET status = EXCLUDED.status, "
    "admin_message_id = EXCLUDED.admin_message_id, requested_at = EXCLUDED.requested_at, "
    "deny_count = EXCLUDED.deny_count, locked_until = EXCLUDED.locked_until, updated_at = now()"
)
GRANT_UPDATE = (
    "UPDATE access_grants SET status = 'granted', deny_count = 0, locked_until = NULL, "
    "decided_at = %s, decided_by = %s, updated_at = now() WHERE tg_user_id = %s"
)
DENY_UPDATE = (
    "UPDATE access_grants SET status = 'denied', deny_count = deny_count + 1, locked_until = %s, "
    "decided_at = %s, decided_by = %s, updated_at = now() "
    "WHERE tg_user_id = %s AND status = 'pending' AND admin_message_id = %s"
)

# --- Переходы (раздел 7) ---
NOTHING = "nothing"      # функция выключена или granted
PENDING = "pending"
LOCKED = "locked"
NEW = "new"              # нет строки, denied или пауза кончилась
SEND_TEXT = "send_text"
SENT = "sent"
TRY_LATER = "try_later"

# --- Исходы решения (раздел 9) ---
GRANTED = "granted"
DENIED = "denied"
ALREADY_GRANTED = "already_granted"
ALREADY_DECIDED = "already_decided"
NOT_FOUND = "not_found"


@dataclass(frozen=True)
class Row:
    status: str
    deny_count: int
    locked_until: datetime | None
    admin_message_id: int | None


@dataclass(frozen=True)
class Verdict:
    kind: str                       # NOTHING | PENDING | LOCKED | NEW
    locked_until: datetime | None = None
    deny_count: int = 0             # для NEW: счётчик, с которым пишется заявка


@dataclass(frozen=True)
class Decision:
    kind: str                       # GRANTED | DENIED | ALREADY_GRANTED | ALREADY_DECIDED | NOT_FOUND
    tg_user_id: int | None = None
    deny_count: int = 0
    locked_until: datetime | None = None


def aware(value: datetime | None) -> datetime | None:
    """timestamptz без пояса → считать UTC."""
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def fmt_msk(value: datetime) -> str:
    """«дд.мм.гггг чч:мм МСК» (Europe/Moscow явно)."""
    return aware(value).astimezone(MSK).strftime("%d.%m.%Y %H:%M") + " МСК"


def to_row(raw) -> Row | None:
    if raw is None:
        return None
    status, deny_count, locked_until, admin_message_id = raw
    return Row(status, int(deny_count or 0), aware(locked_until), admin_message_id)


def classify(row: Row | None, now: datetime) -> Verdict:
    """Раздел 7: что делать с текстом от пользователя при этой строке."""
    if row is None:
        return Verdict(NEW, deny_count=0)
    if row.status == "granted":
        return Verdict(NOTHING)
    if row.status == "pending":
        return Verdict(PENDING)
    if row.locked_until is not None:
        if row.locked_until > now:
            return Verdict(LOCKED, locked_until=row.locked_until)
        return Verdict(NEW, deny_count=0)  # пауза кончилась: deny_count = 0, locked_until = NULL
    return Verdict(NEW, deny_count=row.deny_count)


def clean_word(text: str | None) -> str | None:
    """Слово после strip; пустое или длиннее 64 → None."""
    word = (text or "").strip()
    if not word or len(word) > WORD_MAX_LEN:
        return None
    return word


def user_label(tg_user_id: int, first_name: str | None, last_name: str | None, username: str | None) -> str:
    """«Имя (@username · ID N) → написать» со ссылкой tg://user?id=N; всё экранировано (08 §8.5)."""
    name = " ".join(p for p in (first_name, last_name) if p) or "—"
    inner = f"@{html.escape(username)} · ID {tg_user_id}" if username else f"ID {tg_user_id}"
    link = f'<a href="tg://user?id={tg_user_id}">{html.escape(texts.ACCESS_ADMIN_WRITE)}</a>'
    return f"{html.escape(name)} ({inner}) → {link}"


def admin_request_text(word: str, who: str) -> str:
    return texts.ACCESS_ADMIN_REQUEST.format(word=html.escape(word), who=who)


def admin_keyboard(tg_user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text=texts.ACCESS_BUTTON_GRANT, callback_data=f"{CALLBACK_PREFIX}:{GRANT}:{tg_user_id}"),
            InlineKeyboardButton(text=texts.ACCESS_BUTTON_DENY, callback_data=f"{CALLBACK_PREFIX}:{DENY}:{tg_user_id}"),
        ]]
    )


def parse_callback(data: str | None) -> tuple[str, int] | None:
    """«acc:g:<id>» / «acc:d:<id>» → (действие, tg_user_id); чужое → None."""
    parts = (data or "").split(":")
    if len(parts) != 3 or parts[0] != CALLBACK_PREFIX or parts[1] not in (GRANT, DENY):
        return None
    try:
        tg_user_id = int(parts[2])
    except ValueError:
        return None
    return (parts[1], tg_user_id) if tg_user_id > 0 else None


def is_admin_context(config, chat_id: int | None, thread_id: int | None, user_id: int | None) -> bool:
    """Решать может только whitelist и только из админ-темы Рабочей группы."""
    return (
        config.access_enabled
        and chat_id == config.work_group_id
        and thread_id == config.access_admin_topic_id
        and user_id in config.access_admin_ids
    )


def deny_result(deny_count_after: int, max_denies: int, lock_hours: int, now: datetime) -> datetime | None:
    """Пауза после отказа: deny_count ≥ ACCESS_MAX_DENIES → сейчас + ACCESS_LOCK_HOURS, иначе None."""
    if deny_count_after >= max_denies:
        return now + timedelta(hours=lock_hours)
    return None


def user_text_for(verdict_kind: str, locked_until: datetime | None = None) -> str | None:
    """Ответ пользователю на текст / /start по исходу раздела 7."""
    if verdict_kind == PENDING:
        return texts.ACCESS_PENDING
    if verdict_kind == LOCKED:
        return texts.ACCESS_LOCKED.format(until=fmt_msk(locked_until))
    if verdict_kind == SEND_TEXT:
        return texts.ACCESS_SEND_TEXT
    if verdict_kind == SENT:
        return texts.ACCESS_REQUEST_SENT
    if verdict_kind == TRY_LATER:
        return texts.ACCESS_TRY_LATER
    return None


def user_text_for_decision(decision: Decision, max_denies: int) -> str | None:
    """Ответ пользователю после решения; None — пользователю ничего."""
    if decision.kind == GRANTED:
        return texts.ACCESS_GRANTED
    if decision.kind != DENIED:
        return None
    if decision.locked_until is not None:
        return texts.ACCESS_LOCKED.format(until=fmt_msk(decision.locked_until))
    left = max_denies - decision.deny_count
    if left == 1:
        return texts.ACCESS_DENIED_LAST
    return texts.ACCESS_DENIED_RETRY.format(n=left)


def admin_note_for(decision: Decision, max_denies: int, now: datetime) -> str | None:
    """Итог, дописываемый к заявке в теме; None — сообщение не правится."""
    if decision.kind == GRANTED:
        return texts.ACCESS_ADMIN_GRANTED.format(time=fmt_msk(now))
    if decision.kind == DENIED:
        return texts.ACCESS_ADMIN_DENIED.format(k=decision.deny_count, max=max_denies, time=fmt_msk(now))
    return None


def admin_reply_for(decision: Decision) -> str | None:
    """Ответ админу, если решение не записано."""
    return {
        ALREADY_GRANTED: texts.ACCESS_ALREADY_GRANTED,
        ALREADY_DECIDED: texts.ACCESS_ALREADY_DECIDED,
        NOT_FOUND: texts.ACCESS_REQUEST_NOT_FOUND,
    }.get(decision.kind)


# --- БД ---

async def connect(dsn: str):
    """Соединение на запрос (autocommit; транзакции — явно)."""
    return await psycopg.AsyncConnection.connect(dsn, autocommit=True, connect_timeout=CONNECT_TIMEOUT,
                                                 options=f"-c lock_timeout={LOCK_TIMEOUT}")


async def read_state(conn, tg_user_id: int, now: datetime) -> Verdict:
    """Без блокировки — для /start и не-текста."""
    cur = await conn.execute(STATE, (tg_user_id,))
    return classify(to_row(await cur.fetchone()), now)


class _SendFailed(Exception):
    """Отправка в тему не удалась → ROLLBACK."""


async def submit_request(conn, bot, config, tg_user_id: int, word_text: str | None, who: str,
                         now: datetime) -> tuple[str, datetime | None]:
    """Текст от пользователя → (исход раздела 7/8, locked_until). Одна транзакция.

    Если UPSERT/COMMIT упал после отправки в тему — в теме остаётся заявка-сирота; удалять её нельзя
    (COMMIT мог пройти). Нажатие на сироту даёт NOT_FOUND или ALREADY_DECIDED; при ALREADY_* кнопки снимаются.
    """
    try:
        async with conn.transaction():
            await conn.execute(LOCK, (tg_user_id,))
            cur = await conn.execute(STATE_FOR_UPDATE, (tg_user_id,))
            verdict = classify(to_row(await cur.fetchone()), now)
            if verdict.kind != NEW:
                return verdict.kind, verdict.locked_until
            word = clean_word(word_text)
            if word is None:
                return SEND_TEXT, None
            try:
                sent = await bot.send_message(
                    chat_id=config.work_group_id,
                    message_thread_id=config.access_admin_topic_id,
                    text=admin_request_text(word, who),
                    parse_mode="HTML",
                    reply_markup=admin_keyboard(tg_user_id),
                )
            except Exception as exc:  # noqa: BLE001 — любая ошибка Telegram → откат
                logger.warning("access: заявка не отправлена в тему (%s)", type(exc).__name__)
                raise _SendFailed from None
            await conn.execute(UPSERT_REQUEST, (tg_user_id, sent.message_id, now, verdict.deny_count))
    except _SendFailed:
        return TRY_LATER, None
    logger.info("access: новая заявка отправлена в тему")
    return SENT, None


async def find_by_message(conn, admin_message_id: int) -> int | None:
    cur = await conn.execute(FIND_BY_MESSAGE, (admin_message_id,))
    row = await cur.fetchone()
    return None if row is None else row[0]


async def decide(conn, config, action: str, tg_user_id: int, admin_message_id: int, admin_id: int,
                 now: datetime) -> Decision:
    """Решение админа (кнопка или команда) в одной транзакции."""
    async with conn.transaction():
        cur = await conn.execute(STATE_FOR_UPDATE, (tg_user_id,))
        row = to_row(await cur.fetchone())
        if row is None:
            return Decision(NOT_FOUND)
        if action == GRANT:
            if row.status == "granted":
                return Decision(ALREADY_GRANTED, tg_user_id)
            if row.admin_message_id != admin_message_id:
                return Decision(ALREADY_DECIDED, tg_user_id)  # заявка устарела: есть более новая
            await conn.execute(GRANT_UPDATE, (now, admin_id, tg_user_id))
            decision = Decision(GRANTED, tg_user_id)
        else:
            count = row.deny_count + 1
            locked_until = deny_result(count, config.access_max_denies, config.access_lock_hours, now)
            cur = await conn.execute(DENY_UPDATE, (locked_until, now, admin_id, tg_user_id, admin_message_id))
            if cur.rowcount == 0:
                return Decision(ALREADY_DECIDED, tg_user_id)
            decision = Decision(DENIED, tg_user_id, count, locked_until)
    logger.info("access: решение записано (%s)", decision.kind)
    return decision
