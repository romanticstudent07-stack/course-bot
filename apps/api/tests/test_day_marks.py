"""PUT /day/marks (iter2-api-2a): отметки блоков в day_marks. С БД — только CI."""
import uuid

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.day_content import get_day_content
from app.day_keys import KIND_DAY_DONE, dsa, key_day_done
from app.projector import run_once
from app.routers.day import DayMarkIn, enter_day_by_test_flag, insert_idempotency_key, put_day_mark
from app.routers.onboarding import register_with_consents


def _block_ids() -> list[str]:
    return [block.block_id for block in get_day_content().get(1, 1, 1).blocks]


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
    with engine.connect() as conn:
        started = conn.execute(
            text("SELECT day_started_at FROM participant_state WHERE pid = :p"), {"p": pid}
        ).scalar_one()
    return pid, started


def _put(engine, tg_user_id: int, payload: dict):
    with Session(engine) as session:
        return put_day_mark(session, tg_user_id, DayMarkIn.model_validate(payload), get_day_content())


def _rows(engine, pid):
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT pid, day_started_at, block_id, value, at FROM day_marks WHERE pid = :p"),
            {"p": pid},
        ).all()


def _http_error(engine, tg_user_id: int, payload: dict) -> HTTPException:
    with pytest.raises(HTTPException) as exc:
        _put(engine, tg_user_id, payload)
    return exc.value


def test_body_validation():
    with pytest.raises(ValidationError):
        DayMarkIn.model_validate({"block_id": "a" * 33, "value": "done"})
    with pytest.raises(ValidationError):
        DayMarkIn.model_validate({"block_id": "Bad-Id", "value": "done"})
    with pytest.raises(ValidationError):
        DayMarkIn.model_validate({"block_id": "ok", "value": "maybe"})
    body = DayMarkIn.model_validate({"block_id": "a" * 32, "value": "done", "pid": "x"})
    assert not hasattr(body, "pid")


def test_mark_and_toggle_keeps_at(db_engine):
    pid, _ = _open_day(db_engine, 9001)
    block = _block_ids()[0]
    assert _put(db_engine, 9001, {"block_id": block, "value": "done"}).value == "done"
    first = _rows(db_engine, pid)
    assert len(first) == 1 and first[0].value is True
    assert _put(db_engine, 9001, {"block_id": block, "value": "not_done"}).value == "not_done"
    second = _rows(db_engine, pid)
    assert len(second) == 1 and second[0].value is False
    assert second[0].at == first[0].at  # at — время первой отметки (В19)


def test_block_not_in_day_422(db_engine):
    pid, _ = _open_day(db_engine, 9002)
    assert "zz_not_in_day" not in _block_ids()
    err = _http_error(db_engine, 9002, {"block_id": "zz_not_in_day", "value": "done"})
    assert (err.status_code, err.detail["code"]) == (422, "BLOCK_NOT_IN_DAY")
    assert _rows(db_engine, pid) == []


def test_day_already_submitted_409(db_engine):
    pid, started = _open_day(db_engine, 9003)
    with Session(db_engine) as session:
        insert_idempotency_key(session, key_day_done(pid, started), KIND_DAY_DONE)
        session.commit()
    err = _http_error(db_engine, 9003, {"block_id": _block_ids()[0], "value": "done"})
    assert (err.status_code, err.detail["code"]) == (409, "DAY_ALREADY_SUBMITTED")
    assert _rows(db_engine, pid) == []


def test_day_not_started_409(db_engine):
    pid = _registered(db_engine, 9004)
    err = _http_error(db_engine, 9004, {"block_id": _block_ids()[0], "value": "done"})
    assert (err.status_code, err.detail["code"]) == (409, "DAY_NOT_STARTED")
    assert _rows(db_engine, pid) == []


def test_tombstoned_404_without_write(db_engine):
    pid, _ = _open_day(db_engine, 9005)
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE tg_user_registry SET tombstoned_at = now() WHERE pid = :p"), {"p": pid}
        )
    err = _http_error(db_engine, 9005, {"block_id": _block_ids()[0], "value": "done"})
    assert (err.status_code, err.detail["code"]) == (404, "PARTICIPANT_NOT_FOUND")
    assert _rows(db_engine, pid) == []


def test_pid_and_day_started_at_from_body_ignored(db_engine):
    pid, started = _open_day(db_engine, 9006)
    stranger = uuid.uuid4()
    payload = {
        "block_id": _block_ids()[0],
        "value": "done",
        "pid": str(stranger),
        "day_started_at": "2001-01-01T00:00:00+00:00",
    }
    _put(db_engine, 9006, payload)
    rows = _rows(db_engine, pid)
    assert len(rows) == 1
    assert rows[0].pid == pid
    assert dsa(rows[0].day_started_at) == dsa(started)
    assert _rows(db_engine, stranger) == []
