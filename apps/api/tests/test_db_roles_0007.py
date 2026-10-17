"""iter2-db-1: миграция 0007_day_state — колонки participant_state, idempotency_keys, права.

Тесты с БД — только CI (соединение CI — суперпользователь, оно делает SET ROLE).
Отказы — SQLSTATE 42501 (psycopg.errors.InsufficientPrivilege). Стоп-правило карточки:
permission denied на право вне раздела 8 — права не расширять, ошибку отдать ШТАБу.
db_engine НЕ чистит idempotency_keys, поэтому ключи в тестах уникальные (uuid4).
tg_user_id — 3201–3299. Тест downgrade — последним в файле; в finally схема возвращается на head.

Фикстуры api_engine, projector_engine, api_as_app_api — копия из test_db_roles.py
(импорт фикстур линтер посчитал бы неиспользуемым); обычные функции — импортом.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from tests.test_db_roles import _assert_denied, _first_launch, role_engine

API_DIR = Path(__file__).resolve().parents[1]

NEW_COLUMNS: tuple[str, ...] = (
    "lives",
    "stage_no",
    "module_no",
    "day_no",
    "day_started_at",
    "missed_streak",
    "tz",
)

DAY_START = datetime(2026, 10, 16, 1, 0, tzinfo=timezone.utc)

# Каждый набор нарушает один CHECK participant_state (под db_engine).
BAD_STATE_VALUES: tuple[dict, ...] = (
    {"lives": 4},
    {"lives": -1},
    {"missed_streak": -1},
    {"tz": ""},
    {"stage_no": 1},
    {"stage_no": 1, "module_no": 1, "day_no": 0, "day_started_at": DAY_START},
    {"module_no": 1, "day_no": 1, "day_started_at": DAY_START},
)
BAD_STATE_IDS: tuple[str, ...] = (
    "lives_4",
    "lives_minus_1",
    "missed_streak_minus_1",
    "tz_empty",
    "only_stage_no",
    "day_no_0",
    "stage_no_null",
)

API_DENIED_0007: tuple[str, ...] = (
    "UPDATE participant_state SET lives = 2",
    "UPDATE participant_state SET tz = 'UTC'",
    "SELECT lives FROM participant_state FOR UPDATE",
    "UPDATE idempotency_keys SET result_ref = 'x'",
    "DELETE FROM idempotency_keys",
    "TRUNCATE idempotency_keys",
)

PROJECTOR_DENIED_0007: tuple[str, ...] = (
    "UPDATE participant_events SET actor = 'x'",
    "DELETE FROM participant_events",
    "TRUNCATE participant_events",
    "UPDATE idempotency_keys SET result_ref = 'x'",
    "DELETE FROM idempotency_keys",
    "TRUNCATE idempotency_keys",
)


def _alembic_config():
    from alembic.config import Config

    cfg = Config(str(API_DIR / "migrations" / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    return cfg


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


def _projected_pid(client, projector_engine, tg_user_id: int) -> str:
    """first-launch под app_api → run_once под app_projector; вернуть pid."""
    from app.projector import run_once

    created = _first_launch(client, tg_user_id)
    assert created.status_code == 201, created.text
    run_once(projector_engine)
    return created.json()["pid"]


def _insert_state(conn, values: dict) -> None:
    """Строка participant_state напрямую (FK у таблицы нет) + заданные новые колонки."""
    columns = ["pid", "lifecycle_phase", "updated_at", "projector_version", *values]
    placeholders = ["gen_random_uuid()", "'onboarding'", "now()", "1"]
    placeholders += [f":{column}" for column in values]
    conn.execute(
        text(
            f"INSERT INTO participant_state ({', '.join(columns)}) "
            f"VALUES ({', '.join(placeholders)})"
        ),
        values,
    )


# 1. Значения по умолчанию у строки, которую построил проектор (UPSERT без правок).
def test_projector_row_gets_defaults(api_as_app_api, projector_engine, db_engine):
    pid = _projected_pid(api_as_app_api, projector_engine, 3201)
    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT lives, missed_streak, tz, stage_no, module_no, day_no, day_started_at "
                "FROM participant_state WHERE pid = CAST(:p AS uuid)"
            ),
            {"p": pid},
        ).one()
    assert tuple(row) == (3, 0, "Europe/Moscow", None, None, None, None)


# 2. CHECK participant_state: каждое нарушение → CheckViolation.
@pytest.mark.parametrize("values", BAD_STATE_VALUES, ids=BAD_STATE_IDS)
def test_state_checks_reject(db_engine, values):
    from psycopg import errors as pg_errors

    with pytest.raises(IntegrityError) as caught:
        with db_engine.begin() as conn:
            _insert_state(conn, values)
    assert isinstance(caught.value.orig, pg_errors.CheckViolation), values


def test_state_checks_accept_full_position(db_engine):
    values = {"stage_no": 1, "module_no": 1, "day_no": 1, "day_started_at": DAY_START}
    with db_engine.begin() as conn:
        _insert_state(conn, values)


# 3. Н4: права 0001 на всю таблицу покрывают новые колонки.
@pytest.mark.parametrize("column", NEW_COLUMNS)
def test_new_columns_privileges(db_engine, column):
    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT has_column_privilege('app_projector', 'participant_state', :c, 'UPDATE'), "
                "has_column_privilege('app_api', 'participant_state', :c, 'SELECT'), "
                "has_column_privilege('app_api', 'participant_state', :c, 'UPDATE')"
            ),
            {"c": column},
        ).one()
    assert tuple(row) == (True, True, False), column


# 4. app_projector обновляет новые колонки своей строки.
def test_projector_updates_new_columns(api_as_app_api, projector_engine):
    pid = _projected_pid(api_as_app_api, projector_engine, 3202)
    with projector_engine.begin() as conn:
        result = conn.execute(
            text(
                "UPDATE participant_state SET lives = 2, missed_streak = 1 "
                "WHERE pid = CAST(:p AS uuid)"
            ),
            {"p": pid},
        )
    assert result.rowcount == 1


# 5. app_api читает новые колонки.
def test_api_reads_new_columns(api_as_app_api, projector_engine, api_engine):
    _projected_pid(api_as_app_api, projector_engine, 3203)
    with api_engine.connect() as conn:
        rows = conn.execute(text("SELECT lives, tz, stage_no FROM participant_state")).all()
    assert len(rows) == 1


# 6. Запреты app_api (каждый — своё соединение).
@pytest.mark.parametrize("sql", API_DENIED_0007)
def test_app_api_denied_0007(api_engine, sql):
    _assert_denied(api_engine, sql)


# 7. Запреты app_projector.
@pytest.mark.parametrize("sql", PROJECTOR_DENIED_0007)
def test_app_projector_denied_0007(projector_engine, sql):
    _assert_denied(projector_engine, sql)


# 8. app_projector МОЖЕТ записать событие (В9 = А): INSERT + USAGE последовательности.
def test_projector_inserts_participant_event(api_as_app_api, projector_engine):
    created = _first_launch(api_as_app_api, 3204)
    assert created.status_code == 201, created.text
    with projector_engine.begin() as conn:
        event_id = conn.execute(
            text(
                "INSERT INTO participant_events (pid, kind, payload, actor, actor_role) "
                "VALUES (CAST(:p AS uuid), 'test_0007', CAST('{}' AS jsonb), 'test', 'system') "
                "RETURNING id"
            ),
            {"p": created.json()["pid"]},
        ).scalar_one()
    assert event_id > 0


# 9. idempotency_keys под каждой ролью: INSERT, SELECT, повтор, ON CONFLICT DO NOTHING.
@pytest.mark.parametrize("engine_name", ["api_engine", "projector_engine"])
def test_idempotency_keys_under_role(request, engine_name):
    from psycopg import errors as pg_errors

    engine = request.getfixturevalue(engine_name)
    key = f"test0007:{uuid4()}"
    insert = text(
        "INSERT INTO idempotency_keys (key, kind, result_ref) VALUES (:k, 'test', 'ref-1') "
        "RETURNING created_at, ttl"
    )

    with engine.begin() as conn:
        row = conn.execute(insert, {"k": key}).one()
    assert row.created_at is not None
    assert row.ttl == timedelta(hours=1)

    with engine.connect() as conn:
        found = conn.execute(
            text("SELECT result_ref FROM idempotency_keys WHERE key = :k"), {"k": key}
        ).scalar_one()
    assert found == "ref-1"

    with pytest.raises(IntegrityError) as caught:
        with engine.begin() as conn:
            conn.execute(insert, {"k": key})
    assert isinstance(caught.value.orig, pg_errors.UniqueViolation)

    with engine.begin() as conn:
        skipped = conn.execute(
            text(
                "INSERT INTO idempotency_keys (key, kind, result_ref) VALUES (:k, 'test', 'ref-2') "
                "ON CONFLICT DO NOTHING RETURNING key"
            ),
            {"k": key},
        ).all()
    assert skipped == []


def test_idempotency_keys_constraints(db_engine):
    from psycopg import errors as pg_errors

    with pytest.raises(IntegrityError) as caught:
        with db_engine.begin() as conn:
            conn.execute(
                text("INSERT INTO idempotency_keys (key, kind) VALUES (:k, NULL)"),
                {"k": f"test0007:{uuid4()}"},
            )
    assert isinstance(caught.value.orig, pg_errors.NotNullViolation)

    with pytest.raises(IntegrityError) as caught:
        with db_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO idempotency_keys (key, kind, ttl) "
                    "VALUES (:k, 'test', interval '0')"
                ),
                {"k": f"test0007:{uuid4()}"},
            )
    assert isinstance(caught.value.orig, pg_errors.CheckViolation)


# 10. ПОСЛЕДНИМ: downgrade 0007 убирает таблицу, колонки и права 0007; права 0006 целы.
def test_downgrade_0007(migrated_db):
    from alembic import command

    cfg = _alembic_config()
    engine = create_engine(migrated_db)
    checks_0007 = text(
        "SELECT to_regclass('public.idempotency_keys') IS NOT NULL, "
        "has_table_privilege('app_projector', 'participant_events', 'INSERT'), "
        "has_sequence_privilege('app_projector', 'participant_events_id_seq', 'USAGE'), "
        "EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' "
        "AND table_name = 'participant_state' AND column_name = 'lives')"
    )
    checks_0006 = text(
        "SELECT has_table_privilege('app_projector', 'participant_events', 'SELECT'), "
        "has_sequence_privilege('app_api', 'participant_events_id_seq', 'USAGE'), "
        "pg_has_role('app_projector', 'participant_state_projector', 'MEMBER')"
    )
    try:
        with engine.connect() as conn:
            assert tuple(conn.execute(checks_0007).one()) == (True,) * 4
            assert tuple(conn.execute(checks_0006).one()) == (True,) * 3
        command.downgrade(cfg, "0006_app_roles")
        with engine.connect() as conn:
            assert tuple(conn.execute(checks_0007).one()) == (False,) * 4
            assert tuple(conn.execute(checks_0006).one()) == (True,) * 3
    finally:
        command.upgrade(cfg, "head")
        engine.dispose()
