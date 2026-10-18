"""Проектор: kind day_entered (iter2-api-2a, PROJECTOR_VERSION 2). С БД — только CI."""
import json
import logging

from sqlalchemy import text

from app.projector import PROJECTOR_VERSION, ProjectorResult, position_from_payload, run_once

POSITION = {"stage_no": 1, "module_no": 1, "day_no": 1, "source": "test_flag"}


def _participant(engine, tg_user_id: int):
    with engine.begin() as conn:
        return conn.execute(
            text(
                "INSERT INTO tg_user_registry (pid, tg_user_id, created_via, created_at) "
                "VALUES (gen_random_uuid(), :u, 'mini_app_first_launch', now()) RETURNING pid"
            ),
            {"u": tg_user_id},
        ).scalar_one()


def _event(engine, pid, kind: str, payload: dict):
    with engine.begin() as conn:
        return conn.execute(
            text(
                "INSERT INTO participant_events (pid, kind, payload, actor, actor_role) "
                "VALUES (:pid, :kind, CAST(:payload AS jsonb), 'system', 'system') "
                "RETURNING id, at"
            ),
            {"pid": pid, "kind": kind, "payload": json.dumps(payload)},
        ).one()


def _state(engine, pid):
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT lifecycle_phase, status_flags, stage_no, module_no, day_no, "
                "day_started_at, missed_streak, projector_version "
                "FROM participant_state WHERE pid = :p"
            ),
            {"p": pid},
        ).one()


def test_position_from_payload():
    assert position_from_payload(POSITION) == (1, 1, 1)
    assert position_from_payload(json.dumps(POSITION)) == (1, 1, 1)
    assert position_from_payload({"stage_no": 1, "module_no": 1}) is None
    assert position_from_payload({"stage_no": 0, "module_no": 1, "day_no": 1}) is None
    assert position_from_payload({"stage_no": True, "module_no": 1, "day_no": 1}) is None
    assert position_from_payload("not json") is None
    assert PROJECTOR_VERSION == 2


def test_consent_and_day_entered_in_one_batch(db_engine):
    pid = _participant(db_engine, 9101)
    _event(db_engine, pid, "mini_app_first_consent", {"schema_version": 1})
    entered = _event(db_engine, pid, "day_entered", POSITION)
    assert run_once(db_engine) == ProjectorResult(processed=2, skipped=0)
    state = _state(db_engine, pid)
    assert state.lifecycle_phase == "onboarding"
    assert list(state.status_flags) == []
    assert (state.stage_no, state.module_no, state.day_no) == (1, 1, 1)
    assert state.day_started_at == entered.at
    assert state.missed_streak == 0
    assert state.projector_version == 2


def test_day_entered_keeps_status_flags(db_engine):
    pid = _participant(db_engine, 9102)
    _event(db_engine, pid, "mini_app_first_consent", {"schema_version": 1})
    run_once(db_engine)
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE participant_state SET status_flags = '{block_lives}' WHERE pid = :p"),
            {"p": pid},
        )
    _event(db_engine, pid, "day_entered", POSITION)
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    state = _state(db_engine, pid)
    assert list(state.status_flags) == ["block_lives"]
    assert state.lifecycle_phase == "onboarding"
    assert state.day_no == 1


def test_repeat_day_entered_skipped(db_engine, caplog):
    pid = _participant(db_engine, 9103)
    _event(db_engine, pid, "mini_app_first_consent", {"schema_version": 1})
    first = _event(db_engine, pid, "day_entered", POSITION)
    run_once(db_engine)
    _event(db_engine, pid, "day_entered", dict(POSITION, day_no=2))
    caplog.set_level(logging.WARNING, logger="app.projector")
    assert run_once(db_engine) == ProjectorResult(processed=0, skipped=1)
    state = _state(db_engine, pid)
    assert state.day_no == 1 and state.day_started_at == first.at
    assert state.lifecycle_phase == "onboarding"
    warnings = [r.getMessage() for r in caplog.records if r.name == "app.projector"]
    assert any("day_entered" in message for message in warnings)
    assert all(str(pid) not in message and "test_flag" not in message for message in warnings)


def test_day_entered_without_state_skipped(db_engine):
    pid = _participant(db_engine, 9104)
    _event(db_engine, pid, "day_entered", POSITION)
    assert run_once(db_engine) == ProjectorResult(processed=0, skipped=1)
    with db_engine.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM participant_state WHERE pid = :p"), {"p": pid}
        ).scalar_one()
    assert count == 0
