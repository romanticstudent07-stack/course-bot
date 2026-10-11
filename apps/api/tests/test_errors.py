"""B-3b: формат ошибок 422 / 500 (D-18) и hide_parameters у движка. Без БД."""
import logging
from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.db.session import _engine_for
from app.errors import install_error_handlers
from tests.conftest import valid_init_data

SECRET = "secret-param-123"
BAD_DATE = "1990-13-45"
FIRST_LAUNCH = "/miniapp/v1/onboarding/first-launch"
INIT_HEADER = "X-Telegram-Init-Data"


class _BirthBody(BaseModel):
    birth_date: date


def _make_app() -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError(SECRET)

    @app.post("/body")
    def body(payload: _BirthBody) -> dict[str, bool]:
        return {"ok": True}

    return app


def _assert_safe_validation_body(r) -> None:
    data = r.json()
    assert data["code"] == "VALIDATION_ERROR"
    assert data["message"] == "Неверный формат запроса."
    errors = data["details"]["errors"]
    assert errors, data
    for err in errors:
        assert set(err) == {"loc", "type"}, err


def test_unhandled_exception_is_500_without_text(caplog):
    caplog.set_level(logging.DEBUG)
    client = TestClient(_make_app(), raise_server_exceptions=False)
    r = client.get("/boom")
    assert r.status_code == 500
    assert r.json() == {
        "code": "INTERNAL_ERROR",
        "message": "Внутренняя ошибка. Попробуйте позже.",
    }
    assert SECRET not in r.text
    assert SECRET not in caplog.text
    assert "RuntimeError" in caplog.text


def test_validation_error_is_422_without_input():
    client = TestClient(_make_app(), raise_server_exceptions=False)
    r = client.post("/body", json={"birth_date": BAD_DATE})
    assert r.status_code == 422
    _assert_safe_validation_body(r)
    assert BAD_DATE not in r.text


def test_first_launch_bad_birth_date_is_422_without_value(api_client):
    r = api_client.post(
        FIRST_LAUNCH,
        headers={INIT_HEADER: valid_init_data()},
        json={"birth_date": BAD_DATE, "consents": ["C0", "C1"]},
    )
    assert r.status_code == 422, r.text
    _assert_safe_validation_body(r)
    assert BAD_DATE not in r.text


def test_first_launch_without_init_data_is_still_401(api_client):
    r = api_client.post(
        FIRST_LAUNCH,
        json={"birth_date": "1990-01-01", "consents": ["C0", "C1"]},
    )
    assert r.status_code == 401, r.text
    assert r.json()["code"] == "TG_INIT_MISSING"


def test_engine_hides_sql_parameters():
    engine = _engine_for("postgresql+psycopg://u:p@127.0.0.1:1/x")
    assert engine.hide_parameters is True
