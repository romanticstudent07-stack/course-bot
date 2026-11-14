"""0017_support_questions: таблица support_questions, права app_api / app_bot (db-sup-1).

Revision ID: 0017_support_questions
Revises: 0015_onboarding_form
Create Date: 2026-11-14 12:00:00

Вопросы в поддержку по Р-19: тема кнопкой → вопрос → пост в тему группы этой темы.
Текст вопроса хранится здесь, в outbox идёт только id (DLQ копирует payload целиком).
topic_code — код темы: s1…s7 и other (8 тем, Р-19); номер темы группы — в .env бота,
в БД его нет. Повтор гасит UNIQUE (pid, client_op_id) и ON CONFLICT DO NOTHING
(idempotency_keys не трогаем); частота — max(created_at) по pid под замком участника
(индекс support_questions_pid_created_idx). Длина текста 2…2000 (после btrim — не короче 2),
как у reflections_log; client_op_id 1…64, как у measurements_log. updated_at нет.
Номер 0016 зарезервирован за журналом списаний. Таблиц после миграции — 20.

Права и SQL, который их требует (раздел 7 карточки db-sup-1; код API — api-sup-1,
код бота — bot-sup-1):

- app_api INSERT (pid, topic_code, body, client_op_id) + SELECT (id, pid, client_op_id,
  created_at) + USAGE support_questions_id_seq: запись вопроса:
      INSERT INTO support_questions (pid, topic_code, body, client_op_id)
      VALUES (:pid, :topic, :body, :op) ON CONFLICT (pid, client_op_id) DO NOTHING RETURNING id
  частота:
      SELECT max(created_at) FROM support_questions WHERE pid = :pid
  RETURNING требует SELECT (id), ON CONFLICT — SELECT (pid, client_op_id),
  DEFAULT nextval — USAGE последовательности. Текст вопроса и тему app_api не читает.
- app_bot SELECT (id, pid, topic_code, body, created_at): пост по question_id:
      SELECT pid, topic_code, body, created_at FROM support_questions WHERE id = :question_id
- app_projector прав не получает. UPDATE, DELETE, TRUNCATE не выданы никому;
  ALTER DEFAULT PRIVILEGES и PUBLIC не используются.

Роли создаются, если их нет (как в 0015). downgrade: DROP INDEX, затем DROP TABLE
(права на support_questions и последовательность уходят вместе с таблицей; на чужих
таблицах 0017 прав не выдаёт); роли кластерные и не удаляются.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_support_questions"
down_revision: str | None = "0015_onboarding_form"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "support_questions"
INDEX = "support_questions_pid_created_idx"
ROLES: tuple[str, ...] = ("app_api", "app_bot")

# (имя, условие); имена и условия — раздел 8 карточки db-sup-1; у каждого явный IS NOT NULL.
CHECKS: tuple[tuple[str, str], ...] = (
    (
        "ck_support_questions_topic_code",
        "topic_code IS NOT NULL AND "
        "topic_code IN ('s1', 's2', 's3', 's4', 's5', 's6', 's7', 'other')",
    ),
    (
        "ck_support_questions_body_len",
        "body IS NOT NULL AND char_length(btrim(body)) >= 2 AND char_length(body) <= 2000",
    ),
    (
        "ck_support_questions_client_op_id",
        "client_op_id IS NOT NULL AND char_length(client_op_id) BETWEEN 1 AND 64",
    ),
)

# (право, объект, роль); одна строка — одно (колоночное) право.
PRIVILEGES: tuple[tuple[str, str, str], ...] = (
    ("INSERT (pid, topic_code, body, client_op_id)", "TABLE support_questions", "app_api"),
    ("SELECT (id, pid, client_op_id, created_at)", "TABLE support_questions", "app_api"),
    ("USAGE", "SEQUENCE support_questions_id_seq", "app_api"),
    ("SELECT (id, pid, topic_code, body, created_at)", "TABLE support_questions", "app_bot"),
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
        sa.Column("topic_code", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("client_op_id", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="support_questions_pkey"),
        sa.ForeignKeyConstraint(
            ["pid"], ["tg_user_registry.pid"], name="support_questions_pid_fkey"
        ),
        sa.UniqueConstraint(
            "pid", "client_op_id", name="support_questions_pid_client_op_id_key"
        ),
        *(sa.CheckConstraint(condition, name=name) for name, condition in CHECKS),
    )
    op.create_index(INDEX, TABLE, ["pid", "created_at"], unique=False)
    for role in ROLES:
        _create_role_if_missing(role)
    for privilege, target, role in PRIVILEGES:
        op.execute(f"GRANT {privilege} ON {target} TO {role}")


def downgrade() -> None:
    op.drop_index(INDEX, table_name=TABLE)
    op.drop_table(TABLE)
