"""db-i3-1: миграция 0013_bot_card — права app_bot для /card и аудита.

Статические тесты (1) идут без БД. Тесты с БД — только в CI (соединение CI — суперпользователь,
оно делает SET ROLE). Роль app_bot — через _bot_role_engine из test_db_roles_0009. Отказы —
SQLSTATE 42501 (psycopg.errors.InsufficientPrivilege). Строку participant_state тест не создаёт
(её пишет только проектор). Строки privacy_audit_log ищутся по pid своего теста.
tg_user_id — 3801–3899. Тест downgrade — последним в файле; в finally схема возвращается на head.
"""
import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from tests.conftest import _alembic_config
from tests.test_db_roles import _assert_denied
from tests.test_db_roles_0009 import _bot_role_engine

API_DIR = Path(__file__).resolve().parents[1]
MIGRATION_0013 = next((API_DIR / "migrations" / "versions").glob("*0013_bot_card*.py"))

EXPECTED_PRIVILEGES_0013: tuple[tuple[str, str, str], ...] = (
    (
        "INSERT (actor_id, actor_role, action, participant_id)",
        "TABLE privacy_audit_log",
        "app_bot",
    ),
    ("USAGE", "SEQUENCE privacy_audit_log_id_seq", "app_bot"),
    ("SELECT (created_at)", "TABLE tg_user_registry", "app_bot"),
    (
        "SELECT (pid, lifecycle_phase, status_flags, stage_no, module_no, day_no, lives, tz)",
        "TABLE participant_state",
        "app_bot",
    ),
)

# Контракт bot-1 (бот, app_bot), карточка db-i3-1, раздел 7.
BOT_AUDIT_INSERT = text(
    "INSERT INTO privacy_audit_log (actor_id, actor_role, action, participant_id) "
    "VALUES (:actor_tg_id_text, 'owner', 'view', :pid)"
)
BOT_BY_SHORT_NO = text(
    "SELECT pid, tg_user_id, created_at FROM tg_user_registry "
    "WHERE short_no = :n AND tombstoned_at IS NULL"
)
BOT_BY_TG_USER_ID = text(
    "SELECT pid, short_no, created_at FROM tg_user_registry "
    "WHERE tg_user_id = :tg AND tombstoned_at IS NULL"
)
BOT_STATE = text(
    "SELECT lifecycle_phase, status_flags, stage_no, module_no, day_no, lives, tz "
    "FROM participant_state WHERE pid = :pid"
)

AUDIT_INSERT_LITERAL = (
    "INSERT INTO privacy_audit_log (actor_id, actor_role, action, participant_id) "
    "VALUES ('3803', 'owner', 'view', NULL)"
)

BOT_DENIED_0013: tuple[str, ...] = (
    "SELECT * FROM participant_state",
    "SELECT missed_streak FROM participant_state",
    "SELECT author_pause_reason FROM participant_state",
    "UPDATE participant_state SET tz = 'UTC'",
    "SELECT id FROM privacy_audit_log",
    AUDIT_INSERT_LITERAL + " RETURNING id",
    "INSERT INTO privacy_audit_log (actor_id, actor_role, action, participant_id, metadata) "
    "VALUES ('3803', 'owner', 'view', NULL, '{}'::jsonb)",
    "UPDATE privacy_audit_log SET action = 'x'",
    "DELETE FROM privacy_audit_log",
    "SELECT created_via FROM tg_user_registry",
    "SELECT * FROM tg_user_registry",
)

AUDIT_INSERT_COLUMNS: tuple[str, ...] = ("actor_id", "actor_role", "action", "participant_id")
AUDIT_INSERT_DENIED_COLUMNS: tuple[str, ...] = ("id", "occurred_at", "metadata")
STATE_SELECT_COLUMNS: tuple[str, ...] = (
    "pid",
    "lifecycle_phase",
    "status_flags",
    "stage_no",
    "module_no",
    "day_no",
    "lives",
    "tz",
)
STATE_DENIED_COLUMNS: tuple[str, ...] = (
    "author_pause_reason",
    "updated_at",
    "projector_version",
    "last_seen_publish_epoch",
    "day_started_at",
    "missed_streak",
)

# (имя, SQL-функция прав, ожидание).
PRIVILEGE_CHECKS_0013: tuple[tuple[str, str, bool], ...] = (
    tuple(
        (
            f"audit-insert-{col}",
            f"has_column_privilege('app_bot', 'privacy_audit_log', '{col}', 'INSERT')",
            True,
        )
        for col in AUDIT_INSERT_COLUMNS
    )
    + tuple(
        (
            f"audit-insert-denied-{col}",
            f"has_column_privilege('app_bot', 'privacy_audit_log', '{col}', 'INSERT')",
            False,
        )
        for col in AUDIT_INSERT_DENIED_COLUMNS
    )
    + tuple(
        (
            f"state-select-{col}",
            f"has_column_privilege('app_bot', 'participant_state', '{col}', 'SELECT')",
            True,
        )
        for col in STATE_SELECT_COLUMNS
    )
    + tuple(
        (
            f"state-select-denied-{col}",
            f"has_column_privilege('app_bot', 'participant_state', '{col}', 'SELECT')",
            False,
        )
        for col in STATE_DENIED_COLUMNS
    )
    + (
        (
            "registry-select-created-at",
            "has_column_privilege('app_bot', 'tg_user_registry', 'created_at', 'SELECT')",
            True,
        ),
        (
            "registry-select-created-via",
            "has_column_privilege('app_bot', 'tg_user_registry', 'created_via', 'SELECT')",
            False,
        ),
        (
            "audit-select-any",
            "has_any_column_privilege('app_bot', 'privacy_audit_log', 'SELECT')",
            False,
        ),
        (
            "audit-update-any",
            "has_any_column_privilege('app_bot', 'privacy_audit_log', 'UPDATE')",
            False,
        ),
        (
            "state-insert-any",
            "has_any_column_privilege('app_bot', 'participant_state', 'INSERT')",
            False,
        ),
        (
            "state-update-any",
            "has_any_column_privilege('app_bot', 'participant_state', 'UPDATE')",
            False,
        ),
        (
            "member-participant-state-reader",
            "pg_has_role('app_bot', 'participant_state_reader', 'MEMBER')",
            False,
        ),
        (
            "audit-seq-usage",
            "has_sequence_privilege('app_bot', 'privacy_audit_log_id_seq', 'USAGE')",
            True,
        ),
    )
)

# Табличных DELETE / TRUNCATE у app_bot на обеих таблицах нет.
TABLE_PRIVILEGES_DENIED_0013: tuple[tuple[str, str], ...] = tuple(
    (table, priv)
    for table in ("privacy_audit_log", "participant_state")
    for priv in ("DELETE", "TRUNCATE")
)

# До downgrade — true, после — false (все 4 права 0013).
GRANTED_0013: tuple[str, ...] = (
    "SELECT has_any_column_privilege('app_bot', 'privacy_audit_log', 'INSERT')",
    "SELECT has_sequence_privilege('app_bot', 'privacy_audit_log_id_seq', 'USAGE')",
    "SELECT has_column_privilege('app_bot', 'tg_user_registry', 'created_at', 'SELECT')",
    "SELECT has_any_column_privilege('app_bot', 'participant_state', 'SELECT')",
)

# true и до, и после downgrade: роль остаётся, права 0009 и 0011 целы.
KEPT_AFTER_0013: tuple[str, ...] = (
    "SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'app_bot')",
    "SELECT has_column_privilege('app_bot', 'tg_user_registry', 'tg_user_id', 'SELECT')",
    "SELECT has_column_privilege('app_bot', 'tg_user_registry', 'short_no', 'SELECT')",
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_0013_bot_card", MIGRATION_0013)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _migration_code(module) -> str:
    """Текст миграции без docstring модуля (в нём запреты названы словами)."""
    source = MIGRATION_0013.read_text(encoding="utf-8")
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


# 1. Статика: revision, ровно 4 права app_bot, только колоночные на TABLE, USAGE на SEQUENCE.
def test_revision_0013():
    module = _load_migration()
    assert module.revision == "0013_bot_card"
    assert module.down_revision == "0012_outbox_api"


def test_privileges_static_0013():
    module = _load_migration()
    assert module.ROLES == ("app_bot",)
    assert module.PRIVILEGES == EXPECTED_PRIVILEGES_0013
    for privilege, target, role in module.PRIVILEGES:
        assert role == "app_bot", (privilege, target, role)
        if target.startswith("TABLE "):
            assert "(" in privilege and privilege.endswith(")"), (privilege, target)
        if privilege == "USAGE":
            assert target.startswith("SEQUENCE "), (privilege, target)
        if target.startswith("SEQUENCE "):
            assert privilege == "USAGE", (privilege, target)
    code = _migration_code(module)
    assert "ALTER DEFAULT PRIVILEGES" not in code.upper()
    assert "PUBLIC" not in code
    assert "participant_state_reader" not in code.lower()


# 2. Контрактный SQL раздела 7 под app_bot.
def test_bot_audit_insert_0013(db_engine, bot_engine):
    pid = _registry_pid(db_engine, 3801)
    with bot_engine.begin() as conn:
        conn.execute(BOT_AUDIT_INSERT, {"actor_tg_id_text": "3899", "pid": pid})
    with db_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT actor_id, actor_role, action, occurred_at, metadata "
                "FROM privacy_audit_log WHERE participant_id = :p"
            ),
            {"p": pid},
        ).all()
    assert len(rows) == 1
    row = rows[0]
    assert (row.actor_id, row.actor_role, row.action) == ("3899", "owner", "view")
    assert row.occurred_at is not None
    assert row.metadata is None


def test_bot_reads_registry_0013(db_engine, bot_engine):
    pid = _registry_pid(db_engine, 3802)
    with db_engine.connect() as conn:
        short_no = conn.execute(
            text("SELECT short_no FROM tg_user_registry WHERE pid = :p"), {"p": pid}
        ).scalar_one()
    with bot_engine.connect() as conn:
        by_no = conn.execute(BOT_BY_SHORT_NO, {"n": short_no}).one()
        by_tg = conn.execute(BOT_BY_TG_USER_ID, {"tg": 3802}).one()
    assert by_no.pid == pid
    assert by_no.tg_user_id == 3802
    assert by_no.created_at is not None
    assert by_tg.pid == pid
    assert by_tg.short_no == short_no
    assert by_tg.created_at == by_no.created_at


def test_bot_reads_missing_state_0013(bot_engine):
    with bot_engine.connect() as conn:
        rows = conn.execute(BOT_STATE, {"pid": uuid.uuid4()}).all()
    assert rows == []


# 3. Отказы app_bot (каждый — своё соединение).
@pytest.mark.parametrize("sql", BOT_DENIED_0013)
def test_app_bot_denied_0013(bot_engine, sql):
    _assert_denied(bot_engine, sql)


# 4. Функции прав.
@pytest.mark.parametrize(
    ("name", "sql", "allowed"),
    PRIVILEGE_CHECKS_0013,
    ids=[c[0] for c in PRIVILEGE_CHECKS_0013],
)
def test_privileges_0013(db_engine, name, sql, allowed):
    with db_engine.connect() as conn:
        granted = conn.execute(text(f"SELECT {sql}")).scalar_one()
    assert granted is allowed, name


@pytest.mark.parametrize(("table", "privilege"), TABLE_PRIVILEGES_DENIED_0013)
def test_no_delete_truncate_0013(db_engine, table, privilege):
    with db_engine.connect() as conn:
        granted = conn.execute(
            text("SELECT has_table_privilege('app_bot', :t, :p)"),
            {"t": table, "p": privilege},
        ).scalar_one()
    assert granted is False, (table, privilege)


# 5. ПОСЛЕДНИМ: downgrade до 0012 снимает 4 права 0013; права 0009 и 0011 остаются.
def test_downgrade_0013(migrated_db):
    from alembic import command

    cfg = _alembic_config()
    engine = create_engine(migrated_db)
    try:
        with engine.connect() as conn:
            for sql in GRANTED_0013 + KEPT_AFTER_0013:
                assert conn.execute(text(sql)).scalar_one() is True, sql
        command.downgrade(cfg, "0012_outbox_api")
        with engine.connect() as conn:
            for sql in GRANTED_0013:
                assert conn.execute(text(sql)).scalar_one() is False, sql
            for sql in KEPT_AFTER_0013:
                assert conn.execute(text(sql)).scalar_one() is True, sql
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            for sql in GRANTED_0013:
                assert conn.execute(text(sql)).scalar_one() is True, sql
    finally:
        command.upgrade(cfg, "head")
        engine.dispose()
