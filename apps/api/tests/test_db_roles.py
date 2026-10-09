"""B-3a-1: роли app_api / app_projector и минимальные GRANT (миграция 0006, D-13).

Тесты с БД — только CI (соединение CI — суперпользователь, оно делает SET ROLE).
Живой код API и проектора гоняется под ролями; отказы — SQLSTATE 42501
(psycopg.errors.InsufficientPrivilege). Стоп-правило карточки: permission denied
в живых сценариях на право вне раздела 8 — права не расширять, ошибку отдать ШТАБу.
Тест downgrade — последним в файле; в finally схема возвращается на head.

conftest.py как модуль не импортируется (pytest подгружает его сам) — нужные константы
и подпись initData продублированы ниже; FAKE_BOT_TOKEN обязан совпадать с conftest.py.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import urlencode

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.telegram_init_data import compute_hash

# Те же значения, что в conftest.py.
FAKE_BOT_TOKEN = "123456:TEST-fake-token-for-pytest-only"
UNREACHABLE_DSN = "postgresql+psycopg://nobody:nopass@127.0.0.1:1/none"
API_DIR = Path(__file__).resolve().parents[1]

APP_ROLES = ("app_api", "app_projector")
FIRST_LAUNCH_URL = "/miniapp/v1/onboarding/first-launch"
STATUS_URL = "/miniapp/v1/onboarding/status"
CONSENTS_URL = "/miniapp/v1/consents"
FIRST_LAUNCH_BODY = {"birth_date": "1990-01-01", "consents": ["C0", "C1"]}

API_DENIED: tuple[str, ...] = (
    "INSERT INTO participant_state (pid) VALUES (gen_random_uuid())",
    "UPDATE participant_state SET updated_at = now()",
    "UPDATE consent_events SET ua = 'x'",
    "DELETE FROM consent_events",
    "TRUNCATE consent_events",
    "UPDATE participant_events SET actor = 'x'",
    "DELETE FROM participant_events",
    "TRUNCATE participant_events",
    "UPDATE tg_user_registry SET tombstoned_at = now()",
    "UPDATE tg_user_registry SET pid = gen_random_uuid()",
    "SELECT payload FROM participant_events",
    "INSERT INTO text_registry (key) VALUES ('x.y')",
)

PROJECTOR_DENIED: tuple[str, ...] = (
    "INSERT INTO tg_user_registry (tg_user_id) VALUES (1)",
    "SELECT pid FROM consent_events",
    "INSERT INTO participant_events (pid) VALUES (gen_random_uuid())",
    "UPDATE participant_events SET actor = 'x'",
    "DELETE FROM participant_events",
    "DELETE FROM participant_state",
)


def _alembic_config():
    from alembic.config import Config

    cfg = Config(str(API_DIR / "migrations" / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    return cfg


def _init_data(tg_user_id: int) -> str:
    """initData, подписанная так же, как в conftest.sign_init_data."""
    pairs = {
        "auth_date": str(int(time.time())),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps(
            {"id": tg_user_id, "first_name": "Test"},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }
    pairs["hash"] = compute_hash(pairs, FAKE_BOT_TOKEN)
    return urlencode(pairs)


def role_engine(dsn: str, role: str):
    """Engine, каждое соединение которого работает под SET ROLE <role>.

    commit обязателен: без него SET откатится вместе с первой транзакцией.
    """
    assert role in APP_ROLES
    engine = create_engine(dsn)

    @event.listens_for(engine, "connect")
    def _set_role(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        try:
            cursor.execute(f"SET ROLE {role}")
        finally:
            cursor.close()
        dbapi_conn.commit()

    return engine


@pytest.fixture
def api_engine(migrated_db):
    engine = role_engine(migrated_db, "app_api")
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def projector_engine(migrated_db):
    engine = role_engine(migrated_db, "app_projector")
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def api_as_app_api(db_api_client, api_engine, monkeypatch):
    """TestClient с настоящей БД, где все маршруты получают engine под app_api."""
    monkeypatch.setattr("app.db.session._engine_for", lambda dsn: api_engine)
    return db_api_client


def _headers(tg_user_id: int) -> dict[str, str]:
    return {"X-Telegram-Init-Data": _init_data(tg_user_id)}


def _first_launch(client, tg_user_id: int):
    return client.post(FIRST_LAUNCH_URL, headers=_headers(tg_user_id), json=FIRST_LAUNCH_BODY)


def _consent_items(body):
    # Ответ GET /consents — список записей (допускается и обёртка с одним списком).
    if isinstance(body, list):
        return body
    lists = [value for value in body.values() if isinstance(value, list)]
    assert len(lists) == 1, body
    return lists[0]


def _assert_denied(engine, sql: str) -> None:
    from psycopg import errors as pg_errors

    with engine.connect() as conn:
        with pytest.raises(ProgrammingError) as caught:
            conn.execute(text(sql))
    assert isinstance(caught.value.orig, pg_errors.InsufficientPrivilege), sql


# 1. Роль действительно применена.
def test_role_engines_use_app_roles(api_engine, projector_engine):
    with api_engine.connect() as conn:
        assert conn.execute(text("SELECT current_user")).scalar_one() == "app_api"
    with projector_engine.connect() as conn:
        assert conn.execute(text("SELECT current_user")).scalar_one() == "app_projector"


# 2. Живой API под app_api: новый и повторный first-launch, status, consents.
def test_api_flow_under_app_api(api_as_app_api):
    client = api_as_app_api

    first = _first_launch(client, 3101)
    assert first.status_code == 201, first.text

    again = _first_launch(client, 3101)  # блокер: SELECT FOR UPDATE
    assert again.status_code == 201, again.text
    assert again.json()["pid"] == first.json()["pid"]
    assert again.json()["short_no"] == first.json()["short_no"]

    status = client.get(STATUS_URL, headers=_headers(3101))
    assert status.status_code == 200, status.text
    assert status.json()["status"] == "returning"

    consents = client.get(CONSENTS_URL, headers=_headers(3101))
    assert consents.status_code == 200, consents.text
    assert {item["id"] for item in _consent_items(consents.json())} == {"C0", "C1"}


# 3. Проектор под app_projector строит состояние после first-launch под app_api.
def test_projector_under_app_projector(api_as_app_api, projector_engine, db_engine):
    from app.projector import run_once

    created = _first_launch(api_as_app_api, 3102)
    assert created.status_code == 201, created.text
    pid = created.json()["pid"]

    result = run_once(projector_engine)
    assert (result.processed, result.skipped) == (1, 0)

    with db_engine.connect() as conn:
        phase = conn.execute(
            text("SELECT lifecycle_phase FROM participant_state WHERE pid = CAST(:p AS uuid)"),
            {"p": pid},
        ).scalar_one()
    assert phase == "onboarding"


# 4. Отказы под app_api (каждый — своё соединение).
@pytest.mark.parametrize("sql", API_DENIED)
def test_app_api_denied(api_engine, sql):
    _assert_denied(api_engine, sql)


# 5. Отказы под app_projector.
@pytest.mark.parametrize("sql", PROJECTOR_DENIED)
def test_app_projector_denied(projector_engine, sql):
    _assert_denied(projector_engine, sql)


# 6. env.py: непустая MIGRATIONS_DATABASE_URL важнее DATABASE_URL; пустая — как не задана;
#    «%» в DSN (URL-кодирование) не ломает configparser Alembic.
def test_env_prefers_migrations_database_url(migrated_db, monkeypatch):
    from alembic import command

    monkeypatch.setenv("MIGRATIONS_DATABASE_URL", migrated_db)
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_DSN)
    command.current(_alembic_config())

    separator = "&" if "?" in migrated_db else "?"
    monkeypatch.setenv(
        "MIGRATIONS_DATABASE_URL", migrated_db + separator + "application_name=b3a1%20test"
    )
    command.current(_alembic_config())

    monkeypatch.setenv("MIGRATIONS_DATABASE_URL", "")
    with pytest.raises(OperationalError):
        command.current(_alembic_config())


# 7. ПОСЛЕДНИМ: downgrade 0006 отзывает права и членство; роли остаются.
def test_downgrade_revokes_privileges(migrated_db):
    from alembic import command

    cfg = _alembic_config()
    engine = create_engine(migrated_db)
    checks = text(
        "SELECT has_table_privilege('app_api', 'tg_user_registry', 'INSERT'), "
        "has_column_privilege('app_api', 'tg_user_registry', 'created_via', 'UPDATE'), "
        "pg_has_role('app_projector', 'participant_state_projector', 'MEMBER'), "
        "has_sequence_privilege('app_api', 'participant_events_id_seq', 'USAGE'), "
        "has_column_privilege('app_api', 'participant_events', 'id', 'SELECT'), "
        "pg_has_role('app_api', 'participant_state_reader', 'MEMBER'), "
        "has_column_privilege('app_projector', 'participant_state_checkpoints', 'at', 'UPDATE')"
    )
    try:
        with engine.connect() as conn:
            assert tuple(conn.execute(checks).one()) == (True,) * 7
        command.downgrade(cfg, "0005_participant_events")
        with engine.connect() as conn:
            assert tuple(conn.execute(checks).one()) == (False,) * 7
    finally:
        command.upgrade(cfg, "head")
        engine.dispose()
