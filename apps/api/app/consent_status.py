"""Действует ли согласие участника — общий код GET /onboarding/status и first-launch.

returning-1 (D-22; решение Автора 06.10, вариант А; ответы З1: 1 Б, 3 да):
  - согласие по kind действует, если ПОСЛЕДНЕЕ событие по kind (порядок at, id; D-15 а) —
    give, и его text_key и text_snapshot совпадают с текущим текстом ключа;
  - ver_of_text (версия файла seed) — НЕ критерий;
  - participant_state и проектор НЕ используются (INV-1: проектор пишет с задержкой) —
    источник только consent_events и text_registry;
  - snapshot_of — единственное преобразование текста: first-launch пишет
    text_snapshot=snapshot_of(body), проверка сравнивает с snapshot_of(body).

Здесь только чтение. Запись согласий — app.routers.onboarding.register_with_consents.
Тексты согласий не логируются.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CONSENT_ACTION_REVOKE, ConsentEvent, TextRegistry

# Какой текст из text_registry принят вместе с согласием (выбирает сервер).
# onboarding.py импортирует под тем же именем (старые тесты берут его оттуда).
CONSENT_TEXT_KEYS: dict[str, str] = {
    "C0": "legal.consent_c0_age_18_plus",
    "C1": "legal.consent_c1_pdn",
}

# Согласия, которые проверяет GET /onboarding/status (обязательные до pid, B-2).
STATUS_KINDS: tuple[str, ...] = ("C0", "C1")

Problem = Literal["missing", "revoked", "text_changed"]

# Закрытый перечень причин reconsent; порядок вывода — такой же.
REASONS: tuple[str, ...] = (
    "C0_missing",
    "C0_revoked",
    "C0_text_changed",
    "C1_missing",
    "C1_revoked",
    "C1_text_changed",
)

# Строка события: (kind, action, text_key, text_snapshot).
EventTuple = tuple[str, str, str, str]


class ConsentTextMissingError(Exception):
    """В text_registry нет текста согласия — fail closed (503 SERVICE_MISCONFIGURED)."""

    def __init__(self, keys: list[str]) -> None:
        super().__init__(", ".join(keys))
        self.keys = keys


def snapshot_of(body: str) -> str:
    """Снимок текста согласия: body без изменений. Единственное преобразование."""
    return body


def consent_problem(
    events: Iterable[Sequence[str]], kind: str, current_key: str, current_body: str
) -> Problem | None:
    """Почему согласие kind не действует, или None, если действует.

    events — строки (kind, action, text_key, text_snapshot) в порядке (at, id).
    Чистая функция: тестируется без БД.
    """
    last: Sequence[str] | None = None
    for event in events:
        if event[0] == kind:
            last = event
    if last is None:
        return "missing"
    action, text_key, text_snapshot = last[1], last[2], last[3]
    if action == CONSENT_ACTION_REVOKE:
        return "revoked"
    if text_key != current_key or text_snapshot != snapshot_of(current_body):
        return "text_changed"
    return None


def reasons(
    events: Iterable[Sequence[str]],
    texts: Mapping[str, str],
    kinds: Sequence[str] = STATUS_KINDS,
) -> list[str]:
    """Причины reconsent по kind (C0, C1) — только из REASONS, в порядке REASONS.

    texts — {text_key: body} текущих текстов (current_texts).
    """
    rows = list(events)
    found: set[str] = set()
    for kind in kinds:
        key = CONSENT_TEXT_KEYS[kind]
        problem = consent_problem(rows, kind, key, texts[key])
        if problem is not None:
            found.add(f"{kind}_{problem}")
    return [reason for reason in REASONS if reason in found]


def load_events(session: Session, pid: uuid.UUID) -> list[EventTuple]:
    """События согласий одного pid в порядке (at, id)."""
    rows = session.execute(
        select(
            ConsentEvent.kind,
            ConsentEvent.action,
            ConsentEvent.text_key,
            ConsentEvent.text_snapshot,
        )
        .where(ConsentEvent.pid == pid)
        .order_by(ConsentEvent.at, ConsentEvent.id)
    ).all()
    return [(r.kind, r.action, r.text_key, r.text_snapshot) for r in rows]


def current_texts(session: Session, kinds: Iterable[str]) -> dict[str, str]:
    """Текущие тексты согласий {text_key: body}; нет ключа → ConsentTextMissingError."""
    wanted = sorted({CONSENT_TEXT_KEYS[kind] for kind in kinds})
    rows = session.execute(
        select(TextRegistry.key, TextRegistry.body).where(TextRegistry.key.in_(wanted))
    ).all()
    texts = {row.key: row.body for row in rows}
    missing = [key for key in wanted if key not in texts]
    if missing:
        raise ConsentTextMissingError(missing)
    return texts
