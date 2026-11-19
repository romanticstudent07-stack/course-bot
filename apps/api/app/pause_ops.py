"""«Часы» пауз участника (api-pause-1b, T2b): старт одобренных и неодобренных по молчанию Автора (канон 02 П.2), конец по сроку.

Запуск: шаг tick вызывает app/projector.py из run_forever раз в PAUSE_OPS_INTERVAL_S, сразу после
шага life_ops (once — без tick). Образец — app/life_ops.py.
Ручная проверка: python -m app.pause_ops dry-run <pid> — роль проектора (PROJECTOR_DATABASE_URL),
только SELECT, ROLLBACK; печатает паузы-кандидаты pid и решение «если сейчас».

Источник — docs/tasks/api-pause-1b.md (§2 Ч1–Ч8, §4), docs/tasks/api-pause-3a.md; решения Р1–Р15 и контракт —
docs/tasks/api-pause-1a.md (разделы 2 и 5). «Часы» пишут ТОЛЬКО ключ idempotency_keys и событие
participant_events (Ч2); статус паузы, флаг, бюджет и позицию применяет проектор (E1 / INV-1).
participant_state, participant_pauses, pause_budgets и outbox здесь не пишутся.

tick(engine, now) → TickResult(started, failed, ended, skipped):
  1. Кандидаты (Ч3) — своя транзакция, только чтение; только kind user; не больше MAX_PER_TICK,
     самые старые start_at / planned_end_at:
       A — status approved или requested, start_at ≤ now;
       C — status active, planned_end_at ≤ now.
  2. Каждая пауза — отдельная транзакция под lock_participant (lock_timeout LOCK_TIMEOUT, Ч4):
     строка паузы и состояние читаются заново; проектор не догнал pid (life_ops._PENDING_EVENT) —
     пропуск до следующего тика.
  3. Решение:
       A (Ч5): вчерашний день не закрыт — life_ops._eligible(state) и day_clock.is_overdue — пропуск
          (сначала закрытие дня life_ops, потом пауза). Затем pause_rules.start_refusal с теми же
          аргументами, что у проектора (_apply_pause_started): бюджет — pause_rules.roll_cycle по now
          только для расчёта, без записи; строки pause_budgets нет → остаток BUDGET_DAYS,
          restart_no 0 (строку создаст проектор, Р12). None → ключ pause_start + pause_started
          {pause_id}; иначе ключ pause_start + pause_start_failed {pause_id, reason}.
          Плохой период (pause_rules.pause_days → ValueError) — WARNING и пропуск.
          requested — тем же путём (api-pause-3a, канон 02 П.2).
       C (Ч7): ключ pause_end + pause_ended {pause_id, reason: "expired"}.
  4. Ключ (Ч8: pause_start:{pid}:{pause_id} / pause_end:{pid}:{pause_id}; ON CONFLICT DO NOTHING
     RETURNING; 0 строк → rollback, пропуск), затем событие с at = now — один commit.
  Любая ошибка на паузе → rollback, WARNING с именем класса, пропуск; другие паузы идут дальше.
  Ошибка чтения кандидатов — наружу (ловит projector).

Время: now — только аргумент (в run_forever — day_clock.utcnow()); сравнения — в UTC или функциями
day_clock / pause_rules. Лог: без pid, tz, payload и ПДн; итог тика — одной строкой INFO.
"""
from __future__ import annotations

import json
import logging
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import SQLAlchemyError

from app import day_clock, life_ops, pause_rules
from app.day_keys import (
    KIND_PAUSE_END,
    KIND_PAUSE_START,
    TTL_PAUSE_END,
    TTL_PAUSE_START,
    key_pause_end,
    key_pause_start,
)
from app.participant_lock import lock_participant

logger = logging.getLogger("app.pause_ops")

MAX_PER_TICK = 200
LOCK_TIMEOUT = "5s"
ACTOR = "pause_ops"
ACTOR_ROLE = "system"
# Совпадают с app/projector.py (EVENT_KIND_PAUSE_*, PAUSE_END_EXPIRED); сверяет
# tests/test_pause_ops.py. Импорта проектора нет: проектор импортирует этот модуль.
EVENT_KIND_PAUSE_STARTED = "pause_started"
EVENT_KIND_PAUSE_START_FAILED = "pause_start_failed"
EVENT_KIND_PAUSE_ENDED = "pause_ended"
PAUSE_END_EXPIRED = "expired"

OUTCOME_STARTED = "started"
OUTCOME_FAILED = "failed"
OUTCOME_ENDED = "ended"

# канон 02 П.2: молчание Автора — авто-старт (api-pause-3a)
_START_STATUSES = ("requested", pause_rules.STATUS_APPROVED)

USAGE = "usage: python -m app.pause_ops dry-run <pid>"

_CANDIDATES = text(
    """
    SELECT id, pid
    FROM participant_pauses
    WHERE kind = 'user'
      AND ((status IN ('approved', 'requested') AND start_at <= :now)
           OR (status = 'active' AND planned_end_at <= :now))
    ORDER BY CASE WHEN status = 'active' THEN planned_end_at ELSE start_at END, id
    LIMIT :limit
    """
)

_PID_CANDIDATES = text(
    """
    SELECT id
    FROM participant_pauses
    WHERE pid = :pid AND kind = 'user'
      AND ((status IN ('approved', 'requested') AND start_at <= :now)
           OR (status = 'active' AND planned_end_at <= :now))
    ORDER BY CASE WHEN status = 'active' THEN planned_end_at ELSE start_at END, id
    """
)

_PAUSE = text(
    """
    SELECT status, start_at, planned_end_at
    FROM participant_pauses
    WHERE id = :id AND pid = :pid AND kind = 'user'
    """
)

# Колонки life_ops._STATE (для life_ops._eligible) плюс stage_no.
_STATE = text(
    """
    SELECT lifecycle_phase, author_pause_reason, day_no, day_started_at, lives,
           missed_streak, tz, status_flags, stage_no
    FROM participant_state
    WHERE pid = :pid
    """
)

_BUDGET = text(
    """
    SELECT days_budget_remaining_annual, cycle_start_at, restart_no
    FROM pause_budgets
    WHERE pid = :pid
    """
)

# Как projector._SELECT_STAGE_TAKEN (Р10).
_STAGE_TAKEN = text(
    """
    SELECT EXISTS (
        SELECT 1 FROM participant_pauses
        WHERE pid = :pid AND kind = 'user' AND status IN ('active', 'ended')
          AND stage_no = :s AND restart_no = :r
    )
    """
)

# Как projector._SELECT_LAST_PAUSE_END.
_LAST_END = text(
    """
    SELECT max(ended_at) FROM participant_pauses
    WHERE pid = :pid AND kind = 'user' AND status = 'ended'
    """
)

_LOCK_TIMEOUT = text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'")

_INSERT_KEY = text(
    """
    INSERT INTO idempotency_keys (key, kind, ttl)
    VALUES (:key, :kind, CAST(:ttl AS interval))
    ON CONFLICT DO NOTHING
    RETURNING key
    """
)

_INSERT_EVENT = text(
    """
    INSERT INTO participant_events (pid, kind, payload, actor, actor_role, at)
    VALUES (:pid, :kind, CAST(:payload AS jsonb), :actor, :actor_role, :at)
    """
)


@dataclass(frozen=True)
class TickResult:
    started: int
    failed: int
    ended: int
    skipped: int


@dataclass(frozen=True)
class PausePlan:
    """Что записать по паузе (без записи)."""

    outcome: str
    key: str
    key_kind: str
    ttl: str
    event_kind: str
    payload: dict[str, Any]


def _require_aware(now: datetime) -> None:
    if now.tzinfo is None or now.tzinfo.utcoffset(now) is None:
        raise ValueError("pause_ops: now — нужен datetime с часовым поясом (naive запрещён)")


def _utc(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc)


def _due(ts: datetime, now: datetime) -> bool:
    return _utc(ts) <= _utc(now)


def _failed(pid: uuid.UUID, pause_id: int, reason: str) -> PausePlan:
    return PausePlan(
        OUTCOME_FAILED,
        key_pause_start(pid, pause_id),
        KIND_PAUSE_START,
        TTL_PAUSE_START,
        EVENT_KIND_PAUSE_START_FAILED,
        {"pause_id": pause_id, "reason": reason},
    )


def _budget_left(conn: Connection, pid: uuid.UUID, now: datetime, tz: str | None) -> tuple[int, int]:
    """(остаток после roll_cycle по now, restart_no) — только расчёт, без записи.

    Строки нет → (BUDGET_DAYS, 0): строку создаст проектор (Р12).
    """
    row = conn.execute(_BUDGET, {"pid": pid}).first()
    if row is None:
        return pause_rules.BUDGET_DAYS, 0
    days_left, cycle_start, restart_no = row
    _start, left = pause_rules.roll_cycle(cycle_start, days_left, now, tz)
    return left, restart_no


def _plan_start(
    conn: Connection, pid: uuid.UUID, pause_id: int, pause: Any, now: datetime
) -> PausePlan | None:
    """A (Ч5, канон 02 П.2): approved или requested; вчерашний день закрыт → start_refusal → started или start_failed."""
    state = conn.execute(_STATE, {"pid": pid}).first()
    if (
        state is not None
        and life_ops._eligible(state)
        and day_clock.is_overdue(state.day_started_at, state.tz, now)
    ):
        return None  # сначала закрытие дня life_ops, потом пауза
    tz = state.tz if state is not None else None
    try:
        days = pause_rules.pause_days(pause.start_at, pause.planned_end_at, tz)
    except ValueError:
        logger.warning("pause_ops: skip (bad period)")
        return None
    days_left, restart_no = _budget_left(conn, pid, now, tz)
    stage_no = state.stage_no if state is not None else None
    stage_taken = bool(
        conn.execute(_STAGE_TAKEN, {"pid": pid, "s": stage_no, "r": restart_no}).scalar()
    )
    last_ended_at = conn.execute(_LAST_END, {"pid": pid}).scalar()
    refusal = pause_rules.start_refusal(
        status=pause_rules.STATUS_APPROVED,
        flags=list(state.status_flags or ()) if state is not None else None,
        phase=state.lifecycle_phase if state is not None else None,
        day_no=state.day_no if state is not None else None,
        days=days,
        days_left=days_left,
        stage_taken=stage_taken,
        last_ended_at=last_ended_at,
        start_at=pause.start_at,
    )
    if refusal is not None:
        return _failed(pid, pause_id, refusal)
    return PausePlan(
        OUTCOME_STARTED,
        key_pause_start(pid, pause_id),
        KIND_PAUSE_START,
        TTL_PAUSE_START,
        EVENT_KIND_PAUSE_STARTED,
        {"pause_id": pause_id},
    )


def plan(conn: Connection, pid: uuid.UUID, pause_id: int, now: datetime) -> PausePlan | None:
    """Шаги 2–3 (только SELECT): None — пропуск (ничего не писать)."""
    pause = conn.execute(_PAUSE, {"id": pause_id, "pid": pid}).first()
    if pause is None:
        return None
    if conn.execute(life_ops._PENDING_EVENT, {"pid": pid}).first() is not None:
        return None  # проектор не догнал pid — следующий тик
    if pause.status == "active" and _due(pause.planned_end_at, now):
        return PausePlan(  # Ч7
            OUTCOME_ENDED,
            key_pause_end(pid, pause_id),
            KIND_PAUSE_END,
            TTL_PAUSE_END,
            EVENT_KIND_PAUSE_ENDED,
            {"pause_id": pause_id, "reason": PAUSE_END_EXPIRED},
        )
    if pause.status in _START_STATUSES and _due(pause.start_at, now):
        return _plan_start(conn, pid, pause_id, pause, now)
    return None


def _write(conn: Connection, pid: uuid.UUID, p: PausePlan, now: datetime) -> bool:
    """Шаг 4: ключ, затем событие (at = now). Commit делает вызывающий."""
    inserted = conn.execute(
        _INSERT_KEY, {"key": p.key, "kind": p.key_kind, "ttl": p.ttl}
    ).first()
    if inserted is None:
        return False  # ключ уже есть — ничего не пишем
    conn.execute(
        _INSERT_EVENT,
        {
            "pid": pid,
            "kind": p.event_kind,
            "payload": json.dumps(p.payload),
            "actor": ACTOR,
            "actor_role": ACTOR_ROLE,
            "at": now,
        },
    )
    return True


def process_one(engine: Engine, pid: uuid.UUID, pause_id: int, now: datetime) -> str | None:
    """Одна пауза — одна транзакция под замком participant:pid. Возвращает исход или None."""
    with engine.connect() as conn:
        conn.execute(_LOCK_TIMEOUT)  # SET LOCAL — только эта транзакция
        lock_participant(conn, pid)
        p = plan(conn, pid, pause_id, now)
        if p is None or not _write(conn, pid, p, now):
            conn.rollback()
            return None
        conn.commit()  # ключ + событие — один commit
    if p.outcome == OUTCOME_FAILED:
        logger.info("pause_ops: %s reason=%s", p.event_kind, p.payload["reason"])
    else:
        logger.info("pause_ops: %s", p.event_kind)
    return p.outcome


def _candidates(engine: Engine, now: datetime) -> list[tuple[int, uuid.UUID]]:
    """Своя транзакция, только чтение; не больше MAX_PER_TICK."""
    with engine.connect() as conn:
        rows = conn.execute(_CANDIDATES, {"now": now, "limit": MAX_PER_TICK}).all()
        conn.rollback()
    return [(pause_id, pid) for pause_id, pid in rows]


def tick(engine: Engine, now: datetime) -> TickResult:
    """Паузы на момент now (aware). Ошибка чтения кандидатов — наружу."""
    _require_aware(now)
    counts = {OUTCOME_STARTED: 0, OUTCOME_FAILED: 0, OUTCOME_ENDED: 0}
    skipped = 0
    for pause_id, pid in _candidates(engine, now):
        try:
            outcome = process_one(engine, pid, pause_id, now)
        except Exception as exc:  # сбой одной паузы не роняет тик
            # Без pid и текста исключения: только имя класса.
            logger.warning("pause_ops: error on pause (%s)", type(exc).__name__)
            outcome = None
        if outcome is None:
            skipped += 1
        else:
            counts[outcome] += 1
    result = TickResult(
        counts[OUTCOME_STARTED], counts[OUTCOME_FAILED], counts[OUTCOME_ENDED], skipped
    )
    logger.info(
        "pause_ops: tick started=%s failed=%s ended=%s skipped=%s",
        result.started,
        result.failed,
        result.ended,
        result.skipped,
    )
    return result


def dry_run(engine: Engine, pid: uuid.UUID, now: datetime) -> list[dict[str, Any]]:
    """Только SELECT, в конце ROLLBACK. Паузы-кандидаты pid и решение «если сейчас»."""
    _require_aware(now)
    out: list[dict[str, Any]] = []
    with engine.connect() as conn:
        try:
            ids = [r[0] for r in conn.execute(_PID_CANDIDATES, {"pid": pid, "now": now}).all()]
            for pause_id in ids:
                pause = conn.execute(_PAUSE, {"id": pause_id, "pid": pid}).first()
                p = plan(conn, pid, pause_id, now)
                out.append(
                    {
                        "pause_id": pause_id,
                        "status": pause.status if pause is not None else None,
                        "start_at": pause.start_at if pause is not None else None,
                        "planned_end_at": pause.planned_end_at if pause is not None else None,
                        "decision_if_now": (
                            "skip" if p is None else f"{p.event_kind} {json.dumps(p.payload)}"
                        ),
                    }
                )
            return out
        finally:
            conn.rollback()


def _parse_args(args: Sequence[str]) -> uuid.UUID | None:
    if len(args) != 2 or args[0] != "dry-run":
        return None
    try:
        return uuid.UUID(args[1])
    except ValueError:
        return None


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    pid = _parse_args(args)
    if pid is None:
        print(USAGE, file=sys.stderr)
        return 2  # к настройкам и БД не обращаемся

    # Импорт настроек и БД — только здесь (неверные аргументы — без них).
    from app.config import get_settings
    from app.db.session import get_engine

    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        engine = get_engine(
            settings.model_copy(update={"database_url": settings.projector_dsn()})
        )
        rows = dry_run(engine, pid, day_clock.utcnow())
    except (SQLAlchemyError, ValueError, ImportError) as exc:
        logger.warning("pause_ops: dry-run failed (%s)", type(exc).__name__)
        return 1
    if not rows:
        print("dry-run: no candidate pauses")
        return 0
    for row in rows:
        print(" ".join(f"{name}={value}" for name, value in row.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
