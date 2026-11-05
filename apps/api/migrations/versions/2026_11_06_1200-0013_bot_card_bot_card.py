"""0013_bot_card: права app_bot для /card — аудит и чтение карточки (db-i3-1).

Revision ID: 0013_bot_card
Revises: 0012_outbox_api
Create Date: 2026-11-06 12:00:00

Л6: бот сам читает БД для /card; карточка формируется свежей из БД в момент запроса
(06 §6.1). До отправки карточки бот пишет строку аудита в privacy_audit_log
(06 fail-safe, 152-ФЗ). Новых таблиц нет, их 17; таблиц, колонок, индексов и ограничений
миграция не меняет — только колоночные GRANT роли app_bot. Права и SQL, который их требует
(контракт bot-1, карточка db-i3-1, раздел 7):

- app_bot INSERT (actor_id, actor_role, action, participant_id) на privacy_audit_log
  + USAGE privacy_audit_log_id_seq: аудит до отправки карточки, без RETURNING и без
  metadata (Ш-3); DEFAULT nextval требует USAGE последовательности:
      INSERT INTO privacy_audit_log (actor_id, actor_role, action, participant_id)
      VALUES (:actor_tg_id_text, 'owner', 'view', :pid)
  SELECT на privacy_audit_log не выдан (читает только audit_reader), поэтому RETURNING
  запрещён; id, occurred_at, metadata app_bot не пишет; UPDATE, DELETE, TRUNCATE нет.
- app_bot SELECT (created_at) на tg_user_registry: дата регистрации (06 §6.4). Вместе
  с SELECT (pid, tg_user_id, tombstoned_at) из 0009 и SELECT (short_no) из 0011:
      SELECT pid, tg_user_id, created_at FROM tg_user_registry
      WHERE short_no = :n AND tombstoned_at IS NULL
      SELECT pid, short_no, created_at FROM tg_user_registry
      WHERE tg_user_id = :tg AND tombstoned_at IS NULL
  created_via не выдан.
- app_bot SELECT (pid, lifecycle_phase, status_flags, stage_no, module_no, day_no, lives,
  tz) на participant_state: позиция, статус, жизни, часовой пояс (06 §6.4 после Р-16,
  Р-15); pid нужен для WHERE:
      SELECT lifecycle_phase, status_flags, stage_no, module_no, day_no, lives, tz
      FROM participant_state WHERE pid = :pid
  author_pause_reason, updated_at, projector_version, last_seen_publish_epoch,
  day_started_at, missed_streak и любая запись не выданы. Нет строки — бот показывает
  «нет данных» (06 fail-safe).
- Членства app_bot в группе чтения participant_state нет (это SELECT на всю таблицу) —
  только колоночные GRANT. ALTER DEFAULT PRIVILEGES не используется; через группу всех
  ролей права не выдаются.

Роль создаётся, если её нет (как в 0012): роль кластерная, повторный прогон не должен
падать. downgrade снимает каждое право в обратном порядке своей строкой (табличный
REVOKE колоночное право не снимает); права 0009 и 0011 остаются; роль не удаляется.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0013_bot_card"
down_revision: str | None = "0012_outbox_api"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES: tuple[str, ...] = ("app_bot",)

# (право, объект, роль); одна строка — одно (колоночное) право.
PRIVILEGES: tuple[tuple[str, str, str], ...] = (
    (
        "INSERT (actor_id, actor_role, action, participant_id)",
        "TABLE privacy_audit_log",
        "app_bot",
    ),
    ("USAGE", "SEQUENCE privacy_audit_log_id_seq", "app_bot"),
    ("SELECT (created_at)", "TABLE tg_user_registry", "app_bot"),
    (
        "SELECT (pid, lifecycle_phase, status_flags, stage_no, module_no, day_no, lives, tz)",
        "TABLE participant_state",
        "app_bot",
    ),
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
