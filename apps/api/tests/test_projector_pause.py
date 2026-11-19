"""Проектор v8–v9 (api-pause-1a раздел 8; api-pause-3b): паузы участника. С БД — только CI.

Фикстуры — по образцу tests/test_projector_restart.py. Строку participant_pauses и события
пишет тест напрямую владельцем БД (писателей ещё нет: T3, T4, часы T2b); состояние
готовит прямым UPDATE — только в тесте.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import day_clock, projector
from app.projector import ProjectorResult, run_once
from app.routers.day import enter_day_by_test_flag
from app.routers.onboarding import register_with_consents

MSK_NAME = "Europe/Moscow"
MSK = ZoneInfo(MSK_NAME)
OLD_STARTED = datetime(2026, 11, 1, 0, 0, tzinfo=MSK)
CYCLE = datetime(2026, 11, 1, 0, 0, tzinfo=MSK)
START = datetime(2026, 11, 21, 0, 0, tzinfo=MSK)
END = datetime(2026, 11, 24, 0, 0, tzinfo=MSK)  # 3 дня
APPROVE_AT = datetime(2026, 11, 20, 10, 0, tzinfo=MSK)
STARTED_AT = datetime(2026, 11, 21, 0, 1, tzinfo=MSK)
POSITION = (2, 3, 5)


def _u(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc)


def _active(engine, tg_user_id: int, *, flags: str = "{}", phase: str = "active", lives: int = 3):
    """Участник с позицией (2, 3, 5, OLD_STARTED), tz Europe/Moscow, бюджет (14, CYCLE, 0)."""
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
                "day_started_at = :s, missed_streak = 1, tz = :tz, lives = :l, "
                "status_flags = CAST(:f AS text[]), lifecycle_phase = :ph WHERE pid = :p"
            ),
            {"p": pid, "s": OLD_STARTED, "tz": MSK_NAME, "l": lives, "f": flags, "ph": phase},
        )
    _set_budget(engine, pid, 14, CYCLE, 0)
    return pid


def _set_budget(engine, pid, d: int, c: datetime, r: int) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO pause_budgets (pid, days_budget_remaining_annual, cycle_start_at, "
                "restart_no) VALUES (:p, :d, :c, :r) ON CONFLICT (pid) DO UPDATE SET "
                "days_budget_remaining_annual = :d, cycle_start_at = :c, restart_no = :r"
            ),
            {"p": pid, "d": d, "c": c, "r": r},
        )


def _pause(
    engine,
    pid,
    *,
    start: datetime = START,
    end: datetime = END,
    status: str = "requested",
    stage_no: int | None = None,
    restart_no: int | None = None,
    ended_at: datetime | None = None,
    op: str = "op-1",
) -> int:
    with engine.begin() as conn:
        return conn.execute(
            text(
                "INSERT INTO participant_pauses (pid, kind, status, start_at, planned_end_at, "
                "ended_at, stage_no, restart_no, client_op_id) "
                "VALUES (:p, 'user', :st, :s, :e, :ea, :sn, :rn, :op) RETURNING id"
            ),
            {
                "p": pid,
                "st": status,
                "s": start,
                "e": end,
                "ea": ended_at,
                "sn": stage_no,
                "rn": restart_no,
                "op": op,
            },
        ).scalar_one()


def _event(engine, pid, kind: str, payload: dict, at: datetime) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO participant_events (pid, kind, payload, actor, actor_role, at) "
                "VALUES (:p, :k, CAST(:pl AS jsonb), 'system', 'system', :at)"
            ),
            {"p": pid, "k": kind, "pl": json.dumps(payload), "at": at},
        )


def _state(engine, pid):
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT stage_no, module_no, day_no, day_started_at, missed_streak, lives, "
                "lifecycle_phase, status_flags, projector_version, tz "
                "FROM participant_state WHERE pid = :p"
            ),
            {"p": pid},
        ).one()


def _budget(engine, pid):
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT days_budget_remaining_annual, cycle_start_at, restart_no "
                "FROM pause_budgets WHERE pid = :p"
            ),
            {"p": pid},
        ).first()


def _pause_row(engine, pause_id: int):
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT status, stage_no, restart_no, ended_at FROM participant_pauses "
                "WHERE id = :i"
            ),
            {"i": pause_id},
        ).one()


def _warnings(caplog) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.name == "app.projector" and r.levelno == logging.WARNING
    ]


def _start(engine, pid, pause_id: int) -> None:
    _event(engine, pid, "pause_approved", {"pause_id": pause_id}, APPROVE_AT)
    _event(engine, pid, "pause_started", {"pause_id": pause_id}, STARTED_AT)


# P1: requested → approved → active → ended expired.
def test_p1_path_expired(db_engine):
    pid = _active(db_engine, 4801)
    pause_id = _pause(db_engine, pid)
    _event(db_engine, pid, "pause_approved", {"pause_id": pause_id}, APPROVE_AT)
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    assert _pause_row(db_engine, pause_id).status == "approved"

    _event(db_engine, pid, "pause_started", {"pause_id": pause_id}, STARTED_AT)
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    row = _pause_row(db_engine, pause_id)
    assert (row.status, row.stage_no, row.restart_no) == ("active", 2, 0)
    state = _state(db_engine, pid)
    assert list(state.status_flags) == ["pause_user"]
    assert state.lifecycle_phase == "sleeping"
    assert state.projector_version == 9
    assert _budget(db_engine, pid).days_budget_remaining_annual == 14 - 3

    ended_at = END + timedelta(minutes=5)
    _event(db_engine, pid, "pause_ended", {"pause_id": pause_id, "reason": "expired"}, ended_at)
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    row = _pause_row(db_engine, pause_id)
    assert row.status == "ended"
    assert _u(row.ended_at) == _u(ended_at)
    state = _state(db_engine, pid)
    assert list(state.status_flags) == []
    assert state.lifecycle_phase == "active"
    assert (state.stage_no, state.module_no, state.day_no) == POSITION
    assert _u(state.day_started_at) == _u(END)
    assert state.missed_streak == 0
    assert _budget(db_engine, pid).days_budget_remaining_annual == 11


# P2: by_participant — возврат по Р6, день нажатия не возвращается.
def test_p2_by_participant_refund(db_engine):
    pid = _active(db_engine, 4802)
    pause_id = _pause(db_engine, pid)
    _start(db_engine, pid, pause_id)
    pressed = datetime(2026, 11, 22, 15, 0, tzinfo=MSK)
    _event(
        db_engine, pid, "pause_ended", {"pause_id": pause_id, "reason": "by_participant"}, pressed
    )
    assert run_once(db_engine) == ProjectorResult(processed=3, skipped=0)
    d = day_clock.next_midnight(pressed, MSK_NAME)
    state = _state(db_engine, pid)
    assert _u(state.day_started_at) == _u(d)
    assert (state.stage_no, state.module_no, state.day_no) == POSITION
    assert list(state.status_flags) == []
    # 14 − 3 + (24.11 − 23.11 = 1); 22.11 потрачен.
    assert _budget(db_engine, pid).days_budget_remaining_annual == 12


# P3: pause_approved при at ≥ start_at → approved. Р14 отменён (api-pause-3b Д2).
def test_p3_late_approve_approved(db_engine):
    pid = _active(db_engine, 4803)
    pause_id = _pause(db_engine, pid)
    _event(db_engine, pid, "pause_approved", {"pause_id": pause_id}, START)
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    assert _pause_row(db_engine, pause_id).status == "approved"
    assert list(_state(db_engine, pid).status_flags) == []


# P4: pause_started с нарушенным правилом → cancelled, флага нет, бюджет цел (Р15).
@pytest.mark.parametrize("reason", ["block_lives", "no_budget", "stage_taken", "gap_24h"])
def test_p4_start_refused(db_engine, caplog, reason):
    if reason == "block_lives":
        pid = _active(db_engine, 4804, flags="{block_lives}", phase="sleeping", lives=0)
    else:
        pid = _active(db_engine, 4804)
    if reason == "no_budget":
        _set_budget(db_engine, pid, 2, CYCLE, 0)
    if reason == "stage_taken":
        _pause(
            db_engine, pid, start=datetime(2026, 11, 2, 0, 0, tzinfo=MSK),
            end=datetime(2026, 11, 5, 0, 0, tzinfo=MSK), status="ended", stage_no=2,
            restart_no=0, ended_at=datetime(2026, 11, 5, 0, 0, tzinfo=MSK), op="op-old",
        )
    if reason == "gap_24h":
        _pause(
            db_engine, pid, start=datetime(2026, 11, 18, 0, 0, tzinfo=MSK),
            end=datetime(2026, 11, 20, 0, 0, tzinfo=MSK), status="ended", stage_no=1,
            restart_no=0, ended_at=datetime(2026, 11, 20, 12, 0, tzinfo=MSK), op="op-old",
        )
    budget_before = _budget(db_engine, pid)
    flags_before = list(_state(db_engine, pid).status_flags)
    pause_id = _pause(db_engine, pid)
    caplog.set_level(logging.WARNING, logger="app.projector")
    _start(db_engine, pid, pause_id)
    assert run_once(db_engine) == ProjectorResult(processed=2, skipped=0)
    assert _pause_row(db_engine, pause_id).status == "cancelled"
    state = _state(db_engine, pid)
    assert "pause_user" not in list(state.status_flags)
    assert list(state.status_flags) == flags_before
    assert _budget(db_engine, pid) == budget_before
    assert any(f"pause_started отклонён: {reason}" in m for m in _warnings(caplog))


# P5: повтор pause_started — без двойного списания.
def test_p5_repeat_started_no_double_charge(db_engine):
    pid = _active(db_engine, 4805)
    pause_id = _pause(db_engine, pid)
    _start(db_engine, pid, pause_id)
    _event(db_engine, pid, "pause_started", {"pause_id": pause_id}, STARTED_AT)
    assert run_once(db_engine) == ProjectorResult(processed=2, skipped=1)
    assert _budget(db_engine, pid).days_budget_remaining_annual == 11
    assert list(_state(db_engine, pid).status_flags) == ["pause_user"]


# P6: годовщина во время паузы → новый цикл 14, возврата нет (Р8, Р9).
def test_p6_anniversary_during_pause_no_refund(db_engine):
    pid = _active(db_engine, 4806)
    _set_budget(db_engine, pid, 5, datetime(2025, 11, 22, 0, 0, tzinfo=MSK), 0)
    pause_id = _pause(db_engine, pid)
    _start(db_engine, pid, pause_id)
    assert run_once(db_engine) == ProjectorResult(processed=2, skipped=0)
    assert _budget(db_engine, pid).days_budget_remaining_annual == 2
    pressed = datetime(2026, 11, 22, 10, 0, tzinfo=MSK)
    _event(
        db_engine, pid, "pause_ended", {"pause_id": pause_id, "reason": "by_participant"}, pressed
    )
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    budget = _budget(db_engine, pid)
    assert budget.days_budget_remaining_annual == 14
    assert _u(budget.cycle_start_at) == _u(datetime(2026, 11, 22, 0, 0, tzinfo=MSK))


# P7: day_entered создаёт pause_budgets один раз; второй day_entered строку не меняет.
def test_p7_day_entered_creates_budget_once(db_engine):
    with Session(db_engine) as session:
        pid = register_with_consents(session, 4807, ["C0", "C1"]).participant.pid
    run_once(db_engine)
    assert _budget(db_engine, pid) is None
    with Session(db_engine) as session:
        enter_day_by_test_flag(session, 4807, True)
    run_once(db_engine)
    with db_engine.connect() as conn:
        first_at = conn.execute(
            text(
                "SELECT at FROM participant_events WHERE pid = :p AND kind = 'day_entered' "
                "ORDER BY id LIMIT 1"
            ),
            {"p": pid},
        ).scalar_one()
    tz = _state(db_engine, pid).tz or MSK_NAME
    budget = _budget(db_engine, pid)
    assert budget.days_budget_remaining_annual == 14
    assert budget.restart_no == 0
    assert _u(budget.cycle_start_at) == _u(
        day_clock.last_midnight(day_clock.active_from(first_at, tz), tz)
    )

    _set_budget(db_engine, pid, 3, CYCLE, 0)
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE participant_state SET stage_no = NULL, module_no = NULL, day_no = NULL, "
                "day_started_at = NULL WHERE pid = :p"
            ),
            {"p": pid},
        )
    _event(
        db_engine, pid, "day_entered", {"stage_no": 1, "module_no": 1, "day_no": 1},
        datetime(2026, 12, 1, 9, 0, tzinfo=MSK),
    )
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    budget = _budget(db_engine, pid)
    assert budget.days_budget_remaining_annual == 3
    assert _u(budget.cycle_start_at) == _u(CYCLE)


# P8: restart_paid → пауза того же Этапа снова разрешена (Р11).
def test_p8_restart_allows_same_stage(db_engine):
    pid = _active(db_engine, 4808, flags="{block_lives}", phase="sleeping", lives=0)
    _pause(
        db_engine, pid, start=datetime(2026, 11, 2, 0, 0, tzinfo=MSK),
        end=datetime(2026, 11, 5, 0, 0, tzinfo=MSK), status="ended", stage_no=2,
        restart_no=0, ended_at=datetime(2026, 11, 5, 0, 0, tzinfo=MSK), op="op-old",
    )
    _event(db_engine, pid, "restart_paid", {}, datetime(2026, 11, 10, 9, 0, tzinfo=MSK))
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    assert _budget(db_engine, pid).restart_no == 1
    pause_id = _pause(db_engine, pid)
    _start(db_engine, pid, pause_id)
    assert run_once(db_engine) == ProjectorResult(processed=2, skipped=0)
    row = _pause_row(db_engine, pause_id)
    assert (row.status, row.stage_no, row.restart_no) == ("active", 2, 1)
    assert _budget(db_engine, pid).days_budget_remaining_annual == 11


# P9: reissue_day без day_start — как в v7 (D = next_midnight(at, tz)).
def test_p9_reissue_day_default(db_engine):
    pid = _active(db_engine, 4809)
    at = datetime(2026, 11, 20, 9, 0, tzinfo=MSK)
    with db_engine.begin() as conn:
        d = projector.reissue_day(conn, pid, (2, 1, 1), at, MSK_NAME)
    expected = day_clock.next_midnight(at, MSK_NAME)
    assert _u(d) == _u(expected)
    state = _state(db_engine, pid)
    assert (state.stage_no, state.module_no, state.day_no) == (2, 1, 1)
    assert _u(state.day_started_at) == _u(expected)
    assert state.missed_streak == 0
