"""0015_onboarding_form: таблица onboarding_form, права app_api (db-i3-3).

Revision ID: 0015_onboarding_form
Revises: 0014_measurements_log
Create Date: 2026-11-08 12:00:00

Анкета участника по Р-16 (имени в db-tables-index нет → onboarding_form, Ш-1): одна
строка на pid — пол (male / female, обязательно, А2) и код ответа «самочувствие»
(wellbeing_code, формат ^[a-z0-9_]{1,32}$, Ш-2; список кодов — в конфиге api-2,
заглушки). Исходная анкета заново не спрашивается (04 §4.8): повтор гасит
ON CONFLICT (pid) DO NOTHING, updated_at и UPDATE нет. Часовой пояс сюда не входит —
событие через проектор в participant_state.tz (api-2; E1, INV-1); вес — measurements_log
(0014). Город, ФИО, телефон, email не хранятся (Р-16). Таблиц после миграции — 19.

Права и SQL, который их требует (раздел 7 карточки db-i3-3; код — api-2):

- app_api INSERT (pid, gender, wellbeing_code) + SELECT (pid, gender, wellbeing_code,
  created_at):
      INSERT INTO onboarding_form (pid, gender, wellbeing_code)
      VALUES (:pid, :gender, :wb) ON CONFLICT (pid) DO NOTHING RETURNING pid
  повтор и чтение:
      SELECT gender, wellbeing_code, created_at FROM onboarding_form WHERE pid = :pid
  RETURNING требует SELECT (pid). Последовательности нет.
- app_bot и app_projector прав не получают (06 §6.4: пола и самочувствия в карточке нет).
- UPDATE, DELETE, TRUNCATE не выданы никому; ALTER DEFAULT PRIVILEGES и PUBLIC
  не используются.

Роль создаётся, если её нет (как в 0014). downgrade: DROP TABLE (права на
onboarding_form уходят вместе с таблицей; на чужих таблицах 0015 прав не выдаёт);
права 0013 и 0014 остаются; роли кластерные и не удаляются.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_onboarding_form"
down_revision: str | None = "0014_measurements_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "onboarding_form"
ROLES: tuple[str, ...] = ("app_api",)

# (имя, условие); имена и условия — раздел 8 карточки db-i3-3.
CHECKS: tuple[tuple[str, str], ...] = (
    ("ck_onboarding_form_gender", "gender IN ('male', 'female')"),
    ("ck_onboarding_form_wellbeing_code", "wellbeing_code ~ '^[a-z0-9_]{1,32}$'"),
)

API_INSERT_COLUMNS = "INSERT (pid, gender, wellbeing_code)"
API_SELECT_COLUMNS = "SELECT (pid, gender, wellbeing_code, created_at)"

# (право, объект, роль); одна строка — одно (колоночное) право.
PRIVILEGES: tuple[tuple[str, str, str], ...] = (
    (API_INSERT_COLUMNS, "TABLE onboarding_form", "app_api"),
    (API_SELECT_COLUMNS, "TABLE onboarding_form", "app_api"),
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
        sa.Column("pid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gender", sa.Text(), nullable=False),
        sa.Column("wellbeing_code", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("pid", name="onboarding_form_pkey"),
        sa.ForeignKeyConstraint(
            ["pid"], ["tg_user_registry.pid"], name="onboarding_form_pid_fkey"
        ),
        *(sa.CheckConstraint(condition, name=name) for name, condition in CHECKS),
    )
    for role in ROLES:
        _create_role_if_missing(role)
    for privilege, target, role in PRIVILEGES:
        op.execute(f"GRANT {privilege} ON {target} TO {role}")


def downgrade() -> None:
    op.drop_table(TABLE)
