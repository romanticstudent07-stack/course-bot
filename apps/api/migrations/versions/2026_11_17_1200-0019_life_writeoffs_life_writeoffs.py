"""0019_life_writeoffs: таблица life_writeoffs, колоночные права app_projector / app_bot (db-pause-2).

Revision ID: 0019_life_writeoffs
Revises: 0018_pauses
Create Date: 2026-11-17 12:00:00

Журнал списаний жизней (T1b): одна строка на событие списания life_ops (delta −1) с позицией
дня (stage_no, module_no, day_no). Пишет проектор при списании (T6a); читает бот для
revive_by_author (T7): возврат = списания после точки отката (02 §2.6, R-2026-11-15 А2).
/life −N в журнал не пишется. event_id — FK на participant_events(id), UNIQUE: повтор гасит
ON CONFLICT (event_id) DO NOTHING. Индекс life_writeoffs_pid_event_idx (pid, event_id), не
UNIQUE, — для выборки T7. Бэкфилла нет: списания до 0019 в журнал не попадают (по ним revive
даёт только +1). Таблиц после миграции — 23.

Права и SQL, который их требует (раздел 7 карточки db-pause-2; код — T6a, T7):

- app_projector (T6a) INSERT (pid, event_id, stage_no, module_no, day_no) + SELECT (event_id)
  + USAGE life_writeoffs_id_seq: в транзакции события списания, после INSERT события:
      INSERT INTO life_writeoffs (pid, event_id, stage_no, module_no, day_no)
      VALUES (:pid, :event_id, :s, :m, :d) ON CONFLICT (event_id) DO NOTHING
  ON CONFLICT требует SELECT (event_id), DEFAULT nextval — USAGE последовательности.
- app_bot (T7) SELECT (pid, event_id, stage_no, module_no, day_no), под замком участника:
      SELECT event_id, stage_no, module_no, day_no FROM life_writeoffs
      WHERE pid = :pid AND event_id > :after ORDER BY event_id
  :after — id последнего revive или рестарта (правило — карточка T7).
- app_api прав не получает. UPDATE, DELETE, TRUNCATE не выданы никому;
  ALTER DEFAULT PRIVILEGES и PUBLIC не используются. Все права выдаются одним циклом.

Роли создаются, если их нет (как в 0017). downgrade: DROP INDEX, затем DROP TABLE
(права на life_writeoffs и последовательность уходят вместе с таблицей; на чужих
таблицах 0019 прав не выдаёт); роли кластерные и не удаляются. 0001–0018 не меняются.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_life_writeoffs"
down_revision: str | None = "0018_pauses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "life_writeoffs"
INDEX = "life_writeoffs_pid_event_idx"
ROLES: tuple[str, ...] = ("app_bot", "app_projector")

# (имя, условие); имена и условия — раздел 8 карточки db-pause-2; у каждого явный IS NOT NULL.
CHECKS: tuple[tuple[str, str], ...] = (
    ("ck_life_writeoffs_stage_no", "stage_no IS NOT NULL AND stage_no >= 1"),
    ("ck_life_writeoffs_module_no", "module_no IS NOT NULL AND module_no >= 1"),
    ("ck_life_writeoffs_day_no", "day_no IS NOT NULL AND day_no >= 1"),
)

# (право, объект, роль); одна строка — одно (колоночное) право.
PRIVILEGES: tuple[tuple[str, str, str], ...] = (
    (
        "INSERT (pid, event_id, stage_no, module_no, day_no)",
        "TABLE life_writeoffs",
        "app_projector",
    ),
    ("SELECT (event_id)", "TABLE life_writeoffs", "app_projector"),
    ("USAGE", "SEQUENCE life_writeoffs_id_seq", "app_projector"),
    (
        "SELECT (pid, event_id, stage_no, module_no, day_no)",
        "TABLE life_writeoffs",
        "app_bot",
    ),
)


def _create_role_if_missing(role: str) -> None:
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles "
        f"WHERE rolname = '{role}') "
        f"THEN CREATE ROLE {role}; "
        "END IF; END $$"
    )


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("pid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("stage_no", sa.SmallInteger(), nullable=False),
        sa.Column("module_no", sa.SmallInteger(), nullable=False),
        sa.Column("day_no", sa.SmallInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="life_writeoffs_pkey"),
        sa.ForeignKeyConstraint(
            ["pid"], ["tg_user_registry.pid"], name="life_writeoffs_pid_fkey"
        ),
        sa.ForeignKeyConstraint(
            ["event_id"], ["participant_events.id"], name="life_writeoffs_event_id_fkey"
        ),
        sa.UniqueConstraint("event_id", name="life_writeoffs_event_id_key"),
        *(sa.CheckConstraint(condition, name=name) for name, condition in CHECKS),
    )
    op.create_index(INDEX, TABLE, ["pid", "event_id"], unique=False)
    for role in ROLES:
        _create_role_if_missing(role)
    for privilege, target, role in PRIVILEGES:
        op.execute(f"GRANT {privilege} ON {target} TO {role}")


def downgrade() -> None:
    op.drop_index(INDEX, table_name=TABLE)
    op.drop_table(TABLE)
