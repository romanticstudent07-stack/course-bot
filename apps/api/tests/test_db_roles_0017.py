"""db-sup-1: миграция 0017_support_questions — вопросы поддержки (Р-19), права app_api / app_bot.

Статические тесты (1) идут без БД. Тесты с БД — только в CI (соединение CI — суперпользователь,
оно делает SET ROLE). Роль переключается так же, как в test_db_roles_0015 (_bot_role_engine,
role_engine). Отказы — SQLSTATE 42501 (psycopg.errors.InsufficientPrivilege). db_engine
(conftest) чистит tg_user_registry с CASCADE, и строки support_questions уходят вместе с ней.
CHECK: каждый случай ломает одно ограничение; NULL ловит NOT NULL раньше CHECK.
tg_user_id — 4201–4299. Тест downgrade — последним в файле; в finally схема возвращается на head.
"""
import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.db import models
from tests.conftest import _alembic_config
from tests.test_db_roles import _assert_denied, role_engine
from tests.test_db_roles_0009 import _bot_role_engine

API_DIR = Path(__file__).resolve().parents[1]
MIGRATION_0017 = next(
    (API_DIR / "migrations" / "versions").glob("*0017_support_questions*.py")
)

# Контракт api-sup-1 (API, app_api): запись вопроса.
API_INSERT = text(
    "INSERT INTO support_questions (pid, topic_code, body, client_op_id) "
    "VALUES (:pid, :topic, :body, :op) ON CONFLICT (pid, client_op_id) DO NOTHING RETURNING id"
)
# Контракт api-sup-1: частота.
API_RATE = text("SELECT max(created_at) FROM support_questions WHERE pid = :pid")
# Контракт bot-sup-1 (бот, app_bot): пост по question_id.
BOT_READ = text(
    "SELECT pid, topic_code, body, created_at FROM support_questions WHERE id = :question_id"
)

OWNER_INSERT = text(
    "INSERT INTO support_questions (pid, topic_code, body, client_op_id) "
    "VALUES (:pid, :topic, :body, :op)"
)
OWNER_INSERT_RETURNING = text(
    "INSERT INTO support_questions (pid, topic_code, body, client_op_id) "
    "VALUES (:pid, :topic, :body, :op) RETURNING id"
)
OWNER_COUNT = text("SELECT count(*) FROM support_questions WHERE pid = :p")

CK_TOPIC = "ck_support_questions_topic_code"
CK_BODY = "ck_support_questions_body_len"
CK_OP = "ck_support_questions_client_op_id"

EXPECTED_PRIVILEGES_0017: tuple[tuple[str, str, str], ...] = (
    ("INSERT (pid, topic_code, body, client_op_id)", "TABLE support_questions", "app_api"),
    ("SELECT (id, pid, client_op_id, created_at)", "TABLE support_questions", "app_api"),
    ("USAGE", "SEQUENCE support_questions_id_seq", "app_api"),
    ("SELECT (id, pid, topic_code, body, created_at)", "TABLE support_questions", "app_bot"),
)

API_DENIED_0017: tuple[str, ...] = (
    "SELECT body FROM support_questions",
    "UPDATE support_questions SET body = 'xx'",
    "DELETE FROM support_questions",
    "TRUNCATE support_questions",
)

BOT_DENIED_0017: tuple[str, ...] = (
    "INSERT INTO support_questions (pid, topic_code, body, client_op_id) "
    "VALUES (gen_random_uuid(), 's1', 'ab', 'op')",
    "SELECT client_op_id FROM support_questions",
    "UPDATE support_questions SET body = 'xx'",
    "DELETE FROM support_questions",
)

PROJECTOR_DENIED_0017: tuple[str, ...] = ("SELECT id FROM support_questions",)

# (имя, SQL-функция прав, ожидание).
PRIVILEGE_CHECKS_0017: tuple[tuple[str, str, bool], ...] = (
    (
        "api-insert-topic-code",
        "has_column_privilege('app_api', 'support_questions', 'topic_code', 'INSERT')",
        True,
    ),
    (
        "api-insert-id",
        "has_column_privilege('app_api', 'support_questions', 'id', 'INSERT')",
        False,
    ),
    (
        "api-insert-created-at",
        "has_column_privilege('app_api', 'support_questions', 'created_at', 'INSERT')",
        False,
    ),
    (
        "api-select-body",
        "has_column_privilege('app_api', 'support_questions', 'body', 'SELECT')",
        False,
    ),
    (
        "api-select-topic-code",
        "has_column_privilege('app_api', 'support_questions', 'topic_code', 'SELECT')",
        False,
    ),
    (
        "api-seq-usage",
        "has_sequence_privilege('app_api', 'support_questions_id_seq', 'USAGE')",
        True,
    ),
    (
        "bot-select-body",
        "has_column_privilege('app_bot', 'support_questions', 'body', 'SELECT')",
        True,
    ),
    (
        "bot-select-topic-code",
        "has_column_privilege('app_bot', 'support_questions', 'topic_code', 'SELECT')",
        True,
    ),
    (
        "bot-select-client-op-id",
        "has_column_privilege('app_bot', 'support_questions', 'client_op_id', 'SELECT')",
        False,
    ),
    (
        "bot-insert",
        "has_any_column_privilege('app_bot', 'support_questions', 'INSERT')",
        False,
    ),
    (
        "projector-select",
        "has_any_column_privilege('app_projector', 'support_questions', 'SELECT')",
        False,
    ),
    (
        "projector-insert",
        "has_any_column_privilege('app_projector', 'support_questions', 'INSERT')",
        False,
    ),
    (
        "public-select",
        "has_any_column_privilege('public', 'support_questions', 'SELECT')",
        False,
    ),
)

# Табличных UPDATE / DELETE / TRUNCATE на support_questions нет ни у кого.
TABLE_PRIVILEGES_DENIED_0017: tuple[tuple[str, str], ...] = tuple(
    (role, priv)
    for role in ("app_api", "app_bot", "app_projector")
    for priv in ("UPDATE", "DELETE", "TRUNCATE")
)

# (id, topic_code, body, client_op_id, ожидаемое имя CHECK).
REJECTED_0017: tuple[tuple[str, str, str, str, str], ...] = (
    ("topic-s0", "s0", "ab", "op", CK_TOPIC),
    ("topic-s8", "s8", "ab", "op", CK_TOPIC),
    ("topic-S1", "S1", "ab", "op", CK_TOPIC),
    ("topic-empty", "", "ab", "op", CK_TOPIC),
    ("topic-other-space", "other ", "ab", "op", CK_TOPIC),
    ("body-a", "s1", "a", "op", CK_BODY),
    ("body-spaced-a", "s1", "   a   ", "op", CK_BODY),
    ("body-empty", "s1", "", "op", CK_BODY),
    ("body-2001-x", "s1", "x" * 2001, "op", CK_BODY),
    ("body-2001-ya", "s1", "я" * 2001, "op", CK_BODY),
    ("op-empty", "s1", "ab", "", CK_OP),
    ("op-65", "s1", "ab", "x" * 65, CK_OP),
)

# (id, topic_code, body, client_op_id) — вставка проходит.
ACCEPTED_0017: tuple[tuple[str, str, str, str], ...] = (
    *((f"topic-{code}", code, "ab", "op") for code in models.SUPPORT_TOPIC_CODES),
    ("body-ab", "s1", "ab", "op"),
    ("body-2000-x", "s1", "x" * 2000, "op"),
    ("body-2000-ya", "s1", "я" * 2000, "op"),
    ("op-64", "s1", "ab", "x" * 64),
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "mig_0017_support_questions", MIGRATION_0017
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _migration_code(module) -> str:
    """Текст миграции без docstring модуля (в нём запреты названы словами)."""
    source = MIGRATION_0017.read_text(encoding="utf-8")
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


def _owner_insert(db_engine, pid, topic, body, op) -> None:
    with db_engine.begin() as conn:
        conn.execute(OWNER_INSERT, {"pid": pid, "topic": topic, "body": body, "op": op})


# 1. Статика: revision, down_revision, права, нет ALTER DEFAULT PRIVILEGES и PUBLIC.
def test_revision_0017():
    module = _load_migration()
    assert module.revision == "0017_support_questions"
    assert module.down_revision == "0015_onboarding_form"


def test_privileges_static_0017():
    module = _load_migration()
    assert module.ROLES == ("app_api", "app_bot")
    assert module.PRIVILEGES == EXPECTED_PRIVILEGES_0017
    for privilege, target, role in module.PRIVILEGES:
        assert role != "app_projector", (privilege, target, role)
        verb = privilege.split()[0].upper()
        assert verb not in {"UPDATE", "DELETE", "TRUNCATE"}, (privilege, target, role)
    code = _migration_code(module)
    assert "ALTER DEFAULT PRIVILEGES" not in code.upper()
    # Слово в верхнем регистре: строчное public допустимо в именах и импортах.
    assert "PUBLIC" not in code
    # GRANT — только в цикле по PRIVILEGES.
    assert code.count("GRANT ") == 1


def test_models_match_checks_0017():
    module = _load_migration()
    checks = dict(module.CHECKS)
    assert models.SUPPORT_TOPIC_CODES == ("s1", "s2", "s3", "s4", "s5", "s6", "s7", "other")
    assert checks == {
        CK_TOPIC: "topic_code IS NOT NULL AND topic_code IN ("
        + ", ".join(f"'{c}'" for c in models.SUPPORT_TOPIC_CODES)
        + ")",
        CK_BODY: (
            f"body IS NOT NULL AND char_length(btrim(body)) >= {models.SUPPORT_BODY_MIN_LEN} "
            f"AND char_length(body) <= {models.SUPPORT_BODY_MAX_LEN}"
        ),
        CK_OP: (
            "client_op_id IS NOT NULL AND char_length(client_op_id) "
            f"BETWEEN 1 AND {models.SUPPORT_CLIENT_OP_ID_MAX_LEN}"
        ),
    }
    columns = set(models.SupportQuestion.__table__.columns.keys())
    assert columns == {"id", "pid", "topic_code", "body", "client_op_id", "created_at"}


# 2. Права: контрактный SQL раздела 7 под app_api и app_bot.
def test_api_contract_0017(db_engine, api_engine):
    pid = _registry_pid(db_engine, 4201)
    other_pid = _registry_pid(db_engine, 4202)
    params = {"pid": pid, "topic": "s1", "body": "вопрос", "op": "op-1"}
    with api_engine.begin() as conn:
        question_id = conn.execute(API_INSERT, params).scalar_one()
    assert question_id > 0

    with api_engine.begin() as conn:
        again = conn.execute(API_INSERT, {**params, "body": "другой"}).first()
    assert again is None
    with db_engine.connect() as conn:
        assert conn.execute(OWNER_COUNT, {"p": pid}).scalar_one() == 1

    with api_engine.begin() as conn:
        other_id = conn.execute(API_INSERT, {**params, "pid": other_pid}).scalar_one()
        last_at = conn.execute(API_RATE, {"pid": pid}).scalar_one()
    assert other_id > 0
    assert last_at is not None


def test_bot_reads_0017(db_engine, bot_engine):
    pid = _registry_pid(db_engine, 4203)
    with db_engine.begin() as conn:
        question_id = conn.execute(
            OWNER_INSERT_RETURNING,
            {"pid": pid, "topic": "other", "body": "вопрос", "op": "op-1"},
        ).scalar_one()
    with bot_engine.connect() as conn:
        row = conn.execute(BOT_READ, {"question_id": question_id}).one()
    assert row.pid == pid
    assert (row.topic_code, row.body) == ("other", "вопрос")
    assert row.created_at is not None


@pytest.mark.parametrize(
    ("name", "sql", "allowed"),
    PRIVILEGE_CHECKS_0017,
    ids=[c[0] for c in PRIVILEGE_CHECKS_0017],
)
def test_privileges_0017(db_engine, name, sql, allowed):
    with db_engine.connect() as conn:
        granted = conn.execute(text(f"SELECT {sql}")).scalar_one()
    assert granted is allowed, name


@pytest.mark.parametrize(("role", "privilege"), TABLE_PRIVILEGES_DENIED_0017)
def test_no_update_delete_truncate_0017(db_engine, role, privilege):
    with db_engine.connect() as conn:
        granted = conn.execute(
            text("SELECT has_table_privilege(:r, 'support_questions', :p)"),
            {"r": role, "p": privilege},
        ).scalar_one()
    assert granted is False, (role, privilege)


@pytest.mark.parametrize("sql", API_DENIED_0017)
def test_app_api_denied_0017(api_engine, sql):
    _assert_denied(api_engine, sql)


@pytest.mark.parametrize("sql", BOT_DENIED_0017)
def test_app_bot_denied_0017(bot_engine, sql):
    _assert_denied(bot_engine, sql)


@pytest.mark.parametrize("sql", PROJECTOR_DENIED_0017)
def test_app_projector_denied_0017(projector_engine, sql):
    _assert_denied(projector_engine, sql)


# 3. CHECK, NOT NULL, UNIQUE, FK, индекс (вставка владельцем, имя ограничения в diag).
@pytest.mark.parametrize(
    ("case", "topic", "body", "op", "constraint"),
    REJECTED_0017,
    ids=[c[0] for c in REJECTED_0017],
)
def test_check_rejected_0017(db_engine, case, topic, body, op, constraint):
    from psycopg import errors as pg_errors

    pid = _registry_pid(db_engine, 4210)
    with pytest.raises(IntegrityError) as caught:
        _owner_insert(db_engine, pid, topic, body, op)
    assert isinstance(caught.value.orig, pg_errors.CheckViolation), case
    assert caught.value.orig.diag.constraint_name == constraint, case


@pytest.mark.parametrize(
    ("case", "topic", "body", "op"),
    ACCEPTED_0017,
    ids=[c[0] for c in ACCEPTED_0017],
)
def test_check_accepted_0017(db_engine, case, topic, body, op):
    pid = _registry_pid(db_engine, 4211)
    _owner_insert(db_engine, pid, topic, body, op)
    with db_engine.connect() as conn:
        assert conn.execute(OWNER_COUNT, {"p": pid}).scalar_one() == 1, case


@pytest.mark.parametrize(
    "column", ["pid", "topic_code", "body", "client_op_id"]
)
def test_not_null_0017(db_engine, column):
    from psycopg import errors as pg_errors

    pid = _registry_pid(db_engine, 4212)
    values = {"pid": pid, "topic": "s1", "body": "ab", "op": "op"}
    key = {"pid": "pid", "topic_code": "topic", "body": "body", "client_op_id": "op"}[column]
    values[key] = None
    with pytest.raises(IntegrityError) as caught:
        with db_engine.begin() as conn:
            conn.execute(OWNER_INSERT, values)
    assert isinstance(caught.value.orig, pg_errors.NotNullViolation), column
    assert caught.value.orig.diag.column_name == column


def test_duplicate_op_rejected_0017(db_engine):
    from psycopg import errors as pg_errors

    pid = _registry_pid(db_engine, 4213)
    _owner_insert(db_engine, pid, "s1", "ab", "op")
    with pytest.raises(IntegrityError) as caught:
        _owner_insert(db_engine, pid, "s2", "cd", "op")
    assert isinstance(caught.value.orig, pg_errors.UniqueViolation)
    assert (
        caught.value.orig.diag.constraint_name == "support_questions_pid_client_op_id_key"
    )


def test_unknown_pid_rejected_0017(db_engine):
    from psycopg import errors as pg_errors

    with pytest.raises(IntegrityError) as caught:
        _owner_insert(db_engine, uuid.uuid4(), "s1", "ab", "op")
    assert isinstance(caught.value.orig, pg_errors.ForeignKeyViolation)
    assert caught.value.orig.diag.constraint_name == "support_questions_pid_fkey"


def test_index_0017(db_engine):
    with db_engine.connect() as conn:
        indexdef = conn.execute(
            text(
                "SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' "
                "AND tablename = 'support_questions' "
                "AND indexname = 'support_questions_pid_created_idx'"
            )
        ).scalar_one()
    assert "UNIQUE" not in indexdef.upper()
    assert indexdef.endswith("(pid, created_at)")


# 4. ПОСЛЕДНИМ: downgrade до 0015 — support_questions нет, onboarding_form и право 0015 целы.
def test_downgrade_0017(migrated_db):
    from alembic import command

    cfg = _alembic_config()
    sq_exists = text("SELECT to_regclass('public.support_questions') IS NOT NULL")
    form_exists = text("SELECT to_regclass('public.onboarding_form') IS NOT NULL")
    api_form_insert = text(
        "SELECT has_any_column_privilege('app_api', 'onboarding_form', 'INSERT')"
    )
    engine = create_engine(migrated_db)
    try:
        with engine.connect() as conn:
            assert conn.execute(sq_exists).scalar_one() is True
        command.downgrade(cfg, "0015_onboarding_form")
        with engine.connect() as conn:
            assert conn.execute(sq_exists).scalar_one() is False
            assert conn.execute(form_exists).scalar_one() is True
            assert conn.execute(api_form_insert).scalar_one() is True  # право 0015 цело
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            assert conn.execute(sq_exists).scalar_one() is True
    finally:
        command.upgrade(cfg, "head")
        engine.dispose()
