"""tg_user_registry: реестр tg_user_id ↔ pid (Итерация 1b, SEAM-PATCH-1)

Revision ID: 0002_tg_user_registry
Revises: 0001_init
Create Date: 2026-09-24 12:00:00

Источники (docs/architecture/**, read-only):
  - normative/I1-wave-a.md → tg_user_id_pid_registry:
      table: tg_user_registry; columns: [tg_user_id, pid, created_via, created_at, tombstoned_at];
      autocreate_source: mini_app_only; tombstone_semantics (новая регистрация того же
      tg_user_id после erasure → новый pid, Р243);
  - normative/seam-patch-1-onboarding.md → SEAM1: единственная точка создания — first-launch Mini App;
  - normative/errata-unified.md → ADD3 INV-AGE-GATE-BEFORE-PID;
  - 06-participant-card.md §6.3: короткий номер «#000123», присваивается при регистрации
    (колонки short_no в И1 нет — docs/DEFECTS-FOUND.md, D-12);
  - build/db-tables-index.md: владелец Б4 (SEAM-1).

0001_init не меняется. participant_state (уже есть в 0001) здесь не трогается:
её пишет только проектор (E1/INV-1) — отдельный PR.

Роли/GRANT на tg_user_registry не заданы — в архитектуре их нет; блокер к проду (D-13).
Дата рождения НЕ хранится (решение Автора): проверка возраста — только в момент запроса.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0002_tg_user_registry"
down_revision: str | None = "0001_init"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "tg_user_registry"

DDL: tuple[str, ...] = (
    """
    CREATE TABLE tg_user_registry (
        pid           uuid PRIMARY KEY,
        tg_user_id    bigint NOT NULL,
        short_no      bigint GENERATED ALWAYS AS IDENTITY,
        created_via   text NOT NULL,
        created_at    timestamptz NOT NULL DEFAULT now(),
        tombstoned_at timestamptz,
        CONSTRAINT tg_user_registry_short_no_key UNIQUE (short_no),
        CONSTRAINT tg_user_registry_tg_user_id_positive CHECK (tg_user_id > 0),
        CONSTRAINT tg_user_registry_created_via_check
            CHECK (created_via IN ('mini_app_first_launch'))
    )
    """,
    # Один АКТИВНЫЙ pid на tg_user_id (идемпотентность first-launch и защита от гонки).
    # Tombstoned-строки в индекс не входят → после erasure новый pid (Р243).
    """
    CREATE UNIQUE INDEX tg_user_registry_active_tg_user_uidx
        ON tg_user_registry (tg_user_id) WHERE tombstoned_at IS NULL
    """,
)


def upgrade() -> None:
    for statement in DDL:
        op.execute(statement)


def downgrade() -> None:
    # Индекс и identity-последовательность удаляются вместе с таблицей.
    op.execute(f"DROP TABLE IF EXISTS {TABLE}")
