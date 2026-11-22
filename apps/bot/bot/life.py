"""apps/bot/bot/life.py — команда /life +N | -N (bot-life-1): разбор, check, has_flag, SQL.

Автор в Рабочей группе меняет жизни участника. Бот пишет только событие life_op
{delta, reason 'author_cmd'} в participant_events; жизни меняет проектор (v5/v6).
participant_state, outbox, access_grants бот здесь не пишет. RETURNING не используется
(SELECT на participant_events у app_bot нет).

Права app_bot (0009, 0011, 0013, 0018) — SQL ниже использует только их:
    tg_user_registry (pid, tg_user_id, tombstoned_at, short_no) — SELECT
    participant_state (lifecycle_phase, status_flags, lives) — SELECT
    idempotency_keys — INSERT (key, kind, result_ref); ttl — DEFAULT 1 ч в БД (0007)
    participant_events — INSERT (pid, kind, payload, actor, actor_role)
Только параметры %s.

check повторяет условия проектора и отказывает ДО записи: проектор такое событие молча пропустил бы.
Принятое ограничение: бот видит participant_state до применения проектором прошлого события —
два быстрых /life могут оба пройти check бота; второе отсечёт проектор.
Логи: без tg_user_id, pid, short_no — только код результата.
"""
from __future__ import annotations

import re
from uuid import uuid4

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from psycopg.types.json import Jsonb

from bot import texts

# --- SQL ---
FIND = "SELECT pid, tg_user_id FROM tg_user_registry WHERE short_no = %s AND tombstoned_at IS NULL"
LOCK = "SELECT pg_advisory_xact_lock(hashtextextended('participant:' || %s, 0))"
STATE = "SELECT lifecycle_phase, status_flags, lives FROM participant_state WHERE pid = %s"
KEY = "INSERT INTO idempotency_keys (key, kind, result_ref) VALUES (%s, 'life_op', %s) ON CONFLICT (key) DO NOTHING"
EVENT = "INSERT INTO participant_events (pid, kind, payload, actor, actor_role) VALUES (%s, 'life_op', %s, 'bot', 'owner')"

CALLBACK_PREFIX = "life"
CONFIRM, CANCEL = "y", "n"
REASON = "author_cmd"
MAX_LIVES = 3
MAX_DELTA = 3
BIGINT_MAX = 9223372036854775807
STALE_SECONDS = 3600

# --- Коды разбора и результата ---
USAGE = "usage"
NOT_FOUND = "not_found"
REFUSE_PHASE = "refuse_phase"
REFUSE_REVIVE = "refuse_revive"
REFUSE_ABOVE_MAX = "refuse_above_max"
REFUSE_BELOW_ZERO = "refuse_below_zero"
ALREADY = "already"
DONE = "done"

TEXT_FOR = {
    USAGE: texts.LIFE_USAGE,
    NOT_FOUND: texts.LIFE_NOT_FOUND,
    REFUSE_PHASE: texts.LIFE_REFUSE_PHASE,
    REFUSE_REVIVE: texts.LIFE_REFUSE_REVIVE,
    REFUSE_ABOVE_MAX: texts.LIFE_REFUSE_ABOVE_MAX,
    REFUSE_BELOW_ZERO: texts.LIFE_REFUSE_BELOW_ZERO,
    ALREADY: texts.LIFE_ALREADY,
    DONE: texts.LIFE_DONE,
}

_ARGS_RE = re.compile(r"(?:#(\d+)\s+)?([+-])(\d{1,3})", re.ASCII)
_CONFIRM_RE = re.compile(rf"{CALLBACK_PREFIX}:{CONFIRM}:(\d{{1,19}}):([+-][1-3]):([0-9a-f]{{16}})", re.ASCII)


def parse_args(args: str | None) -> tuple[str, int | None, int | None]:
    """Аргументы /life → (код, short_no, delta).

    («ok», номер или None — номер из reply, delta) | (USAGE, None, None) | (NOT_FOUND, None, None).
    Знак обязателен, N = 1…3; номер больше bigint → NOT_FOUND.
    """
    m = _ARGS_RE.fullmatch((args or "").strip())
    if m is None:
        return USAGE, None, None
    digits, sign, n = m.groups()
    value = int(n)
    if not 1 <= value <= MAX_DELTA:
        return USAGE, None, None
    delta = value if sign == "+" else -value
    if digits is None:
        return "ok", None, delta
    if len(digits) > 19 or int(digits) > BIGINT_MAX:
        return NOT_FOUND, None, None
    return "ok", int(digits), delta


def has_flag(flags, name: str) -> bool:
    """status_flags — text[] (list); dict — по значению; None и прочее → False."""
    if flags is None:
        return False
    if isinstance(flags, dict):
        return bool(flags.get(name))
    if isinstance(flags, (list, tuple, set, frozenset)):
        return name in flags
    return False


def check(phase, flags, lives, delta: int) -> str | None:
    """Код отказа или None. Порядок — карточка bot-life-1 §7 (REVIVE раньше фазы намеренно)."""
    if phase is None or lives is None:
        return NOT_FOUND
    if phase in ("muted", "erased"):
        return REFUSE_PHASE
    if delta > 0 and (lives == 0 or has_flag(flags, "block_lives")):
        return REFUSE_REVIVE
    if phase not in ("onboarding", "active"):
        return REFUSE_PHASE
    if lives + delta > MAX_LIVES:
        return REFUSE_ABOVE_MAX
    if lives + delta < 0:
        return REFUSE_BELOW_ZERO
    return None


def new_op() -> str:
    """client_op_id: 16 hex-символов."""
    return uuid4().hex[:16]


def confirm_data(short_no: int, delta: int, op: str) -> str:
    return f"{CALLBACK_PREFIX}:{CONFIRM}:{short_no}:{delta:+d}:{op}"


def preview_keyboard(short_no: int, delta: int, op: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=texts.LIFE_BUTTON_CONFIRM, callback_data=confirm_data(short_no, delta, op)),
        InlineKeyboardButton(text=texts.LIFE_BUTTON_CANCEL, callback_data=f"{CALLBACK_PREFIX}:{CANCEL}"),
    ]])


def parse_callback(data: str | None) -> tuple[str, int | None, int | None, str | None] | None:
    """«life:n» → (CANCEL, …); «life:y:<номер>:<±N>:<op>» → (CONFIRM, номер, delta, op); иначе None."""
    if data == f"{CALLBACK_PREFIX}:{CANCEL}":
        return CANCEL, None, None, None
    m = _CONFIRM_RE.fullmatch(data or "")
    if m is None:
        return None
    short_no = int(m.group(1))
    if short_no > BIGINT_MAX:
        return None
    return CONFIRM, short_no, int(m.group(2)), m.group(3)


# --- БД ---

async def preview(conn, short_no: int, delta: int) -> tuple[str | None, int | None]:
    """Шаг 1, без записи: FIND → STATE → check. → (код отказа или None, жизни сейчас)."""
    cur = await conn.execute(FIND, (short_no,))
    found = await cur.fetchone()
    if found is None:
        return NOT_FOUND, None
    cur = await conn.execute(STATE, (found[0],))
    state = await cur.fetchone()
    phase, flags, lives = state if state is not None else (None, None, None)
    return check(phase, flags, lives, delta), lives


class _Refused(Exception):
    """check отказал внутри транзакции → откат."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


async def apply(conn, short_no: int, delta: int, op: str) -> str:
    """Шаг 2: одна транзакция FIND → замок → STATE → check → ключ → событие. → код результата."""
    try:
        async with conn.transaction():
            cur = await conn.execute(FIND, (short_no,))
            found = await cur.fetchone()
            if found is None:
                raise _Refused(NOT_FOUND)
            pid = found[0]
            await conn.execute(LOCK, (str(pid),))
            cur = await conn.execute(STATE, (pid,))
            state = await cur.fetchone()
            phase, flags, lives = state if state is not None else (None, None, None)
            code = check(phase, flags, lives, delta)
            if code is not None:
                raise _Refused(code)
            cur = await conn.execute(KEY, (f"life_op:{pid}:{op}", str(delta)))
            if cur.rowcount == 0:
                return ALREADY
            await conn.execute(EVENT, (pid, Jsonb({"delta": int(delta), "reason": REASON})))
    except _Refused as refused:
        return refused.code
    return DONE
