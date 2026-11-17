"""Проектор v5 (api-sleep-1a): журнал списаний life_writeoffs (0019). С БД — только CI.

Тестовое состояние готовит прямым UPDATE владелец БД — только в тесте. События пишет тест
напрямую; DELETE checkpoint — тоже только в тесте (владелец БД).
"""
import json
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.day_keys import dsa
from app.projector import (
    _INSERT_LIFE_WRITEOFF,
    EVENT_KIND_LIFE_OP,
    ProjectorResult,
    run_once,
)
from app.routers.day import enter_day_by_test_flag
from app.routers.onboarding import register_with_consents

OLD_DAY = "2001-01-01T00:00:00+00:00"
INSERT_SQL = (
    "INSERT INTO life_writeoffs (pid, event_id, stage_no, module_no, day_no) "
    "VALUES (:pid, :event_id, :s, :m, :d) ON CONFLICT (event_id) DO NOTHING"
)
MIGRATION_0019 = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "2026_11_17_1200-0019_life_writeoffs_life_writeoffs.py"
)


def _norm(value: str) -> str:
    return " ".join(value.split())


# ---------------------------------- без БД ----------------------------------


def test_insert_sql_matches_0019():
    assert _norm(_INSERT_LIFE_WRITEOFF.text) == INSERT_SQL
    assert INSERT_SQL in _norm(MIGRATION_0019.read_text(encoding="utf-8"))
    assert "RETURNING" not in _INSERT_LIFE_WRITEOFF.text


# ---------------------------------- с БД ----------------------------------


def _open_day(engine, tg_user_id: int):
    with Session(engine) as session:
        pid = register_with_consents(session, tg_user_id, ["C0", "C1"]).participant.pid
    run_once(engine)
    with Session(engine) as session:
        enter_day_by_test_flag(session, tg_user_id, True)
    run_once(engine)
    with engine.connect() as conn:
        started = conn.execute(
            text("SELECT day_started_at FROM participant_state WHERE pid = :p"), {"p": pid}
        ).scalar_one()
    return pid, started


def _event(engine, pid, payload) -> int:
    with engine.begin() as conn:
        return conn.execute(
            text(
                "INSERT INTO participant_events (pid, kind, payload, actor, actor_role) "
                "VALUES (:p, :k, CAST(:pl AS jsonb), 'system', 'system') RETURNING id"
            ),
            {"p": pid, "k": EVENT_KIND_LIFE_OP, "pl": json.dumps(payload)},
        ).scalar_one()


def _missed(started) -> dict:
    return {"day_started_at": started, "delta": -1, "reason": "missed_days"}


def _rows(engine, event_id: int):
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT pid, event_id, stage_no, module_no, day_no FROM life_writeoffs "
                "WHERE event_id = :e"
            ),
            {"e": event_id},
        ).all()


def test_missed_days_writes_row(db_engine):
    pid, started = _open_day(db_engine, 4551)
    event_id = _event(db_engine, pid, _missed(dsa(started)))
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    rows = _rows(db_engine, event_id)
    assert len(rows) == 1
    assert rows[0].pid == pid
    assert (rows[0].stage_no, rows[0].module_no, rows[0].day_no) == (1, 1, 1)
    with db_engine.connect() as conn:
        joined = conn.execute(
            text(
                "SELECT count(*) FROM life_writeoffs w "
                "JOIN participant_events e ON e.id = w.event_id AND e.pid = w.pid "
                "WHERE w.event_id = :e"
            ),
            {"e": event_id},
        ).scalar_one()
    assert joined == 1


def test_two_participants_one_batch(db_engine):
    pid_a, started_a = _open_day(db_engine, 4552)
    pid_b, started_b = _open_day(db_engine, 4553)
    event_a = _event(db_engine, pid_a, _missed(dsa(started_a)))
    event_b = _event(db_engine, pid_b, _missed(dsa(started_b)))
    assert run_once(db_engine) == ProjectorResult(processed=2, skipped=0)
    assert [r.pid for r in _rows(db_engine, event_a)] == [pid_a]
    assert [r.pid for r in _rows(db_engine, event_b)] == [pid_b]


def test_replay_no_duplicate(db_engine):
    pid, started = _open_day(db_engine, 4554)
    event_id = _event(db_engine, pid, _missed(dsa(started)))
    run_once(db_engine)
    with db_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM participant_state_checkpoints WHERE pid = :p"), {"p": pid}
        )
    run_once(db_engine)
    assert len(_rows(db_engine, event_id)) == 1


def test_author_cmd_no_row(db_engine):
    pid, _ = _open_day(db_engine, 4555)
    event_id = _event(db_engine, pid, {"delta": -2, "reason": "author_cmd"})
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    assert _rows(db_engine, event_id) == []


def test_skipped_life_op_no_row(db_engine):
    pid, _ = _open_day(db_engine, 4556)
    event_id = _event(db_engine, pid, _missed(OLD_DAY))
    assert run_once(db_engine) == ProjectorResult(processed=0, skipped=1)
    assert _rows(db_engine, event_id) == []
