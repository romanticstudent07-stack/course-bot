"""apps/bot/bot/pause.py — паузы (bot-pause-1, Р-6а): SQL, ключи, чистые функции, decide.

Участник подаёт заявку в Mini App; бот выкладывает Автору карточку с кнопками ✅/✖ (один тап),
пишет событие решения pause_approved | pause_rejected {"pause_id": <int>} в participant_events
(actor 'bot', actor_role 'owner'), уведомляет участника о смене статуса и шлёт Автору алерт,
если пауза началась без его решения. Статус, флаги и бюджет меняет только проектор, старт и
конец — часы pause_ops; participant_pauses и participant_state бот не пишет. RETURNING нет.

Решения карточки: молчание Автора до start_at = авто-разрешение (Р1); решение пишется только
при status = 'requested' AND now() < start_at, now() — из БД в той же транзакции (Р2).
Шлём только по ТЕКУЩЕМУ статусу строки; пропущенные статусы не досылаются (Р9), кроме алерта.

Права app_bot (0009, 0011, 0013, 0018, 0021) — SQL ниже использует только их:
    participant_pauses (id, pid, kind, status, start_at, planned_end_at, created_at) — SELECT (0021)
    tg_user_registry (pid, tg_user_id, tombstoned_at, short_no) — SELECT
    participant_state (tz) — SELECT
    participant_events — INSERT (pid, kind, payload, actor, actor_role)
    idempotency_keys — INSERT (key, kind, result_ref, ttl); SELECT (key, result_ref)
Только параметры %s. LOCK — из bot.life (как в revive.apply).

Даты — по поясу участника (participant_state.tz); пуст или неизвестен → UTC с пометкой « (UTC)».
N = местная дата planned_end_at − местная дата start_at; последний день = местная дата planned_end_at − 1.
Логи: без tg_user_id, pid, short_no и дат — только метка и код.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import NamedTuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from psycopg.types.json import Jsonb

from bot import texts
from bot.life import LOCK

logger = logging.getLogger(__name__)

# --- SQL (карточка §5) ---
WATCH = """SELECT p.id, p.pid, p.status, p.start_at, p.planned_end_at,
  r.tg_user_id, r.short_no, s.tz, now() AS db_now,
  (p.status = 'requested' AND now() < p.start_at) AS open
FROM participant_pauses p
JOIN tg_user_registry r ON r.pid = p.pid
LEFT JOIN participant_state s ON s.pid = p.pid
WHERE p.kind = 'user' AND r.tombstoned_at IS NULL
  AND p.created_at > now() - interval '10 days'
ORDER BY p.id"""
DECIDE_ROW = "SELECT pid FROM participant_pauses WHERE id = %s AND kind = 'user'"
DECIDE_CHECK = "SELECT status = 'requested' AND now() < start_at FROM participant_pauses WHERE id = %s"
KEY_TTL = ("INSERT INTO idempotency_keys (key, kind, result_ref, ttl) "
           "VALUES (%s, %s, %s, interval '30 days') ON CONFLICT (key) DO NOTHING")
KEY_EXISTS = "SELECT key FROM idempotency_keys WHERE key = %s"
EVENT = ("INSERT INTO participant_events (pid, kind, payload, actor, actor_role) "
         "VALUES (%s, %s, %s, 'bot', 'owner')")

CALLBACK_PREFIX = "pse"
APPROVE, REJECT = "a", "r"
NOTE_KIND = "pause_note"
DECIDE_KIND = "pause_decide"

# --- Метки уведомлений ---
REQUESTED = "requested"
APPROVED_L = "approved"
REJECTED_L = "rejected"
CANCELLED = "cancelled"
ACTIVE = "active"
ENDING = "ending"
ENDED = "ended"
AUTO = "auto"
AUTHOR_LABELS = frozenset({REQUESTED, AUTO})
_STATUS_LABELS = frozenset({APPROVED_L, REJECTED_L, CANCELLED, ENDED})

# --- Коды decide ---
GONE = "gone"
NOT_OPEN = "not_open"
ALREADY = "already"
APPROVED = "approved"
REJECTED = "rejected"
TRY_LATER = "try_later"

TEXT_FOR = {
    GONE: texts.PAUSE_GONE,
    NOT_OPEN: texts.PAUSE_NOT_OPEN,
    ALREADY: texts.PAUSE_ALREADY,
    APPROVED: texts.PAUSE_DONE_APPROVED,
    REJECTED: texts.PAUSE_DONE_REJECTED,
    TRY_LATER: texts.PAUSE_TRY_LATER,
}

_CALLBACK_RE = re.compile(r"^pse:(a|r):(\d{1,18})$")


class Row(NamedTuple):
    """Строка WATCH в порядке колонок."""
    id: int
    pid: object
    status: str
    start_at: datetime
    planned_end_at: datetime
    tg_user_id: int
    short_no: int
    tz: str | None
    db_now: datetime
    open: bool


# --- ключи ---

def note_key(pid, pause_id: int, label: str) -> str:
    return f"pause_note:{pid}:{pause_id}:{label}"


def decide_key(pid, pause_id: int) -> str:
    return f"pause_decide:{pid}:{pause_id}"


# --- чистые функции ---

def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _zone(tz: str | None):
    """(пояс, пометка UTC): пуст или неизвестен → UTC с пометкой."""
    if tz:
        try:
            return ZoneInfo(tz), False
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return timezone.utc, True


def local_dates(start_at: datetime, planned_end_at: datetime, tz: str | None) -> tuple[date, date, int, bool]:
    """→ (первый день, последний день, N, пометка UTC) по поясу участника."""
    zone, utc_mark = _zone(tz)
    first = _aware(start_at).astimezone(zone).date()
    end = _aware(planned_end_at).astimezone(zone).date()
    return first, end - timedelta(days=1), (end - first).days, utc_mark


def fmt_day(day: date, utc_mark: bool) -> str:
    """«дд.мм», при поясе UTC — с « (UTC)»."""
    return day.strftime("%d.%m") + (" (UTC)" if utc_mark else "")


def is_ending(row: Row, n: int) -> bool:
    """active, N ≥ 2 и 0 < planned_end_at − now() < 24 ч (Р8)."""
    if row.status != ACTIVE or n < 2:
        return False
    left = _aware(row.planned_end_at) - _aware(row.db_now)
    return timedelta(0) < left < timedelta(hours=24)


def labels_for(row: Row, n: int, decided: bool) -> list[str]:
    """Метки по ТЕКУЩЕМУ статусу (Р7–Р9). decided — есть ключ pause_decide (нужен только для active)."""
    if row.status == REQUESTED:
        return [REQUESTED] if row.open else []
    if row.status == ACTIVE:
        labels = [] if decided else [AUTO]
        labels.append(ACTIVE)
        if is_ending(row, n):
            labels.append(ENDING)
        return labels
    if row.status in _STATUS_LABELS:
        return [row.status]
    return []


def who(short_no: int) -> str:
    return f"#{int(short_no):06d}"


def text_for_label(label: str, row: Row) -> str:
    """Текст уведомления по метке."""
    first, last, n, utc_mark = local_dates(row.start_at, row.planned_end_at, row.tz)
    f, la = fmt_day(first, utc_mark), fmt_day(last, utc_mark)
    if label == REQUESTED:
        return texts.PAUSE_CARD.format(who=who(row.short_no), first=f, last=la, days=n)
    if label == AUTO:
        return texts.PAUSE_AUTO_ALERT.format(who=who(row.short_no), first=f, last=la)
    if label == APPROVED_L:
        return texts.PAUSE_USER_APPROVED.format(first=f, last=la)
    if label == REJECTED_L:
        return texts.PAUSE_USER_REJECTED
    if label == CANCELLED:
        return texts.PAUSE_USER_CANCELLED
    if label == ACTIVE:
        text = texts.PAUSE_USER_ACTIVE.format(last=la)
        return text + "\n\n" + texts.PAUSE_USER_LONG_WARN if n >= 3 else text
    if label == ENDING:
        return texts.PAUSE_USER_ENDING.format(resume=fmt_day(last + timedelta(days=1), utc_mark))
    if label == ENDED:
        return texts.PAUSE_USER_ENDED
    raise ValueError(label)


def card_keyboard(pause_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=texts.PAUSE_BTN_APPROVE, callback_data=f"{CALLBACK_PREFIX}:{APPROVE}:{pause_id}"),
        InlineKeyboardButton(text=texts.PAUSE_BTN_REJECT, callback_data=f"{CALLBACK_PREFIX}:{REJECT}:{pause_id}"),
    ]])


def parse_callback(data: str | None) -> tuple[bool, int] | None:
    """«pse:a:<id>» → (True, id); «pse:r:<id>» → (False, id); иначе None."""
    m = _CALLBACK_RE.fullmatch(data or "")
    if m is None:
        return None
    return m.group(1) == APPROVE, int(m.group(2))


# --- БД ---

async def decide(conn, pause_id: int, approve: bool) -> str:
    """Одна транзакция: DECIDE_ROW → LOCK → DECIDE_CHECK → KEY_TTL → EVENT. Ошибка БД → TRY_LATER."""
    result = APPROVED if approve else REJECTED
    try:
        async with conn.transaction():
            cur = await conn.execute(DECIDE_ROW, (pause_id,))
            found = await cur.fetchone()
            if found is None:
                return GONE
            pid = found[0]
            await conn.execute(LOCK, (str(pid),))
            cur = await conn.execute(DECIDE_CHECK, (pause_id,))
            check = await cur.fetchone()
            if check is None or check[0] is not True:
                return NOT_OPEN
            cur = await conn.execute(KEY_TTL, (decide_key(pid, pause_id), DECIDE_KIND, result))
            if cur.rowcount == 0:
                return ALREADY
            kind = "pause_approved" if approve else "pause_rejected"
            await conn.execute(EVENT, (pid, kind, Jsonb({"pause_id": int(pause_id)})))
    except Exception as exc:  # noqa: BLE001
        logger.error("pause: решение не записано (%s)", type(exc).__name__)
        return TRY_LATER
    return result
