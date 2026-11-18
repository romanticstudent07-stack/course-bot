"""Проектор v7 (api-revive-1): revive_by_author. С БД — только CI.

Тестовое состояние готовит прямым UPDATE владелец БД — только в тесте; позиция
(stage_no, module_no, day_no, day_started_at) задана целиком или вся NULL, lives 0..3.
Событие revive_by_author пишет тест напрямую (писателя ещё нет, bot-revive-1);
actor 'bot', actor_role 'owner' — по контракту §7.1.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import day_clock, notify_ops, projector
from app.projector import (
    EVENT_KIND_REVIVE_BY_AUTHOR,
    ProjectorResult,
    revive_from_payload,
    run_once,
)
from app.routers.day import enter_day_by_test_flag
from app.routers.onboarding import register_with_consents

MSK_NAME = "Europe/Moscow"
MSK = ZoneInfo(MSK_NAME)
AT = datetime(2026, 11, 20, 9, 0, tzinfo=MSK)
OLD_STARTED = datetime(2026, 11, 1, 0, 0, tzinfo=MSK)


def _u(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc)


def _payload(target=(2, 3, 1), lives_returned=1) -> dict:
    s, m, d = target
    return {
        "target": {"stage_no": s, "module_no": m, "day_no": d},
        "lives_returned": lives_returned,
    }


# ---------------------------------- без БД ----------------------------------


# V9: revive_from_payload — валидный → кортеж; каждый битый случай → None.
def test_v9_revive_from_payload():
    assert revive_from_payload(_payload()) == ((2, 3, 1), 1)
    extra = {**_payload(), "extra": "x"}
    extra["target"]["note"] = 1
    assert revive_from_payload(extra) == ((2, 3, 1), 1)
    assert revive_from_payload(json.dumps(_payload(lives_returned=0))) == ((2, 3, 1), 0)

    def with_field(value) -> dict:
        data = _payload()
        data["target"]["day_no"] = value
        return data

    bad = [
        {"lives_returned": 1},
        {"target": [2, 3, 1], "lives_returned": 1},
        with_field(True),
        with_field(0),
        with_field(-1),
        with_field("1"),
        with_field(1.0),
        {"target": {"stage_no": 2, "module_no": 3, "day_no": 1}},
        _payload(lives_returned=False),
        _payload(lives_returned=-1),
        [1, 2],
        "not json",
    ]
    for payload in bad:
        assert revive_from_payload(payload) is None


# V11: kind совпадает в notify_ops и projector; REISSUE_KINDS — оба вида перевыдачи.
def test_v11_kind_shared():
    assert notify_ops.EVENT_KIND_REVIVE_BY_AUTHOR == projector.EVENT_KIND_REVIVE_BY_AUTHOR
    assert notify_ops.REISSUE_KINDS == ("restart_paid", "revive_by_author", "pause_ended")


# ---------------------------------- с БД ----------------------------------


def _onboarded(engine, tg_user_id: int):
    with Session(engine) as session:
        pid = register_with_consents(session, tg_user_id, ["C0", "C1"]).participant.pid
    run_once(engine)
    return pid


def _blocked(engine, tg_user_id: int, flags: str = "{block_lives}"):
    """sleeping, lives 0, позиция (2, 3, 5, OLD_STARTED), tz Europe/Moscow."""
    pid = _onboarded(engine, tg_user_id)
    with Session(engine) as session:
        enter_day_by_test_flag(session, tg_user_id, True)
    run_once(engine)
    _set(engine, pid, lives=0, flags=flags, phase="sleeping")
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE participant_state SET stage_no = 2, module_no = 3, day_no = 5, "
                "day_started_at = :s, missed_streak = 1, tz = :tz WHERE pid = :p"
            ),
            {"p": pid, "s": OLD_STARTED, "tz": MSK_NAME},
        )
    return pid


def _set(engine, pid, *, lives: int, flags: str, phase: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE participant_state SET lives = :l, status_flags = CAST(:f AS text[]), "
                "lifecycle_phase = :ph WHERE pid = :p"
            ),
            {"p": pid, "l": lives, "f": flags, "ph": phase},
        )


def _revive(engine, pid, payload=None, at: datetime = AT) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO participant_events (pid, kind, payload, actor, actor_role, at) "
                "VALUES (:p, :k, CAST(:pl AS jsonb), 'bot', 'owner', :at)"
            ),
            {
                "p": pid,
                "k": EVENT_KIND_REVIVE_BY_AUTHOR,
                "pl": json.dumps(payload if payload is not None else _payload()),
                "at": at,
            },
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
        ).first()


def _count(engine, table: str, pid) -> int:
    assert table in ("day_marks", "life_writeoffs")
    with engine.connect() as conn:
        return conn.execute(
            text(f"SELECT count(*) FROM {table} WHERE pid = :p"), {"p": pid}
        ).scalar_one()


def _budget(engine, pid):
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT days_budget_remaining_annual, cycle_start_at, restart_no "
                "FROM pause_budgets WHERE pid = :p"
            ),
            {"p": pid},
        ).first()


def _warnings(caplog) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.name == "app.projector" and r.levelno == logging.WARNING
    ]


def _assert_reissued(state, position, at: datetime = AT) -> None:
    assert (state.stage_no, state.module_no, state.day_no) == position
    assert _u(state.day_started_at) == _u(day_clock.next_midnight(at, MSK_NAME))
    assert state.missed_streak == 0
    assert state.projector_version == 8


# V1: lives_returned 1 → lives 2, флаги сняты, active, день (2, 3, 1) с D.
def test_v1_revive_applied(db_engine):
    pid = _blocked(db_engine, 4701)
    marks = _count(db_engine, "day_marks", pid)
    writeoffs = _count(db_engine, "life_writeoffs", pid)
    _revive(db_engine, pid)
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    state = _state(db_engine, pid)
    assert state.lives == 2
    assert list(state.status_flags) == []
    assert state.lifecycle_phase == "active"
    _assert_reissued(state, (2, 3, 1))
    assert _count(db_engine, "day_marks", pid) == marks
    assert _count(db_engine, "life_writeoffs", pid) == writeoffs


# V2: lives_returned 0 → lives 1 (списания до 0019).
def test_v2_zero_returned(db_engine):
    pid = _blocked(db_engine, 4702)
    _revive(db_engine, pid, _payload(lives_returned=0))
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    assert _state(db_engine, pid).lives == 1


# V3: lives_returned 5 → lives 3.
def test_v3_capped(db_engine):
    pid = _blocked(db_engine, 4703)
    _revive(db_engine, pid, _payload(lives_returned=5))
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    assert _state(db_engine, pid).lives == 3


# V4: {pause_user, block_lives} → {pause_user}, sleeping (Р2), день перевыдан.
def test_v4_keeps_pause(db_engine):
    pid = _blocked(db_engine, 4704, flags="{pause_user,block_lives}")
    _revive(db_engine, pid)
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    state = _state(db_engine, pid)
    assert list(state.status_flags) == ["pause_user"]
    assert state.lifecycle_phase == "sleeping"
    _assert_reissued(state, (2, 3, 1))


# V5: pause_budgets не меняется; если строки не было — не появляется.
def test_v5_pause_budget_untouched(db_engine):
    pid = _blocked(db_engine, 4705)
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO pause_budgets (pid, days_budget_remaining_annual, cycle_start_at, "
                "restart_no) VALUES (:p, 5, :c, 0) ON CONFLICT (pid) DO UPDATE SET "
                "days_budget_remaining_annual = 5, cycle_start_at = :c, restart_no = 0"
            ),
            {"p": pid, "c": OLD_STARTED},
        )
    before = _budget(db_engine, pid)
    other = _blocked(db_engine, 4706)
    other_before = _budget(db_engine, other)
    _revive(db_engine, pid)
    _revive(db_engine, other)
    assert run_once(db_engine) == ProjectorResult(processed=2, skipped=0)
    assert _budget(db_engine, pid) == before
    assert _budget(db_engine, other) == other_before


# V6: target другого Этапа или впереди текущей позиции → пропуск, состояние прежнее.
def test_v6_bad_target_skipped(db_engine, caplog):
    pid = _blocked(db_engine, 4707)
    before = _state(db_engine, pid)
    caplog.set_level(logging.WARNING, logger="app.projector")
    for target in [(2, 3, 6), (2, 4, 1), (3, 1, 1), (1, 1, 1)]:
        _revive(db_engine, pid, _payload(target=target))
        assert run_once(db_engine) == ProjectorResult(processed=0, skipped=1)
        assert _state(db_engine, pid) == before
    warnings = _warnings(caplog)
    assert any("revive: target ahead" in m for m in warnings)
    assert any("revive: other stage" in m for m in warnings)


# V7: target = текущая позиция → применено, day_started_at = D.
def test_v7_target_current(db_engine):
    pid = _blocked(db_engine, 4708)
    _revive(db_engine, pid, _payload(target=(2, 3, 5)))
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    _assert_reissued(_state(db_engine, pid), (2, 3, 5))


# V8: active, lives 2, без флагов → пропуск.
def test_v8_not_blocked_skipped(db_engine, caplog):
    pid = _blocked(db_engine, 4709)
    _set(db_engine, pid, lives=2, flags="{}", phase="active")
    before = _state(db_engine, pid)
    caplog.set_level(logging.WARNING, logger="app.projector")
    _revive(db_engine, pid)
    assert run_once(db_engine) == ProjectorResult(processed=0, skipped=1)
    assert _state(db_engine, pid) == before
    assert any("revive: not blocked or no position" in m for m in _warnings(caplog))


# V8: {block_lives} при всей позиции NULL → пропуск.
def test_v8_no_position_skipped(db_engine, caplog):
    pid = _onboarded(db_engine, 4710)
    _set(db_engine, pid, lives=0, flags="{block_lives}", phase="sleeping")
    before = _state(db_engine, pid)
    assert before.stage_no is None and before.day_started_at is None
    caplog.set_level(logging.WARNING, logger="app.projector")
    _revive(db_engine, pid)
    assert run_once(db_engine) == ProjectorResult(processed=0, skipped=1)
    assert _state(db_engine, pid) == before
    assert any("revive: not blocked or no position" in m for m in _warnings(caplog))


# V8: нет строки состояния → пропуск.
def test_v8_no_state_skipped(db_engine, caplog):
    pid = _onboarded(db_engine, 4711)
    with db_engine.begin() as conn:
        conn.execute(text("DELETE FROM participant_state WHERE pid = :p"), {"p": pid})
    caplog.set_level(logging.WARNING, logger="app.projector")
    _revive(db_engine, pid)
    assert run_once(db_engine) == ProjectorResult(processed=0, skipped=1)
    assert _state(db_engine, pid) is None
    assert any("(no state)" in m for m in _warnings(caplog))


# V10: второй revive после применённого первого → пропуск, lives не меняются.
def test_v10_second_revive_skipped(db_engine):
    pid = _blocked(db_engine, 4712)
    _revive(db_engine, pid)
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    before = _state(db_engine, pid)
    _revive(db_engine, pid, _payload(lives_returned=2), at=datetime(2026, 11, 21, 9, 0, tzinfo=MSK))
    assert run_once(db_engine) == ProjectorResult(processed=0, skipped=1)
    assert _state(db_engine, pid) == before
    assert before.lives == 2


def _outbox(engine, pid, event_type: str) -> list:
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT payload FROM outbox WHERE aggregate_id::text = :a "
                "AND event_type = :t ORDER BY id"
            ),
            {"a": str(pid), "t": event_type},
        ).all()


def _text_id(payload) -> str:
    data = payload if isinstance(payload, dict) else json.loads(payload)
    return data["text_id"]


# V12: НП3 после revive в 10:00 по поясу → «завтра»; повторный tick → 0.
def test_v12_tasks_open_after_revive(db_engine):
    at = datetime(2026, 11, 20, 10, 0, tzinfo=MSK)
    pid = _blocked(db_engine, 4713)
    _revive(db_engine, pid, at=at)
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    now = at + timedelta(minutes=5)
    assert notify_ops.tick_tasks_open(db_engine, _u(now)).sent == 1
    rows = _outbox(db_engine, pid, notify_ops.EVENT_TYPE)
    assert len(rows) == 1
    assert _text_id(rows[0].payload) == notify_ops.TEXT_TOMORROW
    assert notify_ops.tick_tasks_open(db_engine, _u(now + timedelta(minutes=1))).sent == 0
    assert len(_outbox(db_engine, pid, notify_ops.EVENT_TYPE)) == 1
