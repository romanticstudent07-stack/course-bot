"""api-i3-3: GET /miniapp/v1/me/card и /me/change-map (тесты 1–10 карточки api-i3-3 §9).

Тесты с БД — DATABASE_URL (в CI обязательно). Строки stage_end вставляются напрямую
через db_engine (владелец): у API записи в БД здесь нет.
"""
from __future__ import annotations

import logging
import uuid

import pytest
from sqlalchemy import text

from app.checkup_config import get_checkup_config
from app.onboarding_form_config import get_onboarding_form_config
from app.routers.me import build_position
from app.telegram_init_data import INIT_DATA_HEADER
from tests.conftest import _database_url, grant_access, valid_init_data

CARD = "/miniapp/v1/me/card"
CHANGE_MAP = "/miniapp/v1/me/change-map"
FORM = "/miniapp/v1/onboarding/form"
CHECKUP = "/miniapp/v1/checkup/submit"
FIRST_LAUNCH = "/miniapp/v1/onboarding/first-launch"
FL_BODY = {"birth_date": "1990-01-01", "consents": ["C0", "C1"]}
FORM_BODY = {"tz": "Asia/Omsk", "gender": "female", "wellbeing_code": "option_3", "weight_kg": 72.5}
LOGGER = "app.me"

CARD_KEYS = {"short_no", "registered_at", "tz", "position", "lives", "measurements"}
MEASUREMENT_KEYS = {
    "weight_start_kg",
    "weight_current_kg",
    "checkup_completed",
    "zone_start",
    "zone_last",
}

_INSERT_BODY_SQL = text(
    "INSERT INTO measurements_log (pid, kind, occasion, stage_no, weight_kg, client_op_id, "
    "created_at) VALUES (:pid, 'body', 'stage_end', 1, :w, :op, now() + make_interval(mins => :m))"
)
_INSERT_CHECKUP_SQL = text(
    "INSERT INTO measurements_log (pid, kind, occasion, stage_no, checkup_answers, "
    "checkup_score, checkup_zone, checkup_config_version, client_op_id, created_at) "
    "VALUES (:pid, 'checkup', 'stage_end', 1, CAST(:a AS smallint[]), :s, :z, 'test', :op, "
    "now() + make_interval(mins => :m))"
)


@pytest.fixture(autouse=True)
def _clear_cache():
    get_checkup_config.cache_clear()
    get_onboarding_form_config.cache_clear()
    yield
    get_checkup_config.cache_clear()
    get_onboarding_form_config.cache_clear()


@pytest.fixture
def clean_me(db_engine):
    with db_engine.begin() as conn:
        conn.execute(text("TRUNCATE onboarding_form, measurements_log RESTART IDENTITY"))
    yield db_engine


def _init(user_id: int) -> dict[str, str]:
    return {INIT_DATA_HEADER: valid_init_data(user={"id": user_id, "first_name": "Test"})}


def _first_launch(client, user_id: int) -> str:
    grant_access(_database_url(), user_id)
    r = client.post(FIRST_LAUNCH, json=FL_BODY, headers=_init(user_id))
    assert r.status_code == 201, r.text
    return r.json()["pid"]


def _post_form(client, user_id: int) -> None:
    headers = {**_init(user_id), "X-Client-Op-Id": str(uuid.uuid4())}
    r = client.post(FORM, json=FORM_BODY, headers=headers)
    assert r.status_code == 200, r.text


def _post_checkup(client, user_id: int, answers: list[int]) -> str:
    headers = {**_init(user_id), "X-Client-Op-Id": str(uuid.uuid4())}
    r = client.post(CHECKUP, json={"occasion": "onboarding", "answers": answers}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["zone"]


def _insert_body(engine, pid: str, weight: float, minutes: int) -> None:
    with engine.begin() as conn:
        conn.execute(
            _INSERT_BODY_SQL,
            {"pid": uuid.UUID(pid), "w": weight, "op": str(uuid.uuid4()), "m": minutes},
        )


def _insert_checkup(engine, pid: str, answers: list[int], zone: str, minutes: int) -> None:
    with engine.begin() as conn:
        conn.execute(
            _INSERT_CHECKUP_SQL,
            {
                "pid": uuid.UUID(pid),
                "a": answers,
                "s": sum(answers),
                "z": zone,
                "op": str(uuid.uuid4()),
                "m": minutes,
            },
        )


def _layers(client, user_id: int) -> dict[str, dict]:
    r = client.get(CHANGE_MAP, headers=_init(user_id))
    assert r.status_code == 200, r.text
    return {layer["layer"]: layer for layer in r.json()["layers"]}


# 1
@pytest.mark.parametrize("path", [CARD, CHANGE_MAP])
def test_no_participant_404(db_api_client, clean_me, path):
    r = db_api_client.get(path, headers=_init(7101))
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "PARTICIPANT_NOT_FOUND"


# 2
def test_card_after_first_launch_only(db_api_client, clean_me):
    _first_launch(db_api_client, 7201)
    r = db_api_client.get(CARD, headers=_init(7201))
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == CARD_KEYS
    assert set(body["measurements"]) == MEASUREMENT_KEYS
    assert body["short_no"].startswith("#")
    assert body["registered_at"]
    assert body["tz"] is None
    assert body["position"] is None
    assert body["lives"] == 3
    assert body["measurements"] == {
        "weight_start_kg": None,
        "weight_current_kg": None,
        "checkup_completed": False,
        "zone_start": None,
        "zone_last": None,
    }


# 3
def test_card_after_form_and_checkup(db_api_client, clean_me):
    _first_launch(db_api_client, 7301)
    _post_form(db_api_client, 7301)
    zone = _post_checkup(db_api_client, 7301, [0] * 15)
    r = db_api_client.get(CARD, headers=_init(7301))
    assert r.status_code == 200, r.text
    m = r.json()["measurements"]
    assert m["weight_start_kg"] == m["weight_current_kg"] == FORM_BODY["weight_kg"]
    assert m["checkup_completed"] is True
    assert m["zone_start"] == m["zone_last"] == zone
    assert "score" not in r.text
    assert "answers" not in r.text


# 4
def test_card_stage_end_rows_update_current(db_api_client, clean_me):
    pid = _first_launch(db_api_client, 7401)
    _post_form(db_api_client, 7401)
    zone = _post_checkup(db_api_client, 7401, [0] * 15)
    assert zone == "green"
    _insert_body(clean_me, pid, 70.0, 10)
    _insert_checkup(clean_me, pid, [3] * 15, "red", 10)
    r = db_api_client.get(CARD, headers=_init(7401))
    assert r.status_code == 200, r.text
    m = r.json()["measurements"]
    assert m["weight_start_kg"] == FORM_BODY["weight_kg"]
    assert m["weight_current_kg"] == 70.0
    assert m["zone_start"] == "green"
    assert m["zone_last"] == "red"
    assert m["checkup_completed"] is True


# 5
def test_change_map_empty(db_api_client, clean_me):
    _first_launch(db_api_client, 7501)
    r = db_api_client.get(CHANGE_MAP, headers=_init(7501))
    assert r.status_code == 200, r.text
    layers = r.json()["layers"]
    assert [x["layer"] for x in layers] == ["anthro", "wellbeing", "checkup", "functional"]
    assert [x["metric"] for x in layers] == [
        "weight_kg",
        "wellbeing_code",
        "inflammation_zone",
        None,
    ]
    for layer in layers:
        assert set(layer) == {"layer", "metric", "baseline", "recent"}
        assert layer["baseline"] is None
        assert layer["recent"] == []


# 6
def test_change_map_baseline_and_recent(db_api_client, clean_me):
    pid = _first_launch(db_api_client, 7601)
    _post_form(db_api_client, 7601)
    weights = [71.0, 70.5, 70.0, 69.5, 69.0, 68.5]
    for i, w in enumerate(weights, start=1):
        _insert_body(clean_me, pid, w, i)
    layers = _layers(db_api_client, 7601)
    anthro = layers["anthro"]
    assert anthro["baseline"]["value"] == FORM_BODY["weight_kg"]
    assert [p["value"] for p in anthro["recent"]] == weights[-5:]
    ats = [p["at"] for p in anthro["recent"]]
    assert ats == sorted(ats)
    assert layers["wellbeing"]["baseline"]["value"] == FORM_BODY["wellbeing_code"]
    assert layers["wellbeing"]["recent"] == []


# 7
def test_change_map_tie_break_min_id(db_api_client, clean_me):
    pid = _first_launch(db_api_client, 7701)
    with clean_me.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO measurements_log (pid, kind, occasion, stage_no, weight_kg, "
                "client_op_id, created_at) VALUES "
                "(:pid, 'body', 'stage_end', 1, 80.0, :op1, '2026-11-01T10:00:00Z'), "
                "(:pid, 'body', 'stage_end', 1, 79.0, :op2, '2026-11-01T10:00:00Z')"
            ),
            {"pid": uuid.UUID(pid), "op1": str(uuid.uuid4()), "op2": str(uuid.uuid4())},
        )
    anthro = _layers(db_api_client, 7701)["anthro"]
    assert anthro["baseline"]["value"] == 80.0
    assert [p["value"] for p in anthro["recent"]] == [79.0]


# 8
@pytest.mark.parametrize("path", [CARD, CHANGE_MAP])
def test_db_unavailable_503(api_client, path):
    r = api_client.get(path, headers=_init(7801))
    assert r.status_code == 503, r.text
    assert r.json()["code"] == "SERVICE_UNAVAILABLE"


# 9
def test_log_has_no_pid_weight_zone(db_api_client, clean_me, caplog):
    pid = _first_launch(db_api_client, 7901)
    _post_form(db_api_client, 7901)
    zone = _post_checkup(db_api_client, 7901, [3] * 15)
    caplog.set_level(logging.INFO, logger=LOGGER)
    assert db_api_client.get(CARD, headers=_init(7901)).status_code == 200
    assert db_api_client.get(CHANGE_MAP, headers=_init(7901)).status_code == 200
    records = [r.getMessage() for r in caplog.records if r.name == LOGGER]
    assert records, "нет записей app.me"
    joined = "\n".join(records)
    assert "tg_user_id=7901" in joined
    assert pid not in joined
    for word in ("72.5", "weight", "zone", "=" + zone, " " + zone, "option_3"):
        assert word not in joined


# 10
@pytest.mark.parametrize(
    ("stage_no", "module_no", "day_no"),
    [(None, 1, 1), (1, None, 1), (1, 1, None), (None, None, None)],
)
def test_build_position_none_if_any_null(stage_no, module_no, day_no):
    assert build_position(stage_no, module_no, day_no) is None


def test_build_position_object_when_all_set():
    pos = build_position(2, 3, 4)
    assert pos is not None
    assert (pos.stage_no, pos.module_no, pos.day_no) == (2, 3, 4)
