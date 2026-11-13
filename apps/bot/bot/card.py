"""apps/bot/bot/card.py — карточка участника (bot-i3-1): SQL и чистые функции.

Карточка собирается свежей из БД в момент запроса (06 §6.1) и не хранится. До отправки —
строка аудита в privacy_audit_log (кто, чью карточку смотрел; 152-ФЗ).

Права app_bot (0009, 0011, 0013, 0014) — SQL ниже использует только их:
    tg_user_registry (pid, tg_user_id, tombstoned_at, short_no, created_at)
    participant_state (lifecycle_phase, stage_no, module_no, day_no, lives, tz) — status_flags не выбирается
    measurements_log (pid, kind, checkup_zone, weight_kg, created_at) — без id и checkup_score
    privacy_audit_log — только INSERT, без SELECT и RETURNING
Только параметры %s. Поиск по short_no (UNIQUE) — 0 или 1 строка.

«Кто» — по Р-15: «Участник #NNNNNN (ID N) → написать»; имя и username не берутся.
Статус — по В1, жизни — по В2. Оплаты, паузы, возвраты — «нет данных» (Р-1, Р-6а).
Балл Чек-Апа не выбирается и не показывается. Каждая подстановка из БД — html.escape.
"""
from __future__ import annotations

import html
import re

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import texts
from bot.access import fmt_msk

# --- SQL ---
FIND = "SELECT pid, tg_user_id, created_at FROM tg_user_registry WHERE short_no = %s AND tombstoned_at IS NULL"
STATE = "SELECT lifecycle_phase, stage_no, module_no, day_no, lives, tz FROM participant_state WHERE pid = %s"
MEASUREMENTS = "SELECT kind, checkup_zone, weight_kg, created_at FROM measurements_log WHERE pid = %s ORDER BY created_at"
AUDIT = "INSERT INTO privacy_audit_log (actor_id, actor_role, action, participant_id) VALUES (%s, 'owner', 'view', %s)"

CALLBACK_PREFIX = "card"
ZONE_RANK = {"green": 0, "yellow": 1, "red": 2}
STATUS_WORDS = {"active": texts.CARD_STATUS_ACTIVE, "sleeping": texts.CARD_STATUS_SLEEPING}

_ARG_RE = re.compile(r"#(\d{1,18})")
_CALLBACK_RE = re.compile(rf"{CALLBACK_PREFIX}:(\d{{1,18}})")


def card_button(short_no: int) -> InlineKeyboardMarkup:
    """Одна кнопка «📇 Карточка» с callback_data «card:<short_no>» (ставит bot-i3-2)."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=texts.CARD_BUTTON, callback_data=f"{CALLBACK_PREFIX}:{short_no}"),
    ]])


def parse_arg(args: str | None) -> int | None:
    """Аргумент /card: целиком «#<цифры>» → номер; иначе None."""
    m = _ARG_RE.fullmatch((args or "").strip())
    return int(m.group(1)) if m else None


def parse_callback(data: str | None) -> int | None:
    """callback_data целиком «card:<цифры>» → номер; иначе None."""
    m = _CALLBACK_RE.fullmatch(data or "")
    return int(m.group(1)) if m else None


def number_from_reply(reply) -> int | None:
    """Номер из поста бота: кнопка «card:N» → первый «#N» до пустой строки → None."""
    markup = getattr(reply, "reply_markup", None)
    for row in (getattr(markup, "inline_keyboard", None) or []):
        for button in row:
            number = parse_callback(getattr(button, "callback_data", None))
            if number is not None:
                return number
    text = getattr(reply, "text", None) or getattr(reply, "caption", None) or ""
    head = text.split("\n\n", 1)[0]  # после пустой строки — текст участника, не смотреть
    m = _ARG_RE.search(head)
    return int(m.group(1)) if m else None


def who_line(short_no: int, tg_user_id: int) -> str:
    """«Участник #NNNNNN (ID N) → написать» (Р-15)."""
    link = f'<a href="tg://user?id={tg_user_id}">' + html.escape(texts.GROUP_WRITE) + "</a>"
    return texts.GROUP_WHO.format(num=f"{short_no:06d}", tg_id=tg_user_id, link=link)


def _esc(value) -> str:
    return texts.CARD_NO_DATA if value is None else html.escape(str(value))


def _zone_mark(start, last, count: int) -> str:
    if count < 2 or start not in ZONE_RANK or last not in ZONE_RANK:
        return ""
    diff = ZONE_RANK[last] - ZONE_RANK[start]
    word = texts.CARD_ZONE_BETTER if diff < 0 else texts.CARD_ZONE_WORSE if diff > 0 else texts.CARD_ZONE_SAME
    return f" · {word}"


def render_card(short_no: int, tg_user_id: int, registered_at, state, rows) -> str:
    """HTML карточки по 06 §6.4. state — строка STATE или None; rows — строки MEASUREMENTS."""
    phase, stage_no, module_no, day_no, lives, tz = state if state is not None else (None,) * 6
    rows = list(rows or [])
    body = [r for r in rows if r[0] == "body"]
    checkup = [r for r in rows if r[0] == "checkup"]

    lines = [texts.CARD_TITLE, who_line(short_no, tg_user_id), texts.CARD_TZ.format(tz=_esc(tz))]

    if body:
        lines.append(texts.CARD_WEIGHT.format(start=_esc(body[0][2]), current=_esc(body[-1][2])))
    else:
        lines.append(texts.CARD_WEIGHT.format(start=texts.CARD_NO_DATA, current=texts.CARD_NO_DATA))

    if checkup:
        start, last = checkup[0][1], checkup[-1][1]
        lines.append(texts.CARD_ZONE.format(start=_esc(start), last=_esc(last),
                                            mark=_zone_mark(start, last, len(checkup))))
    else:
        lines.append(texts.CARD_ZONE.format(start=texts.CARD_NO_DATA, last=texts.CARD_NO_DATA, mark=""))

    if None in (stage_no, module_no, day_no):
        position = texts.CARD_NO_DATA
    else:
        position = texts.CARD_POSITION.format(s=_esc(stage_no), m=_esc(module_no), d=_esc(day_no))
    if phase is None:
        status = texts.CARD_NO_DATA
    else:
        status = STATUS_WORDS.get(phase) or texts.CARD_STATUS_RAW.format(code=html.escape(str(phase)))
    lines.append(f"{position} · {status}")

    lines.append(texts.CARD_NO_DATA if lives is None else texts.CARD_LIVES.format(n=_esc(lives)))
    lines.append(texts.CARD_LIVES_LOG)

    lines.append(texts.CARD_PAYMENTS.format(value=texts.CARD_NO_DATA))
    lines.append(texts.CARD_PAUSES.format(value=texts.CARD_NO_DATA))
    lines.append(texts.CARD_RETURNS.format(value=texts.CARD_NO_DATA))

    lines.append(texts.CARD_REGISTERED.format(date=fmt_msk(registered_at)))
    return "\n".join(lines)


async def load_and_audit(conn, short_no: int, actor_id: str) -> tuple[int, str] | None:
    """FIND (нет → None, аудита нет) → STATE → MEASUREMENTS → AUDIT → render. Исключение пробрасывается."""
    cur = await conn.execute(FIND, (short_no,))
    found = await cur.fetchone()
    if found is None:
        return None
    pid, tg_user_id, created_at = found
    cur = await conn.execute(STATE, (pid,))
    state = await cur.fetchone()
    cur = await conn.execute(MEASUREMENTS, (pid,))
    rows = await cur.fetchall()
    await conn.execute(AUDIT, (actor_id, pid))
    return tg_user_id, render_card(short_no, tg_user_id, created_at, state, rows)
