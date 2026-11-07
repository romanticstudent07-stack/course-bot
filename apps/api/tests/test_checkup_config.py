"""api-i3-1: конфиг Чек-Апа, score_and_zone, GET config и валидация POST submit — без БД."""
from __future__ import annotations

import copy
import json
import uuid

import pytest

import app.checkup_config
from app.checkup_config import (
    CheckupConfigError,
    get_checkup_config,
    load_checkup_config,
    score_and_zone,
)
from tests.conftest import valid_init_data

STUB = "Заглушка"


@pytest.fixture(autouse=True)
def _clear_cache():
    get_checkup_config.cache_clear()
    yield
    get_checkup_config.cache_clear()


def _good() -> dict:
    return json.loads(app.checkup_config.CHECKUP_CONFIG_PATH.read_text(encoding="utf-8"))


def _write(tmp_path, data) -> object:
    path = tmp_path / "bad.json"
    text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------- настоящий файл ----------------------------


def test_real_config_loads_and_all_texts_are_stubs():
    cfg = get_checkup_config()
    assert cfg.version.strip()
    assert len(cfg.questions) == 15
    assert [q.id for q in cfg.questions] == [f"q{i:02d}" for i in range(1, 16)]
    assert len(cfg.blocks) == 4
    assert [z.id for z in cfg.zones] == ["green", "yellow", "red"]
    assert [(z.min, z.max) for z in cfg.zones] == [(0, 9), (10, 22), (23, 45)]
    assert all(z.legal_status == "pre-legal-review" for z in cfg.zones)
    texts = [b.title for b in cfg.blocks] + [q.text for q in cfg.questions]
    texts += [z.title for z in cfg.zones] + [z.text for z in cfg.zones] + [cfg.disclaimer]
    assert all(t.startswith(STUB) for t in texts)


# ---------------------------- score_and_zone ----------------------------


@pytest.mark.parametrize(
    ("answers", "score", "zone"),
    [
        ([0] * 15, 0, "green"),
        ([3, 3, 3] + [0] * 12, 9, "green"),
        ([3, 3, 3, 1] + [0] * 11, 10, "yellow"),
        ([3] * 7 + [1] + [0] * 7, 22, "yellow"),
        ([3] * 7 + [2] + [0] * 7, 23, "red"),
        ([3] * 15, 45, "red"),
    ],
)
def test_score_and_zone_boundaries(answers, score, zone):
    assert sum(answers) == score
    assert score_and_zone(answers, get_checkup_config()) == (score, zone)


# ---------------------------- битый конфиг ----------------------------


def _zone(data, zone_id):
    return next(z for z in data["zones"] if z["id"] == zone_id)


def _gap(d):
    _zone(d, "yellow")["min"] = 11


def _overlap(d):
    _zone(d, "yellow")["min"] = 9


def _first_min_1(d):
    _zone(d, "green")["min"] = 1


def _last_max_44(d):
    _zone(d, "red")["max"] = 44


def _q14(d):
    d["questions"] = d["questions"][:14]


def _q16(d):
    d["questions"].append({"id": "q16", "block": 4, "text": "Заглушка: 16"})


def _dup_qid(d):
    d["questions"][1]["id"] = d["questions"][0]["id"]


def _block_5(d):
    d["questions"][0]["block"] = 5


def _scale_max_4(d):
    d["scale"]["max"] = 4


def _no_version(d):
    del d["version"]


def _empty_version(d):
    d["version"] = "   "


def _long_version(d):
    d["version"] = "v" * 65


def _zone_order(d):
    d["zones"][0], d["zones"][1] = d["zones"][1], d["zones"][0]


def _empty_disclaimer(d):
    d["disclaimer"] = ""


def _legal_draft(d):
    d["zones"][2]["legal_status"] = "draft"


@pytest.mark.parametrize(
    "mutate",
    [
        _gap,
        _overlap,
        _first_min_1,
        _last_max_44,
        _q14,
        _q16,
        _dup_qid,
        _block_5,
        _scale_max_4,
        _no_version,
        _empty_version,
        _long_version,
        _zone_order,
        _empty_disclaimer,
        _legal_draft,
    ],
)
def test_broken_config_raises(tmp_path, mutate):
    data = copy.deepcopy(_good())
    mutate(data)
    with pytest.raises(CheckupConfigError):
        load_checkup_config(_write(tmp_path, data))


def test_not_json_raises(tmp_path):
    with pytest.raises(CheckupConfigError):
        load_checkup_config(_write(tmp_path, "{not json"))


def test_missing_file_raises(tmp_path):
    with pytest.raises(CheckupConfigError):
        load_checkup_config(tmp_path / "nope.json")


def test_version_64_chars_ok(tmp_path):
    data = _good()
    data["version"] = "v" * 64
    assert load_checkup_config(_write(tmp_path, data)).version == "v" * 64


def test_create_app_fails_on_broken_config(tmp_path, monkeypatch):
    data = _good()
    _gap(data)
    monkeypatch.setattr(app.checkup_config, "CHECKUP_CONFIG_PATH", _write(tmp_path, data))
    get_checkup_config.cache_clear()
    from main import create_app

    with pytest.raises(CheckupConfigError):
        create_app()


# ---------------------------- GET /checkup/config ----------------------------


def _keys(obj) -> set[str]:
    if isinstance(obj, dict):
        return set(obj) | {k for v in obj.values() for k in _keys(v)}
    if isinstance(obj, list):
        return {k for v in obj for k in _keys(v)}
    return set()


def test_get_config_200_without_bounds_and_score(api_client):
    resp = api_client.get(
        "/miniapp/v1/checkup/config", headers={"X-Telegram-Init-Data": valid_init_data()}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"version", "scale", "blocks", "questions", "zones", "disclaimer"}
    assert body["scale"] == {"min": 0, "max": 3}
    assert len(body["questions"]) == 15 and len(body["blocks"]) == 4
    for zone in body["zones"]:
        assert set(zone) == {"id", "title", "text"}
    assert "score" not in _keys(body)
    assert not {"min", "max", "legal_status"} & _keys(body["zones"])


# ---------------------------- POST /checkup/submit (валидация) ----------------------------


def _post(client, body, op_id: str | None = "new"):
    headers = {"X-Telegram-Init-Data": valid_init_data()}
    if op_id == "new":
        op_id = str(uuid.uuid4())
    if op_id is not None:
        headers["X-Client-Op-Id"] = op_id
    return client.post("/miniapp/v1/checkup/submit", json=body, headers=headers)


GOOD_BODY = {"occasion": "onboarding", "answers": [1] * 15}


def _assert_422(resp):
    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "VALIDATION_ERROR"


def test_submit_without_op_id_422(api_client):
    _assert_422(_post(api_client, GOOD_BODY, op_id=None))


def test_submit_op_id_not_v4_422(api_client):
    _assert_422(_post(api_client, GOOD_BODY, op_id=str(uuid.uuid1())))


def test_submit_op_id_not_uuid_422(api_client):
    _assert_422(_post(api_client, GOOD_BODY, op_id="not-a-uuid"))


def test_submit_stage_end_422(api_client):
    _assert_422(_post(api_client, {"occasion": "stage_end", "answers": [1] * 15}))


def test_submit_14_answers_422(api_client):
    _assert_422(_post(api_client, {"occasion": "onboarding", "answers": [1] * 14}))


def test_submit_16_answers_422(api_client):
    _assert_422(_post(api_client, {"occasion": "onboarding", "answers": [1] * 16}))


def test_submit_answer_4_422(api_client):
    _assert_422(_post(api_client, {"occasion": "onboarding", "answers": [4] + [0] * 14}))


def test_submit_answer_negative_422(api_client):
    _assert_422(_post(api_client, {"occasion": "onboarding", "answers": [-1] + [0] * 14}))


def test_submit_answer_true_422(api_client):
    _assert_422(_post(api_client, {"occasion": "onboarding", "answers": [True] + [0] * 14}))


def test_submit_answer_string_422(api_client):
    _assert_422(_post(api_client, {"occasion": "onboarding", "answers": ["1"] + [0] * 14}))


def test_submit_valid_db_unavailable_503(api_client):
    resp = _post(api_client, GOOD_BODY)
    assert resp.status_code == 503, resp.text
    assert resp.json()["code"] == "SERVICE_UNAVAILABLE"
