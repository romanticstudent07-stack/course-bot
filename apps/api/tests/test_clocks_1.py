"""clocks-1: пропуск дня рефлексии (−1 сразу), алерт ladder_day2_alert, ключ ladder_day2.

Без БД: is_reflection_day, close_outcome с флагом и без, key_ladder_day2 и TTL, is_day2.
С БД (только CI): life_ops.tick на днях 5 / 6 / 7 / 13, dry_run; лестница и алерт «день 2».
День: старт 00:00 21.10 по поясу участника → активация 04:00 21.10, дедлайн 00:00 22.10.
now — аргументом. Тестовое состояние готовит владелец БД (UPDATE), как в test_notify_ladder.
outbox и idempotency_keys фикстура db_engine не чистит — проверки по pid.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import day_clock, life_ops
from app.day_clock import CloseOutcome, close_outcome, is_reflection_day
from app.day_keys import KIND_DAY_DONE, TTL_BY_KIND, key_day_done, key_ladder, key_ladder_day2
from app.notify_ladder import EVENT_TYPE_DAY2, is_day2, tick_ladder
from app.projector import run_once
from app.routers.day import enter_day_by_test_flag
from app.routers.onboarding import register_with_consents

MSK = ZoneInfo("Europe/Moscow")
VVO = ZoneInfo("Asia/Vladivostok")
PID = uuid.UUID("11111111-2222-3333-4444-555555555555")


def _u(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc)


# ------------------------------ без БД ------------------------------


# 1. is_reflection_day.
def test_is_reflection_day():
    assert day_clock.REFLECTION_DAYS == (6, 13)
    assert is_reflection_day(6) is True
    assert is_reflection_day(13) is True
    for value in (1, 5, 7, 12, 14, None, True, False, "6", 6.0):
        assert is_reflection_day(value) is False


# 2. close_outcome с флагом: ровно −1, счётчик 0, sleeping при lives 1, lives 0 → ValueError.
def test_close_outcome_reflection():
    assert close_outcome(True, 0, 3, is_reflection_day=True) == CloseOutcome("came", 0, -1, False)
    assert close_outcome(False, 1, 3, is_reflection_day=True) == CloseOutcome(
        "silent", 0, -1, False
    )
    assert close_outcome(False, 0, 2, is_reflection_day=True) == CloseOutcome(
        "silent", 0, -1, False
    )
    assert close_outcome(True, 1, 1, is_reflection_day=True) == CloseOutcome("came", 0, -1, True)
    assert close_outcome(False, 1, 1, is_reflection_day=True).sleeping is True
    with pytest.raises(ValueError):
        close_outcome(True, 0, 0, is_reflection_day=True)
    with pytest.raises(ValueError):
        close_outcome(True, -1, 3, is_reflection_day=True)


# 3. Без флага — прежние значения; key_ladder_day2 и TTL.
def test_close_outcome_default_and_key():
    assert close_outcome(True, 1, 3) == CloseOutcome("came", 0, 0, False)
    assert close_outcome(False, 0, 3) == CloseOutcome("silent", 1, 0, False)
    assert close_outcome(False, 1, 3) == CloseOutcome("silent", 0, -1, False)
    assert close_outcome(False, 1, 1) == CloseOutcome("silent", 0, -1, True)
    assert close_outcome(False, 1, 3, is_reflection_day=False) == close_outcome(False, 1, 3)
    started = datetime(2026, 10, 21, 0, 0, tzinfo=MSK)
    assert key_ladder_day2(PID, started) == f"ladder_day2:{PID}:2026-10-20T21:00:00+00:00"
    assert key_ladder_day2(PID, started) == key_ladder_day2(PID, _u(started))
    with pytest.raises(ValueError):
        key_ladder_day2(PID, datetime(2026, 10, 21, 0, 0))
    assert TTL_BY_KIND["ladder_day2"] == "3650 days"


# 4. is_day2.
def test_is_day2():
    started = datetime(2026, 10, 22, 0, 0, tzinfo=MSK)
    iso_utc = _u(started).isoformat()
    iso_vvo = started.astimezone(VVO).isoformat()
    assert is_day2({"outcome": "came", "next_day_started_at": iso_utc}, started) is True
    assert is_day2({"outcome": "came", "next_day_started_at": iso_vvo}, started) is True
    assert is_day2({"outcome": "came", "next_day_started_at": iso_utc}, _u(started)) is True
    other = _u(started + timedelta(days=1)).isoformat()
    assert is_day2({"outcome": "silent", "next_day_started_at": iso_utc}, started) is False
    assert is_day2({"outcome": "came", "next_day_started_at": other}, started) is False
    assert is_day2({"outcome": "came"}, started) is False
    assert is_day2({"outcome": "came", "next_day_started_at": 123}, started) is False
    assert is_day2({"outcome": "came", "next_day_started_at": None}, started) is False
    assert is_day2({"outcome": "came", "next_day_started_at": "2026-10-22T00:00:00"}, started) is False
    assert is_day2({"outcome": "came", "next_day_started_at": "not a date"}, started) is False
    assert is_day2(None, started) is False
    assert is_day2([], started) is False
    assert is_day2("came", started) is False


# ---------------------------------- с БД ----------------------------------


def _open_day(engine, tg_user_id: int, day_no: int = 1, **state):
    """День с фиксированным стартом 00:00 21.10 по поясу участника; day_no и поля — UPDATE."""
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
    sets = ["day_started_at = :s", "day_no = :d"]
    params = {"p": pid, "s": started, "d": day_no}
    for name, value in state.items():  # только имена из теста
        sets.append(f"{name} = :{name}")
        params[name] = value
    with engine.begin() as conn:
        conn.execute(
            text(f"UPDATE participant_state SET {', '.join(sets)} WHERE pid = :p"), params
        )
    return pid, started, tz, z


def _mark(engine, pid, started, at, block_id="task_1"):
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO day_marks (pid, day_started_at, block_id, value, at) "
                "VALUES (:pid, :ts, :b, :v, :at)"
            ),
            {"pid": pid, "ts": started, "b": block_id, "v": True, "at": at},
        )


def _payload(raw) -> dict:
    return raw if isinstance(raw, dict) else json.loads(raw)


def _events(engine, pid) -> list[tuple[str, dict]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT kind, payload FROM participant_events "
                "WHERE pid = :p AND kind IN ('life_op', 'day_closed') ORDER BY id"
            ),
            {"p": pid},
        ).all()
    return [(k, _payload(p)) for k, p in rows]


def _state(engine, pid):
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT lives, missed_streak, lifecycle_phase, day_started_at "
                "FROM participant_state WHERE pid = :p"
            ),
            {"p": pid},
        ).one()


def _outbox(engine, pid, event_type: str) -> list:
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT payload FROM outbox "
                "WHERE aggregate_id::text = :a AND event_type = :t ORDER BY id"
            ),
            {"a": str(pid), "t": event_type},
        ).all()


def _has_key(engine, key: str) -> bool:
    with engine.connect() as conn:
        return (
            conn.execute(text("SELECT 1 FROM idempotency_keys WHERE key = :k"), {"k": key}).first()
            is not None
        )


def _after_deadline(z) -> datetime:
    return _u(datetime(2026, 10, 22, 0, 5, tzinfo=z))


# 5. День 6 с отметками, без отчёта → life_op −1 (missed_days) и day_closed came.
def test_reflection_day6_came_loses_life(db_engine):
    pid, started, _tz, z = _open_day(db_engine, 9951, day_no=6)
    _mark(db_engine, pid, started, _u(datetime(2026, 10, 21, 15, 0, tzinfo=z)))
    before = _state(db_engine, pid)
    life_ops.tick(db_engine, _after_deadline(z))
    events = _events(db_engine, pid)
    assert [k for k, _ in events] == ["life_op", "day_closed"]
    assert events[0][1]["delta"] == -1
    assert events[0][1]["reason"] == "missed_days"
    assert events[1][1]["outcome"] == "came"
    assert events[1][1]["missed_streak"] == 0
    run_once(db_engine)
    after = _state(db_engine, pid)
    assert after.lives == before.lives - 1
    assert after.missed_streak == 0


# 6. День 13, тишина, missed_streak 1 → ровно −1 (не −2), счётчик 0.
def test_reflection_day13_silent_one_life(db_engine):
    pid, _started, _tz, z = _open_day(db_engine, 9952, day_no=13, missed_streak=1)
    before = _state(db_engine, pid)
    life_ops.tick(db_engine, _after_deadline(z))
    events = _events(db_engine, pid)
    assert [k for k, _ in events] == ["life_op", "day_closed"]
    assert events[0][1]["delta"] == -1
    assert events[1][1]["outcome"] == "silent"
    run_once(db_engine)
    after = _state(db_engine, pid)
    assert after.lives == before.lives - 1
    assert after.missed_streak == 0


# 7. День 6 с ключом day_done → ничего; день 6 при lives 1 → sleeping.
def test_reflection_day6_done_and_sleeping(db_engine):
    pid, started, _tz, z = _open_day(db_engine, 9953, day_no=6)
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO idempotency_keys (key, kind, ttl) "
                "VALUES (:k, :kind, CAST(:ttl AS interval))"
            ),
            {"k": key_day_done(pid, started), "kind": KIND_DAY_DONE, "ttl": "3650 days"},
        )
    life_ops.tick(db_engine, _after_deadline(z))
    assert _events(db_engine, pid) == []
    with db_engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT 1 FROM idempotency_keys WHERE key LIKE :k"),
                {"k": f"day_close:{pid}:%"},
            ).first()
            is None
        )

    pid2, _s2, _tz2, z2 = _open_day(db_engine, 9954, day_no=6, lives=1)
    life_ops.tick(db_engine, _after_deadline(z2))
    run_once(db_engine)
    after = _state(db_engine, pid2)
    assert after.lives == 0
    assert after.lifecycle_phase == "sleeping"


# 8. Дни 5 и 7 — прежнее поведение; dry_run на дне 6 → life_delta −1.
@pytest.mark.parametrize("tg, day_no", [(9955, 5), (9956, 7)])
def test_non_reflection_days_unchanged(db_engine, tg, day_no):
    pid, started, _tz, z = _open_day(db_engine, tg, day_no=day_no)
    _mark(db_engine, pid, started, _u(datetime(2026, 10, 21, 15, 0, tzinfo=z)))
    life_ops.tick(db_engine, _after_deadline(z))
    events = _events(db_engine, pid)
    assert [k for k, _ in events] == ["day_closed"]
    assert events[0][1]["outcome"] == "came"


def test_dry_run_reflection_day(db_engine):
    pid, started, _tz, z = _open_day(db_engine, 9957, day_no=6)
    _mark(db_engine, pid, started, _u(datetime(2026, 10, 21, 15, 0, tzinfo=z)))
    info = life_ops.dry_run(db_engine, pid, _after_deadline(z))
    assert info is not None
    assert info["outcome_if_closed_now"]["life_delta"] == -1
    assert info["outcome_if_closed_now"]["missed_streak"] == 0
    assert _events(db_engine, pid) == []


def _day2(engine, tg: int, came: bool = True):
    """День 1 закрыт tick-ом life_ops (came или silent) → run_once → день 2 (00:00 22.10)."""
    pid, started, tz, z = _open_day(engine, tg)
    if came:
        _mark(engine, pid, started, _u(datetime(2026, 10, 21, 15, 0, tzinfo=z)))
    life_ops.tick(engine, _after_deadline(z))
    run_once(engine)
    day2 = datetime(2026, 10, 22, 0, 0, tzinfo=z)
    assert _u(_state(engine, pid).day_started_at) == _u(day2)
    return pid, day2, z


def _at2(z, h, m, s=0) -> datetime:
    return _u(datetime(2026, 10, 22, h, m, s, tzinfo=z))


# 9. «День 2»: plus1h → 1 ladder_reminder, 1 ladder_day2_alert, ключ; повтор → без второго.
def test_day2_alert_once(db_engine):
    pid, day2, z = _day2(db_engine, 9961)
    _mark(db_engine, pid, day2, _at2(z, 15, 0))
    r = tick_ladder(db_engine, _at2(z, 16, 0, 30))
    assert r.sent == 1
    assert len(_outbox(db_engine, pid, "ladder_reminder")) == 1
    alerts = _outbox(db_engine, pid, EVENT_TYPE_DAY2)
    assert len(alerts) == 1
    assert _payload(alerts[0].payload) == {"pid": str(pid)}
    assert _has_key(db_engine, key_ladder_day2(pid, day2))
    tick_ladder(db_engine, _at2(z, 16, 1))
    tick_ladder(db_engine, _at2(z, 22, 0, 30))
    assert len(_outbox(db_engine, pid, EVENT_TYPE_DAY2)) == 1


# 10. plus1h ушёл в late (отметка 21:30) → алерт есть; простой до 23:30 → алерт есть.
@pytest.mark.parametrize(
    "tg, mark, tick", [(9962, (21, 30), (22, 0, 30)), (9963, (15, 0), (23, 30, 30))]
)
def test_day2_alert_when_plus1h_late(db_engine, tg, mark, tick):
    pid, day2, z = _day2(db_engine, tg)
    _mark(db_engine, pid, day2, _at2(z, *mark))
    r = tick_ladder(db_engine, _at2(z, *tick))
    assert r.sent == 1 and r.late >= 1
    assert len(_outbox(db_engine, pid, EVENT_TYPE_DAY2)) == 1


# 11. Прошлый день silent; day_closed нет; ключ plus1h записан раньше → алерта нет.
def test_day2_no_alert_after_silent(db_engine):
    pid, day2, z = _day2(db_engine, 9964, came=False)
    _mark(db_engine, pid, day2, _at2(z, 15, 0))
    assert tick_ladder(db_engine, _at2(z, 16, 0, 30)).sent == 1
    assert _outbox(db_engine, pid, EVENT_TYPE_DAY2) == []
    assert not _has_key(db_engine, key_ladder_day2(pid, day2))


def test_day2_no_alert_without_day_closed(db_engine):
    pid, started, _tz, z = _open_day(db_engine, 9965)
    _mark(db_engine, pid, started, _u(datetime(2026, 10, 21, 15, 0, tzinfo=z)))
    assert tick_ladder(db_engine, _u(datetime(2026, 10, 21, 16, 0, 30, tzinfo=z))).sent == 1
    assert _outbox(db_engine, pid, EVENT_TYPE_DAY2) == []


def test_day2_no_alert_when_plus1h_key_earlier(db_engine):
    pid, day2, z = _day2(db_engine, 9966)
    _mark(db_engine, pid, day2, _at2(z, 15, 0))
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO idempotency_keys (key, kind, ttl) "
                "VALUES (:k, 'ladder', CAST('3650 days' AS interval))"
            ),
            {"k": key_ladder(pid, day2, "plus1h")},
        )
    assert tick_ladder(db_engine, _at2(z, 22, 0, 30)).sent == 1
    assert _outbox(db_engine, pid, EVENT_TYPE_DAY2) == []


# 12. Логи без pid; есть строка «ladder day2=».
def test_day2_logs_without_pid(db_engine, caplog):
    pid, day2, z = _day2(db_engine, 9967)
    _mark(db_engine, pid, day2, _at2(z, 15, 0))
    with caplog.at_level(logging.INFO):
        tick_ladder(db_engine, _at2(z, 16, 0, 30))
    assert any("ladder day2=" in rec.getMessage() for rec in caplog.records)
    assert str(pid) not in caplog.text
