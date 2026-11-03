"""db-2: миграция 0012_outbox_api — права app_api на INSERT в outbox.

Статические тесты (1) идут без БД. Тесты с БД — только в CI (соединение CI —
суперпользователь, оно делает SET ROLE). Роли переключает role_engine из tests.test_db_roles.
Отказы — SQLSTATE 42501 (psycopg.errors.InsufficientPrivilege). Стоп-правило карточки:
permission denied на право вне раздела 8 — права не расширять, ошибку отдать ШТАБу.
TRUNCATE outbox тут не делается: conftest outbox не чистит, а RESTART IDENTITY мешает
соседним тестам; своя строка ищется по своему aggregate_id (как в test_notify_ops.py).
Главный смысл задачи — пара INSERT (reflections_log + outbox) в ОДНОЙ транзакции под
app_api: тесты 6. tg_user_id — 3701–3799 (диапазон 0012), строку tg_user_registry для FK
вставляет владелец. Тест downgrade — последним в файле; в finally схема возвращается на head.
"""
import importlib.util
import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from tests.conftest import _alembic_config
from tests.test_db_roles import _assert_denied, role_engine
from tests.test_db_roles_0011 import _registry_pid

API_DIR = Path(__file__).resolve().parents[1]
MIGRATION_0012 = next((API_DIR / "migrations" / "versions").glob("*0012_outbox_api*.py"))

EVENT_TYPE = "reflection_submitted"
STUB_PAYLOAD = {"text_id": "stub.text", "reflection_id": 1}

# Эталон PRIVILEGES миграции 0012: сверка целиком, не по первому слову (ревью #167).
EXPECTED_PRIVILEGES_0012: tuple[tuple[str, str, str], ...] = (
    ("INSERT (aggregate_id, event_type, payload, tx_id)", "TABLE outbox", "app_api"),
    ("USAGE", "SEQUENCE outbox_id_seq", "app_api"),
)

# Контракт api-refl-1, раздел 7, Т7 (API, app_api): без RETURNING.
API_INSERT_OUTBOX = text(
    "INSERT INTO outbox (aggregate_id, event_type, payload, tx_id) "
    "VALUES (:a, 'reflection_submitted', CAST(:payload AS jsonb), pg_current_xact_id())"
)
# Контракт 0011 (db-1): INSERT в reflections_log с RETURNING id.
API_INSERT_REFLECTION = text(
    "INSERT INTO reflections_log (pid, stage_no, module_no, day_no, day_started_at, body) "
    "VALUES (:pid, :s, :m, :d, now(), :body) RETURNING id"
)
# Контракт iter2-api-3 («часы», app_projector): права 0009 задача не трогает.
PROJECTOR_INSERT_OUTBOX = text(
    "INSERT INTO outbox (aggregate_id, event_type, payload, tx_id) "
    "VALUES (:a, :t, CAST(:payload AS jsonb), pg_current_xact_id())"
)

INSERT_OUTBOX_LITERAL = (
    "INSERT INTO outbox (aggregate_id, event_type, payload, tx_id) "
    "VALUES ('x', 'reflection_submitted', '{}'::jsonb, pg_current_xact_id())"
)

API_DENIED_0012: tuple[str, ...] = (
    INSERT_OUTBOX_LITERAL + " RETURNING id",
    "INSERT INTO outbox (aggregate_id, event_type, payload, tx_id, sent_at) "
    "VALUES ('x', 'reflection_submitted', '{}'::jsonb, pg_current_xact_id(), now())",
    "INSERT INTO outbox (id, aggregate_id, event_type, payload, tx_id) "
    "VALUES (1, 'x', 'reflection_submitted', '{}'::jsonb, pg_current_xact_id())",
    "INSERT INTO outbox (aggregate_id, event_type, payload, tx_id, created_at) "
    "VALUES ('x', 'reflection_submitted', '{}'::jsonb, pg_current_xact_id(), now())",
    "SELECT id FROM outbox",
    "SELECT * FROM outbox",
    "UPDATE outbox SET sent_at = now()",
    "UPDATE outbox SET payload = '{}'::jsonb",
    "DELETE FROM outbox",
    "TRUNCATE outbox",
    "SELECT id FROM outbox_dlq",
    "INSERT INTO outbox_dlq (original_id, payload, error) VALUES (1, '{}'::jsonb, 'e')",
)

# (имя, SQL-функция прав, ожидание).
PRIVILEGE_CHECKS_0012: tuple[tuple[str, str, bool], ...] = (
    (
        "api-insert-aggregate-id",
        "has_column_privilege('app_api', 'outbox', 'aggregate_id', 'INSERT')",
        True,
    ),
    (
        "api-insert-event-type",
        "has_column_privilege('app_api', 'outbox', 'event_type', 'INSERT')",
        True,
    ),
    (
        "api-insert-payload",
        "has_column_privilege('app_api', 'outbox', 'payload', 'INSERT')",
        True,
    ),
    (
        "api-insert-tx-id",
        "has_column_privilege('app_api', 'outbox', 'tx_id', 'INSERT')",
        True,
    ),
    (
        "api-insert-id",
        "has_column_privilege('app_api', 'outbox', 'id', 'INSERT')",
        False,
    ),
    (
        "api-insert-created-at",
        "has_column_privilege('app_api', 'outbox', 'created_at', 'INSERT')",
        False,
    ),
    (
        "api-insert-sent-at",
        "has_column_privilege('app_api', 'outbox', 'sent_at', 'INSERT')",
        False,
    ),
    ("api-select", "has_any_column_privilege('app_api', 'outbox', 'SELECT')", False),
    ("api-update", "has_any_column_privilege('app_api', 'outbox', 'UPDATE')", False),
    ("api-delete", "has_table_privilege('app_api', 'outbox', 'DELETE')", False),
    ("api-truncate", "has_table_privilege('app_api', 'outbox', 'TRUNCATE')", False),
    (
        "api-dlq-update",
        "has_table_privilege('app_api', 'outbox_dlq', 'UPDATE')",
        False,
    ),
    (
        "api-dlq-delete",
        "has_table_privilege('app_api', 'outbox_dlq', 'DELETE')",
        False,
    ),
    (
        "api-dlq-truncate",
        "has_table_privilege('app_api', 'outbox_dlq', 'TRUNCATE')",
        False,
    ),
    (
        "api-seq-usage",
        "has_sequence_privilege('app_api', 'outbox_id_seq', 'USAGE')",
        True,
    ),
    (
        "public-seq-usage",
        "has_sequence_privilege('public', 'outbox_id_seq', 'USAGE')",
        False,
    ),
    ("public-insert", "has_table_privilege('public', 'outbox', 'INSERT')", False),
    (
        "public-insert-any-column",
        "has_any_column_privilege('public', 'outbox', 'INSERT')",
        False,
    ),
    (
        "projector-insert-0009",
        "has_any_column_privilege('app_projector', 'outbox', 'INSERT')",
        True,
    ),
    (
        "projector-seq-usage-0009",
        "has_sequence_privilege('app_projector', 'outbox_id_seq', 'USAGE')",
        True,
    ),
)

# До downgrade — true, после — false (права 0012).
API_GRANTED_0012: tuple[str, ...] = (
    "SELECT has_column_privilege('app_api', 'outbox', 'aggregate_id', 'INSERT')",
    "SELECT has_column_privilege('app_api', 'outbox', 'event_type', 'INSERT')",
    "SELECT has_column_privilege('app_api', 'outbox', 'payload', 'INSERT')",
    "SELECT has_column_privilege('app_api', 'outbox', 'tx_id', 'INSERT')",
    "SELECT has_sequence_privilege('app_api', 'outbox_id_seq', 'USAGE')",
)

# true и до, и после downgrade: права 0009 задача не трогает.
PROJECTOR_KEPT_0012: tuple[str, ...] = (
    "SELECT has_any_column_privilege('app_projector', 'outbox', 'INSERT')",
    "SELECT has_sequence_privilege('app_projector', 'outbox_id_seq', 'USAGE')",
)


class _Rollback(Exception):
    """Принудительный откат транзакции в тесте (наружу не выходит)."""


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_0012_outbox_api", MIGRATION_0012)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _migration_code(module) -> str:
    """Текст миграции без docstring модуля (в нём запреты названы словами)."""
    source = MIGRATION_0012.read_text(encoding="utf-8")
    assert module.__doc__ and module.__doc__ in source
    return source.replace(module.__doc__, "", 1)


def _count_rows(db_engine, pid) -> tuple[int, int]:
    """Сколько строк reflections_log и outbox принадлежит этому pid."""
    with db_engine.connect() as conn:
        reflections = conn.execute(
            text("SELECT count(*) FROM reflections_log WHERE pid = :p"), {"p": pid}
        ).scalar_one()
        outbox = conn.execute(
            text("SELECT count(*) FROM outbox WHERE aggregate_id = :a"), {"a": str(pid)}
        ).scalar_one()
    return reflections, outbox


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


# 1. Статика: ревизии, состав PRIVILEGES, запрещённые конструкции.
def test_revision_0012():
    module = _load_migration()
    assert module.revision == "0012_outbox_api"
    assert module.down_revision == "0011_reflections_log"


def test_privileges_static_0012():
    module = _load_migration()
    assert tuple(module.PRIVILEGES) == EXPECTED_PRIVILEGES_0012
    code = _migration_code(module)
    assert "ALTER DEFAULT PRIVILEGES" not in code.upper()
    # Слово в верхнем регистре: в коде есть имена и импорты со словом public строчными.
    assert "PUBLIC" not in code


# 2. Контракт раздела 7: INSERT под app_api без RETURNING; строку читает владелец.
def test_api_inserts_outbox(db_engine, api_engine):
    aggregate_id = str(uuid.uuid4())
    with api_engine.begin() as conn:
        conn.execute(
            API_INSERT_OUTBOX,
            {"a": aggregate_id, "payload": json.dumps(STUB_PAYLOAD)},
        )
    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT event_type, payload, sent_at, tx_id "
                "FROM outbox WHERE aggregate_id = :a"
            ),
            {"a": aggregate_id},
        ).one()
    assert row.event_type == EVENT_TYPE
    assert row.payload == STUB_PAYLOAD
    assert row.sent_at is None
    assert row.tx_id is not None


# 3. Права 0009 целы: app_projector по-прежнему пишет outbox своим контрактом.
def test_projector_still_inserts_outbox(db_engine, projector_engine):
    aggregate_id = str(uuid.uuid4())
    with projector_engine.begin() as conn:
        conn.execute(
            PROJECTOR_INSERT_OUTBOX,
            {"a": aggregate_id, "t": "stub.push", "payload": json.dumps(STUB_PAYLOAD)},
        )
    with db_engine.connect() as conn:
        event_type = conn.execute(
            text("SELECT event_type FROM outbox WHERE aggregate_id = :a"),
            {"a": aggregate_id},
        ).scalar_one()
    assert event_type == "stub.push"


# 4. Запреты app_api (каждый — своё соединение).
@pytest.mark.parametrize("sql", API_DENIED_0012)
def test_app_api_denied_0012(api_engine, sql):
    _assert_denied(api_engine, sql)


# 5. Права по колонкам, таблице и последовательности.
@pytest.mark.parametrize(
    ("name", "sql", "allowed"),
    PRIVILEGE_CHECKS_0012,
    ids=[c[0] for c in PRIVILEGE_CHECKS_0012],
)
def test_privileges_0012(db_engine, name, sql, allowed):
    with db_engine.connect() as conn:
        granted = conn.execute(text(f"SELECT {sql}")).scalar_one()
    assert granted is allowed, name


# 6. Главное: reflections_log и outbox одной транзакцией под app_api (api-refl-1, Т7).
def test_reflection_and_outbox_one_transaction_commit(db_engine, api_engine):
    pid = _registry_pid(db_engine, 3701)
    with api_engine.begin() as conn:
        reflection_id = conn.execute(
            API_INSERT_REFLECTION,
            {"pid": pid, "s": 1, "m": 2, "d": 6, "body": "заглушка рефлексии"},
        ).scalar_one()
        conn.execute(
            API_INSERT_OUTBOX,
            {
                "a": str(pid),
                "payload": json.dumps({**STUB_PAYLOAD, "reflection_id": reflection_id}),
            },
        )
    assert reflection_id > 0
    with db_engine.connect() as conn:
        body = conn.execute(
            text("SELECT body FROM reflections_log WHERE id = :i"), {"i": reflection_id}
        ).scalar_one()
        row = conn.execute(
            text(
                "SELECT event_type, payload, sent_at, tx_id "
                "FROM outbox WHERE aggregate_id = :a"
            ),
            {"a": str(pid)},
        ).one()
    assert body == "заглушка рефлексии"
    assert row.event_type == EVENT_TYPE
    assert row.payload["reflection_id"] == reflection_id
    assert row.sent_at is None
    assert row.tx_id is not None


def test_reflection_and_outbox_one_transaction_rollback(db_engine, api_engine):
    pid = _registry_pid(db_engine, 3702)
    with pytest.raises(_Rollback):
        with api_engine.begin() as conn:
            reflection_id = conn.execute(
                API_INSERT_REFLECTION,
                {"pid": pid, "s": 1, "m": 2, "d": 6, "body": "откат рефлексии"},
            ).scalar_one()
            conn.execute(
                API_INSERT_OUTBOX,
                {
                    "a": str(pid),
                    "payload": json.dumps({**STUB_PAYLOAD, "reflection_id": reflection_id}),
                },
            )
            raise _Rollback
    assert _count_rows(db_engine, pid) == (0, 0)


# 7. ПОСЛЕДНИМ: downgrade 0012 снимает права app_api; права 0009 остаются.
def test_downgrade_0012(migrated_db):
    from alembic import command

    cfg = _alembic_config()
    engine = create_engine(migrated_db)
    try:
        with engine.connect() as conn:
            for sql in API_GRANTED_0012 + PROJECTOR_KEPT_0012:
                assert conn.execute(text(sql)).scalar_one() is True, sql
        command.downgrade(cfg, "0011_reflections_log")
        with engine.connect() as conn:
            for sql in API_GRANTED_0012:
                assert conn.execute(text(sql)).scalar_one() is False, sql
            for sql in PROJECTOR_KEPT_0012:
                assert conn.execute(text(sql)).scalar_one() is True, sql
    finally:
        command.upgrade(cfg, "head")
        engine.dispose()
