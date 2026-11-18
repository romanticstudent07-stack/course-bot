"""0020_bot_events_select: колоночный SELECT (id, pid, kind) на participant_events для app_bot (db-revive-0020).

Revision ID: 0020_bot_events_select
Revises: 0019_life_writeoffs
Create Date: 2026-11-18 12:00:00

Зачем: бот (bot-revive-1, команда /revive) считает точку отката :after — id последнего
revive_by_author или restart_paid этого pid. До 0020 у app_bot на participant_events есть
только INSERT (pid, kind, payload, actor, actor_role) и USAGE participant_events_id_seq (0018).

SQL, которому нужно право (под замком participant:pid, в одной транзакции с SELECT
life_writeoffs и INSERT revive_by_author — bot-revive-1 §7):

    SELECT coalesce(max(id), 0) FROM participant_events
    WHERE pid = %s AND kind IN ('revive_by_author', 'restart_paid')

Права только колоночные: payload, at, actor, actor_role для app_bot не открываются, табличного
SELECT нет; RETURNING в боте по-прежнему не используется. app_api и app_projector не меняются.
ALTER DEFAULT PRIVILEGES и PUBLIC не используются. Таблицы не добавляются.

Роль создаётся, если её нет (как в 0019). downgrade: REVOKE ровно выданного; роли не
удаляются, права 0018 (INSERT, USAGE) не трогаются. 0001–0019 не меняются.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0020_bot_events_select"
down_revision: str | None = "0019_life_writeoffs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES: tuple[str, ...] = ("app_bot",)

# (право, объект, роль); одна строка — одно колоночное право.
PRIVILEGES: tuple[tuple[str, str, str], ...] = (
    ("SELECT (id, pid, kind)", "TABLE participant_events", "app_bot"),
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
