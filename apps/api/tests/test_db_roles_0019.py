"""db-pause-2: миграция 0019_life_writeoffs — журнал списаний жизней, права app_projector / app_bot.

Статические тесты (1) идут без БД. Тесты с БД — только в CI (соединение CI — суперпользователь,
оно делает SET ROLE). Роль переключается так же, как в test_db_roles_0017 (_bot_role_engine,
role_engine). Отказы — SQLSTATE 42501 (psycopg.errors.InsufficientPrivilege). db_engine
(conftest) чистит tg_user_registry с CASCADE. Событие для FK event_id вставляет владелец.
CHECK: каждый случай ломает одно ограничение; NULL ловит NOT NULL раньше CHECK.
tg_user_id — 4401–4499. Тест downgrade — последним в файле; в finally схема возвращается на head.
"""
import importlib.util
import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from tests.conftest import _alembic_config
from tests.test_db_roles import _assert_denied, role_engine
from tests.test_db_roles_0009 import _bot_role_engine

API_DIR = Path(__file__).resolve().parents[1]
MIGRATION_0019 = next(
    (API_DIR / "migrations" / "versions").glob("*0019_life_writeoffs*.py")
)

# Контракт T6a (проектор, app_projector): запись списания.
PROJECTOR_INSERT = text(
    "INSERT INTO life_writeoffs (pid, event_id, stage_no, module_no, day_no) "
    "VALUES (:pid, :event_id, :s, :m, :d) ON CONFLICT (event_id) DO NOTHING"
)
# Контракт T7 (бот, app_bot): списания после точки отката.
BOT_READ = text(
    "SELECT event_id, stage_no, module_no, day_no FROM life_writeoffs "
    "WHERE pid = :pid AND event_id > :after ORDER BY event_id"
)

OWNER_INSERT = text(
    "INSERT INTO life_writeoffs (pid, event_id, stage_no, module_no, day_no) "
    "VALUES (:pid, :event_id, :s, :m, :d)"
)
OWNER_COUNT = text("SELECT count(*) FROM life_writeoffs WHERE pid = :p")
OWNER_EVENT = text(
    "INSERT INTO participant_events (pid, kind, payload, actor, actor_role) "
    "VALUES (:p, 'test_0019', CAST(:payload AS jsonb), 'test', 'system') RETURNING id"
)

CK_STAGE = "ck_life_writeoffs_stage_no"
CK_MODULE = "ck_life_writeoffs_module_no"
CK_DAY = "ck_life_writeoffs_day_no"

EXPECTED_PRIVILEGES_0019: tuple[tuple[str, str, str], ...] = (
    (
        "INSERT (pid, event_id, stage_no, module_no, day_no)",
        "TABLE life_writeoffs",
        "app_projector",
    ),
    ("SELECT (event_id)", "TABLE life_writeoffs", "app_projector"),
    ("USAGE", "SEQUENCE life_writeoffs_id_seq", "app_projector"),
    (
        "SELECT (pid, event_id, stage_no, module_no, day_no)",
        "TABLE life_writeoffs",
        "app_bot",
    ),
)

WRITE_COLUMNS = ("pid", "event_id", "stage_no", "module_no", "day_no")


def _col(role: str, column: str, priv: str) -> str:
    return f"has_column_privilege('{role}', 'life_writeoffs', '{column}', '{priv}')"


# (имя, SQL-функция прав, ожидание).
PRIVILEGE_CHECKS_0019: tuple[tuple[str, str, bool], ...] = (
    *(
        (f"projector-insert-{c}", _col("app_projector", c, "INSERT"), True)
        for c in WRITE_COLUMNS
    ),
    ("projector-select-event-id", _col("app_projector", "event_id", "SELECT"), True),
    (
        "projector-seq-usage",
        "has_sequence_privilege('app_projector', 'life_writeoffs_id_seq', 'USAGE')",
        True,
    ),
    *((f"bot-select-{c}", _col("app_bot", c, "SELECT"), True) for c in WRITE_COLUMNS),
    ("projector-select-stage-no", _col("app_projector", "stage_no", "SELECT"), False),
    (
        "projector-update",
        "has_any_column_privilege('app_projector', 'life_writeoffs', 'UPDATE')",
        False,
    ),
    (
        "bot-insert",
        "has_any_column_privilege('app_bot', 'life_writeoffs', 'INSERT')",
        False,
    ),
    *(
        (
            f"api-{priv.lower()}",
            f"has_any_column_privilege('app_api', 'life_writeoffs', '{priv}')",
            False,
        )
        for priv in ("SELECT", "INSERT", "UPDATE", "REFERENCES")
    ),
    *(
        (
            f"api-table-{priv.lower()}",
            f"has_table_privilege('app_api', 'life_writeoffs', '{priv}')",
            False,
        )
        for priv in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE")
    ),
    (
        "api-seq-usage",
        "has_sequence_privilege('app_api', 'life_writeoffs_id_seq', 'USAGE')",
        False,
    ),
)

# Табличных DELETE / TRUNCATE на life_writeoffs нет ни у кого.
TABLE_PRIVILEGES_DENIED_0019: tuple[tuple[str, str], ...] = tuple(
    (role, priv)
    for role in ("app_api", "app_bot", "app_projector")
    for priv in ("DELETE", "TRUNCATE")
)

# (id, stage_no, module_no, day_no, ожидаемое имя CHECK).
REJECTED_0019: tuple[tuple[str, int, int, int, str], ...] = (
    ("stage-0", 0, 1, 1, CK_STAGE),
    ("module-0", 1, 0, 1, CK_MODULE),
    ("day-0", 1, 1, 0, CK_DAY),
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "mig_0019_life_writeoffs", MIGRATION_0019
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _migration_code(module) -> str:
    """Текст миграции без docstring модуля (в нём запреты названы словами)."""
    source = MIGRATION_0019.read_text(encoding="utf-8")
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


def _event_id(db_engine, pid) -> int:
    """Событие participant_events от владельца (для FK event_id); вернуть id."""
    with db_engine.begin() as conn:
        return conn.execute(
            OWNER_EVENT, {"p": pid, "payload": json.dumps({"schema_version": 1})}
        ).scalar_one()


def _owner_insert(db_engine, pid, event_id, s=1, m=1, d=1) -> None:
    with db_engine.begin() as conn:
        conn.execute(
            OWNER_INSERT, {"pid": pid, "event_id": event_id, "s": s, "m": m, "d": d}
        )


# 1. Статика: revision, down_revision, ROLES, PRIVILEGES, CHECKS, запреты.
def test_revision_0019():
    module = _load_migration()
    assert module.revision == "0019_life_writeoffs"
    assert module.down_revision == "0018_pauses"


def test_privileges_static_0019():
    module = _load_migration()
    assert module.ROLES == ("app_bot", "app_projector")
    assert module.PRIVILEGES == EXPECTED_PRIVILEGES_0019
    for privilege, target, role in module.PRIVILEGES:
        assert role != "app_api", (privilege, target, role)
        verb = privilege.split()[0].upper()
        assert verb not in {"UPDATE", "DELETE", "TRUNCATE"}, (privilege, target, role)
    code = _migration_code(module)
    assert "ALTER DEFAULT PRIVILEGES" not in code.upper()
    # Слово в верхнем регистре: строчное public допустимо в именах и импортах.
    assert "PUBLIC" not in code
    # GRANT — только в цикле по PRIVILEGES.
    assert code.count("GRANT ") == 1


def test_checks_static_0019():
    module = _load_migration()
    assert dict(module.CHECKS) == {
        CK_STAGE: "stage_no IS NOT NULL AND stage_no >= 1",
        CK_MODULE: "module_no IS NOT NULL AND module_no >= 1",
        CK_DAY: "day_no IS NOT NULL AND day_no >= 1",
    }


# 2. Права: выданное True, лишнее False.
@pytest.mark.parametrize(
    ("name", "sql", "allowed"),
    PRIVILEGE_CHECKS_0019,
    ids=[c[0] for c in PRIVILEGE_CHECKS_0019],
)
def test_privileges_0019(db_engine, name, sql, allowed):
    with db_engine.connect() as conn:
        granted = conn.execute(text(f"SELECT {sql}")).scalar_one()
    assert granted is allowed, name


@pytest.mark.parametrize(("role", "privilege"), TABLE_PRIVILEGES_DENIED_0019)
def test_no_delete_truncate_0019(db_engine, role, privilege):
    with db_engine.connect() as conn:
        granted = conn.execute(
            text("SELECT has_table_privilege(:r, 'life_writeoffs', :p)"),
            {"r": role, "p": privilege},
        ).scalar_one()
    assert granted is False, (role, privilege)


# 3. Контракт раздела 7 под app_projector и app_bot; отказы.
def test_projector_contract_0019(db_engine, projector_engine):
    pid = _registry_pid(db_engine, 4401)
    event_id = _event_id(db_engine, pid)
    params = {"pid": pid, "event_id": event_id, "s": 1, "m": 2, "d": 3}
    with projector_engine.begin() as conn:
        first = conn.execute(PROJECTOR_INSERT, params)
    assert first.rowcount == 1

    with projector_engine.begin() as conn:
        again = conn.execute(PROJECTOR_INSERT, {**params, "d": 4})
    assert again.rowcount == 0
    with db_engine.connect() as conn:
        assert conn.execute(OWNER_COUNT, {"p": pid}).scalar_one() == 1


def test_bot_reads_0019(db_engine, bot_engine):
    pid = _registry_pid(db_engine, 4402)
    other_pid = _registry_pid(db_engine, 4403)
    events = [_event_id(db_engine, pid) for _ in range(3)]
    other_event = _event_id(db_engine, other_pid)
    # Вставка не по порядку event_id — выборка всё равно в порядке event_id.
    _owner_insert(db_engine, pid, events[2], 1, 1, 3)
    _owner_insert(db_engine, pid, events[0], 1, 1, 1)
    _owner_insert(db_engine, pid, events[1], 1, 1, 2)
    _owner_insert(db_engine, other_pid, other_event, 2, 2, 2)
    with bot_engine.connect() as conn:
        rows = conn.execute(BOT_READ, {"pid": pid, "after": events[0]}).all()
    assert [tuple(r) for r in rows] == [
        (events[1], 1, 1, 2),
        (events[2], 1, 1, 3),
    ]


def test_app_bot_insert_denied_0019(db_engine, bot_engine):
    pid = _registry_pid(db_engine, 4404)
    event_id = _event_id(db_engine, pid)
    _assert_denied(
        bot_engine,
        "INSERT INTO life_writeoffs (pid, event_id, stage_no, module_no, day_no) "
        f"VALUES ('{pid}', {event_id}, 1, 1, 1)",
    )


def test_app_projector_select_stage_denied_0019(projector_engine):
    _assert_denied(projector_engine, "SELECT stage_no FROM life_writeoffs")


def test_app_api_select_denied_0019(api_engine):
    _assert_denied(api_engine, "SELECT event_id FROM life_writeoffs")


# 4. CHECK и NOT NULL (вставка владельцем, имя ограничения в diag).
@pytest.mark.parametrize(
    ("case", "s", "m", "d", "constraint"),
    REJECTED_0019,
    ids=[c[0] for c in REJECTED_0019],
)
def test_check_rejected_0019(db_engine, case, s, m, d, constraint):
    from psycopg import errors as pg_errors

    pid = _registry_pid(db_engine, 4410)
    event_id = _event_id(db_engine, pid)
    with pytest.raises(IntegrityError) as caught:
        _owner_insert(db_engine, pid, event_id, s, m, d)
    assert isinstance(caught.value.orig, pg_errors.CheckViolation), case
    assert caught.value.orig.diag.constraint_name == constraint, case


def test_check_accepted_0019(db_engine):
    pid = _registry_pid(db_engine, 4411)
    event_id = _event_id(db_engine, pid)
    _owner_insert(db_engine, pid, event_id, 1, 1, 1)
    with db_engine.connect() as conn:
        assert conn.execute(OWNER_COUNT, {"p": pid}).scalar_one() == 1


@pytest.mark.parametrize("column", ["pid", "event_id", "stage_no", "module_no", "day_no"])
def test_not_null_0019(db_engine, column):
    from psycopg import errors as pg_errors

    pid = _registry_pid(db_engine, 4412)
    event_id = _event_id(db_engine, pid)
    values = {"pid": pid, "event_id": event_id, "s": 1, "m": 1, "d": 1}
    key = {
        "pid": "pid",
        "event_id": "event_id",
        "stage_no": "s",
        "module_no": "m",
        "day_no": "d",
    }[column]
    values[key] = None
    with pytest.raises(IntegrityError) as caught:
        with db_engine.begin() as conn:
            conn.execute(OWNER_INSERT, values)
    assert isinstance(caught.value.orig, pg_errors.NotNullViolation), column
    assert caught.value.orig.diag.column_name == column


# 5. UNIQUE event_id, FK pid и event_id, индекс (pid, event_id) не UNIQUE.
def test_duplicate_event_rejected_0019(db_engine):
    from psycopg import errors as pg_errors

    pid = _registry_pid(db_engine, 4413)
    event_id = _event_id(db_engine, pid)
    _owner_insert(db_engine, pid, event_id, 1, 1, 1)
    with pytest.raises(IntegrityError) as caught:
        _owner_insert(db_engine, pid, event_id, 1, 1, 2)
    assert isinstance(caught.value.orig, pg_errors.UniqueViolation)
    assert caught.value.orig.diag.constraint_name == "life_writeoffs_event_id_key"


def test_unknown_pid_rejected_0019(db_engine):
    from psycopg import errors as pg_errors

    pid = _registry_pid(db_engine, 4414)
    event_id = _event_id(db_engine, pid)
    with pytest.raises(IntegrityError) as caught:
        _owner_insert(db_engine, uuid.uuid4(), event_id)
    assert isinstance(caught.value.orig, pg_errors.ForeignKeyViolation)
    assert caught.value.orig.diag.constraint_name == "life_writeoffs_pid_fkey"


def test_unknown_event_rejected_0019(db_engine):
    from psycopg import errors as pg_errors

    pid = _registry_pid(db_engine, 4415)
    with db_engine.connect() as conn:
        missing = conn.execute(
            text("SELECT coalesce(max(id), 0) + 1000000 FROM participant_events")
        ).scalar_one()
    with pytest.raises(IntegrityError) as caught:
        _owner_insert(db_engine, pid, missing)
    assert isinstance(caught.value.orig, pg_errors.ForeignKeyViolation)
    assert caught.value.orig.diag.constraint_name == "life_writeoffs_event_id_fkey"


def test_index_0019(db_engine):
    with db_engine.connect() as conn:
        indexdef = conn.execute(
            text(
                "SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' "
                "AND tablename = 'life_writeoffs' "
                "AND indexname = 'life_writeoffs_pid_event_idx'"
            )
        ).scalar_one()
        unique = conn.execute(
            text(
                "SELECT i.indisunique FROM pg_index i "
                "JOIN pg_class c ON c.oid = i.indexrelid "
                "WHERE c.relname = 'life_writeoffs_pid_event_idx'"
            )
        ).scalar_one()
    assert unique is False
    assert "UNIQUE" not in indexdef.upper()
    assert indexdef.endswith("(pid, event_id)")


# 6. ПОСЛЕДНИМ: downgrade до 0018 — life_writeoffs нет, таблицы и право 0018 целы.
def test_downgrade_0019(migrated_db):
    from alembic import command

    cfg = _alembic_config()
    lw_exists = text("SELECT to_regclass('public.life_writeoffs') IS NOT NULL")
    pauses_exists = text("SELECT to_regclass('public.participant_pauses') IS NOT NULL")
    budgets_exists = text("SELECT to_regclass('public.pause_budgets') IS NOT NULL")
    bot_events_insert = text(
        "SELECT has_any_column_privilege('app_bot', 'participant_events', 'INSERT')"
    )
    engine = create_engine(migrated_db)
    try:
        with engine.connect() as conn:
            assert conn.execute(lw_exists).scalar_one() is True
        command.downgrade(cfg, "0018_pauses")
        with engine.connect() as conn:
            assert conn.execute(lw_exists).scalar_one() is False
            assert conn.execute(pauses_exists).scalar_one() is True
            assert conn.execute(budgets_exists).scalar_one() is True
            assert conn.execute(bot_events_insert).scalar_one() is True  # право 0018 цело
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            assert conn.execute(lw_exists).scalar_one() is True
    finally:
        command.upgrade(cfg, "head")
        engine.dispose()
