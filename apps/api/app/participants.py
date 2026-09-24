"""Создание / поиск участника в tg_user_registry (SEAM-PATCH-1, first-launch).

Идемпотентность — на уровне БД: частичный уникальный индекс
tg_user_registry_active_tg_user_uidx (tg_user_id) WHERE tombstoned_at IS NULL.
INSERT ... ON CONFLICT DO NOTHING + SELECT: два одновременных вызова одного
пользователя дают одну строку и один pid (второй INSERT ждёт коммита первого,
затем ничего не вставляет и читает уже закоммиченную строку).

Вызывать ТОЛЬКО из обработчика first-launch Mini App и ТОЛЬКО после hard-check
возраста (ADD3 INV-AGE-GATE-BEFORE-PID, SEAM-1 pid_creation_only_via_mini_app_first_launch).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import CREATED_VIA_MINI_APP_FIRST_LAUNCH, TgUserRegistry


@dataclass(frozen=True)
class Participant:
    pid: uuid.UUID
    short_no: int
    created: bool  # True — создан этим вызовом; False — уже был


def format_short_no(short_no: int) -> str:
    """«#000123» (06-participant-card.md §6.3). Больше 999999 — просто больше цифр."""
    return f"#{short_no:06d}"


# Сколько раз повторить INSERT, если активную строку tombstone-нули между INSERT и SELECT.
_MAX_ATTEMPTS = 3


def get_or_create_participant(session: Session, tg_user_id: int) -> Participant:
    table = TgUserRegistry.__table__
    for _ in range(_MAX_ATTEMPTS):
        stmt = (
            insert(table)
            .values(
                pid=uuid.uuid4(),
                tg_user_id=tg_user_id,
                created_via=CREATED_VIA_MINI_APP_FIRST_LAUNCH,
            )
            .on_conflict_do_nothing(
                index_elements=[table.c.tg_user_id],
                index_where=table.c.tombstoned_at.is_(None),
            )
            .returning(table.c.pid, table.c.short_no)
        )
        row = session.execute(stmt).first()
        if row is not None:
            session.commit()
            return Participant(pid=row.pid, short_no=row.short_no, created=True)

        existing = session.execute(
            select(table.c.pid, table.c.short_no).where(
                table.c.tg_user_id == tg_user_id, table.c.tombstoned_at.is_(None)
            )
        ).first()
        session.commit()
        if existing is not None:
            return Participant(pid=existing.pid, short_no=existing.short_no, created=False)
        # Конфликт был, но активной строки уже нет (tombstone между INSERT и SELECT) —
        # повторяем: новая регистрация получит новый pid (Р243).
    raise RuntimeError("tg_user_registry: не удалось создать или найти активную запись")
