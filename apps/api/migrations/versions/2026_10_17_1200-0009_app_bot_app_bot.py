"""0009_app_bot: роль app_bot и права доставки пушей из outbox (iter2-db-3).

Revision ID: 0009_app_bot
Revises: 0008_day_marks
Create Date: 2026-10-17 12:00:00

Схема доставки (В4 = В): «часы» в проекторе (app_projector) пишут событие и строку outbox
одной транзакцией; бот (app_bot) берёт строку, шлёт в Telegram, ставит sent_at; сбой —
строка в outbox_dlq. Новых таблиц нет (их 15). Права и SQL, который их требует:

- app_bot SELECT (id, aggregate_id, event_type, payload, created_at, sent_at) на outbox
  + UPDATE (sent_at): забор пачки и отметка «обработано»:
      SELECT id, aggregate_id, event_type, payload FROM outbox WHERE sent_at IS NULL
      ORDER BY created_at LIMIT :n FOR UPDATE SKIP LOCKED
      UPDATE outbox SET sent_at = now() WHERE id = :id AND sent_at IS NULL
  FOR UPDATE требует UPDATE хотя бы на одну колонку; WHERE по id и sent_at требует SELECT.
  tx_id бот не читает — колонка для reconciler. INSERT, DELETE, TRUNCATE на outbox нет.
  Компакция по sent_at (INV-3) — не бот.
- app_bot INSERT (original_id, payload, error) на outbox_dlq + USAGE outbox_dlq_id_seq:
  перенос сбоя (DEFAULT nextval требует USAGE последовательности):
      INSERT INTO outbox_dlq (original_id, payload, error) VALUES (:id, :payload, :error)
  SELECT и UPDATE на outbox_dlq нет: RETURNING не нужен, replayed_* — действие Автора позже.
- app_bot SELECT (pid, tg_user_id, tombstoned_at) на tg_user_registry: адресат и проверка
  стирания в момент отправки (В11):
      SELECT tg_user_id FROM tg_user_registry
      WHERE pid = CAST(:aggregate_id AS uuid) AND tombstoned_at IS NULL
- app_bot SELECT на text_registry: текст по text_id из payload собирает бот (В12); ПДн там нет.
- app_projector INSERT (aggregate_id, event_type, payload, tx_id) на outbox + USAGE
  outbox_id_seq: «часы» пишут outbox вместе с событием (В14):
      INSERT INTO outbox (aggregate_id, event_type, payload, tx_id)
      VALUES (:pid_text, :event_type, CAST(:payload AS jsonb), pg_current_xact_id())
  sent_at писать не может; SELECT на outbox нет — RETURNING запрещён.
- В8 = А: права выданы прямо app_*. Соответствие канону: app_bot ≈ outbox_relay (уже — по
  колонкам; плюс outbox_dlq, tg_user_registry, text_registry); app_projector ≈ outbox_writer
  (плюс USAGE последовательности).
- В13 = А: после переноса в DLQ sent_at = now() в той же транзакции — «обработано»,
  не «доставлено»; сбой видно по outbox_dlq.
- LOGIN, пароль, DSN бота — вне задачи (iter2-send-1, infra). ALTER DEFAULT PRIVILEGES
  не используется. downgrade снимает права (колоночные — своей строкой: табличный REVOKE
  их не снимает); роль не удаляется — она кластерная (как в 0001 и 0006).
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0009_app_bot"
down_revision: str | None = "0008_day_marks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES: tuple[str, ...] = ("app_bot",)

# (право, объект, роль); одна строка — одно (колоночное) право.
PRIVILEGES: tuple[tuple[str, str, str], ...] = (
    (
        "SELECT (id, aggregate_id, event_type, payload, created_at, sent_at)",
        "TABLE outbox",
        "app_bot",
    ),
    ("UPDATE (sent_at)", "TABLE outbox", "app_bot"),
    ("INSERT (original_id, payload, error)", "TABLE outbox_dlq", "app_bot"),
    ("USAGE", "SEQUENCE outbox_dlq_id_seq", "app_bot"),
    ("SELECT (pid, tg_user_id, tombstoned_at)", "TABLE tg_user_registry", "app_bot"),
    ("SELECT", "TABLE text_registry", "app_bot"),
    ("INSERT (aggregate_id, event_type, payload, tx_id)", "TABLE outbox", "app_projector"),
    ("USAGE", "SEQUENCE outbox_id_seq", "app_projector"),
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
