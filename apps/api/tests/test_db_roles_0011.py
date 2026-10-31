"""db-1: миграция 0011_reflections_log — неизменяемый лог рефлексий, права app_api / app_bot.

Статические тесты (1) идут без БД. Тесты с БД — только в CI (соединение CI — суперпользователь,
оно делает SET ROLE). Роль переключается так же, как в test_db_roles_0010 (_bot_role_engine,
role_engine). Отказы — SQLSTATE 42501 (psycopg.errors.InsufficientPrivilege). db_engine
(conftest) чистит tg_user_registry с CASCADE, и строки reflections_log уходят вместе с ней.
tg_user_id — 3601–3699. Тест downgrade — последним в файле; в finally схема возвращается на head.
"""
import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from tests.conftest import _alembic_config
from tests.test_db_roles import _assert_denied, role_engine
from tests.test_db_roles_0009 import _bot_role_engine

API_DIR = Path(__file__).resolve().parents[1]
MIGRATION_0011 = next(
    (API_DIR / "migrations" / "versions").glob("*0011_reflections_log*.py")
)

# Контракт api-refl-1 (API, app_api).
API_INSERT = text(
    "INSERT INTO reflections_log (pid, stage_no, module_no, day_no, day_started_at, body) "
    "VALUES (:pid, :s, :m, :d, now(), :body) RETURNING id"
)
# Контракт bot-group-1 (бот, app_bot).
BOT_READ_REFLECTION = text(
    "SELECT pid, stage_no, module_no, day_no, body, created_at FROM reflections_log "
    "WHERE id = :reflection_id"
)
BOT_READ_SHORT_NO = text(
    "SELECT tg_user_id, short_no FROM tg_user_registry "
    "WHERE pid = CAST(:pid AS uuid) AND tombstoned_at IS NULL"
)

OWNER_INSERT = text(
    "INSERT INTO reflections_log (pid, stage_no, module_no, day_no, day_started_at, body) "
    "VALUES (:pid, 1, 1, :d, now(), :body)"
)

API_DENIED_0011: tuple[str, ...] = (
    "UPDATE reflections_log SET body = 'xx'",
    "DELETE FROM reflections_log",
    "TRUNCATE reflections_log",
)

BOT_DENIED_0011: tuple[str, ...] = (
    "INSERT INTO reflections_log (pid, stage_no, module_no, day_no, day_started_at, body) "
    "VALUES (gen_random_uuid(), 1, 1, 6, now(), 'xx')",
    "UPDATE reflections_log SET body = 'xx'",
    "DELETE FROM reflections_log",
)

PROJECTOR_DENIED_0011: tuple[str, ...] = (
    "SELECT id FROM reflections_log",
    "SELECT body FROM reflections_log",
)

# (роль, SQL-функция прав, ожидание).
PRIVILEGE_CHECKS_0011: tuple[tuple[str, str, bool], ...] = (
    ("api-insert", "has_any_column_privilege('app_api', 'reflections_log', 'INSERT')", True),
    ("api-select", "has_any_column_privilege('app_api', 'reflections_log', 'SELECT')", True),
    ("api-update", "has_any_column_privilege('app_api', 'reflections_log', 'UPDATE')", False),
    ("api-delete", "has_table_privilege('app_api', 'reflections_log', 'DELETE')", False),
    (
        "api-seq-usage",
        "has_sequence_privilege('app_api', 'reflections_log_id_seq', 'USAGE')",
        True,
    ),
    (
        "bot-select-body",
        "has_column_privilege('app_bot', 'reflections_log', 'body', 'SELECT')",
        True,
    ),
    ("bot-insert", "has_any_column_privilege('app_bot', 'reflections_log', 'INSERT')", False),
    ("bot-update", "has_any_column_privilege('app_bot', 'reflections_log', 'UPDATE')", False),
    (
        "bot-select-short-no",
        "has_column_privilege('app_bot', 'tg_user_registry', 'short_no', 'SELECT')",
        True,
    ),
    (
        "projector-select",
        "has_any_column_privilege('app_projector', 'reflections_log', 'SELECT')",
        False,
    ),
    (
        "projector-insert",
        "has_any_column_privilege('app_projector', 'reflections_log', 'INSERT')",
        False,
    ),
    (
        "projector-update",
        "has_any_column_privilege('app_projector', 'reflections_log', 'UPDATE')",
        False,
    ),
)

# Табличных DELETE / TRUNCATE на reflections_log нет ни у кого.
TABLE_PRIVILEGES_DENIED_0011: tuple[tuple[str, str], ...] = tuple(
    (role, priv)
    for role in ("app_bot", "app_api", "app_projector")
    for priv in ("DELETE", "TRUNCATE")
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_0011_reflections_log", MIGRATION_0011)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _migration_code(module) -> str:
    """Текст миграции без docstring модуля (в нём запреты названы словами)."""
    source = MIGRATION_0011.read_text(encoding="utf-8")
    assert module.__doc__ and module.__doc__ in source
    return source.replace(module.__doc__, "", 1)


@pytest.fixture
def bot_engine(migrated_db):
    engine = _bot_role_engine(migrated_db)
    try:
        yield engine
    finally:
        engine.dispose()


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


def _owner_insert(db_engine, pid, body: str, day_no: int = 6) -> None:
    with db_engine.begin() as conn:
        conn.execute(OWNER_INSERT, {"pid": pid, "d": day_no, "body": body})


# 1. Статика: revision, down_revision, нет UPDATE / DELETE / TRUNCATE, app_projector пуст.
def test_revision_0011():
    module = _load_migration()
    assert module.revision == "0011_reflections_log"
    assert module.down_revision == "0010_access_grants"


def test_privileges_static_0011():
    module = _load_migration()
    for privilege, target, role in module.PRIVILEGES:
        assert role != "app_projector", (privilege, target, role)
        if target == "TABLE reflections_log":
            verb = privilege.split()[0].upper()
            assert verb not in {"UPDATE", "DELETE", "TRUNCATE"}, (privilege, target, role)
    assert "ALTER DEFAULT PRIVILEGES" not in _migration_code(module).upper()
    assert module.REVOKE_SHORT_NO == (
        "REVOKE SELECT (short_no) ON TABLE tg_user_registry FROM app_bot"
    )


# 2. Права: контрактный SQL раздела 8 под ролями.
def test_api_insert_bot_reads(db_engine, api_engine, bot_engine):
    pid = _registry_pid(db_engine, 3601)
    with api_engine.begin() as conn:
        reflection_id = conn.execute(
            API_INSERT, {"pid": pid, "s": 1, "m": 2, "d": 6, "body": "заглушка рефлексии"}
        ).scalar_one()
    assert reflection_id > 0
    with bot_engine.connect() as conn:
        row = conn.execute(BOT_READ_REFLECTION, {"reflection_id": reflection_id}).one()
        owner = conn.execute(BOT_READ_SHORT_NO, {"pid": str(pid)}).one()
    assert row.pid == pid
    assert (row.stage_no, row.module_no, row.day_no) == (1, 2, 6)
    assert row.body == "заглушка рефлексии"
    assert row.created_at is not None
    assert owner.tg_user_id == 3601
    assert owner.short_no > 0


def test_revert_is_new_row(db_engine, api_engine):
    pid = _registry_pid(db_engine, 3602)
    params = {"pid": pid, "s": 1, "m": 1, "d": 6}
    with api_engine.begin() as conn:
        first = conn.execute(API_INSERT, {**params, "body": "первая"}).scalar_one()
    with api_engine.begin() as conn:
        second = conn.execute(API_INSERT, {**params, "body": "вторая"}).scalar_one()
    assert second != first
    with db_engine.connect() as conn:
        bodies = conn.execute(
            text("SELECT body FROM reflections_log WHERE pid = :p ORDER BY id"), {"p": pid}
        ).scalars().all()
    assert bodies == ["первая", "вторая"]


@pytest.mark.parametrize(
    ("name", "sql", "allowed"),
    PRIVILEGE_CHECKS_0011,
    ids=[c[0] for c in PRIVILEGE_CHECKS_0011],
)
def test_privileges_0011(db_engine, name, sql, allowed):
    with db_engine.connect() as conn:
        granted = conn.execute(text(f"SELECT {sql}")).scalar_one()
    assert granted is allowed, name


@pytest.mark.parametrize(("role", "privilege"), TABLE_PRIVILEGES_DENIED_0011)
def test_no_delete_truncate_0011(db_engine, role, privilege):
    with db_engine.connect() as conn:
        granted = conn.execute(
            text("SELECT has_table_privilege(:r, 'reflections_log', :p)"),
            {"r": role, "p": privilege},
        ).scalar_one()
    assert granted is False, (role, privilege)


@pytest.mark.parametrize("sql", API_DENIED_0011)
def test_app_api_denied_0011(api_engine, sql):
    _assert_denied(api_engine, sql)


@pytest.mark.parametrize("sql", BOT_DENIED_0011)
def test_app_bot_denied_0011(bot_engine, sql):
    _assert_denied(bot_engine, sql)


@pytest.mark.parametrize("sql", PROJECTOR_DENIED_0011)
def test_app_projector_denied_0011(projector_engine, sql):
    _assert_denied(projector_engine, sql)


# 3. CHECK длины текста, позиции дня и FK pid.
@pytest.mark.parametrize(
    "body",
    ["a", "   a   ", "", "x" * 2001],
    ids=["one-char", "one-char-padded", "empty", "len-2001"],
)
def test_body_len_rejected_0011(db_engine, body):
    from psycopg import errors as pg_errors

    pid = _registry_pid(db_engine, 3610)
    with pytest.raises(IntegrityError) as caught:
        _owner_insert(db_engine, pid, body)
    assert isinstance(caught.value.orig, pg_errors.CheckViolation)
    assert caught.value.orig.diag.constraint_name == "ck_reflections_log_body_len"


@pytest.mark.parametrize("body", ["ab", "x" * 2000], ids=["two-chars", "len-2000"])
def test_body_len_accepted_0011(db_engine, body):
    pid = _registry_pid(db_engine, 3611)
    _owner_insert(db_engine, pid, body)
    with db_engine.connect() as conn:
        stored = conn.execute(
            text("SELECT body FROM reflections_log WHERE pid = :p"), {"p": pid}
        ).scalar_one()
    assert stored == body


def test_day_no_zero_rejected_0011(db_engine):
    from psycopg import errors as pg_errors

    pid = _registry_pid(db_engine, 3612)
    with pytest.raises(IntegrityError) as caught:
        _owner_insert(db_engine, pid, "ab", day_no=0)
    assert isinstance(caught.value.orig, pg_errors.CheckViolation)
    assert caught.value.orig.diag.constraint_name == "ck_reflections_log_position_positive"


def test_unknown_pid_rejected_0011(db_engine):
    from psycopg import errors as pg_errors

    with pytest.raises(IntegrityError) as caught:
        _owner_insert(db_engine, uuid.uuid4(), "ab")
    assert isinstance(caught.value.orig, pg_errors.ForeignKeyViolation)
    assert caught.value.orig.diag.constraint_name == "reflections_log_pid_fkey"


# 4. ПОСЛЕДНИМ: downgrade до 0010 — таблицы нет, SELECT (short_no) у app_bot снят.
def test_downgrade_0011(migrated_db):
    from alembic import command

    cfg = _alembic_config()
    table_exists = text("SELECT to_regclass('public.reflections_log') IS NOT NULL")
    short_no = text(
        "SELECT has_column_privilege('app_bot', 'tg_user_registry', 'short_no', 'SELECT')"
    )
    tg_user_id = text(
        "SELECT has_column_privilege('app_bot', 'tg_user_registry', 'tg_user_id', 'SELECT')"
    )
    engine = create_engine(migrated_db)
    try:
        with engine.connect() as conn:
            assert conn.execute(table_exists).scalar_one() is True
            assert conn.execute(short_no).scalar_one() is True
        command.downgrade(cfg, "0010_access_grants")
        with engine.connect() as conn:
            assert conn.execute(table_exists).scalar_one() is False
            assert conn.execute(short_no).scalar_one() is False
            assert conn.execute(tg_user_id).scalar_one() is True  # право 0009 цело
    finally:
        command.upgrade(cfg, "head")
        engine.dispose()
