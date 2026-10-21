"""Дополнения ШТАБа iter2-api-2b.

Д1 (ревью #101; с БД — только CI): гонка двух писателей одного pid. Первый писатель держит
замок participant:pid — его commit придержан (session.commit подменён на ожидание события);
второй стартует и ждёт замок (видно в pg_locks: advisory, granted = false); затем commit
первого отпускается. Итог согласован: одно событие, один ключ, отметки = последний писатель.
Д2 (без БД): TestClient, подменены require_init_data, rate_limit, get_settings и
get_db_session (сессия-шпион); флаг выкл. → POST /miniapp/v1/day/test-enter = 404,
у шпиона 0 обращений.
"""
import threading
import time
import uuid
from datetime import timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import day_clock
from app.config import Settings, get_settings
from app.day_content import get_day_content
from app.db.session import get_db_session
from app.projector import run_once
from app.rate_limit import rate_limit
from app.routers.day import (
    DayMarkIn,
    DayReportIn,
    enter_day_by_test_flag,
    put_day_mark,
    submit_day_report,
)
from app.routers.onboarding import register_with_consents
from app.telegram_init_data import InitDataContext, TelegramUser, require_init_data
from tests.conftest import FAKE_BOT_TOKEN, UNREACHABLE_DSN


# life-ops-b: «сейчас» — внутри окна дня из test-enter (ближайшая 04:00 + 1 ч, пояс по умолчанию).
_REAL_UTCNOW = day_clock.utcnow


@pytest.fixture(autouse=True)
def _inside_day_window(monkeypatch):
    now = day_clock.active_from(_REAL_UTCNOW(), day_clock.DEFAULT_TZ).astimezone(
        timezone.utc
    ) + timedelta(hours=1)
    monkeypatch.setattr(day_clock, "utcnow", lambda: now)
    return now

WAIT_SECONDS = 10
TEST_ENTER = "/miniapp/v1/day/test-enter"
_WAITERS_SQL = text("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted")


# ---------------------------- Д1: гонка писателей ----------------------------


def _call(fn, session):
    try:
        return fn(session)
    except Exception as exc:  # результат потока — значение или исключение
        return exc


def _wait_for_lock_waiter(engine) -> bool:
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        with engine.connect() as conn:
            if conn.execute(_WAITERS_SQL).scalar_one() > 0:
                return True
        time.sleep(0.05)
    return False


def _race(engine, first, second):
    """first(session): commit придержан, пока second(session) не ждёт замок.

    Возвращает (результат first, результат second, second ждал замок).
    """
    ready = threading.Event()
    release = threading.Event()
    out: dict[str, object] = {}

    def run_first():
        with Session(engine) as session:
            real_commit = session.commit

            def held_commit():
                ready.set()
                release.wait(WAIT_SECONDS)
                real_commit()

            session.commit = held_commit
            out["first"] = _call(first, session)

    def run_second():
        with Session(engine) as session:
            out["second"] = _call(second, session)

    t1 = threading.Thread(target=run_first)
    t2 = threading.Thread(target=run_second)
    t1.start()
    try:
        assert ready.wait(WAIT_SECONDS), "первый писатель не дошёл до commit"
        t2.start()
        waited = _wait_for_lock_waiter(engine)
    finally:
        release.set()
    t1.join(WAIT_SECONDS)
    if t2.is_alive() or t2.ident is not None:
        t2.join(WAIT_SECONDS)
    assert not t1.is_alive() and not t2.is_alive()
    return out["first"], out["second"], waited


def _registered(engine, tg_user_id: int):
    with Session(engine) as session:
        pid = register_with_consents(session, tg_user_id, ["C0", "C1"]).participant.pid
    run_once(engine)
    return pid


def _open_day(engine, tg_user_id: int):
    pid = _registered(engine, tg_user_id)
    with Session(engine) as session:
        enter_day_by_test_flag(session, tg_user_id, True)
    run_once(engine)
    return pid


def _block_ids() -> list[str]:
    return [block.block_id for block in get_day_content().get(1, 1, 1).blocks]


def _all(value: str) -> DayReportIn:
    return DayReportIn.model_validate(
        {"marks": [{"block_id": b, "value": value} for b in _block_ids()]}
    )


def _count(engine, sql: str, pid) -> int:
    with engine.connect() as conn:
        return conn.execute(text(sql), {"p": pid}).scalar_one()


def _marks(engine, pid) -> dict[str, bool]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT block_id, value FROM day_marks WHERE pid = :p"), {"p": pid}
        ).all()
    return {row.block_id: row.value for row in rows}


def _reports(engine, pid) -> int:
    return _count(
        engine,
        "SELECT count(*) FROM participant_events WHERE pid = :p AND kind = 'day_report_submitted'",
        pid,
    )


def test_race_test_enter_twice(db_engine):
    pid = _registered(db_engine, 9101)

    def enter(session):
        return enter_day_by_test_flag(session, 9101, True)

    first, second, waited = _race(db_engine, enter, enter)
    assert waited, "второй писатель не ждал замок participant:pid"
    assert first.status == "entering" and second.status == "entering"
    entered = _count(
        db_engine,
        "SELECT count(*) FROM participant_events WHERE pid = :p AND kind = 'day_entered'",
        pid,
    )
    keys = _count(
        db_engine,
        "SELECT count(*) FROM idempotency_keys WHERE key = 'day_enter:' || CAST(:p AS text)",
        pid,
    )
    assert (entered, keys) == (1, 1)


def test_race_submit_then_marks(db_engine):
    pid = _open_day(db_engine, 9102)
    blocks = _block_ids()

    def submit(session):
        return submit_day_report(session, 9102, uuid.uuid4(), _all("done"), get_day_content())

    def mark(session):
        body = DayMarkIn(block_id=blocks[0], value="not_done")
        return put_day_mark(session, 9102, body, get_day_content())

    first, second, waited = _race(db_engine, submit, mark)
    assert waited
    assert first.verdict == "passed"
    assert isinstance(second, HTTPException)
    assert (second.status_code, second.detail["code"]) == (409, "DAY_ALREADY_SUBMITTED")
    assert _marks(db_engine, pid) == {b: True for b in blocks}
    assert _reports(db_engine, pid) == 1


def test_race_marks_then_submit(db_engine):
    pid = _open_day(db_engine, 9103)
    blocks = _block_ids()

    def mark(session):
        body = DayMarkIn(block_id=blocks[0], value="not_done")
        return put_day_mark(session, 9103, body, get_day_content())

    def submit(session):
        return submit_day_report(session, 9103, uuid.uuid4(), _all("done"), get_day_content())

    first, second, waited = _race(db_engine, mark, submit)
    assert waited
    assert first.value == "not_done"
    assert second.verdict == "passed"
    assert _marks(db_engine, pid) == {b: True for b in blocks}  # отчёт записан после отметки
    assert _reports(db_engine, pid) == 1


# ---------------------- Д2: флаг выкл. → 0 обращений к БД ----------------------


class _SpySession:
    """Любое обращение к атрибуту записывается и падает: БД трогать нельзя."""

    def __init__(self) -> None:
        object.__setattr__(self, "calls", [])

    def __getattr__(self, name):
        self.calls.append(name)
        raise AssertionError(f"обращение к сессии БД: {name}")


@pytest.fixture
def spy_app():
    from main import app

    try:
        yield app
    finally:
        app.dependency_overrides.clear()


def _client(app, spy: _SpySession, enabled: bool):
    from fastapi.testclient import TestClient

    app.dependency_overrides[get_settings] = lambda: Settings(
        bot_token=FAKE_BOT_TOKEN, database_url=UNREACHABLE_DSN, day_test_entry_enabled=enabled
    )
    app.dependency_overrides[require_init_data] = lambda: InitDataContext(
        user=TelegramUser(id=4242), auth_date=int(time.time())
    )
    app.dependency_overrides[rate_limit] = lambda: None
    app.dependency_overrides[get_db_session] = lambda: spy
    return TestClient(app, raise_server_exceptions=False)


def test_flag_off_http_404_zero_db_calls(spy_app):
    spy = _SpySession()
    r = _client(spy_app, spy, enabled=False).post(TEST_ENTER)
    assert r.status_code == 404
    assert r.json()["code"] == "NOT_FOUND"
    assert spy.calls == []


def test_flag_on_spy_is_wired(spy_app):
    # Контроль: при включённом флаге обработчик обращается к сессии — шпион это видит.
    spy = _SpySession()
    r = _client(spy_app, spy, enabled=True).post(TEST_ENTER)
    assert r.status_code == 500
    assert spy.calls != []
