"""iter2-db-2: миграция 0008_day_marks — таблица day_marks и права.

Тесты с БД — только CI (соединение CI — суперпользователь, оно делает SET ROLE).
Отказы — SQLSTATE 42501 (psycopg.errors.InsufficientPrivilege). Стоп-правило карточки:
permission denied на право вне раздела 8 — права не расширять, ошибку отдать ШТАБу.
db_engine чистит day_marks через TRUNCATE tg_user_registry CASCADE. Каждый тест сам
создаёт участника и свои отметки (от порядка тестов не зависит). tg_user_id — 3301–3399.
Тест downgrade — последним в файле; в finally схема возвращается на head.

Фикстуры api_engine, projector_engine, api_as_app_api — копия из test_db_roles_0007.py
(импорт фикстур линтер посчитал бы неиспользуемым); обычные функции — импортом.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from tests.test_db_roles import _assert_denied, _first_launch, role_engine

API_DIR = Path(__file__).resolve().parents[1]

DAY_START = datetime(2026, 10, 16, 1, 0, tzinfo=timezone.utc)
DAY_REISSUED = DAY_START + timedelta(days=1)
UNKNOWN_PID = "00000000-0000-0000-0000-000000000001"

# Повторная отметка — как будет в задаче API (iter2-api-2): время ставим явно.
UPSERT_MARK = text(
    "INSERT INTO day_marks (pid, day_started_at, block_id, value) "
    "VALUES (CAST(:p AS uuid), :d, :b, :v) "
    "ON CONFLICT (pid, day_started_at, block_id) "
    "DO UPDATE SET value = EXCLUDED.value, at = now() "
    "RETURNING value, at"
)

SELECT_MARKS = text(
    "SELECT day_started_at, block_id, value FROM day_marks "
    "WHERE pid = CAST(:p AS uuid) ORDER BY day_started_at, block_id"
)

API_DENIED_0008: tuple[str, ...] = (
    "UPDATE day_marks SET pid = gen_random_uuid()",
    "UPDATE day_marks SET block_id = 'x'",
    "UPDATE day_marks SET day_started_at = now()",
    "DELETE FROM day_marks",
    "TRUNCATE day_marks",
)

PROJECTOR_DENIED_0008: tuple[str, ...] = (
    "INSERT INTO day_marks (pid, day_started_at, block_id, value) "
    "VALUES (gen_random_uuid(), now(), 'b1', true)",
    "UPDATE day_marks SET value = true",
    "DELETE FROM day_marks",
    "TRUNCATE day_marks",
)

# Каждый набор нарушает одно ограничение day_marks (под db_engine).
INSERT_FULL = text(
    "INSERT INTO day_marks (pid, day_started_at, block_id, value, at) "
    "VALUES (CAST(:p AS uuid), :d, :b, :v, :at)"
)
BAD_MARKS: tuple[tuple[str, dict, str], ...] = (
    ("duplicate", {"b": "b1"}, "UniqueViolation"),
    ("unknown_pid", {"p": UNKNOWN_PID}, "ForeignKeyViolation"),
    ("value_null", {"v": None}, "NotNullViolation"),
    ("at_null", {"at": None}, "NotNullViolation"),
    ("block_id_empty", {"b": ""}, "CheckViolation"),
)

COLUMN_UPDATE_PRIVILEGES: tuple[tuple[str, bool], ...] = (
    ("value", True),
    ("at", True),
    ("pid", False),
    ("block_id", False),
    ("day_started_at", False),
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


def _created_pid(client, tg_user_id: int) -> str:
    """first-launch под app_api; вернуть pid (FK day_marks — на tg_user_registry)."""
    created = _first_launch(client, tg_user_id)
    assert created.status_code == 201, created.text
    return created.json()["pid"]


def _upsert(engine, pid: str, day: datetime, block_id: str, value: bool):
    with engine.begin() as conn:
        return conn.execute(
            UPSERT_MARK, {"p": pid, "d": day, "b": block_id, "v": value}
        ).one()


# 1. app_api: новая отметка, затем повтор через ON CONFLICT DO UPDATE — строка одна.
def test_api_upsert_mark(api_as_app_api, api_engine):
    pid = _created_pid(api_as_app_api, 3301)
    first = _upsert(api_engine, pid, DAY_START, "b1", True)
    assert first.value is True
    second = _upsert(api_engine, pid, DAY_START, "b1", False)
    assert second.value is False
    assert second.at >= first.at

    with api_engine.connect() as conn:
        rows = conn.execute(SELECT_MARKS, {"p": pid}).all()
    assert [tuple(row) for row in rows] == [(DAY_START, "b1", False)]


# 2. Перевыдача дня (В10): новый day_started_at — новые строки, старая цела.
def test_reissued_day_starts_empty(api_as_app_api, api_engine):
    pid = _created_pid(api_as_app_api, 3302)
    _upsert(api_engine, pid, DAY_START, "b1", True)

    current = text(
        "SELECT block_id FROM day_marks "
        "WHERE pid = CAST(:p AS uuid) AND day_started_at = :d"
    )
    with api_engine.connect() as conn:
        assert conn.execute(current, {"p": pid, "d": DAY_REISSUED}).all() == []

    _upsert(api_engine, pid, DAY_REISSUED, "b1", False)
    with api_engine.connect() as conn:
        rows = conn.execute(SELECT_MARKS, {"p": pid}).all()
    assert [tuple(row) for row in rows] == [
        (DAY_START, "b1", True),
        (DAY_REISSUED, "b1", False),
    ]


# 3. app_projector читает отметки.
def test_projector_reads_marks(api_as_app_api, api_engine, projector_engine):
    pid = _created_pid(api_as_app_api, 3303)
    _upsert(api_engine, pid, DAY_START, "b1", True)
    with projector_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT pid, block_id, value FROM day_marks WHERE pid = CAST(:p AS uuid)"
            ),
            {"p": pid},
        ).all()
    assert [(str(row.pid), row.block_id, row.value) for row in rows] == [(pid, "b1", True)]


# 4. Запреты app_api (каждый — своё соединение).
@pytest.mark.parametrize("sql", API_DENIED_0008)
def test_app_api_denied_0008(api_engine, sql):
    _assert_denied(api_engine, sql)


# 5. Запреты app_projector.
@pytest.mark.parametrize("sql", PROJECTOR_DENIED_0008)
def test_app_projector_denied_0008(projector_engine, sql):
    _assert_denied(projector_engine, sql)


# 6. Ограничения таблицы: каждое нарушение → свой SQLSTATE.
@pytest.mark.parametrize(
    ("overrides", "error_name"),
    [(case[1], case[2]) for case in BAD_MARKS],
    ids=[case[0] for case in BAD_MARKS],
)
def test_day_marks_constraints(api_as_app_api, db_engine, overrides, error_name):
    from psycopg import errors as pg_errors

    pid = _created_pid(api_as_app_api, 3304)
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO day_marks (pid, day_started_at, block_id, value) "
                "VALUES (CAST(:p AS uuid), :d, 'b1', true) ON CONFLICT DO NOTHING"
            ),
            {"p": pid, "d": DAY_START},
        )

    params = {"p": pid, "d": DAY_START, "b": "b9", "v": True, "at": DAY_START}
    params.update(overrides)
    with pytest.raises(IntegrityError) as caught:
        with db_engine.begin() as conn:
            conn.execute(INSERT_FULL, params)
    assert isinstance(caught.value.orig, getattr(pg_errors, error_name)), overrides


# 7. Права по колонкам: app_api меняет только value и at.
@pytest.mark.parametrize(("column", "allowed"), COLUMN_UPDATE_PRIVILEGES)
def test_api_column_update_privileges(db_engine, column, allowed):
    with db_engine.connect() as conn:
        granted = conn.execute(
            text("SELECT has_column_privilege('app_api', 'day_marks', :c, 'UPDATE')"),
            {"c": column},
        ).scalar_one()
    assert granted is allowed, column


# 8. ПОСЛЕДНИМ: downgrade 0008 убирает day_marks; права 0007 целы.
def test_downgrade_0008(migrated_db):
    from alembic import command

    cfg = _alembic_config()
    engine = create_engine(migrated_db)
    check_0008 = text("SELECT to_regclass('public.day_marks') IS NOT NULL")
    check_0007 = text("SELECT has_table_privilege('app_api', 'idempotency_keys', 'INSERT')")
    try:
        with engine.connect() as conn:
            assert conn.execute(check_0008).scalar_one() is True
            assert conn.execute(check_0007).scalar_one() is True
        command.downgrade(cfg, "0007_day_state")
        with engine.connect() as conn:
            assert conn.execute(check_0008).scalar_one() is False
            assert conn.execute(check_0007).scalar_one() is True
    finally:
        command.upgrade(cfg, "head")
        engine.dispose()
