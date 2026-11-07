"""api-i3-1: POST /miniapp/v1/checkup/submit с БД (DATABASE_URL; в CI обязательно).

Пишется только measurements_log. Тексты text_registry фикстура не откатывает →
тест смены текста возвращает его в finally (как test_onboarding_status.py).
"""
from __future__ import annotations

import logging
import uuid

import pytest
from sqlalchemy import text

from app.checkup_config import get_checkup_config
from app.consent_status import ConsentTextMissingError
from app.telegram_init_data import INIT_DATA_HEADER
from tests.conftest import _database_url, grant_access, valid_init_data

SUBMIT = "/miniapp/v1/checkup/submit"
FIRST_LAUNCH = "/miniapp/v1/onboarding/first-launch"
FL_BODY = {"birth_date": "1990-01-01", "consents": ["C0", "C1"]}
C0_KEY = "legal.consent_c0_age_18_plus"
C1_KEY = "legal.consent_c1_pdn"
LOGGER = "app.checkup"


@pytest.fixture(autouse=True)
def _clear_cache():
    get_checkup_config.cache_clear()
    yield
    get_checkup_config.cache_clear()


@pytest.fixture
def clean_measurements(db_engine):
    # measurements_log FK на tg_user_registry: TRUNCATE ... CASCADE в db_engine её чистит,
    # но явная очистка не зависит от порядка фикстур.
    with db_engine.begin() as conn:
        conn.execute(text("TRUNCATE measurements_log RESTART IDENTITY"))
    yield db_engine


def _headers(user_id: int, op_id: str | None = None) -> dict[str, str]:
    headers = {INIT_DATA_HEADER: valid_init_data(user={"id": user_id, "first_name": "Test"})}
    headers["X-Client-Op-Id"] = op_id or str(uuid.uuid4())
    return headers


def _first_launch(client, user_id: int) -> str:
    grant_access(_database_url(), user_id)
    r = client.post(
        FIRST_LAUNCH,
        json=FL_BODY,
        headers={INIT_DATA_HEADER: valid_init_data(user={"id": user_id, "first_name": "Test"})},
    )
    assert r.status_code == 201, r.text
    return r.json()["pid"]


def _submit(client, user_id: int, answers, op_id: str | None = None, **extra):
    body = {"occasion": "onboarding", "answers": answers, **extra}
    return client.post(SUBMIT, json=body, headers=_headers(user_id, op_id))


def _rows(engine, pid: str | None = None) -> list:
    sql = (
        "SELECT kind, occasion, stage_no, checkup_answers, checkup_score, checkup_zone, "
        "checkup_config_version, client_op_id FROM measurements_log"
    )
    params = {}
    if pid is not None:
        sql += " WHERE pid = :p"
        params["p"] = uuid.UUID(pid)
    with engine.connect() as conn:
        return conn.execute(text(sql + " ORDER BY id"), params).all()


def _revoke(engine, pid: str, kind: str) -> None:
    key = C0_KEY if kind == "C0" else C1_KEY
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO consent_events "
                "(pid, kind, action, at, ver_of_text, text_key, text_snapshot, created_via) "
                "VALUES (:pid, :k, 'revoke', now(), '0.2.0', :t, "
                "'[ЗАГЛУШКА] x', 'mini_app_first_launch')"
            ),
            {"pid": uuid.UUID(pid), "k": kind, "t": key},
        )


def _get_text(engine, key: str) -> str:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT text FROM text_registry WHERE key = :k"), {"k": key}
        ).scalar_one()


def _set_text(engine, key: str, value: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE text_registry SET text = :v WHERE key = :k"), {"v": value, "k": key}
        )


# ---------------------------- зоны и строка ----------------------------


@pytest.mark.parametrize(
    ("user_id", "answers", "score", "zone"),
    [
        (5101, [3, 3, 3] + [0] * 12, 9, "green"),
        (5102, [3, 3, 3, 1] + [0] * 11, 10, "yellow"),
        (5103, [3] * 7 + [1] + [0] * 7, 22, "yellow"),
        (5104, [3] * 7 + [2] + [0] * 7, 23, "red"),
    ],
)
def test_submit_boundaries_write_row(db_api_client, clean_measurements, user_id, answers, score, zone):
    pid = _first_launch(db_api_client, user_id)
    op_id = str(uuid.uuid4())
    r = _submit(db_api_client, user_id, answers, op_id)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"zone", "config_version", "created_at"}
    assert body["zone"] == zone
    assert body["config_version"] == get_checkup_config().version
    assert "score" not in r.text
    rows = _rows(clean_measurements, pid)
    assert len(rows) == 1
    row = rows[0]
    assert row.kind == "checkup"
    assert row.occasion == "onboarding"
    assert row.stage_no is None
    assert list(row.checkup_answers) == answers
    assert row.checkup_score == score
    assert row.checkup_zone == zone
    assert row.checkup_config_version == get_checkup_config().version
    assert row.client_op_id == op_id


def test_client_score_and_zone_ignored(db_api_client, clean_measurements):
    pid = _first_launch(db_api_client, 5201)
    r = _submit(db_api_client, 5201, [0] * 15, score=45, zone="red", stage_no=3)
    assert r.status_code == 200, r.text
    assert r.json()["zone"] == "green"
    rows = _rows(clean_measurements, pid)
    assert len(rows) == 1
    assert rows[0].checkup_score == 0
    assert rows[0].checkup_zone == "green"
    assert rows[0].stage_no is None


# ---------------------------- идемпотентность ----------------------------


def test_repeat_op_id_returns_same_without_new_row(db_api_client, clean_measurements):
    pid = _first_launch(db_api_client, 5301)
    op_id = str(uuid.uuid4())
    first = _submit(db_api_client, 5301, [0] * 15, op_id)
    assert first.status_code == 200, first.text
    again = _submit(db_api_client, 5301, [3] * 15, op_id)
    assert again.status_code == 200, again.text
    assert again.json() == first.json()
    rows = _rows(clean_measurements, pid)
    assert len(rows) == 1
    assert rows[0].checkup_score == 0
    other = _submit(db_api_client, 5301, [3] * 15)
    assert other.status_code == 200, other.text
    assert other.json()["zone"] == "red"
    assert len(_rows(clean_measurements, pid)) == 2


# ---------------------------- ошибки, строк 0 ----------------------------


def test_no_participant_404(db_api_client, clean_measurements):
    r = _submit(db_api_client, 5401, [1] * 15)
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "PARTICIPANT_NOT_FOUND"
    assert _rows(clean_measurements) == []


def test_revoked_c1_409(db_api_client, clean_measurements):
    pid = _first_launch(db_api_client, 5501)
    _revoke(clean_measurements, pid, "C1")
    r = _submit(db_api_client, 5501, [1] * 15)
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "RECONSENT_REQUIRED"
    assert _rows(clean_measurements) == []


def test_text_changed_409(db_api_client, clean_measurements):
    _first_launch(db_api_client, 5601)
    old = _get_text(clean_measurements, C1_KEY)
    _set_text(clean_measurements, C1_KEY, old + " (новая редакция)")
    try:
        r = _submit(db_api_client, 5601, [1] * 15)
    finally:
        _set_text(clean_measurements, C1_KEY, old)
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "RECONSENT_REQUIRED"
    assert _rows(clean_measurements) == []


def test_consent_text_missing_503(db_api_client, clean_measurements, monkeypatch):
    _first_launch(db_api_client, 5701)

    def _no_text(session, kinds):
        raise ConsentTextMissingError([C0_KEY])

    # Подмена там, где её вызывает checkup; тексты в БД не меняются.
    monkeypatch.setattr("app.routers.checkup.current_texts", _no_text)
    r = _submit(db_api_client, 5701, [1] * 15)
    assert r.status_code == 503, r.text
    assert r.json()["code"] == "SERVICE_MISCONFIGURED"
    assert _rows(clean_measurements) == []


# ---------------------------- лог ----------------------------


def test_log_has_no_health_data(db_api_client, clean_measurements, caplog):
    pid = _first_launch(db_api_client, 5801)
    op_id = str(uuid.uuid4())
    answers = [3] * 7 + [2] + [0] * 7
    caplog.set_level(logging.INFO, logger=LOGGER)
    assert _submit(db_api_client, 5801, answers, op_id).status_code == 200
    assert _submit(db_api_client, 5801, answers, op_id).status_code == 200
    records = [r.getMessage() for r in caplog.records if r.name == LOGGER]
    assert records, "нет записей app.checkup"
    joined = "\n".join(records)
    assert "tg_user_id=5801" in joined
    assert "status=created" in joined and "status=repeat" in joined
    assert pid not in joined
    assert op_id not in joined
    assert str(answers) not in joined
    assert ",".join(map(str, answers)) not in joined
    assert "23" not in joined
    assert "score" not in joined
    # "red" есть внутри "status=created" — проверяем ключ и значение зоны отдельно.
    assert "zone" not in joined
    assert "=red" not in joined and " red" not in joined
