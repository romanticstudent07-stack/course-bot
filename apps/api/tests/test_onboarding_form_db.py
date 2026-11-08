"""api-i3-2: GET и POST /miniapp/v1/onboarding/form с БД (DATABASE_URL; в CI обязательно).

Тесты 5–14 карточки api-i3-2 §9. Пишутся onboarding_form, measurements_log (kind body) и
событие tz_set; participant_state пишет только проектор (run_once).
"""
from __future__ import annotations

import logging
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.onboarding_form_config import get_onboarding_form_config
from app.projector import EVENT_KIND_TZ_SET, run_once
from app.routers import onboarding_form
from app.telegram_init_data import INIT_DATA_HEADER
from tests.conftest import _database_url, grant_access, valid_init_data

FORM = "/miniapp/v1/onboarding/form"
CHECKUP = "/miniapp/v1/checkup/submit"
FIRST_LAUNCH = "/miniapp/v1/onboarding/first-launch"
FL_BODY = {"birth_date": "1990-01-01", "consents": ["C0", "C1"]}
C1_KEY = "legal.consent_c1_pdn"
LOGGER = "app.onboarding_form"
TZ = "Asia/Omsk"
BODY = {"tz": TZ, "gender": "female", "wellbeing_code": "option_3", "weight_kg": 72.5}


@pytest.fixture(autouse=True)
def _clear_cache():
    get_onboarding_form_config.cache_clear()
    yield
    get_onboarding_form_config.cache_clear()


@pytest.fixture
def clean_form(db_engine):
    # FK на tg_user_registry: TRUNCATE ... CASCADE в db_engine их чистит,
    # явная очистка не зависит от порядка фикстур.
    with db_engine.begin() as conn:
        conn.execute(text("TRUNCATE onboarding_form, measurements_log RESTART IDENTITY"))
    yield db_engine


def _init(user_id: int) -> str:
    return valid_init_data(user={"id": user_id, "first_name": "Test"})


def _first_launch(client, user_id: int) -> str:
    grant_access(_database_url(), user_id)
    r = client.post(FIRST_LAUNCH, json=FL_BODY, headers={INIT_DATA_HEADER: _init(user_id)})
    assert r.status_code == 201, r.text
    return r.json()["pid"]


def _post(client, user_id: int, op_id: str | None = None, body: dict | None = None):
    headers = {INIT_DATA_HEADER: _init(user_id), "X-Client-Op-Id": op_id or str(uuid.uuid4())}
    return client.post(FORM, json=body or BODY, headers=headers)


def _get(client, user_id: int):
    return client.get(FORM, headers={INIT_DATA_HEADER: _init(user_id)})


def _counts(engine) -> tuple[int, int, int]:
    """(анкет, строк body, событий tz_set) — по всей БД."""
    with engine.connect() as conn:
        forms = conn.execute(text("SELECT count(*) FROM onboarding_form")).scalar_one()
        bodies = conn.execute(
            text("SELECT count(*) FROM measurements_log WHERE kind = 'body'")
        ).scalar_one()
        events = conn.execute(
            text("SELECT count(*) FROM participant_events WHERE kind = :k"),
            {"k": EVENT_KIND_TZ_SET},
        ).scalar_one()
    return forms, bodies, events


def _state_tz(engine, pid: str):
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT tz FROM participant_state WHERE pid = :p"), {"p": uuid.UUID(pid)}
        ).scalar()


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


# 5
def test_first_post_writes_three_rows(db_api_client, clean_form):
    pid = _first_launch(db_api_client, 6101)
    run_once(clean_form)
    tz_before = _state_tz(clean_form, pid)
    op_id = str(uuid.uuid4())
    r = _post(db_api_client, 6101, op_id, {**BODY, "city": "Омск", "name": "X"})
    assert r.status_code == 200, r.text
    assert set(r.json()) == {"created_at"}
    with clean_form.connect() as conn:
        form = conn.execute(
            text("SELECT gender, wellbeing_code FROM onboarding_form WHERE pid = :p"),
            {"p": uuid.UUID(pid)},
        ).one()
        body = conn.execute(
            text(
                "SELECT kind, occasion, stage_no, weight_kg, client_op_id "
                "FROM measurements_log WHERE pid = :p"
            ),
            {"p": uuid.UUID(pid)},
        ).all()
        events = conn.execute(
            text(
                "SELECT payload, actor, actor_role FROM participant_events "
                "WHERE pid = :p AND kind = :k"
            ),
            {"p": uuid.UUID(pid), "k": EVENT_KIND_TZ_SET},
        ).all()
    assert (form.gender, form.wellbeing_code) == ("female", "option_3")
    assert len(body) == 1
    assert body[0].kind == "body" and body[0].occasion == "onboarding"
    assert body[0].stage_no is None
    assert body[0].weight_kg == Decimal("72.5")
    assert body[0].client_op_id == op_id
    assert len(events) == 1
    assert events[0].payload == {"schema_version": 1, "tz": TZ}
    assert events[0].actor == "participant" and events[0].actor_role == "participant"
    assert _state_tz(clean_form, pid) == tz_before


# 6
def test_projector_applies_tz(db_api_client, clean_form):
    pid = _first_launch(db_api_client, 6201)
    assert _post(db_api_client, 6201).status_code == 200
    run_once(clean_form)
    assert _state_tz(clean_form, pid) == TZ


# 7
def test_repeat_same_op_id_200_no_new_rows(db_api_client, clean_form):
    _first_launch(db_api_client, 6301)
    op_id = str(uuid.uuid4())
    first = _post(db_api_client, 6301, op_id)
    assert first.status_code == 200, first.text
    before = _counts(clean_form)
    again = _post(db_api_client, 6301, op_id, {**BODY, "weight_kg": 80})
    assert again.status_code == 200, again.text
    assert again.json() == first.json()
    assert _counts(clean_form) == before


# 8
def test_other_op_id_after_form_409(db_api_client, clean_form):
    _first_launch(db_api_client, 6401)
    assert _post(db_api_client, 6401).status_code == 200
    before = _counts(clean_form)
    r = _post(db_api_client, 6401)
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "ONBOARDING_FORM_EXISTS"
    assert _counts(clean_form) == before


# 9
def test_op_id_taken_by_checkup_409(db_api_client, clean_form):
    _first_launch(db_api_client, 6501)
    op_id = str(uuid.uuid4())
    c = db_api_client.post(
        CHECKUP,
        json={"occasion": "onboarding", "answers": [1] * 15},
        headers={INIT_DATA_HEADER: _init(6501), "X-Client-Op-Id": op_id},
    )
    assert c.status_code == 200, c.text
    r = _post(db_api_client, 6501, op_id)
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert _counts(clean_form) == (0, 0, 0)


# 10
def test_reconsent_and_no_participant(db_api_client, clean_form):
    pid = _first_launch(db_api_client, 6601)
    _revoke(clean_form, pid)
    r = _post(db_api_client, 6601)
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "RECONSENT_REQUIRED"

    r = _post(db_api_client, 6602)
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "PARTICIPANT_NOT_FOUND"

    pid3 = _first_launch(db_api_client, 6603)
    with clean_form.begin() as conn:
        conn.execute(
            text("UPDATE tg_user_registry SET tombstoned_at = now() WHERE pid = :p"),
            {"p": uuid.UUID(pid3)},
        )
    r = _post(db_api_client, 6603)
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "PARTICIPANT_NOT_FOUND"
    assert _counts(clean_form) == (0, 0, 0)


# 11
def test_event_insert_failure_503_nothing_written(db_api_client, clean_form, monkeypatch):
    _first_launch(db_api_client, 6701)

    def _boom(session, pid, tz):
        raise OperationalError("INSERT participant_events", {}, Exception("boom"))

    monkeypatch.setattr(onboarding_form, "_insert_tz_event", _boom)
    r = _post(db_api_client, 6701)
    assert r.status_code == 503, r.text
    assert r.json()["code"] == "SERVICE_UNAVAILABLE"
    assert _counts(clean_form) == (0, 0, 0)


# 12
def test_get_form_status(db_api_client, clean_form):
    _first_launch(db_api_client, 6801)
    r = _get(db_api_client, 6801)
    assert r.status_code == 200, r.text
    assert r.json() == {"submitted": False, "created_at": None}

    post = _post(db_api_client, 6801)
    assert post.status_code == 200, post.text
    r = _get(db_api_client, 6801)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"submitted", "created_at"}
    assert body["submitted"] is True and body["created_at"]
    for word in ("gender", "weight", "tz", "female", TZ):
        assert word not in r.text

    r = _get(db_api_client, 6802)
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "PARTICIPANT_NOT_FOUND"


# 13
def test_log_has_no_form_data(db_api_client, clean_form, caplog):
    pid = _first_launch(db_api_client, 6901)
    op_id = str(uuid.uuid4())
    caplog.set_level(logging.INFO, logger=LOGGER)
    assert _post(db_api_client, 6901, op_id).status_code == 200
    assert _post(db_api_client, 6901, op_id).status_code == 200
    assert _post(db_api_client, 6901).status_code == 409
    records = [r.getMessage() for r in caplog.records if r.name == LOGGER]
    assert records, "нет записей app.onboarding_form"
    joined = "\n".join(records)
    assert "tg_user_id=6901" in joined
    for word in ("status=created", "status=repeat", "status=exists"):
        assert word in joined
    for word in (pid, op_id, TZ, "Omsk", "72.5", "option_3", "female"):
        assert word not in joined


# 14
def test_tz_set_kind_matches_projector():
    assert onboarding_form.EVENT_KIND_TZ_SET == EVENT_KIND_TZ_SET
