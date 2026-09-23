---
file: build/db-tables-index.md
title: "Реестр таблиц БД: имя → владелец → назначение"
status: скелет
doc_version: "db-tables-index v1.1"
contains: [32 таблицы + 2 роли БД, ссылка на db-schema.sql]
---

# db-tables-index.md — реестр таблиц БД

Реестр имён и владельцев. Колонки, типы, ключи и индексы для критичных таблиц — в
[db-schema.sql](db-schema.sql) (8 эталонных таблиц). Остальные 24 таблицы наполняются
как alembic-миграции в репозитории `course-bot` во время Итерации 1
(см. [build-order.md](build-order.md), Уровень 1 и Итерация 1).

## Правило владения

- **Владелец таблицы** — блок, который её описывает и вправе менять контракт.
- **Durability-owner** — блок, обеспечивающий физическую durability (обычно Б14/Б15).
- Пара «владелец + durability-owner» — стандарт архитектуры, не двоевластие. Инвариант
  `single_owner_per_table` относится к **владельцу контракта**, не к durability.

## Таблицы (32)

| Таблица | Владелец / durability | Назначение |
|---|---|---|
| `tg_user_registry` | Б4 (SEAM-1) | Регистрация Telegram-пользователей, первый вход через Mini App |
| `participant_state` | Б10 (`participant_state_projector`) / Б14 | Проекция FSM участника (E1 ERRATA: regular table) |
| `state_transition_log` | Б10 / Б14 | Append-only лог переходов состояний |
| `role_capability_matrix` | Б17 | Матрица «команда × роль» (E3 ERRATA) |
| `hard_confirm_phrases` | Б17 / Б14 | Реестр фраз hard-confirm (хэши, E3) |
| `whitelist_admin_ids` | Б17 / Б14 | Whitelist Автора/Помощников/Finance |
| `text_registry` | **Б9 (владелец) / Б14 (durability)** | Единый источник текстов (три тона, `{домен}.{имя}`), И4 |
| `topic_bindings` | Б8 / Б14 | Привязка форум-топиков к alias'ам |
| `metric_catalog_log` | Б14 | Append-only лог метрик и их определений |
| `issuance_log` | Б15 / Б14 | Append-only лог выдач контента (см. db-schema.sql) |
| `anomaly_log` | Б15 / Б14 | Append-only лог аномалий темпа (см. db-schema.sql) |
| `piracy_holds` | Б15 / Б14 | Соft-suspend после подозрительного темпа |
| `delivery_registry` | Б15 / Б14 | Outbox pattern: registry of scheduled deliveries |
| `outbox` | Б15 / Б14 | Transactional Outbox с partitioning по sent_at (см. db-schema.sql) |
| `outbox_dlq` | Б15 / Б14 | Dead Letter Queue (см. db-schema.sql) |
| `consumer_offsets` | Б15 / Б14 | Позиции relay-читателей outbox |
| `identity_map` | Б14 | `participant_id` (surrogate) ↔ `chat_id` (Telegram) |
| `change_map_cache` | Б14 | Инкрементально материализованная проекция прогресса |
| `tz_change_log` | Б14 | История смены таймзоны участника |
| `stage_publish_log` | Б14 | Публикация этапов (FIX1 ERRATA: publish_epoch, см. db-schema.sql) |
| `measurements_log` | Б5 / Б14 | Append-only лог замеров (Чек-Ап, антропометрия) |
| `reflections_log` | Б7 / Б14 | Append-only лог рефлексий |
| `money_ops_log` | Б16 / Б14 | Append-only лог финансовых операций |
| `refund_details` | Б16 / Б14 | Детали refund'ов (retention 3 года, НК РФ) |
| `payment_receipts` | Б16 / Б14 | Чеки НПД (54-ФЗ) |
| `erasure_blacklist` | Б14 (`erasure_worker`) | Суррогатные ID, не восстанавливаемые из бэкапов (см. db-schema.sql) |
| `pii_access_log` | Б14 (privacy) | Log каждого просмотра ПДн |
| `privacy_audit_log` | Б14 (privacy) | 152-ФЗ, каждый доступ Автора/Помощника к ПДн (см. db-schema.sql) |
| `admin_action_log` | Б17 / Б14 | Оперативный лог команд Автора/Помощников |
| `owner_dashboard_state` | Б17 / Б14 | Read-only проекция для UI владельца |
| `refund_saga_log` | Б16 / Б14 | Пошаговый лог Refund Saga |
| `red_flags_log` | Б9 (Red Flags Protocol) / Б14 | Триггеры Red Flags и действия (60 сек, sleeping) |

## Роли БД (2)

| Роль | Что делает |
|---|---|
| `participant_state_projector` | Единственный писатель `participant_state` (E1 ERRATA, INV-1) |
| `participant_state_reader` | Все read-only читатели `participant_state` |

Дополнительные роли (`outbox_writer`, `outbox_relay`, `erasure_worker`, `audit_reader`) —
в [db-schema.sql](db-schema.sql).

## Долги реестра

- Столбцы, типы, ключи, индексы для 24 таблиц вне [db-schema.sql](db-schema.sql) — наполняются
  как alembic-миграции в `course-bot` во время Итерации 1.
- Retention-политики для не-audit таблиц — в [../99/99-03-yaml-v2ext.md](../99/99-03-yaml-v2ext.md).

## Связанные файлы

- [db-schema.sql](db-schema.sql) — эталонные ядра (8 таблиц + роли).
- [build-order.md](build-order.md) — порядок реализации.
- [config-schemas/text_registry.schema.json](config-schemas/text_registry.schema.json) — JSON-Schema для `text_registry`.
