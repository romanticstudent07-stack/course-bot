"""«Часы» пауз (api-pause-1b, §7): pause_ops.tick. С БД — только CI.

Фикстуры — по образцу tests/test_projector_pause.py. Строку participant_pauses и события
пишет тест напрямую владельцем БД (писателей T3 / T4 ещё нет); состояние готовит прямым
UPDATE — только в тесте. tg_user_id — вымышленные.
"""
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import life_ops, pause_ops, projector
from app.day_keys import key_pause_end, key_pause_start
from app.pause_ops import TickResult
from app.projector import run_once
from app.routers.day import enter_day_by_test_flag
from app.routers.onboarding import register_with_consents

MSK_NAME = "Europe/Moscow"
MSK = ZoneInfo(MSK_NAME)
CYCLE = datetime(2026, 11, 1, 0, 0, tzinfo=MSK)
START = datetime(2026, 11, 21, 0, 0, tzinfo=MSK)
END = datetime(2026, 11, 24, 0, 0, tzinfo=MSK)  # 3 дня
YESTERDAY = datetime(2026, 11, 20, 0, 0, tzinfo=MSK)
APPROVE_AT = datetime(2026, 11, 20, 10, 0, tzinfo=MSK)
TICK_START = START + timedelta(minutes=5)  # после CLOSE_GRACE вчерашнего дня
TICK_END = END + timedelta(minutes=5)
POSITION = (2, 3, 5)


def _u(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc)


def _active(
    engine,
    tg_user_id: int,
    *,
    started: datetime = START,
    flags: str = "{}",
    phase: str = "active",
    lives: int = 3,
):
    """Участник с позицией (2, 3, 5, started), tz Europe/Moscow, бюджет (14, CYCLE, 0)."""
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
                "day_started_at = :s, missed_streak = 0, tz = :tz, lives = :l, "
                "status_flags = CAST(:f AS text[]), lifecycle_phase = :ph WHERE pid = :p"
            ),
            {"p": pid, "s": started, "tz": MSK_NAME, "l": lives, "f": flags, "ph": phase},
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
    kind: str = "user",
    start: datetime = START,
    end: datetime = END,
    status: str = "approved",
    stage_no: int | None = None,
    restart_no: int | None = None,
    op: str = "op-1",
) -> int:
    with engine.begin() as conn:
        return conn.execute(
            text(
                "INSERT INTO participant_pauses (pid, kind, status, start_at, planned_end_at, "
                "stage_no, restart_no, client_op_id) "
                "VALUES (:p, :k, :st, :s, :e, :sn, :rn, :op) RETURNING id"
            ),
            {
                "p": pid,
                "k": kind,
                "st": status,
                "s": start,
                "e": end,
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


def _pause_events(engine, pid) -> list[tuple[str, dict]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT kind, payload FROM participant_events WHERE pid = :p "
                "AND actor = 'pause_ops' ORDER BY id"
            ),
            {"p": pid},
        ).all()
    return [(k, p if isinstance(p, dict) else json.loads(p)) for k, p in rows]


def _key_count(engine, key: str) -> int:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT count(*) FROM idempotency_keys WHERE key = :k"), {"k": key}
        ).scalar_one()


def _pause_status(engine, pause_id: int) -> str:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT status FROM participant_pauses WHERE id = :i"), {"i": pause_id}
        ).scalar_one()


def _state(engine, pid):
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT stage_no, module_no, day_no, day_started_at, status_flags, "
                "lifecycle_phase FROM participant_state WHERE pid = :p"
            ),
            {"p": pid},
        ).one()


def _budget_left(engine, pid) -> int:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT days_budget_remaining_annual FROM pause_budgets WHERE pid = :p"),
            {"p": pid},
        ).scalar_one()


# A: вчерашний день не закрыт — пропуск; после day_closed (life_ops + проектор) — pause_started.
def test_a_yesterday_open_skip_then_started(db_engine):
    pid = _active(db_engine, 4901, started=YESTERDAY)
    pause_id = _pause(db_engine, pid)
    assert pause_ops.tick(db_engine, TICK_START) == TickResult(0, 0, 0, 1)
    assert _pause_events(db_engine, pid) == []
    assert _key_count(db_engine, key_pause_start(pid, pause_id)) == 0

    assert life_ops.tick(db_engine, TICK_START).closed == 1
    run_once(db_engine)
    assert _u(_state(db_engine, pid).day_started_at) == _u(START)
    assert pause_ops.tick(db_engine, TICK_START) == TickResult(1, 0, 0, 0)
    assert _pause_events(db_engine, pid) == [("pause_started", {"pause_id": pause_id})]
    assert _key_count(db_engine, key_pause_start(pid, pause_id)) == 1


# A с отказом start_refusal → pause_start_failed с его reason; проектор гасит заявку.
@pytest.mark.parametrize("reason", ["block_lives", "no_budget"])
def test_a_refused_start_failed(db_engine, reason):
    if reason == "block_lives":
        pid = _active(db_engine, 4902, flags="{block_lives}", phase="sleeping", lives=0)
    else:
        pid = _active(db_engine, 4902)
        _set_budget(db_engine, pid, 2, CYCLE, 0)
    pause_id = _pause(db_engine, pid)
    assert pause_ops.tick(db_engine, TICK_START) == TickResult(0, 1, 0, 0)
    assert _pause_events(db_engine, pid) == [
        ("pause_start_failed", {"pause_id": pause_id, "reason": reason})
    ]
    run_once(db_engine)
    assert _pause_status(db_engine, pause_id) == "cancelled"
    assert "pause_user" not in list(_state(db_engine, pid).status_flags)


# B: requested при now ≥ start_at → pause_start_failed not_approved (Р14).
def test_b_requested_not_approved(db_engine):
    pid = _active(db_engine, 4903)
    pause_id = _pause(db_engine, pid, status="requested")
    assert pause_ops.tick(db_engine, TICK_START) == TickResult(0, 1, 0, 0)
    assert _pause_events(db_engine, pid) == [
        ("pause_start_failed", {"pause_id": pause_id, "reason": "not_approved"})
    ]
    run_once(db_engine)
    assert _pause_status(db_engine, pause_id) == "cancelled"


# C: active при now ≥ planned_end_at → pause_ended expired; проектор: D = last_midnight (Р5).
def test_c_active_expired(db_engine):
    pid = _active(db_engine, 4904, flags="{pause_user}", phase="sleeping")
    pause_id = _pause(db_engine, pid, status="active", stage_no=2, restart_no=0)
    assert pause_ops.tick(db_engine, END - timedelta(minutes=1)) == TickResult(0, 0, 0, 0)
    assert pause_ops.tick(db_engine, TICK_END) == TickResult(0, 0, 1, 0)
    assert _pause_events(db_engine, pid) == [
        ("pause_ended", {"pause_id": pause_id, "reason": "expired"})
    ]
    assert _key_count(db_engine, key_pause_end(pid, pause_id)) == 1
    run_once(db_engine)
    assert _pause_status(db_engine, pause_id) == "ended"
    assert _u(_state(db_engine, pid).day_started_at) == _u(END)


# Проектор не догнал pid (pause_approved ещё не применён) — пропуск до следующего тика.
def test_pending_event_skip(db_engine):
    pid = _active(db_engine, 4905)
    pause_id = _pause(db_engine, pid, status="requested")
    _event(db_engine, pid, "pause_approved", {"pause_id": pause_id}, APPROVE_AT)
    assert pause_ops.tick(db_engine, TICK_START) == TickResult(0, 0, 0, 1)
    assert _pause_events(db_engine, pid) == []
    run_once(db_engine)
    assert _pause_status(db_engine, pause_id) == "approved"
    assert pause_ops.tick(db_engine, TICK_START) == TickResult(1, 0, 0, 0)


# Два тика подряд — одно событие; ключ второй раз не пишется.
def test_two_ticks_one_event(db_engine):
    pid = _active(db_engine, 4906)
    pause_id = _pause(db_engine, pid, status="requested")
    assert pause_ops.tick(db_engine, TICK_START).failed == 1
    assert pause_ops.tick(db_engine, TICK_START).failed == 0
    assert len(_pause_events(db_engine, pid)) == 1
    key = key_pause_start(pid, pause_id)
    assert _key_count(db_engine, key) == 1
    again = pause_ops.PausePlan(
        pause_ops.OUTCOME_FAILED,
        key,
        "pause_start",
        "3650 days",
        "pause_start_failed",
        {"pause_id": pause_id, "reason": "not_approved"},
    )
    with db_engine.connect() as conn:
        assert pause_ops._write(conn, pid, again, TICK_START) is False
        conn.rollback()
    assert len(_pause_events(db_engine, pid)) == 1


# MAX_PER_TICK: самые старые start_at — в этом тике, остальные — в следующем.
def test_max_per_tick(db_engine, monkeypatch):
    monkeypatch.setattr(pause_ops, "MAX_PER_TICK", 2)
    pids = [_active(db_engine, 4910 + i) for i in range(3)]
    starts = [START - timedelta(days=2), START - timedelta(days=1), START]
    ids = [
        _pause(db_engine, pid, status="requested", start=s, end=END)
        for pid, s in zip(pids, starts)
    ]
    assert pause_ops.tick(db_engine, TICK_START) == TickResult(0, 2, 0, 0)
    assert [len(_pause_events(db_engine, pid)) for pid in pids] == [1, 1, 0]
    run_once(db_engine)
    assert pause_ops.tick(db_engine, TICK_START) == TickResult(0, 1, 0, 0)
    assert _pause_events(db_engine, pids[2]) == [
        ("pause_start_failed", {"pause_id": ids[2], "reason": "not_approved"})
    ]


# Полный путь: tick → проектор → active → tick → ended → проектор.
def test_full_path(db_engine):
    assert pause_ops.EVENT_KIND_PAUSE_STARTED == projector.EVENT_KIND_PAUSE_STARTED
    assert pause_ops.EVENT_KIND_PAUSE_START_FAILED == projector.EVENT_KIND_PAUSE_START_FAILED
    assert pause_ops.EVENT_KIND_PAUSE_ENDED == projector.EVENT_KIND_PAUSE_ENDED
    assert pause_ops.PAUSE_END_EXPIRED == projector.PAUSE_END_EXPIRED
    pid = _active(db_engine, 4920)
    pause_id = _pause(db_engine, pid)
    assert pause_ops.tick(db_engine, TICK_START) == TickResult(1, 0, 0, 0)
    run_once(db_engine)
    assert _pause_status(db_engine, pause_id) == "active"
    state = _state(db_engine, pid)
    assert list(state.status_flags) == ["pause_user"]
    assert _budget_left(db_engine, pid) == 11
    assert pause_ops.tick(db_engine, TICK_START + timedelta(days=1)) == TickResult(0, 0, 0, 0)
    assert pause_ops.tick(db_engine, TICK_END) == TickResult(0, 0, 1, 0)
    run_once(db_engine)
    assert _pause_status(db_engine, pause_id) == "ended"
    state = _state(db_engine, pid)
    assert list(state.status_flags) == []
    assert state.lifecycle_phase == "active"
    assert (state.stage_no, state.module_no, state.day_no) == POSITION
    assert _u(state.day_started_at) == _u(END)
    assert [k for k, _p in _pause_events(db_engine, pid)] == ["pause_started", "pause_ended"]


# Кандидаты — только kind user: author / shadow часы не берут.
def test_author_shadow_not_candidates(db_engine):
    pid = _active(db_engine, 4930)
    _pause(db_engine, pid, kind="author", status="approved", op="op-a")
    _pause(db_engine, pid, kind="shadow", status="active", op="op-s")
    assert pause_ops.tick(db_engine, TICK_END) == TickResult(0, 0, 0, 0)
    assert _pause_events(db_engine, pid) == []
