-- ============================================================
-- build/db-schema.sql — минимальный DDL-скелет
--
-- СТАТУС: намеренный минимальный скелет.
-- ЦЕЛЬ: зафиксировать критичные инварианты (владельцы, роли, типы полей для
--        durability-таблиц), не более того.
-- ПОЛНЫЙ DDL: живёт в репозитории реализации `course-bot`,
--        как alembic-миграции. Здесь — только эталонные ядра.
--
-- Источник имён и владельцев: architecture/build/db-tables-index.md (32 таблицы + 2 роли).
-- Источник колонок и типов: оригинал Архитектура.docx — блоки 8, 14, 15, И2, И3, И4.
-- Правило: при расхождении побеждает корпус, а не этот файл.
-- ============================================================

-- ==================== РОЛИ ====================
-- E1 ERRATA: единственный писатель participant_state — participant_state_projector

CREATE ROLE participant_state_projector;   -- единственный писатель participant_state
CREATE ROLE participant_state_reader;      -- все читатели participant_state
CREATE ROLE outbox_writer;                 -- пишет в outbox (транзакционно с доменом)
CREATE ROLE outbox_relay;                  -- читает outbox, помечает sent_at
CREATE ROLE erasure_worker;                -- пишет в erasure_blacklist
CREATE ROLE audit_reader;                  -- read-only privacy_audit_log

-- ==================== БЛОК 10 (Lifecycle) ====================
-- Владелец: participant_state_projector
-- E1 ERRATA: regular_table_populated_by_projector (НЕ materialized_view)

CREATE TABLE participant_state (
    pid                 uuid PRIMARY KEY,
    lifecycle_phase     text NOT NULL,          -- эксклюзивная ось: pre_road, active, pending_erasure, erased
    status_flags        text[] NOT NULL DEFAULT '{}',  -- модификаторы: pause_user, pause_shadow, author_pause, block_lives, ban_mod, freeze_unpaid
    author_pause_reason text,                   -- Р477: reason_class при sleeping+author_pause (block, red_flag, etc.)
    updated_at          timestamptz NOT NULL,
    projector_version   int NOT NULL,
    -- FIX1 ERRATA: publish_epoch принадлежит Б14, здесь только последнее замеченное значение
    last_seen_publish_epoch xid8
);

GRANT INSERT, UPDATE ON participant_state TO participant_state_projector;
GRANT SELECT ON participant_state TO participant_state_reader;

-- ==================== БЛОК 14 (Durability) ====================
-- Источник истины для publish_epoch (FIX1 ERRATA)

CREATE TABLE stage_publish_log (
    id              bigserial PRIMARY KEY,
    stage_id        text NOT NULL,
    publish_epoch   xid8 NOT NULL,              -- 8-байтовый TX-ID PostgreSQL (защита от XID wraparound)
    published_at    timestamptz NOT NULL,
    published_by    text NOT NULL,              -- tg_user_id Автора/Помощника
    withdrawn_at    timestamptz,
    UNIQUE (stage_id, publish_epoch)
);

-- Outbox — паттерн Transactional Outbox (ADD1 ERRATA: компакция с sent_at)
CREATE TABLE outbox (
    id              bigserial PRIMARY KEY,
    aggregate_id    text NOT NULL,
    event_type      text NOT NULL,
    payload         jsonb NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    sent_at         timestamptz,                -- NULL = не отправлено; заполненная = кандидат на компакцию
    tx_id           xid8 NOT NULL               -- для reconciler
);
CREATE INDEX outbox_unsent_idx ON outbox (created_at) WHERE sent_at IS NULL;

GRANT INSERT ON outbox TO outbox_writer;
GRANT SELECT, UPDATE ON outbox TO outbox_relay;

-- DLQ — dead letter queue
CREATE TABLE outbox_dlq (
    id              bigserial PRIMARY KEY,
    original_id     bigint NOT NULL,
    payload         jsonb NOT NULL,
    error           text NOT NULL,
    moved_at        timestamptz NOT NULL DEFAULT now(),
    replayed_at     timestamptz,
    replayed_by     text
);

-- ==================== БЛОК 15 (Storage / Audit) ====================

-- Append-only лог выдач контента
CREATE TABLE issuance_log (
    issuance_id     bigserial PRIMARY KEY,
    participant_id  uuid NOT NULL,              -- surrogate ID
    stage           int NOT NULL,
    day             int NOT NULL,
    issued_at       timestamptz NOT NULL DEFAULT now(),
    window_seq      int NOT NULL,               -- № окна лимита (3 выдачи в 24 часа)
    message_id      bigint,                     -- Telegram message_id (для отзыва)
    idempotency_key text NOT NULL UNIQUE        -- защита от дубликатов
);

-- Append-only лог аномалий (детекция подозрительного темпа)
CREATE TABLE anomaly_log (
    id                  bigserial PRIMARY KEY,
    participant_id      uuid NOT NULL,
    detected_pattern    jsonb NOT NULL,         -- какой триггер сработал
    occurred_at         timestamptz NOT NULL DEFAULT now(),
    action_taken        text NOT NULL           -- soft_suspend, escalate, etc.
);

-- Erasure blacklist — суррогатные ID, которые нельзя восстанавливать из бэкапа
CREATE TABLE erasure_blacklist (
    participant_id  uuid PRIMARY KEY,
    erased_at       timestamptz NOT NULL,
    retention_until timestamptz NOT NULL        -- = full_backup_rotation_cycle (Boot-gate, ADD5)
);

GRANT INSERT, SELECT ON erasure_blacklist TO erasure_worker;

-- Privacy Audit Log — 152-ФЗ, каждый доступ к ПДн
CREATE TABLE privacy_audit_log (
    id              bigserial PRIMARY KEY,
    actor_id        text NOT NULL,              -- tg_user_id Автора/Помощника
    actor_role      text NOT NULL,              -- owner, moderator, finance, helper
    action          text NOT NULL,              -- view, export, legal_open, send_blocked_hard_ban, send_blocked_erasure
    participant_id  uuid,                       -- цель действия (NULL для системных)
    occurred_at     timestamptz NOT NULL DEFAULT now(),
    metadata        jsonb                       -- контекст (например, hash фото)
);
CREATE INDEX privacy_audit_actor_idx ON privacy_audit_log (actor_id, occurred_at);
CREATE INDEX privacy_audit_participant_idx ON privacy_audit_log (participant_id, occurred_at);

GRANT SELECT ON privacy_audit_log TO audit_reader;

-- ==================== ИНВАРИАНТЫ БД (в CI-чеки) ====================
-- INV-1: единственный писатель participant_state — participant_state_projector
-- INV-2: append_only_logs (issuance_log, anomaly_log, privacy_audit_log,
--        measurements_log, reflections_log, money_ops_log) — только INSERT
-- INV-3: outbox компакция с sent_at (INV-OUTBOX-SENT-AT-COMPACTION, ADD1)
-- INV-4: erasure_blacklist.retention_until = full_backup_rotation_cycle
--        (Boot-gate: до подстановки — блокирует прод)
-- INV-5: refund_details retention = 3 года (НК РФ), отдельно от PII
-- INV-6: publish_epoch хранится в stage_publish_log (Б14), а не в participant_state (Б10)

-- ==================== ОСТАЛЬНЫЕ ~25 ТАБЛИЦ ====================
-- Список имён и владельцев: architecture/build/db-tables-index.md.
-- Колонки и типы: наполняются как alembic-миграции в репозитории `course-bot`
-- при первой итерации реализации (см. build-order.md, Уровень 1 и Итерация 1).
--
-- Причина минимума здесь: оригинал Архитектуры не содержит полного DDL
-- одним куском; заполнить его гипотезами означало бы ввести агента в
-- заблуждение. Критичные для durability таблицы (те 8 выше) — единственные,
-- для которых оригинал даёт колонки и типы. Всё остальное — прикладная
-- работа реализатора, которая делается в код-репозитории вместе с миграциями.

-- END OF SKELETON
