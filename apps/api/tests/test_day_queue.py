"""life-ops-b: позиция следующего дня в payload, ключ day_queue, очередь в GET /day/current
(карточка §9, У4, У7). «Сейчас» — monkeypatch app.day_clock.utcnow.

Без БД: next_position (passed → day_no + 1, последний день контента → та же позиция,
not_passed / all_not_done → та же). С БД — только CI: payload next_*, ключ day_queue по
next_day_started_at (= новый day_started_at после проектора), GET queued → open, поля
active_from / deadline_at у дня из test-enter.
"""
from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import day_clock
from app.day_content import get_day_content
from app.day_keys import dsa, key_day_queue
from app.projector import run_once
from app.routers.day import (
    DayReportIn,
    enter_day_by_test_flag,
    next_position,
    read_day_current,
    submit_day_report,
)
from app.routers.onboarding import register_with_consents
from app.telegram_init_data import INIT_DATA_HEADER
from tests.conftest import valid_init_data

URL = "/miniapp/v1/day/current"
SUBMIT = "/miniapp/v1/day/report/submit"
SANTIAGO = "America/Santiago"
SECOND = timedelta(seconds=1)
PASSED = {"task_1": "done", "task_2": "done", "task_3": "done", "task_4": "not_done"}
NOT_PASSED = {"task_1": "not_done", "task_2": "done", "task_3": "done", "task_4": "done"}
ALL_NOT_DONE = {b: "not_done" for b in PASSED}


def _u(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc)


def _set_now(monkeypatch, now: datetime) -> None:
    monkeypatch.setattr(day_clock, "utcnow", lambda: now)


# ================================ без БД ================================


def _row(day_no: int):
    return SimpleNamespace(stage_no=1, module_no=1, day_no=day_no)


@pytest.mark.parametrize(
    ("day_no", "result", "expected"),
    [
        (1, "passed", (1, 1, 2)),
        (2, "passed", (1, 1, 2)),  # последний день контента-заглушки → та же позиция
        (1, "not_passed", (1, 1, 1)),
        (1, "all_not_done", (1, 1, 1)),
    ],
)
def test_next_position(day_no, result, expected):
    content = get_day_content()
    assert content.get(1, 1, 3) is None  # заглушка: дней 1 и 2
    assert next_position(content, _row(day_no), result) == expected


# ================================= с БД =================================


def _open_day(engine, tg_user_id: int):
    with Session(engine) as session:
        pid = register_with_consents(session, tg_user_id, ["C0", "C1"]).participant.pid
    run_once(engine)
    with Session(engine) as session:
        enter_day_by_test_flag(session, tg_user_id, True)
    run_once(engine)
    return pid, *_state(engine, pid)


def _state(engine, pid):
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT day_started_at, tz, day_no FROM participant_state WHERE pid = :p"),
            {"p": pid},
        ).one()
    return row.day_started_at, row.tz, row.day_no


def _body(values: dict[str, str]) -> DayReportIn:
    return DayReportIn.model_validate(
        {"marks": [{"block_id": b, "value": v} for b, v in values.items()]}
    )


def _submit(engine, tg_user_id: int, values: dict[str, str]):
    with Session(engine) as session:
        return submit_day_report(session, tg_user_id, uuid.uuid4(), _body(values), get_day_content())


def _payload(engine, pid) -> dict:
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT payload FROM participant_events "
                "WHERE pid = :p AND kind = 'day_report_submitted' ORDER BY id DESC LIMIT 1"
            ),
            {"p": pid},
        ).scalar_one()


def _key_kind(engine, key: str):
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT kind FROM idempotency_keys WHERE key = :k"), {"k": key}
        ).scalar_one_or_none()


def _current(engine, tg_user_id: int):
    with Session(engine) as session:
        return read_day_current(session, tg_user_id, get_day_content(), False)


def _in_window(started: datetime, tz: str) -> datetime:
    return _u(day_clock.active_from(started, tz)) + timedelta(hours=2)


@pytest.mark.parametrize(
    ("tg_user_id", "values", "next_day_no"),
    [(9501, PASSED, 2), (9502, NOT_PASSED, 1), (9503, ALL_NOT_DONE, 1)],
)
def test_payload_next_and_queue_key(db_engine, monkeypatch, tg_user_id, values, next_day_no):
    pid, started, tz, _ = _open_day(db_engine, tg_user_id)
    now = _in_window(started, tz)
    _set_now(monkeypatch, now)
    _submit(db_engine, tg_user_id, values)
    payload = _payload(db_engine, pid)
    assert payload["day_started_at"] == dsa(started)
    assert (payload["next_stage_no"], payload["next_module_no"], payload["next_day_no"]) == (
        1,
        1,
        next_day_no,
    )
    assert payload["next_day_started_at"] == dsa(now)
    assert _key_kind(db_engine, key_day_queue(pid, now)) == "day_queue"
    # У4: после проектора ключ ищется по новому day_started_at.
    run_once(db_engine)
    new_started, _, day_no = _state(db_engine, pid)
    assert day_no == next_day_no
    assert dsa(new_started) == payload["next_day_started_at"]
    assert _key_kind(db_engine, key_day_queue(pid, new_started)) == "day_queue"


def test_passed_on_last_content_day_same_position(db_engine, monkeypatch):
    pid, started, tz, _ = _open_day(db_engine, 9504)
    now = _in_window(started, tz)
    _set_now(monkeypatch, now)
    _submit(db_engine, 9504, PASSED)
    run_once(db_engine)
    day2_started, tz, day_no = _state(db_engine, pid)
    assert day_no == 2
    now2 = _in_window(day2_started, tz)
    _set_now(monkeypatch, now2)
    day2 = get_day_content().get(1, 1, 2)
    _submit(db_engine, 9504, {b.block_id: "done" for b in day2.blocks})
    payload = _payload(db_engine, pid)
    assert (payload["next_stage_no"], payload["next_module_no"], payload["next_day_no"]) == (1, 1, 2)
    assert payload["next_day_started_at"] == dsa(now2)


def test_get_queued_then_open(db_engine, monkeypatch):
    pid, started, tz, _ = _open_day(db_engine, 9505)
    now = _in_window(started, tz)
    _set_now(monkeypatch, now)
    _submit(db_engine, 9505, PASSED)
    run_once(db_engine)
    new_started, tz, _ = _state(db_engine, pid)

    queued = _current(db_engine, 9505)
    assert queued.status == "queued"
    assert (queued.position, queued.blocks, queued.min_optional) == (None, None, None)
    assert (queued.can_submit, queued.buttons_active) == (False, False)
    delay = _u(queued.queued_until) - _u(now)
    assert timedelta(minutes=10) <= delay <= timedelta(minutes=60)
    assert str(queued.queued_until.tzinfo) == str(day_clock.zone(tz))  # пояс участника
    # active_from / deadline_at — нового дня; повтор GET не меняет queued_until.
    assert _u(queued.active_from) == _u(day_clock.active_from(new_started, tz))
    assert _u(queued.deadline_at) == _u(day_clock.deadline_at(new_started, tz))
    assert _u(_current(db_engine, 9505).queued_until) == _u(queued.queued_until)

    _set_now(monkeypatch, _u(queued.queued_until) + SECOND)
    shown = _current(db_engine, 9505)
    assert shown.status == "open"
    assert shown.buttons_active is False  # кнопки — с ближайшей 04:00
    assert shown.can_submit is False
    assert shown.queued_until is None
    assert shown.position.day_no == 2 and shown.blocks
    af = shown.active_from
    assert _u(af) > _u(now)
    # Н4: ровно ближайшая 04:00 по поясу участника после момента сдачи (сдача в 06:00 местного).
    zone = day_clock.zone(tz)
    nearest = datetime.combine(
        _u(now).astimezone(zone).date() + timedelta(days=1), time(4), tzinfo=zone
    )
    assert _u(af) == _u(nearest)


def test_get_fields_for_test_enter_day(db_engine, monkeypatch):
    pid, started, tz, _ = _open_day(db_engine, 9506)
    _set_now(monkeypatch, _u(started) + SECOND)  # сразу после test-enter (ЛО-2 А)
    current = _current(db_engine, 9506)
    zone = day_clock.zone(tz)
    assert current.status == "open"
    assert current.buttons_active is False and current.can_submit is False
    assert current.queued_until is None
    assert _u(current.active_from) == _u(day_clock.active_from(started, tz))
    assert _u(current.deadline_at) == _u(day_clock.deadline_at(started, tz))
    assert str(current.active_from.tzinfo) == str(zone)  # пояс участника
    assert str(current.deadline_at.tzinfo) == str(zone)
    assert current.active_from.astimezone(zone).time().isoformat() == "04:00:00"
    assert current.deadline_at.astimezone(zone).time().isoformat() == "00:00:00"
    assert _u(current.deadline_at) - _u(current.active_from) == timedelta(hours=20)


def test_get_http_fields_present(db_api_client, db_engine, monkeypatch):
    # HTTP: новые поля в ответе при позиции, queued_until явно null; ISO 8601 со сдвигом.
    r = db_api_client.post(
        "/miniapp/v1/onboarding/first-launch",
        json={"birth_date": "1990-01-01", "consents": ["C0", "C1"]},
        headers={INIT_DATA_HEADER: valid_init_data(user={"id": 9507, "first_name": "Test"})},
    )
    assert r.status_code == 201
    pid = uuid.UUID(r.json()["pid"])
    run_once(db_engine)
    with Session(db_engine) as session:
        enter_day_by_test_flag(session, 9507, True)
    run_once(db_engine)
    started, tz, _ = _state(db_engine, pid)
    _set_now(monkeypatch, _in_window(started, tz))
    body = db_api_client.get(
        URL, headers={INIT_DATA_HEADER: valid_init_data(user={"id": 9507, "first_name": "Test"})}
    ).json()
    assert body["status"] == "open"
    assert body["buttons_active"] is True
    assert "queued_until" in body and body["queued_until"] is None
    af = datetime.fromisoformat(body["active_from"])
    assert af.utcoffset() is not None and _u(af) == _u(day_clock.active_from(started, tz))
    assert datetime.fromisoformat(body["deadline_at"]).utcoffset() is not None


def test_http_submit_santiago_before_dst_jump(db_api_client, db_engine, monkeypatch):
    # Н4: пояс с переводом часов. Santiago 2026-09-06 00:00 −04:00 → 01:00 −03:00.
    # День начат 2026-09-05 03:00 местного, сдача 23:30 местного (окно open) → passed.
    with Session(db_engine) as session:
        pid = register_with_consents(session, 9508, ["C0", "C1"]).participant.pid
    run_once(db_engine)
    with Session(db_engine) as session:
        enter_day_by_test_flag(session, 9508, True)
    run_once(db_engine)
    zone = day_clock.zone(SANTIAGO)
    started = datetime(2026, 9, 5, 3, 0, tzinfo=zone)
    with db_engine.begin() as conn:  # тестовая подготовка состояния (не код приложения)
        conn.execute(
            text("UPDATE participant_state SET tz = :tz, day_started_at = :ts WHERE pid = :p"),
            {"tz": SANTIAGO, "ts": started, "p": pid},
        )
    now = _u(datetime(2026, 9, 5, 23, 30, tzinfo=zone))
    assert day_clock.window(started, SANTIAGO, now) == day_clock.WINDOW_OPEN
    _set_now(monkeypatch, now)
    headers = {INIT_DATA_HEADER: valid_init_data(user={"id": 9508, "first_name": "Test"})}
    r = db_api_client.post(
        SUBMIT,
        json={"marks": [{"block_id": b, "value": v} for b, v in PASSED.items()]},
        headers={**headers, "X-Client-Op-Id": str(uuid.uuid4())},
    )
    assert r.status_code == 200
    assert r.json() == {"verdict": "passed", "queued": True}
    run_once(db_engine)
    next_started, tz, day_no = _state(db_engine, pid)
    assert (tz, day_no) == (SANTIAGO, 2)

    r = db_api_client.get(URL, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "queued"
    af = datetime.fromisoformat(body["active_from"])
    assert _u(af) == _u(day_clock.active_from(next_started, SANTIAGO))
    assert _u(af) > now
    assert _u(af) == datetime(2026, 9, 6, 7, 0, tzinfo=timezone.utc)  # 04:00 −03:00
    delay = _u(datetime.fromisoformat(body["queued_until"])) - now
    assert timedelta(minutes=10) <= delay <= timedelta(minutes=60)
