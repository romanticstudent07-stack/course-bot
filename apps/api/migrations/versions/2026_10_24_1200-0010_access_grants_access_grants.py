"""0010_access_grants: таблица access_grants, права app_bot / app_api, backfill (db-access-1).

Revision ID: 0010_access_grants
Revises: 0009_app_bot
Create Date: 2026-10-24 12:00:00

Р-2 (STATE, R-2026-10-1): Start → промокод → админ-тема → «Выдать / Запретить» → онбординг.
Флажок доступа — в НОВОЙ таблице по tg_user_id (tg_user_registry не трогаем). Статусы
pending / granted / denied, счётчик отказов deny_count и пауза locked_until. Кодовое слово,
имя и username в БД НЕ хранятся (минимизация ПДн). Таблиц после миграции — 16.

admin_message_id — id сообщения ПОСЛЕДНЕЙ заявки в админ-теме; после решения не обнуляется
(по reply на него /access_grant находит пользователя), новая заявка его перезаписывает.
updated_at пишет код (триггера нет).

Права и SQL, который их требует (SQL — по разделам 7 и 10 карточки db-access-1; точные
запросы бота — карточка bot-access-1, разделы 8–9):

- app_bot SELECT (tg_user_id, status, deny_count, locked_until, admin_message_id,
  requested_at, decided_at, decided_by): чтение состояния и поиск по reply:
      SELECT status, deny_count, locked_until, admin_message_id FROM access_grants
      WHERE tg_user_id = :id FOR UPDATE
  FOR UPDATE требует UPDATE хотя бы на одну колонку — он есть (ниже).
- app_bot INSERT (tg_user_id, status, deny_count, locked_until, admin_message_id,
  requested_at, created_via): новая заявка:
      INSERT INTO access_grants (tg_user_id, status, admin_message_id, requested_at,
                                 deny_count, locked_until, created_via)
      VALUES (:id, 'pending', :mid, now(), 0, NULL, 'bot_promo')
      ON CONFLICT (tg_user_id) DO UPDATE SET status = EXCLUDED.status,
          admin_message_id = EXCLUDED.admin_message_id, requested_at = EXCLUDED.requested_at,
          deny_count = EXCLUDED.deny_count, locked_until = EXCLUDED.locked_until,
          updated_at = now()
  ON CONFLICT DO UPDATE требует UPDATE на изменяемые колонки — они есть.
- app_bot UPDATE (status, deny_count, locked_until, admin_message_id, requested_at,
  decided_at, decided_by, updated_at): решение админа (условный UPDATE):
      UPDATE access_grants SET status = 'denied', deny_count = deny_count + 1,
          decided_at = now(), decided_by = :admin, updated_at = now()
      WHERE tg_user_id = :id AND status = 'pending' AND admin_message_id = :mid
- pg_advisory_xact_lock — прав на таблицу не требует.
- app_api SELECT (tg_user_id, status): проверка «доступ выдан» перед онбордингом:
      SELECT status FROM access_grants WHERE tg_user_id = :id
- DELETE и TRUNCATE не выданы никому; app_projector прав не получает.

Backfill (после CREATE и GRANT): активным строкам tg_user_registry — granted,
created_via = backfill_0010. Роли создаются, если их нет (как в 0009); downgrade —
DROP TABLE (права уходят вместе с таблицей); роли кластерные и не удаляются.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_access_grants"
down_revision: str | None = "0009_app_bot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "access_grants"
ROLES: tuple[str, ...] = ("app_bot", "app_api")

# (право, объект, роль); одна строка — одно (колоночное) право.
PRIVILEGES: tuple[tuple[str, str, str], ...] = (
    (
        "SELECT (tg_user_id, status, deny_count, locked_until, admin_message_id, "
        "requested_at, decided_at, decided_by)",
        "TABLE access_grants",
        "app_bot",
    ),
    (
        "INSERT (tg_user_id, status, deny_count, locked_until, admin_message_id, "
        "requested_at, created_via)",
        "TABLE access_grants",
        "app_bot",
    ),
    (
        "UPDATE (status, deny_count, locked_until, admin_message_id, requested_at, "
        "decided_at, decided_by, updated_at)",
        "TABLE access_grants",
        "app_bot",
    ),
    ("SELECT (tg_user_id, status)", "TABLE access_grants", "app_api"),
)

BACKFILL_SQL = (
    "INSERT INTO access_grants (tg_user_id, status, created_via, decided_at) "
    "SELECT tg_user_id, 'granted', 'backfill_0010', now() FROM tg_user_registry "
    "WHERE tombstoned_at IS NULL "
    "ON CONFLICT (tg_user_id) DO NOTHING"
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
        sa.Column("tg_user_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("deny_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("admin_message_id", sa.BigInteger(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.BigInteger(), nullable=True),
        sa.Column("created_via", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("tg_user_id", name="access_grants_pkey"),
        sa.CheckConstraint("tg_user_id > 0", name="ck_access_grants_tg_user_id_positive"),
        sa.CheckConstraint(
            "status IN ('pending', 'granted', 'denied')", name="ck_access_grants_status"
        ),
        sa.CheckConstraint("deny_count >= 0", name="ck_access_grants_deny_count_nonneg"),
        sa.CheckConstraint(
            "created_via IN ('bot_promo', 'backfill_0010')",
            name="ck_access_grants_created_via",
        ),
        sa.CheckConstraint(
            "status <> 'pending' OR admin_message_id IS NOT NULL",
            name="ck_access_grants_pending_msg",
        ),
    )
    op.create_index(
        "uq_access_grants_admin_message_id",
        TABLE,
        ["admin_message_id"],
        unique=True,
        postgresql_where=sa.text("admin_message_id IS NOT NULL"),
    )
    for role in ROLES:
        _create_role_if_missing(role)
    for privilege, target, role in PRIVILEGES:
        op.execute(f"GRANT {privilege} ON {target} TO {role}")
    op.execute(BACKFILL_SQL)


def downgrade() -> None:
    op.drop_index("uq_access_grants_admin_message_id", table_name=TABLE)
    op.drop_table(TABLE)
