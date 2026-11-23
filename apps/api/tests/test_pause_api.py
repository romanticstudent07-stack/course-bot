"""api-pause-2 (T3): маршруты паузы без БД — 401, 422, формат ключей (карточка §8).

tg_user_id 8801–8899 (свой диапазон, не пересекается с test_support_db.py).
"""
from __future__ import annotations

import uuid

import pytest

from app.day_keys import (
    KIND_PAUSE_CANCEL,
    KIND_PAUSE_OP,
    KIND_PAUSE_REQUEST,
    KIND_PAUSE_RESUME,
    TTL_BY_KIND,
    key_pause_cancel,
    key_pause_op,
    key_pause_request,
    key_pause_resume,
)
from app.telegram_init_data import INIT_DATA_HEADER
from tests.conftest import valid_init_data

PREFIX = "/miniapp/v1"
ROUTES = (
    ("get", "/pause"),
    ("post", "/pause/request"),
    ("post", "/pause/cancel"),
    ("post", "/pause/resume"),
)
PID = uuid.UUID("00000000-0000-4000-8000-000000008801")


def _init(user_id: int) -> str:
    return valid_init_data(user={"id": user_id, "first_name": "Test"})


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_no_init_data_is_401(api_client, method, path):
    kwargs: dict = {}
    if path == "/pause/request":
        kwargs = {"json": {"days": 1, "start_date": "2026-11-21"}}
    elif path in ("/pause/cancel", "/pause/resume"):
        kwargs = {"json": {"pause_id": 1}}
    headers = {"X-Client-Op-Id": str(uuid.uuid4())}
    r = getattr(api_client, method)(PREFIX + path, headers=headers, **kwargs)
    assert r.status_code == 401, r.text
    assert r.json()["code"] == "TG_INIT_MISSING"


@pytest.mark.parametrize("days", [0, 8, "x"])
def test_days_out_of_range_is_422(api_client, days):
    headers = {INIT_DATA_HEADER: _init(8802), "X-Client-Op-Id": str(uuid.uuid4())}
    body = {"days": days, "start_date": "2026-11-21"}
    r = api_client.post(PREFIX + "/pause/request", json=body, headers=headers)
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("op", [None, str(uuid.uuid1())])
def test_op_id_missing_or_not_v4_is_422(api_client, op):
    headers = {INIT_DATA_HEADER: _init(8803)}
    if op is not None:
        headers["X-Client-Op-Id"] = op
    body = {"days": 1, "start_date": "2026-11-21"}
    r = api_client.post(PREFIX + "/pause/request", json=body, headers=headers)
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("body", [{"days": 1}, {"days": 1, "start_date": "21.11.2026"}])
def test_start_date_missing_or_bad_is_422(api_client, body):
    headers = {INIT_DATA_HEADER: _init(8804), "X-Client-Op-Id": str(uuid.uuid4())}
    r = api_client.post(PREFIX + "/pause/request", json=body, headers=headers)
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "VALIDATION_ERROR"


def test_key_formats():
    assert key_pause_cancel(PID, 7) == f"pause_cancel:{PID}:7"
    assert key_pause_resume(PID, 7) == f"pause_resume:{PID}:7"
    assert (KIND_PAUSE_CANCEL, KIND_PAUSE_RESUME) == ("pause_cancel", "pause_resume")
    assert TTL_BY_KIND[KIND_PAUSE_CANCEL] == TTL_BY_KIND[KIND_PAUSE_RESUME] == "3650 days"
    op = "11111111-1111-4111-8111-111111111111"
    assert key_pause_request(PID, op) == f"pause_request:{PID}:{op}"
    assert KIND_PAUSE_REQUEST == "pause_request"
    assert TTL_BY_KIND[KIND_PAUSE_REQUEST] == "3650 days"
    assert key_pause_op(PID, op) == f"pause_op:{PID}:{op}"
    assert KIND_PAUSE_OP == "pause_op"
    assert TTL_BY_KIND[KIND_PAUSE_OP] == "3650 days"


# ---------------------------- pause-api-a4 ----------------------------

_TARGET_CASES = (
    ("no_op", None, {"pause_id": 1}),
    ("op_v1", str(uuid.uuid1()), {"pause_id": 1}),
    ("no_body", "v4", None),
    ("pause_id_str", "v4", {"pause_id": "x"}),
)


@pytest.mark.parametrize("path", ["/pause/cancel", "/pause/resume"])
@pytest.mark.parametrize(
    ("case", "op", "body"), _TARGET_CASES, ids=[c[0] for c in _TARGET_CASES]
)
def test_target_validation_is_422(api_client, path, case, op, body):
    headers = {INIT_DATA_HEADER: _init(8805)}
    if op is not None:
        headers["X-Client-Op-Id"] = str(uuid.uuid4()) if op == "v4" else op
    kwargs = {"json": body} if body is not None else {}
    r = api_client.post(PREFIX + path, headers=headers, **kwargs)
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("path", ["/pause/cancel", "/pause/resume"])
def test_no_init_data_without_body_is_401(api_client, path):
    r = api_client.post(PREFIX + path)
    assert r.status_code == 401, r.text
    assert r.json()["code"] == "TG_INIT_MISSING"
