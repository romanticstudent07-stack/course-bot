"""Миграции ⇔ модели ⇔ живая схема (Итерация 1b+1c). Нужен DATABASE_URL.

- цикл upgrade head → downgrade base → upgrade head;
- число таблиц: 8 (0001) + 1 (0002 tg_user_registry) = 9;
- 0002 не трогает 0001: downgrade до 0001_init оставляет ровно 8 таблиц 0001;
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


def test_upgrade_downgrade_upgrade_cycle(migrated_db):
    cfg = _alembic_config()
    assert _tables(migrated_db) == _tables_0001() | {"tg_user_registry"}
    assert len(_tables(migrated_db)) == 9

    command.downgrade(cfg, "0001_init")
    assert _tables(migrated_db) == _tables_0001()  # 0002 не ломает 0001

    command.downgrade(cfg, "base")
    assert _tables(migrated_db) == set()

    command.upgrade(cfg, "head")
    assert len(_tables(migrated_db)) == 9


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
