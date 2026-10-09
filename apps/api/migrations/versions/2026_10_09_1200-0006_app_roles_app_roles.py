"""app_roles: роли app_api / app_projector и минимальные GRANT (B-3a-1, D-13)

Revision ID: 0006_app_roles
Revises: 0005_participant_events
Create Date: 2026-10-09 12:00:00

Роли NOLOGIN app_api (API Mini App) и app_projector (проектор Б10). Права выданы
по списку SQL, который реально выполняет код 90f7df2 (карточка B-3a-1, раздел 4):

app_api:
  - tg_user_registry: SELECT, INSERT (INSERT ON CONFLICT DO NOTHING RETURNING pid, short_no;
    short_no — IDENTITY, права на последовательность не нужны);
    UPDATE (created_via) — только ради SELECT FOR UPDATE при повторном first-launch
    (блокировка строки требует UPDATE хотя бы на одну колонку);
  - text_registry: SELECT;
  - consent_events: SELECT, INSERT + USAGE consent_events_id_seq (bigserial, RETURNING id);
  - participant_events: INSERT + SELECT (id) (SQLAlchemy добавляет RETURNING id)
    + USAGE participant_events_id_seq; UPDATE/DELETE нет — журнал append-only (0005);
  - участник participant_state_reader (SELECT participant_state); писать туда не может (E1, INV-1).
app_projector:
  - participant_events: SELECT;
  - participant_state_checkpoints: SELECT, INSERT, UPDATE (last_event_id, at)
    (INSERT ON CONFLICT DO UPDATE SET last_event_id = GREATEST, at);
  - участник participant_state_projector (INSERT, UPDATE) и participant_state_reader
    (SELECT для ON CONFLICT WHERE и RETURNING pid).
pg_advisory_lock, CONNECT к БД и USAGE схемы public есть у PUBLIC; FK проверяет владелец таблицы.

Почему UPDATE (created_via) безопасен: CHECK на created_via разрешает одно значение
('mini_app_first_launch'), поэтому изменить данные этим правом API не может; pid, short_no,
tg_user_id, tombstoned_at, created_at обновлять нельзя. Триггеров на tg_user_registry нет
(0001–0005 их не создают). УСЛОВИЕ: если CHECK created_via расширят — это право
пересмотреть в той же миграции.

Правило (STATE): каждая следующая миграция с новой таблицей выдаёт GRANT ролям
app_api / app_projector в той же миграции. ALTER DEFAULT PRIVILEGES не используется.

LOGIN-пользователей и паролей здесь нет: их создаёт серверный чат вручную (B-3a-2, раздел 10).
downgrade отзывает всё выданное и членство в ролях; роли НЕ удаляются (кластерные, как в 0001).
0001–0005 не меняются.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0006_app_roles"
down_revision: str | None = "0005_participant_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES: tuple[str, ...] = ("app_api", "app_projector")

# (право, объект, роль) — GRANT в upgrade, REVOKE в обратном порядке в downgrade.
# Колоночные права отзываются отдельно: табличный REVOKE их не снимает.
PRIVILEGES: tuple[tuple[str, str, str], ...] = (
    ("SELECT, INSERT", "TABLE tg_user_registry", "app_api"),
    ("UPDATE (created_via)", "TABLE tg_user_registry", "app_api"),
    ("SELECT", "TABLE text_registry", "app_api"),
    ("SELECT, INSERT", "TABLE consent_events", "app_api"),
    ("INSERT", "TABLE participant_events", "app_api"),
    ("SELECT (id)", "TABLE participant_events", "app_api"),
    ("USAGE", "SEQUENCE consent_events_id_seq, participant_events_id_seq", "app_api"),
    ("SELECT", "TABLE participant_events", "app_projector"),
    ("SELECT, INSERT", "TABLE participant_state_checkpoints", "app_projector"),
    ("UPDATE (last_event_id, at)", "TABLE participant_state_checkpoints", "app_projector"),
)

# (роль 0001, кому) — членство в ролях participant_state (E1).
MEMBERSHIPS: tuple[tuple[str, str], ...] = (
    ("participant_state_reader", "app_api"),
    ("participant_state_projector", "app_projector"),
    ("participant_state_reader", "app_projector"),
)


def _create_role_if_missing(role: str) -> str:
    # Как в 0001: роль — объект кластера, повторный прогон не должен падать. NOLOGIN по умолчанию.
    return f"""
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = '{role}') THEN
            CREATE ROLE {role};
        END IF;
    END

    $$
    """


def upgrade() -> None:
    for role in ROLES:
        op.execute(_create_role_if_missing(role))
    for privilege, target, role in PRIVILEGES:
        op.execute(f"GRANT {privilege} ON {target} TO {role}")
    for granted, member in MEMBERSHIPS:
        op.execute(f"GRANT {granted} TO {member}")


def downgrade() -> None:
    for granted, member in reversed(MEMBERSHIPS):
        op.execute(f"REVOKE {granted} FROM {member}")
    for privilege, target, role in reversed(PRIVILEGES):
        op.execute(f"REVOKE {privilege} ON {target} FROM {role}")
    # Роли НЕ удаляются: они общие для кластера (как в 0001). DROP ROLE — ручная операция Автора.
