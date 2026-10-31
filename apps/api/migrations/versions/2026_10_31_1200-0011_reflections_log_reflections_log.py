"""0011_reflections_log: таблица reflections_log, права app_api / app_bot (db-1).

Revision ID: 0011_reflections_log
Revises: 0010_access_grants
Create Date: 2026-10-31 12:00:00

Неизменяемый лог рефлексий дней 6 / 13-M / 13-P (03 §3.12; В1 = А, Автор 30.10): минимум
2 символа, смысл не оценивается, «как замеры»; при ревёрте поле снова обязательно, старый
текст остаётся в истории. Каждая сдача — новая строка, действующая — последняя по
created_at; UNIQUE нет (повтор гасит idempotency_keys), updated_at нет. Лимит 2000
символов (Ш-1): пост в тему «Рефлексии» с запасом влезает в 4096 символов Telegram;
422 REFLECTION_REQUIRED отдаёт API (api-refl-1), CHECK — страховка. ПДн, кроме текста
рефлексии, не хранятся. Таблиц после миграции — 17.

Права и SQL, который их требует (SQL — раздел 8 карточки db-1; код API — api-refl-1,
код бота — bot-group-1):

- app_api INSERT (pid, stage_no, module_no, day_no, day_started_at, body)
  + SELECT (id, pid, stage_no, module_no, day_no, day_started_at, body, created_at)
  + USAGE reflections_log_id_seq: сдача рефлексии:
      INSERT INTO reflections_log (pid, stage_no, module_no, day_no, day_started_at, body)
      VALUES (:pid, :s, :m, :d, :ds, :body) RETURNING id
  RETURNING требует SELECT (id), DEFAULT nextval — USAGE последовательности.
- app_bot SELECT (те же 8 колонок) на reflections_log: пост по reflection_id:
      SELECT pid, stage_no, module_no, day_no, body, created_at FROM reflections_log
      WHERE id = :reflection_id
- app_bot SELECT (short_no) на tg_user_registry (Ш-2): метка #NNNNNN в посте:
      SELECT tg_user_id, short_no FROM tg_user_registry
      WHERE pid = CAST(:pid AS uuid) AND tombstoned_at IS NULL
- UPDATE, DELETE, TRUNCATE на reflections_log не выданы никому; app_projector прав
  не получает. ALTER DEFAULT PRIVILEGES не используется.

Роли создаются, если их нет (как в 0010). downgrade: REVOKE SELECT (short_no) своей
строкой (колоночное право на другой таблице, как в 0009), затем DROP INDEX и DROP TABLE
(права на reflections_log и на последовательность уходят вместе с таблицей);
роли кластерные и не удаляются.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_reflections_log"
down_revision: str | None = "0010_access_grants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "reflections_log"
INDEX = "reflections_log_pid_day_idx"
ROLES: tuple[str, ...] = ("app_api", "app_bot")

SELECT_COLUMNS = (
    "SELECT (id, pid, stage_no, module_no, day_no, day_started_at, body, created_at)"
)

# (право, объект, роль); одна строка — одно (колоночное) право.
PRIVILEGES: tuple[tuple[str, str, str], ...] = (
    (
        "INSERT (pid, stage_no, module_no, day_no, day_started_at, body)",
        "TABLE reflections_log",
        "app_api",
    ),
    (SELECT_COLUMNS, "TABLE reflections_log", "app_api"),
    ("USAGE", "SEQUENCE reflections_log_id_seq", "app_api"),
    (SELECT_COLUMNS, "TABLE reflections_log", "app_bot"),
    ("SELECT (short_no)", "TABLE tg_user_registry", "app_bot"),
)

REVOKE_SHORT_NO = "REVOKE SELECT (short_no) ON TABLE tg_user_registry FROM app_bot"


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
        sa.Column("stage_no", sa.Integer(), nullable=False),
        sa.Column("module_no", sa.Integer(), nullable=False),
        sa.Column("day_no", sa.Integer(), nullable=False),
        sa.Column("day_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="reflections_log_pkey"),
        sa.ForeignKeyConstraint(
            ["pid"], ["tg_user_registry.pid"], name="reflections_log_pid_fkey"
        ),
        sa.CheckConstraint(
            "stage_no > 0 AND module_no > 0 AND day_no > 0",
            name="ck_reflections_log_position_positive",
        ),
        sa.CheckConstraint(
            "char_length(btrim(body)) >= 2 AND char_length(body) <= 2000",
            name="ck_reflections_log_body_len",
        ),
    )
    op.create_index(
        INDEX,
        TABLE,
        ["pid", "stage_no", "module_no", "day_no", "created_at"],
        unique=False,
    )
    for role in ROLES:
        _create_role_if_missing(role)
    for privilege, target, role in PRIVILEGES:
        op.execute(f"GRANT {privilege} ON {target} TO {role}")


def downgrade() -> None:
    op.execute(REVOKE_SHORT_NO)
    op.drop_index(INDEX, table_name=TABLE)
    op.drop_table(TABLE)
