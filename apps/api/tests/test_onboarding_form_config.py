"""api-i3-2: конфиг анкеты, GET form/config и валидация тела POST /onboarding/form — без БД.

Тесты 1–4 карточки api-i3-2 §9.
"""
from __future__ import annotations

import csv
import re
import uuid
from zoneinfo import ZoneInfo

import pytest

import app.onboarding_form_config
from app.db.models import WELLBEING_CODE_PATTERN
from app.onboarding_form_config import get_onboarding_form_config
from tests.conftest import valid_init_data

STUB = "Заглушка"
CONFIG = "/miniapp/v1/onboarding/form/config"
FORM = "/miniapp/v1/onboarding/form"


@pytest.fixture(autouse=True)
def _clear_cache():
    get_onboarding_form_config.cache_clear()
    yield
    get_onboarding_form_config.cache_clear()


# 1
def test_get_config_200_schema(api_client):
    resp = api_client.get(CONFIG, headers={"X-Telegram-Init-Data": valid_init_data()})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {
        "version",
        "genders",
        "wellbeing_question",
        "wellbeing",
        "weight",
        "timezones",
        "fallback_title",
        "cities",
    }
    assert body["genders"] == ["male", "female"]
    assert body["weight"] == {"min": 30, "max": 300, "step": 0.1}
    for item in body["wellbeing"]:
        assert set(item) == {"code", "text"}
    assert len(body["timezones"]) == 11
    for item in body["timezones"]:
        assert set(item) == {"tz", "city"}
    assert len(body["cities"]) > 1000
    for city in body["cities"]:
        assert len(city) == 3
        assert isinstance(city[0], str) and isinstance(city[1], str)
        assert isinstance(city[2], int) and 0 <= city[2] <= 10


# 2
def test_all_texts_are_stubs_and_codes_valid():
    cfg = get_onboarding_form_config()
    texts = [cfg.wellbeing_question, cfg.fallback_title] + [w.text for w in cfg.wellbeing]
    assert all(t.startswith(STUB) for t in texts)
    codes = [w.code for w in cfg.wellbeing]
    assert codes == ["option_1", "option_2", "option_3", "option_4"]
    assert len(set(codes)) == len(codes)
    assert all(re.fullmatch(WELLBEING_CODE_PATTERN, c) for c in codes)


# 3
def test_cities_tz_in_timezones_and_zoneinfo_opens():
    cfg = get_onboarding_form_config()
    tz_list = [t.tz for t in cfg.timezones]
    assert len(tz_list) == 11
    for tz in tz_list:
        ZoneInfo(tz)
    path = app.onboarding_form_config.CITIES_PATH
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows
    assert {row["tz"] for row in rows} <= set(tz_list)
    assert cfg.allowed_tz == frozenset(tz_list)


# 4
GOOD_BODY = {
    "tz": "Asia/Omsk",
    "gender": "female",
    "wellbeing_code": "option_2",
    "weight_kg": 72.5,
}


def _post(client, body, op_id: str | None = "new"):
    headers = {"X-Telegram-Init-Data": valid_init_data()}
    if op_id == "new":
        op_id = str(uuid.uuid4())
    if op_id is not None:
        headers["X-Client-Op-Id"] = op_id
    return client.post(FORM, json=body, headers=headers)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tz", "Europe/London"),
        ("tz", "Moscow"),
        ("tz", ""),
        ("gender", "other"),
        ("wellbeing_code", "option_9"),
        ("weight_kg", 72.55),
        ("weight_kg", 29.9),
        ("weight_kg", 300.1),
        ("weight_kg", "abc"),
        ("weight_kg", True),
    ],
)
def test_submit_body_validation_422(api_client, field, value):
    resp = _post(api_client, {**GOOD_BODY, field: value})
    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("op_id", [None, str(uuid.uuid1())])
def test_submit_op_id_missing_or_not_v4_422(api_client, op_id):
    resp = _post(api_client, GOOD_BODY, op_id=op_id)
    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "VALIDATION_ERROR"


def test_submit_valid_db_unavailable_503(api_client):
    resp = _post(api_client, {**GOOD_BODY, "city": "Омск", "phone": "+70000000000"})
    assert resp.status_code == 503, resp.text
    assert resp.json()["code"] == "SERVICE_UNAVAILABLE"
