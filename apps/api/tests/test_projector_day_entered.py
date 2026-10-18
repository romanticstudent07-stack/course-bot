"""Проектор: kind day_entered (iter2-api-2a, PROJECTOR_VERSION 2). С БД — только CI.

Ревью #101: граница MAX_POSITION_VALUE, SAVEPOINT на событие (битое событие не
останавливает пачку), checkpoint сдвигается и при пропуске.
"""
import json
import logging

from sqlalchemy import text

import app.projector as projector
from app.projector import (
    MAX_POSITION_VALUE,
    PROJECTOR_VERSION,
    ProjectorResult,
    position_from_payload,
    run_once,
)

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


def _checkpoint(engine, pid):
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT last_event_id FROM participant_state_checkpoints WHERE pid = :p"),
            {"p": pid},
        ).scalar_one_or_none()


def _onboarded(engine, tg_user_id: int):
    pid = _participant(engine, tg_user_id)
    _event(engine, pid, "mini_app_first_consent", {"schema_version": 1})
    assert run_once(engine) == ProjectorResult(processed=1, skipped=0)
    return pid


def _projector_warnings(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == "app.projector"]


def test_position_from_payload():
    assert position_from_payload(POSITION) == (1, 1, 1)
    assert position_from_payload(json.dumps(POSITION)) == (1, 1, 1)
    assert position_from_payload({"stage_no": 1, "module_no": 1}) is None
    assert position_from_payload({"stage_no": 0, "module_no": 1, "day_no": 1}) is None
    assert position_from_payload({"stage_no": True, "module_no": 1, "day_no": 1}) is None
    assert position_from_payload("not json") is None
    assert PROJECTOR_VERSION == 2


def test_position_upper_bound():
    assert MAX_POSITION_VALUE == 32767
    edge = {"stage_no": 32767, "module_no": 32767, "day_no": 32767}
    assert position_from_payload(edge) == (32767, 32767, 32767)
    for field in ("stage_no", "module_no", "day_no"):
        assert position_from_payload(dict(POSITION, **{field: 32768})) is None
        assert position_from_payload(dict(POSITION, **{field: 2**63})) is None


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
    pid = _onboarded(db_engine, 9102)
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
    second = _event(db_engine, pid, "day_entered", dict(POSITION, day_no=2))
    caplog.set_level(logging.WARNING, logger="app.projector")
    assert run_once(db_engine) == ProjectorResult(processed=0, skipped=1)
    state = _state(db_engine, pid)
    assert state.day_no == 1 and state.day_started_at == first.at
    assert state.lifecycle_phase == "onboarding"
    assert _checkpoint(db_engine, pid) == second.id
    warnings = _projector_warnings(caplog)
    assert any("day_entered" in message for message in warnings)
    assert all(str(pid) not in message and "test_flag" not in message for message in warnings)


def test_day_entered_without_state_skipped(db_engine):
    pid = _participant(db_engine, 9104)
    event = _event(db_engine, pid, "day_entered", POSITION)
    assert run_once(db_engine) == ProjectorResult(processed=0, skipped=1)
    with db_engine.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM participant_state WHERE pid = :p"), {"p": pid}
        ).scalar_one()
    assert count == 0
    assert _checkpoint(db_engine, pid) == event.id


def _assert_bad_day_no_skipped(db_engine, caplog, tg_user_id: int, day_no: int) -> None:
    pid = _onboarded(db_engine, tg_user_id)
    event = _event(db_engine, pid, "day_entered", dict(POSITION, day_no=day_no))
    caplog.set_level(logging.WARNING, logger="app.projector")
    assert run_once(db_engine) == ProjectorResult(processed=0, skipped=1)
    state = _state(db_engine, pid)
    assert (state.stage_no, state.module_no, state.day_no, state.day_started_at) == (
        None,
        None,
        None,
        None,
    )
    assert _checkpoint(db_engine, pid) == event.id
    warnings = _projector_warnings(caplog)
    assert any(
        f"id={event.id}" in m and "kind=day_entered" in m and "bad payload" in m for m in warnings
    )
    assert all(str(pid) not in m and str(day_no) not in m for m in warnings)


def test_day_no_2_pow_63_skipped(db_engine, caplog):
    _assert_bad_day_no_skipped(db_engine, caplog, 9105, 2**63)


def test_day_no_32768_skipped(db_engine, caplog):
    _assert_bad_day_no_skipped(db_engine, caplog, 9106, 32768)


def test_db_error_in_one_event_does_not_stop_batch(db_engine, caplog, monkeypatch):
    # Обходим проверку границы: позиция вне диапазона smallint доходит до БД → DataError
    # внутри SAVEPOINT. В той же пачке годное событие другого pid применяется.
    pid_a = _onboarded(db_engine, 9107)
    bad = _event(db_engine, pid_a, "day_entered", POSITION)
    pid_b = _participant(db_engine, 9108)
    good = _event(db_engine, pid_b, "mini_app_first_consent", {"schema_version": 1})
    monkeypatch.setattr(projector, "position_from_payload", lambda payload: (1, 1, 2**63))
    caplog.set_level(logging.WARNING, logger="app.projector")

    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=1)

    assert _state(db_engine, pid_b).lifecycle_phase == "onboarding"
    assert _checkpoint(db_engine, pid_b) == good.id
    state_a = _state(db_engine, pid_a)
    assert state_a.day_no is None and state_a.lifecycle_phase == "onboarding"
    assert _checkpoint(db_engine, pid_a) == bad.id
    warnings = _projector_warnings(caplog)
    assert any(
        f"id={bad.id}" in m
        and "kind=day_entered" in m
        and "bad payload" in m
        and ("DataError" in m or "IntegrityError" in m)
        for m in warnings
    )
    assert all(str(pid_a) not in m and str(pid_b) not in m for m in warnings)
