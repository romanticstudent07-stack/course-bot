"""GET /miniapp/v1/day/current (iter2-api-1, карточка §9) + ключи day_keys (Ш4).

Без БД: day_keys (dsa, форматы, TTL), build_blocks, 401, 503 при недоступной БД.
С БД (DATABASE_URL, в CI обязательно): 404 (нет участника, tombstoned), not_started
(нет строки state; day_no NULL), entering (ключ day_enter), open с отметками, can_submit,
отметки другого day_started_at не видны, submitted (ключ day_done), 503 DAY_CONTENT_MISSING,
GET ничего не пишет, Ш4 — ключ из day_started_at, прочитанного из БД.
Строки participant_state, day_marks и idempotency_keys тест вставляет владельцем БД.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.day_content import load_day_content
from app.day_keys import (
    KIND_DAY_DONE,
    KIND_DAY_ENTER,
    KIND_DAY_REPORT,
    TTL_BY_KIND,
    dsa,
    key_day_done,
    key_day_enter,
    key_day_report,
)
from app.routers.day import build_blocks
from app.telegram_init_data import INIT_DATA_HEADER
from tests.conftest import valid_init_data

URL = "/miniapp/v1/day/current"
FIRST_LAUNCH = "/miniapp/v1/onboarding/first-launch"
BODY = {"birth_date": "1990-01-01", "consents": ["C0", "C1"]}
MSK = timezone(timedelta(hours=3))
T_MSK = datetime(2026, 10, 18, 9, 0, tzinfo=MSK)
T_UTC = datetime(2026, 10, 18, 6, 0, tzinfo=timezone.utc)
PID = uuid.UUID("00000000-0000-4000-8000-000000000001")


def _headers(user_id: int) -> dict[str, str]:
    return {INIT_DATA_HEADER: valid_init_data(user={"id": user_id, "first_name": "Test"})}


# ============================ без БД ============================


def test_dsa_same_moment_same_string():
    assert dsa(T_MSK) == dsa(T_UTC) == "2026-10-18T06:00:00+00:00"


def test_dsa_naive_is_value_error():
    with pytest.raises(ValueError):
        dsa(datetime(2026, 10, 18, 9, 0))
    with pytest.raises(ValueError):
        key_day_done(PID, datetime(2026, 10, 18, 9, 0))


def test_key_formats():
    assert key_day_enter(PID) == f"day_enter:{PID}"
    assert key_day_done(PID, T_MSK) == f"day_done:{PID}:2026-10-18T06:00:00+00:00"
    assert key_day_done(PID, T_MSK) == key_day_done(PID, T_UTC)
    assert key_day_report(PID, "op-1") == f"day_report:{PID}:op-1"


def test_kinds_and_ttl():
    assert (KIND_DAY_ENTER, KIND_DAY_DONE, KIND_DAY_REPORT) == (
        "day_enter",
        "day_done",
        "day_report",
    )
    assert TTL_BY_KIND == {
        "day_enter": "3650 days",
        "day_done": "3650 days",
        "day_report": "1 hour",
    }


def test_build_blocks_marks():
    day = load_day_content().get(1, 1, 1)
    blocks = build_blocks(day, {"task_1": True, "task_2": False, "alien": True})
    assert [b.block_id for b in blocks] == ["task_1", "task_2", "task_3", "task_4"]
    assert [b.mark for b in blocks] == ["done", "not_done", None, None]


def test_no_init_data_is_401(api_client):
    r = api_client.get(URL)
    assert r.status_code == 401
    assert r.json()["code"] == "TG_INIT_MISSING"


def test_db_unavailable_is_503(api_client):
    r = api_client.get(URL, headers=_headers(42))
    assert r.status_code == 503
    assert r.json()["code"] == "SERVICE_UNAVAILABLE"
    assert "127.0.0.1" not in r.text and "nopass" not in r.text


# ============================ с БД ============================


def _pid(client, user_id: int) -> uuid.UUID:
    r = client.post(FIRST_LAUNCH, json=BODY, headers=_headers(user_id))
    assert r.status_code == 201
    return uuid.UUID(r.json()["pid"])


def _state(engine, pid: uuid.UUID, day_no: int | None = 1, ts: datetime = T_MSK) -> None:
    with engine.begin() as conn:
        if day_no is None:
            conn.execute(text("INSERT INTO participant_state (pid) VALUES (:pid)"), {"pid": pid})
            return
        conn.execute(
            text(
                "INSERT INTO participant_state "
                "(pid, stage_no, module_no, day_no, day_started_at) "
                "VALUES (:pid, 1, 1, :d, :ts)"
            ),
            {"pid": pid, "d": day_no, "ts": ts},
        )


def _key(engine, key: str, kind: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO idempotency_keys (key, kind, ttl) "
                "VALUES (:k, :kind, CAST(:ttl AS interval))"
            ),
            {"k": key, "kind": kind, "ttl": TTL_BY_KIND[kind]},
        )


def _mark(engine, pid: uuid.UUID, ts: datetime, block_id: str, value: bool) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO day_marks (pid, day_started_at, block_id, value) "
                "VALUES (:pid, :ts, :b, :v)"
            ),
            {"pid": pid, "ts": ts, "b": block_id, "v": value},
        )


def _mark_all(engine, pid: uuid.UUID, ts: datetime = T_MSK) -> None:
    for i, block_id in enumerate(["task_1", "task_2", "task_3", "task_4"]):
        _mark(engine, pid, ts, block_id, i % 2 == 0)


def _count(engine, table: str) -> int:
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()


def test_no_participant_is_404(db_api_client):
    r = db_api_client.get(URL, headers=_headers(2001))
    assert r.status_code == 404
    assert r.json()["code"] == "PARTICIPANT_NOT_FOUND"


def test_tombstoned_is_404(db_api_client, db_engine):
    _pid(db_api_client, 2002)
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE tg_user_registry SET tombstoned_at = now() WHERE tg_user_id = 2002")
        )
    r = db_api_client.get(URL, headers=_headers(2002))
    assert r.status_code == 404
    assert r.json()["code"] == "PARTICIPANT_NOT_FOUND"


def test_not_started_without_state(db_api_client):
    _pid(db_api_client, 2003)
    r = db_api_client.get(URL, headers=_headers(2003))
    assert r.status_code == 200
    assert r.json() == {"status": "not_started", "lives": 3, "test_entry": False}


def test_not_started_day_no_null(db_api_client, db_engine):
    pid = _pid(db_api_client, 2004)
    _state(db_engine, pid, day_no=None)
    r = db_api_client.get(URL, headers=_headers(2004))
    assert r.status_code == 200
    assert r.json() == {"status": "not_started", "lives": 3, "test_entry": False}


def test_entering_with_day_enter_key(db_api_client, db_engine):
    pid = _pid(db_api_client, 2005)
    _state(db_engine, pid, day_no=None)
    _key(db_engine, key_day_enter(pid), KIND_DAY_ENTER)
    r = db_api_client.get(URL, headers=_headers(2005))
    assert r.status_code == 200
    assert r.json() == {"status": "entering", "lives": 3, "test_entry": False}


def test_open_with_marks(db_api_client, db_engine):
    pid = _pid(db_api_client, 2006)
    _state(db_engine, pid)
    _mark(db_engine, pid, T_MSK, "task_1", True)
    _mark(db_engine, pid, T_MSK, "task_2", False)
    r = db_api_client.get(URL, headers=_headers(2006))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "open"
    assert body["lives"] == 3
    assert body["test_entry"] is False
    assert body["position"] == {"stage_no": 1, "module_no": 1, "day_no": 1}
    assert datetime.fromisoformat(body["day_started_at"]) == T_MSK
    assert body["min_optional"] == 1
    assert body["can_submit"] is False
    assert [b["mark"] for b in body["blocks"]] == ["done", "not_done", None, None]
    first = body["blocks"][0]
    assert set(first) == {"block_id", "title_key", "help_key", "critical", "mark"}
    assert first["title_key"] == "B9.day_m1_d01_task_1_title"
    assert first["critical"] is True


def test_can_submit_when_all_marked(db_api_client, db_engine):
    pid = _pid(db_api_client, 2007)
    _state(db_engine, pid)
    _mark_all(db_engine, pid)
    body = db_api_client.get(URL, headers=_headers(2007)).json()
    assert body["status"] == "open"
    assert body["can_submit"] is True
    assert all(b["mark"] is not None for b in body["blocks"])


def test_marks_of_other_day_are_hidden(db_api_client, db_engine):
    pid = _pid(db_api_client, 2008)
    _state(db_engine, pid)
    _mark_all(db_engine, pid, ts=T_MSK - timedelta(days=1))
    body = db_api_client.get(URL, headers=_headers(2008)).json()
    assert body["status"] == "open"
    assert [b["mark"] for b in body["blocks"]] == [None, None, None, None]
    assert body["can_submit"] is False


def test_submitted_with_day_done_key(db_api_client, db_engine):
    pid = _pid(db_api_client, 2009)
    _state(db_engine, pid)
    _mark_all(db_engine, pid)
    _key(db_engine, key_day_done(pid, T_UTC), KIND_DAY_DONE)  # тот же момент, другой пояс
    body = db_api_client.get(URL, headers=_headers(2009)).json()
    assert body["status"] == "submitted"
    assert body["can_submit"] is False


def test_day_content_missing_is_503(db_api_client, db_engine, caplog):
    pid = _pid(db_api_client, 2010)
    _state(db_engine, pid, day_no=99)
    with caplog.at_level(logging.ERROR, logger="app.routers.day"):
        r = db_api_client.get(URL, headers=_headers(2010))
    assert r.status_code == 503
    assert r.json()["code"] == "DAY_CONTENT_MISSING"
    assert "day=99" in caplog.text
    assert str(pid) not in caplog.text


def test_get_writes_nothing(db_api_client, db_engine):
    pid = _pid(db_api_client, 2011)
    _state(db_engine, pid)
    _mark(db_engine, pid, T_MSK, "task_1", True)
    tables = ("participant_state", "day_marks", "idempotency_keys", "tg_user_registry")
    before = [_count(db_engine, t) for t in tables]
    db_api_client.get(URL, headers=_headers(2011))
    db_api_client.get(URL, headers=_headers(2012))  # без участника — 404, ничего не создаёт
    assert [_count(db_engine, t) for t in tables] == before


def test_sh4_key_from_db_timestamp(db_api_client, db_engine):
    pid = _pid(db_api_client, 2013)
    _state(db_engine, pid, ts=T_UTC)
    with db_engine.connect() as conn:
        db_ts = conn.execute(
            text("SELECT day_started_at FROM participant_state WHERE pid = :p"), {"p": pid}
        ).scalar_one()
    assert db_ts.tzinfo is not None
    assert key_day_done(pid, db_ts) == key_day_done(pid, T_MSK)
