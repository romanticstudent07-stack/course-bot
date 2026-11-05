"""0014_measurements_log: таблица measurements_log, права app_api / app_bot (db-i3-2).

Revision ID: 0014_measurements_log
Revises: 0013_bot_card
Create Date: 2026-11-07 12:00:00

Append-only журнал замеров (db-tables-index: measurements_log, Б5 / Б14): результат
Чек-Апа (05 §5.5: все 15 ответов по шкале 0–3, балл, зона, версия конфига) и стартовый
вес — отдельными строками по kind (checkup / body; Р-16, А1: из замеров только вес,
объёмов нет). Повод occasion — onboarding (stage_no NULL) или stage_end (stage_no >= 1,
Карта изменений). Каждый замер — новая строка, старая неприкосновенна (04 §4.8);
updated_at нет; повтор гасит UNIQUE (pid, client_op_id) через ON CONFLICT DO NOTHING.
Балл — сумма 15 ответов (CHECK ck_measurements_log_score_sum, 15 слагаемых выписаны:
подзапрос в CHECK нельзя). Связи балл↔зона в CHECK нет (Р-7): границы зон — в конфиге
с версией (Л2), их проверяет API (api-1). Город, ФИО, телефон, email и объёмы не
хранятся (Р-16, А1). Таблиц после миграции — 18.

Права и SQL, который их требует (раздел 7 карточки db-i3-2; код — api-1, api-2, bot-1):

- app_api INSERT (pid, kind, occasion, stage_no, checkup_answers, checkup_score,
  checkup_zone, checkup_config_version, weight_kg, client_op_id)
  + SELECT (id, pid, kind, occasion, stage_no, checkup_answers, checkup_score,
  checkup_zone, checkup_config_version, weight_kg, client_op_id, created_at)
  + USAGE measurements_log_id_seq: Чек-Ап и вес:
      INSERT INTO measurements_log (pid, kind, occasion, stage_no, checkup_answers,
      checkup_score, checkup_zone, checkup_config_version, client_op_id)
      VALUES (:pid, 'checkup', :occ, :stage, :answers, :score, :zone, :ver, :op)
      ON CONFLICT (pid, client_op_id) DO NOTHING RETURNING id
      INSERT INTO measurements_log (pid, kind, occasion, stage_no, weight_kg, client_op_id)
      VALUES (:pid, 'body', :occ, :stage, :w, :op)
      ON CONFLICT (pid, client_op_id) DO NOTHING RETURNING id
  повтор (RETURNING дал 0 строк):
      SELECT id, checkup_score, checkup_zone, created_at FROM measurements_log
      WHERE pid = :pid AND client_op_id = :op
  RETURNING требует SELECT (id), DEFAULT nextval — USAGE последовательности.
- app_bot SELECT (pid, kind, occasion, checkup_zone, weight_kg, created_at): карточка:
      SELECT kind, occasion, checkup_zone, weight_kg, created_at FROM measurements_log
      WHERE pid = :pid ORDER BY created_at
  id, stage_no, checkup_answers, checkup_score, checkup_config_version, client_op_id
  боту не выданы (балл участнику не показываем, Л2; stage_no карточке не нужен).
- UPDATE, DELETE, TRUNCATE не выданы никому; app_projector прав не получает;
  ALTER DEFAULT PRIVILEGES и PUBLIC не используются.

Роли создаются, если их нет (как в 0011). downgrade: DROP INDEX, затем DROP TABLE
(права на measurements_log и на последовательность уходят вместе с таблицей; на чужих
таблицах 0014 прав не выдаёт); права 0013 остаются; роли кластерные и не удаляются.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_measurements_log"
down_revision: str | None = "0013_bot_card"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "measurements_log"
INDEX = "measurements_log_pid_kind_idx"
ROLES: tuple[str, ...] = ("app_api", "app_bot")

# Сумма 15 ответов, каждое слагаемое выписано: подзапрос в CHECK нельзя.
SCORE_SUM = " + ".join(f"checkup_answers[{i}]" for i in range(1, 16))

# (имя, условие); имена — раздел 8 карточки db-i3-2.
CHECKS: tuple[tuple[str, str], ...] = (
    ("ck_measurements_log_kind", "kind IN ('checkup', 'body')"),
    ("ck_measurements_log_occasion", "occasion IN ('onboarding', 'stage_end')"),
    (
        "ck_measurements_log_stage",
        "(occasion = 'onboarding' AND stage_no IS NULL) "
        "OR (occasion = 'stage_end' AND stage_no >= 1)",
    ),
    (
        "ck_measurements_log_kind_checkup",
        "kind <> 'checkup' OR (checkup_answers IS NOT NULL AND checkup_score IS NOT NULL "
        "AND checkup_zone IS NOT NULL AND checkup_config_version IS NOT NULL "
        "AND weight_kg IS NULL)",
    ),
    (
        "ck_measurements_log_kind_body",
        "kind <> 'body' OR (weight_kg IS NOT NULL AND checkup_answers IS NULL "
        "AND checkup_score IS NULL AND checkup_zone IS NULL "
        "AND checkup_config_version IS NULL)",
    ),
    (
        "ck_measurements_log_answers",
        "checkup_answers IS NULL OR (array_ndims(checkup_answers) = 1 "
        "AND array_lower(checkup_answers, 1) = 1 AND cardinality(checkup_answers) = 15 "
        "AND array_position(checkup_answers, NULL) IS NULL "
        "AND 0 <= ALL (checkup_answers) AND 3 >= ALL (checkup_answers))",
    ),
    (
        "ck_measurements_log_score_sum",
        f"checkup_score IS NULL OR checkup_score = {SCORE_SUM}",
    ),
    (
        "ck_measurements_log_score_range",
        "checkup_score IS NULL OR checkup_score BETWEEN 0 AND 45",
    ),
    (
        "ck_measurements_log_zone",
        "checkup_zone IS NULL OR checkup_zone IN ('green', 'yellow', 'red')",
    ),
    (
        "ck_measurements_log_config_version",
        "checkup_config_version IS NULL "
        "OR char_length(btrim(checkup_config_version)) BETWEEN 1 AND 64",
    ),
    (
        "ck_measurements_log_weight",
        "weight_kg IS NULL OR weight_kg BETWEEN 30 AND 300",
    ),
    (
        "ck_measurements_log_client_op_id",
        "char_length(client_op_id) BETWEEN 1 AND 64",
    ),
)

API_INSERT_COLUMNS = (
    "INSERT (pid, kind, occasion, stage_no, checkup_answers, checkup_score, checkup_zone, "
    "checkup_config_version, weight_kg, client_op_id)"
)
API_SELECT_COLUMNS = (
    "SELECT (id, pid, kind, occasion, stage_no, checkup_answers, checkup_score, "
    "checkup_zone, checkup_config_version, weight_kg, client_op_id, created_at)"
)
BOT_SELECT_COLUMNS = "SELECT (pid, kind, occasion, checkup_zone, weight_kg, created_at)"

# (право, объект, роль); одна строка — одно (колоночное) право.
PRIVILEGES: tuple[tuple[str, str, str], ...] = (
    (API_INSERT_COLUMNS, "TABLE measurements_log", "app_api"),
    (API_SELECT_COLUMNS, "TABLE measurements_log", "app_api"),
    ("USAGE", "SEQUENCE measurements_log_id_seq", "app_api"),
    (BOT_SELECT_COLUMNS, "TABLE measurements_log", "app_bot"),
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
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("occasion", sa.Text(), nullable=False),
        sa.Column("stage_no", sa.SmallInteger(), nullable=True),
        sa.Column("checkup_answers", postgresql.ARRAY(sa.SmallInteger()), nullable=True),
        sa.Column("checkup_score", sa.SmallInteger(), nullable=True),
        sa.Column("checkup_zone", sa.Text(), nullable=True),
        sa.Column("checkup_config_version", sa.Text(), nullable=True),
        sa.Column("weight_kg", sa.Numeric(5, 1), nullable=True),
        sa.Column("client_op_id", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="measurements_log_pkey"),
        sa.ForeignKeyConstraint(
            ["pid"], ["tg_user_registry.pid"], name="measurements_log_pid_fkey"
        ),
        sa.UniqueConstraint(
            "pid", "client_op_id", name="measurements_log_pid_client_op_id_key"
        ),
        *(sa.CheckConstraint(condition, name=name) for name, condition in CHECKS),
    )
    op.create_index(INDEX, TABLE, ["pid", "kind", "created_at"], unique=False)
    for role in ROLES:
        _create_role_if_missing(role)
    for privilege, target, role in PRIVILEGES:
        op.execute(f"GRANT {privilege} ON {target} TO {role}")


def downgrade() -> None:
    op.drop_index(INDEX, table_name=TABLE)
    op.drop_table(TABLE)
