"""api-pause-2 (T3): маршруты паузы без БД — 401, 422, формат ключей (карточка §8).

tg_user_id 8801–8899 (свой диапазон, не пересекается с test_support_db.py).
"""
from __future__ import annotations

import uuid

import pytest

from app.day_keys import (
    KIND_PAUSE_CANCEL,
    KIND_PAUSE_RESUME,
    TTL_BY_KIND,
    key_pause_cancel,
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
    kwargs = {"json": {"days": 1}} if path == "/pause/request" else {}
    headers = {"X-Client-Op-Id": str(uuid.uuid4())}
    r = getattr(api_client, method)(PREFIX + path, headers=headers, **kwargs)
    assert r.status_code == 401, r.text
    assert r.json()["code"] == "TG_INIT_MISSING"


@pytest.mark.parametrize("days", [0, 8, "x"])
def test_days_out_of_range_is_422(api_client, days):
    headers = {INIT_DATA_HEADER: _init(8802), "X-Client-Op-Id": str(uuid.uuid4())}
    r = api_client.post(PREFIX + "/pause/request", json={"days": days}, headers=headers)
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("op", [None, str(uuid.uuid1())])
def test_op_id_missing_or_not_v4_is_422(api_client, op):
    headers = {INIT_DATA_HEADER: _init(8803)}
    if op is not None:
        headers["X-Client-Op-Id"] = op
    r = api_client.post(PREFIX + "/pause/request", json={"days": 1}, headers=headers)
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "VALIDATION_ERROR"


def test_key_formats():
    assert key_pause_cancel(PID, 7) == f"pause_cancel:{PID}:7"
    assert key_pause_resume(PID, 7) == f"pause_resume:{PID}:7"
    assert (KIND_PAUSE_CANCEL, KIND_PAUSE_RESUME) == ("pause_cancel", "pause_resume")
    assert TTL_BY_KIND[KIND_PAUSE_CANCEL] == TTL_BY_KIND[KIND_PAUSE_RESUME] == "3650 days"
