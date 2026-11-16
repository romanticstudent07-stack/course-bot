"""db-pause-1: миграция 0018_pauses — participant_pauses, pause_budgets, права, бэкфилл бюджета.

Статические тесты (1) идут без БД. Тесты с БД — только в CI (соединение CI — суперпользователь,
оно делает SET ROLE). Роли: app_api и app_projector — tests.test_db_roles.role_engine,
app_bot — tests.test_db_roles_0009._bot_role_engine (как в test_db_roles_0017). Отказы —
SQLSTATE 42501 (psycopg.errors.InsufficientPrivilege). db_engine (conftest) чистит
tg_user_registry с CASCADE, и строки новых таблиц (FK pid) уходят вместе с ней.
CHECK: каждый случай ломает одно ограничение; NULL ловит NOT NULL раньше CHECK.
tg_user_id — 4301–4399. Тест downgrade — последним в файле; в finally схема возвращается на head.
"""
import importlib.util
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app import day_clock
from tests.conftest import _alembic_config
from tests.test_db_roles import _assert_denied, role_engine
from tests.test_db_roles_0009 import _bot_role_engine

API_DIR = Path(__file__).resolve().parents[1]
MIGRATION_0018 = next((API_DIR / "migrations" / "versions").glob("*0018_pauses*.py"))

MSK = ZoneInfo("Europe/Moscow")
START = datetime(2026, 11, 20, 0, 0, tzinfo=MSK)

PP_COLUMNS: tuple[str, ...] = (
    "id",
    "pid",
    "kind",
    "status",
    "start_at",
    "planned_end_at",
    "ended_at",
    "stage_no",
    "restart_no",
    "client_op_id",
    "created_at",
)
PB_COLUMNS: tuple[str, ...] = (
    "pid",
    "days_budget_remaining_annual",
    "cycle_start_at",
    "restart_no",
)
PP = ", ".join(PP_COLUMNS)
PB = ", ".join(PB_COLUMNS)

EXPECTED_PRIVILEGES_0018: tuple[tuple[str, str, str], ...] = (
    (
        "INSERT (pid, kind, status, start_at, planned_end_at, client_op_id)",
        "TABLE participant_pauses",
        "app_api",
    ),
    (f"SELECT ({PP})", "TABLE participant_pauses", "app_api"),
    ("USAGE", "SEQUENCE participant_pauses_id_seq", "app_api"),
    (f"SELECT ({PB})", "TABLE pause_budgets", "app_api"),
    (f"SELECT ({PP})", "TABLE participant_pauses", "app_projector"),
    (
        "UPDATE (status, stage_no, restart_no, ended_at)",
        "TABLE participant_pauses",
        "app_projector",
    ),
    (f"SELECT ({PB})", "TABLE pause_budgets", "app_projector"),
    (f"INSERT ({PB})", "TABLE pause_budgets", "app_projector"),
    (
        "UPDATE (days_budget_remaining_annual, cycle_start_at, restart_no)",
        "TABLE pause_budgets",
        "app_projector",
    ),
)

EXPECTED_FOREIGN_PRIVILEGES_0018: tuple[tuple[str, str, str], ...] = (
    ("INSERT (pid, kind, payload, actor, actor_role)", "TABLE participant_events", "app_bot"),
    ("USAGE", "SEQUENCE participant_events_id_seq", "app_bot"),
    ("INSERT (key, kind, result_ref)", "TABLE idempotency_keys", "app_bot"),
    ("SELECT (key, result_ref)", "TABLE idempotency_keys", "app_bot"),
)

CK_KIND = "ck_participant_pauses_kind"
CK_STATUS = "ck_participant_pauses_status"
CK_PERIOD = "ck_participant_pauses_period"
CK_USER_MAX = "ck_participant_pauses_user_max"
CK_USER_STAGE = "ck_participant_pauses_user_stage"
CK_ENDED_AT = "ck_participant_pauses_ended_at"
CK_STAGE_NO = "ck_participant_pauses_stage_no"
CK_RESTART_NO = "ck_participant_pauses_restart_no"
CK_OP = "ck_participant_pauses_client_op_id"
CK_BUDGET_DAYS = "ck_pause_budgets_days_remaining"
CK_BUDGET_RESTART = "ck_pause_budgets_restart_no"

EXPECTED_CHECKS_PAUSES: dict[str, str] = {
    CK_KIND: "kind IS NOT NULL AND kind IN ('user', 'author', 'shadow')",
    CK_STATUS: "status IS NOT NULL AND status IN "
    "('requested', 'approved', 'active', 'ended', 'cancelled', 'rejected')",
    CK_PERIOD: "start_at IS NOT NULL AND planned_end_at IS NOT NULL "
    "AND planned_end_at > start_at",
    CK_USER_MAX: "kind IS NOT NULL AND start_at IS NOT NULL AND planned_end_at IS NOT NULL "
    "AND (kind <> 'user' OR planned_end_at <= start_at + interval '169 hours')",
    CK_USER_STAGE: "kind IS NOT NULL AND status IS NOT NULL AND (kind <> 'user' "
    "OR status NOT IN ('active', 'ended') OR (stage_no IS NOT NULL AND restart_no IS NOT NULL))",
    CK_ENDED_AT: "status IS NOT NULL AND (status <> 'ended' OR ended_at IS NOT NULL)",
    CK_STAGE_NO: "stage_no IS NULL OR stage_no >= 1",
    CK_RESTART_NO: "restart_no IS NULL OR restart_no >= 0",
    CK_OP: "client_op_id IS NOT NULL AND char_length(client_op_id) BETWEEN 1 AND 64",
}

EXPECTED_CHECKS_BUDGETS: dict[str, str] = {
    CK_BUDGET_DAYS: "days_budget_remaining_annual IS NOT NULL "
    "AND days_budget_remaining_annual >= 0",
    CK_BUDGET_RESTART: "restart_no IS NOT NULL AND restart_no >= 0",
}

IX_ONE_ACTIVE = "participant_pauses_one_active_uq"
IX_ONE_OPEN = "participant_pauses_one_open_user_uq"
IX_STAGE_TAKEN = "participant_pauses_stage_taken_uq"

# Контракт T3 (API, app_api).
API_INSERT = text(
    "INSERT INTO participant_pauses (pid, kind, status, start_at, planned_end_at, client_op_id) "
    "VALUES (:pid, 'user', 'requested', :start, :end, :op) "
    "ON CONFLICT (pid, client_op_id) DO NOTHING RETURNING id"
)
API_LIST = text("SELECT * FROM participant_pauses WHERE pid = :pid ORDER BY id DESC")
API_BUDGET = text(
    "SELECT days_budget_remaining_annual, cycle_start_at, restart_no FROM pause_budgets "
    "WHERE pid = :pid"
)
# Контракт T2 (проектор, app_projector).
PROJECTOR_ACTIVATE = text(
    "UPDATE participant_pauses SET status = 'active', stage_no = :s, restart_no = :r "
    "WHERE id = :id AND status = 'approved'"
)
PROJECTOR_UPSERT_BUDGET = text(
    "INSERT INTO pause_budgets (pid, days_budget_remaining_annual, cycle_start_at, restart_no) "
    "VALUES (:pid, :d, :c, :r) ON CONFLICT (pid) DO UPDATE SET "
    "days_budget_remaining_annual = EXCLUDED.days_budget_remaining_annual, "
    "cycle_start_at = EXCLUDED.cycle_start_at, restart_no = EXCLUDED.restart_no"
)
# Контракт T4, T6b, T7 (бот, app_bot), без RETURNING.
BOT_KEY_INSERT = text(
    "INSERT INTO idempotency_keys (key, kind, result_ref) VALUES (:key, :kind, :ref) "
    "ON CONFLICT (key) DO NOTHING"
)
BOT_KEY_READ = text("SELECT result_ref FROM idempotency_keys WHERE key = :key")
BOT_EVENT_INSERT = text(
    "INSERT INTO participant_events (pid, kind, payload, actor, actor_role) "
    "VALUES (:pid, :kind, :payload, :actor, :role)"
)

OWNER_PAUSE = text(
    "INSERT INTO participant_pauses (pid, kind, status, start_at, planned_end_at, ended_at, "
    "stage_no, restart_no, client_op_id) VALUES (:pid, :kind, :status, :start, :end, :ended, "
    ":stage, :restart, :op) RETURNING id"
)
OWNER_BUDGET = text(
    "INSERT INTO pause_budgets (pid, days_budget_remaining_annual, cycle_start_at, restart_no) "
    "VALUES (:pid, :d, :c, :r)"
)
OWNER_BUDGET_NO_RESTART = text(
    "INSERT INTO pause_budgets (pid, days_budget_remaining_annual, cycle_start_at) "
    "VALUES (:pid, :d, :c)"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_0018_pauses", MIGRATION_0018)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _migration_code(module) -> str:
    """Текст миграции без docstring модуля (в нём запреты названы словами)."""
    source = MIGRATION_0018.read_text(encoding="utf-8")
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


def _registry_pid(engine, tg_id: int, *, tombstoned: bool = False) -> uuid.UUID:
    """Строка tg_user_registry от владельца; вернуть pid."""
    pid = uuid.uuid4()
    tombstone = "now()" if tombstoned else "NULL"
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tg_user_registry (pid, tg_user_id, created_via, tombstoned_at) "
                f"VALUES (:p, :t, 'mini_app_first_launch', {tombstone})"
            ),
            {"p": pid, "t": tg_id},
        )
    return pid


def _pause(
    pid,
    *,
    kind="user",
    status="requested",
    start=START,
    hours=24,
    ended=None,
    stage=None,
    restart=None,
    op="op",
) -> dict:
    return {
        "pid": pid,
        "kind": kind,
        "status": status,
        "start": start,
        "end": start + timedelta(hours=hours),
        "ended": ended,
        "stage": stage,
        "restart": restart,
        "op": op,
    }


def _owner_pause(engine, values: dict) -> int:
    with engine.begin() as conn:
        return conn.execute(OWNER_PAUSE, values).scalar_one()


# 1. Статика: revision, роли, права, CHECK, нет ALTER DEFAULT PRIVILEGES и PUBLIC, один GRANT.
def test_revision_0018():
    module = _load_migration()
    assert module.revision == "0018_pauses"
    assert module.down_revision == "0017_support_questions"


def test_privileges_static_0018():
    module = _load_migration()
    assert module.ROLES == ("app_api", "app_bot", "app_projector")
    assert module.PRIVILEGES == EXPECTED_PRIVILEGES_0018
    assert module.FOREIGN_PRIVILEGES == EXPECTED_FOREIGN_PRIVILEGES_0018
    code = _migration_code(module)
    assert "ALTER DEFAULT PRIVILEGES" not in code.upper()
    # Слово в верхнем регистре: строчное public допустимо в именах и импортах.
    assert "PUBLIC" not in code
    # GRANT — только в одном цикле по (*PRIVILEGES, *FOREIGN_PRIVILEGES).
    assert code.count("GRANT ") == 1


def test_checks_static_0018():
    module = _load_migration()
    assert dict(module.CHECKS_PAUSES) == EXPECTED_CHECKS_PAUSES
    assert dict(module.CHECKS_BUDGETS) == EXPECTED_CHECKS_BUDGETS


# 2. Права: выданное — True, запрещённое — False.
def _granted_checks() -> list[tuple[str, str, bool]]:
    checks: list[tuple[str, str, bool]] = []
    for privilege, target, role in (
        *EXPECTED_PRIVILEGES_0018,
        *EXPECTED_FOREIGN_PRIVILEGES_0018,
    ):
        kind, obj = target.split(" ", 1)
        if kind == "SEQUENCE":
            checks.append(
                (
                    f"{role}-{obj}-usage",
                    f"has_sequence_privilege('{role}', '{obj}', 'USAGE')",
                    True,
                )
            )
            continue
        verb, columns = privilege.split(" ", 1)
        for column in columns.strip("()").split(", "):
            checks.append(
                (
                    f"{role}-{obj}-{column}-{verb.lower()}",
                    f"has_column_privilege('{role}', '{obj}', '{column}', '{verb}')",
                    True,
                )
            )
    return checks


DENIED_CHECKS_0018: tuple[tuple[str, str, bool], ...] = (
    (
        "api-update-pauses",
        "has_any_column_privilege('app_api', 'participant_pauses', 'UPDATE')",
        False,
    ),
    *(
        (
            f"bot-{verb.lower()}-{table}",
            f"has_any_column_privilege('app_bot', '{table}', '{verb}')",
            False,
        )
        for table in ("participant_pauses", "pause_budgets")
        for verb in ("SELECT", "INSERT", "UPDATE")
    ),
    (
        "bot-pauses-seq",
        "has_sequence_privilege('app_bot', 'participant_pauses_id_seq', 'USAGE')",
        False,
    ),
    (
        "projector-insert-pauses",
        "has_any_column_privilege('app_projector', 'participant_pauses', 'INSERT')",
        False,
    ),
    (
        "bot-select-payload-events",
        "has_column_privilege('app_bot', 'participant_events', 'payload', 'SELECT')",
        False,
    ),
    *(
        (
            f"{role}-{verb.lower()}-{table}",
            f"has_table_privilege('{role}', '{table}', '{verb}')",
            False,
        )
        for role in ("app_api", "app_bot", "app_projector")
        for table in ("participant_pauses", "pause_budgets")
        for verb in ("DELETE", "TRUNCATE")
    ),
)

PRIVILEGE_CHECKS_0018: tuple[tuple[str, str, bool], ...] = (
    *_granted_checks(),
    *DENIED_CHECKS_0018,
)


@pytest.mark.parametrize(
    ("name", "sql", "allowed"),
    PRIVILEGE_CHECKS_0018,
    ids=[c[0] for c in PRIVILEGE_CHECKS_0018],
)
def test_privileges_0018(db_engine, name, sql, allowed):
    with db_engine.connect() as conn:
        granted = conn.execute(text(f"SELECT {sql}")).scalar_one()
    assert granted is allowed, name


# 3. Контракт раздела 7 под ролями.
def test_api_contract_0018(db_engine, api_engine):
    pid = _registry_pid(db_engine, 4301)
    params = {"pid": pid, "start": START, "end": START + timedelta(days=7), "op": "op-1"}
    with api_engine.begin() as conn:
        pause_id = conn.execute(API_INSERT, params).scalar_one()
    assert pause_id > 0
    with api_engine.begin() as conn:
        again = conn.execute(API_INSERT, params).first()
    assert again is None

    cycle = datetime(2026, 11, 1, 0, 0, tzinfo=MSK)
    with db_engine.begin() as conn:
        conn.execute(OWNER_BUDGET, {"pid": pid, "d": 14, "c": cycle, "r": 0})
    with api_engine.connect() as conn:
        rows = conn.execute(API_LIST, {"pid": pid}).all()
        budget = conn.execute(API_BUDGET, {"pid": pid}).one()
    assert [row.id for row in rows] == [pause_id]
    assert (rows[0].kind, rows[0].status, rows[0].client_op_id) == ("user", "requested", "op-1")
    assert tuple(rows[0]._mapping.keys()) == PP_COLUMNS
    assert budget.days_budget_remaining_annual == 14
    assert budget.cycle_start_at == cycle
    assert budget.restart_no == 0


def test_projector_contract_0018(db_engine, projector_engine):
    pid = _registry_pid(db_engine, 4302)
    pause_id = _owner_pause(db_engine, _pause(pid, status="approved"))
    with projector_engine.begin() as conn:
        updated = conn.execute(PROJECTOR_ACTIVATE, {"id": pause_id, "s": 1, "r": 0}).rowcount
    assert updated == 1
    with projector_engine.begin() as conn:
        again = conn.execute(PROJECTOR_ACTIVATE, {"id": pause_id, "s": 1, "r": 0}).rowcount
    assert again == 0

    cycle = datetime(2026, 11, 1, 0, 0, tzinfo=MSK)
    with projector_engine.begin() as conn:
        conn.execute(PROJECTOR_UPSERT_BUDGET, {"pid": pid, "d": 14, "c": cycle, "r": 0})
    with projector_engine.begin() as conn:
        conn.execute(PROJECTOR_UPSERT_BUDGET, {"pid": pid, "d": 7, "c": cycle, "r": 1})
    with db_engine.connect() as conn:
        status = conn.execute(
            text("SELECT status, stage_no, restart_no FROM participant_pauses WHERE id = :id"),
            {"id": pause_id},
        ).one()
        budget = conn.execute(
            text(f"SELECT {PB} FROM pause_budgets WHERE pid = :p"), {"p": pid}
        ).one()
    assert tuple(status) == ("active", 1, 0)
    assert (budget.days_budget_remaining_annual, budget.restart_no) == (7, 1)
    assert budget.cycle_start_at == cycle


def test_bot_contract_0018(db_engine, bot_engine):
    from sqlalchemy import bindparam
    from sqlalchemy.dialects.postgresql import JSONB

    pid = _registry_pid(db_engine, 4303)
    key = f"pause_test:{pid}:op-1"
    with bot_engine.begin() as conn:
        conn.execute(BOT_KEY_INSERT, {"key": key, "kind": "pause_test", "ref": "ref-1"})
    with bot_engine.begin() as conn:
        conn.execute(BOT_KEY_INSERT, {"key": key, "kind": "pause_test", "ref": "ref-2"})
        assert conn.execute(BOT_KEY_READ, {"key": key}).scalar_one() == "ref-1"

    event = BOT_EVENT_INSERT.bindparams(bindparam("payload", type_=JSONB))
    with bot_engine.begin() as conn:
        conn.execute(
            event,
            {
                "pid": pid,
                "kind": "test_0018",
                "payload": {"schema_version": 1},
                "actor": "bot",
                "role": "system",
            },
        )
    with db_engine.connect() as conn:
        payload = conn.execute(
            text("SELECT payload FROM participant_events WHERE pid = :p AND kind = 'test_0018'"),
            {"p": pid},
        ).scalar_one()
    assert payload == {"schema_version": 1}


def test_api_update_pauses_denied_0018(api_engine):
    _assert_denied(api_engine, "UPDATE participant_pauses SET status = 'active'")


def test_bot_select_pauses_denied_0018(bot_engine):
    _assert_denied(bot_engine, "SELECT id FROM participant_pauses")


def test_api_insert_budget_denied_0018(api_engine):
    _assert_denied(
        api_engine,
        "INSERT INTO pause_budgets (pid, days_budget_remaining_annual, cycle_start_at) "
        "VALUES (gen_random_uuid(), 14, now())",
    )


# 4. CHECK (вставка владельцем, имя ограничения в diag).
# (id, поля _pause, ожидаемое имя CHECK).
REJECTED_PAUSES_0018: tuple[tuple[str, dict, str], ...] = (
    ("kind-User", {"kind": "User"}, CK_KIND),
    ("status-paused", {"status": "paused"}, CK_STATUS),
    ("period-equal", {"hours": 0}, CK_PERIOD),
    ("user-170h", {"hours": 170}, CK_USER_MAX),
    ("user-active-no-stage", {"status": "active", "restart": 0}, CK_USER_STAGE),
    (
        "ended-no-ended-at",
        {"status": "ended", "stage": 1, "restart": 0},
        CK_ENDED_AT,
    ),
    ("stage-0", {"stage": 0}, CK_STAGE_NO),
    ("restart-minus-1", {"restart": -1}, CK_RESTART_NO),
    ("op-empty", {"op": ""}, CK_OP),
    ("op-65", {"op": "x" * 65}, CK_OP),
)

ACCEPTED_PAUSES_0018: tuple[tuple[str, dict], ...] = (
    ("author-170h", {"kind": "author", "hours": 170}),
    ("user-requested-no-stage", {}),
    ("user-active-stage-1-restart-0", {"status": "active", "stage": 1, "restart": 0}),
    ("user-169h", {"hours": 169}),
    ("op-64", {"op": "x" * 64}),
)

# (id, остаток, restart_no, ожидаемое имя CHECK).
REJECTED_BUDGETS_0018: tuple[tuple[str, int, int, str], ...] = (
    ("budget-days-minus-1", -1, 0, CK_BUDGET_DAYS),
    ("budget-restart-minus-1", 14, -1, CK_BUDGET_RESTART),
)


@pytest.mark.parametrize(
    ("case", "fields", "constraint"),
    REJECTED_PAUSES_0018,
    ids=[c[0] for c in REJECTED_PAUSES_0018],
)
def test_pause_check_rejected_0018(db_engine, case, fields, constraint):
    from psycopg import errors as pg_errors

    pid = _registry_pid(db_engine, 4310)
    with pytest.raises(IntegrityError) as caught:
        _owner_pause(db_engine, _pause(pid, **fields))
    assert isinstance(caught.value.orig, pg_errors.CheckViolation), case
    assert caught.value.orig.diag.constraint_name == constraint, case


@pytest.mark.parametrize(
    ("case", "fields"),
    ACCEPTED_PAUSES_0018,
    ids=[c[0] for c in ACCEPTED_PAUSES_0018],
)
def test_pause_check_accepted_0018(db_engine, case, fields):
    pid = _registry_pid(db_engine, 4311)
    assert _owner_pause(db_engine, _pause(pid, **fields)) > 0, case


@pytest.mark.parametrize(
    ("case", "days", "restart", "constraint"),
    REJECTED_BUDGETS_0018,
    ids=[c[0] for c in REJECTED_BUDGETS_0018],
)
def test_budget_check_rejected_0018(db_engine, case, days, restart, constraint):
    from psycopg import errors as pg_errors

    pid = _registry_pid(db_engine, 4312)
    with pytest.raises(IntegrityError) as caught:
        with db_engine.begin() as conn:
            conn.execute(OWNER_BUDGET, {"pid": pid, "d": days, "c": START, "r": restart})
    assert isinstance(caught.value.orig, pg_errors.CheckViolation), case
    assert caught.value.orig.diag.constraint_name == constraint, case


# 5. Частичные UNIQUE-индексы.
# (id, первая пауза, вторая пауза, имя индекса).
INDEX_REJECTED_0018: tuple[tuple[str, dict, dict, str], ...] = (
    (
        "second-active",
        {"kind": "author", "status": "active"},
        {"kind": "author", "status": "active"},
        IX_ONE_ACTIVE,
    ),
    ("second-user-requested", {}, {"status": "requested"}, IX_ONE_OPEN),
    ("second-user-approved", {}, {"status": "approved"}, IX_ONE_OPEN),
    (
        "second-user-ended-same-stage",
        {"status": "ended", "stage": 1, "restart": 0, "ended": START},
        {"status": "ended", "stage": 1, "restart": 0, "ended": START},
        IX_STAGE_TAKEN,
    ),
)

INDEX_ACCEPTED_0018: tuple[tuple[str, dict, dict], ...] = (
    ("requested-and-cancelled", {"status": "cancelled"}, {"status": "requested"}),
    (
        "ended-next-restart",
        {"status": "ended", "stage": 1, "restart": 0, "ended": START},
        {"status": "ended", "stage": 1, "restart": 1, "ended": START},
    ),
    (
        "author-active-after-user-ended",
        {"status": "ended", "stage": 1, "restart": 0, "ended": START},
        {"kind": "author", "status": "active"},
    ),
)


@pytest.mark.parametrize(
    ("case", "first", "second", "index"),
    INDEX_REJECTED_0018,
    ids=[c[0] for c in INDEX_REJECTED_0018],
)
def test_index_rejected_0018(db_engine, case, first, second, index):
    from psycopg import errors as pg_errors

    pid = _registry_pid(db_engine, 4320)
    _owner_pause(db_engine, _pause(pid, op="op-1", **first))
    with pytest.raises(IntegrityError) as caught:
        _owner_pause(db_engine, _pause(pid, op="op-2", **second))
    assert isinstance(caught.value.orig, pg_errors.UniqueViolation), case
    assert caught.value.orig.diag.constraint_name == index, case


@pytest.mark.parametrize(
    ("case", "first", "second"),
    INDEX_ACCEPTED_0018,
    ids=[c[0] for c in INDEX_ACCEPTED_0018],
)
def test_index_accepted_0018(db_engine, case, first, second):
    pid = _registry_pid(db_engine, 4321)
    _owner_pause(db_engine, _pause(pid, op="op-1", **first))
    assert _owner_pause(db_engine, _pause(pid, op="op-2", **second)) > 0, case


# 6. FK pid и NOT NULL по каждой NOT NULL колонке без DEFAULT.
def test_unknown_pid_pause_rejected_0018(db_engine):
    from psycopg import errors as pg_errors

    with pytest.raises(IntegrityError) as caught:
        _owner_pause(db_engine, _pause(uuid.uuid4()))
    assert isinstance(caught.value.orig, pg_errors.ForeignKeyViolation)
    assert caught.value.orig.diag.constraint_name == "participant_pauses_pid_fkey"


def test_unknown_pid_budget_rejected_0018(db_engine):
    from psycopg import errors as pg_errors

    with pytest.raises(IntegrityError) as caught:
        with db_engine.begin() as conn:
            conn.execute(OWNER_BUDGET, {"pid": uuid.uuid4(), "d": 14, "c": START, "r": 0})
    assert isinstance(caught.value.orig, pg_errors.ForeignKeyViolation)
    assert caught.value.orig.diag.constraint_name == "pause_budgets_pid_fkey"


# колонка participant_pauses → ключ _pause.
PAUSE_NOT_NULL_0018: dict[str, str] = {
    "pid": "pid",
    "kind": "kind",
    "status": "status",
    "start_at": "start",
    "planned_end_at": "end",
    "client_op_id": "op",
}


@pytest.mark.parametrize("column", list(PAUSE_NOT_NULL_0018))
def test_pause_not_null_0018(db_engine, column):
    from psycopg import errors as pg_errors

    pid = _registry_pid(db_engine, 4330)
    values = _pause(pid)
    values[PAUSE_NOT_NULL_0018[column]] = None
    with pytest.raises(IntegrityError) as caught:
        _owner_pause(db_engine, values)
    assert isinstance(caught.value.orig, pg_errors.NotNullViolation), column
    assert caught.value.orig.diag.column_name == column


# колонка pause_budgets → ключ OWNER_BUDGET_NO_RESTART (restart_no имеет DEFAULT 0).
BUDGET_NOT_NULL_0018: dict[str, str] = {
    "pid": "pid",
    "days_budget_remaining_annual": "d",
    "cycle_start_at": "c",
}


@pytest.mark.parametrize("column", list(BUDGET_NOT_NULL_0018))
def test_budget_not_null_0018(db_engine, column):
    from psycopg import errors as pg_errors

    pid = _registry_pid(db_engine, 4331)
    values = {"pid": pid, "d": 14, "c": START}
    values[BUDGET_NOT_NULL_0018[column]] = None
    with pytest.raises(IntegrityError) as caught:
        with db_engine.begin() as conn:
            conn.execute(OWNER_BUDGET_NO_RESTART, values)
    assert isinstance(caught.value.orig, pg_errors.NotNullViolation), column
    assert caught.value.orig.diag.column_name == column


# 7. Бэкфилл: данные владельцем при схеме 0017, затем upgrade.
def _state_row(conn, pid, tz: str) -> None:
    conn.execute(
        text(
            "INSERT INTO participant_state (pid, lifecycle_phase, updated_at, "
            "projector_version, tz) VALUES (:p, 'onboarding', now(), 1, :tz)"
        ),
        {"p": pid, "tz": tz},
    )


def _day_entered(conn, pid, at: datetime) -> None:
    conn.execute(
        text(
            "INSERT INTO participant_events (pid, kind, payload, at, actor, actor_role) "
            "VALUES (:p, 'day_entered', CAST(:payload AS jsonb), :at, 'test', 'system')"
        ),
        {"p": pid, "payload": json.dumps({"schema_version": 1}), "at": at},
    )


def test_backfill_0018(db_engine, migrated_db):
    from alembic import command

    cfg = _alembic_config()
    day = datetime(2026, 11, 10, tzinfo=MSK)
    at_0359 = day.replace(hour=3, minute=59)
    at_0400 = day.replace(hour=4, minute=0)
    at_0401 = day.replace(hour=4, minute=1)
    at_mars = day.replace(hour=5, minute=0)
    at_first = day.replace(hour=10, minute=0)
    at_second = day - timedelta(days=5)  # больший id, но раньше по времени
    same_date = datetime(2026, 11, 10, 0, 0, tzinfo=MSK)
    next_date = datetime(2026, 11, 11, 0, 0, tzinfo=MSK)
    try:
        command.downgrade(cfg, "0017_support_questions")
        pids = {}
        with db_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO tg_user_registry (pid, tg_user_id, created_via, tombstoned_at) "
                    "VALUES (:p, :t, 'mini_app_first_launch', "
                    "CASE WHEN :dead THEN now() END)"
                ),
                [
                    {"p": pid, "t": tg, "dead": dead}
                    for name, tg, dead in (
                        ("0359", 4350, False),
                        ("0400", 4351, False),
                        ("0401", 4352, False),
                        ("mars", 4353, False),
                        ("two", 4354, False),
                        ("tomb", 4355, True),
                        ("no_state", 4356, False),
                        ("no_day", 4357, False),
                    )
                    for pid in [pids.setdefault(name, uuid.uuid4())]
                ],
            )
            for name in ("0359", "0400", "0401", "two", "tomb", "no_day"):
                _state_row(conn, pids[name], "Europe/Moscow")
            _state_row(conn, pids["mars"], "Mars/Base")
            _day_entered(conn, pids["0359"], at_0359)
            _day_entered(conn, pids["0400"], at_0400)
            _day_entered(conn, pids["0401"], at_0401)
            _day_entered(conn, pids["mars"], at_mars)
            _day_entered(conn, pids["two"], at_first)
            _day_entered(conn, pids["two"], at_second)
            _day_entered(conn, pids["tomb"], at_first)
            _day_entered(conn, pids["no_state"], at_first)
        command.upgrade(cfg, "0018_pauses")
        command.upgrade(cfg, "head")

        with db_engine.connect() as conn:
            rows = {
                row.pid: row
                for row in conn.execute(text(f"SELECT {PB} FROM pause_budgets")).all()
            }
        cases = (
            ("0359", at_0359, "Europe/Moscow", same_date),
            ("0400", at_0400, "Europe/Moscow", same_date),
            ("0401", at_0401, "Europe/Moscow", next_date),
            ("mars", at_mars, "Mars/Base", next_date),
            ("two", at_first, "Europe/Moscow", next_date),
        )
        assert set(rows) == {pids[name] for name, *_ in cases}
        for name, at, tz, expected in cases:
            row = rows[pids[name]]
            formula = day_clock.last_midnight(day_clock.active_from(at, tz), tz)
            assert row.cycle_start_at == formula, name
            assert row.cycle_start_at == expected, name
            assert row.days_budget_remaining_annual == 14, name
            assert row.restart_no == 0, name
        for name in ("tomb", "no_state", "no_day"):
            assert pids[name] not in rows, name
    finally:
        command.upgrade(cfg, "head")
        engine = create_engine(migrated_db)
        try:
            with engine.begin() as conn:
                conn.execute(
                    text("TRUNCATE tg_user_registry, participant_state, participant_events CASCADE")
                )
        finally:
            engine.dispose()


# 8. ПОСЛЕДНИМ: downgrade до 0017 — таблиц 0018 нет, права app_bot сняты, 0007 и 0017 целы.
def test_downgrade_0018(migrated_db):
    from alembic import command

    cfg = _alembic_config()
    tables = text(
        "SELECT to_regclass('public.participant_pauses') IS NOT NULL, "
        "to_regclass('public.pause_budgets') IS NOT NULL"
    )
    bot_rights = text(
        "SELECT has_any_column_privilege('app_bot', 'participant_events', 'INSERT'), "
        "has_sequence_privilege('app_bot', 'participant_events_id_seq', 'USAGE'), "
        "has_any_column_privilege('app_bot', 'idempotency_keys', 'INSERT'), "
        "has_any_column_privilege('app_bot', 'idempotency_keys', 'SELECT')"
    )
    projector_events_insert = text(
        "SELECT has_table_privilege('app_projector', 'participant_events', 'INSERT')"
    )
    sq_exists = text("SELECT to_regclass('public.support_questions') IS NOT NULL")
    engine = create_engine(migrated_db)
    try:
        with engine.connect() as conn:
            assert tuple(conn.execute(tables).one()) == (True, True)
            assert tuple(conn.execute(bot_rights).one()) == (True,) * 4
        command.downgrade(cfg, "0017_support_questions")
        with engine.connect() as conn:
            assert tuple(conn.execute(tables).one()) == (False, False)
            assert tuple(conn.execute(bot_rights).one()) == (False,) * 4
            assert conn.execute(projector_events_insert).scalar_one() is True  # право 0007
            assert conn.execute(sq_exists).scalar_one() is True
    finally:
        command.upgrade(cfg, "head")
        engine.dispose()
