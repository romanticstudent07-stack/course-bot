"""text_registry: единый реестр текстов (Итерация 1d, Б9 / Б14)

Revision ID: 0003_text_registry
Revises: 0002_tg_user_registry
Create Date: 2026-09-30 12:00:00

Источники (docs/architecture/**, read-only):
  - build/build-order.md, Уровень 1, п.3: text_registry — пустая таблица + seed (И4);
  - build/config-schemas/text_registry.schema.json: key, tone, legal_status, text,
    plurals_ru, notes (копия схемы — apps/api/config/text_registry.schema.json);
  - build/db-tables-index.md: владелец Б9, durability Б14.

Шаблон ключа — шаблон СХЕМЫ (решение Автора, docs/DEFECTS-FOUND.md D-14); тот же,
что app.texts.KEY_PATTERN (tests/test_texts.py сверяет).

Данных миграция не вставляет: seed пишет загрузчик `python -m app.texts load`.
GRANT нет — это задача B-3 (D-13). 0001 и 0002 не меняются.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0003_text_registry"
down_revision: str | None = "0002_tg_user_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "text_registry"

DDL: tuple[str, ...] = (
    r"""
    CREATE TABLE text_registry (
        key              text PRIMARY KEY,
        tone             text NOT NULL,
        legal_status     text NOT NULL,
        text             text NOT NULL,
        plurals_ru       jsonb,
        notes            text,
        registry_version text NOT NULL,
        updated_at       timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT text_registry_key_format
            CHECK (key ~ '^(B2|B4|B5|B7|B9|B10|B14|B15|B16|legal)\.[a-z][a-z0-9_]*$'),
        CONSTRAINT text_registry_tone_check
            CHECK (tone IN ('soft', 'neutral', 'strict')),
        CONSTRAINT text_registry_legal_status_check
            CHECK (legal_status IN ('pre-legal-review', 'approved')),
        CONSTRAINT text_registry_text_length
            CHECK (char_length(text) BETWEEN 1 AND 4096)
    )
    """,
)


def upgrade() -> None:
    for statement in DDL:
        op.execute(statement)


def downgrade() -> None:
    op.execute(f"DROP TABLE IF EXISTS {TABLE}")
