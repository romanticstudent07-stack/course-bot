"""Перевыдача дня с 00:00 (api-sleep-1b): «будущий» день после restart_paid. С БД — только CI.

Сначала событие restart_paid проводит проектор (D = next_midnight(at, tz)); затем «часы» с
now аргументом. До 04:00 даты D окно not_active: нет закрытия дня, НП1 и лестницы; НП3 —
третий запуск, текст по дате. Тестовое состояние готовит владелец БД — только в тесте; позиция
задана целиком, lives 0..3. outbox и idempotency_keys фикстура не чистит — проверки по pid.
"""
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import day_clock, life_ops, notify_ladder, notify_ops
from app.day_keys import key_tasks_open
from app.projector import EVENT_KIND_RESTART_PAID, ProjectorResult, run_once
from app.routers.day import enter_day_by_test_flag
from app.routers.onboarding import register_with_consents

TZ = "Europe/Moscow"
MSK = ZoneInfo(TZ)
OLD_STARTED = datetime(2026, 11, 1, 0, 0, tzinfo=MSK)


def _msk(day: int, h: int, m: int) -> datetime:
    return datetime(2026, 11, day, h, m, tzinfo=MSK)


def _u(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc)


# ---------------------------------- без БД ----------------------------------


# F7: choose_text_reissue и is_reissue на случаях F4–F6.
def test_f7_choose_text_reissue_and_is_reissue():
    cases = [
        (_msk(20, 10, 0), _msk(20, 10, 5), notify_ops.TEXT_TOMORROW),  # F4
        (_msk(20, 1, 0), _msk(20, 1, 5), notify_ops.TEXT_TOMORROW),  # F5
        (_msk(20, 23, 58), _msk(21, 0, 1), notify_ops.TEXT_TODAY),  # F6
    ]
    for at, now, expected in cases:
        started = day_clock.next_midnight(at, TZ)
        assert notify_ops.choose_text_reissue(started, TZ, now) == expected
        assert notify_ops.is_reissue(started, TZ, [at]) is True
    assert notify_ops.choose_text(_msk(20, 1, 5), TZ) == notify_ops.TEXT_TODAY  # F5: старый текст
    started = day_clock.next_midnight(_msk(20, 10, 0), TZ)
    assert notify_ops.is_reissue(started, TZ, [_msk(21, 10, 0)]) is False
    assert notify_ops.is_reissue(started, TZ, []) is False


# ---------------------------------- с БД ----------------------------------


def _restarted(engine, tg_user_id: int, at: datetime) -> tuple:
    """block_lives → restart_paid в at → проектор. Возвращает (pid, D)."""
    with Session(engine) as session:
        pid = register_with_consents(session, tg_user_id, ["C0", "C1"]).participant.pid
    run_once(engine)
    with Session(engine) as session:
        enter_day_by_test_flag(session, tg_user_id, True)
    run_once(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE participant_state SET lives = 0, status_flags = CAST('{block_lives}' "
                "AS text[]), lifecycle_phase = 'sleeping', stage_no = 1, module_no = 2, "
                "day_no = 4, day_started_at = :s, missed_streak = 1, tz = :tz WHERE pid = :p"
            ),
            {"p": pid, "s": OLD_STARTED, "tz": TZ},
        )
        conn.execute(
            text(
                "INSERT INTO participant_events (pid, kind, payload, actor, actor_role, at) "
                "VALUES (:p, :k, CAST(:pl AS jsonb), 'system', 'system', :at)"
            ),
            {"p": pid, "k": EVENT_KIND_RESTART_PAID, "pl": json.dumps({}), "at": at},
        )
    assert run_once(engine) == ProjectorResult(processed=1, skipped=0)
    started = day_clock.next_midnight(at, TZ)
    with engine.connect() as conn:
        actual = conn.execute(
            text("SELECT day_started_at FROM participant_state WHERE pid = :p"), {"p": pid}
        ).scalar_one()
    assert _u(actual) == _u(started)
    return pid, started


def _outbox(engine, pid, event_type: str) -> list:
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT payload FROM outbox WHERE aggregate_id::text = :a "
                "AND event_type = :t ORDER BY id"
            ),
            {"a": str(pid), "t": event_type},
        ).all()


def _keys(engine, pattern: str) -> list:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT key FROM idempotency_keys WHERE key LIKE :k"), {"k": pattern}
        ).all()


def _text_id(payload) -> str:
    data = payload if isinstance(payload, dict) else json.loads(payload)
    return data["text_id"]


# F1: часы не закрывают день до D и до 04:00 даты D.
def test_f1_life_ops_no_close(db_engine):
    at = _msk(20, 9, 0)
    pid, started = _restarted(db_engine, 4651, at)
    for now in (_msk(20, 20, 0), _msk(21, 2, 0)):
        assert _u(at) < _u(now) < _u(day_clock.active_from(started, TZ))
        life_ops.tick(db_engine, _u(now))
    with db_engine.connect() as conn:
        count = conn.execute(
            text(
                "SELECT count(*) FROM participant_events WHERE pid = :p "
                "AND kind IN ('day_closed', 'life_op')"
            ),
            {"p": pid},
        ).scalar_one()
    assert count == 0
    assert _keys(db_engine, f"day_close:{pid}:%") == []


# F2: НП1 в день рестарта (12:30) не уходит.
def test_f2_no_noon(db_engine):
    pid, _started = _restarted(db_engine, 4652, _msk(20, 9, 0))
    notify_ops.tick_noon(db_engine, _u(_msk(20, 12, 30)))
    assert _outbox(db_engine, pid, notify_ops.NOON_EVENT_TYPE) == []


# F3: лестница с отметкой на D в тот же now не уходит.
def test_f3_no_ladder(db_engine):
    pid, started = _restarted(db_engine, 4653, _msk(20, 9, 0))
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO day_marks (pid, day_started_at, block_id, value, at) "
                "VALUES (:pid, :ts, :b, :v, :at)"
            ),
            {"pid": pid, "ts": started, "b": "task_1", "v": True, "at": _msk(20, 12, 0)},
        )
    notify_ladder.tick_ladder(db_engine, _u(_msk(20, 12, 30)))
    assert _outbox(db_engine, pid, "ladder_reminder") == []


# F4: рестарт в 10:00, tick через 5 мин → «завтра»; повтор — 0 (ключ).
def test_f4_tasks_open_tomorrow(db_engine):
    at = _msk(20, 10, 0)
    pid, started = _restarted(db_engine, 4654, at)
    now = at + timedelta(minutes=5)
    assert notify_ops.tick_tasks_open(db_engine, _u(now)).sent == 1
    rows = _outbox(db_engine, pid, notify_ops.EVENT_TYPE)
    assert len(rows) == 1
    assert _text_id(rows[0].payload) == notify_ops.TEXT_TOMORROW
    assert _keys(db_engine, key_tasks_open(pid, started)) != []
    assert notify_ops.tick_tasks_open(db_engine, _u(now + timedelta(minutes=1))).sent == 0
    assert len(_outbox(db_engine, pid, notify_ops.EVENT_TYPE)) == 1


# F5: рестарт в 01:00 → «завтра» (choose_text дал бы «сегодня»).
def test_f5_tasks_open_after_1am(db_engine):
    at = _msk(20, 1, 0)
    pid, _started = _restarted(db_engine, 4655, at)
    assert notify_ops.tick_tasks_open(db_engine, _u(at + timedelta(minutes=5))).sent == 1
    rows = _outbox(db_engine, pid, notify_ops.EVENT_TYPE)
    assert len(rows) == 1
    assert _text_id(rows[0].payload) == notify_ops.TEXT_TOMORROW


# F6: рестарт в 23:58, tick в 00:01 → «сегодня».
def test_f6_tasks_open_today(db_engine):
    pid, _started = _restarted(db_engine, 4656, _msk(20, 23, 58))
    assert notify_ops.tick_tasks_open(db_engine, _u(_msk(21, 0, 1))).sent == 1
    rows = _outbox(db_engine, pid, notify_ops.EVENT_TYPE)
    assert len(rows) == 1
    assert _text_id(rows[0].payload) == notify_ops.TEXT_TODAY


# F6: tick после 04:00 даты D без прошлого НП3 → late: ключ есть, outbox нет.
def test_f6_tasks_open_late(db_engine):
    pid, started = _restarted(db_engine, 4657, _msk(20, 23, 58))
    result = notify_ops.tick_tasks_open(db_engine, _u(_msk(21, 5, 0)))
    assert (result.sent, result.late) == (0, 1)
    assert _keys(db_engine, key_tasks_open(pid, started)) != []
    assert _outbox(db_engine, pid, notify_ops.EVENT_TYPE) == []
