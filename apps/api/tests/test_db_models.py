"""Миграции ⇔ модели ⇔ живая схема. Нужен DATABASE_URL.

- после upgrade head таблицы = apps/api/tests/expected_tables.txt (тот же список, что в CI);
- цикл: head → 0010 (без reflections_log) → 0009 (без access_grants)
  → 0007 (ещё и без day_marks)
  → 0006 (ещё и без idempotency_keys)
  → 0004 (ещё и без participant_events и participant_state_checkpoints)
  → 0003 (ещё и без consent_events) → 0002 (ещё и без text_registry)
  → 0001 (ровно таблицы 0001) → base (пусто); в finally — upgrade head
  (упавший шаг не оставит схему внизу для следующих тестов), затем проверка таблиц;
- модели SQLAlchemy совпадают с живой схемой (alembic compare_metadata).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text

from app.db import models  # noqa: F401
from app.db.base import Base
from tests.conftest import _alembic_config

API_DIR = Path(__file__).resolve().parents[1]
MIGRATION_0001 = next((API_DIR / "migrations" / "versions").glob("*0001_init*.py"))
EXPECTED_TABLES_FILE = API_DIR / "tests" / "expected_tables.txt"

TABLES_0005 = {"participant_events", "participant_state_checkpoints"}
TABLES_0007 = {"idempotency_keys"}
TABLES_0008 = {"day_marks"}
TABLES_0010 = {"access_grants"}
TABLES_0011 = {"reflections_log"}

_COUNT_SQL = text(
    "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename <> 'alembic_version'"
)


def _tables(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            return {r[0] for r in conn.execute(_COUNT_SQL)}
    finally:
        engine.dispose()


def _tables_0001() -> set[str]:
    spec = importlib.util.spec_from_file_location("mig_0001_init_models", MIGRATION_0001)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return set(module.TABLES_DROP_ORDER)


def _expected_tables() -> set[str]:
    """Список из expected_tables.txt: без комментариев (#) и пустых строк."""
    names = set()
    for line in EXPECTED_TABLES_FILE.read_text(encoding="utf-8").splitlines():
        name = line.strip()
        if name and not name.startswith("#"):
            names.add(name)
    return names


def test_expected_tables_file_includes_0001():
    assert _tables_0001() <= _expected_tables()


def test_expected_tables_count_after_0011():
    assert len(_expected_tables()) == 17
    assert TABLES_0011 <= _expected_tables()
    assert TABLES_0010 <= _expected_tables()
    assert "consent_events" in _expected_tables()
    assert TABLES_0005 <= _expected_tables()
    assert TABLES_0007 <= _expected_tables()
    assert TABLES_0008 <= _expected_tables()


def test_upgrade_downgrade_upgrade_cycle(migrated_db):
    cfg = _alembic_config()
    expected = _expected_tables()
    assert _tables(migrated_db) == expected

    try:
        command.downgrade(cfg, "0010_access_grants")
        assert _tables(migrated_db) == expected - TABLES_0011  # 0011 не ломает 0010

        expected = expected - TABLES_0011  # дальше — как было, без таблиц 0011
        command.downgrade(cfg, "0009_app_bot")
        assert _tables(migrated_db) == expected - TABLES_0010  # 0010 не ломает 0009

        expected = expected - TABLES_0010  # дальше — как было, без таблиц 0010
        command.downgrade(cfg, "0007_day_state")
        assert _tables(migrated_db) == expected - TABLES_0008  # 0008 не ломает 0007

        command.downgrade(cfg, "0006_app_roles")
        assert _tables(migrated_db) == expected - TABLES_0008 - TABLES_0007

        command.downgrade(cfg, "0004_consent_events")
        assert _tables(migrated_db) == expected - TABLES_0008 - TABLES_0007 - TABLES_0005

        command.downgrade(cfg, "0003_text_registry")
        assert _tables(migrated_db) == expected - TABLES_0008 - TABLES_0007 - TABLES_0005 - {
            "consent_events",
        }

        command.downgrade(cfg, "0002_tg_user_registry")
        assert _tables(migrated_db) == expected - TABLES_0008 - TABLES_0007 - TABLES_0005 - {
            "text_registry",
            "consent_events",
        }

        command.downgrade(cfg, "0001_init")
        assert _tables(migrated_db) == _tables_0001()  # 0002 не ломает 0001

        command.downgrade(cfg, "base")
        assert _tables(migrated_db) == set()
    finally:
        command.upgrade(cfg, "head")

    assert _tables(migrated_db) == _expected_tables()


def test_models_match_live_schema(migrated_db):
    engine = create_engine(migrated_db)
    try:
        with engine.connect() as conn:
            ctx = MigrationContext.configure(
                conn,
                opts={
                    "compare_type": True,
                    "compare_server_default": False,
                    # Сверяем только таблицы, описанные моделями (0001 моделями не покрыта,
                    # и её xid8-колонки SQLAlchemy не распознаёт).
                    "include_name": lambda name, type_, parent_names: (
                        type_ != "table" or name in Base.metadata.tables
                    ),
                },
            )
            diff = compare_metadata(ctx, Base.metadata)
    finally:
        engine.dispose()
    assert diff == [], diff
