"""api-sup-1: POST /miniapp/v1/support/question с БД (DATABASE_URL; в CI обязательно).

Тесты t1–t13 карточки api-sup-1 §9. tg_user_id 4301–4399. outbox фикстура db_engine не
чистит: строки outbox считаются только по event_type support_question и aggregate_id = pid;
support_questions — тоже по pid (очищается каскадом через tg_user_registry).
"""
from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy import text

from app.db import models
from app.routers import support
from app.telegram_init_data import INIT_DATA_HEADER
from tests.conftest import _database_url, grant_access, valid_init_data

URL = "/miniapp/v1/support/question"
FIRST_LAUNCH = "/miniapp/v1/onboarding/first-launch"
FL_BODY = {"birth_date": "1990-01-01", "consents": ["C0", "C1"]}
C1_KEY = "legal.consent_c1_pdn"
LOGGER = "app.support"
QUESTION = "  Как пройти первый день курса?  "
BODY = {"topic_code": "s3", "text": QUESTION}


def _init(user_id: int) -> str:
    return valid_init_data(user={"id": user_id, "first_name": "Test"})


def _first_launch(client, user_id: int) -> str:
    grant_access(_database_url(), user_id)
    r = client.post(FIRST_LAUNCH, json=FL_BODY, headers={INIT_DATA_HEADER: _init(user_id)})
    assert r.status_code == 201, r.text
    return r.json()["pid"]


def _post(client, user_id: int, op_id: str | None = None, body: dict | None = None):
    headers = {INIT_DATA_HEADER: _init(user_id), "X-Client-Op-Id": op_id or str(uuid.uuid4())}
    return client.post(URL, json=BODY if body is None else body, headers=headers)


def _questions(engine, pid: str) -> int:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT count(*) FROM support_questions WHERE pid = :p"),
            {"p": uuid.UUID(pid)},
        ).scalar_one()


def _outbox(engine, pid: str) -> list:
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT payload FROM outbox "
                "WHERE event_type = 'support_question' AND aggregate_id = :a"
            ),
            {"a": pid},
        ).all()


def _shift(engine, pid: str) -> None:
    """Сдвинуть created_at вопросов pid на −31 с (под владельцем)."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE support_questions SET created_at = created_at - interval '31 seconds' "
                "WHERE pid = :p"
            ),
            {"p": uuid.UUID(pid)},
        )


def _revoke(engine, pid: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO consent_events "
                "(pid, kind, action, at, ver_of_text, text_key, text_snapshot, created_via) "
                "VALUES (:pid, 'C1', 'revoke', now(), '0.2.0', :t, "
                "'[ЗАГЛУШКА] x', 'mini_app_first_launch')"
            ),
            {"pid": uuid.UUID(pid), "t": C1_KEY},
        )


# t1
def test_route_exists_and_requires_init_data(api_client):
    from main import app

    # Подключённые роутеры в app.routes — вложенные объекты; маршрут ищем в схеме OpenAPI.
    assert "post" in app.openapi()["paths"].get(URL, {})
    r = api_client.post(URL, json=BODY, headers={"X-Client-Op-Id": str(uuid.uuid4())})
    assert r.status_code == 401, r.text
    assert r.json()["code"] == "TG_INIT_MISSING"


# t2
def test_validation_error(api_client):
    init = {INIT_DATA_HEADER: _init(4302)}
    cases = [
        (init, BODY),
        ({**init, "X-Client-Op-Id": str(uuid.uuid1())}, BODY),
        ({**init, "X-Client-Op-Id": str(uuid.uuid4())}, {"topic_code": "s1"}),
        ({**init, "X-Client-Op-Id": str(uuid.uuid4())}, {"topic_code": "s1", "text": 12345}),
    ]
    for headers, body in cases:
        r = api_client.post(URL, json=body, headers=headers)
        assert r.status_code == 422, r.text
        assert r.json()["code"] == "VALIDATION_ERROR"


# t3
def test_topic_invalid(db_api_client, db_engine):
    pid = _first_launch(db_api_client, 4303)
    for topic in ("s0", "s8", "S1", "", "other "):
        r = _post(db_api_client, 4303, body={"topic_code": topic, "text": "вопрос"})
        assert r.status_code == 422, r.text
        assert r.json()["code"] == "SUPPORT_TOPIC_INVALID"
    assert _questions(db_engine, pid) == 0


# t4
def test_text_invalid(db_api_client, db_engine):
    pid = _first_launch(db_api_client, 4304)
    for value in ("a", "   a   ", "\n\na", "x" * 2001, "ab\x00"):
        r = _post(db_api_client, 4304, body={"topic_code": "s1", "text": value})
        assert r.status_code == 422, r.text
        assert r.json()["code"] == "SUPPORT_TEXT_INVALID"
    assert _questions(db_engine, pid) == 0


# t5
def test_new_question_row_and_outbox(db_api_client, db_engine):
    pid = _first_launch(db_api_client, 4305)
    op_id = str(uuid.uuid4())
    r = _post(db_api_client, 4305, op_id, {**BODY, "group_topic_id": 7})
    assert r.status_code == 201, r.text
    assert r.json() == {"status": "sent"}
    with db_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, topic_code, body, client_op_id FROM support_questions "
                "WHERE pid = :p"
            ),
            {"p": uuid.UUID(pid)},
        ).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.topic_code == "s3"
    assert row.body == QUESTION.strip()
    assert row.client_op_id == op_id
    outbox = _outbox(db_engine, pid)
    assert len(outbox) == 1
    assert outbox[0].payload == {"pid": pid, "question_id": row.id}
    dumped = json.dumps(outbox[0].payload, ensure_ascii=False)
    assert QUESTION.strip() not in dumped
    assert "первый день" not in dumped


# t6
def test_accepted_values(db_api_client, db_engine):
    pid = _first_launch(db_api_client, 4306)
    bodies = [
        {"topic_code": "s1", "text": "ab"},
        {"topic_code": "s1", "text": "я" * 2000},
        {"topic_code": "other", "text": "вопрос"},
        {"topic_code": "s7", "text": "вопрос"},
    ]
    for i, body in enumerate(bodies, start=1):
        if i > 1:
            _shift(db_engine, pid)
        r = _post(db_api_client, 4306, body=body)
        assert r.status_code == 201, r.text
        assert _questions(db_engine, pid) == i


# t7
def test_repeat_same_op_id(db_api_client, db_engine):
    pid = _first_launch(db_api_client, 4307)
    op_id = str(uuid.uuid4())
    assert _post(db_api_client, 4307, op_id).status_code == 201
    again = _post(db_api_client, 4307, op_id)
    assert again.status_code == 201, again.text
    assert again.json() == {"status": "sent"}
    assert _questions(db_engine, pid) == 1
    assert len(_outbox(db_engine, pid)) == 1


# t8
def test_too_frequent(db_api_client, db_engine):
    pid = _first_launch(db_api_client, 4308)
    assert _post(db_api_client, 4308).status_code == 201
    r = _post(db_api_client, 4308)
    assert r.status_code == 429, r.text
    assert r.json()["code"] == "SUPPORT_TOO_FREQUENT"
    retry = r.headers.get("Retry-After")
    assert retry is not None and retry.isdigit()
    assert 1 <= int(retry) <= 30
    assert _questions(db_engine, pid) == 1

    _shift(db_engine, pid)
    r = _post(db_api_client, 4308)
    assert r.status_code == 201, r.text
    assert _questions(db_engine, pid) == 2


# t9
def test_participant_not_found(db_api_client, db_engine):
    r = _post(db_api_client, 4309)
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "PARTICIPANT_NOT_FOUND"

    pid = _first_launch(db_api_client, 4310)
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE tg_user_registry SET tombstoned_at = now() WHERE pid = :p"),
            {"p": uuid.UUID(pid)},
        )
    r = _post(db_api_client, 4310)
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "PARTICIPANT_NOT_FOUND"
    assert _questions(db_engine, pid) == 0


# t10
def test_reconsent_required(db_api_client, db_engine):
    pid = _first_launch(db_api_client, 4311)
    _revoke(db_engine, pid)
    r = _post(db_api_client, 4311)
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "RECONSENT_REQUIRED"
    assert _questions(db_engine, pid) == 0
    assert _outbox(db_engine, pid) == []


# t11
def test_outbox_failure_rolls_back(db_api_client, db_engine, monkeypatch):
    pid = _first_launch(db_api_client, 4312)
    monkeypatch.setattr(support, "_INSERT_OUTBOX", text("SELECT 1/0"))
    r = _post(db_api_client, 4312)
    assert r.status_code == 503, r.text
    assert r.json()["code"] == "SERVICE_UNAVAILABLE"
    assert _questions(db_engine, pid) == 0
    assert _outbox(db_engine, pid) == []


# t12
def test_log_has_no_question_data(db_api_client, db_engine, caplog):
    pid = _first_launch(db_api_client, 4313)
    op_id = str(uuid.uuid4())
    body = {"topic_code": "s5", "text": "Секретный вопрос участника"}
    caplog.set_level(logging.INFO, logger=LOGGER)
    assert _post(db_api_client, 4313, op_id, body).status_code == 201
    assert _post(db_api_client, 4313, op_id, body).status_code == 201
    assert _post(db_api_client, 4313, body=body).status_code == 429
    records = [r.getMessage() for r in caplog.records if r.name == LOGGER]
    assert records, "нет записей app.support"
    joined = "\n".join(records)
    assert "tg_user_id=4313" in joined
    for word in ("status=created", "status=repeat", "status=SUPPORT_TOO_FREQUENT"):
        assert word in joined
    for word in (pid, op_id, "s5", "Секретный", "вопрос участника"):
        assert word not in joined


# t13
def test_module_constants():
    assert support.SUPPORT_MIN_INTERVAL_S == 30
    assert support.EVENT_TYPE == "support_question"
    assert support.SUPPORT_TOPIC_CODES is models.SUPPORT_TOPIC_CODES
