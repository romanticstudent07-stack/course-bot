"""db-i3-2: миграция 0014_measurements_log — Чек-Ап и стартовый вес, права app_api / app_bot.

Статические тесты (1) идут без БД. Тесты с БД — только в CI (соединение CI — суперпользователь,
оно делает SET ROLE). Роль переключается так же, как в test_db_roles_0011 (_bot_role_engine,
role_engine). Отказы — SQLSTATE 42501 (psycopg.errors.InsufficientPrivilege). db_engine
(conftest) чистит tg_user_registry с CASCADE, и строки measurements_log уходят вместе с ней.
CHECK: каждый случай ломает одно ограничение; исключение — occasion 'x', он ломает ещё и
ck_measurements_log_stage, а PostgreSQL проверяет CHECK в порядке имён, поэтому в diag —
ck_measurements_log_occasion. Связи балл↔зона в CHECK нет (Р-7): баллы 9 / 10 / 22 / 23
проходят с любой зоной.
tg_user_id — 3901–3999. Тест downgrade — последним в файле; в finally схема возвращается на head.
"""
import importlib.util
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from tests.conftest import _alembic_config
from tests.test_db_roles import _assert_denied, role_engine
from tests.test_db_roles_0009 import _bot_role_engine

API_DIR = Path(__file__).resolve().parents[1]
MIGRATION_0014 = next(
    (API_DIR / "migrations" / "versions").glob("*0014_measurements_log*.py")
)

# Контракт api-1 (API, app_api): Чек-Ап.
API_INSERT_CHECKUP = text(
    "INSERT INTO measurements_log (pid, kind, occasion, stage_no, checkup_answers, "
    "checkup_score, checkup_zone, checkup_config_version, client_op_id) "
    "VALUES (:pid, 'checkup', :occ, :stage, :answers, :score, :zone, :ver, :op) "
    "ON CONFLICT (pid, client_op_id) DO NOTHING RETURNING id"
)
# Контракт api-2 (API, app_api): вес из анкеты.
API_INSERT_BODY = text(
    "INSERT INTO measurements_log (pid, kind, occasion, stage_no, weight_kg, client_op_id) "
    "VALUES (:pid, 'body', :occ, :stage, :w, :op) "
    "ON CONFLICT (pid, client_op_id) DO NOTHING RETURNING id"
)
# Контракт api-1: повтор (RETURNING дал 0 строк).
API_REPEAT = text(
    "SELECT id, checkup_score, checkup_zone, created_at FROM measurements_log "
    "WHERE pid = :pid AND client_op_id = :op"
)
# Контракт bot-1 (бот, app_bot): карточка.
BOT_READ_CARD = text(
    "SELECT kind, occasion, checkup_zone, weight_kg, created_at FROM measurements_log "
    "WHERE pid = :pid ORDER BY created_at"
)

OWNER_INSERT = text(
    "INSERT INTO measurements_log (pid, kind, occasion, stage_no, checkup_answers, "
    "checkup_score, checkup_zone, checkup_config_version, weight_kg, client_op_id) "
    "VALUES (:pid, :kind, :occ, :stage, CAST(:answers AS smallint[]), :score, :zone, "
    ":ver, :w, :op)"
)
OWNER_COUNT = text("SELECT count(*) FROM measurements_log WHERE pid = :p")

CK_ANSWERS = "ck_measurements_log_answers"
CK_SCORE_SUM = "ck_measurements_log_score_sum"
CK_ZONE = "ck_measurements_log_zone"
CK_KIND = "ck_measurements_log_kind"
CK_OCCASION = "ck_measurements_log_occasion"
CK_KIND_CHECKUP = "ck_measurements_log_kind_checkup"
CK_KIND_BODY = "ck_measurements_log_kind_body"
CK_WEIGHT = "ck_measurements_log_weight"
CK_CONFIG_VERSION = "ck_measurements_log_config_version"
CK_CLIENT_OP_ID = "ck_measurements_log_client_op_id"
CK_STAGE = "ck_measurements_log_stage"

API_DENIED_0014: tuple[str, ...] = (
    "UPDATE measurements_log SET checkup_zone = 'green'",
    "DELETE FROM measurements_log",
    "TRUNCATE measurements_log",
)

BOT_DENIED_0014: tuple[str, ...] = (
    "SELECT checkup_score FROM measurements_log",
    "SELECT checkup_answers FROM measurements_log",
    "SELECT checkup_config_version FROM measurements_log",
    "SELECT client_op_id FROM measurements_log",
    "SELECT stage_no FROM measurements_log",
    "SELECT * FROM measurements_log",
    "INSERT INTO measurements_log (pid, kind, occasion, weight_kg, client_op_id) "
    "VALUES (gen_random_uuid(), 'body', 'onboarding', 70, 'bot-op')",
    "UPDATE measurements_log SET checkup_zone = 'green'",
)

PROJECTOR_DENIED_0014: tuple[str, ...] = ("SELECT id FROM measurements_log",)

# (имя, SQL-функция прав, ожидание).
PRIVILEGE_CHECKS_0014: tuple[tuple[str, str, bool], ...] = (
    (
        "api-insert",
        "has_any_column_privilege('app_api', 'measurements_log', 'INSERT')",
        True,
    ),
    (
        "api-select",
        "has_any_column_privilege('app_api', 'measurements_log', 'SELECT')",
        True,
    ),
    (
        "api-update",
        "has_any_column_privilege('app_api', 'measurements_log', 'UPDATE')",
        False,
    ),
    (
        "api-delete",
        "has_table_privilege('app_api', 'measurements_log', 'DELETE')",
        False,
    ),
    (
        "api-seq-usage",
        "has_sequence_privilege('app_api', 'measurements_log_id_seq', 'USAGE')",
        True,
    ),
    (
        "api-insert-id",
        "has_column_privilege('app_api', 'measurements_log', 'id', 'INSERT')",
        False,
    ),
    (
        "api-insert-created-at",
        "has_column_privilege('app_api', 'measurements_log', 'created_at', 'INSERT')",
        False,
    ),
    (
        "bot-select-zone",
        "has_column_privilege('app_bot', 'measurements_log', 'checkup_zone', 'SELECT')",
        True,
    ),
    (
        "bot-select-weight",
        "has_column_privilege('app_bot', 'measurements_log', 'weight_kg', 'SELECT')",
        True,
    ),
    (
        "bot-select-score",
        "has_column_privilege('app_bot', 'measurements_log', 'checkup_score', 'SELECT')",
        False,
    ),
    (
        "bot-select-answers",
        "has_column_privilege('app_bot', 'measurements_log', 'checkup_answers', 'SELECT')",
        False,
    ),
    (
        "bot-select-stage-no",
        "has_column_privilege('app_bot', 'measurements_log', 'stage_no', 'SELECT')",
        False,
    ),
    (
        "bot-insert",
        "has_any_column_privilege('app_bot', 'measurements_log', 'INSERT')",
        False,
    ),
    (
        "bot-update",
        "has_any_column_privilege('app_bot', 'measurements_log', 'UPDATE')",
        False,
    ),
    (
        "bot-seq-usage",
        "has_sequence_privilege('app_bot', 'measurements_log_id_seq', 'USAGE')",
        False,
    ),
    (
        "projector-select",
        "has_any_column_privilege('app_projector', 'measurements_log', 'SELECT')",
        False,
    ),
    (
        "projector-insert",
        "has_any_column_privilege('app_projector', 'measurements_log', 'INSERT')",
        False,
    ),
    (
        "projector-update",
        "has_any_column_privilege('app_projector', 'measurements_log', 'UPDATE')",
        False,
    ),
    (
        "public-select",
        "has_table_privilege('public', 'measurements_log', 'SELECT')",
        False,
    ),
    (
        "public-select-any-column",
        "has_any_column_privilege('public', 'measurements_log', 'SELECT')",
        False,
    ),
)

# Табличных DELETE / TRUNCATE на measurements_log нет ни у кого.
TABLE_PRIVILEGES_DENIED_0014: tuple[tuple[str, str], ...] = tuple(
    (role, priv)
    for role in ("app_bot", "app_api", "app_projector")
    for priv in ("DELETE", "TRUNCATE")
)


def _answers(total: int) -> list[int]:
    """15 ответов 0–3 с суммой total (0–45): сначала тройки, потом остаток и нули."""
    assert 0 <= total <= 45
    answers: list[int] = []
    left = total
    for _ in range(15):
        value = min(3, left)
        answers.append(value)
        left -= value
    return answers


# (id, вид строки, отличия от валидной строки, ожидаемое имя CHECK).
REJECTED_0014: tuple[tuple[str, str, dict, str], ...] = (
    ("answers-14", "checkup", {"answers": [0] * 14, "score": 0}, CK_ANSWERS),
    ("answers-16", "checkup", {"answers": [0] * 16, "score": 0}, CK_ANSWERS),
    ("answer-4", "checkup", {"answers": [4] + [0] * 14, "score": 4}, CK_ANSWERS),
    ("answer-minus-1", "checkup", {"answers": [-1] + [1] * 14, "score": 13}, CK_ANSWERS),
    ("answer-null", "checkup", {"answers": [None] + [0] * 14, "score": 0}, CK_ANSWERS),
    (
        "answers-lower-bound-0",
        "checkup",
        {"answers": "[0:14]={0,0,0,0,0,0,0,0,0,0,0,0,0,0,0}", "score": 0},
        CK_ANSWERS,
    ),
    ("score-not-sum", "checkup", {"answers": _answers(10), "score": 11}, CK_SCORE_SUM),
    ("zone-blue", "checkup", {"zone": "blue"}, CK_ZONE),
    ("kind-x", "checkup", {"kind": "x"}, CK_KIND),
    ("occasion-x", "checkup", {"occ": "x"}, CK_OCCASION),
    ("checkup-with-weight", "checkup", {"w": Decimal("70")}, CK_KIND_CHECKUP),
    ("body-without-weight", "body", {"w": None}, CK_KIND_BODY),
    ("body-with-answers", "body", {"answers": _answers(0)}, CK_KIND_BODY),
    ("weight-29.9", "body", {"w": Decimal("29.9")}, CK_WEIGHT),
    ("weight-300.1", "body", {"w": Decimal("300.1")}, CK_WEIGHT),
    ("version-empty", "checkup", {"ver": ""}, CK_CONFIG_VERSION),
    ("version-spaces", "checkup", {"ver": "   "}, CK_CONFIG_VERSION),
    ("client-op-id-empty", "checkup", {"op": ""}, CK_CLIENT_OP_ID),
    ("onboarding-stage-1", "checkup", {"stage": 1}, CK_STAGE),
    ("stage-end-no-stage", "checkup", {"occ": "stage_end"}, CK_STAGE),
    ("stage-end-stage-0", "checkup", {"occ": "stage_end", "stage": 0}, CK_STAGE),
)

# (id, вид строки, отличия от валидной строки) — вставка проходит.
ACCEPTED_0014: tuple[tuple[str, str, dict], ...] = (
    ("weight-30", "body", {"w": Decimal("30")}),
    ("weight-300", "body", {"w": Decimal("300")}),
    ("score-9-red", "checkup", {"answers": _answers(9), "score": 9, "zone": "red"}),
    ("score-10-green", "checkup", {"answers": _answers(10), "score": 10, "zone": "green"}),
    ("score-22-red", "checkup", {"answers": _answers(22), "score": 22, "zone": "red"}),
    ("score-23-green", "checkup", {"answers": _answers(23), "score": 23, "zone": "green"}),
    ("stage-end-stage-2", "checkup", {"occ": "stage_end", "stage": 2}),
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_0014_measurements_log", MIGRATION_0014)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _migration_code(module) -> str:
    """Текст миграции без docstring модуля (в нём запреты названы словами)."""
    source = MIGRATION_0014.read_text(encoding="utf-8")
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


def _row(pid, kind: str, overrides: dict) -> dict:
    """Валидная строка вида kind (checkup / body) для вставки владельцем + отличия."""
    if kind == "checkup":
        row = {
            "pid": pid,
            "kind": "checkup",
            "occ": "onboarding",
            "stage": None,
            "answers": _answers(10),
            "score": 10,
            "zone": "yellow",
            "ver": "checkup-stub-v1",
            "w": None,
            "op": f"op-{uuid.uuid4()}",
        }
    else:
        row = {
            "pid": pid,
            "kind": "body",
            "occ": "onboarding",
            "stage": None,
            "answers": None,
            "score": None,
            "zone": None,
            "ver": None,
            "w": Decimal("72.5"),
            "op": f"op-{uuid.uuid4()}",
        }
    row.update(overrides)
    return row


def _owner_insert(db_engine, row: dict) -> None:
    with db_engine.begin() as conn:
        conn.execute(OWNER_INSERT, row)


# 1. Статика: revision, down_revision, права, нет ALTER DEFAULT PRIVILEGES и PUBLIC.
def test_revision_0014():
    module = _load_migration()
    assert module.revision == "0014_measurements_log"
    assert module.down_revision == "0013_bot_card"


def test_privileges_static_0014():
    module = _load_migration()
    for privilege, target, role in module.PRIVILEGES:
        assert role != "app_projector", (privilege, target, role)
        verb = privilege.split()[0].upper()
        assert verb not in {"UPDATE", "DELETE", "TRUNCATE"}, (privilege, target, role)
        if role == "app_bot":
            for column in (
                "checkup_score",
                "checkup_answers",
                "checkup_config_version",
                "client_op_id",
                "stage_no",
            ):
                assert column not in privilege, (privilege, target, role)
    code = _migration_code(module)
    assert "ALTER DEFAULT PRIVILEGES" not in code.upper()
    # Слово в верхнем регистре: в коде 0014 есть public строчными (импорты и имена).
    assert "PUBLIC" not in code
    # GRANT — только в цикле по PRIVILEGES (замечание РЕВЬЮЕРА #174).
    assert code.count("GRANT ") == 1


# 2. Права: контрактный SQL раздела 7 под ролями.
def test_api_contract_and_bot_card(db_engine, api_engine, bot_engine):
    pid = _registry_pid(db_engine, 3901)
    checkup = {
        "pid": pid,
        "occ": "onboarding",
        "stage": None,
        "answers": _answers(10),
        "score": 10,
        "zone": "yellow",
        "ver": "checkup-stub-v1",
        "op": "op-checkup-1",
    }
    with api_engine.begin() as conn:
        checkup_id = conn.execute(API_INSERT_CHECKUP, checkup).scalar_one()
    assert checkup_id > 0

    with api_engine.begin() as conn:
        again = conn.execute(API_INSERT_CHECKUP, checkup).first()
        repeat = conn.execute(API_REPEAT, {"pid": pid, "op": "op-checkup-1"}).one()
    assert again is None
    assert repeat.id == checkup_id
    assert (repeat.checkup_score, repeat.checkup_zone) == (10, "yellow")
    assert repeat.created_at is not None
    with db_engine.connect() as conn:
        assert conn.execute(OWNER_COUNT, {"p": pid}).scalar_one() == 1

    body = {"pid": pid, "occ": "onboarding", "stage": None, "w": Decimal("72.5"), "op": "op-w-1"}
    with api_engine.begin() as conn:
        body_id = conn.execute(API_INSERT_BODY, body).scalar_one()
    assert body_id > 0
    assert body_id != checkup_id

    with bot_engine.connect() as conn:
        rows = conn.execute(BOT_READ_CARD, {"pid": pid}).all()
    assert len(rows) == 2
    assert {(r.kind, r.occasion, r.checkup_zone, r.weight_kg) for r in rows} == {
        ("checkup", "onboarding", "yellow", None),
        ("body", "onboarding", None, Decimal("72.5")),
    }
    assert all(r.created_at is not None for r in rows)


@pytest.mark.parametrize(
    ("name", "sql", "allowed"),
    PRIVILEGE_CHECKS_0014,
    ids=[c[0] for c in PRIVILEGE_CHECKS_0014],
)
def test_privileges_0014(db_engine, name, sql, allowed):
    with db_engine.connect() as conn:
        granted = conn.execute(text(f"SELECT {sql}")).scalar_one()
    assert granted is allowed, name


@pytest.mark.parametrize(("role", "privilege"), TABLE_PRIVILEGES_DENIED_0014)
def test_no_delete_truncate_0014(db_engine, role, privilege):
    with db_engine.connect() as conn:
        granted = conn.execute(
            text("SELECT has_table_privilege(:r, 'measurements_log', :p)"),
            {"r": role, "p": privilege},
        ).scalar_one()
    assert granted is False, (role, privilege)


@pytest.mark.parametrize("sql", API_DENIED_0014)
def test_app_api_denied_0014(api_engine, sql):
    _assert_denied(api_engine, sql)


@pytest.mark.parametrize("sql", BOT_DENIED_0014)
def test_app_bot_denied_0014(bot_engine, sql):
    _assert_denied(bot_engine, sql)


@pytest.mark.parametrize("sql", PROJECTOR_DENIED_0014)
def test_app_projector_denied_0014(projector_engine, sql):
    _assert_denied(projector_engine, sql)


# 3. CHECK, UNIQUE и FK (вставка владельцем, имя ограничения в diag).
@pytest.mark.parametrize(
    ("case", "kind", "overrides", "constraint"),
    REJECTED_0014,
    ids=[c[0] for c in REJECTED_0014],
)
def test_check_rejected_0014(db_engine, case, kind, overrides, constraint):
    from psycopg import errors as pg_errors

    pid = _registry_pid(db_engine, 3910)
    with pytest.raises(IntegrityError) as caught:
        _owner_insert(db_engine, _row(pid, kind, overrides))
    assert isinstance(caught.value.orig, pg_errors.CheckViolation), case
    assert caught.value.orig.diag.constraint_name == constraint, case


@pytest.mark.parametrize(
    ("case", "kind", "overrides"),
    ACCEPTED_0014,
    ids=[c[0] for c in ACCEPTED_0014],
)
def test_check_accepted_0014(db_engine, case, kind, overrides):
    pid = _registry_pid(db_engine, 3911)
    _owner_insert(db_engine, _row(pid, kind, overrides))
    with db_engine.connect() as conn:
        assert conn.execute(OWNER_COUNT, {"p": pid}).scalar_one() == 1, case


def test_duplicate_client_op_id_rejected_0014(db_engine):
    from psycopg import errors as pg_errors

    pid = _registry_pid(db_engine, 3912)
    _owner_insert(db_engine, _row(pid, "checkup", {"op": "op-dup"}))
    with pytest.raises(IntegrityError) as caught:
        _owner_insert(db_engine, _row(pid, "body", {"op": "op-dup"}))
    assert isinstance(caught.value.orig, pg_errors.UniqueViolation)
    assert (
        caught.value.orig.diag.constraint_name == "measurements_log_pid_client_op_id_key"
    )


def test_unknown_pid_rejected_0014(db_engine):
    from psycopg import errors as pg_errors

    with pytest.raises(IntegrityError) as caught:
        _owner_insert(db_engine, _row(uuid.uuid4(), "body", {}))
    assert isinstance(caught.value.orig, pg_errors.ForeignKeyViolation)
    assert caught.value.orig.diag.constraint_name == "measurements_log_pid_fkey"


# 4. ПОСЛЕДНИМ: downgrade до 0013 — таблицы нет, право 0013 у app_bot цело.
def test_downgrade_0014(migrated_db):
    from alembic import command

    cfg = _alembic_config()
    table_exists = text("SELECT to_regclass('public.measurements_log') IS NOT NULL")
    tz_select = text(
        "SELECT has_column_privilege('app_bot', 'participant_state', 'tz', 'SELECT')"
    )
    engine = create_engine(migrated_db)
    try:
        with engine.connect() as conn:
            assert conn.execute(table_exists).scalar_one() is True
            assert conn.execute(tz_select).scalar_one() is True
        command.downgrade(cfg, "0013_bot_card")
        with engine.connect() as conn:
            assert conn.execute(table_exists).scalar_one() is False
            assert conn.execute(tz_select).scalar_one() is True  # право 0013 цело
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            assert conn.execute(table_exists).scalar_one() is True
    finally:
        command.upgrade(cfg, "head")
        engine.dispose()
