"""0022_security_events: таблица security_events и права ролей (pause-api-a1).

Revision ID: 0022_security_events
Revises: 0021_bot_pauses_select
Create Date: 2026-11-22 12:00:00

R-2026-11-21: событие client_op_id_conflict пишется долговечной записью в отдельную таблицу,
в отдельной транзакции (app.security_events.record_security_event), чтобы откат транзакции
запроса перед 409 запись не стирал. privacy_audit_log для этого не используется.
pid без FK: стирание участника не упирается в ограничение.

Права (одна строка — одно право, выдаются одним циклом):
- app_api: INSERT (event_type, pid, op_kind, client_op_id) + USAGE security_events_id_seq;
  без SELECT, поэтому без RETURNING:
      INSERT INTO security_events (event_type, pid, op_kind, client_op_id)
      VALUES (:event_type, :pid, :op_kind, :client_op_id)
- audit_reader: SELECT security_events.
UPDATE, DELETE и TRUNCATE не выданы никому; права по умолчанию и общая роль не используются.
Срок хранения и очистка — не здесь. Роли создаются, если их нет (как в 0018).
downgrade: DROP индекса, DROP TABLE (права уходят с таблицей); роли не удаляются.
Таблиц после миграции — 24.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022_security_events"
down_revision: str | None = "0021_bot_pauses_select"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "security_events"
INDEX = "security_events_created_at_idx"
ROLES: tuple[str, ...] = ("app_api", "audit_reader")

# (имя, условие); раздел 8 карточки pause-api-a1; NULL обработан явно.
CHECKS: tuple[tuple[str, str], ...] = (
    (
        "ck_security_events_event_type",
        "event_type IS NOT NULL AND event_type IN ('client_op_id_conflict')",
    ),
    (
        "ck_security_events_op_kind",
        "op_kind IS NOT NULL AND char_length(op_kind) BETWEEN 1 AND 64",
    ),
    (
        "ck_security_events_client_op_id",
        "client_op_id IS NOT NULL AND char_length(client_op_id) BETWEEN 1 AND 64",
    ),
)

# (право, объект, роль); одна строка — одно (колоночное) право.
PRIVILEGES: tuple[tuple[str, str, str], ...] = (
    ("INSERT (event_type, pid, op_kind, client_op_id)", "TABLE security_events", "app_api"),
    ("USAGE", "SEQUENCE security_events_id_seq", "app_api"),
    ("SELECT", "TABLE security_events", "audit_reader"),
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
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("pid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("op_kind", sa.Text(), nullable=False),
        sa.Column("client_op_id", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="security_events_pkey"),
        *(sa.CheckConstraint(condition, name=name) for name, condition in CHECKS),
    )
    op.create_index(INDEX, TABLE, ["created_at"], unique=False)
    for role in ROLES:
        _create_role_if_missing(role)
    for privilege, target, role in PRIVILEGES:
        op.execute(f"GRANT {privilege} ON {target} TO {role}")


def downgrade() -> None:
    op.drop_index(INDEX, table_name=TABLE)
    op.drop_table(TABLE)
