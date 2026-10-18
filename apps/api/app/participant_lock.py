"""Замок участника: pg_advisory_xact_lock(hashtext('participant:' || pid)) (iter2-api-2a).

Зачем: курсор проектора (app/projector.py) идёт по pid в порядке e.id. Порядок событий
одного pid держится, только если писатели событий СУЩЕСТВУЮЩЕГО pid не пересекаются:
каждый берёт этот замок ДО INSERT в participant_events и держит его до commit / rollback
(xact-замок Postgres снимает сам в конце транзакции). Источник — docs/research/iter2-api.md §4.

Ключ — 'participant:' || pid (текст uuid, как str(uuid.UUID)). Тот же ключ — в I2B
(В20; расхождение с 'life:' — DEFECTS). Замок проектора (participant_state_projector) —
другой ключ, с этим не пересекается.

first-launch (Ш2, проверено КОДЕРОМ iter2-api-2a): participant_events пишется только для pid,
созданного этим же вызовом (строка ещё не закоммичена и другим не видна), — замок не нужен.

Правила:
  - сначала замок, потом запись;
  - строки tg_user_registry FOR UPDATE под замком не брать (только обычный SELECT);
  - active_pid_locked: find_active_participant → замок → повторный SELECT, что pid всё ещё
    активен (tombstoned_at IS NULL). Строки нет → None: вызывающий ничего не пишет.
COMMIT здесь нет: транзакцией владеет вызывающий.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Connection, text
from sqlalchemy.orm import Session

from app.participants import find_active_participant

LOCK_KEY_PREFIX = "participant:"

_LOCK_SQL = text(
    "SELECT pg_advisory_xact_lock(hashtext('participant:' || CAST(:pid AS text)))"
)

# Обычный SELECT, без FOR UPDATE (порядок блокировок: только advisory-замок).
_ACTIVE_SQL = text(
    "SELECT pid FROM tg_user_registry WHERE pid = :pid AND tombstoned_at IS NULL"
)


def lock_participant(session: Session | Connection, pid: uuid.UUID | str) -> None:
    """Взять xact-замок participant:pid. Ждёт, пока замок держит другая транзакция."""
    session.execute(_LOCK_SQL, {"pid": str(pid)})


def active_pid_locked(session: Session | Connection, tg_user_id: int) -> uuid.UUID | None:
    """pid активного участника под замком или None (нет участника или tombstoned).

    pid — только по tg_user_id из проверенной initData (вызывающий берёт его из
    InitDataContext). После None вызывающий ничего не пишет.
    """
    found = find_active_participant(session, tg_user_id)
    if found is None:
        return None
    pid = found[0]
    lock_participant(session, pid)
    still_active = session.execute(_ACTIVE_SQL, {"pid": pid}).first()
    if still_active is None:
        return None
    return pid
