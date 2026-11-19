"""0021_bot_pauses_select: SELECT строк participant_pauses и INSERT (ttl) idempotency_keys для app_bot (db-pause-0021).

Revision ID: 0021_bot_pauses_select
Revises: 0020_bot_events_select
Create Date: 2026-11-19 12:00:00

Зачем: бот (bot-pause-1) видит заявку паузы участника и её статус — выкладывает карточку заявки
Автору, перед решением проверяет status = 'requested' AND now() < start_at (api-pause-1a §5),
уведомляет участника о смене статуса. Ключи бота пишутся с ttl interval '30 days' вместо
DEFAULT 1 ч (0007).

Выдано app_bot (только колоночные права):
  - participant_pauses: SELECT (id, pid, kind, status, start_at, planned_end_at, created_at);
  - idempotency_keys: INSERT (ttl).
SELECT (key, result_ref) и INSERT (key, kind, result_ref) на idempotency_keys у app_bot уже есть
(0018) и здесь не выдаются.

Не выдано: запись в participant_pauses (INSERT, UPDATE, DELETE, TRUNCATE); pause_budgets целиком;
колонки client_op_id, ended_at, stage_no, restart_no; последовательность participant_pauses_id_seq;
UPDATE на idempotency_keys. Фраза docstring 0018 «app_bot прав на participant_pauses не получает»
для SELECT перечисленных колонок больше не верна; 0018 не меняется.

RETURNING в боте по-прежнему не используется. app_api и app_projector не меняются.
ALTER DEFAULT PRIVILEGES и PUBLIC не используются. Таблицы не добавляются.

Роль создаётся, если её нет (как в 0020). downgrade: REVOKE ровно выданного; роли не удаляются,
права 0018 и 0020 не трогаются. 0001–0020 не меняются.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0021_bot_pauses_select"
down_revision: str | None = "0020_bot_events_select"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES: tuple[str, ...] = ("app_bot",)

# (право, объект, роль); одна строка — одно колоночное право.
PRIVILEGES: tuple[tuple[str, str, str], ...] = (
    (
        "SELECT (id, pid, kind, status, start_at, planned_end_at, created_at)",
        "TABLE participant_pauses",
        "app_bot",
    ),
    ("INSERT (ttl)", "TABLE idempotency_keys", "app_bot"),
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
