"""db-access-1: миграция 0010_access_grants — таблица, права app_bot / app_api, backfill.

Тесты с БД — только CI (соединение CI — суперпользователь, оно делает SET ROLE).
Роль переключается так же, как в test_db_roles_0009 (_bot_role_engine, role_engine).
Отказы — SQLSTATE 42501 (psycopg.errors.InsufficientPrivilege). db_engine (conftest)
чистит access_grants и tg_user_registry. tg_user_id — 3501–3599.
Тест гонки: два соединения под app_bot, lock_timeout 10 s, join потока — 10 с.
Тест backfill (downgrade до 0009) — последним в файле; в finally схема возвращается на head.
"""
import threading
import time
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from tests.conftest import _alembic_config
from tests.test_db_roles import _assert_denied, role_engine
from tests.test_db_roles_0009 import _bot_role_engine

RACE_TG = 3550
RACE_MSG = 100

# Контракт bot-access-1 (бот, app_bot), без RETURNING.
INSERT_REQUEST = text(
    "INSERT INTO access_grants (tg_user_id, status, admin_message_id, requested_at, "
    "deny_count, locked_until, created_via) "
    "VALUES (:id, 'pending', :mid, now(), 0, NULL, 'bot_promo')"
)
UPSERT_REQUEST = text(
    "INSERT INTO access_grants (tg_user_id, status, admin_message_id, requested_at, "
    "deny_count, locked_until, created_via) "
    "VALUES (:id, 'pending', :mid, now(), 0, NULL, 'bot_promo') "
    "ON CONFLICT (tg_user_id) DO UPDATE SET status = EXCLUDED.status, "
    "admin_message_id = EXCLUDED.admin_message_id, requested_at = EXCLUDED.requested_at, "
    "deny_count = EXCLUDED.deny_count, locked_until = EXCLUDED.locked_until, "
    "updated_at = now()"
)
LOCK_ROW = text(
    "SELECT status, deny_count, locked_until, admin_message_id FROM access_grants "
    "WHERE tg_user_id = :id FOR UPDATE"
)
GRANT_DECISION = text(
    "UPDATE access_grants SET status = 'granted', decided_at = now(), decided_by = :admin, "
    "updated_at = now() WHERE tg_user_id = :id AND status = 'pending'"
)
DENY_IF_PENDING = text(
    "UPDATE access_grants SET deny_count = deny_count + 1, status = 'denied', "
    "updated_at = now() "
    "WHERE tg_user_id = :id AND status = 'pending' AND admin_message_id = :mid"
)
API_READ = text("SELECT tg_user_id, status FROM access_grants WHERE tg_user_id = :id")

OWNER_INSERT = text(
    "INSERT INTO access_grants (tg_user_id, status, admin_message_id, deny_count, created_via) "
    "VALUES (:id, :status, :mid, :deny, 'bot_promo')"
)

BOT_DENIED_0010: tuple[str, ...] = (
    "DELETE FROM access_grants",
    "TRUNCATE access_grants",
    "SELECT created_at FROM access_grants",
    "SELECT created_via FROM access_grants",
    "UPDATE access_grants SET created_via = 'bot_promo'",
    "UPDATE access_grants SET tg_user_id = 1",
    "INSERT INTO access_grants (tg_user_id, status, created_via, decided_at) "
    "VALUES (3599, 'granted', 'bot_promo', now())",
)

API_DENIED_0010: tuple[str, ...] = (
    "SELECT deny_count FROM access_grants",
    "SELECT * FROM access_grants",
    "INSERT INTO access_grants (tg_user_id, status, created_via) "
    "VALUES (3598, 'granted', 'bot_promo')",
    "UPDATE access_grants SET status = 'granted'",
    "DELETE FROM access_grants",
)

PROJECTOR_DENIED_0010: tuple[str, ...] = (
    "SELECT tg_user_id FROM access_grants",
    "SELECT status FROM access_grants",
)

# (роль, колонка, право, ожидание) на access_grants.
COLUMN_PRIVILEGES_0010: tuple[tuple[str, str, str, bool], ...] = (
    ("app_bot", "decided_by", "SELECT", True),
    ("app_bot", "created_at", "SELECT", False),
    ("app_bot", "created_via", "INSERT", True),
    ("app_bot", "decided_at", "INSERT", False),
    ("app_bot", "updated_at", "UPDATE", True),
    ("app_bot", "created_via", "UPDATE", False),
    ("app_api", "tg_user_id", "SELECT", True),
    ("app_api", "status", "SELECT", True),
    ("app_api", "deny_count", "SELECT", False),
    ("app_api", "status", "UPDATE", False),
    ("app_projector", "status", "SELECT", False),
)

# Табличных DELETE / TRUNCATE нет ни у кого.
TABLE_PRIVILEGES_DENIED_0010: tuple[tuple[str, str], ...] = tuple(
    (role, priv)
    for role in ("app_bot", "app_api", "app_projector")
    for priv in ("DELETE", "TRUNCATE")
)


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


def _owner_insert(db_engine, tg_id: int, status: str, mid: int | None, deny: int = 0) -> None:
    with db_engine.begin() as conn:
        conn.execute(OWNER_INSERT, {"id": tg_id, "status": status, "mid": mid, "deny": deny})


def _row(db_engine, tg_id: int):
    with db_engine.connect() as conn:
        return conn.execute(
            text("SELECT * FROM access_grants WHERE tg_user_id = :id"), {"id": tg_id}
        ).one()


# 1. app_bot: INSERT заявки, FOR UPDATE, решение UPDATE.
def test_bot_insert_lock_update(db_engine, bot_engine):
    with bot_engine.begin() as conn:
        assert conn.execute(INSERT_REQUEST, {"id": 3501, "mid": 501}).rowcount == 1
    with bot_engine.begin() as conn:
        locked = conn.execute(LOCK_ROW, {"id": 3501}).one()
        assert locked.status == "pending" and locked.admin_message_id == 501
        assert conn.execute(GRANT_DECISION, {"id": 3501, "admin": 7}).rowcount == 1
    row = _row(db_engine, 3501)
    assert row.status == "granted"
    assert row.decided_by == 7
    assert row.created_via == "bot_promo"
    assert row.decided_at is not None


# 2. app_bot: INSERT … ON CONFLICT (tg_user_id) DO UPDATE — новая заявка после отказа.
def test_bot_upsert_request(db_engine, bot_engine):
    _owner_insert(db_engine, 3502, "denied", 502, deny=2)
    with bot_engine.begin() as conn:
        assert conn.execute(UPSERT_REQUEST, {"id": 3502, "mid": 503}).rowcount == 1
    row = _row(db_engine, 3502)
    assert row.status == "pending"
    assert row.admin_message_id == 503
    assert row.requested_at is not None
    assert row.updated_at > row.created_at
    with bot_engine.begin() as conn:  # без конфликта — обычная вставка
        assert conn.execute(UPSERT_REQUEST, {"id": 3503, "mid": 504}).rowcount == 1
    assert _row(db_engine, 3503).status == "pending"


# 3. app_api читает только (tg_user_id, status).
def test_api_reads_status(db_engine, api_engine):
    _owner_insert(db_engine, 3504, "granted", None)
    with api_engine.connect() as conn:
        row = conn.execute(API_READ, {"id": 3504}).one()
    assert tuple(row) == (3504, "granted")


# 4–6. Запреты.
@pytest.mark.parametrize("sql", BOT_DENIED_0010)
def test_app_bot_denied_0010(bot_engine, sql):
    _assert_denied(bot_engine, sql)


@pytest.mark.parametrize("sql", API_DENIED_0010)
def test_app_api_denied_0010(api_engine, sql):
    _assert_denied(api_engine, sql)


@pytest.mark.parametrize("sql", PROJECTOR_DENIED_0010)
def test_app_projector_denied_0010(projector_engine, sql):
    _assert_denied(projector_engine, sql)


# 7. Права по колонкам.
@pytest.mark.parametrize(
    ("role", "column", "privilege", "allowed"),
    COLUMN_PRIVILEGES_0010,
    ids=[f"{c[0]}-{c[1]}-{c[2]}" for c in COLUMN_PRIVILEGES_0010],
)
def test_column_privileges_0010(db_engine, role, column, privilege, allowed):
    with db_engine.connect() as conn:
        granted = conn.execute(
            text("SELECT has_column_privilege(:r, 'access_grants', :c, :p)"),
            {"r": role, "c": column, "p": privilege},
        ).scalar_one()
    assert granted is allowed, (role, column, privilege)


# 8. DELETE и TRUNCATE не выданы никому.
@pytest.mark.parametrize(("role", "privilege"), TABLE_PRIVILEGES_DENIED_0010)
def test_no_delete_truncate_0010(db_engine, role, privilege):
    with db_engine.connect() as conn:
        granted = conn.execute(
            text("SELECT has_table_privilege(:r, 'access_grants', :p)"),
            {"r": role, "p": privilege},
        ).scalar_one()
    assert granted is False, (role, privilege)


# 9. CHECK и частичный UNIQUE.
@pytest.mark.parametrize(
    ("status", "mid", "deny", "constraint"),
    [
        ("x", 601, 0, "ck_access_grants_status"),
        ("granted", None, -1, "ck_access_grants_deny_count_nonneg"),
        ("pending", None, 0, "ck_access_grants_pending_msg"),
    ],
    ids=["status-x", "deny-negative", "pending-without-msg"],
)
def test_check_constraints_0010(db_engine, status, mid, deny, constraint):
    from psycopg import errors as pg_errors

    with pytest.raises(IntegrityError) as caught:
        _owner_insert(db_engine, 3510, status, mid, deny=deny)
    assert isinstance(caught.value.orig, pg_errors.CheckViolation)
    assert caught.value.orig.diag.constraint_name == constraint


def test_unique_admin_message_id_0010(db_engine):
    from psycopg import errors as pg_errors

    _owner_insert(db_engine, 3511, "pending", 700)
    _owner_insert(db_engine, 3512, "granted", None)
    _owner_insert(db_engine, 3513, "granted", None)  # NULL — не конфликт
    with pytest.raises(IntegrityError) as caught:
        _owner_insert(db_engine, 3514, "denied", 700)
    assert isinstance(caught.value.orig, pg_errors.UniqueViolation)
    assert caught.value.orig.diag.constraint_name == "uq_access_grants_admin_message_id"


# 10. ГОНКА: два одновременных решения по одной заявке — проходит ровно одно.
def test_concurrent_decisions_one_wins(db_engine, bot_engine):
    _owner_insert(db_engine, RACE_TG, "pending", RACE_MSG)
    params = {"id": RACE_TG, "mid": RACE_MSG}
    result: dict[str, object] = {}
    started = threading.Event()

    def second_decision() -> None:
        try:
            with bot_engine.connect() as conn2:
                conn2.execute(text("SET lock_timeout = '10s'"))
                conn2.commit()
                with conn2.begin():
                    result["pid"] = conn2.execute(text("SELECT pg_backend_pid()")).scalar_one()
                    started.set()
                    conn2.execute(LOCK_ROW, {"id": RACE_TG}).all()  # ждёт соединение 1
                    result["rowcount"] = conn2.execute(DENY_IF_PENDING, params).rowcount
        except Exception as exc:  # noqa: BLE001 — ошибка потока проверяется ниже
            result["error"] = exc
        finally:
            started.set()

    worker = threading.Thread(target=second_decision, daemon=True)
    with bot_engine.connect() as conn1:
        conn1.execute(text("SET lock_timeout = '10s'"))
        conn1.commit()
        with conn1.begin():
            assert conn1.execute(LOCK_ROW, {"id": RACE_TG}).one().status == "pending"

            worker.start()
            assert started.wait(10)
            time.sleep(0.5)
            assert worker.is_alive(), result  # поток ждёт блокировку строки
            assert "error" not in result, result
            with db_engine.connect() as watcher:  # и ждёт именно замок (pg_stat_activity)
                wait_type = watcher.execute(
                    text("SELECT wait_event_type FROM pg_stat_activity WHERE pid = :p"),
                    {"p": result["pid"]},
                ).scalar_one()
            assert wait_type == "Lock"

            assert conn1.execute(DENY_IF_PENDING, params).rowcount == 1
        # COMMIT соединения 1 — выход из begin()

    worker.join(timeout=10)
    assert not worker.is_alive(), "второе решение не дождалось блокировки за 10 с"
    assert "error" not in result, result
    assert result["rowcount"] == 0

    row = _row(db_engine, RACE_TG)
    assert row.deny_count == 1
    assert row.status == "denied"


# 11. ПОСЛЕДНИМ: backfill 0010 — granted только активным строкам tg_user_registry.
def test_backfill_0010(db_engine, migrated_db):
    from alembic import command

    cfg = _alembic_config()
    active = (3521, 3522)
    tombstoned = 3523
    try:
        command.downgrade(cfg, "0009_app_bot")
        with db_engine.begin() as conn:
            for tg_id in active:
                conn.execute(
                    text(
                        "INSERT INTO tg_user_registry (pid, tg_user_id, created_via) "
                        "VALUES (:p, :t, 'mini_app_first_launch')"
                    ),
                    {"p": uuid.uuid4(), "t": tg_id},
                )
            conn.execute(
                text(
                    "INSERT INTO tg_user_registry (pid, tg_user_id, created_via, tombstoned_at) "
                    "VALUES (:p, :t, 'mini_app_first_launch', now())"
                ),
                {"p": uuid.uuid4(), "t": tombstoned},
            )
        command.upgrade(cfg, "head")
        with db_engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT tg_user_id, status, created_via, decided_at, deny_count "
                    "FROM access_grants ORDER BY tg_user_id"
                )
            ).all()
        assert [r.tg_user_id for r in rows] == list(active)
        assert all(r.status == "granted" for r in rows)
        assert all(r.created_via == "backfill_0010" for r in rows)
        assert all(r.decided_at is not None and r.deny_count == 0 for r in rows)
    finally:
        command.upgrade(cfg, "head")
        engine = create_engine(migrated_db)
        try:
            with engine.begin() as conn:
                conn.execute(text("TRUNCATE access_grants, tg_user_registry CASCADE"))
        finally:
            engine.dispose()
