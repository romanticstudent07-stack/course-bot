"""api-pause-2 (T3): маршруты паузы с БД (DATABASE_URL; в CI обязательно) — карточка §8.

tg_user_id 8811–8899 (свой диапазон, не пересекается с test_support_db.py). «Сейчас» —
pause.get_now через dependency_overrides. participant_state, pause_budgets, строки
participant_pauses (active / ended) и ключи часов тест вставляет владельцем БД; проектор
в тестах не работает — статус строк после событий не меняется.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from app import day_keys
from app.routers import pause
from app.telegram_init_data import INIT_DATA_HEADER
from tests.conftest import _database_url, grant_access, valid_init_data

PREFIX = "/miniapp/v1"
FIRST_LAUNCH = "/miniapp/v1/onboarding/first-launch"
FL_BODY = {"birth_date": "1990-01-01", "consents": ["C0", "C1"]}
LOGGER = "app.pause"
TZ = "Europe/Moscow"
MSK = ZoneInfo(TZ)
NOW = datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc)  # 12:00 МСК
TOMORROW = datetime(2026, 11, 21, 0, 0, tzinfo=MSK)


@pytest.fixture
def client(db_api_client):
    from main import app

    app.dependency_overrides[pause.get_now] = lambda: NOW
    return db_api_client  # overrides очищает db_api_client


def _init(user_id: int) -> dict[str, str]:
    return {INIT_DATA_HEADER: valid_init_data(user={"id": user_id, "first_name": "Test"})}


def _pid(client, user_id: int) -> uuid.UUID:
    grant_access(_database_url(), user_id)
    r = client.post(FIRST_LAUNCH, json=FL_BODY, headers=_init(user_id))
    assert r.status_code == 201, r.text
    return uuid.UUID(r.json()["pid"])


def _state(engine, pid, flags: str = "{}", phase: str = "active") -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO participant_state (pid, lifecycle_phase, updated_at, "
                "projector_version, stage_no, module_no, day_no, day_started_at, tz, "
                "status_flags) VALUES (:pid, :ph, now(), 1, 1, 1, 1, :ts, :tz, "
                "CAST(:f AS text[]))"
            ),
            {"pid": pid, "ph": phase, "ts": NOW - timedelta(hours=8), "tz": TZ, "f": flags},
        )


def _participant(client, engine, user_id: int, **kwargs) -> uuid.UUID:
    pid = _pid(client, user_id)
    _state(engine, pid, **kwargs)
    return pid


def _budget(engine, pid, days: int, cycle_start: datetime) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO pause_budgets (pid, days_budget_remaining_annual, cycle_start_at, "
                "restart_no) VALUES (:pid, :d, :c, 0)"
            ),
            {"pid": pid, "d": days, "c": cycle_start},
        )


def _pause_row(engine, pid, status: str, start: datetime, ended_at: datetime | None = None) -> int:
    with engine.begin() as conn:
        return conn.execute(
            text(
                "INSERT INTO participant_pauses (pid, kind, status, start_at, planned_end_at, "
                "ended_at, stage_no, restart_no, client_op_id) "
                "VALUES (:pid, 'user', :s, :st, :end, :ea, 1, 0, :op) RETURNING id"
            ),
            {
                "pid": pid,
                "s": status,
                "st": start,
                "end": start + timedelta(days=3),
                "ea": ended_at,
                "op": str(uuid.uuid4()),
            },
        ).scalar_one()


def _key(engine, key: str, kind: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO idempotency_keys (key, kind, ttl) "
                "VALUES (:k, :kind, CAST(:ttl AS interval))"
            ),
            {"k": key, "kind": kind, "ttl": day_keys.TTL_BY_KIND[kind]},
        )


def _rows(engine, pid) -> list:
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT id, kind, status, start_at, planned_end_at, client_op_id "
                "FROM participant_pauses WHERE pid = :p ORDER BY id"
            ),
            {"p": pid},
        ).all()


def _events(engine, pid, kind: str) -> list:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT payload, at FROM participant_events WHERE pid = :p AND kind = :k"),
            {"p": pid, "k": kind},
        ).all()


def _key_exists(engine, key: str) -> bool:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT 1 FROM idempotency_keys WHERE key = :k"), {"k": key}
        ).first() is not None


def _request(client, user_id: int, days: int = 3, op: str | None = None):
    headers = {**_init(user_id), "X-Client-Op-Id": op or str(uuid.uuid4())}
    return client.post(PREFIX + "/pause/request", json={"days": days}, headers=headers)


def _get(client, user_id: int):
    return client.get(PREFIX + "/pause", headers=_init(user_id))


def _cancel(client, user_id: int):
    return client.post(PREFIX + "/pause/cancel", headers=_init(user_id))


def _resume(client, user_id: int):
    return client.post(PREFIX + "/pause/resume", headers=_init(user_id))


def _refused(r, reason: str) -> None:
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["code"] == "PAUSE_REFUSED"
    assert body["details"] == {"reason": reason}


# ============================ request ============================


def test_request_created(client, db_engine):
    pid = _participant(client, db_engine, 8811)
    op = str(uuid.uuid4())
    r = _request(client, 8811, days=3, op=op)
    assert r.status_code == 201, r.text
    got = r.json()["pause"]
    rows = _rows(db_engine, pid)
    assert len(rows) == 1
    row = rows[0]
    assert (row.kind, row.status, row.client_op_id) == ("user", "requested", op)
    assert row.start_at == TOMORROW
    assert row.planned_end_at == datetime(2026, 11, 24, 0, 0, tzinfo=MSK)
    assert row.start_at.astimezone(MSK).time().hour == 0
    assert got["id"] == row.id and got["status"] == "requested"
    assert datetime.fromisoformat(got["start_at"]) == row.start_at
    assert datetime.fromisoformat(got["planned_end_at"]) == row.planned_end_at


def test_request_repeat_same_op(client, db_engine):
    pid = _participant(client, db_engine, 8812)
    op = str(uuid.uuid4())
    first = _request(client, 8812, op=op)
    assert first.status_code == 201, first.text
    again = _request(client, 8812, days=5, op=op)
    assert again.status_code == 201, again.text
    assert again.json()["pause"]["id"] == first.json()["pause"]["id"]
    assert len(_rows(db_engine, pid)) == 1


def test_request_other_op_already_open(client, db_engine):
    pid = _participant(client, db_engine, 8813)
    assert _request(client, 8813).status_code == 201
    r = _request(client, 8813)
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "PAUSE_ALREADY_OPEN"
    assert len(_rows(db_engine, pid)) == 1


def test_refused_block_lives(client, db_engine):
    pid = _participant(client, db_engine, 8814, flags="{block_lives}")
    _refused(_request(client, 8814), "block_lives")
    assert _rows(db_engine, pid) == []


def test_refused_state(client, db_engine):
    pid = _pid(client, 8815)  # строки participant_state нет
    _refused(_request(client, 8815), "state")
    assert _rows(db_engine, pid) == []


def test_refused_gap_24h(client, db_engine):
    pid = _participant(client, db_engine, 8816)
    _pause_row(db_engine, pid, "ended", NOW - timedelta(days=3), ended_at=NOW)
    _refused(_request(client, 8816), "gap_24h")


def test_refused_stage_taken(client, db_engine):
    pid = _participant(client, db_engine, 8817)
    _pause_row(db_engine, pid, "ended", NOW - timedelta(days=20), ended_at=NOW - timedelta(days=17))
    _refused(_request(client, 8817), "stage_taken")


def test_refused_no_budget(client, db_engine):
    pid = _participant(client, db_engine, 8818)
    _budget(db_engine, pid, 2, NOW - timedelta(days=30))
    _refused(_request(client, 8818, days=3), "no_budget")
    assert _rows(db_engine, pid) == []


def test_no_participant_is_404(client):
    r = _request(client, 8819)
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "PARTICIPANT_NOT_FOUND"


# ============================ GET ============================


def test_get_without_budget_row(client, db_engine):
    _participant(client, db_engine, 8820)
    r = _get(client, 8820)
    assert r.status_code == 200, r.text
    assert r.json() == {
        "budget_days_left": 14,
        "budget_days_total": 14,
        "cycle_ends_at": None,
        "pause": None,
        "can_request": True,
        "refusal": None,
    }


def test_get_anniversary_in_past(client, db_engine):
    pid = _participant(client, db_engine, 8821)
    start = datetime(2025, 1, 1, 0, 0, tzinfo=MSK)
    _budget(db_engine, pid, 3, start)
    r = _get(client, 8821)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["budget_days_left"] == 14
    assert datetime.fromisoformat(body["cycle_ends_at"]) == datetime(2027, 1, 1, tzinfo=MSK)
    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT days_budget_remaining_annual, cycle_start_at FROM pause_budgets "
                "WHERE pid = :p"
            ),
            {"p": pid},
        ).one()
    assert (row.days_budget_remaining_annual, row.cycle_start_at) == (3, start)


def test_get_open_request(client, db_engine):
    _participant(client, db_engine, 8822)
    created = _request(client, 8822).json()["pause"]
    body = _get(client, 8822).json()
    assert body["refusal"] == "already_open"
    assert body["can_request"] is False
    assert body["pause"]["id"] == created["id"]
    assert body["pause"]["status"] == "requested"


# ============================ cancel ============================


def test_cancel_and_repeat(client, db_engine):
    pid = _participant(client, db_engine, 8823)
    pause_id = _request(client, 8823).json()["pause"]["id"]
    r = _cancel(client, 8823)
    assert r.status_code == 202, r.text
    assert r.json() == {"status": "accepted"}
    events = _events(db_engine, pid, "pause_cancel")
    assert len(events) == 1
    assert events[0].payload == {"pause_id": pause_id}
    assert events[0].at == NOW
    assert _key_exists(db_engine, day_keys.key_pause_cancel(pid, pause_id))
    again = _cancel(client, 8823)
    assert again.status_code == 202, again.text
    assert len(_events(db_engine, pid, "pause_cancel")) == 1


def test_cancel_after_clock_start_key(client, db_engine):
    pid = _participant(client, db_engine, 8824)
    pause_id = _request(client, 8824).json()["pause"]["id"]
    _key(db_engine, day_keys.key_pause_start(pid, pause_id), day_keys.KIND_PAUSE_START)
    r = _cancel(client, 8824)
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "PAUSE_NOT_CANCELLABLE"
    assert _events(db_engine, pid, "pause_cancel") == []


def test_cancel_without_open(client, db_engine):
    _participant(client, db_engine, 8825)
    r = _cancel(client, 8825)
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "PAUSE_NOT_CANCELLABLE"


# ============================ resume ============================


def test_resume_and_repeat(client, db_engine):
    pid = _participant(client, db_engine, 8826)
    pause_id = _pause_row(db_engine, pid, "active", NOW - timedelta(hours=9))
    r = _resume(client, 8826)
    assert r.status_code == 202, r.text
    assert r.json() == {"status": "accepted"}
    events = _events(db_engine, pid, "pause_ended")
    assert len(events) == 1
    assert events[0].payload == {"pause_id": pause_id, "reason": "by_participant"}
    assert events[0].at == NOW
    again = _resume(client, 8826)
    assert again.status_code == 202, again.text
    assert len(_events(db_engine, pid, "pause_ended")) == 1


def test_resume_after_clock_end_key(client, db_engine):
    pid = _participant(client, db_engine, 8827)
    pause_id = _pause_row(db_engine, pid, "active", NOW - timedelta(hours=9))
    _key(db_engine, day_keys.key_pause_end(pid, pause_id), day_keys.KIND_PAUSE_END)
    r = _resume(client, 8827)
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "PAUSE_NOT_ACTIVE"
    assert _events(db_engine, pid, "pause_ended") == []


def test_resume_not_active(client, db_engine):
    _participant(client, db_engine, 8828)
    assert _request(client, 8828).status_code == 201  # requested, не active
    r = _resume(client, 8828)
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "PAUSE_NOT_ACTIVE"


# ============================ ошибки и лог ============================


def test_db_error_is_503_and_rolls_back(client, db_engine, monkeypatch):
    pid = _participant(client, db_engine, 8829)
    pause_id = _request(client, 8829).json()["pause"]["id"]
    monkeypatch.setattr(pause, "_INSERT_EVENT_SQL", text("SELECT 1/0"))
    r = _cancel(client, 8829)
    assert r.status_code == 503, r.text
    assert r.json()["code"] == "SERVICE_UNAVAILABLE"
    assert not _key_exists(db_engine, day_keys.key_pause_cancel(pid, pause_id))
    assert _events(db_engine, pid, "pause_cancel") == []


def test_log_has_no_pid_or_op(client, db_engine, caplog):
    pid = _participant(client, db_engine, 8830)
    op = str(uuid.uuid4())
    caplog.set_level(logging.INFO, logger=LOGGER)
    pause_id = _request(client, 8830, op=op).json()["pause"]["id"]
    assert _request(client, 8830, op=op).status_code == 201
    assert _request(client, 8830).status_code == 409
    assert _cancel(client, 8830).status_code == 202
    records = [r.getMessage() for r in caplog.records if r.name == LOGGER]
    joined = "\n".join(records)
    assert "tg_user_id=8830" in joined
    for word in ("status=created", "status=repeat", "status=PAUSE_ALREADY_OPEN", "status=accepted"):
        assert word in joined
    for word in (str(pid), op, f"pause_id={pause_id}", TZ):
        assert word not in joined
    assert json.dumps(str(pid)) not in joined
