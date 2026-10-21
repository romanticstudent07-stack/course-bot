"""«Часы» дня (life-ops-c): закрытие просроченного дня без отчёта, пропуски, жизни, sleeping.

Запуск: шаг tick вызывает app/projector.py из run_forever раз в LIFE_OPS_INTERVAL_S (once — без tick).
Ручная проверка: python -m app.life_ops dry-run <pid> — роль проектора (PROJECTOR_DATABASE_URL),
только SELECT, ROLLBACK; печатает состояние дня и исход «если закрыть сейчас».

Источник — docs/tasks/life-ops-c.md (§7) и уточнения ШТАБа У1–У7. «Часы» пишут ТОЛЬКО ключ
idempotency_keys и события participant_events (life_op, day_closed); состояние участника
применяет проектор (E1 / INV-1). Outbox здесь не пишется.

tick(engine, now) → TickResult(closed, skipped):
  1. Кандидаты — своя транзакция, только чтение: строки состояния с фазой onboarding / active,
     author_pause_reason IS NULL, day_no IS NOT NULL; в Python — day_clock.is_overdue.
     Не больше MAX_PER_TICK (самые старые day_started_at), остальные — в следующем тике.
  2. Каждый pid — отдельная транзакция под lock_participant: состояние читается заново и фильтр
     п. 1 + is_overdue проверяются снова (У3: sleeping, muted, erased, пауза → пропуск).
  3. «Проектор догнал pid»: нет событий pid с id больше checkpoint (курсор по pid, как в
     projector._SELECT_BATCH). Есть — пропуск: отчёт, принятый до 00:00, не теряется.
  4. Есть ключ day_done или day_close по D → пропуск.
  5. came = есть строки day_marks (pid, D); исход — day_clock.close_outcome.
  6. next = last_midnight(now, tz); строго позже D в UTC (У5), иначе WARNING без pid и пропуск
     (проектор такой day_closed не применил бы, Н5).
  7. Ключ day_close:{pid}:{dsa(D)} (ON CONFLICT DO NOTHING RETURNING; 0 строк → пропуск),
     затем life_op (если delta ≠ 0 и нет флага block_lives — У2), затем day_closed. Всё —
     ОДНА транзакция, один commit (У1, ревью #111 Н4): ни одно из трёх без остальных.
  Ошибка БД на pid → rollback, WARNING с именем класса, пропуск; другие pid тика идут дальше.

Время (У4): now — только аргумент (в run_forever — day_clock.utcnow()); все сравнения — через
day_clock или в UTC. datetime.now(), time.time() и SQL now() в логике не используются.
Лог (У7): без pid, tz, payload и ПДн. На закрытие — исход и delta; итог тика — одной строкой.
Известное ограничение: tombstone «часы» не видят (до прода; GRANT — миграцией до 0-Б).
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

from app import day_clock
from app.day_keys import KIND_DAY_CLOSE, TTL_DAY_CLOSE, dsa, key_day_close, key_day_done
from app.participant_lock import lock_participant

logger = logging.getLogger("app.life_ops")

LIFE_OPS_INTERVAL_S = 30
MAX_PER_TICK = 200
ACTOR = "life_ops"
ACTOR_ROLE = "system"
# Совпадают с app/projector.py (EVENT_KIND_LIFE_OP, EVENT_KIND_DAY_CLOSED, LIFE_OP_REASON);
# сверяет tests/test_life_ops.py. Импорта проектора нет: проектор импортирует этот модуль.
EVENT_KIND_LIFE_OP = "life_op"
EVENT_KIND_DAY_CLOSED = "day_closed"
LIFE_OP_REASON = "missed_days"
# Флаг status_flags (миграция 0001): жизни не списываются (решение 21.10, Issue #109).
FLAG_BLOCK_LIVES = "block_lives"
PHASES = ("onboarding", "active")
USAGE = "usage: python -m app.life_ops dry-run <pid>"

_CANDIDATES = text(
    """
    SELECT pid, tz, day_started_at
    FROM participant_state
    WHERE lifecycle_phase IN ('onboarding', 'active')
      AND author_pause_reason IS NULL
      AND day_no IS NOT NULL
      AND day_started_at IS NOT NULL
    ORDER BY day_started_at, pid
    """
)

_STATE = text(
    """
    SELECT lifecycle_phase, author_pause_reason, day_no, day_started_at, lives,
           missed_streak, tz, status_flags
    FROM participant_state
    WHERE pid = :pid
    """
)

# Курсор проектора — по pid (projector._SELECT_BATCH).
_PENDING_EVENT = text(
    """
    SELECT 1
    FROM participant_events e
    LEFT JOIN participant_state_checkpoints c USING (pid)
    WHERE e.pid = :pid AND e.id > coalesce(c.last_event_id, 0)
    LIMIT 1
    """
)

_HAS_KEY = text("SELECT 1 FROM idempotency_keys WHERE key IN (:done, :close) LIMIT 1")

_HAS_MARKS = text(
    "SELECT 1 FROM day_marks WHERE pid = :pid AND day_started_at = :started LIMIT 1"
)

_INSERT_CLOSE_KEY = text(
    """
    INSERT INTO idempotency_keys (key, kind, ttl)
    VALUES (:key, :kind, CAST(:ttl AS interval))
    ON CONFLICT DO NOTHING
    RETURNING key
    """
)

_INSERT_EVENT = text(
    """
    INSERT INTO participant_events (pid, kind, payload, actor, actor_role)
    VALUES (:pid, :kind, CAST(:payload AS jsonb), :actor, :actor_role)
    """
)


@dataclass(frozen=True)
class TickResult:
    closed: int
    skipped: int


@dataclass(frozen=True)
class ClosePlan:
    """Что записать при закрытии дня D (без записи)."""

    started: datetime
    next_started: datetime
    outcome: day_clock.CloseOutcome
    came: bool
    write_life_op: bool


def _require_aware(now: datetime) -> None:
    if now.tzinfo is None or now.tzinfo.utcoffset(now) is None:
        raise ValueError("life_ops: now — нужен datetime с часовым поясом (naive запрещён)")


def _utc(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc)


def _eligible(row: Any) -> bool:
    """Фильтр §7 п. 1 (повторяется под замком, У3)."""
    return (
        row.lifecycle_phase in PHASES
        and row.author_pause_reason is None
        and row.day_no is not None
        and row.day_started_at is not None
    )


def _candidates(engine: Engine, now: datetime) -> list[uuid.UUID]:
    """Своя транзакция, только чтение; не больше MAX_PER_TICK просроченных."""
    with engine.connect() as conn:
        rows = conn.execute(_CANDIDATES).all()
        conn.rollback()
    found: list[uuid.UUID] = []
    for pid, tz, started in rows:
        if day_clock.is_overdue(started, tz, now):
            found.append(pid)
            if len(found) >= MAX_PER_TICK:
                break
    return found


def _plan(conn: Connection, pid: uuid.UUID, row: Any, now: datetime) -> ClosePlan | None:
    """Шаги 2–6 под замком: None — пропуск (ничего не писать)."""
    if not _eligible(row) or not day_clock.is_overdue(row.day_started_at, row.tz, now):
        return None
    if conn.execute(_PENDING_EVENT, {"pid": pid}).first() is not None:
        return None  # проектор не догнал pid — следующий тик
    started: datetime = row.day_started_at
    keys = {"done": key_day_done(pid, started), "close": key_day_close(pid, started)}
    if conn.execute(_HAS_KEY, keys).first() is not None:
        return None
    came = conn.execute(_HAS_MARKS, {"pid": pid, "started": started}).first() is not None
    try:
        outcome = day_clock.close_outcome(came, row.missed_streak, row.lives)
    except ValueError:
        logger.warning("life_ops: skip (state out of range)")
        return None
    next_started = day_clock.last_midnight(now, row.tz)
    if not _utc(next_started) > _utc(started):
        logger.warning("life_ops: skip (next day not later than current)")
        return None
    flags = list(row.status_flags or ())
    write_life_op = outcome.life_delta != 0 and FLAG_BLOCK_LIVES not in flags
    return ClosePlan(started, next_started, outcome, came, write_life_op)


def _insert_event(conn: Connection, pid: uuid.UUID, kind: str, payload: dict[str, Any]) -> None:
    conn.execute(
        _INSERT_EVENT,
        {
            "pid": pid,
            "kind": kind,
            "payload": json.dumps(payload),
            "actor": ACTOR,
            "actor_role": ACTOR_ROLE,
        },
    )


def _write(conn: Connection, pid: uuid.UUID, plan: ClosePlan) -> bool:
    """Шаг 7: ключ, life_op (если нужен), day_closed. Commit делает вызывающий."""
    inserted = conn.execute(
        _INSERT_CLOSE_KEY,
        {"key": key_day_close(pid, plan.started), "kind": KIND_DAY_CLOSE, "ttl": TTL_DAY_CLOSE},
    ).first()
    if inserted is None:
        return False  # ключ уже есть (рестарт) — ничего не пишем
    started = dsa(plan.started)
    if plan.write_life_op:
        _insert_event(
            conn,
            pid,
            EVENT_KIND_LIFE_OP,
            {"day_started_at": started, "delta": plan.outcome.life_delta, "reason": LIFE_OP_REASON},
        )
    _insert_event(
        conn,
        pid,
        EVENT_KIND_DAY_CLOSED,
        {
            "day_started_at": started,
            "outcome": plan.outcome.outcome,
            "missed_streak": plan.outcome.missed_streak,
            "next_day_started_at": dsa(plan.next_started),
        },
    )
    return True


def close_one(engine: Engine, pid: uuid.UUID, now: datetime) -> bool:
    """Один pid — одна транзакция под замком participant:pid. True — день закрыт."""
    # Ошибка до commit → выход из with закрывает соединение, транзакция откатывается целиком.
    with engine.connect() as conn:
        lock_participant(conn, pid)
        row = conn.execute(_STATE, {"pid": pid}).first()
        plan = None if row is None else _plan(conn, pid, row, now)
        if plan is None or not _write(conn, pid, plan):
            conn.rollback()
            return False
        conn.commit()  # У1: ключ + life_op + day_closed — один commit
    delta = plan.outcome.life_delta if plan.write_life_op else 0
    logger.info("life_ops: day closed outcome=%s delta=%s", plan.outcome.outcome, delta)
    return True


def tick(engine: Engine, now: datetime) -> TickResult:
    """Закрыть просроченные дни на момент now (aware). Ошибка чтения кандидатов — наружу."""
    _require_aware(now)
    closed = 0
    skipped = 0
    for pid in _candidates(engine, now):
        try:
            done = close_one(engine, pid, now)
        except SQLAlchemyError as exc:
            # Без pid и текста исключения: только имя класса.
            logger.warning("life_ops: db error on close (%s)", type(exc).__name__)
            done = False
        if done:
            closed += 1
        else:
            skipped += 1
    logger.info("life_ops: tick closed=%s skipped=%s", closed, skipped)
    return TickResult(closed, skipped)


def dry_run(engine: Engine, pid: uuid.UUID, now: datetime) -> dict[str, Any] | None:
    """Только SELECT, в конце ROLLBACK. None — строки состояния нет."""
    _require_aware(now)
    with engine.connect() as conn:
        try:
            row = conn.execute(_STATE, {"pid": pid}).first()
            if row is None:
                return None
            info: dict[str, Any] = {
                "lifecycle_phase": row.lifecycle_phase,
                "lives": row.lives,
                "missed_streak": row.missed_streak,
                "tz": row.tz,
                "day_started_at": row.day_started_at,
                "active_from": None,
                "deadline_at": None,
                "is_overdue": False,
                "outcome_if_closed_now": None,
            }
            started = row.day_started_at
            if started is not None:
                info["active_from"] = day_clock.active_from(started, row.tz)
                info["deadline_at"] = day_clock.deadline_at(started, row.tz)
                info["is_overdue"] = day_clock.is_overdue(started, row.tz, now)
                came = conn.execute(_HAS_MARKS, {"pid": pid, "started": started}).first()
                try:
                    o = day_clock.close_outcome(came is not None, row.missed_streak, row.lives)
                    blocked = FLAG_BLOCK_LIVES in list(row.status_flags or ())
                    info["outcome_if_closed_now"] = {
                        "outcome": o.outcome,
                        "missed_streak": o.missed_streak,
                        "life_delta": 0 if blocked else o.life_delta,
                        "sleeping": False if blocked else o.sleeping,
                        "next_day_started_at": day_clock.last_midnight(now, row.tz),
                    }
                except ValueError:
                    info["outcome_if_closed_now"] = "not closable (lives or missed_streak)"
            return info
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
        info = dry_run(engine, pid, day_clock.utcnow())
    except (SQLAlchemyError, ValueError, ImportError) as exc:
        logger.warning("life_ops: dry-run failed (%s)", type(exc).__name__)
        return 1
    if info is None:
        print("dry-run: no participant_state row")
        return 0
    for name, value in info.items():
        print(f"{name}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
