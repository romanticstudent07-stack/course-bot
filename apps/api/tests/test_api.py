"""Тесты API: health, онбординг-мок, CSP-репорт. initData подписана по-настоящему."""
from datetime import date

import pytest

from app.routers.onboarding import full_years
from app.telegram_init_data import INIT_DATA_HEADER
from tests.conftest import TEST_USER_ID, valid_init_data

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


def test_first_launch_underage_is_403_and_no_pid(api_client):
    today = date.today()
    minor = today.replace(year=today.year - 17).isoformat() if not (
        today.month == 2 and today.day == 29
    ) else date(today.year - 17, 2, 28).isoformat()
    r = api_client.post(
        FIRST_LAUNCH, json={"birth_date": minor}, headers={INIT_DATA_HEADER: valid_init_data()}
    )
    assert r.status_code == 403
    assert r.json()["code"] == "AGE_GATE_UNDERAGE"
    assert "pid" not in r.json()


def test_first_launch_adult_is_mock_501_with_tg_user_id(api_client):
    r = api_client.post(
        FIRST_LAUNCH,
        json={"birth_date": "1990-01-01"},
        headers={INIT_DATA_HEADER: valid_init_data()},
    )
    assert r.status_code == 501
    body = r.json()
    assert body["code"] == "NOT_IMPLEMENTED"
    assert body["details"] == {"tg_user_id": TEST_USER_ID}
    assert "pid" not in body


def test_first_launch_future_birth_date(api_client):
    r = api_client.post(
        FIRST_LAUNCH,
        json={"birth_date": "2999-01-01"},
        headers={INIT_DATA_HEADER: valid_init_data()},
    )
    assert r.status_code == 422


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
