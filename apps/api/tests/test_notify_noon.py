"""Полуденное НП1 (noon-1): чистые функции, tick_noon, tick с двумя правилами. С БД — только CI.

now — аргументом tick, от фиксированного day_started_at (реальное время запуска не влияет).
Тестовое состояние и отметки day_marks готовятся владельцем БД — только в тесте.
outbox и idempotency_keys фикстура db_engine не чистит — проверки по pid.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import day_clock, notify_ops
from app.day_keys import TTL_BY_KIND, key_day_done, key_noon
from app.notify_ops import (
    TEXT_NOON,
    decide_noon,
    is_13p,
    noon_local_date,
    noon_window,
    tick_noon,
)
from app.projector import run_once
from app.routers.day import enter_day_by_test_flag
from app.routers.onboarding import register_with_consents

MSK = ZoneInfo("Europe/Moscow")
VVO = ZoneInfo("Asia/Vladivostok")
PID = uuid.UUID("11111111-2222-3333-4444-555555555555")
DAY_JSON = Path(__file__).resolve().parents[1] / "config" / "texts" / "day.json"


def _u(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc)


# ------------------------------ без БД ------------------------------


# 1. noon_window: 11:59 нет; 12:00 и 17:59 да; 18:00 нет; тот же момент в UTC — тот же ответ.
@pytest.mark.parametrize("tz_name, z", [("Europe/Moscow", MSK), ("Asia/Vladivostok", VVO)])
def test_noon_window(tz_name, z):
    day = (2026, 10, 21)
    cases = [((11, 59), False), ((12, 0), True), ((17, 59), True), ((18, 0), False)]
    for (h, m), expected in cases:
        local = datetime(*day, h, m, tzinfo=z)
        assert noon_window(local, tz_name) is expected
        assert noon_window(_u(local), tz_name) is expected
    assert noon_local_date(_u(datetime(*day, 12, 0, tzinfo=z)), tz_name) == date(*day)


# 2. decide_noon.
def test_decide_noon_gates():
    tz = "Europe/Moscow"
    started = datetime(2026, 10, 21, 0, 0, tzinfo=MSK)  # открыт 04:00 21.10 — 00:00 22.10
    now = datetime(2026, 10, 21, 12, 30, tzinfo=MSK)
    assert decide_noon(now, tz, started, 1, 5, False, False, False) == "send"
    assert decide_noon(now, tz, started, 1, 5, True, False, False) is None
    assert decide_noon(now, tz, started, 1, 5, False, True, False) is None
    assert decide_noon(now, tz, started, 1, 5, False, False, True) is None
    # Сдача утром: started сегодня 10:00 → active_from завтра 04:00, now 12:30 → не активен.
    morning = datetime(2026, 10, 21, 10, 0, tzinfo=MSK)
    assert day_clock.active_from(morning, tz) == datetime(2026, 10, 22, 4, 0, tzinfo=MSK)
    assert decide_noon(now, tz, morning, 1, 5, False, False, False) is None
    # Окно closed: день позавчерашний.
    old = datetime(2026, 10, 19, 0, 0, tzinfo=MSK)
    assert day_clock.window(old, tz, now) == day_clock.WINDOW_CLOSED
    assert decide_noon(now, tz, old, 1, 5, False, False, False) is None
    # 13-P.
    assert decide_noon(now, tz, started, 2, 13, False, False, False) is None


# 3. is_13p.
def test_is_13p():
    assert is_13p(2, 13) is True
    assert is_13p(1, 13) is False
    assert is_13p(2, 12) is False
    assert is_13p(3, 13) is False


# 4. key_noon и TTL.
def test_key_noon_format_and_ttl():
    assert key_noon(PID, date(2026, 10, 21)) == f"noon:{PID}:2026-10-21"
    # Местная дата: 23:30 UTC 20.10 = 02:30 МСК 21.10 и 09:30 Владивосток 21.10.
    late_utc = datetime(2026, 10, 20, 23, 30, tzinfo=timezone.utc)
    assert key_noon(PID, noon_local_date(late_utc, "Europe/Moscow")) == f"noon:{PID}:2026-10-21"
    assert key_noon(PID, noon_local_date(late_utc, "UTC")) == f"noon:{PID}:2026-10-20"
    assert TTL_BY_KIND["noon"] == "3650 days"


# 5. Статика: TEXT_NOON есть в day.json (версию не сверяем — её поднимет ladder-1).
def test_static_text_noon_in_day_json():
    data = json.loads(DAY_JSON.read_text(encoding="utf-8"))
    keys = {e["key"] for e in data["entries"]}
    assert TEXT_NOON in keys


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


def _mark(engine, pid: uuid.UUID, ts: datetime, block_id: str = "task_1") -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO day_marks (pid, day_started_at, block_id, value) "
                "VALUES (:pid, :ts, :b, :v)"
            ),
            {"pid": pid, "ts": ts, "b": block_id, "v": True},
        )


def _outbox(engine, pid) -> list:
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT event_type, payload, tx_id FROM outbox "
                "WHERE aggregate_id::text = :a ORDER BY id"
            ),
            {"a": str(pid)},
        ).all()


def _noon_keys(engine, pid) -> list[str]:
    with engine.connect() as conn:
        return list(
            conn.execute(
                text("SELECT key FROM idempotency_keys WHERE key LIKE :k"),
                {"k": f"noon:{pid}:%"},
            ).scalars()
        )


def _payload(raw) -> dict:
    return raw if isinstance(raw, dict) else json.loads(raw)


# 6. 12:00:30 местного, без отметок → 1 outbox и ключ; второй tick → 0.
def test_noon_sent_once(db_engine):
    pid, _started, _tz, z = _open_day(db_engine, 9901)
    now = _u(datetime(2026, 10, 21, 12, 0, 30, tzinfo=z))
    assert tick_noon(db_engine, now).sent == 1
    assert _noon_keys(db_engine, pid) == [key_noon(pid, date(2026, 10, 21))]
    rows = _outbox(db_engine, pid)
    assert len(rows) == 1
    assert rows[0].event_type == "noon_nudge"
    assert _payload(rows[0].payload) == {"text_id": TEXT_NOON, "payload_vars": {}, "tier": "T3"}
    assert rows[0].tx_id is not None
    assert tick_noon(db_engine, now + timedelta(seconds=30)).sent == 0
    assert len(_outbox(db_engine, pid)) == 1


# 7. Отметка за текущий day_started_at → 0; отметка за старый не мешает → 1.
def test_noon_marks_current_vs_old(db_engine):
    pid_a, started_a, _tz, z = _open_day(db_engine, 9902)
    _mark(db_engine, pid_a, started_a)
    pid_b, started_b, _tz_b, _z_b = _open_day(db_engine, 9903)
    _mark(db_engine, pid_b, started_b - timedelta(days=1))
    now = _u(datetime(2026, 10, 21, 12, 0, 30, tzinfo=z))
    tick_noon(db_engine, now)
    assert _noon_keys(db_engine, pid_a) == []
    assert _outbox(db_engine, pid_a) == []
    assert _noon_keys(db_engine, pid_b) == [key_noon(pid_b, date(2026, 10, 21))]
    assert len(_outbox(db_engine, pid_b)) == 1


# 8. Ключ day_done → 0. 18:00 → 0, ключа нет; догон 17:59 → 1.
def test_noon_day_done_and_until(db_engine):
    pid_done, started_done, _tz, z = _open_day(db_engine, 9904)
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO idempotency_keys (key, kind, ttl) "
                "VALUES (:k, 'day_done', CAST('3650 days' AS interval))"
            ),
            {"k": key_day_done(pid_done, started_done)},
        )
    noon = _u(datetime(2026, 10, 21, 12, 0, 30, tzinfo=z))
    assert tick_noon(db_engine, noon).sent == 0
    assert _noon_keys(db_engine, pid_done) == []
    assert _outbox(db_engine, pid_done) == []
    pid, _started, _tz2, z2 = _open_day(db_engine, 9905)
    assert tick_noon(db_engine, _u(datetime(2026, 10, 21, 18, 0, tzinfo=z2))).sent == 0
    assert _noon_keys(db_engine, pid) == []
    assert _outbox(db_engine, pid) == []
    assert tick_noon(db_engine, _u(datetime(2026, 10, 21, 17, 59, tzinfo=z2))).sent == 1
    assert _noon_keys(db_engine, pid) == [key_noon(pid, date(2026, 10, 21))]
    assert len(_outbox(db_engine, pid)) == 1


# 9. Фильтры: пауза, block_lives, sleeping, событие после checkpoint.
@pytest.mark.parametrize(
    "tg, case", [(9906, "pause"), (9907, "block_lives"), (9908, "sleeping"), (9909, "pending")]
)
def test_noon_filters_nothing_written(db_engine, tg, case):
    pid, _started, _tz, z = _open_day(db_engine, tg)
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
    result = tick_noon(db_engine, _u(datetime(2026, 10, 21, 12, 0, 30, tzinfo=z)))
    assert result.sent == 0
    assert _noon_keys(db_engine, pid) == []
    assert _outbox(db_engine, pid) == []


# 10. tick: правило tasks_open падает → WARNING, полуденное всё равно отправлено.
def test_tick_rule_failure_isolated(db_engine, monkeypatch, caplog):
    pid, _started, _tz, z = _open_day(db_engine, 9910)

    def broken(engine, now):
        raise RuntimeError("boom")

    monkeypatch.setattr(notify_ops, "tick_tasks_open", broken)
    now = _u(datetime(2026, 10, 21, 12, 0, 30, tzinfo=z))
    with caplog.at_level(logging.WARNING, logger="app.notify_ops"):
        r = notify_ops.tick(db_engine, now)
    assert r.noon.sent == 1
    assert r.tasks_open.sent == 0
    messages = [rec.getMessage() for rec in caplog.records if rec.name == "app.notify_ops"]
    assert any("rule tasks_open failed (RuntimeError)" in m for m in messages)
    assert len(_outbox(db_engine, pid)) == 1
