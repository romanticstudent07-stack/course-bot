"""Тесты API: health, отказ first-launch без initData, full_years, CSP-репорт.

First-launch с БД и возрастной гейт — tests/test_first_launch.py.
"""
from datetime import date

import pytest

from app.routers.onboarding import full_years
from app.telegram_init_data import INIT_DATA_HEADER

FIRST_LAUNCH = "/miniapp/v1/onboarding/first-launch"


def test_healthz(api_client):
    r = api_client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_first_launch_requires_init_data(api_client):
    r = api_client.post(FIRST_LAUNCH, json={"birth_date": "1990-01-01"})
    assert r.status_code == 401
    assert r.json()["code"] == "TG_INIT_MISSING"


def test_first_launch_rejects_init_data_without_hash(api_client):
    r = api_client.post(
        FIRST_LAUNCH,
        json={"birth_date": "1990-01-01"},
        headers={INIT_DATA_HEADER: "auth_date=1"},
    )
    assert r.status_code == 401
    assert r.json()["code"] == "TG_INIT_INVALID"


@pytest.mark.parametrize(
    ("birth", "today", "expected"),
    [
        (date(2000, 5, 10), date(2018, 5, 9), 17),
        (date(2000, 5, 10), date(2018, 5, 10), 18),
        (date(2000, 2, 29), date(2018, 2, 28), 17),
        (date(2000, 2, 29), date(2018, 3, 1), 18),
    ],
)
def test_full_years(birth, today, expected):
    assert full_years(birth, today) == expected


def test_csp_report_accepted(api_client):
    r = api_client.post(
        "/security/csp-report",
        content=b'{"csp-report":{}}',
        headers={"Content-Type": "application/csp-report"},
    )
    assert r.status_code == 204
