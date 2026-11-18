"""Проектор v5 (api-sleep-1a): block_lives, sleeping, life_op author_cmd, бэкфилл. С БД — только CI.

Тестовое состояние (lives, status_flags, фаза) готовит прямым UPDATE владелец БД — только
в тесте; API participant_state не пишет. События пишет тест напрямую.
"""
import json
import logging
from contextlib import contextmanager

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import projector
from app.day_keys import dsa
from app.projector import (
    EVENT_KIND_LIFE_OP,
    PROJECTOR_VERSION,
    SLEEP_FLAGS,
    ProjectorResult,
    author_life_op_from_payload,
    classify_life_op,
    phase_for_flags,
    run_once,
)
from app.routers.day import enter_day_by_test_flag
from app.routers.onboarding import register_with_consents


class _Stop(Exception):
    pass


@contextmanager
def _fake_lock(engine):
    yield _FakeConn()


class _FakeConn:
    def execute(self, *args, **kwargs):
        return None

    def commit(self):
        return None


# ---------------------------------- без БД ----------------------------------


def test_sleep_flags():
    assert SLEEP_FLAGS == ("pause_user", "author_pause", "pause_shadow", "block_lives", "ban_mod")
    assert "freeze_unpaid" not in SLEEP_FLAGS


def test_phase_for_flags():
    assert phase_for_flags("onboarding", ["block_lives"]) == "sleeping"
    assert phase_for_flags("sleeping", []) == "active"
    assert phase_for_flags("sleeping", ["freeze_unpaid"]) == "active"
    assert phase_for_flags("muted", ["block_lives"]) == "muted"
    assert phase_for_flags("onboarding", []) == "onboarding"


def test_classify_life_op():
    assert classify_life_op(0, 1, []) == "lives_zero_use_revive"
    assert classify_life_op(2, 1, ["block_lives"]) == "lives_zero_use_revive"
    assert classify_life_op(3, 1, []) == "life_above_max"
    assert classify_life_op(1, -2, []) == "life_below_zero"
    assert classify_life_op(3, -2, []) is None


def test_author_life_op_from_payload():
    for delta in (1, 2, 3, -1, -2, -3):
        assert author_life_op_from_payload({"delta": delta, "reason": "author_cmd"}) == delta
    for delta in (True, 0, 4, -4, "1"):
        assert author_life_op_from_payload({"delta": delta, "reason": "author_cmd"}) is None
    assert author_life_op_from_payload({"reason": "author_cmd"}) is None


def test_version_is_7():
    assert PROJECTOR_VERSION == 7


def test_run_forever_calls_backfill(monkeypatch):
    calls = {"n": 0}

    def backfill(engine):
        calls["n"] += 1
        return 0

    def sleep(seconds):
        raise _Stop

    monkeypatch.setattr(projector, "_advisory_lock", _fake_lock)
    monkeypatch.setattr(projector, "_backfill_block_lives", backfill)
    monkeypatch.setattr(projector, "_drain", lambda engine: ProjectorResult(0, 0))
    monkeypatch.setattr(projector, "_life_ops_step", lambda engine, last: last)
    monkeypatch.setattr(projector, "_notify_ops_step", lambda engine, last: last)
    with pytest.raises(_Stop):
        projector.run_forever(object(), poll_seconds=1.0, sleep=sleep)  # type: ignore[arg-type]
    assert calls["n"] == 1


def test_run_once_backfill_before_drain(monkeypatch):
    order: list[str] = []

    def backfill(engine):
        order.append("_backfill_block_lives")
        return 0

    def drain(engine):
        order.append("_drain")
        return ProjectorResult(0, 0)

    monkeypatch.setattr(projector, "_advisory_lock", _fake_lock)
    monkeypatch.setattr(projector, "_backfill_block_lives", backfill)
    monkeypatch.setattr(projector, "_drain", drain)
    assert run_once(object()) == ProjectorResult(0, 0)  # type: ignore[arg-type]
    assert order.count("_backfill_block_lives") == 1
    assert order.index("_backfill_block_lives") < order.index("_drain")


# ---------------------------------- с БД ----------------------------------


def _onboarded(engine, tg_user_id: int):
    with Session(engine) as session:
        pid = register_with_consents(session, tg_user_id, ["C0", "C1"]).participant.pid
    run_once(engine)
    return pid


def _open_day(engine, tg_user_id: int):
    pid = _onboarded(engine, tg_user_id)
    with Session(engine) as session:
        enter_day_by_test_flag(session, tg_user_id, True)
    run_once(engine)
    return pid, _state(engine, pid).day_started_at


def _prepare(
    engine, pid, *, lives: int, flags: str = "{}", phase: str | None = None, streak: int = 1
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE participant_state SET lives = :l, missed_streak = :m, "
                "status_flags = CAST(:f AS text[]), "
                "lifecycle_phase = coalesce(:ph, lifecycle_phase) WHERE pid = :p"
            ),
            {"p": pid, "l": lives, "m": streak, "f": flags, "ph": phase},
        )


def _event(engine, pid, payload) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO participant_events (pid, kind, payload, actor, actor_role) "
                "VALUES (:p, :k, CAST(:pl AS jsonb), 'system', 'system')"
            ),
            {"p": pid, "k": EVENT_KIND_LIFE_OP, "pl": json.dumps(payload)},
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


def _missed(started) -> dict:
    return {"day_started_at": dsa(started), "delta": -1, "reason": "missed_days"}


def _author(delta) -> dict:
    return {"delta": delta, "reason": "author_cmd"}


def _warnings(caplog) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.name == "app.projector" and r.levelno == logging.WARNING
    ]


def _infos(caplog) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.name == "app.projector" and r.levelno == logging.INFO
    ]


@pytest.mark.parametrize("flags", ["{}", "{block_lives}"])
def test_missed_days_to_zero_block_lives(db_engine, flags):
    pid, started = _open_day(db_engine, 4501)
    _prepare(db_engine, pid, lives=1, flags=flags)
    _event(db_engine, pid, _missed(started))
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    state = _state(db_engine, pid)
    assert state.lives == 0
    assert state.lifecycle_phase == "sleeping"
    assert list(state.status_flags) == ["block_lives"]
    assert state.projector_version == 7


def test_author_minus_two_keeps_day(db_engine):
    pid, started = _open_day(db_engine, 4502)
    _prepare(db_engine, pid, lives=3, streak=1)
    before = _state(db_engine, pid)
    _event(db_engine, pid, _author(-2))
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    state = _state(db_engine, pid)
    assert state.lives == 1
    assert state.lifecycle_phase == before.lifecycle_phase
    assert (state.stage_no, state.module_no, state.day_no) == (
        before.stage_no,
        before.module_no,
        before.day_no,
    )
    assert state.day_started_at == before.day_started_at
    assert state.missed_streak == before.missed_streak


def test_author_plus_two(db_engine):
    pid, _ = _open_day(db_engine, 4503)
    _prepare(db_engine, pid, lives=1)
    _event(db_engine, pid, _author(2))
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    assert _state(db_engine, pid).lives == 3


def test_author_minus_one_to_zero_sleeping(db_engine):
    pid, _ = _open_day(db_engine, 4504)
    _prepare(db_engine, pid, lives=1)
    _event(db_engine, pid, _author(-1))
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    state = _state(db_engine, pid)
    assert state.lives == 0
    assert state.lifecycle_phase == "sleeping"
    assert list(state.status_flags) == ["block_lives"]


@pytest.mark.parametrize(
    ("lives", "flags", "delta", "reason"),
    [
        (3, "{}", 1, "life_above_max"),
        (1, "{}", -2, "life_below_zero"),
        (0, "{}", 1, "lives_zero_use_revive"),
        (2, "{block_lives}", 1, "lives_zero_use_revive"),
    ],
)
def test_author_skipped_with_reason(db_engine, caplog, lives, flags, delta, reason):
    pid, _ = _open_day(db_engine, 4505)
    _prepare(db_engine, pid, lives=lives, flags=flags)
    _event(db_engine, pid, _author(delta))
    with caplog.at_level(logging.WARNING, logger="app.projector"):
        assert run_once(db_engine) == ProjectorResult(processed=0, skipped=1)
    assert _state(db_engine, pid).lives == lives
    messages = _warnings(caplog)
    assert any(reason in m for m in messages)
    assert all(str(pid) not in m for m in messages)


def test_author_sleeping_skipped(db_engine, caplog):
    pid, _ = _open_day(db_engine, 4506)
    _prepare(db_engine, pid, lives=2, phase="sleeping")
    _event(db_engine, pid, _author(-1))
    with caplog.at_level(logging.WARNING, logger="app.projector"):
        assert run_once(db_engine) == ProjectorResult(processed=0, skipped=1)
    assert _state(db_engine, pid).lives == 2
    messages = _warnings(caplog)
    assert any("phase not allowed" in m for m in messages)
    assert all(str(pid) not in m for m in messages)


def test_author_bad_delta_skipped(db_engine, caplog):
    pid, _ = _open_day(db_engine, 4507)
    _prepare(db_engine, pid, lives=2)
    _event(db_engine, pid, _author(True))
    with caplog.at_level(logging.WARNING, logger="app.projector"):
        assert run_once(db_engine) == ProjectorResult(processed=0, skipped=1)
    assert _state(db_engine, pid).lives == 2
    messages = _warnings(caplog)
    assert any("bad payload" in m for m in messages)
    assert all(str(pid) not in m for m in messages)


def test_backfill_zero_rows(db_engine, caplog):
    a = _onboarded(db_engine, 4511)
    b = _onboarded(db_engine, 4512)
    _prepare(db_engine, a, lives=0, flags="{block_lives}", phase="sleeping")
    _prepare(db_engine, b, lives=0)
    before = {pid: _state(db_engine, pid) for pid in (a, b)}
    with caplog.at_level(logging.INFO, logger="app.projector"):
        run_once(db_engine)
    assert any("backfill block_lives, строк 0" in m for m in _infos(caplog))
    assert {pid: _state(db_engine, pid) for pid in (a, b)} == before


def test_backfill_n_rows(db_engine, caplog):
    a = _onboarded(db_engine, 4521)
    b = _onboarded(db_engine, 4522)
    c = _onboarded(db_engine, 4523)
    d = _onboarded(db_engine, 4524)
    _prepare(db_engine, a, lives=0, phase="sleeping")
    _prepare(db_engine, b, lives=0, phase="sleeping")
    _prepare(db_engine, c, lives=0, flags="{block_lives}", phase="sleeping")
    _prepare(db_engine, d, lives=0)
    others = {pid: _state(db_engine, pid) for pid in (c, d)}
    with caplog.at_level(logging.INFO, logger="app.projector"):
        run_once(db_engine)
    assert any("backfill block_lives, строк 2" in m for m in _infos(caplog))
    for pid in (a, b):
        state = _state(db_engine, pid)
        assert list(state.status_flags) == ["block_lives"]
        assert state.projector_version == 7
    assert {pid: _state(db_engine, pid) for pid in (c, d)} == others
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="app.projector"):
        run_once(db_engine)
    assert any("backfill block_lives, строк 0" in m for m in _infos(caplog))
