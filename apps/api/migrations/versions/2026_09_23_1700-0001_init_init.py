"""init: эталонные ядра БД из docs/architecture/build/db-schema.sql

Revision ID: 0001_init
Revises:
Create Date: 2026-09-23 17:00:00

Источник: docs/architecture/build/db-schema.sql (read-only зеркало DOCS-course-bot).
Содержимое перенесено ДОСЛОВНО: 6 ролей, 8 таблиц, 3 индекса, 7 GRANT.
Единственное отступление — CREATE ROLE обёрнут в идемпотентный DO-блок:
роли PostgreSQL живут на уровне КЛАСТЕРА, а не БД, и голый CREATE ROLE
падает при повторном прогоне на кластере, где роль уже есть.

Соответствие миграции и db-schema.sql проверяет tests/test_migration_init.py
(правило нулевых потерь): при обновлении зеркала тест упадёт и покажет расхождение.

Нормы:
  - E1 ERRATA / OVERRIDES.E1: participant_state — ОБЫЧНАЯ таблица,
    единственный писатель — роль participant_state_projector (INV-1);
  - FIX1 ERRATA: publish_epoch принадлежит Б14 (stage_publish_log),
    в participant_state — только last_seen_publish_epoch;
  - ADD1 ERRATA: outbox.sent_at + частичный индекс по неотправленным.

Остальные ~24 таблицы (db-tables-index.md) — отдельными миграциями в Итерации 1.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_init"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ==================== РОЛИ ====================
# E1 ERRATA: единственный писатель participant_state — participant_state_projector
ROLES: tuple[str, ...] = (
    "participant_state_projector",  # единственный писатель participant_state
    "participant_state_reader",  # все читатели participant_state
    "outbox_writer",  # пишет в outbox (транзакционно с доменом)
    "outbox_relay",  # читает outbox, помечает sent_at
    "erasure_worker",  # пишет в erasure_blacklist
    "audit_reader",  # read-only privacy_audit_log
)

# Порядок важен: таблицы → индексы → GRANT (как в db-schema.sql).
DDL: tuple[str, ...] = (
    # ==================== БЛОК 10 (Lifecycle) ====================
    # Владелец: participant_state_projector
    # E1 ERRATA: regular_table_populated_by_projector (НЕ materialized_view)
    """
    CREATE TABLE participant_state (
        pid                 uuid PRIMARY KEY,
        lifecycle_phase     text NOT NULL,          -- эксклюзивная ось: pre_road, active, pending_erasure, erased
        status_flags        text[] NOT NULL DEFAULT '{}',  -- модификаторы: pause_user, pause_shadow, author_pause, block_lives, ban_mod, freeze_unpaid
        author_pause_reason text,                   -- Р477: reason_class при sleeping+author_pause (block, red_flag, etc.)
        updated_at          timestamptz NOT NULL,
        projector_version   int NOT NULL,
        -- FIX1 ERRATA: publish_epoch принадлежит Б14, здесь только последнее замеченное значение
        last_seen_publish_epoch xid8
    )
    """,
    "GRANT INSERT, UPDATE ON participant_state TO participant_state_projector",
    "GRANT SELECT ON participant_state TO participant_state_reader",
    # ==================== БЛОК 14 (Durability) ====================
    # Источник истины для publish_epoch (FIX1 ERRATA)
    """
    CREATE TABLE stage_publish_log (
        id              bigserial PRIMARY KEY,
        stage_id        text NOT NULL,
        publish_epoch   xid8 NOT NULL,              -- 8-байтовый TX-ID PostgreSQL (защита от XID wraparound)
        published_at    timestamptz NOT NULL,
        published_by    text NOT NULL,              -- tg_user_id Автора/Помощника
        withdrawn_at    timestamptz,
        UNIQUE (stage_id, publish_epoch)
    )
    """,
    # Outbox — паттерн Transactional Outbox (ADD1 ERRATA: компакция с sent_at)
    """
    CREATE TABLE outbox (
        id              bigserial PRIMARY KEY,
        aggregate_id    text NOT NULL,
        event_type      text NOT NULL,
        payload         jsonb NOT NULL,
        created_at      timestamptz NOT NULL DEFAULT now(),
        sent_at         timestamptz,                -- NULL = не отправлено; заполненная = кандидат на компакцию
        tx_id           xid8 NOT NULL               -- для reconciler
    )
    """,
    "CREATE INDEX outbox_unsent_idx ON outbox (created_at) WHERE sent_at IS NULL",
    "GRANT INSERT ON outbox TO outbox_writer",
    "GRANT SELECT, UPDATE ON outbox TO outbox_relay",
    # DLQ — dead letter queue
    """
    CREATE TABLE outbox_dlq (
        id              bigserial PRIMARY KEY,
        original_id     bigint NOT NULL,
        payload         jsonb NOT NULL,
        error           text NOT NULL,
        moved_at        timestamptz NOT NULL DEFAULT now(),
        replayed_at     timestamptz,
        replayed_by     text
    )
    """,
    # ==================== БЛОК 15 (Storage / Audit) ====================
    # Append-only лог выдач контента
    """
    CREATE TABLE issuance_log (
        issuance_id     bigserial PRIMARY KEY,
        participant_id  uuid NOT NULL,              -- surrogate ID
        stage           int NOT NULL,
        day             int NOT NULL,
        issued_at       timestamptz NOT NULL DEFAULT now(),
        window_seq      int NOT NULL,               -- № окна лимита (3 выдачи в 24 часа)
        message_id      bigint,                     -- Telegram message_id (для отзыва)
        idempotency_key text NOT NULL UNIQUE        -- защита от дубликатов
    )
    """,
    # Append-only лог аномалий (детекция подозрительного темпа)
    """
    CREATE TABLE anomaly_log (
        id                  bigserial PRIMARY KEY,
        participant_id      uuid NOT NULL,
        detected_pattern    jsonb NOT NULL,         -- какой триггер сработал
        occurred_at         timestamptz NOT NULL DEFAULT now(),
        action_taken        text NOT NULL           -- soft_suspend, escalate, etc.
    )
    """,
    # Erasure blacklist — суррогатные ID, которые нельзя восстанавливать из бэкапа
    """
    CREATE TABLE erasure_blacklist (
        participant_id  uuid PRIMARY KEY,
        erased_at       timestamptz NOT NULL,
        retention_until timestamptz NOT NULL        -- = full_backup_rotation_cycle (Boot-gate, ADD5)
    )
    """,
    "GRANT INSERT, SELECT ON erasure_blacklist TO erasure_worker",
    # Privacy Audit Log — 152-ФЗ, каждый доступ к ПДн
    """
    CREATE TABLE privacy_audit_log (
        id              bigserial PRIMARY KEY,
        actor_id        text NOT NULL,              -- tg_user_id Автора/Помощника
        actor_role      text NOT NULL,              -- owner, moderator, finance, helper
        action          text NOT NULL,              -- view, export, legal_open, send_blocked_hard_ban, send_blocked_erasure
        participant_id  uuid,                       -- цель действия (NULL для системных)
        occurred_at     timestamptz NOT NULL DEFAULT now(),
        metadata        jsonb                       -- контекст (например, hash фото)
    )
    """,
    "CREATE INDEX privacy_audit_actor_idx ON privacy_audit_log (actor_id, occurred_at)",
    "CREATE INDEX privacy_audit_participant_idx ON privacy_audit_log (participant_id, occurred_at)",
    "GRANT SELECT ON privacy_audit_log TO audit_reader",
)

# Обратный порядок создания; индексы и GRANT удаляются вместе с таблицами.
TABLES_DROP_ORDER: tuple[str, ...] = (
    "privacy_audit_log",
    "erasure_blacklist",
    "anomaly_log",
    "issuance_log",
    "outbox_dlq",
    "outbox",
    "stage_publish_log",
    "participant_state",
)


def _create_role_if_missing(role: str) -> str:
    # Роль — объект кластера; повторный прогон (другая БД того же кластера) не должен падать.
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
    for statement in DDL:
        op.execute(statement)


def downgrade() -> None:
    for table in TABLES_DROP_ORDER:
        op.execute(f"DROP TABLE IF EXISTS {table}")
    # Роли НЕ удаляются: они общие для кластера и могут использоваться другой БД.
    # Удаление ролей — ручная операция Автора (DROP ROLE ...), чтобы не потерять чужие права.
