"""api-i3-4: GET /miniapp/v1/checkup/status (Р-18) — тесты 1–6 карточки api-i3-4 §9.

С БД (DATABASE_URL; в CI обязательно), кроме теста 5 (api_client, недоступная БД).
Признак — строка measurements_log kind checkup и occasion onboarding; балла и зоны в ответе нет.
"""
from __future__ import annotations

import logging
import uuid

import pytest
from sqlalchemy import text

from app.checkup_config import get_checkup_config
from app.onboarding_form_config import get_onboarding_form_config
from app.telegram_init_data import INIT_DATA_HEADER
from tests.conftest import _database_url, grant_access, valid_init_data

STATUS = "/miniapp/v1/checkup/status"
SUBMIT = "/miniapp/v1/checkup/submit"
FORM = "/miniapp/v1/onboarding/form"
FIRST_LAUNCH = "/miniapp/v1/onboarding/first-launch"
FL_BODY = {"birth_date": "1990-01-01", "consents": ["C0", "C1"]}
FORM_BODY = {"tz": "Asia/Omsk", "gender": "female", "wellbeing_code": "option_3", "weight_kg": 72.5}
RED_ANSWERS = [3] * 15
LOGGER = "app.checkup"


@pytest.fixture(autouse=True)
def _clear_cache():
    get_checkup_config.cache_clear()
    get_onboarding_form_config.cache_clear()
    yield
    get_checkup_config.cache_clear()
    get_onboarding_form_config.cache_clear()


@pytest.fixture
def clean_measurements(db_engine):
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


def _op_headers(user_id: int) -> dict[str, str]:
    return {INIT_DATA_HEADER: _init(user_id), "X-Client-Op-Id": str(uuid.uuid4())}


def _submit(client, user_id: int, answers=RED_ANSWERS):
    body = {"occasion": "onboarding", "answers": answers}
    return client.post(SUBMIT, json=body, headers=_op_headers(user_id))


def _status(client, user_id: int):
    return client.get(STATUS, headers={INIT_DATA_HEADER: _init(user_id)})


# 1
def test_no_participant_404(db_api_client, clean_measurements):
    r = _status(db_api_client, 7101)
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "PARTICIPANT_NOT_FOUND"


# 2
def test_no_checkup_not_completed(db_api_client, clean_measurements):
    _first_launch(db_api_client, 7201)
    r = _status(db_api_client, 7201)
    assert r.status_code == 200, r.text
    assert r.json() == {"completed": False, "created_at": None}


# 3
def test_after_submit_completed(db_api_client, clean_measurements):
    _first_launch(db_api_client, 7301)
    assert _submit(db_api_client, 7301).status_code == 200
    r = _status(db_api_client, 7301)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"completed", "created_at"}
    assert body["completed"] is True and body["created_at"]
    for word in ("zone", "score", "green", "red"):
        assert word not in r.text


# 4
def test_body_row_not_counted(db_api_client, clean_measurements):
    _first_launch(db_api_client, 7401)
    form = db_api_client.post(FORM, json=FORM_BODY, headers=_op_headers(7401))
    assert form.status_code == 200, form.text
    r = _status(db_api_client, 7401)
    assert r.status_code == 200, r.text
    assert r.json() == {"completed": False, "created_at": None}


# 5
def test_db_unavailable_503(api_client):
    r = api_client.get(STATUS, headers={INIT_DATA_HEADER: valid_init_data()})
    assert r.status_code == 503, r.text
    assert r.json()["code"] == "SERVICE_UNAVAILABLE"


# 6
def test_log_has_no_pid_and_zone(db_api_client, clean_measurements, caplog):
    pid = _first_launch(db_api_client, 7601)
    caplog.set_level(logging.INFO, logger=LOGGER)
    assert _submit(db_api_client, 7601).status_code == 200
    assert _status(db_api_client, 7601).status_code == 200
    records = [r.getMessage() for r in caplog.records if r.name == LOGGER]
    assert records, "нет записей app.checkup"
    joined = "\n".join(records)
    assert "tg_user_id=7601" in joined
    assert "checkup/status: tg_user_id=7601 status=ok" in joined
    assert pid not in joined
    # "red" есть внутри "status=created" — проверяем ключ и значение зоны отдельно.
    assert "zone" not in joined
    assert "=red" not in joined and " red" not in joined
