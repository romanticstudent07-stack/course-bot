"""db-pause-0021: миграция 0021_bot_pauses_select — SELECT строк participant_pauses и INSERT (ttl)
idempotency_keys для app_bot.

Статические тесты (1) идут без БД. Тесты с БД — только в CI (соединение CI — суперпользователь,
оно делает SET ROLE через _bot_role_engine). Отказы — SQLSTATE 42501 (_assert_denied).
Строки вставляет владелец. tg_user_id — 4401–4499. SQL бота — bot-pause-1 §5 (стиль :param).
Тест downgrade — последним в файле; в finally схема возвращается на head.
"""
import importlib.util
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from tests.conftest import _alembic_config
from tests.test_db_roles import _assert_denied
from tests.test_db_roles_0009 import _bot_role_engine

API_DIR = Path(__file__).resolve().parents[1]
MIGRATION_0021 = next(
    (API_DIR / "migrations" / "versions").glob("*0021_bot_pauses_select*.py")
)

# Контракт bot-pause-1 §5 (бот, app_bot), без RETURNING.
WATCH = text(
    "SELECT p.id, p.pid, p.status, p.start_at, p.planned_end_at, "
    "r.tg_user_id, r.short_no, s.tz, now() AS db_now, "
    "(p.status = 'requested' AND now() < p.start_at) AS open "
    "FROM participant_pauses p "
    "JOIN tg_user_registry r ON r.pid = p.pid "
    "LEFT JOIN participant_state s ON s.pid = p.pid "
    "WHERE p.kind = 'user' AND r.tombstoned_at IS NULL "
    "AND p.created_at > now() - interval '10 days' "
    "ORDER BY p.id"
)
DECIDE_ROW = text("SELECT pid FROM participant_pauses WHERE id = :id AND kind = 'user'")
DECIDE_CHECK = text(
    "SELECT status = 'requested' AND now() < start_at FROM participant_pauses WHERE id = :id"
)
KEY_TTL = text(
    "INSERT INTO idempotency_keys (key, kind, result_ref, ttl) "
    "VALUES (:key, :kind, :ref, interval '30 days') ON CONFLICT (key) DO NOTHING"
)

# Владелец: start_at / planned_end_at — смещения от now() в часах.
OWNER_PAUSE = text(
    "INSERT INTO participant_pauses (pid, kind, status, start_at, planned_end_at, client_op_id) "
    "VALUES (:pid, :kind, :status, now() + make_interval(hours => :s), "
    "now() + make_interval(hours => :e), :op) RETURNING id"
)

EXPECTED_PRIVILEGES_0021: tuple[tuple[str, str, str], ...] = (
    (
        "SELECT (id, pid, kind, status, start_at, planned_end_at, created_at)",
        "TABLE participant_pauses",
        "app_bot",
    ),
    ("INSERT (ttl)", "TABLE idempotency_keys", "app_bot"),
)

SELECT_ALLOWED = ("id", "pid", "kind", "status", "start_at", "planned_end_at", "created_at")
SELECT_DENIED = ("client_op_id", "ended_at", "stage_no", "restart_no")


def _col(table: str, column: str, verb: str) -> str:
    return f"has_column_privilege('app_bot', '{table}', '{column}', '{verb}')"


def _any(table: str, verb: str) -> str:
    return f"has_any_column_privilege('app_bot', '{table}', '{verb}')"


def _table(table: str, verb: str) -> str:
    return f"has_table_privilege('app_bot', '{table}', '{verb}')"


# (имя, SQL-функция прав, ожидание).
PRIVILEGE_CHECKS_0021: tuple[tuple[str, str, bool], ...] = (
    *(
        (f"bot-pauses-select-{c}", _col("participant_pauses", c, "SELECT"), True)
        for c in SELECT_ALLOWED
    ),
    ("bot-keys-insert-ttl", _col("idempotency_keys", "ttl", "INSERT"), True),
    *(
        (f"bot-pauses-select-{c}", _col("participant_pauses", c, "SELECT"), False)
        for c in SELECT_DENIED
    ),
    *(
        (f"bot-pauses-{v.lower()}", _any("participant_pauses", v), False)
        for v in ("INSERT", "UPDATE")
    ),
    *(
        (f"bot-pauses-{v.lower()}", _table("participant_pauses", v), False)
        for v in ("DELETE", "TRUNCATE")
    ),
    (
        "bot-pauses-seq",
        "has_sequence_privilege('app_bot', 'participant_pauses_id_seq', 'USAGE')",
        False,
    ),
    *(
        (f"bot-budgets-{v.lower()}", _any("pause_budgets", v), False)
        for v in ("SELECT", "INSERT", "UPDATE")
    ),
    *(
        (f"bot-budgets-{v.lower()}", _table("pause_budgets", v), False)
        for v in ("DELETE", "TRUNCATE")
    ),
    ("bot-keys-update", _any("idempotency_keys", "UPDATE"), False),
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "mig_0021_bot_pauses_select", MIGRATION_0021
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _migration_code(module) -> str:
    """Текст миграции без docstring модуля (в нём запреты названы словами)."""
    source = MIGRATION_0021.read_text(encoding="utf-8")
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


def _owner_pause(db_engine, pid, *, kind: str, status: str, s: int, e: int, op: str) -> int:
    with db_engine.begin() as conn:
        return conn.execute(
            OWNER_PAUSE,
            {"pid": pid, "kind": kind, "status": status, "s": s, "e": e, "op": op},
        ).scalar_one()


# 1. Статика: revision, down_revision, ROLES, PRIVILEGES, запреты.
def test_revision_0021():
    module = _load_migration()
    assert module.revision == "0021_bot_pauses_select"
    assert module.down_revision == "0020_bot_events_select"


def test_privileges_static_0021():
    module = _load_migration()
    assert module.ROLES == ("app_bot",)
    assert module.PRIVILEGES == EXPECTED_PRIVILEGES_0021
    code = _migration_code(module)
    assert "ALTER DEFAULT PRIVILEGES" not in code.upper()
    # Слово в верхнем регистре: строчное public допустимо в именах и импортах.
    assert "PUBLIC" not in code
    # GRANT — только в цикле upgrade.
    assert code.count("GRANT ") == 1


# 2. Права: выданное True, лишнее False.
@pytest.mark.parametrize(
    ("name", "sql", "allowed"),
    PRIVILEGE_CHECKS_0021,
    ids=[c[0] for c in PRIVILEGE_CHECKS_0021],
)
def test_privileges_0021(db_engine, name, sql, allowed):
    with db_engine.connect() as conn:
        granted = conn.execute(text(f"SELECT {sql}")).scalar_one()
    assert granted is allowed, name


# 3. Контракт bot-pause-1 §5 под app_bot.
def test_bot_watch_contract_0021(db_engine, bot_engine):
    pid = _registry_pid(db_engine, 4401)
    pause_id = _owner_pause(
        db_engine, pid, kind="user", status="requested", s=24, e=48, op="op-1"
    )
    _owner_pause(db_engine, pid, kind="author", status="active", s=-1, e=23, op="op-a")
    with bot_engine.connect() as conn:
        rows = conn.execute(WATCH).all()
        assert conn.execute(DECIDE_ROW, {"id": pause_id}).scalar_one() == pid
        assert conn.execute(DECIDE_CHECK, {"id": pause_id}).scalar_one() is True
    assert [row.id for row in rows] == [pause_id]
    row = rows[0]
    assert (row.pid, row.status, row.tg_user_id) == (pid, "requested", 4401)
    assert row.short_no is not None
    assert row.start_at < row.planned_end_at
    assert row.db_now is not None
    assert row.open is True


def test_bot_decide_check_started_0021(db_engine, bot_engine):
    pid = _registry_pid(db_engine, 4402)
    pause_id = _owner_pause(
        db_engine, pid, kind="user", status="requested", s=-1, e=23, op="op-1"
    )
    with bot_engine.connect() as conn:
        assert conn.execute(DECIDE_CHECK, {"id": pause_id}).scalar_one() is False


def test_bot_key_ttl_contract_0021(db_engine, bot_engine):
    pid = _registry_pid(db_engine, 4403)
    key = f"pause_decide:{pid}:1"
    params = {"key": key, "kind": "pause_decide", "ref": "approved"}
    with bot_engine.begin() as conn:
        assert conn.execute(KEY_TTL, params).rowcount == 1
    with bot_engine.begin() as conn:
        assert conn.execute(KEY_TTL, params).rowcount == 0
    with db_engine.connect() as conn:
        ttl = conn.execute(
            text("SELECT ttl = interval '30 days' FROM idempotency_keys WHERE key = :k"),
            {"k": key},
        ).scalar_one()
        ttl_value = conn.execute(
            text("SELECT ttl FROM idempotency_keys WHERE key = :k"), {"k": key}
        ).scalar_one()
    assert ttl is True
    assert ttl_value == timedelta(days=30)


# 4. Отказы: client_op_id и pause_budgets app_bot не читает.
def test_bot_select_client_op_id_denied_0021(bot_engine):
    _assert_denied(bot_engine, "SELECT client_op_id FROM participant_pauses")


def test_bot_select_budgets_denied_0021(bot_engine):
    _assert_denied(bot_engine, "SELECT pid FROM pause_budgets")


# 5. ПОСЛЕДНИМ: downgrade до 0020 — права 0021 сняты, права 0018 и 0020 целы.
def test_downgrade_0021(migrated_db):
    from alembic import command

    cfg = _alembic_config()
    pauses_status = text(f"SELECT {_col('participant_pauses', 'status', 'SELECT')}")
    keys_ttl = text(f"SELECT {_col('idempotency_keys', 'ttl', 'INSERT')}")
    events_id = text(f"SELECT {_col('participant_events', 'id', 'SELECT')}")
    keys_key = text(f"SELECT {_col('idempotency_keys', 'key', 'INSERT')}")
    engine = create_engine(migrated_db)
    try:
        with engine.connect() as conn:
            assert conn.execute(pauses_status).scalar_one() is True
            assert conn.execute(keys_ttl).scalar_one() is True
        command.downgrade(cfg, "0020_bot_events_select")
        with engine.connect() as conn:
            assert conn.execute(pauses_status).scalar_one() is False
            assert conn.execute(keys_ttl).scalar_one() is False
            assert conn.execute(events_id).scalar_one() is True  # право 0020 цело
            assert conn.execute(keys_key).scalar_one() is True  # право 0018 цело
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            assert conn.execute(pauses_status).scalar_one() is True
    finally:
        command.upgrade(cfg, "head")
        engine.dispose()
