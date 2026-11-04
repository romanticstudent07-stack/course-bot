"""api-refl-1: рефлексия в отчёте дня — поле reflection, лог reflections_log, outbox
reflection_submitted, reflection_required в GET /day/current (карточка §9, пункты 1–13).

Без БД: валидация модели (2001 символ, NUL), 422 VALIDATION_ERROR через TestClient,
params_hash (Т5), DayCurrentOut без позиции не несёт reflection_required (Т8).
С БД (только CI): позиция «день 6» / «день 1» — строка participant_state владельцем БД
(как _state в test_day_current.py; проектор не запускается), «сейчас» — monkeypatch
day_clock.utcnow внутри окна. Тест 13 — права app_api (role_engine, как test_db_roles_0011).
tg_user_id — 4701–4799.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import day_clock
from app.day_content import get_day_content
from app.day_report import params_hash
from app.rate_limit import rate_limit
from app.routers.day import (
    _INSERT_REFLECTION,
    _INSERT_REFLECTION_OUTBOX,
    DayCurrentOut,
    DayReportIn,
    post_day_report_submit,
    read_day_current,
    submit_day_report,
)
from app.routers.onboarding import register_with_consents
from app.telegram_init_data import INIT_DATA_HEADER, InitDataContext, TelegramUser
from tests.conftest import valid_init_data
from tests.test_day_report_submit import _fail_insert
from tests.test_db_roles import role_engine

SUBMIT = "/miniapp/v1/day/report/submit"
MSK = timezone(timedelta(hours=3))
STARTED = datetime(2026, 10, 18, 9, 0, tzinfo=MSK)
# Внутри окна дня STARTED (04:00 19.10 — 00:00 20.10 МСК).
NOW_IN_WINDOW = datetime(2026, 10, 19, 12, 0, tzinfo=MSK)


@pytest.fixture(autouse=True)
def _inside_day_window(monkeypatch):
    monkeypatch.setattr(day_clock, "utcnow", lambda: NOW_IN_WINDOW)


def _marks(day_no: int, value: str = "done") -> list[dict[str, str]]:
    blocks = get_day_content().get(1, 1, day_no).blocks
    return [{"block_id": b.block_id, "value": value} for b in blocks]


def _body(day_no: int = 6, value: str = "done", **extra) -> DayReportIn:
    return DayReportIn.model_validate({"marks": _marks(day_no, value), **extra})


# ============================ без БД ============================


def test_6_model_2001_and_nul_rejected():
    marks = [{"block_id": "task_1", "value": "done"}]
    assert DayReportIn.model_validate({"marks": marks, "reflection": "я" * 2000}).reflection
    with pytest.raises(ValidationError):
        DayReportIn.model_validate({"marks": marks, "reflection": "я" * 2001})
    with pytest.raises(ValidationError):
        DayReportIn.model_validate({"marks": marks, "reflection": "ок\x00ок"})
    with pytest.raises(ValidationError):
        DayReportIn.model_validate({"marks": marks, "reflection": 123})


@pytest.mark.parametrize("reflection", ["я" * 2001, "ок\x00ок", 5])
def test_6_http_validation_error_422(api_client, reflection):
    from main import app

    app.dependency_overrides[rate_limit] = lambda: None
    r = api_client.post(
        SUBMIT,
        json={"marks": [{"block_id": "task_1", "value": "done"}], "reflection": reflection},
        headers={INIT_DATA_HEADER: valid_init_data(), "X-Client-Op-Id": str(uuid.uuid4())},
    )
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"


def test_11_params_hash():
    pairs = [("task_1", "done"), ("task_2", "not_done")]
    assert params_hash(pairs) == params_hash(pairs, None)
    assert params_hash(pairs, "ок") != params_hash(pairs)
    assert params_hash(list(reversed(pairs)), "ок") == params_hash(pairs, "ок")
    assert params_hash(pairs, "  ок  ") == params_hash(pairs, "ок")  # norm = strip


def test_12_no_position_without_reflection_required():
    for status in ("not_started", "entering"):
        out = DayCurrentOut(status=status, lives=3, test_entry=False)
        assert "reflection_required" not in out.model_dump(exclude_unset=True)


# ============================ с БД ============================


def _pid(engine, tg_user_id: int, day_no: int = 6) -> uuid.UUID:
    """Участник + строка participant_state владельцем (позиция 1/1/day_no, STARTED)."""
    with Session(engine) as session:
        pid = register_with_consents(session, tg_user_id, ["C0", "C1"]).participant.pid
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO participant_state "
                "(pid, lifecycle_phase, updated_at, projector_version, "
                "stage_no, module_no, day_no, day_started_at) "
                "VALUES (:pid, 'onboarding', now(), 1, 1, 1, :d, :ts)"
            ),
            {"pid": pid, "d": day_no, "ts": STARTED},
        )
    return pid


def _submit(engine, tg_user_id: int, op_id, body: DayReportIn):
    with Session(engine) as session:
        return submit_day_report(session, tg_user_id, op_id, body, get_day_content())


def _http_error(engine, tg_user_id: int, op_id, body: DayReportIn) -> HTTPException:
    with pytest.raises(HTTPException) as exc:
        _submit(engine, tg_user_id, op_id, body)
    return exc.value


def _ctx(tg_user_id: int) -> InitDataContext:
    return InitDataContext(user=TelegramUser(id=tg_user_id), auth_date=int(time.time()))


def _scalar(engine, sql: str, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar_one()


def _counts(engine, pid) -> dict[str, int]:
    return {
        "events": _scalar(
            engine,
            "SELECT count(*) FROM participant_events "
            "WHERE pid = :p AND kind = 'day_report_submitted'",
            p=pid,
        ),
        "keys": _scalar(
            engine,
            "SELECT count(*) FROM idempotency_keys WHERE key LIKE :a OR key LIKE :b OR key LIKE :c",
            a=f"day_done:{pid}:%",
            b=f"day_report:{pid}:%",
            c=f"day_queue:{pid}:%",
        ),
        "marks": _scalar(engine, "SELECT count(*) FROM day_marks WHERE pid = :p", p=pid),
        "log": _scalar(engine, "SELECT count(*) FROM reflections_log WHERE pid = :p", p=pid),
        "outbox": _scalar(
            engine, "SELECT count(*) FROM outbox WHERE aggregate_id = :p", p=str(pid)
        ),
    }


NOTHING = {"events": 0, "keys": 0, "marks": 0, "log": 0, "outbox": 0}


def _required(err: HTTPException) -> bool:
    return (err.status_code, err.detail["code"]) == (422, "REFLECTION_REQUIRED")


def test_1_day6_without_field_422(db_engine):
    pid = _pid(db_engine, 4701)
    err = _http_error(db_engine, 4701, uuid.uuid4(), _body())
    assert _required(err)
    assert err.detail["message"] == "Нужна рефлексия: минимум 2 символа."
    assert _counts(db_engine, pid) == NOTHING


@pytest.mark.parametrize("reflection", [" а ", "\t\n"])
def test_2_day6_short_reflection_422(db_engine, reflection):
    pid = _pid(db_engine, 4702)
    err = _http_error(db_engine, 4702, uuid.uuid4(), _body(reflection=reflection))
    assert _required(err)
    assert _counts(db_engine, pid) == NOTHING


def test_3_day6_all_not_done_without_field_422(db_engine):
    pid = _pid(db_engine, 4703)
    err = _http_error(db_engine, 4703, uuid.uuid4(), _body(value="not_done"))
    assert _required(err)
    assert _counts(db_engine, pid) == NOTHING


def _log_rows(engine, pid):
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT id, stage_no, module_no, day_no, day_started_at, body "
                "FROM reflections_log WHERE pid = :p"
            ),
            {"p": pid},
        ).all()


def _outbox_rows(engine, pid):
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT aggregate_id, event_type, payload FROM outbox WHERE aggregate_id = :p"),
            {"p": str(pid)},
        ).all()


def test_4_day6_reflection_200(db_engine):
    pid = _pid(db_engine, 4704)
    out = _submit(db_engine, 4704, uuid.uuid4(), _body(reflection="  ок  "))
    assert out.queued is True
    rows = _log_rows(db_engine, pid)
    assert len(rows) == 1
    row = rows[0]
    assert row.body == "ок"
    assert (row.stage_no, row.module_no, row.day_no) == (1, 1, 6)
    assert row.day_started_at == STARTED
    outbox = _outbox_rows(db_engine, pid)
    assert len(outbox) == 1
    assert (str(outbox[0].aggregate_id), outbox[0].event_type) == (
        str(pid),
        "reflection_submitted",
    )
    assert _counts(db_engine, pid)["events"] == 1


def test_5_payload_and_no_body_in_logs(db_engine, caplog):
    pid = _pid(db_engine, 4705)
    secret = "моя тайная рефлексия дня"
    op_id = uuid.uuid4()
    with caplog.at_level(logging.DEBUG):
        with Session(db_engine) as session:
            post_day_report_submit(
                _body(reflection=f"  {secret}  "), op_id, _ctx(4705), session, get_day_content()
            )
    (log_row,) = _log_rows(db_engine, pid)
    (outbox,) = _outbox_rows(db_engine, pid)
    assert outbox.payload == {"pid": str(pid), "reflection_id": log_row.id}
    assert type(outbox.payload["reflection_id"]) is int
    assert secret not in outbox.payload.values()
    for record in caplog.records:
        message = record.getMessage()
        assert secret not in message
        if record.name.startswith("app."):
            assert str(pid) not in message and str(op_id) not in message


def test_6_day6_2000_cyrillic_200(db_engine):
    pid = _pid(db_engine, 4706)
    _submit(db_engine, 4706, uuid.uuid4(), _body(reflection="я" * 2000))
    (row,) = _log_rows(db_engine, pid)
    assert row.body == "я" * 2000


def test_7_repeat_op_id(db_engine):
    pid = _pid(db_engine, 4707)
    op_id = uuid.uuid4()
    first = _submit(db_engine, 4707, op_id, _body(reflection="ок"))
    again = _submit(db_engine, 4707, op_id, _body(reflection="  ок "))  # тот же norm
    assert again == first
    assert (_counts(db_engine, pid)["log"], _counts(db_engine, pid)["outbox"]) == (1, 1)
    err = _http_error(db_engine, 4707, op_id, _body(reflection="другая"))
    assert (err.status_code, err.detail["code"]) == (409, "IDEMPOTENCY_CONFLICT")
    assert (_counts(db_engine, pid)["log"], _counts(db_engine, pid)["outbox"]) == (1, 1)


def test_8_new_op_id_after_submit_409(db_engine):
    pid = _pid(db_engine, 4708)
    _submit(db_engine, 4708, uuid.uuid4(), _body(reflection="ок"))
    err = _http_error(db_engine, 4708, uuid.uuid4(), _body())
    assert (err.status_code, err.detail["code"]) == (409, "DAY_ALREADY_SUBMITTED")
    assert _counts(db_engine, pid)["log"] == 1


def test_9_day1_reflection_accepted_not_logged(db_engine):
    pid = _pid(db_engine, 4709, day_no=1)
    out = _submit(db_engine, 4709, uuid.uuid4(), _body(day_no=1, reflection="ок"))
    assert out.queued is True
    counts = _counts(db_engine, pid)
    assert (counts["log"], counts["outbox"], counts["events"]) == (0, 0, 1)


def test_10_reflection_insert_fails_503_nothing_written(db_engine, monkeypatch):
    pid = _pid(db_engine, 4710)
    with Session(db_engine) as session:
        hit = _fail_insert(
            monkeypatch, session, lambda sql, params: "INSERT INTO reflections_log" in sql
        )
        with pytest.raises(HTTPException) as exc:
            post_day_report_submit(
                _body(reflection="ок"), uuid.uuid4(), _ctx(4710), session, get_day_content()
            )
    assert hit["hit"]
    assert (exc.value.status_code, exc.value.detail["code"]) == (503, "SERVICE_UNAVAILABLE")
    assert _counts(db_engine, pid) == NOTHING


@pytest.mark.parametrize(("tg_user_id", "day_no", "expected"), [(4712, 6, True), (4713, 1, False)])
def test_12_get_reflection_required(db_engine, tg_user_id, day_no, expected):
    _pid(db_engine, tg_user_id, day_no=day_no)
    with Session(db_engine) as session:
        current = read_day_current(session, tg_user_id, get_day_content(), False)
    assert current.status == "open"
    assert current.reflection_required is expected
    assert current.model_dump(exclude_unset=True)["reflection_required"] is expected


@pytest.fixture
def api_engine(migrated_db):
    engine = role_engine(migrated_db, "app_api")
    try:
        yield engine
    finally:
        engine.dispose()


def test_13_app_api_can_insert_reflection_and_outbox(db_engine, api_engine):
    # Единственный тест прав: CI работает суперпользователем, здесь — SET ROLE app_api.
    pid = uuid.uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tg_user_registry (pid, tg_user_id, created_via) "
                "VALUES (:p, 4714, 'mini_app_first_launch')"
            ),
            {"p": pid},
        )
    with api_engine.begin() as conn:
        reflection_id = conn.execute(
            _INSERT_REFLECTION,
            {"pid": pid, "s": 1, "m": 1, "d": 6, "ds": STARTED, "body": "ок"},
        ).scalar_one()
        assert type(reflection_id) is int and reflection_id > 0
        conn.execute(
            _INSERT_REFLECTION_OUTBOX,
            {
                "pid_text": str(pid),
                "payload": json.dumps({"pid": str(pid), "reflection_id": reflection_id}),
            },
        )
    (outbox,) = _outbox_rows(db_engine, pid)
    assert outbox.payload == {"pid": str(pid), "reflection_id": reflection_id}
