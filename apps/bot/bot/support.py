"""apps/bot/bot/support.py — вопросы поддержки (bot-sup-1, Р-19): SQL и чистые функции.

Без БД и Bot API. Права app_bot (0017, 0009/0011) — SQL ниже использует только их:
    support_questions SELECT (id, pid, topic_code, body, created_at) — 0017
    tg_user_registry  SELECT (pid, tg_user_id, tombstoned_at) — 0009
Только параметры %s, без SELECT * и RETURNING.

callback_data: sup:r:<N> (✉️ Ответить), sup:s:<N> (Отправить), sup:x:<N> (Отмена);
N — question_id, 1…19 цифр и не больше 9223372036854775807 (bigint), иначе None.
Состояния в памяти нет: N берётся из callback_data и из первой строки своих сообщений бота
(промпт SUPPORT_PROMPT, предпросмотр SUPPORT_PREVIEW) — регулярки строятся из шаблонов texts.
"""
from __future__ import annotations

import re

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import texts
from bot.card import card_button

# --- SQL ---
SUPPORT_Q = "SELECT pid, topic_code, body, created_at FROM support_questions WHERE id = %s"
PARTICIPANT = "SELECT tg_user_id, tombstoned_at FROM tg_user_registry WHERE pid = %s"

CALLBACK_PREFIX = "sup"
ACTION_REPLY, ACTION_SEND, ACTION_CANCEL = "r", "s", "x"
BIGINT_MAX = 9223372036854775807

_CALLBACK_RE = re.compile(rf"{CALLBACK_PREFIX}:([rsx]):(\d{{1,19}})")


def _header_re(template: str) -> re.Pattern:
    """Регулярка строки из шаблона texts: {n} — группа из 1…19 цифр, остальное — как есть."""
    parts = re.split(r"(\{n\})", template)
    return re.compile("".join(r"(\d{1,19})" if part == "{n}" else re.escape(part) for part in parts))


_PROMPT_RE = _header_re(texts.SUPPORT_PROMPT)
_PREVIEW_RE = _header_re(texts.SUPPORT_PREVIEW)


def _bigint(digits: str) -> int | None:
    number = int(digits)
    return number if number <= BIGINT_MAX else None


def _callback(action: str, n: int) -> str:
    return f"{CALLBACK_PREFIX}:{action}:{n}"


def question_markup(short_no, n: int) -> InlineKeyboardMarkup:
    """Один ряд под постом вопроса: [«📇 Карточка», если short_no есть] + [«✉️ Ответить», sup:r:N]."""
    row = []
    if short_no is not None:
        row.append(card_button(int(short_no)).inline_keyboard[0][0])
    row.append(InlineKeyboardButton(text=texts.SUPPORT_BUTTON_REPLY, callback_data=_callback(ACTION_REPLY, n)))
    return InlineKeyboardMarkup(inline_keyboard=[row])


def preview_markup(n: int) -> InlineKeyboardMarkup:
    """Один ряд под предпросмотром: «Отправить» (sup:s:N) и «Отмена» (sup:x:N)."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=texts.SUPPORT_BUTTON_SEND, callback_data=_callback(ACTION_SEND, n)),
        InlineKeyboardButton(text=texts.SUPPORT_BUTTON_CANCEL, callback_data=_callback(ACTION_CANCEL, n)),
    ]])


def parse_callback(data: str | None) -> tuple[str, int] | None:
    """callback_data целиком «sup:<r|s|x>:<до 19 цифр>» и N ≤ bigint → (action, N); иначе None."""
    m = _CALLBACK_RE.fullmatch(data or "")
    if not m:
        return None
    n = _bigint(m.group(2))
    return None if n is None else (m.group(1), n)


def n_from_prompt(text: str | None) -> int | None:
    """N из промпта ✉️: первая строка целиком совпадает с SUPPORT_PROMPT; иначе None."""
    first = (text or "").split("\n", 1)[0]
    m = _PROMPT_RE.fullmatch(first)
    return _bigint(m.group(1)) if m else None


def n_from_preview(text: str | None) -> tuple[int, str] | None:
    """(N, текст ответа) из предпросмотра: первая строка = SUPPORT_PREVIEW, ответ — после первой «\\n\\n»."""
    text = text or ""
    first = text.split("\n", 1)[0]
    m = _PREVIEW_RE.fullmatch(first)
    if not m or "\n\n" not in text:
        return None
    n = _bigint(m.group(1))
    if n is None:
        return None
    body = text.split("\n\n", 1)[1]
    return (n, body) if body else None
