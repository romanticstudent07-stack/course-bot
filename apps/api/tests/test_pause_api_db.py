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


def _pause_row(
    engine,
    pid,
    status: str,
    start: datetime,
    ended_at: datetime | None = None,
    op: str | None = None,
) -> int:
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
                "op": op or str(uuid.uuid4()),
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


def _key_hash(engine, key: str):
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT params_hash FROM idempotency_keys WHERE key = :k"), {"k": key}
        ).first()


def _security_events(engine, pid) -> list:
    """security_events читает владелец (db_engine): у app_api SELECT нет."""
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT event_type, op_kind, client_op_id FROM security_events "
                "WHERE pid = :p ORDER BY 1"
            ),
            {"p": pid},
        ).all()


def _request(
    client,
    user_id: int,
    days: int = 3,
    op: str | None = None,
    start_date: str | None = TOMORROW.date().isoformat(),
):
    headers = {**_init(user_id), "X-Client-Op-Id": op or str(uuid.uuid4())}
    body = {"days": days, "start_date": start_date}
    return client.post(PREFIX + "/pause/request", json=body, headers=headers)


def _get(client, user_id: int):
    return client.get(PREFIX + "/pause", headers=_init(user_id))


def _cancel(client, user_id: int, pause_id: int, op: str | None = None):
    headers = {**_init(user_id), "X-Client-Op-Id": op or str(uuid.uuid4())}
    return client.post(PREFIX + "/pause/cancel", json={"pause_id": pause_id}, headers=headers)


def _resume(client, user_id: int, pause_id: int, op: str | None = None):
    headers = {**_init(user_id), "X-Client-Op-Id": op or str(uuid.uuid4())}
    return client.post(PREFIX + "/pause/resume", json={"pause_id": pause_id}, headers=headers)


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


def test_request_repeat_same_params(client, db_engine):
    pid = _participant(client, db_engine, 8812)
    op = str(uuid.uuid4())
    first = _request(client, 8812, op=op)
    assert first.status_code == 201, first.text
    again = _request(client, 8812, op=op)
    assert again.status_code == 201, again.text
    assert again.json()["pause"]["id"] == first.json()["pause"]["id"]
    assert len(_rows(db_engine, pid)) == 1
    key = _key_hash(db_engine, day_keys.key_pause_request(pid, op))
    assert key is not None and key.params_hash is not None
    assert _security_events(db_engine, pid) == []


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
        "start_date": "2026-11-21",
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
    assert body["start_date"] == TOMORROW.date().isoformat()


def test_get_start_date_after_midnight(client, db_engine):
    from main import app

    _participant(client, db_engine, 8849)
    app.dependency_overrides[pause.get_now] = lambda: datetime(
        2026, 11, 20, 21, 30, tzinfo=timezone.utc
    )
    r = _get(client, 8849)
    assert r.status_code == 200, r.text
    assert r.json()["start_date"] == "2026-11-22"


# ============================ cancel ============================


def test_cancel_and_repeat(client, db_engine):
    pid = _participant(client, db_engine, 8823)
    pause_id = _request(client, 8823).json()["pause"]["id"]
    op = str(uuid.uuid4())
    r = _cancel(client, 8823, pause_id, op=op)
    assert r.status_code == 202, r.text
    assert r.json() == {"status": "accepted"}
    events = _events(db_engine, pid, "pause_cancel")
    assert len(events) == 1
    assert events[0].payload == {"pause_id": pause_id}
    assert events[0].at == NOW
    assert _key_exists(db_engine, day_keys.key_pause_cancel(pid, pause_id))
    assert _key_exists(db_engine, day_keys.key_pause_op(pid, op))
    again = _cancel(client, 8823, pause_id, op=op)
    assert again.status_code == 202, again.text
    assert len(_events(db_engine, pid, "pause_cancel")) == 1


def test_cancel_after_clock_start_key(client, db_engine):
    pid = _participant(client, db_engine, 8824)
    pause_id = _request(client, 8824).json()["pause"]["id"]
    _key(db_engine, day_keys.key_pause_start(pid, pause_id), day_keys.KIND_PAUSE_START)
    r = _cancel(client, 8824, pause_id)
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "PAUSE_NOT_CANCELLABLE"
    assert _events(db_engine, pid, "pause_cancel") == []


def test_cancel_without_open(client, db_engine):
    _participant(client, db_engine, 8825)
    r = _cancel(client, 8825, 999999)  # строки нет
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "PAUSE_NOT_CANCELLABLE"


# ============================ resume ============================


def test_resume_and_repeat(client, db_engine):
    pid = _participant(client, db_engine, 8826)
    pause_id = _pause_row(db_engine, pid, "active", NOW - timedelta(hours=9))
    op = str(uuid.uuid4())
    r = _resume(client, 8826, pause_id, op=op)
    assert r.status_code == 202, r.text
    assert r.json() == {"status": "accepted"}
    events = _events(db_engine, pid, "pause_ended")
    assert len(events) == 1
    assert events[0].payload == {"pause_id": pause_id, "reason": "by_participant"}
    assert events[0].at == NOW
    again = _resume(client, 8826, pause_id, op=op)
    assert again.status_code == 202, again.text
    assert len(_events(db_engine, pid, "pause_ended")) == 1


def test_resume_after_clock_end_key(client, db_engine):
    pid = _participant(client, db_engine, 8827)
    pause_id = _pause_row(db_engine, pid, "active", NOW - timedelta(hours=9))
    _key(db_engine, day_keys.key_pause_end(pid, pause_id), day_keys.KIND_PAUSE_END)
    r = _resume(client, 8827, pause_id)
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "PAUSE_NOT_ACTIVE"
    assert _events(db_engine, pid, "pause_ended") == []


def test_resume_not_active(client, db_engine):
    _participant(client, db_engine, 8828)
    created = _request(client, 8828)  # requested, не active
    assert created.status_code == 201
    r = _resume(client, 8828, created.json()["pause"]["id"])
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "PAUSE_NOT_ACTIVE"


# ============================ ошибки и лог ============================


def test_db_error_is_503_and_rolls_back(client, db_engine, monkeypatch):
    pid = _participant(client, db_engine, 8829)
    pause_id = _request(client, 8829).json()["pause"]["id"]
    monkeypatch.setattr(pause, "_INSERT_EVENT_SQL", text("SELECT 1/0"))
    op = str(uuid.uuid4())
    r = _cancel(client, 8829, pause_id, op=op)
    assert r.status_code == 503, r.text
    assert r.json()["code"] == "SERVICE_UNAVAILABLE"
    assert not _key_exists(db_engine, day_keys.key_pause_cancel(pid, pause_id))
    assert not _key_exists(db_engine, day_keys.key_pause_op(pid, op))
    assert _events(db_engine, pid, "pause_cancel") == []


def test_log_has_no_pid_or_op(client, db_engine, caplog):
    pid = _participant(client, db_engine, 8830)
    op = str(uuid.uuid4())
    caplog.set_level(logging.INFO, logger=LOGGER)
    pause_id = _request(client, 8830, op=op).json()["pause"]["id"]
    assert _request(client, 8830, op=op).status_code == 201
    assert _request(client, 8830).status_code == 409
    assert _cancel(client, 8830, pause_id).status_code == 202
    records = [r.getMessage() for r in caplog.records if r.name == LOGGER]
    joined = "\n".join(records)
    assert "tg_user_id=8830" in joined
    for word in ("status=created", "status=repeat", "status=PAUSE_ALREADY_OPEN", "status=accepted"):
        assert word in joined
    for word in (str(pid), op, f"pause_id={pause_id}", TZ):
        assert word not in joined
    assert json.dumps(str(pid)) not in joined


# ============================ pause-api-a2: повтор, коллизия, start_date ============================


@pytest.mark.parametrize(
    ("user_id", "changed"),
    [(8831, {"days": 5}), (8832, {"start_date": "2026-11-22"})],
    ids=["other_days", "other_start_date"],
)
def test_request_collision_409_and_audit(client, db_engine, user_id, changed):
    pid = _participant(client, db_engine, user_id)
    op = str(uuid.uuid4())
    first = _request(client, user_id, op=op)
    assert first.status_code == 201, first.text
    before = _rows(db_engine, pid)
    r = _request(client, user_id, op=op, **changed)
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert _security_events(db_engine, pid) == [("client_op_id_conflict", "pause_request", op)]
    after = _rows(db_engine, pid)
    assert len(after) == 1
    assert after == before


def test_request_row_without_key_is_repeat(client, db_engine):
    pid = _participant(client, db_engine, 8833)
    op = str(uuid.uuid4())
    row_id = _pause_row(db_engine, pid, "requested", TOMORROW, op=op)
    r = _request(client, 8833, op=op)
    assert r.status_code == 201, r.text
    assert r.json()["pause"]["id"] == row_id
    assert not _key_exists(db_engine, day_keys.key_pause_request(pid, op))
    assert _security_events(db_engine, pid) == []


@pytest.mark.parametrize(
    ("user_id", "start_date"),
    [(8834, "2026-11-20"), (8835, "2026-11-22")],
    ids=["today", "day_after_tomorrow"],
)
def test_request_start_date_mismatch(client, db_engine, user_id, start_date):
    pid = _participant(client, db_engine, user_id)
    op = str(uuid.uuid4())
    _refused(_request(client, user_id, op=op, start_date=start_date), "start_date_passed")
    assert _rows(db_engine, pid) == []
    assert not _key_exists(db_engine, day_keys.key_pause_request(pid, op))
    assert _security_events(db_engine, pid) == []


def test_business_409_no_audit(client, db_engine):
    pid = _participant(client, db_engine, 8836)
    assert _request(client, 8836).status_code == 201
    r = _request(client, 8836)
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "PAUSE_ALREADY_OPEN"
    assert _security_events(db_engine, pid) == []
    refused_pid = _participant(client, db_engine, 8837, flags="{block_lives}")
    _refused(_request(client, 8837), "block_lives")
    assert _security_events(db_engine, refused_pid) == []


def test_audit_failed_still_409(client, db_engine, monkeypatch):
    _participant(client, db_engine, 8838)
    op = str(uuid.uuid4())
    assert _request(client, 8838, op=op).status_code == 201
    monkeypatch.setattr(pause, "record_security_event", lambda *a, **k: False)
    r = _request(client, 8838, days=5, op=op)
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_audit_after_rollback(client, db_engine, monkeypatch):
    _participant(client, db_engine, 8839)
    op = str(uuid.uuid4())
    assert _request(client, 8839, op=op).status_code == 201
    calls: list[str] = []
    original = pause._rollback

    def rollback(session):
        calls.append("rollback")
        original(session)

    def audit(*args, **kwargs):
        calls.append("audit")
        return True

    monkeypatch.setattr(pause, "_rollback", rollback)
    monkeypatch.setattr(pause, "record_security_event", audit)
    r = _request(client, 8839, days=5, op=op)
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert "audit" in calls
    idx = calls.index("audit")
    assert idx > 0 and calls[idx - 1] == "rollback"


# ============================ pause-api-a4: цель pause_id и X-Client-Op-Id ============================


def test_cancel_other_op_same_pause_no_event(client, db_engine):
    pid = _participant(client, db_engine, 8841)
    pause_id = _request(client, 8841).json()["pause"]["id"]
    op1, op2 = str(uuid.uuid4()), str(uuid.uuid4())
    assert _cancel(client, 8841, pause_id, op=op1).status_code == 202
    r = _cancel(client, 8841, pause_id, op=op2)
    assert r.status_code == 202, r.text
    assert r.json() == {"status": "accepted"}
    assert len(_events(db_engine, pid, "pause_cancel")) == 1
    assert _key_exists(db_engine, day_keys.key_pause_op(pid, op1))
    assert _key_exists(db_engine, day_keys.key_pause_op(pid, op2))
    assert _security_events(db_engine, pid) == []


def test_op_collision_other_pause_id(client, db_engine):
    pid = _participant(client, db_engine, 8842)
    pause_id = _request(client, 8842).json()["pause"]["id"]
    op = str(uuid.uuid4())
    assert _cancel(client, 8842, pause_id, op=op).status_code == 202
    r = _cancel(client, 8842, pause_id + 1, op=op)
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert _security_events(db_engine, pid) == [("client_op_id_conflict", "pause_cancel", op)]
    assert len(_events(db_engine, pid, "pause_cancel")) == 1


def test_op_collision_cancel_then_resume(client, db_engine):
    pid = _participant(client, db_engine, 8843)
    pause_id = _request(client, 8843).json()["pause"]["id"]
    op = str(uuid.uuid4())
    assert _cancel(client, 8843, pause_id, op=op).status_code == 202
    r = _resume(client, 8843, pause_id, op=op)
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert _security_events(db_engine, pid) == [("client_op_id_conflict", "pause_resume", op)]
    assert _events(db_engine, pid, "pause_ended") == []


def test_foreign_pause_409_no_audit(client, db_engine):
    # у A две строки: requested и active (как в _OPEN_SQL); B бьёт по их pause_id
    pid_a = _participant(client, db_engine, 8844)
    requested_id = _request(client, 8844).json()["pause"]["id"]
    active_id = _pause_row(db_engine, pid_a, "active", NOW - timedelta(hours=9))
    pid_b = _participant(client, db_engine, 8845)
    r = _cancel(client, 8845, requested_id)
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "PAUSE_NOT_CANCELLABLE"
    r = _resume(client, 8845, active_id)
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "PAUSE_NOT_ACTIVE"
    assert _events(db_engine, pid_a, "pause_cancel") == []
    assert _events(db_engine, pid_a, "pause_ended") == []
    assert not _key_exists(db_engine, day_keys.key_pause_cancel(pid_a, requested_id))
    assert not _key_exists(db_engine, day_keys.key_pause_resume(pid_a, active_id))
    assert _security_events(db_engine, pid_b) == []


def test_target_is_given_pause(client, db_engine):
    pid = _participant(client, db_engine, 8847)
    ended_id = _pause_row(
        db_engine, pid, "ended", NOW - timedelta(days=20), ended_at=NOW - timedelta(days=17)
    )
    requested_id = _pause_row(db_engine, pid, "requested", TOMORROW)
    r = _cancel(client, 8847, ended_id)
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "PAUSE_NOT_CANCELLABLE"
    assert not _key_exists(db_engine, day_keys.key_pause_cancel(pid, requested_id))
    assert _events(db_engine, pid, "pause_cancel") == []


def test_target_audit_after_rollback(client, db_engine, monkeypatch):
    _participant(client, db_engine, 8848)
    pause_id = _request(client, 8848).json()["pause"]["id"]
    op = str(uuid.uuid4())
    assert _cancel(client, 8848, pause_id, op=op).status_code == 202
    calls: list[str] = []
    original = pause._rollback

    def rollback(session):
        calls.append("rollback")
        original(session)

    def audit(*args, **kwargs):
        calls.append("audit")
        return True

    monkeypatch.setattr(pause, "_rollback", rollback)
    monkeypatch.setattr(pause, "record_security_event", audit)
    r = _cancel(client, 8848, pause_id + 1, op=op)
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert "audit" in calls
    idx = calls.index("audit")
    assert idx > 0 and calls[idx - 1] == "rollback"
