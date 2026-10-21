"""Проектор v3 (life-ops-a): day_report_submitted с next_*, life_op, day_closed. С БД — только CI.

Тестовое состояние (lives, missed_streak, status_flags) готовится прямым UPDATE от владельца
БД — только в тесте; API participant_state не пишет. События пишет тест напрямую:
после life-ops-a их пишут только задачи life-ops-b и life-ops-c.
"""
import json
import logging
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.day_keys import dsa
from app.projector import (
    EVENT_KIND_DAY_CLOSED,
    EVENT_KIND_DAY_REPORT_SUBMITTED,
    EVENT_KIND_LIFE_OP,
    PROJECTOR_VERSION,
    ProjectorResult,
    run_once,
)
from app.routers.day import enter_day_by_test_flag
from app.routers.onboarding import register_with_consents

OLD_DAY = "2001-01-01T00:00:00+00:00"
NEXT_DAY = datetime(2030, 1, 2, 1, 0, tzinfo=timezone.utc)


def test_version_is_3():
    assert PROJECTOR_VERSION == 3


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


def _prepare(
    engine, pid, *, lives: int = 3, missed_streak: int = 1, phase: str | None = None
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE participant_state SET missed_streak = :m, lives = :l, "
                "status_flags = CAST(:f AS text[]), "
                "lifecycle_phase = coalesce(:ph, lifecycle_phase) WHERE pid = :p"
            ),
            {"p": pid, "m": missed_streak, "l": lives, "f": "{block_lives}", "ph": phase},
        )


def _event(engine, pid, kind, payload) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO participant_events (pid, kind, payload, actor, actor_role) "
                "VALUES (:p, :k, CAST(:pl AS jsonb), 'system', 'system')"
            ),
            {"p": pid, "k": kind, "pl": json.dumps(payload)},
        )


def _state(engine, pid):
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT stage_no, module_no, day_no, day_started_at, missed_streak, lives, "
                "lifecycle_phase, status_flags, projector_version "
                "FROM participant_state WHERE pid = :p"
            ),
            {"p": pid},
        ).one()


def _report(started_str: str, **extra) -> dict:
    payload = {
        "day_started_at": started_str,
        "verdict": "passed",
        "stage_no": 1,
        "module_no": 1,
        "day_no": 1,
    }
    payload.update(extra)
    return payload


def _next(**override) -> dict:
    fields = {
        "next_stage_no": 1,
        "next_module_no": 1,
        "next_day_no": 2,
        "next_day_started_at": dsa(NEXT_DAY),
    }
    fields.update(override)
    return fields


def _life_op(started_str: str, delta: int = -1) -> dict:
    return {"day_started_at": started_str, "delta": delta, "reason": "missed_days"}


def _closed(started_str: str, missed_streak: int = 1, outcome: str = "silent") -> dict:
    return {
        "day_started_at": started_str,
        "outcome": outcome,
        "missed_streak": missed_streak,
        "next_day_started_at": dsa(NEXT_DAY),
    }


def _warnings(caplog) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.name == "app.projector" and r.levelno == logging.WARNING
    ]


# --- day_report_submitted v3 ---
def test_report_with_next_fields_advances_day(db_engine):
    pid, started = _open_day(db_engine, 9501)
    _prepare(db_engine, pid, missed_streak=1, lives=2)
    _event(db_engine, pid, EVENT_KIND_DAY_REPORT_SUBMITTED, _report(dsa(started), **_next()))
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    state = _state(db_engine, pid)
    assert (state.stage_no, state.module_no, state.day_no) == (1, 1, 2)
    assert dsa(state.day_started_at) == dsa(NEXT_DAY)
    assert state.missed_streak == 0
    assert state.lives == 2
    assert state.lifecycle_phase == "onboarding"
    assert list(state.status_flags) == ["block_lives"]
    assert state.projector_version == 3


def test_old_payload_103_only_resets_streak(db_engine):
    pid, started = _open_day(db_engine, 9502)
    _prepare(db_engine, pid, missed_streak=1)
    _event(db_engine, pid, EVENT_KIND_DAY_REPORT_SUBMITTED, _report(dsa(started)))
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    state = _state(db_engine, pid)
    assert state.missed_streak == 0
    assert (state.stage_no, state.module_no, state.day_no) == (1, 1, 1)
    assert dsa(state.day_started_at) == dsa(started)


@pytest.mark.parametrize(
    "partial",
    [
        {"next_day_no": 2},
        {"next_stage_no": 1, "next_module_no": 1, "next_day_no": 2},
        _next(next_day_no=0),
        _next(next_day_no=True),
        _next(next_day_started_at=""),
    ],
)
def test_report_partial_next_fields_skipped(db_engine, caplog, partial):
    pid, started = _open_day(db_engine, 9503)
    _prepare(db_engine, pid, missed_streak=1)
    _event(db_engine, pid, EVENT_KIND_DAY_REPORT_SUBMITTED, _report(dsa(started), **partial))
    with caplog.at_level(logging.WARNING, logger="app.projector"):
        assert run_once(db_engine) == ProjectorResult(processed=0, skipped=1)
    state = _state(db_engine, pid)
    assert state.missed_streak == 1
    assert state.day_no == 1
    messages = _warnings(caplog)
    assert any("bad payload" in m for m in messages)
    assert all(str(pid) not in m for m in messages)


def test_report_bad_next_date_skipped_next_applied(db_engine):
    pid, started = _open_day(db_engine, 9504)
    _prepare(db_engine, pid, missed_streak=1)
    _event(
        db_engine,
        pid,
        EVENT_KIND_DAY_REPORT_SUBMITTED,
        _report(dsa(started), **_next(next_day_started_at="not-a-date")),
    )
    _event(db_engine, pid, EVENT_KIND_DAY_REPORT_SUBMITTED, _report(dsa(started), **_next()))
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=1)
    assert _state(db_engine, pid).day_no == 2


def test_report_other_day_skipped(db_engine, caplog):
    pid, started = _open_day(db_engine, 9505)
    _prepare(db_engine, pid, missed_streak=1)
    _event(db_engine, pid, EVENT_KIND_DAY_REPORT_SUBMITTED, _report(OLD_DAY, **_next()))
    with caplog.at_level(logging.WARNING, logger="app.projector"):
        assert run_once(db_engine) == ProjectorResult(processed=0, skipped=1)
    state = _state(db_engine, pid)
    assert state.day_no == 1
    assert dsa(state.day_started_at) == dsa(started)
    assert state.missed_streak == 1
    assert any(f"kind={EVENT_KIND_DAY_REPORT_SUBMITTED}" in m for m in _warnings(caplog))


# --- life_op ---
def test_life_op_minus_one(db_engine):
    pid, started = _open_day(db_engine, 9511)
    _prepare(db_engine, pid, lives=3)
    _event(db_engine, pid, EVENT_KIND_LIFE_OP, _life_op(dsa(started)))
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    state = _state(db_engine, pid)
    assert state.lives == 2
    assert state.lifecycle_phase == "onboarding"
    assert dsa(state.day_started_at) == dsa(started)
    assert state.missed_streak == 1  # life_op счётчик не трогает
    assert list(state.status_flags) == ["block_lives"]


def test_life_op_to_zero_sleeping(db_engine):
    pid, started = _open_day(db_engine, 9512)
    _prepare(db_engine, pid, lives=1)
    _event(db_engine, pid, EVENT_KIND_LIFE_OP, _life_op(dsa(started)))
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    state = _state(db_engine, pid)
    assert state.lives == 0
    assert state.lifecycle_phase == "sleeping"


# (3, 1): delta +1 теперь «bad payload» (Н3) — тоже пропуск без изменений.
@pytest.mark.parametrize(("lives", "delta"), [(0, -1), (3, 1)])
def test_life_op_out_of_range_skipped(db_engine, caplog, lives, delta):
    pid, started = _open_day(db_engine, 9513)
    _prepare(db_engine, pid, lives=lives)
    _event(db_engine, pid, EVENT_KIND_LIFE_OP, _life_op(dsa(started), delta))
    with caplog.at_level(logging.WARNING, logger="app.projector"):
        assert run_once(db_engine) == ProjectorResult(processed=0, skipped=1)
    state = _state(db_engine, pid)
    assert state.lives == lives
    assert state.lifecycle_phase == "onboarding"
    assert any(f"kind={EVENT_KIND_LIFE_OP}" in m for m in _warnings(caplog))


def test_life_op_other_day_skipped(db_engine):
    pid, _ = _open_day(db_engine, 9514)
    _prepare(db_engine, pid, lives=3)
    _event(db_engine, pid, EVENT_KIND_LIFE_OP, _life_op(OLD_DAY))
    assert run_once(db_engine) == ProjectorResult(processed=0, skipped=1)
    assert _state(db_engine, pid).lives == 3


@pytest.mark.parametrize(
    "payload",
    [
        {"delta": -1, "reason": "missed_days"},
        {"day_started_at": OLD_DAY, "delta": True},
        # Н3 (ревью #111): только delta == −1 и reason == "missed_days".
        {"day_started_at": OLD_DAY, "delta": 1, "reason": "missed_days"},
        {"day_started_at": OLD_DAY, "delta": -2, "reason": "missed_days"},
        {"day_started_at": OLD_DAY, "delta": 0, "reason": "missed_days"},
        {"day_started_at": OLD_DAY, "delta": -1, "reason": "other"},
        {"day_started_at": OLD_DAY, "delta": -1},
    ],
)
def test_life_op_bad_payload_skipped(db_engine, caplog, payload):
    pid, started = _open_day(db_engine, 9515)
    _prepare(db_engine, pid, lives=3)
    if "day_started_at" in payload:
        payload = dict(payload, day_started_at=dsa(started))
    _event(db_engine, pid, EVENT_KIND_LIFE_OP, payload)
    with caplog.at_level(logging.WARNING, logger="app.projector"):
        assert run_once(db_engine) == ProjectorResult(processed=0, skipped=1)
    assert _state(db_engine, pid).lives == 3
    assert any("bad payload" in m for m in _warnings(caplog))


# Н2 (ревью #111): life_op — только для onboarding и active (В29).
def test_life_op_active_applied(db_engine):
    pid, started = _open_day(db_engine, 9516)
    _prepare(db_engine, pid, lives=1, phase="active")
    _event(db_engine, pid, EVENT_KIND_LIFE_OP, _life_op(dsa(started)))
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    state = _state(db_engine, pid)
    assert state.lives == 0
    assert state.lifecycle_phase == "sleeping"


@pytest.mark.parametrize("phase", ["muted", "sleeping"])
def test_life_op_muted_or_sleeping_skipped(db_engine, caplog, phase):
    pid, started = _open_day(db_engine, 9517)
    _prepare(db_engine, pid, lives=1, phase=phase)
    _event(db_engine, pid, EVENT_KIND_LIFE_OP, _life_op(dsa(started)))
    with caplog.at_level(logging.WARNING, logger="app.projector"):
        assert run_once(db_engine) == ProjectorResult(processed=0, skipped=1)
    state = _state(db_engine, pid)
    assert state.lives == 1
    assert state.lifecycle_phase == phase
    assert any(f"kind={EVENT_KIND_LIFE_OP}" in m for m in _warnings(caplog))


# Н4 (ревью #111): фиксирует ТЕКУЩЕЕ поведение — два life_op одного дня без day_closed
# применяются оба (−2 жизни). Проектор это не ловит; защита — у писателя (life-ops-c):
# life_op, day_closed и ключ day_close в одной транзакции под participant:pid.
def test_two_life_ops_same_day_both_applied(db_engine):
    pid, started = _open_day(db_engine, 9518)
    _prepare(db_engine, pid, lives=3)
    _event(db_engine, pid, EVENT_KIND_LIFE_OP, _life_op(dsa(started)))
    _event(db_engine, pid, EVENT_KIND_LIFE_OP, _life_op(dsa(started)))
    assert run_once(db_engine) == ProjectorResult(processed=2, skipped=0)
    state = _state(db_engine, pid)
    assert state.lives == 1
    assert dsa(state.day_started_at) == dsa(started)


# --- day_closed ---
@pytest.mark.parametrize(("outcome", "streak"), [("silent", 1), ("came", 0)])
def test_day_closed_moves_day_keeps_position(db_engine, outcome, streak):
    pid, started = _open_day(db_engine, 9521)
    _prepare(db_engine, pid, lives=3, missed_streak=0 if outcome == "silent" else 1)
    _event(db_engine, pid, EVENT_KIND_DAY_CLOSED, _closed(dsa(started), streak, outcome))
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    state = _state(db_engine, pid)
    assert dsa(state.day_started_at) == dsa(NEXT_DAY)
    assert state.missed_streak == streak
    assert (state.stage_no, state.module_no, state.day_no) == (1, 1, 1)
    assert state.lives == 3
    assert state.lifecycle_phase == "onboarding"


def test_day_closed_other_day_skipped(db_engine, caplog):
    pid, started = _open_day(db_engine, 9522)
    _prepare(db_engine, pid, missed_streak=0)
    _event(db_engine, pid, EVENT_KIND_DAY_CLOSED, _closed(OLD_DAY))
    with caplog.at_level(logging.WARNING, logger="app.projector"):
        assert run_once(db_engine) == ProjectorResult(processed=0, skipped=1)
    state = _state(db_engine, pid)
    assert dsa(state.day_started_at) == dsa(started)
    assert state.missed_streak == 0
    assert any(f"kind={EVENT_KIND_DAY_CLOSED}" in m for m in _warnings(caplog))


@pytest.mark.parametrize(
    "override",
    [{"outcome": "other"}, {"missed_streak": -1}, {"missed_streak": "1"}, {"next_day_started_at": ""}],
)
def test_day_closed_bad_payload_skipped(db_engine, override):
    pid, started = _open_day(db_engine, 9523)
    _prepare(db_engine, pid, missed_streak=0)
    _event(db_engine, pid, EVENT_KIND_DAY_CLOSED, dict(_closed(dsa(started)), **override))
    assert run_once(db_engine) == ProjectorResult(processed=0, skipped=1)
    assert dsa(_state(db_engine, pid).day_started_at) == dsa(started)


# Н5 (ревью #111): next_day_started_at не позже текущего → пропуск (иначе повтор применится).
@pytest.mark.parametrize("shift", [timedelta(0), timedelta(seconds=-1)])
def test_day_closed_next_not_later_skipped(db_engine, caplog, shift):
    pid, started = _open_day(db_engine, 9524)
    _prepare(db_engine, pid, missed_streak=0)
    payload = dict(_closed(dsa(started)), next_day_started_at=dsa(started + shift))
    _event(db_engine, pid, EVENT_KIND_DAY_CLOSED, payload)
    with caplog.at_level(logging.WARNING, logger="app.projector"):
        assert run_once(db_engine) == ProjectorResult(processed=0, skipped=1)
    state = _state(db_engine, pid)
    assert dsa(state.day_started_at) == dsa(started)
    assert state.missed_streak == 0
    assert any(f"kind={EVENT_KIND_DAY_CLOSED}" in m for m in _warnings(caplog))


# --- порядок life-ops-c: life_op, затем day_closed; повтор не применяется ---
def test_life_op_then_day_closed_and_replay(db_engine):
    pid, started = _open_day(db_engine, 9531)
    _prepare(db_engine, pid, lives=2, missed_streak=1)
    _event(db_engine, pid, EVENT_KIND_LIFE_OP, _life_op(dsa(started)))
    _event(db_engine, pid, EVENT_KIND_DAY_CLOSED, _closed(dsa(started), 0))
    assert run_once(db_engine) == ProjectorResult(processed=2, skipped=0)
    state = _state(db_engine, pid)
    assert state.lives == 1
    assert state.missed_streak == 0
    assert dsa(state.day_started_at) == dsa(NEXT_DAY)
    # once дважды — без изменений (checkpoint сдвинут).
    assert run_once(db_engine) == ProjectorResult(processed=0, skipped=0)
    assert _state(db_engine, pid) == state
    # Повтор тех же событий (как после рестарта писателя) — день уже другой, пропуск.
    _event(db_engine, pid, EVENT_KIND_LIFE_OP, _life_op(dsa(started)))
    _event(db_engine, pid, EVENT_KIND_DAY_CLOSED, _closed(dsa(started), 0))
    assert run_once(db_engine) == ProjectorResult(processed=0, skipped=2)
    assert _state(db_engine, pid) == state


def test_next_day_started_at_any_zone_same_moment(db_engine):
    pid, started = _open_day(db_engine, 9532)
    _prepare(db_engine, pid)
    local = NEXT_DAY.astimezone(timezone(timedelta(hours=3))).isoformat()
    _event(
        db_engine,
        pid,
        EVENT_KIND_DAY_CLOSED,
        dict(_closed(dsa(started)), next_day_started_at=local),
    )
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    assert dsa(_state(db_engine, pid).day_started_at) == dsa(NEXT_DAY)
