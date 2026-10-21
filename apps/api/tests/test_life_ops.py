"""«Часы» дня (life-ops-c): tick, dry-run, вызов из run_forever. С БД — только CI.

now — аргументом tick, от фактического day_started_at (реальное время запуска не влияет).
Тестовое состояние (lives, missed_streak, фаза, флаги) готовится прямым UPDATE от владельца
БД — только в тесте; «часы» и API participant_state не пишут.
"""
import json
import logging
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app import day_clock, life_ops, projector
from app.day_keys import dsa, key_day_close
from app.life_ops import TickResult, close_one, dry_run, tick
from app.projector import ProjectorResult, run_once
from app.routers.day import enter_day_by_test_flag
from app.routers.onboarding import register_with_consents


def _u(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc)


# ------------------------------ без БД ------------------------------


def test_kinds_match_projector():
    assert life_ops.EVENT_KIND_LIFE_OP == projector.EVENT_KIND_LIFE_OP
    assert life_ops.EVENT_KIND_DAY_CLOSED == projector.EVENT_KIND_DAY_CLOSED
    assert life_ops.LIFE_OP_REASON == projector.LIFE_OP_REASON
    assert life_ops.LIFE_OPS_INTERVAL_S == 30


@pytest.mark.parametrize(
    "argv", [[], ["dry-run"], ["dry-run", "not-a-uuid"], ["run", str(uuid.uuid4())], ["x"]]
)
def test_main_bad_args_code_2(argv, capsys):
    assert life_ops.main(argv) == 2
    assert "usage" in capsys.readouterr().err


def test_main_bad_args_fast_without_db_and_settings():
    # Отдельный процесс: без DATABASE_URL и BOT_TOKEN, код 2 за < 1 с, БД не импортируется.
    code = (
        "import sys, time; t = time.monotonic(); from app import life_ops; "
        "rc = life_ops.main(['dry-run']); "
        "assert 'app.db.session' not in sys.modules; "
        "assert time.monotonic() - t < 1.0; sys.exit(rc)"
    )
    from pathlib import Path

    api_dir = Path(__file__).resolve().parents[1]
    started = time.monotonic()
    done = subprocess.run(
        [sys.executable, "-c", code], cwd=api_dir, env={"PATH": "/usr/bin:/bin"},
        capture_output=True, timeout=30,
    )
    assert done.returncode == 2, done.stderr
    assert time.monotonic() - started < 10


def test_tick_naive_now_value_error():
    with pytest.raises(ValueError):
        tick(object(), datetime(2026, 10, 21, 0, 0))  # type: ignore[arg-type]


class _Stop(BaseException):
    pass


class _FakeConn:
    def execute(self, *args, **kwargs):
        return None

    def commit(self):
        return None


@contextmanager
def _fake_lock(engine):
    yield _FakeConn()


def _run_forever_with(monkeypatch, tick_impl, clock, iterations: int):
    """run_forever без БД: lock и drain подменены, sleep считает итерации и сдвигает часы."""
    drains = {"n": 0}

    def drain(engine):
        drains["n"] += 1
        return ProjectorResult(0, 0)

    def sleep(seconds):
        clock["now"] += timedelta(seconds=seconds)
        if drains["n"] >= iterations:
            raise _Stop

    monkeypatch.setattr(projector, "_advisory_lock", _fake_lock)
    monkeypatch.setattr(projector, "_drain", drain)
    monkeypatch.setattr(life_ops, "tick", tick_impl)
    monkeypatch.setattr(day_clock, "utcnow", lambda: clock["now"])
    with pytest.raises(_Stop):
        projector.run_forever(object(), poll_seconds=1.0, sleep=sleep)  # type: ignore[arg-type]
    return drains["n"]


def test_run_forever_ticks_every_30s(monkeypatch):
    clock = {"now": datetime(2026, 10, 21, 21, 0, tzinfo=timezone.utc)}
    calls: list[datetime] = []

    def fake_tick(engine, now):
        calls.append(now)
        return TickResult(0, 0)

    drains = _run_forever_with(monkeypatch, fake_tick, clock, iterations=61)
    assert drains == 61
    # Проходы раз в 1 с, tick — на 0, 30, 60 с.
    assert [int((c - calls[0]).total_seconds()) for c in calls] == [0, 30, 60]
    assert all(c.tzinfo is not None for c in calls)


def test_run_forever_tick_error_warning_loop_alive(monkeypatch, caplog):
    clock = {"now": datetime(2026, 10, 21, 21, 0, tzinfo=timezone.utc)}
    secret = str(uuid.uuid4())

    def broken_tick(engine, now):
        raise RuntimeError(secret)

    with caplog.at_level(logging.WARNING, logger="app.projector"):
        drains = _run_forever_with(monkeypatch, broken_tick, clock, iterations=65)
    assert drains == 65  # цикл проектора жив после ошибок tick
    messages = [r.getMessage() for r in caplog.records if r.name == "app.projector"]
    failed = [m for m in messages if "life_ops tick failed" in m]
    assert len(failed) == 3
    assert all("RuntimeError" in m and secret not in m for m in failed)


def test_run_once_without_tick(monkeypatch):
    def must_not_tick(engine, now):
        raise AssertionError("once — без tick")

    monkeypatch.setattr(projector, "_advisory_lock", _fake_lock)
    monkeypatch.setattr(projector, "_drain", lambda engine: ProjectorResult(0, 0))
    monkeypatch.setattr(life_ops, "tick", must_not_tick)
    assert run_once(object()) == ProjectorResult(0, 0)  # type: ignore[arg-type]


# ---------------------------------- с БД ----------------------------------


def _open_day(engine, tg_user_id: int):
    with Session(engine) as session:
        pid = register_with_consents(session, tg_user_id, ["C0", "C1"]).participant.pid
    run_once(engine)
    with Session(engine) as session:
        enter_day_by_test_flag(session, tg_user_id, True)
    run_once(engine)
    return pid, _state(engine, pid).day_started_at


def _prepare(
    engine, pid, *, lives=3, missed_streak=0, phase=None, flags="{}", pause=None
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE participant_state SET missed_streak = :m, lives = :l, "
                "status_flags = CAST(:f AS text[]), author_pause_reason = :ap, "
                "lifecycle_phase = coalesce(:ph, lifecycle_phase) WHERE pid = :p"
            ),
            {"p": pid, "m": missed_streak, "l": lives, "f": flags, "ph": phase, "ap": pause},
        )


def _state(engine, pid):
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT day_no, day_started_at, missed_streak, lives, lifecycle_phase, tz "
                "FROM participant_state WHERE pid = :p"
            ),
            {"p": pid},
        ).one()


def _events(engine, pid, kind=None) -> list:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT kind, payload, actor, actor_role FROM participant_events "
                "WHERE pid = :p AND kind IN ('life_op', 'day_closed') ORDER BY id"
            ),
            {"p": pid},
        ).all()
    return [r for r in rows if kind is None or r.kind == kind]


def _close_keys(engine, pid) -> int:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT count(*) FROM idempotency_keys WHERE key LIKE :k"),
            {"k": f"day_close:{pid}:%"},
        ).scalar_one()


def _overdue_now(engine, pid, extra=timedelta(seconds=1)) -> datetime:
    state = _state(engine, pid)
    deadline = _u(day_clock.deadline_at(state.day_started_at, state.tz))
    return deadline + day_clock.CLOSE_GRACE + extra


def _life_msgs(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == "app.life_ops"]


def test_silence_once_streak_1_lives_3(db_engine, caplog):
    pid, started = _open_day(db_engine, 9701)
    _prepare(db_engine, pid)
    now = _overdue_now(db_engine, pid)
    with caplog.at_level(logging.INFO, logger="app.life_ops"):
        assert tick(db_engine, now) == TickResult(closed=1, skipped=0)
    events = _events(db_engine, pid)
    assert [e.kind for e in events] == ["day_closed"]
    payload = events[0].payload
    assert payload == {
        "day_started_at": dsa(started),
        "outcome": "silent",
        "missed_streak": 1,
        "next_day_started_at": dsa(day_clock.last_midnight(now, "Europe/Moscow")),
    }
    assert (events[0].actor, events[0].actor_role) == ("life_ops", "system")
    assert _close_keys(db_engine, pid) == 1
    run_once(db_engine)
    state = _state(db_engine, pid)
    assert (state.missed_streak, state.lives, state.lifecycle_phase) == (1, 3, "onboarding")
    assert dsa(state.day_started_at) == payload["next_day_started_at"]
    messages = _life_msgs(caplog)
    assert any("tick closed=1 skipped=0" in m for m in messages)
    assert all(str(pid) not in m and "Moscow" not in m for m in messages)


def test_second_silence_minus_life_streak_0(db_engine):
    pid, started = _open_day(db_engine, 9702)
    _prepare(db_engine, pid)
    assert tick(db_engine, _overdue_now(db_engine, pid)) == TickResult(1, 0)
    run_once(db_engine)
    assert tick(db_engine, _overdue_now(db_engine, pid)) == TickResult(1, 0)
    kinds = [e.kind for e in _events(db_engine, pid)]
    assert kinds == ["day_closed", "life_op", "day_closed"]
    life_op = _events(db_engine, pid, "life_op")[0].payload
    assert life_op["delta"] == -1 and life_op["reason"] == "missed_days"
    run_once(db_engine)
    state = _state(db_engine, pid)
    assert (state.missed_streak, state.lives, state.lifecycle_phase) == (0, 2, "onboarding")


def test_came_marks_without_report_streak_0(db_engine):
    pid, started = _open_day(db_engine, 9703)
    _prepare(db_engine, pid, missed_streak=1)
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO day_marks (pid, day_started_at, block_id, value) "
                "VALUES (:p, :s, 'task_1', true)"
            ),
            {"p": pid, "s": started},
        )
    assert tick(db_engine, _overdue_now(db_engine, pid)) == TickResult(1, 0)
    events = _events(db_engine, pid)
    assert [e.kind for e in events] == ["day_closed"]
    assert events[0].payload["outcome"] == "came"
    run_once(db_engine)
    state = _state(db_engine, pid)
    assert (state.missed_streak, state.lives) == (0, 3)


@pytest.mark.parametrize("phase", [None, "active"])
def test_last_life_sleeping_then_skipped(db_engine, phase):
    pid, _ = _open_day(db_engine, 9704 if phase is None else 9705)
    _prepare(db_engine, pid, lives=1, missed_streak=1, phase=phase)
    now = _overdue_now(db_engine, pid)
    assert tick(db_engine, now) == TickResult(1, 0)
    run_once(db_engine)
    state = _state(db_engine, pid)
    assert (state.lives, state.lifecycle_phase, state.missed_streak) == (0, "sleeping", 0)
    later = now + timedelta(days=3)
    assert tick(db_engine, later) == TickResult(0, 0)
    assert len(_events(db_engine, pid)) == 2


@pytest.mark.parametrize(
    ("tg", "kw"),
    [
        (9706, {"phase": "sleeping"}),
        (9707, {"phase": "muted"}),
        (9708, {"phase": "erased"}),
        (9709, {"pause": "block"}),
    ],
)
def test_sleeping_muted_paused_skipped(db_engine, tg, kw):
    pid, _ = _open_day(db_engine, tg)
    _prepare(db_engine, pid, missed_streak=1, **kw)
    now = _overdue_now(db_engine, pid)
    assert tick(db_engine, now) == TickResult(0, 0)
    # Повторная проверка под замком (У3): прямой вызов на «не том» pid — ничего не пишет.
    assert close_one(db_engine, pid, now) is False
    assert _events(db_engine, pid) == []
    assert _close_keys(db_engine, pid) == 0


def test_before_deadline_plus_grace_nothing(db_engine):
    pid, _ = _open_day(db_engine, 9710)
    _prepare(db_engine, pid)
    now = _overdue_now(db_engine, pid, extra=timedelta(0))  # ровно дедлайн + 120 с
    assert tick(db_engine, now) == TickResult(0, 0)
    assert close_one(db_engine, pid, now) is False
    assert _events(db_engine, pid) == []


def test_tick_twice_same_now_one_close(db_engine):
    pid, started = _open_day(db_engine, 9711)
    _prepare(db_engine, pid, missed_streak=1)
    now = _overdue_now(db_engine, pid)
    assert tick(db_engine, now) == TickResult(1, 0)
    assert tick(db_engine, now) == TickResult(0, 1)  # проектор ещё не догнал
    run_once(db_engine)
    assert tick(db_engine, now) == TickResult(0, 0)  # день уже другой
    # Рестарт со «старым» состоянием (день D снова текущий): ключ day_close не даёт закрыть.
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE participant_state SET day_started_at = :s WHERE pid = :p"),
            {"p": pid, "s": started},
        )
    assert tick(db_engine, now) == TickResult(0, 1)
    assert _close_keys(db_engine, pid) == 1
    assert [e.kind for e in _events(db_engine, pid)] == ["life_op", "day_closed"]
    assert _state(db_engine, pid).lives == 2


def test_downtime_5_days_one_close(db_engine):
    pid, started = _open_day(db_engine, 9712)
    _prepare(db_engine, pid, missed_streak=1)
    now = _overdue_now(db_engine, pid, extra=timedelta(days=5, seconds=1))
    assert tick(db_engine, now) == TickResult(1, 0)
    run_once(db_engine)
    assert tick(db_engine, now) == TickResult(0, 0)
    state = _state(db_engine, pid)
    expected = _u(day_clock.last_midnight(now, state.tz))
    assert _u(state.day_started_at) == expected
    assert expected > _u(started)
    assert state.lives == 2  # одна жизнь, а не по дню простоя
    assert [e.kind for e in _events(db_engine, pid)] == ["life_op", "day_closed"]


def test_pending_event_skipped(db_engine):
    pid, _ = _open_day(db_engine, 9713)
    _prepare(db_engine, pid, missed_streak=1)
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO participant_events (pid, kind, payload, actor, actor_role) "
                "VALUES (:p, 'test_pending', CAST(:pl AS jsonb), 'system', 'system')"
            ),
            {"p": pid, "pl": json.dumps({})},
        )
    assert tick(db_engine, _overdue_now(db_engine, pid)) == TickResult(0, 1)
    assert _events(db_engine, pid) == []
    assert _close_keys(db_engine, pid) == 0


def test_u1_day_closed_insert_fails_rollback_all(db_engine, monkeypatch, caplog):
    pid, _ = _open_day(db_engine, 9714)
    _prepare(db_engine, pid, missed_streak=1)
    real = life_ops._insert_event
    hit = {"life_op": False}

    def failing(conn, p, kind, payload):
        if kind == life_ops.EVENT_KIND_DAY_CLOSED:
            raise OperationalError("INSERT", {}, Exception("insert failed"))
        hit["life_op"] = True
        return real(conn, p, kind, payload)

    monkeypatch.setattr(life_ops, "_insert_event", failing)
    with caplog.at_level(logging.WARNING, logger="app.life_ops"):
        assert tick(db_engine, _overdue_now(db_engine, pid)) == TickResult(0, 1)
    assert hit["life_op"]  # life_op и ключ были записаны до сбоя — и откатились
    assert _close_keys(db_engine, pid) == 0
    assert _events(db_engine, pid) == []
    run_once(db_engine)
    assert _state(db_engine, pid).lives == 3
    warnings = [m for m in _life_msgs(caplog) if "db error" in m]
    assert warnings and all("OperationalError" in m and str(pid) not in m for m in warnings)


def test_u2_block_lives_no_life_op(db_engine):
    pid, started = _open_day(db_engine, 9715)
    _prepare(db_engine, pid, missed_streak=1, flags="{block_lives}")
    assert tick(db_engine, _overdue_now(db_engine, pid)) == TickResult(1, 0)
    events = _events(db_engine, pid)
    assert [e.kind for e in events] == ["day_closed"]
    assert events[0].payload["outcome"] == "silent"
    assert events[0].payload["missed_streak"] == 0
    assert _close_keys(db_engine, pid) == 1
    run_once(db_engine)
    state = _state(db_engine, pid)
    assert (state.lives, state.missed_streak) == (3, 0)


def test_u5_next_not_later_nothing_written(db_engine, monkeypatch, caplog):
    pid, started = _open_day(db_engine, 9716)
    _prepare(db_engine, pid, missed_streak=1)
    monkeypatch.setattr(day_clock, "last_midnight", lambda now, tz: started)
    with caplog.at_level(logging.WARNING, logger="app.life_ops"):
        assert tick(db_engine, _overdue_now(db_engine, pid)) == TickResult(0, 1)
    assert _events(db_engine, pid) == []
    assert _close_keys(db_engine, pid) == 0
    warnings = [m for m in _life_msgs(caplog) if "not later" in m]
    assert warnings and all(str(pid) not in m for m in warnings)


def test_dry_run_writes_nothing(db_engine, capsys):
    pid, started = _open_day(db_engine, 9717)
    _prepare(db_engine, pid, missed_streak=1)
    now = _overdue_now(db_engine, pid)
    info = dry_run(db_engine, pid, now)
    assert info is not None
    assert info["is_overdue"] is True
    assert info["outcome_if_closed_now"]["life_delta"] == -1
    assert _u(info["deadline_at"]) == _u(day_clock.deadline_at(started, "Europe/Moscow"))
    assert _events(db_engine, pid) == []
    assert _close_keys(db_engine, pid) == 0
    assert dry_run(db_engine, uuid.uuid4(), now) is None
    with db_engine.connect() as conn:
        key = conn.execute(
            text("SELECT 1 FROM idempotency_keys WHERE key = :k"),
            {"k": key_day_close(pid, started)},
        ).first()
    assert key is None
