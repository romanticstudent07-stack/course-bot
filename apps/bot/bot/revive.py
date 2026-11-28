"""apps/bot/bot/revive.py — команда /revive (bot-revive-1): разбор, check, count_returned, SQL, preview, apply.

Автор в Рабочей группе возвращает участника из block_lives (Р-20): бот пишет только событие
revive_by_author {target {stage_no, module_no, day_no}, lives_returned} в participant_events
(actor 'bot', actor_role 'owner'). Жизни (min(3, 1 + lives_returned)), флаг и день меняет
проектор v7; participant_state, outbox, life_writeoffs бот не пишет. RETURNING не используется.

lives_returned (02 §2.6, §2.4): списания из life_writeoffs после точки отката :after
(id последнего revive_by_author или restart_paid этого pid, 0 — если нет), у которых
(stage_no, module_no, day_no) >= target. Без обрезки: min(3, 1 + x) делает проектор.
Ш3 (риск принят ШТАБом): :after берёт и неприменённое проектором событие.

Права app_bot (0009, 0011, 0013, 0018, 0019, 0020) — SQL ниже использует только их:
    tg_user_registry (pid, tg_user_id, tombstoned_at, short_no) — SELECT (FIND из bot.life)
    participant_state (lifecycle_phase, status_flags, stage_no, module_no, day_no) — SELECT
    participant_events (id, pid, kind) — SELECT (0020); INSERT (pid, kind, payload, actor, actor_role)
    life_writeoffs (pid, event_id, stage_no, module_no, day_no) — SELECT (0019)
    idempotency_keys — INSERT (key, kind, result_ref); ttl — DEFAULT 1 ч в БД (0007)
Только параметры %s. FIND, LOCK, has_flag, new_op, STALE_SECONDS — из bot.life.

check повторяет условия проектора v7 и отказывает ДО записи. REFUSE_STAGE в потоке недостижим
(target.stage_no — stage из той же транзакции): защита чистой функции.
День target внутри модуля не проверяется — контента у бота нет (риск карточки §7.6).
Логи: без tg_user_id, pid, short_no, target — только код результата.
"""
from __future__ import annotations

import re
from typing import NamedTuple

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from psycopg.types.json import Jsonb

from bot import texts
from bot.life import BIGINT_MAX, FIND, LOCK, has_flag

# --- SQL ---
STATE = "SELECT lifecycle_phase, status_flags, stage_no, module_no, day_no FROM participant_state WHERE pid = %s"
AFTER = ("SELECT coalesce(max(id), 0) FROM participant_events "
         "WHERE pid = %s AND kind IN ('revive_by_author', 'restart_paid')")
WRITEOFFS = ("SELECT event_id, stage_no, module_no, day_no FROM life_writeoffs "
             "WHERE pid = %s AND event_id > %s ORDER BY event_id")
KEY = "INSERT INTO idempotency_keys (key, kind, result_ref) VALUES (%s, 'revive', %s) ON CONFLICT (key) DO NOTHING"
EVENT = ("INSERT INTO participant_events (pid, kind, payload, actor, actor_role) "
         "VALUES (%s, 'revive_by_author', %s, 'bot', 'owner')")

CALLBACK_PREFIX = "rvb"
CONFIRM, CANCEL = "y", "n"
MAX_LIVES = 3
MAX_POS = 999

# --- Коды разбора и результата ---
USAGE = "usage"
NOT_FOUND = "not_found"
REFUSE_PHASE = "refuse_phase"
REFUSE_NOT_BLOCKED = "refuse_not_blocked"
REFUSE_NO_POSITION = "refuse_no_position"
REFUSE_STAGE = "refuse_stage"
REFUSE_AHEAD = "refuse_ahead"
ALREADY = "already"
DONE = "done"

TEXT_FOR = {
    USAGE: texts.REVIVE_USAGE,
    NOT_FOUND: texts.REVIVE_NOT_FOUND,
    REFUSE_PHASE: texts.REVIVE_REFUSE_PHASE,
    REFUSE_NOT_BLOCKED: texts.REVIVE_REFUSE_NOT_BLOCKED,
    REFUSE_NO_POSITION: texts.REVIVE_REFUSE_NO_POSITION,
    REFUSE_STAGE: texts.REVIVE_REFUSE_STAGE,
    REFUSE_AHEAD: texts.REVIVE_REFUSE_AHEAD,
    ALREADY: texts.REVIVE_ALREADY,
    DONE: texts.REVIVE_DONE,
}

_ARGS_RE = re.compile(r"(?:#(\d+)(?=\s|$))?\s*(?:(\d{1,3})\.(\d{1,3}))?", re.ASCII)
_CONFIRM_RE = re.compile(
    rf"{CALLBACK_PREFIX}:{CONFIRM}:(\d{{1,19}}):(\d{{1,3}}):(\d{{1,3}}):([0-9a-f]{{16}})",
    re.ASCII,
)


def parse_args(args: str | None) -> tuple[str, int | None, int | None, int | None]:
    """Аргументы /revive → (код, short_no, module, day).

    («ok», номер или None — номер из reply, М или None, Д или None) | (USAGE, …) | (NOT_FOUND, …).
    М и Д — 1…999; номер больше bigint → NOT_FOUND.
    """
    m = _ARGS_RE.fullmatch((args or "").strip())
    if m is None:
        return USAGE, None, None, None
    digits, mod, day = m.groups()
    module_no = int(mod) if mod is not None else None
    day_no = int(day) if day is not None else None
    if module_no is not None and not (1 <= module_no <= MAX_POS and 1 <= day_no <= MAX_POS):
        return USAGE, None, None, None
    if digits is None:
        return "ok", None, module_no, day_no
    if len(digits) > 19 or int(digits) > BIGINT_MAX:
        return NOT_FOUND, None, None, None
    return "ok", int(digits), module_no, day_no


def check(phase, flags, stage, module, day, target) -> str | None:
    """Код отказа или None. Порядок — карточка bot-revive-1 §7.3; target = (stage_no, module_no, day_no)."""
    if phase is None:
        return NOT_FOUND
    if phase in ("muted", "erased"):
        return REFUSE_PHASE
    if not has_flag(flags, "block_lives"):
        return REFUSE_NOT_BLOCKED
    if stage is None or module is None or day is None:
        return REFUSE_NO_POSITION
    ts, tm, td = target
    if ts != stage:
        return REFUSE_STAGE
    if (tm, td) > (module, day):
        return REFUSE_AHEAD
    return None


def count_returned(rows, target) -> int:
    """Число строк (event_id, stage_no, module_no, day_no) с (stage_no, module_no, day_no) >= target."""
    t = tuple(int(v) for v in target)
    return sum(1 for row in rows if tuple(int(v) for v in row[1:4]) >= t)


def confirm_data(short_no: int, module_no: int, day_no: int, op: str) -> str:
    return f"{CALLBACK_PREFIX}:{CONFIRM}:{short_no}:{module_no}:{day_no}:{op}"


def preview_keyboard(short_no: int, module_no: int, day_no: int, op: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=texts.REVIVE_BUTTON_CONFIRM,
                             callback_data=confirm_data(short_no, module_no, day_no, op)),
        InlineKeyboardButton(text=texts.REVIVE_BUTTON_CANCEL, callback_data=f"{CALLBACK_PREFIX}:{CANCEL}"),
    ]])


def parse_callback(data: str | None) -> tuple[str, int | None, int | None, int | None, str | None] | None:
    """«rvb:n» → (CANCEL, …); «rvb:y:<номер>:<м>:<д>:<op>» → (CONFIRM, номер, м, д, op); иначе None."""
    if data == f"{CALLBACK_PREFIX}:{CANCEL}":
        return CANCEL, None, None, None, None
    m = _CONFIRM_RE.fullmatch(data or "")
    if m is None:
        return None
    short_no, module_no, day_no = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if short_no > BIGINT_MAX or not (1 <= module_no <= MAX_POS and 1 <= day_no <= MAX_POS):
        return None
    return CONFIRM, short_no, module_no, day_no, m.group(4)


def lives_after(returned: int) -> int:
    """Только для текста предпросмотра; применяет проектор."""
    return min(MAX_LIVES, 1 + returned)


# --- БД ---

class Preview(NamedTuple):
    code: str | None
    position: tuple | None = None
    target: tuple | None = None
    returned: int | None = None


class Result(NamedTuple):
    code: str
    tg_user_id: int | None = None


async def _state(conn, pid):
    cur = await conn.execute(STATE, (pid,))
    row = await cur.fetchone()
    return row if row is not None else (None, None, None, None, None)


async def _returned(conn, pid, target) -> int:
    cur = await conn.execute(AFTER, (pid,))
    after = (await cur.fetchone())[0]
    cur = await conn.execute(WRITEOFFS, (pid, after))
    rows = await cur.fetchall()
    return count_returned(rows, target)


async def preview(conn, short_no: int, module_no: int | None, day_no: int | None) -> Preview:
    """Шаг 1, без записи и без замка: FIND → STATE → check → AFTER → WRITEOFFS → count."""
    cur = await conn.execute(FIND, (short_no,))
    found = await cur.fetchone()
    if found is None:
        return Preview(NOT_FOUND)
    pid = found[0]
    phase, flags, stage, module, day = await _state(conn, pid)
    target = (stage, module_no or module, day_no or 1)
    code = check(phase, flags, stage, module, day, target)
    if code is not None:
        return Preview(code)
    returned = await _returned(conn, pid, target)
    return Preview(None, (stage, module, day), target, returned)


class _Refused(Exception):
    """check отказал внутри транзакции → откат."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


async def apply(conn, short_no: int, module_no: int, day_no: int, op: str) -> Result:
    """Шаг 2: одна транзакция FIND → замок → STATE → check → AFTER → WRITEOFFS → ключ → событие."""
    try:
        async with conn.transaction():
            cur = await conn.execute(FIND, (short_no,))
            found = await cur.fetchone()
            if found is None:
                raise _Refused(NOT_FOUND)
            pid, tg_user_id = found[0], found[1]
            await conn.execute(LOCK, (str(pid),))
            phase, flags, stage, module, day = await _state(conn, pid)
            target = (stage, module_no, day_no)
            code = check(phase, flags, stage, module, day, target)
            if code is not None:
                raise _Refused(code)
            returned = await _returned(conn, pid, target)
            cur = await conn.execute(KEY, (f"revive:{pid}:{op}", str(returned)))
            if cur.rowcount == 0:
                return Result(ALREADY)
            payload = {
                "target": {"stage_no": int(stage), "module_no": int(module_no), "day_no": int(day_no)},
                "lives_returned": int(returned),
            }
            await conn.execute(EVENT, (pid, Jsonb(payload)))
    except _Refused as refused:
        return Result(refused.code)
    return Result(DONE, tg_user_id)
