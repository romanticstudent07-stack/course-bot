"""НП3 после паузы (api-pause-1b, Ч9, §7) и тишина пушей во время паузы. С БД — только CI.

Фикстуры — по образцу tests/test_projector_pause.py; состояние готовит прямым UPDATE — только
в тесте. tg_user_id — вымышленные. now — аргументом, реальное время запуска не влияет.
"""
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import day_clock, notify_ops
from app.day_keys import key_tasks_open
from app.projector import run_once
from app.routers.day import enter_day_by_test_flag
from app.routers.onboarding import register_with_consents

MSK_NAME = "Europe/Moscow"
MSK = ZoneInfo(MSK_NAME)
CYCLE = datetime(2026, 11, 1, 0, 0, tzinfo=MSK)
START = datetime(2026, 11, 21, 0, 0, tzinfo=MSK)
END = datetime(2026, 11, 24, 0, 0, tzinfo=MSK)


def _u(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc)


def _paused(engine, tg_user_id: int) -> tuple:
    """Участник на паузе: флаг pause_user, фаза sleeping, пауза active (Этап 2, рестарт 0)."""
    with Session(engine) as session:
        pid = register_with_consents(session, tg_user_id, ["C0", "C1"]).participant.pid
    run_once(engine)
    with Session(engine) as session:
        enter_day_by_test_flag(session, tg_user_id, True)
    run_once(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE participant_state SET stage_no = 2, module_no = 3, day_no = 5, "
                "day_started_at = :s, missed_streak = 0, tz = :tz, lives = 3, "
                "status_flags = CAST('{pause_user}' AS text[]), lifecycle_phase = 'sleeping' "
                "WHERE pid = :p"
            ),
            {"p": pid, "s": START, "tz": MSK_NAME},
        )
        conn.execute(
            text(
                "INSERT INTO pause_budgets (pid, days_budget_remaining_annual, cycle_start_at, "
                "restart_no) VALUES (:p, 11, :c, 0) ON CONFLICT (pid) DO UPDATE SET "
                "days_budget_remaining_annual = 11, cycle_start_at = :c, restart_no = 0"
            ),
            {"p": pid, "c": CYCLE},
        )
        pause_id = conn.execute(
            text(
                "INSERT INTO participant_pauses (pid, kind, status, start_at, planned_end_at, "
                "stage_no, restart_no, client_op_id) "
                "VALUES (:p, 'user', 'active', :s, :e, 2, 0, 'op-1') RETURNING id"
            ),
            {"p": pid, "s": START, "e": END},
        ).scalar_one()
    return pid, pause_id


def _event(engine, pid, kind: str, payload: dict, at: datetime) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO participant_events (pid, kind, payload, actor, actor_role, at) "
                "VALUES (:p, :k, CAST(:pl AS jsonb), 'system', 'system', :at)"
            ),
            {"p": pid, "k": kind, "pl": json.dumps(payload), "at": at},
        )


def _outbox(engine, pid) -> list:
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT event_type, payload FROM outbox "
                "WHERE aggregate_id::text = :a ORDER BY id"
            ),
            {"a": str(pid)},
        ).all()


def _key_count(engine, key: str) -> int:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT count(*) FROM idempotency_keys WHERE key = :k"), {"k": key}
        ).scalar_one()


def _started(engine, pid) -> datetime:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT day_started_at FROM participant_state WHERE pid = :p"), {"p": pid}
        ).scalar_one()


def _payload(raw) -> dict:
    return raw if isinstance(raw, dict) else json.loads(raw)


def _assert_one_tasks_open(engine, pid, d: datetime, text_id: str) -> None:
    rows = [r for r in _outbox(engine, pid) if r.event_type == notify_ops.EVENT_TYPE]
    assert len(rows) == 1
    assert _payload(rows[0].payload)["text_id"] == text_id
    assert _key_count(engine, key_tasks_open(pid, d)) == 1


# pause_ended by_participant: D = next_midnight(at); НП3 про перевыданный день — один раз.
def test_np3_after_by_participant(db_engine):
    pid, pause_id = _paused(db_engine, 4951)
    pressed = datetime(2026, 11, 22, 15, 0, tzinfo=MSK)
    _event(
        db_engine, pid, "pause_ended", {"pause_id": pause_id, "reason": "by_participant"}, pressed
    )
    run_once(db_engine)
    d = day_clock.next_midnight(pressed, MSK_NAME)
    assert _u(_started(db_engine, pid)) == _u(d)
    now = pressed + timedelta(minutes=1)
    assert notify_ops.tick_tasks_open(db_engine, now).sent == 1
    assert notify_ops.tick_tasks_open(db_engine, now + timedelta(minutes=1)).sent == 0
    _assert_one_tasks_open(db_engine, pid, d, notify_ops.TEXT_TOMORROW)


# pause_ended expired: D = last_midnight(at) (Р5, Ч9); НП3 про перевыданный день — один раз.
def test_np3_after_expired(db_engine):
    pid, pause_id = _paused(db_engine, 4952)
    ended_at = END + timedelta(minutes=5)
    _event(db_engine, pid, "pause_ended", {"pause_id": pause_id, "reason": "expired"}, ended_at)
    run_once(db_engine)
    d = day_clock.last_midnight(ended_at, MSK_NAME)
    assert _u(d) == _u(END)
    assert _u(_started(db_engine, pid)) == _u(d)
    now = ended_at + timedelta(minutes=1)
    assert notify_ops.tick_tasks_open(db_engine, now).sent == 1
    assert notify_ops.tick_tasks_open(db_engine, now + timedelta(minutes=1)).sent == 0
    _assert_one_tasks_open(db_engine, pid, d, notify_ops.TEXT_TODAY)


# Во время паузы НП1 / НП3 / лестницы нет (BLOCKING_FLAGS, без правок).
def test_no_pushes_during_pause(db_engine):
    pid, _pause_id = _paused(db_engine, 4953)
    noon = datetime(2026, 11, 21, 12, 30, tzinfo=MSK)
    notify_ops.tick(db_engine, noon)
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO day_marks (pid, day_started_at, block_id, value, at) "
                "VALUES (:p, :s, 'task_1', true, :at)"
            ),
            {"p": pid, "s": START, "at": noon},
        )
    notify_ops.tick(db_engine, datetime(2026, 11, 21, 22, 30, tzinfo=MSK))
    notify_ops.tick(db_engine, datetime(2026, 11, 21, 23, 45, tzinfo=MSK))
    assert _outbox(db_engine, pid) == []
    with db_engine.connect() as conn:
        keys = conn.execute(
            text("SELECT key FROM idempotency_keys WHERE key LIKE :p"), {"p": f"%:{pid}:%"}
        ).all()
    assert keys == []
