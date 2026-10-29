"""life-ops-b: окно дня 04:00–00:00 на PUT /day/marks и POST /day/report/submit (карточка §9, У3, У5).

«Сейчас» — monkeypatch app.day_clock.utcnow. Без БД: 409-ошибки окна и правило next_day_started
(У3). С БД — только CI: до 04:00 → 409 DAY_NOT_ACTIVE; в 04:00:00 → 200; 23:59:59 и ровно 00:00:00
→ 200; 00:00:01 → 409 DAY_CLOSED; повтор того же op_id после 00:00 → тот же 200; после 409 ничего
не записано; гонка на 00:00 — «сейчас» берётся после замка; GET closed; GET submitted внутри
открытого окна — buttons_active и can_submit false (Р1).
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import day_clock
from app.day_content import get_day_content
from app.day_keys import dsa, key_day_done
from app.projector import run_once
from app.routers.day import (
    DayMarkIn,
    DayReportIn,
    _window_error,
    enter_day_by_test_flag,
    next_day_started,
    put_day_mark,
    read_day_current,
    submit_day_report,
)
from app.routers.onboarding import register_with_consents
from tests.conftest import wait_for_lock_waiter

MSK = "Europe/Moscow"
SECOND = timedelta(seconds=1)
WAIT_SECONDS = 10


def _set_now(monkeypatch, now: datetime) -> None:
    monkeypatch.setattr(day_clock, "utcnow", lambda: now)


def _u(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc)


# ================================ без БД ================================


def test_window_errors_format():
    not_active = _window_error(day_clock.WINDOW_NOT_ACTIVE)
    closed = _window_error(day_clock.WINDOW_CLOSED)
    assert (not_active.status_code, not_active.detail) == (
        409,
        {"code": "DAY_NOT_ACTIVE", "message": "Кнопки дня станут активны в 04:00."},
    )
    assert (closed.status_code, closed.detail) == (
        409,
        {"code": "DAY_CLOSED", "message": "День закрыт: отчёт принимался до 00:00."},
    )
    assert _window_error(day_clock.WINDOW_OPEN) is None


def test_next_started_exactly_at_0400_shifted_by_microsecond():
    # У3 (а): сдача ровно в 04:00:00.000000 → кнопки следующего дня — 04:00 следующих суток.
    now = datetime(2026, 10, 20, 1, 0, tzinfo=timezone.utc)  # 04:00 МСК
    nxt = next_day_started(now, MSK)
    assert nxt == now + timedelta(microseconds=1)
    af = day_clock.active_from(nxt, MSK)
    assert _u(af) > _u(now)
    assert af.isoformat() == "2026-10-21T04:00:00+03:00"


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 10, 20, 20, 59, 59, tzinfo=timezone.utc),  # 23:59:59 МСК
        datetime(2026, 10, 20, 21, 0, tzinfo=timezone.utc),  # 00:00:00 МСК
    ],
)
def test_next_started_late_evening_is_now(now):
    # У3 (б): active_from(next) — ближайшая 04:00, строго позже сдачи.
    nxt = next_day_started(now, MSK)
    assert nxt == now
    af = day_clock.active_from(nxt, MSK)
    assert _u(af) > _u(now)
    assert af.isoformat() == "2026-10-21T04:00:00+03:00"


def test_next_started_empty_tz_falls_back_to_default():
    now = datetime(2026, 10, 20, 1, 0, tzinfo=timezone.utc)
    assert next_day_started(now, "") == now + timedelta(microseconds=1)


# ================================= с БД =================================


def _open_day(engine, tg_user_id: int):
    with Session(engine) as session:
        pid = register_with_consents(session, tg_user_id, ["C0", "C1"]).participant.pid
    run_once(engine)
    with Session(engine) as session:
        enter_day_by_test_flag(session, tg_user_id, True)
    run_once(engine)
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT day_started_at, tz FROM participant_state WHERE pid = :p"), {"p": pid}
        ).one()
    return pid, row.day_started_at, row.tz


def _block_ids() -> list[str]:
    return [block.block_id for block in get_day_content().get(1, 1, 1).blocks]


def _report(value: str = "done") -> DayReportIn:
    return DayReportIn.model_validate(
        {"marks": [{"block_id": b, "value": value} for b in _block_ids()]}
    )


def _submit(engine, tg_user_id: int, op_id, body: DayReportIn):
    with Session(engine) as session:
        return submit_day_report(session, tg_user_id, op_id, body, get_day_content())


def _mark(engine, tg_user_id: int, value: str = "done"):
    with Session(engine) as session:
        body = DayMarkIn(block_id=_block_ids()[0], value=value)
        return put_day_mark(session, tg_user_id, body, get_day_content())


def _http_error(fn, *args) -> HTTPException:
    with pytest.raises(HTTPException) as exc:
        fn(*args)
    return exc.value


def _snapshot(engine, pid):
    """Состояние, события, ключи и отметки pid — для проверки «после 409 ничего не изменилось»."""
    with engine.connect() as conn:
        state = conn.execute(
            text(
                "SELECT stage_no, module_no, day_no, day_started_at, lives, missed_streak "
                "FROM participant_state WHERE pid = :p"
            ),
            {"p": pid},
        ).one()
        events = conn.execute(
            text("SELECT count(*) FROM participant_events WHERE pid = :p"), {"p": pid}
        ).scalar_one()
        keys = conn.execute(
            text("SELECT count(*) FROM idempotency_keys WHERE key LIKE :k"),
            {"k": f"%:{pid}%"},
        ).scalar_one()
        marks = conn.execute(
            text("SELECT count(*) FROM day_marks WHERE pid = :p"), {"p": pid}
        ).scalar_one()
    return tuple(state), events, keys, marks


def _reports(engine, pid) -> int:
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT count(*) FROM participant_events "
                "WHERE pid = :p AND kind = 'day_report_submitted'"
            ),
            {"p": pid},
        ).scalar_one()


def _has_key(engine, key: str) -> bool:
    with engine.connect() as conn:
        found = conn.execute(
            text("SELECT 1 FROM idempotency_keys WHERE key = :k"), {"k": key}
        ).first()
    return found is not None


def test_before_0400_marks_and_submit_409_not_active(db_engine, monkeypatch):
    pid, started, tz = _open_day(db_engine, 9401)
    _set_now(monkeypatch, day_clock.active_from(started, tz) - SECOND)
    before = _snapshot(db_engine, pid)
    err = _http_error(_mark, db_engine, 9401)
    assert (err.status_code, err.detail["code"]) == (409, "DAY_NOT_ACTIVE")
    err = _http_error(_submit, db_engine, 9401, uuid.uuid4(), _report())
    assert (err.status_code, err.detail["code"]) == (409, "DAY_NOT_ACTIVE")
    assert _snapshot(db_engine, pid) == before


def test_at_0400_marks_and_submit_200(db_engine, monkeypatch):
    pid, started, tz = _open_day(db_engine, 9402)
    now = day_clock.active_from(started, tz)
    _set_now(monkeypatch, now)
    assert _mark(db_engine, 9402).value == "done"
    assert _submit(db_engine, 9402, uuid.uuid4(), _report()).verdict == "passed"
    run_once(db_engine)
    with db_engine.connect() as conn:
        next_started = conn.execute(
            text("SELECT day_started_at FROM participant_state WHERE pid = :p"), {"p": pid}
        ).scalar_one()
    # У3 (а): кнопки следующего дня — 04:00 следующих суток по поясу, строго позже сдачи.
    af = day_clock.active_from(next_started, tz)
    assert _u(af) > _u(now)
    assert _u(af) == _u(now) + timedelta(days=1)
    assert af.astimezone(day_clock.zone(tz)).time().isoformat() == "04:00:00"


@pytest.mark.parametrize(("tg_user_id", "offset"), [(9403, -SECOND), (9404, timedelta(0))])
def test_submit_until_midnight_200_and_written(db_engine, monkeypatch, tg_user_id, offset):
    pid, started, tz = _open_day(db_engine, tg_user_id)
    now = day_clock.deadline_at(started, tz) + offset  # 23:59:59 и ровно 00:00:00
    _set_now(monkeypatch, now)
    assert _submit(db_engine, tg_user_id, uuid.uuid4(), _report()).verdict == "passed"
    # П-31: ответ 200 = запись есть.
    assert _has_key(db_engine, key_day_done(pid, started))
    assert _reports(db_engine, pid) == 1
    run_once(db_engine)
    with db_engine.connect() as conn:
        next_started = conn.execute(
            text("SELECT day_started_at FROM participant_state WHERE pid = :p"), {"p": pid}
        ).scalar_one()
    # У3 (б): active_from(next) — ближайшая 04:00 по поясу, строго позже сдачи.
    af = day_clock.active_from(next_started, tz)
    assert _u(af) > _u(now)
    assert _u(af) - _u(now) <= timedelta(hours=4, seconds=1)
    assert af.astimezone(day_clock.zone(tz)).time().isoformat() == "04:00:00"


def test_after_midnight_marks_and_submit_409_closed(db_engine, monkeypatch):
    pid, started, tz = _open_day(db_engine, 9405)
    _set_now(monkeypatch, day_clock.deadline_at(started, tz) + SECOND)  # 00:00:01
    before = _snapshot(db_engine, pid)
    err = _http_error(_mark, db_engine, 9405)
    assert (err.status_code, err.detail["code"]) == (409, "DAY_CLOSED")
    err = _http_error(_submit, db_engine, 9405, uuid.uuid4(), _report())
    assert (err.status_code, err.detail["code"]) == (409, "DAY_CLOSED")
    assert _snapshot(db_engine, pid) == before


def test_repeat_same_op_id_after_midnight_same_200(db_engine, monkeypatch):
    pid, started, tz = _open_day(db_engine, 9406)
    op_id = uuid.uuid4()
    _set_now(monkeypatch, day_clock.deadline_at(started, tz) - SECOND)
    first = _submit(db_engine, 9406, op_id, _report())
    _set_now(monkeypatch, day_clock.deadline_at(started, tz) + timedelta(minutes=5))
    before = _snapshot(db_engine, pid)
    assert _submit(db_engine, 9406, op_id, _report()) == first  # повтор — раньше окна
    err = _http_error(_submit, db_engine, 9406, op_id, _report("not_done"))
    assert (err.status_code, err.detail["code"]) == (409, "IDEMPOTENCY_CONFLICT")
    assert _snapshot(db_engine, pid) == before
    assert _reports(db_engine, pid) == 1


def test_race_on_midnight_now_taken_after_lock(db_engine, monkeypatch):
    """Первый отчёт берёт «сейчас» = 00:00:00 и держит замок; второй ждёт замок, а его
    «сейчас» (00:00:01) берётся уже после замка → 409 DAY_CLOSED, событие одно."""
    pid, started, tz = _open_day(db_engine, 9407)
    deadline = day_clock.deadline_at(started, tz)
    calls: list[datetime] = []
    guard = threading.Lock()

    def fake_now():
        with guard:
            calls.append(deadline if not calls else deadline + SECOND)
            return calls[-1]

    monkeypatch.setattr(day_clock, "utcnow", fake_now)
    ready = threading.Event()
    release = threading.Event()
    out: dict[str, object] = {}
    holder: dict[str, int] = {}

    def run(name: str, hold: bool):
        with Session(db_engine) as session:
            if hold:
                real_commit = session.commit

                def held_commit():
                    holder["pid"] = session.execute(text("SELECT pg_backend_pid()")).scalar_one()
                    ready.set()
                    release.wait(WAIT_SECONDS)
                    real_commit()

                session.commit = held_commit
            try:
                out[name] = submit_day_report(
                    session, 9407, uuid.uuid4(), _report(), get_day_content()
                )
            except Exception as exc:  # результат потока — значение или исключение
                out[name] = exc

    t1 = threading.Thread(target=run, args=("first", True))
    t2 = threading.Thread(target=run, args=("second", False))
    t1.start()
    try:
        assert ready.wait(WAIT_SECONDS)
        t2.start()
        assert wait_for_lock_waiter(db_engine, holder["pid"])  # второй ждёт замок participant:pid
        assert len(calls) == 1  # «сейчас» второго ещё не взято: он ждёт замок
    finally:
        release.set()
    t1.join(WAIT_SECONDS)
    t2.join(WAIT_SECONDS)
    assert out["first"].verdict == "passed"
    second = out["second"]
    assert isinstance(second, HTTPException)
    assert (second.status_code, second.detail["code"]) == (409, "DAY_CLOSED")
    assert _reports(db_engine, pid) == 1


def test_get_closed_after_midnight(db_engine, monkeypatch):
    pid, started, tz = _open_day(db_engine, 9408)
    _set_now(monkeypatch, day_clock.deadline_at(started, tz) + SECOND)
    with Session(db_engine) as session:
        current = read_day_current(session, 9408, get_day_content(), False)
    assert current.status == "closed"
    assert current.buttons_active is False
    assert current.can_submit is False
    assert current.queued_until is None
    assert current.blocks and current.position is not None
    assert dsa(current.day_started_at) == dsa(started)


def test_get_submitted_inside_open_window_buttons_inactive(db_engine, monkeypatch):
    # Р1: после сдачи marks отвечает 409 DAY_ALREADY_SUBMITTED → кнопки неактивны и в окне open.
    pid, started, tz = _open_day(db_engine, 9409)
    now = _u(day_clock.active_from(started, tz)) + timedelta(hours=1)
    _set_now(monkeypatch, now)
    assert day_clock.window(started, tz, now) == day_clock.WINDOW_OPEN
    with db_engine.begin() as conn:  # ключ day_done есть, проектор день ещё не сдвинул
        conn.execute(
            text(
                "INSERT INTO idempotency_keys (key, kind, ttl, result_ref) "
                "VALUES (:k, 'day_done', CAST('3650 days' AS interval), 'passed')"
            ),
            {"k": key_day_done(pid, started)},
        )
    with Session(db_engine) as session:
        current = read_day_current(session, 9409, get_day_content(), False)
    assert current.status == "submitted"
    assert current.buttons_active is False
    assert current.can_submit is False
    assert current.queued_until is None
