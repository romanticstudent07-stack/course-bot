"""db-i3-3: миграция 0015_onboarding_form — анкета по Р-16 (пол, самочувствие), права app_api.

Статические тесты (1) идут без БД. Тесты с БД — только в CI (соединение CI — суперпользователь,
оно делает SET ROLE). Роль переключается так же, как в test_db_roles_0014 (_bot_role_engine,
role_engine). Отказы — SQLSTATE 42501 (psycopg.errors.InsufficientPrivilege). db_engine
(conftest) чистит tg_user_registry с CASCADE, и строки onboarding_form уходят вместе с ней.
CHECK: каждый случай ломает одно ограничение; NULL в gender или wellbeing_code ловит NOT NULL.
tg_user_id — 4001–4099. Тест downgrade — последним в файле; в finally схема возвращается на head.
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
MIGRATION_0015 = next(
    (API_DIR / "migrations" / "versions").glob("*0015_onboarding_form*.py")
)

# Контракт api-2 (API, app_api): запись анкеты.
API_INSERT = text(
    "INSERT INTO onboarding_form (pid, gender, wellbeing_code) "
    "VALUES (:pid, :gender, :wb) ON CONFLICT (pid) DO NOTHING RETURNING pid"
)
# Контракт api-2: повтор и чтение.
API_READ = text(
    "SELECT gender, wellbeing_code, created_at FROM onboarding_form WHERE pid = :pid"
)

OWNER_INSERT = text(
    "INSERT INTO onboarding_form (pid, gender, wellbeing_code) VALUES (:pid, :g, :wb)"
)
OWNER_COUNT = text("SELECT count(*) FROM onboarding_form WHERE pid = :p")

CK_GENDER = "ck_onboarding_form_gender"
CK_WELLBEING = "ck_onboarding_form_wellbeing_code"

EXPECTED_PRIVILEGES_0015: tuple[tuple[str, str, str], ...] = (
    ("INSERT (pid, gender, wellbeing_code)", "TABLE onboarding_form", "app_api"),
    ("SELECT (pid, gender, wellbeing_code, created_at)", "TABLE onboarding_form", "app_api"),
)

API_DENIED_0015: tuple[str, ...] = (
    "UPDATE onboarding_form SET gender = 'female'",
    "DELETE FROM onboarding_form",
    "TRUNCATE onboarding_form",
)

BOT_DENIED_0015: tuple[str, ...] = (
    "SELECT pid FROM onboarding_form",
    "SELECT gender FROM onboarding_form",
    "INSERT INTO onboarding_form (pid, gender, wellbeing_code) "
    "VALUES (gen_random_uuid(), 'male', 'ok')",
)

PROJECTOR_DENIED_0015: tuple[str, ...] = ("SELECT pid FROM onboarding_form",)

# (имя, SQL-функция прав, ожидание).
PRIVILEGE_CHECKS_0015: tuple[tuple[str, str, bool], ...] = (
    (
        "api-insert-gender",
        "has_column_privilege('app_api', 'onboarding_form', 'gender', 'INSERT')",
        True,
    ),
    (
        "api-select-created-at",
        "has_column_privilege('app_api', 'onboarding_form', 'created_at', 'SELECT')",
        True,
    ),
    (
        "api-insert-created-at",
        "has_column_privilege('app_api', 'onboarding_form', 'created_at', 'INSERT')",
        False,
    ),
    (
        "api-update",
        "has_any_column_privilege('app_api', 'onboarding_form', 'UPDATE')",
        False,
    ),
    (
        "bot-select",
        "has_any_column_privilege('app_bot', 'onboarding_form', 'SELECT')",
        False,
    ),
    (
        "bot-insert",
        "has_any_column_privilege('app_bot', 'onboarding_form', 'INSERT')",
        False,
    ),
    (
        "projector-select",
        "has_any_column_privilege('app_projector', 'onboarding_form', 'SELECT')",
        False,
    ),
    (
        "projector-insert",
        "has_any_column_privilege('app_projector', 'onboarding_form', 'INSERT')",
        False,
    ),
    (
        "public-select",
        "has_table_privilege('public', 'onboarding_form', 'SELECT')",
        False,
    ),
    (
        "public-insert",
        "has_table_privilege('public', 'onboarding_form', 'INSERT')",
        False,
    ),
    (
        "public-select-any-column",
        "has_any_column_privilege('public', 'onboarding_form', 'SELECT')",
        False,
    ),
)

# Табличных UPDATE / DELETE / TRUNCATE на onboarding_form нет ни у кого.
TABLE_PRIVILEGES_DENIED_0015: tuple[tuple[str, str], ...] = tuple(
    (role, priv)
    for role in ("app_bot", "app_api", "app_projector")
    for priv in ("UPDATE", "DELETE", "TRUNCATE")
)

# (id, gender, wellbeing_code, ожидаемое имя CHECK).
REJECTED_0015: tuple[tuple[str, str, str, str], ...] = (
    ("gender-other", "other", "ok", CK_GENDER),
    ("gender-Male", "Male", "ok", CK_GENDER),
    ("gender-empty", "", "ok", CK_GENDER),
    ("wellbeing-Bad", "male", "Bad", CK_WELLBEING),
    ("wellbeing-empty", "male", "", CK_WELLBEING),
    ("wellbeing-dash", "male", "a-b", CK_WELLBEING),
    ("wellbeing-len-33", "male", "x" * 33, CK_WELLBEING),
    ("wellbeing-cyrillic", "male", "хорошо", CK_WELLBEING),
)

# (id, gender, wellbeing_code) — вставка проходит.
ACCEPTED_0015: tuple[tuple[str, str, str], ...] = (
    ("ok", "male", "ok"),
    ("scale-3", "female", "scale_3"),
    ("len-32", "female", "x" * 32),
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_0015_onboarding_form", MIGRATION_0015)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _migration_code(module) -> str:
    """Текст миграции без docstring модуля (в нём запреты названы словами)."""
    source = MIGRATION_0015.read_text(encoding="utf-8")
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


def _owner_insert(db_engine, pid, gender, wellbeing_code) -> None:
    with db_engine.begin() as conn:
        conn.execute(OWNER_INSERT, {"pid": pid, "g": gender, "wb": wellbeing_code})


# 1. Статика: revision, down_revision, права, нет ALTER DEFAULT PRIVILEGES и PUBLIC.
def test_revision_0015():
    module = _load_migration()
    assert module.revision == "0015_onboarding_form"
    assert module.down_revision == "0014_measurements_log"


def test_privileges_static_0015():
    module = _load_migration()
    assert module.ROLES == ("app_api",)
    for privilege, target, role in module.PRIVILEGES:
        assert role == "app_api", (privilege, target, role)
        verb = privilege.split()[0].upper()
        assert verb not in {"UPDATE", "DELETE", "TRUNCATE"}, (privilege, target, role)
    assert module.PRIVILEGES == EXPECTED_PRIVILEGES_0015
    code = _migration_code(module)
    assert "ALTER DEFAULT PRIVILEGES" not in code.upper()
    # Слово в верхнем регистре: строчное public допустимо в именах и импортах.
    assert "PUBLIC" not in code
    # GRANT — только в цикле по PRIVILEGES (замечание РЕВЬЮЕРА #174).
    assert code.count("GRANT ") == 1


def test_models_match_checks_0015():
    module = _load_migration()
    checks = dict(module.CHECKS)
    assert models.GENDERS == ("male", "female")
    assert checks[CK_GENDER] == (
        "gender IN (" + ", ".join(f"'{g}'" for g in models.GENDERS) + ")"
    )
    assert models.WELLBEING_CODE_PATTERN == "^[a-z0-9_]{1,32}$"
    assert checks[CK_WELLBEING] == f"wellbeing_code ~ '{models.WELLBEING_CODE_PATTERN}'"
    # Р-16: только пол и самочувствие; города, пояса, ФИО, телефона, email нет.
    columns = set(models.OnboardingForm.__table__.columns.keys())
    assert columns == {"pid", "gender", "wellbeing_code", "created_at"}


# 2. Права: контрактный SQL раздела 7 под app_api.
def test_api_contract_0015(db_engine, api_engine):
    pid = _registry_pid(db_engine, 4001)
    with api_engine.begin() as conn:
        returned = conn.execute(
            API_INSERT, {"pid": pid, "gender": "male", "wb": "ok"}
        ).scalar_one()
    assert returned == pid

    with api_engine.begin() as conn:
        again = conn.execute(API_INSERT, {"pid": pid, "gender": "female", "wb": "bad"}).first()
        row = conn.execute(API_READ, {"pid": pid}).one()
    assert again is None
    assert (row.gender, row.wellbeing_code) == ("male", "ok")
    assert row.created_at is not None
    with db_engine.connect() as conn:
        assert conn.execute(OWNER_COUNT, {"p": pid}).scalar_one() == 1


@pytest.mark.parametrize(
    ("name", "sql", "allowed"),
    PRIVILEGE_CHECKS_0015,
    ids=[c[0] for c in PRIVILEGE_CHECKS_0015],
)
def test_privileges_0015(db_engine, name, sql, allowed):
    with db_engine.connect() as conn:
        granted = conn.execute(text(f"SELECT {sql}")).scalar_one()
    assert granted is allowed, name


@pytest.mark.parametrize(("role", "privilege"), TABLE_PRIVILEGES_DENIED_0015)
def test_no_update_delete_truncate_0015(db_engine, role, privilege):
    with db_engine.connect() as conn:
        granted = conn.execute(
            text("SELECT has_table_privilege(:r, 'onboarding_form', :p)"),
            {"r": role, "p": privilege},
        ).scalar_one()
    assert granted is False, (role, privilege)


@pytest.mark.parametrize("sql", API_DENIED_0015)
def test_app_api_denied_0015(api_engine, sql):
    _assert_denied(api_engine, sql)


@pytest.mark.parametrize("sql", BOT_DENIED_0015)
def test_app_bot_denied_0015(bot_engine, sql):
    _assert_denied(bot_engine, sql)


@pytest.mark.parametrize("sql", PROJECTOR_DENIED_0015)
def test_app_projector_denied_0015(projector_engine, sql):
    _assert_denied(projector_engine, sql)


# 3. CHECK, NOT NULL, PK и FK (вставка владельцем, имя ограничения в diag).
@pytest.mark.parametrize(
    ("case", "gender", "wellbeing_code", "constraint"),
    REJECTED_0015,
    ids=[c[0] for c in REJECTED_0015],
)
def test_check_rejected_0015(db_engine, case, gender, wellbeing_code, constraint):
    from psycopg import errors as pg_errors

    pid = _registry_pid(db_engine, 4010)
    with pytest.raises(IntegrityError) as caught:
        _owner_insert(db_engine, pid, gender, wellbeing_code)
    assert isinstance(caught.value.orig, pg_errors.CheckViolation), case
    assert caught.value.orig.diag.constraint_name == constraint, case


@pytest.mark.parametrize(
    ("case", "gender", "wellbeing_code"),
    ACCEPTED_0015,
    ids=[c[0] for c in ACCEPTED_0015],
)
def test_check_accepted_0015(db_engine, case, gender, wellbeing_code):
    pid = _registry_pid(db_engine, 4011)
    _owner_insert(db_engine, pid, gender, wellbeing_code)
    with db_engine.connect() as conn:
        assert conn.execute(OWNER_COUNT, {"p": pid}).scalar_one() == 1, case


@pytest.mark.parametrize(
    ("column", "gender", "wellbeing_code"),
    [("gender", None, "ok"), ("wellbeing_code", "male", None)],
    ids=["gender-null", "wellbeing-null"],
)
def test_not_null_0015(db_engine, column, gender, wellbeing_code):
    from psycopg import errors as pg_errors

    pid = _registry_pid(db_engine, 4012)
    with pytest.raises(IntegrityError) as caught:
        _owner_insert(db_engine, pid, gender, wellbeing_code)
    assert isinstance(caught.value.orig, pg_errors.NotNullViolation), column
    assert caught.value.orig.diag.column_name == column


def test_duplicate_pid_rejected_0015(db_engine):
    from psycopg import errors as pg_errors

    pid = _registry_pid(db_engine, 4013)
    _owner_insert(db_engine, pid, "male", "ok")
    with pytest.raises(IntegrityError) as caught:
        _owner_insert(db_engine, pid, "female", "ok")
    assert isinstance(caught.value.orig, pg_errors.UniqueViolation)
    assert caught.value.orig.diag.constraint_name == "onboarding_form_pkey"


def test_unknown_pid_rejected_0015(db_engine):
    from psycopg import errors as pg_errors

    with pytest.raises(IntegrityError) as caught:
        _owner_insert(db_engine, uuid.uuid4(), "male", "ok")
    assert isinstance(caught.value.orig, pg_errors.ForeignKeyViolation)
    assert caught.value.orig.diag.constraint_name == "onboarding_form_pid_fkey"


# 4. ПОСЛЕДНИМ: downgrade до 0014 — onboarding_form нет, measurements_log и права 0013/0014 целы.
def test_downgrade_0015(migrated_db):
    from alembic import command

    cfg = _alembic_config()
    form_exists = text("SELECT to_regclass('public.onboarding_form') IS NOT NULL")
    log_exists = text("SELECT to_regclass('public.measurements_log') IS NOT NULL")
    api_log_insert = text(
        "SELECT has_any_column_privilege('app_api', 'measurements_log', 'INSERT')"
    )
    tz_select = text(
        "SELECT has_column_privilege('app_bot', 'participant_state', 'tz', 'SELECT')"
    )
    engine = create_engine(migrated_db)
    try:
        with engine.connect() as conn:
            assert conn.execute(form_exists).scalar_one() is True
            assert conn.execute(log_exists).scalar_one() is True
        command.downgrade(cfg, "0014_measurements_log")
        with engine.connect() as conn:
            assert conn.execute(form_exists).scalar_one() is False
            assert conn.execute(log_exists).scalar_one() is True
            assert conn.execute(api_log_insert).scalar_one() is True  # право 0014 цело
            assert conn.execute(tz_select).scalar_one() is True  # право 0013 цело
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            assert conn.execute(form_exists).scalar_one() is True
    finally:
        command.upgrade(cfg, "head")
        engine.dispose()
