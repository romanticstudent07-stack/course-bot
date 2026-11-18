"""db-revive-0020: миграция 0020_bot_events_select — SELECT (id, pid, kind) на participant_events для app_bot.

Статические тесты (1) идут без БД. Тесты с БД — только в CI (соединение CI — суперпользователь,
оно делает SET ROLE через _bot_role_engine). Отказы — SQLSTATE 42501 (_assert_denied).
События вставляет владелец. tg_user_id — 5001–5019. Тест downgrade — последним в файле;
в finally схема возвращается на head.
"""
import importlib.util
import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from tests.conftest import _alembic_config
from tests.test_db_roles import _assert_denied
from tests.test_db_roles_0009 import _bot_role_engine

API_DIR = Path(__file__).resolve().parents[1]
MIGRATION_0020 = next(
    (API_DIR / "migrations" / "versions").glob("*0020_bot_events_select*.py")
)

# Контракт bot-revive-1 §7 (бот, app_bot): точка отката :after.
BOT_AFTER = text(
    "SELECT coalesce(max(id), 0) FROM participant_events "
    "WHERE pid = :pid AND kind IN ('revive_by_author', 'restart_paid')"
)
OWNER_EVENT = text(
    "INSERT INTO participant_events (pid, kind, payload, actor, actor_role) "
    "VALUES (:p, :k, CAST(:payload AS jsonb), 'test', 'system') RETURNING id"
)

EXPECTED_PRIVILEGES_0020: tuple[tuple[str, str, str], ...] = (
    ("SELECT (id, pid, kind)", "TABLE participant_events", "app_bot"),
)

SELECT_ALLOWED = ("id", "pid", "kind")
SELECT_DENIED = ("payload", "at", "actor", "actor_role")


def _col(column: str) -> str:
    return f"has_column_privilege('app_bot', 'participant_events', '{column}', 'SELECT')"


# (имя, SQL-функция прав, ожидание).
PRIVILEGE_CHECKS_0020: tuple[tuple[str, str, bool], ...] = (
    *((f"bot-select-{c}", _col(c), True) for c in SELECT_ALLOWED),
    *((f"bot-select-{c}", _col(c), False) for c in SELECT_DENIED),
    (
        "bot-table-select",
        "has_table_privilege('app_bot', 'participant_events', 'SELECT')",
        False,
    ),
    (
        "bot-insert-0018",
        "has_any_column_privilege('app_bot', 'participant_events', 'INSERT')",
        True,
    ),
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "mig_0020_bot_events_select", MIGRATION_0020
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _migration_code(module) -> str:
    """Текст миграции без docstring модуля (в нём запреты названы словами)."""
    source = MIGRATION_0020.read_text(encoding="utf-8")
    assert module.__doc__ and module.__doc__ in source
    return source.replace(module.__doc__, "", 1)


@pytest.fixture
def bot_engine(migrated_db):
    engine = _bot_role_engine(migrated_db)
    try:
        yield engine
    finally:
        engine.dispose()


def _registry_pid(db_engine, tg_id: int) -> uuid.UUID:
    """Строка tg_user_registry от владельца; вернуть pid."""
    pid = uuid.uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tg_user_registry (pid, tg_user_id, created_via) "
                "VALUES (:p, :t, 'mini_app_first_launch')"
            ),
            {"p": pid, "t": tg_id},
        )
    return pid


def _event(db_engine, pid, kind: str) -> int:
    """Событие participant_events от владельца; вернуть id."""
    with db_engine.begin() as conn:
        return conn.execute(
            OWNER_EVENT,
            {"p": pid, "k": kind, "payload": json.dumps({"schema_version": 1})},
        ).scalar_one()


# 1. Статика: revision, down_revision, ROLES, PRIVILEGES, запреты.
def test_revision_0020():
    module = _load_migration()
    assert module.revision == "0020_bot_events_select"
    assert module.down_revision == "0019_life_writeoffs"


def test_privileges_static_0020():
    module = _load_migration()
    assert module.ROLES == ("app_bot",)
    assert module.PRIVILEGES == EXPECTED_PRIVILEGES_0020
    code = _migration_code(module)
    assert "ALTER DEFAULT PRIVILEGES" not in code.upper()
    # Слово в верхнем регистре: строчное public допустимо в именах и импортах.
    assert "PUBLIC" not in code
    # GRANT — только в цикле upgrade, REVOKE — только в цикле downgrade.
    assert code.count("GRANT ") == 1
    assert code.count("REVOKE ") == 1


# 2. Права: выданное True, лишнее False, INSERT 0018 цел.
@pytest.mark.parametrize(
    ("name", "sql", "allowed"),
    PRIVILEGE_CHECKS_0020,
    ids=[c[0] for c in PRIVILEGE_CHECKS_0020],
)
def test_privileges_0020(db_engine, name, sql, allowed):
    with db_engine.connect() as conn:
        granted = conn.execute(text(f"SELECT {sql}")).scalar_one()
    assert granted is allowed, name


# 3. Контракт §7 под app_bot.
def test_bot_after_contract_0020(db_engine, bot_engine):
    pid = _registry_pid(db_engine, 5001)
    other_pid = _registry_pid(db_engine, 5002)
    empty_pid = _registry_pid(db_engine, 5003)
    _event(db_engine, pid, "restart_paid")
    _event(db_engine, pid, "life_op")
    revive_id = _event(db_engine, pid, "revive_by_author")
    _event(db_engine, pid, "life_op")
    _event(db_engine, other_pid, "revive_by_author")
    with bot_engine.connect() as conn:
        assert conn.execute(BOT_AFTER, {"pid": pid}).scalar_one() == revive_id
        assert conn.execute(BOT_AFTER, {"pid": empty_pid}).scalar_one() == 0


# 4. Отказ: payload app_bot не читает.
def test_bot_select_payload_denied_0020(bot_engine):
    _assert_denied(bot_engine, "SELECT payload FROM participant_events")


# 5. ПОСЛЕДНИМ: downgrade до 0019 — SELECT id снят, INSERT 0018 цел, life_writeoffs на месте.
def test_downgrade_0020(migrated_db):
    from alembic import command

    cfg = _alembic_config()
    bot_select_id = text(f"SELECT {_col('id')}")
    bot_events_insert = text(
        "SELECT has_any_column_privilege('app_bot', 'participant_events', 'INSERT')"
    )
    lw_exists = text("SELECT to_regclass('public.life_writeoffs') IS NOT NULL")
    engine = create_engine(migrated_db)
    try:
        with engine.connect() as conn:
            assert conn.execute(bot_select_id).scalar_one() is True
        command.downgrade(cfg, "0019_life_writeoffs")
        with engine.connect() as conn:
            assert conn.execute(bot_select_id).scalar_one() is False
            assert conn.execute(bot_events_insert).scalar_one() is True  # право 0018 цело
            assert conn.execute(lw_exists).scalar_one() is True
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            assert conn.execute(bot_select_id).scalar_one() is True
    finally:
        command.upgrade(cfg, "head")
        engine.dispose()
