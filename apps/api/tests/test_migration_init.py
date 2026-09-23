"""Правило нулевых потерь: миграция 0001_init ⇔ docs/architecture/build/db-schema.sql.

Сравниваются нормализованные SQL-выражения (без комментариев и пробелов).
Если зеркало архитектуры обновится — тест упадёт и покажет, что перенести.
Проверка на живой БД (pg_dump-сверка) описана в PR; здесь — статическая.
"""
import importlib.util
import re
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = API_DIR.parents[1]
SCHEMA_SQL = REPO_ROOT / "docs" / "architecture" / "build" / "db-schema.sql"
MIGRATION = next((API_DIR / "migrations" / "versions").glob("*0001_init*.py"))


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_0001_init", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _normalize(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", "", sql)
    return re.sub(r"\s+", " ", sql).strip().rstrip(";").strip()


def _schema_statements() -> list[str]:
    text = re.sub(r"--[^\n]*", "", SCHEMA_SQL.read_text(encoding="utf-8"))
    return [_normalize(s) for s in text.split(";") if _normalize(s)]


def test_schema_file_exists():
    assert SCHEMA_SQL.is_file(), f"нет {SCHEMA_SQL}"


def test_roles_match_schema():
    mig = _load_migration()
    schema_roles = [
        s.removeprefix("CREATE ROLE ").strip()
        for s in _schema_statements()
        if s.startswith("CREATE ROLE ")
    ]
    assert list(mig.ROLES) == schema_roles


def test_ddl_matches_schema_one_to_one():
    mig = _load_migration()
    schema_ddl = [s for s in _schema_statements() if not s.startswith("CREATE ROLE ")]
    migration_ddl = [_normalize(s) for s in mig.DDL]
    assert migration_ddl == schema_ddl


def test_participant_state_is_regular_table_e1():
    # E1 ERRATA / OVERRIDES.E1: не materialized view.
    mig = _load_migration()
    joined = " ".join(mig.DDL).upper()
    assert "MATERIALIZED VIEW" not in joined
    assert "CREATE TABLE PARTICIPANT_STATE" in re.sub(r"\s+", " ", joined)


def test_no_banned_states_r477():
    # Р477 (И2): состояния banned_soft / banned_hard удалены из FSM.
    mig = _load_migration()
    joined = " ".join(mig.DDL).lower()
    assert "banned_soft" not in joined and "banned_hard" not in joined


def test_downgrade_drops_every_created_table():
    mig = _load_migration()
    created = re.findall(r"CREATE TABLE (\w+)", " ".join(mig.DDL))
    assert sorted(created) == sorted(mig.TABLES_DROP_ORDER)
