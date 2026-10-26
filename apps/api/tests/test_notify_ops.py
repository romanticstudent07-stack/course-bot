"""«Часы» НП3 (pushi-notify-1): чистые функции, tick, шаг в run_forever. С БД — только CI.

now — аргументом tick, от фактического day_started_at (реальное время запуска не влияет).
Тестовое состояние (day_started_at, фаза, флаги, пауза) готовится прямым UPDATE от владельца
БД — только в тесте; «часы» participant_state не пишут.
outbox и idempotency_keys фикстура db_engine не чистит — проверки по pid.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import day_clock, life_ops, notify_ops, projector
from app.day_keys import TTL_BY_KIND, key_day_queue, key_tasks_open
from app.notify_ops import (
    TEXT_TODAY,
    TEXT_TOMORROW,
    NotifyResult,
    choose_text,
    decide,
    is_late,
    tick,
)
from app.projector import ProjectorResult, run_once
from app.routers.day import enter_day_by_test_flag
from app.routers.onboarding import register_with_consents

MSK = ZoneInfo("Europe/Moscow")
VVO = ZoneInfo("Asia/Vladivostok")
PID = uuid.UUID("11111111-2222-3333-4444-555555555555")


def _u(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc)


# ------------------------------ без БД ------------------------------


# 1. choose_text: 03:59 → today; 04:00 и 23:59 → tomorrow.
@pytest.mark.parametrize("tz_name, z", [("Europe/Moscow", MSK), ("Asia/Vladivostok", VVO)])
def test_choose_text_by_local_time(tz_name, z):
    day = (2026, 10, 21)
    assert choose_text(datetime(*day, 3, 59, tzinfo=z), tz_name) == TEXT_TODAY
    assert choose_text(datetime(*day, 4, 0, tzinfo=z), tz_name) == TEXT_TOMORROW
    assert choose_text(datetime(*day, 23, 59, tzinfo=z), tz_name) == TEXT_TOMORROW
    # Тот же момент в UTC — тот же ответ (местное время берётся по поясу участника).
    assert choose_text(_u(datetime(*day, 3, 59, tzinfo=z)), tz_name) == TEXT_TODAY


# 2. is_late и decide.
def test_is_late_and_decide_send_late_queue():
    started = datetime(2026, 10, 20, 15, 0, tzinfo=MSK)
    tz = "Europe/Moscow"
    evening = datetime(2026, 10, 20, 20, 0, tzinfo=MSK)
    next_0400 = datetime(2026, 10, 21, 4, 0, tzinfo=MSK)
    assert is_late(started, tz, evening) is False
    assert is_late(started, tz, next_0400) is True
    assert decide(PID, started, tz, evening, False, True) == "send"
    assert decide(PID, started, tz, next_0400, False, True) == "late"
    until = day_clock.queue_until(PID, started)
    assert decide(PID, started, tz, until - timedelta(seconds=1), True, False) is None
    assert decide(PID, started, tz, started + timedelta(minutes=5), True, True) is None
    assert decide(PID, started, tz, until, True, False) == "send"
    assert decide(PID, started, tz, _u(until), True, False) == "send"


# 3. Нет day_queue и нет day_entered (день после day_closed) → None.
def test_decide_no_queue_no_entered_none():
    started = datetime(2026, 10, 21, 0, 0, tzinfo=MSK)
    for now in (
        datetime(2026, 10, 21, 1, 0, tzinfo=MSK),
        datetime(2026, 10, 21, 12, 0, tzinfo=MSK),
    ):
        assert decide(PID, started, "Europe/Moscow", now, False, False) is None


# 4. key_tasks_open.
def test_key_tasks_open_format_and_ttl():
    ts = datetime(2026, 10, 20, 15, 0, tzinfo=MSK)
    assert key_tasks_open(PID, ts) == f"tasks_open:{PID}:2026-10-20T12:00:00+00:00"
    assert key_tasks_open(PID, ts) == key_tasks_open(PID, _u(ts))
    with pytest.raises(ValueError):
        key_tasks_open(PID, datetime(2026, 10, 20, 15, 0))
    assert TTL_BY_KIND["tasks_open"] == "3650 days"


# 5. Статика.
def test_static_outbox_insert_and_kinds():
    src = Path(notify_ops.__file__).read_text(encoding="utf-8")
    inserts = re.findall(r"INSERT INTO outbox.*?\"\"\"", src, flags=re.S)
    assert inserts, "нет INSERT INTO outbox"
    assert all("RETURNING" not in block for block in inserts)
    assert "pg_current_xact_id()" in src
    assert "INSERT INTO participant_events" not in src
    assert "participant_state SET" not in src and "INSERT INTO participant_state" not in src
    assert notify_ops.EVENT_KIND_DAY_ENTERED == projector.EVENT_KIND_DAY_ENTERED


# 6. tick с naive now; _notify_ops_step и run_forever переживают ошибку tick.
def test_tick_naive_now_value_error():
    with pytest.raises(ValueError):
        tick(object(), datetime(2026, 10, 21, 12, 0))  # type: ignore[arg-type]


class _Stop(Exception):
    pass


class _FakeConn:
    def execute(self, *args, **kwargs):
        return None

    def commit(self):
        return None


@contextmanager
def _fake_lock(engine):
    yield _FakeConn()


def test_notify_ops_step_error_warning_loop_alive(monkeypatch, caplog):
    clock = {"now": datetime(2026, 10, 21, 21, 0, tzinfo=timezone.utc)}
    secret = str(uuid.uuid4())
    order: list[str] = []
    drains = {"n": 0}

    def life_tick(engine, now):
        order.append("life")
        return life_ops.TickResult(0, 0)

    def broken_tick(engine, now):
        order.append("notify")
        raise RuntimeError(secret)

    def drain(engine):
        drains["n"] += 1
        return ProjectorResult(0, 0)

    def sleep(seconds):
        clock["now"] += timedelta(seconds=seconds)
        if drains["n"] >= 61:
            raise _Stop

    monkeypatch.setattr(projector, "_advisory_lock", _fake_lock)
    monkeypatch.setattr(projector, "_drain", drain)
    monkeypatch.setattr(life_ops, "tick", life_tick)
    monkeypatch.setattr(notify_ops, "tick", broken_tick)
    monkeypatch.setattr(day_clock, "utcnow", lambda: clock["now"])
    with caplog.at_level(logging.WARNING, logger="app.projector"):
        assert projector._notify_ops_step(object(), None) == clock["now"]  # type: ignore[arg-type]
        order.clear()
        with pytest.raises(_Stop):
            projector.run_forever(object(), poll_seconds=1.0, sleep=sleep)  # type: ignore[arg-type]
    assert drains["n"] == 61  # цикл проектора жив после ошибок tick
    assert order == ["life", "notify"] * 3  # на 0, 30, 60 с; notify — сразу после life
    messages = [r.getMessage() for r in caplog.records if r.name == "app.projector"]
    failed = [m for m in messages if "notify_ops tick failed" in m]
    assert len(failed) == 4
    assert all("RuntimeError" in m and secret not in m for m in failed)


# ---------------------------------- с БД ----------------------------------


def _open_day(engine, tg_user_id: int):
    with Session(engine) as session:
        pid = register_with_consents(session, tg_user_id, ["C0", "C1"]).participant.pid
    run_once(engine)
    with Session(engine) as session:
        enter_day_by_test_flag(session, tg_user_id, True)
    run_once(engine)
    return pid, _state(engine, pid).day_started_at


def _state(engine, pid):
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT day_started_at, tz FROM participant_state WHERE pid = :p"),
            {"p": pid},
        ).one()


def _queued_day(engine, tg_user_id: int):
    """День с фиксированным стартом 15:00 по поясу участника и ключом day_queue к нему."""
    pid, _ = _open_day(engine, tg_user_id)
    tz = _state(engine, pid).tz
    started = datetime(2026, 10, 20, 15, 0, tzinfo=day_clock.zone(tz))
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE participant_state SET day_started_at = :s WHERE pid = :p"),
            {"p": pid, "s": started},
        )
        conn.execute(
            text(
                "INSERT INTO idempotency_keys (key, kind, ttl) "
                "VALUES (:k, 'day_queue', CAST('3650 days' AS interval))"
            ),
            {"k": key_day_queue(pid, started)},
        )
    return pid, started, tz


def _outbox(engine, pid) -> list:
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT event_type, payload, tx_id FROM outbox "
                "WHERE aggregate_id::text = :a ORDER BY id"
            ),
            {"a": str(pid)},
        ).all()


def _tasks_open_keys(engine, pid) -> list[str]:
    with engine.connect() as conn:
        return list(
            conn.execute(
                text("SELECT key FROM idempotency_keys WHERE key LIKE :k"),
                {"k": f"tasks_open:{pid}:%"},
            ).scalars()
        )


def _payload(raw) -> dict:
    return raw if isinstance(raw, dict) else json.loads(raw)


# 7. После очереди.
def test_after_queue_one_outbox_then_nothing(db_engine):
    pid, started, tz = _queued_day(db_engine, 9801)
    now = _u(day_clock.queue_until(pid, started)) + timedelta(seconds=1)
    assert tick(db_engine, now) == NotifyResult(sent=1, late=0, skipped=0)
    rows = _outbox(db_engine, pid)
    assert len(rows) == 1
    assert rows[0].event_type == "tasks_open_notice"
    assert _payload(rows[0].payload) == {
        "text_id": choose_text(now, tz),
        "payload_vars": {},
        "tier": "T2",
    }
    assert _payload(rows[0].payload)["text_id"] == TEXT_TOMORROW  # 15:10–16:01 местного
    assert rows[0].tx_id is not None
    assert _tasks_open_keys(db_engine, pid) == [key_tasks_open(pid, started)]
    assert tick(db_engine, now + timedelta(seconds=30)) == NotifyResult(0, 0, 0)
    assert len(_outbox(db_engine, pid)) == 1


# 8. После онбординга: day_entered и состояние с тем же day_started_at.
def test_after_onboarding_day_entered_one_outbox(db_engine):
    pid, started = _open_day(db_engine, 9802)
    # now = старт дня: задания ещё не открыты (active_from ≥ started).
    assert tick(db_engine, _u(started)) == NotifyResult(sent=1, late=0, skipped=0)
    rows = _outbox(db_engine, pid)
    assert len(rows) == 1
    assert _payload(rows[0].payload)["tier"] == "T2"
    assert _tasks_open_keys(db_engine, pid) == [key_tasks_open(pid, started)]


# 9. Опоздание (В4): now после active_from → ключ есть, outbox 0.
def test_late_after_active_from_key_only(db_engine):
    pid, started, tz = _queued_day(db_engine, 9803)
    now = _u(day_clock.active_from(started, tz)) + timedelta(seconds=1)
    assert tick(db_engine, now) == NotifyResult(sent=0, late=1, skipped=0)
    assert _tasks_open_keys(db_engine, pid) == [key_tasks_open(pid, started)]
    assert _outbox(db_engine, pid) == []


# 10. Фильтры: пауза, block_lives, sleeping, событие после checkpoint.
@pytest.mark.parametrize(
    "tg, case", [(9804, "pause"), (9805, "block_lives"), (9806, "sleeping"), (9807, "pending")]
)
def test_filters_nothing_written(db_engine, tg, case):
    pid, started, _tz = _queued_day(db_engine, tg)
    with db_engine.begin() as conn:
        if case == "pause":
            conn.execute(
                text("UPDATE participant_state SET author_pause_reason = 'test' WHERE pid = :p"),
                {"p": pid},
            )
        elif case == "block_lives":
            conn.execute(
                text(
                    "UPDATE participant_state SET status_flags = CAST('{block_lives}' AS text[]) "
                    "WHERE pid = :p"
                ),
                {"p": pid},
            )
        elif case == "sleeping":
            conn.execute(
                text("UPDATE participant_state SET lifecycle_phase = 'sleeping' WHERE pid = :p"),
                {"p": pid},
            )
        else:
            conn.execute(
                text(
                    "INSERT INTO participant_events (pid, kind, payload, actor, actor_role) "
                    "VALUES (:p, 'test_pending', CAST(:pl AS jsonb), 'system', 'system')"
                ),
                {"p": pid, "pl": json.dumps({})},
            )
    now = _u(day_clock.queue_until(pid, started)) + timedelta(seconds=1)
    result = tick(db_engine, now)
    assert result.sent == 0 and result.late == 0
    assert _tasks_open_keys(db_engine, pid) == []
    assert _outbox(db_engine, pid) == []


# 11. Роль app_projector: INSERT в outbox без RETURNING проходит; tx_id не NULL.
def test_app_projector_role_outbox_insert(db_engine):
    aggregate_id = str(uuid.uuid4())
    payload = {"text_id": TEXT_TODAY, "payload_vars": {}, "tier": "T2"}
    with db_engine.begin() as conn:
        conn.execute(text("SET LOCAL ROLE app_projector"))
        conn.execute(
            notify_ops._INSERT_OUTBOX,
            {
                "aggregate_id": aggregate_id,
                "event_type": notify_ops.EVENT_TYPE,
                "payload": json.dumps(payload),
            },
        )
    rows = _outbox(db_engine, aggregate_id)
    assert len(rows) == 1
    assert rows[0].tx_id is not None
    assert rows[0].event_type == "tasks_open_notice"
