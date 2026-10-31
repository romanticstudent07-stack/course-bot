"""iter2-db-3: миграция 0009_app_bot — роль app_bot и права доставки из outbox.

Тесты с БД — только CI (соединение CI — суперпользователь, оно делает SET ROLE).
Отказы — SQLSTATE 42501 (psycopg.errors.InsufficientPrivilege). Стоп-правило карточки:
permission denied на право вне раздела 8 — права не расширять, ошибку отдать ШТАБу.
role_engine из tests.test_db_roles принимает только APP_ROLES (app_api, app_projector),
поэтому для app_bot — своя функция _bot_role_engine (дополнение ШТАБа Д1).
clean_outbox чистит outbox и outbox_dlq (conftest их не чистит). Строку outbox вставляет
только app_projector, никогда app_bot. tg_user_id — 3401–3499. Время — только «>».
Тест downgrade — последним в файле; в finally схема возвращается на head.
"""
import json
import uuid

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import DataError

from tests.conftest import _alembic_config
from tests.test_db_roles import _assert_denied, _first_launch, role_engine

EVENT_TYPE = "stub.push"
STUB_PAYLOAD = {"text_id": "stub.text"}

# Контракт iter2-api-3 («часы», app_projector): без RETURNING.
INSERT_OUTBOX = text(
    "INSERT INTO outbox (aggregate_id, event_type, payload, tx_id) "
    "VALUES (:a, :t, CAST(:payload AS jsonb), pg_current_xact_id())"
)
# Контракт iter2-send-1 (бот, app_bot).
CLAIM_BATCH = text(
    "SELECT id, aggregate_id, event_type, payload FROM outbox WHERE sent_at IS NULL "
    "ORDER BY created_at LIMIT :n FOR UPDATE SKIP LOCKED"
)
MARK_SENT = text("UPDATE outbox SET sent_at = now() WHERE id = :id AND sent_at IS NULL")
INSERT_DLQ = text(
    "INSERT INTO outbox_dlq (original_id, payload, error) "
    "VALUES (:id, CAST(:payload AS jsonb), :e)"
)
SELECT_RECIPIENT = text(
    "SELECT tg_user_id FROM tg_user_registry "
    "WHERE pid = CAST(:p AS uuid) AND tombstoned_at IS NULL"
)

INSERT_OUTBOX_LITERAL = (
    "INSERT INTO outbox (aggregate_id, event_type, payload, tx_id) "
    "VALUES ('x', 't', '{}'::jsonb, pg_current_xact_id())"
)
INSERT_DLQ_LITERAL = (
    "INSERT INTO outbox_dlq (original_id, payload, error) VALUES (1, '{}'::jsonb, 'e')"
)

BOT_DENIED_0009: tuple[str, ...] = (
    "SELECT * FROM outbox",
    "SELECT tx_id FROM outbox",
    "UPDATE outbox SET payload = '{}'::jsonb",
    INSERT_OUTBOX_LITERAL,
    "DELETE FROM outbox",
    "TRUNCATE outbox",
    "SELECT * FROM outbox_dlq",
    "UPDATE outbox_dlq SET replayed_at = now()",
    "DELETE FROM outbox_dlq",
    INSERT_DLQ_LITERAL + " RETURNING id",
    "SELECT * FROM tg_user_registry",
    "SELECT pid FROM participant_state",
    "SELECT id FROM participant_events",
    "DELETE FROM text_registry",
)

PROJECTOR_DENIED_0009: tuple[str, ...] = (
    INSERT_OUTBOX_LITERAL + " RETURNING id",
    "SELECT id FROM outbox",
    "UPDATE outbox SET sent_at = now()",
    "DELETE FROM outbox",
    "INSERT INTO outbox (aggregate_id, event_type, payload, tx_id, sent_at) "
    "VALUES ('x', 't', '{}'::jsonb, pg_current_xact_id(), now())",
    INSERT_DLQ_LITERAL,
)

API_DENIED_0009: tuple[str, ...] = (
    "SELECT id FROM outbox",
    INSERT_OUTBOX_LITERAL,
    "SELECT id FROM outbox_dlq",
)

# (роль, таблица, колонка, право, ожидание)
COLUMN_PRIVILEGES_0009: tuple[tuple[str, str, str, str, bool], ...] = (
    ("app_bot", "outbox", "sent_at", "UPDATE", True),
    ("app_bot", "outbox", "payload", "UPDATE", False),
    ("app_bot", "outbox", "tx_id", "SELECT", False),
    ("app_bot", "tg_user_registry", "tg_user_id", "SELECT", True),
    ("app_bot", "outbox_dlq", "replayed_by", "INSERT", False),
    ("app_projector", "outbox", "tx_id", "INSERT", True),
    ("app_projector", "outbox", "sent_at", "INSERT", False),
)

# До downgrade — true, после — false.
GRANTED_0009: tuple[str, ...] = (
    "SELECT has_any_column_privilege('app_bot', 'outbox', 'SELECT')",
    "SELECT has_any_column_privilege('app_bot', 'outbox_dlq', 'INSERT')",
    "SELECT has_any_column_privilege('app_bot', 'tg_user_registry', 'SELECT')",
    "SELECT has_any_column_privilege('app_projector', 'outbox', 'INSERT')",
    "SELECT has_table_privilege('app_bot', 'text_registry', 'SELECT')",
    "SELECT has_sequence_privilege('app_bot', 'outbox_dlq_id_seq', 'USAGE')",
    "SELECT has_sequence_privilege('app_projector', 'outbox_id_seq', 'USAGE')",
)

# true и до, и после downgrade: роль остаётся, права 0008 и 0007 целы.
KEPT_AFTER_0009: tuple[str, ...] = (
    "SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'app_bot')",
    "SELECT has_column_privilege('app_api', 'day_marks', 'value', 'UPDATE')",
    "SELECT has_table_privilege('app_api', 'idempotency_keys', 'INSERT')",
)


def _bot_role_engine(dsn: str):
    """Как tests.test_db_roles.role_engine, но для app_bot (там assert role in APP_ROLES)."""
    engine = create_engine(dsn)

    @event.listens_for(engine, "connect")
    def _set_role(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        try:
            cursor.execute("SET ROLE app_bot")
        finally:
            cursor.close()
        dbapi_conn.commit()

    return engine


@pytest.fixture
def bot_engine(migrated_db):
    engine = _bot_role_engine(migrated_db)
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
def api_engine(migrated_db):
    engine = role_engine(migrated_db, "app_api")
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def clean_outbox(db_engine):
    """Пустые outbox и outbox_dlq; вернуть db_engine (суперпользователь — для проверок)."""
    with db_engine.begin() as conn:
        conn.execute(text("TRUNCATE outbox, outbox_dlq RESTART IDENTITY"))
    return db_engine


def _projector_insert(projector_engine, db_engine) -> tuple[int, str]:
    """Строка outbox от app_projector (своя транзакция); id узнаём под db_engine."""
    aggregate_id = str(uuid.uuid4())
    with projector_engine.begin() as conn:
        conn.execute(
            INSERT_OUTBOX,
            {"a": aggregate_id, "t": EVENT_TYPE, "payload": json.dumps(STUB_PAYLOAD)},
        )
    with db_engine.connect() as conn:
        outbox_id = conn.execute(
            text("SELECT id FROM outbox WHERE aggregate_id = :a"), {"a": aggregate_id}
        ).scalar_one()
    return outbox_id, aggregate_id


# 1. app_bot — NOLOGIN.
def test_app_bot_nologin(db_engine):
    with db_engine.connect() as conn:
        can_login = conn.execute(
            text("SELECT rolcanlogin FROM pg_catalog.pg_roles WHERE rolname = 'app_bot'")
        ).scalar_one()
    assert can_login is False


# 2. app_projector пишет outbox по контракту (без RETURNING).
def test_projector_inserts_outbox(clean_outbox, projector_engine):
    outbox_id, aggregate_id = _projector_insert(projector_engine, clean_outbox)
    with clean_outbox.connect() as conn:
        row = conn.execute(
            text(
                "SELECT aggregate_id, event_type, payload, sent_at, tx_id "
                "FROM outbox WHERE id = :id"
            ),
            {"id": outbox_id},
        ).one()
    assert row.aggregate_id == aggregate_id
    assert row.event_type == EVENT_TYPE
    assert row.payload == STUB_PAYLOAD
    assert row.sent_at is None
    assert row.tx_id is not None


# 3. FOR UPDATE SKIP LOCKED: вторая транзакция не видит захваченную строку.
def test_bot_claim_skip_locked(clean_outbox, projector_engine, bot_engine):
    outbox_id, _ = _projector_insert(projector_engine, clean_outbox)
    with bot_engine.connect() as first, bot_engine.connect() as second:
        first_tx = first.begin()
        claimed = first.execute(CLAIM_BATCH, {"n": 10}).all()
        assert [row.id for row in claimed] == [outbox_id]

        second_tx = second.begin()
        assert second.execute(CLAIM_BATCH, {"n": 10}).all() == []
        second_tx.rollback()

        first_tx.rollback()
        with second.begin():
            again = second.execute(CLAIM_BATCH, {"n": 10}).all()
        assert [row.id for row in again] == [outbox_id]


# 4. sent_at ставится один раз; INSERT и UPDATE — разные транзакции.
def test_bot_marks_sent(clean_outbox, projector_engine, bot_engine):
    outbox_id, _ = _projector_insert(projector_engine, clean_outbox)
    with bot_engine.begin() as conn:
        assert conn.execute(MARK_SENT, {"id": outbox_id}).rowcount == 1
    with clean_outbox.connect() as conn:
        row = conn.execute(
            text("SELECT created_at, sent_at FROM outbox WHERE id = :id"),
            {"id": outbox_id},
        ).one()
    assert row.sent_at is not None
    assert row.sent_at > row.created_at
    with bot_engine.begin() as conn:
        assert conn.execute(MARK_SENT, {"id": outbox_id}).rowcount == 0


# 5. Сбой: DLQ и sent_at одной транзакцией (В13 — «обработано»).
def test_bot_moves_to_dlq(clean_outbox, projector_engine, bot_engine):
    outbox_id, _ = _projector_insert(projector_engine, clean_outbox)
    with bot_engine.begin() as conn:
        claimed = conn.execute(CLAIM_BATCH, {"n": 1}).one()
        conn.execute(
            INSERT_DLQ,
            {"id": claimed.id, "payload": json.dumps(claimed.payload), "e": "stub: failed"},
        )
        assert conn.execute(MARK_SENT, {"id": claimed.id}).rowcount == 1
    with clean_outbox.connect() as conn:
        dlq = conn.execute(
            text("SELECT original_id, payload, replayed_at FROM outbox_dlq")
        ).all()
        sent_at = conn.execute(
            text("SELECT sent_at FROM outbox WHERE id = :id"), {"id": outbox_id}
        ).scalar_one()
    assert [tuple(row) for row in dlq] == [(outbox_id, STUB_PAYLOAD, None)]
    assert sent_at is not None


# 6. Адресат: pid → tg_user_id, только не стёртый (В11).
def test_bot_reads_recipient(db_api_client, bot_engine):
    created = _first_launch(db_api_client, 3401)
    assert created.status_code == 201, created.text
    pid = created.json()["pid"]
    with bot_engine.connect() as conn:
        recipients = conn.execute(SELECT_RECIPIENT, {"p": pid}).scalars().all()
    assert recipients == [3401]


# 7. Не uuid в aggregate_id — ошибка данных, а не отказ в правах.
def test_bot_bad_uuid_is_data_error(bot_engine):
    from psycopg import errors as pg_errors

    with pytest.raises(DataError) as caught:
        with bot_engine.connect() as conn:
            conn.execute(
                text(
                    "SELECT tg_user_id FROM tg_user_registry "
                    "WHERE pid = CAST('not-a-uuid' AS uuid) AND tombstoned_at IS NULL"
                )
            )
    assert isinstance(caught.value.orig, pg_errors.InvalidTextRepresentation)
    assert not isinstance(caught.value.orig, pg_errors.InsufficientPrivilege)


# 8. app_bot читает text_registry (seed — из db_engine).
def test_bot_reads_text_registry(db_engine, bot_engine):
    with bot_engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM text_registry")).scalar_one()
    assert count > 0


# 9. Запреты app_bot (каждый — своё соединение).
@pytest.mark.parametrize("sql", BOT_DENIED_0009)
def test_app_bot_denied_0009(bot_engine, sql):
    _assert_denied(bot_engine, sql)


# 10. Запреты app_projector.
@pytest.mark.parametrize("sql", PROJECTOR_DENIED_0009)
def test_app_projector_denied_0009(projector_engine, sql):
    _assert_denied(projector_engine, sql)


# 11. Запреты app_api.
@pytest.mark.parametrize("sql", API_DENIED_0009)
def test_app_api_denied_0009(api_engine, sql):
    _assert_denied(api_engine, sql)


# 12. Права по колонкам.
@pytest.mark.parametrize(
    ("role", "table", "column", "privilege", "allowed"),
    COLUMN_PRIVILEGES_0009,
    ids=[f"{c[0]}-{c[1]}-{c[2]}-{c[3]}" for c in COLUMN_PRIVILEGES_0009],
)
def test_column_privileges_0009(db_engine, role, table, column, privilege, allowed):
    with db_engine.connect() as conn:
        granted = conn.execute(
            text("SELECT has_column_privilege(:r, :t, :c, :p)"),
            {"r": role, "t": table, "c": column, "p": privilege},
        ).scalar_one()
    assert granted is allowed, (role, table, column, privilege)


# 13. ПОСЛЕДНИМ: downgrade 0009 снимает права; роль и права 0008/0007 остаются.
def test_downgrade_0009(migrated_db):
    from alembic import command

    cfg = _alembic_config()
    engine = create_engine(migrated_db)
    try:
        with engine.connect() as conn:
            for sql in GRANTED_0009 + KEPT_AFTER_0009:
                assert conn.execute(text(sql)).scalar_one() is True, sql
        command.downgrade(cfg, "0008_day_marks")
        with engine.connect() as conn:
            for sql in GRANTED_0009:
                assert conn.execute(text(sql)).scalar_one() is False, sql
            for sql in KEPT_AFTER_0009:
                assert conn.execute(text(sql)).scalar_one() is True, sql
    finally:
        command.upgrade(cfg, "head")
        engine.dispose()
