"""pause-api-a1: миграция 0022_security_events — таблица security_events и права ролей.

Статические тесты (1) идут без БД. Тесты с БД — только в CI (соединение CI — суперпользователь,
оно делает SET LOCAL ROLE). Отказы — SQLSTATE 42501. Изоляция — новый pid uuid4 в каждом тесте.
Тест downgrade — последним в файле; в finally схема возвращается на head.
"""
import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.security_events import INSERT_SQL
from tests.conftest import _alembic_config

API_DIR = Path(__file__).resolve().parents[1]
MIGRATION_0022 = next(
    (API_DIR / "migrations" / "versions").glob("*0022_security_events*.py")
)

EXPECTED_PRIVILEGES_0022: tuple[tuple[str, str, str], ...] = (
    ("INSERT (event_type, pid, op_kind, client_op_id)", "TABLE security_events", "app_api"),
    ("USAGE", "SEQUENCE security_events_id_seq", "app_api"),
    ("SELECT", "TABLE security_events", "audit_reader"),
)

INSERT_ALLOWED = ("event_type", "pid", "op_kind", "client_op_id")
INSERT_DENIED = ("id", "created_at")
T = "security_events"


def _col(role: str, column: str, verb: str) -> str:
    return f"has_column_privilege('{role}', '{T}', '{column}', '{verb}')"


def _any(role: str, verb: str) -> str:
    return f"has_any_column_privilege('{role}', '{T}', '{verb}')"


def _table(role: str, verb: str) -> str:
    return f"has_table_privilege('{role}', '{T}', '{verb}')"


# (имя, SQL-функция прав, ожидание).
PRIVILEGE_CHECKS_0022: tuple[tuple[str, str, bool], ...] = (
    *((f"api-insert-{c}", _col("app_api", c, "INSERT"), True) for c in INSERT_ALLOWED),
    *((f"api-insert-{c}", _col("app_api", c, "INSERT"), False) for c in INSERT_DENIED),
    ("api-select", _any("app_api", "SELECT"), False),
    ("api-update", _any("app_api", "UPDATE"), False),
    ("api-delete", _table("app_api", "DELETE"), False),
    ("api-truncate", _table("app_api", "TRUNCATE"), False),
    (
        "api-seq",
        "has_sequence_privilege('app_api', 'security_events_id_seq', 'USAGE')",
        True,
    ),
    ("audit-select", _table("audit_reader", "SELECT"), True),
    ("audit-insert", _any("audit_reader", "INSERT"), False),
    *(
        (f"{r}-{v.lower()}", _any(r, v), False)
        for r in ("app_bot", "app_projector")
        for v in ("SELECT", "INSERT", "UPDATE")
    ),
    *((f"{r}-delete", _table(r, "DELETE"), False) for r in ("app_bot", "app_projector")),
    ("public-select", _table("public", "SELECT"), False),
)

OWNER_INSERT = text(
    "INSERT INTO security_events (event_type, pid, op_kind, client_op_id) "
    "VALUES (:event_type, :pid, :op_kind, :client_op_id)"
)

GOOD = {"event_type": "client_op_id_conflict", "op_kind": "pause_start", "client_op_id": "op-1"}

# (имя, поле, плохое значение) — CHECK и NOT NULL отклоняют.
BAD_VALUES: tuple[tuple[str, str, object], ...] = (
    ("event-type-null", "event_type", None),
    ("event-type-empty", "event_type", ""),
    ("event-type-other", "event_type", "other"),
    ("op-kind-null", "op_kind", None),
    ("op-kind-empty", "op_kind", ""),
    ("op-null", "client_op_id", None),
    ("op-empty", "client_op_id", ""),
    ("op-65", "client_op_id", "x" * 65),
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_0022_security_events", MIGRATION_0022)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _migration_code(module) -> str:
    """Текст миграции без docstring модуля (в нём запреты названы словами)."""
    source = MIGRATION_0022.read_text(encoding="utf-8")
    assert module.__doc__ and module.__doc__ in source
    return source.replace(module.__doc__, "", 1)


def _count(db_engine, pid: uuid.UUID) -> int:
    with db_engine.connect() as conn:
        return conn.execute(
            text("SELECT count(*) FROM security_events WHERE pid = :p"), {"p": pid}
        ).scalar_one()


# 1. Статика.
def test_revision_0022():
    module = _load_migration()
    assert module.revision == "0022_security_events"
    assert module.down_revision == "0021_bot_pauses_select"


def test_privileges_static_0022():
    module = _load_migration()
    assert module.ROLES == ("app_api", "audit_reader")
    assert module.PRIVILEGES == EXPECTED_PRIVILEGES_0022
    code = _migration_code(module)
    assert "ALTER DEFAULT PRIVILEGES" not in code.upper()
    assert "PUBLIC" not in code
    assert code.count("GRANT ") == 1


# 2. Права: выданное True, лишнее False.
@pytest.mark.parametrize(
    ("name", "sql", "allowed"),
    PRIVILEGE_CHECKS_0022,
    ids=[c[0] for c in PRIVILEGE_CHECKS_0022],
)
def test_privileges_0022(db_engine, name, sql, allowed):
    with db_engine.connect() as conn:
        granted = conn.execute(text(f"SELECT {sql}")).scalar_one()
    assert granted is allowed, name


# 3. Контракт app_api: INSERT проходит, SELECT — 42501.
def test_api_insert_contract_0022(db_engine):
    pid = uuid.uuid4()
    with db_engine.begin() as conn:
        conn.execute(text("SET LOCAL ROLE app_api"))
        conn.execute(INSERT_SQL, {**GOOD, "pid": pid})
    assert _count(db_engine, pid) == 1
    with db_engine.connect() as conn:
        conn.execute(text("SET LOCAL ROLE app_api"))
        with pytest.raises(DBAPIError) as info:
            conn.execute(text("SELECT id FROM security_events"))
        conn.rollback()
    assert info.value.orig.sqlstate == "42501"


# 4. CHECK и NOT NULL (владелец).
@pytest.mark.parametrize(
    ("name", "field", "value"), BAD_VALUES, ids=[b[0] for b in BAD_VALUES]
)
def test_checks_0022(db_engine, name, field, value):
    params = {**GOOD, "pid": uuid.uuid4(), field: value}
    with pytest.raises(IntegrityError):
        with db_engine.begin() as conn:
            conn.execute(OWNER_INSERT, params)


# 5. ПОСЛЕДНИМ: downgrade до 0021 — таблицы нет; в finally head.
def test_downgrade_0022(migrated_db):
    from alembic import command

    cfg = _alembic_config()
    exists = text("SELECT to_regclass('security_events') IS NULL")
    engine = create_engine(migrated_db)
    try:
        with engine.connect() as conn:
            assert conn.execute(exists).scalar_one() is False
        command.downgrade(cfg, "0021_bot_pauses_select")
        with engine.connect() as conn:
            assert conn.execute(exists).scalar_one() is True
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            assert conn.execute(exists).scalar_one() is False
    finally:
        command.upgrade(cfg, "head")
        engine.dispose()
