"""Проектор v6 (api-sleep-1b): restart_paid, reissue_day, pause_budgets. С БД — только CI.

Тестовое состояние готовит прямым UPDATE владелец БД — только в тесте; позиция
(stage_no, module_no, day_no, day_started_at) задана целиком или вся NULL, lives 0..3.
Событие restart_paid пишет тест напрямую (писателя ещё нет, T6b).
"""
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import day_clock, notify_ops, projector
from app.projector import EVENT_KIND_RESTART_PAID, ProjectorResult, run_once
from app.routers.day import enter_day_by_test_flag
from app.routers.onboarding import register_with_consents

MSK_NAME = "Europe/Moscow"
MSK = ZoneInfo(MSK_NAME)
AT = datetime(2026, 11, 20, 9, 0, tzinfo=MSK)
OLD_STARTED = datetime(2026, 11, 1, 0, 0, tzinfo=MSK)
MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations" / "versions"


def _u(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc)


# ---------------------------------- без БД ----------------------------------


# R8: SQL UPSERT pause_budgets совпадает с docstring 0018.
def test_r8_upsert_matches_0018():
    (path,) = list(MIGRATIONS.glob("*0018_pauses*.py"))
    source = path.read_text(encoding="utf-8")
    found = re.search(
        r"INSERT INTO pause_budgets \(pid, days_budget_remaining_annual.*?"
        r"restart_no = EXCLUDED\.restart_no",
        source,
        re.S,
    )
    assert found is not None

    def norm(sql: str) -> str:
        return " ".join(sql.split())

    assert norm(projector._UPSERT_PAUSE_BUDGET.text) == norm(found.group(0))


# R9: next_midnight.
def test_r9_next_midnight():
    vvo = "Asia/Vladivostok"
    at = datetime(2026, 11, 20, 13, 30, tzinfo=timezone.utc)
    assert _u(day_clock.next_midnight(at, vvo)) == datetime(2026, 11, 20, 14, 0, tzinfo=timezone.utc)
    midnight = datetime(2026, 11, 20, 14, 0, tzinfo=timezone.utc)  # 00:00 21.11 по поясу
    assert _u(day_clock.next_midnight(midnight, vvo)) == datetime(
        2026, 11, 21, 14, 0, tzinfo=timezone.utc
    )
    santiago = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
    assert _u(day_clock.next_midnight(santiago, "America/Santiago")) == datetime(
        2026, 9, 6, 4, 0, tzinfo=timezone.utc
    )
    with pytest.raises(ValueError):
        day_clock.next_midnight(datetime(2026, 11, 20, 9, 0), vvo)


# R10: kind совпадает в notify_ops и projector.
def test_r10_kind_shared():
    assert notify_ops.EVENT_KIND_RESTART_PAID == projector.EVENT_KIND_RESTART_PAID
    assert "restart_paid" in notify_ops.REISSUE_KINDS


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


def _restart(engine, pid, at: datetime = AT, payload_json: str | None = None) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO participant_events (pid, kind, payload, actor, actor_role, at) "
                "VALUES (:p, :k, CAST(:pl AS jsonb), 'system', 'system', :at)"
            ),
            {
                "p": pid,
                "k": EVENT_KIND_RESTART_PAID,
                "pl": payload_json if payload_json is not None else json.dumps({}),
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


def _warnings(caplog) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.name == "app.projector" and r.levelno == logging.WARNING
    ]


def _assert_restarted(state, budget, restart_no: int) -> None:
    d = day_clock.next_midnight(AT, MSK_NAME)
    assert state.lives == 3
    assert (state.stage_no, state.module_no, state.day_no) == (2, 1, 1)
    assert _u(state.day_started_at) == _u(d)
    assert state.missed_streak == 0
    assert state.projector_version == 9
    assert budget is not None
    assert budget.days_budget_remaining_annual == 14
    assert _u(budget.cycle_start_at) == _u(d)
    assert budget.restart_no == restart_no


# R1: строки pause_budgets нет.
def test_r1_restart_no_budget(db_engine):
    pid = _blocked(db_engine, 4601)
    _restart(db_engine, pid)
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    state = _state(db_engine, pid)
    assert list(state.status_flags) == []
    assert state.lifecycle_phase == "active"
    _assert_restarted(state, _budget(db_engine, pid), 1)


# R2: строка pause_budgets (5, старая дата, 0) → (14, D, 1).
def test_r2_restart_existing_budget(db_engine):
    pid = _blocked(db_engine, 4602)
    _set_budget(db_engine, pid, 5, OLD_STARTED, 0)
    _restart(db_engine, pid)
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    _assert_restarted(_state(db_engine, pid), _budget(db_engine, pid), 1)


# R3: {pause_user, block_lives} → {pause_user}, sleeping, день перевыдан.
def test_r3_restart_keeps_pause(db_engine):
    pid = _blocked(db_engine, 4603, flags="{pause_user,block_lives}")
    _restart(db_engine, pid)
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    state = _state(db_engine, pid)
    assert list(state.status_flags) == ["pause_user"]
    assert state.lifecycle_phase == "sleeping"
    _assert_restarted(state, _budget(db_engine, pid), 1)


# R4: active, lives 2, флагов нет → пропуск.
def test_r4_not_blocked_skipped(db_engine, caplog):
    pid = _blocked(db_engine, 4604)
    _set(db_engine, pid, lives=2, flags="{}", phase="active")
    before = _state(db_engine, pid)
    budget_before = _budget(db_engine, pid)
    caplog.set_level(logging.WARNING, logger="app.projector")
    _restart(db_engine, pid)
    assert run_once(db_engine) == ProjectorResult(processed=0, skipped=1)
    assert _state(db_engine, pid) == before
    assert _budget(db_engine, pid) == budget_before
    assert any("restart: not blocked or no position" in m for m in _warnings(caplog))


# R5: вся позиция NULL → пропуск «no position».
def test_r5_no_position_skipped(db_engine, caplog):
    pid = _onboarded(db_engine, 4605)
    _set(db_engine, pid, lives=0, flags="{block_lives}", phase="sleeping")
    before = _state(db_engine, pid)
    assert before.stage_no is None and before.day_started_at is None
    caplog.set_level(logging.WARNING, logger="app.projector")
    _restart(db_engine, pid)
    assert run_once(db_engine) == ProjectorResult(processed=0, skipped=1)
    assert _state(db_engine, pid) == before
    assert _budget(db_engine, pid) is None
    assert any("restart: not blocked or no position" in m for m in _warnings(caplog))


# R6: нет строки состояния → пропуск; payload — список или не-JSON → «bad payload».
def test_r6_no_state_skipped(db_engine, caplog):
    pid = _onboarded(db_engine, 4606)
    with db_engine.begin() as conn:
        conn.execute(text("DELETE FROM participant_state WHERE pid = :p"), {"p": pid})
    caplog.set_level(logging.WARNING, logger="app.projector")
    _restart(db_engine, pid)
    assert run_once(db_engine) == ProjectorResult(processed=0, skipped=1)
    assert any("(no state)" in m for m in _warnings(caplog))
    assert _budget(db_engine, pid) is None


@pytest.mark.parametrize("payload_json", ["[1, 2]", json.dumps("not json")])
def test_r6_bad_payload(db_engine, caplog, payload_json):
    pid = _blocked(db_engine, 4607)
    before = _state(db_engine, pid)
    caplog.set_level(logging.WARNING, logger="app.projector")
    _restart(db_engine, pid, payload_json=payload_json)
    assert run_once(db_engine) == ProjectorResult(processed=0, skipped=1)
    assert _state(db_engine, pid) == before
    assert any("bad payload" in m for m in _warnings(caplog))


# R7: второй restart_paid после применённого первого → пропуск, restart_no 1.
def test_r7_second_restart_skipped(db_engine):
    pid = _blocked(db_engine, 4608)
    _restart(db_engine, pid)
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    _restart(db_engine, pid, at=datetime(2026, 11, 21, 9, 0, tzinfo=MSK))
    assert run_once(db_engine) == ProjectorResult(processed=0, skipped=1)
    _assert_restarted(_state(db_engine, pid), _budget(db_engine, pid), 1)
