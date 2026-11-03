"""0012_outbox_api: права app_api на INSERT в outbox (db-2).

Revision ID: 0012_outbox_api
Revises: 0011_reflections_log
Create Date: 2026-11-03 12:00:00

Решение Автора 03.11 (вариант А): строку outbox reflection_submitted пишет API (роль
app_api) в одной транзакции с INSERT в reflections_log. Новых таблиц нет, их 17; таблиц,
колонок, индексов и ограничений миграция не меняет — только GRANT.

Контракт api-refl-1, раздел 7, Т7 — INSERT без RETURNING, tx_id = pg_current_xact_id():

    INSERT INTO outbox (aggregate_id, event_type, payload, tx_id)
    VALUES (:pid_text, 'reflection_submitted', CAST(:payload AS jsonb), pg_current_xact_id())

- app_api INSERT (aggregate_id, event_type, payload, tx_id) на outbox + USAGE
  outbox_id_seq — один в один как у app_projector в 0009 (В14): DEFAULT nextval требует
  USAGE последовательности.
- SELECT на outbox роли app_api не выдан, поэтому RETURNING запрещён; sent_at ставит
  только app_bot (0009). UPDATE, DELETE, TRUNCATE на outbox и любые права на outbox_dlq
  роль app_api не получает.
- ALTER DEFAULT PRIVILEGES не используется; через группу всех ролей права не выдаются.

Роль создаётся, если её нет (как в 0010 и 0011): роль кластерная, повторный прогон
не должен падать. downgrade снимает оба права (колоночное — своей строкой: табличный
REVOKE колоночное право не снимает); роль не удаляется.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0012_outbox_api"
down_revision: str | None = "0011_reflections_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES: tuple[str, ...] = ("app_api",)

# (право, объект, роль); одна строка — одно (колоночное) право.
PRIVILEGES: tuple[tuple[str, str, str], ...] = (
    ("INSERT (aggregate_id, event_type, payload, tx_id)", "TABLE outbox", "app_api"),
    ("USAGE", "SEQUENCE outbox_id_seq", "app_api"),
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
    for role in ROLES:
        _create_role_if_missing(role)
    for privilege, target, role in PRIVILEGES:
        op.execute(f"GRANT {privilege} ON {target} TO {role}")


def downgrade() -> None:
    for privilege, target, role in reversed(PRIVILEGES):
        op.execute(f"REVOKE {privilege} ON {target} FROM {role}")
