"""Лестница «пришёл, но не отправил» (ladder-1, DM 3.17). С БД — только CI.

День: старт 00:00 21.10 по поясу участника → активация 04:00 21.10, дедлайн 00:00 22.10.
now — аргументом, реальное время запуска не влияет. Отметки day_marks (at задаётся явно)
и тестовое состояние готовит владелец БД — только в тесте. outbox и idempotency_keys фикстура
db_engine не чистит — проверки по pid.
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import day_clock, notify_ladder, notify_ops
from app.day_keys import LADDER_STEPS, TTL_BY_KIND, key_day_done, key_ladder
from app.notify_ladder import TEXT_BY_STEP, LadderPlan, decide_ladder, step_times, tick_ladder
from app.projector import run_once
from app.routers.day import enter_day_by_test_flag
from app.routers.onboarding import register_with_consents

MSK = ZoneInfo("Europe/Moscow")
VVO = ZoneInfo("Asia/Vladivostok")
PID = uuid.UUID("11111111-2222-3333-4444-555555555555")
API_DIR = Path(__file__).resolve().parents[1]
DAY_JSON = API_DIR / "config" / "texts" / "day.json"
ZONES = [("Europe/Moscow", MSK), ("Asia/Vladivostok", VVO)]


def _u(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc)


def _day(z):
    started = datetime(2026, 10, 21, 0, 0, tzinfo=z)
    return started, (lambda h, m: datetime(2026, 10, 21, h, m, tzinfo=z))


# ------------------------------ без БД ------------------------------


# 1. step_times: отметка 15:00 → 16:00, 22:00, 23:30; отметка 21:30 → plus1h = 22:00.
@pytest.mark.parametrize("tz_name, z", ZONES)
def test_step_times(tz_name, z):
    started, at = _day(z)
    deadline = day_clock.deadline_at(started, tz_name)
    assert _u(deadline) == _u(datetime(2026, 10, 22, 0, 0, tzinfo=z))
    assert step_times(at(15, 0), deadline) == [
        ("plus1h", _u(at(16, 0))),
        ("minus2h", _u(at(22, 0))),
        ("minus30m", _u(at(23, 30))),
    ]
    assert step_times(at(21, 30), deadline)[0] == ("plus1h", _u(at(22, 0)))
    # Тот же момент в UTC — тот же результат.
    assert step_times(_u(at(15, 0)), _u(deadline)) == step_times(at(15, 0), deadline)


# 2. decide_ladder: шаги, ключи, простой (В7 А).
@pytest.mark.parametrize("tz_name, z", ZONES)
def test_decide_steps(tz_name, z):
    started, at = _day(z)
    deadline = day_clock.deadline_at(started, tz_name)
    first = at(15, 0)
    assert decide_ladder(at(15, 59), True, first, deadline, False, set()) is None
    assert decide_ladder(at(16, 0), True, first, deadline, False, set()) == LadderPlan(
        "plus1h", ()
    )
    assert decide_ladder(at(22, 0), True, first, deadline, False, {"plus1h"}) == LadderPlan(
        "minus2h", ()
    )
    assert decide_ladder(at(22, 0), True, first, deadline, False, set()) == LadderPlan(
        "minus2h", ("plus1h",)
    )
    assert decide_ladder(_u(at(23, 30)), True, first, deadline, False, set()) == LadderPlan(
        "minus30m", ("plus1h", "minus2h")
    )
    assert (
        decide_ladder(at(23, 40), True, first, deadline, False, set(LADDER_STEPS)) is None
    )


# 3. Отметка 21:30 → first + 1 ч = 22:30, plus1h = 22:00: 21:45 → None; 22:00 → minus2h, late plus1h.
@pytest.mark.parametrize("tz_name, z", ZONES)
def test_decide_late_mark(tz_name, z):
    started, at = _day(z)
    deadline = day_clock.deadline_at(started, tz_name)
    first = at(21, 30)
    assert decide_ladder(at(21, 45), True, first, deadline, False, set()) is None
    assert decide_ladder(at(22, 0), True, first, deadline, False, set()) == LadderPlan(
        "minus2h", ("plus1h",)
    )


# 4. done → None; окно закрыто (после дедлайна) → None; отметок нет → None.
@pytest.mark.parametrize("tz_name, z", ZONES)
def test_decide_gates(tz_name, z):
    started, at = _day(z)
    deadline = day_clock.deadline_at(started, tz_name)
    first = at(15, 0)
    assert decide_ladder(at(16, 0), True, first, deadline, True, set()) is None
    after = deadline + timedelta(minutes=1)
    assert day_clock.window(started, tz_name, after) == day_clock.WINDOW_CLOSED
    assert decide_ladder(after, False, first, deadline, False, set()) is None
    assert decide_ladder(at(16, 0), True, None, deadline, False, set()) is None
    with pytest.raises(ValueError):
        decide_ladder(datetime(2026, 10, 21, 16, 0), True, first, deadline, False, set())


# 5. key_ladder: формат, тот же момент в UTC — тот же ключ, неизвестный шаг → ValueError; TTL.
def test_key_ladder_format_and_ttl():
    started = datetime(2026, 10, 21, 0, 0, tzinfo=MSK)
    assert key_ladder(PID, started, "plus1h") == (
        f"ladder:{PID}:2026-10-20T21:00:00+00:00:plus1h"
    )
    for step in LADDER_STEPS:
        assert key_ladder(PID, started, step) == key_ladder(PID, _u(started), step)
    with pytest.raises(ValueError):
        key_ladder(PID, started, "minus1h")
    assert TTL_BY_KIND["ladder"] == "3650 days"


# 6. Импорт в обоих порядках — без цикла.
@pytest.mark.parametrize(
    "code",
    ["import app.notify_ladder, app.notify_ops", "import app.notify_ops, app.notify_ladder"],
)
def test_import_both_orders(code):
    result = subprocess.run([sys.executable, "-c", code], cwd=API_DIR, capture_output=True)
    assert result.returncode == 0, result.stderr.decode(errors="replace")


# 7. Все три текста есть в day.json.
def test_static_texts_in_day_json():
    data = json.loads(DAY_JSON.read_text(encoding="utf-8"))
    keys = {e["key"] for e in data["entries"]}
    assert set(TEXT_BY_STEP) == set(LADDER_STEPS)
    assert set(TEXT_BY_STEP.values()) <= keys


# ---------------------------------- с БД ----------------------------------


def _open_day(engine, tg_user_id: int):
    """День с фиксированным стартом 00:00 21.10 по поясу участника (открыт 04:00 — 00:00)."""
    with Session(engine) as session:
        pid = register_with_consents(session, tg_user_id, ["C0", "C1"]).participant.pid
    run_once(engine)
    with Session(engine) as session:
        enter_day_by_test_flag(session, tg_user_id, True)
    run_once(engine)
    with engine.connect() as conn:
        tz = conn.execute(
            text("SELECT tz FROM participant_state WHERE pid = :p"), {"p": pid}
        ).scalar_one()
    z = day_clock.zone(tz)
    started = datetime(2026, 10, 21, 0, 0, tzinfo=z)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE participant_state SET day_started_at = :s WHERE pid = :p"),
            {"p": pid, "s": started},
        )
    return pid, started, tz, z


def _mark(engine, pid: uuid.UUID, started: datetime, at: datetime, block_id: str = "task_1"):
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO day_marks (pid, day_started_at, block_id, value, at) "
                "VALUES (:pid, :ts, :b, :v, :at)"
            ),
            {"pid": pid, "ts": started, "b": block_id, "v": True, "at": at},
        )


def _outbox(engine, pid) -> list:
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT event_type, payload, tx_id FROM outbox "
                "WHERE aggregate_id::text = :a AND event_type = 'ladder_reminder' ORDER BY id"
            ),
            {"a": str(pid)},
        ).all()


def _ladder_keys(engine, pid) -> set[str]:
    with engine.connect() as conn:
        return set(
            conn.execute(
                text("SELECT key FROM idempotency_keys WHERE key LIKE :k"),
                {"k": f"ladder:{pid}:%"},
            ).scalars()
        )


def _payload(raw) -> dict:
    return raw if isinstance(raw, dict) else json.loads(raw)


# 8. Через 1 ч после отметки → sent 1, ключ plus1h, 1 outbox (T2); второй tick → 0.
def test_ladder_plus1h_once(db_engine):
    pid, started, _tz, z = _open_day(db_engine, 9921)
    _mark(db_engine, pid, started, _u(datetime(2026, 10, 21, 15, 0, tzinfo=z)))
    _mark(db_engine, pid, started, _u(datetime(2026, 10, 21, 15, 40, tzinfo=z)), "task_2")
    now = _u(datetime(2026, 10, 21, 16, 0, 30, tzinfo=z))
    r = tick_ladder(db_engine, now)
    assert (r.sent, r.late) == (1, 0)
    assert _ladder_keys(db_engine, pid) == {key_ladder(pid, started, "plus1h")}
    rows = _outbox(db_engine, pid)
    assert len(rows) == 1
    assert _payload(rows[0].payload) == {
        "text_id": TEXT_BY_STEP["plus1h"],
        "payload_vars": {},
        "tier": "T2",
    }
    assert rows[0].tx_id is not None
    assert tick_ladder(db_engine, now + timedelta(seconds=30)).sent == 0
    assert len(_outbox(db_engine, pid)) == 1


# 9. 23:30 после простоя → 1 outbox (minus30m) и 3 ключа.
def test_ladder_after_downtime(db_engine):
    pid, started, _tz, z = _open_day(db_engine, 9922)
    _mark(db_engine, pid, started, _u(datetime(2026, 10, 21, 15, 0, tzinfo=z)))
    r = tick_ladder(db_engine, _u(datetime(2026, 10, 21, 23, 30, 30, tzinfo=z)))
    assert (r.sent, r.late) == (1, 2)
    assert _ladder_keys(db_engine, pid) == {key_ladder(pid, started, s) for s in LADDER_STEPS}
    rows = _outbox(db_engine, pid)
    assert len(rows) == 1
    assert _payload(rows[0].payload)["text_id"] == TEXT_BY_STEP["minus30m"]


# 10. Ключ day_done → 0; пауза, флаг, sleeping, не догнанное событие → 0, ни ключа, ни outbox.
@pytest.mark.parametrize(
    "tg, case",
    [
        (9923, "day_done"),
        (9924, "pause"),
        (9925, "block_lives"),
        (9926, "sleeping"),
        (9927, "pending"),
    ],
)
def test_ladder_filters_nothing_written(db_engine, tg, case):
    pid, started, _tz, z = _open_day(db_engine, tg)
    _mark(db_engine, pid, started, _u(datetime(2026, 10, 21, 15, 0, tzinfo=z)))
    with db_engine.begin() as conn:
        if case == "day_done":
            conn.execute(
                text(
                    "INSERT INTO idempotency_keys (key, kind, ttl) "
                    "VALUES (:k, 'day_done', CAST('3650 days' AS interval))"
                ),
                {"k": key_day_done(pid, started)},
            )
        elif case == "pause":
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
    r = tick_ladder(db_engine, _u(datetime(2026, 10, 21, 16, 0, 30, tzinfo=z)))
    assert r.sent == 0
    assert _ladder_keys(db_engine, pid) == set()
    assert _outbox(db_engine, pid) == []


# 11. tick: результат по полям; падение одного правила не останавливает другие.
def test_tick_ladder_field_and_isolation(db_engine, monkeypatch, caplog):
    pid, started, _tz, z = _open_day(db_engine, 9928)
    _mark(db_engine, pid, started, _u(datetime(2026, 10, 21, 15, 0, tzinfo=z)))

    def broken(engine, now):
        raise RuntimeError("boom")

    monkeypatch.setattr(notify_ops, "tick_noon", broken)
    now = _u(datetime(2026, 10, 21, 16, 0, 30, tzinfo=z))
    with caplog.at_level(logging.WARNING, logger="app.notify_ops"):
        r = notify_ops.tick(db_engine, now)
    assert r.ladder.sent == 1
    assert r.noon.sent == 0
    messages = [rec.getMessage() for rec in caplog.records if rec.name == "app.notify_ops"]
    assert any("rule noon failed (RuntimeError)" in m for m in messages)
    assert len(_outbox(db_engine, pid)) == 1

    # Падает лестница — остальные правила возвращают результат, tick не падает.
    monkeypatch.setattr(notify_ladder, "tick_ladder", broken)
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="app.notify_ops"):
        r2 = notify_ops.tick(db_engine, now + timedelta(minutes=1))
    assert r2.ladder == notify_ops.NotifyResult(0, 0, 0)
    assert isinstance(r2.tasks_open, notify_ops.NotifyResult)
    messages = [rec.getMessage() for rec in caplog.records if rec.name == "app.notify_ops"]
    assert any("rule ladder failed (RuntimeError)" in m for m in messages)
