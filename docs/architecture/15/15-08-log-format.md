---
file: 15/15-08-log-format.md
block: 15
title: "Шаг 8 — Формат логов"
status: закрыт
doc_version: "consolidated v3"
contains: [Шаг 8, четыре журнала, модель контента в логах, неизменность, durability, чистка, приватность, retention, yaml step_8]
---

# БЛОК 15 · ШАГ 8 — ФОРМАТ ЛОГОВ

Шаг определяет журналы Блока 15: состав, структуру под детекцию, неизменность, чистку, приватность, сроки хранения. Журналы — фундамент детектора Шага 7 и механики удаления Шага 3.

Четыре журнала, которые нельзя сливать. Три собственных: журнал выдач (issuance_log) — событийная запись каждого факта выдачи текста, сырьё детектора и стык с лимитом 3/24ч; журнал регенераций (regeneration_log) — повторное построение карточки, не являющееся новой выдачей нового дня (перевход, рестарт-восстановление, пере-рендер после сбоя); журнал аномалий (anomaly_log) — срабатывания детектора (триггер, snapshot, приостановка, алерт, снятие). Четвёртый — аудит доступа по 152-ФЗ — принадлежит Блоку 6/правовому блоку, вне Б15; свои журналы проектируем так, чтобы не пересекаться с ним по назначению.

Модель контента в логах: хранятся идентификаторы контента (stage, day), но никогда сам текст задания (раздувание + утечка ценности). Прямой идентификатор участника (chat_id) в логах не хранится — используется суррогат participant_id; связка participant_id ↔ chat_id живёт в единственной защищённой таблице identity_map. Реестр message_id (delivery_registry) для механики «удаление = отзыв доступа» связан с журналом выдач общим ключом issuance_id и является единственным, кроме identity_map, местом с chat_id.

Неизменность — техническая: все три журнала append-only, гарантия на уровне прав — рабочая роль имеет только INSERT/SELECT, UPDATE/DELETE отозваны (REVOKE); даже баг не перепишет запись. Durability и атомарность: критичные журналы (выдачи, аномалии) пишутся синхронно в PG в одной транзакции с действием — исключает и «выдано, но не залогировано» (ослепление детектора), и «залогировано, но не выдано» (ложное срабатывание). Redis для критичных недопустим как источник правды. Батчинг для критичных запрещён (буфер теряется при краше), разрешён только для некритичной телеметрии регенераций. Скользящее окно 24ч: источник правды — issuance_log в PG (не счётчик Redis, снимает класс гонок), Redis — только кэш; обязателен индекс (participant_id, issued_at).

Чистка и защита от переполнения: ретеншен через DROP партиций по времени (мгновенно, без bloat), а не построчный DELETE (нагружает autovacuum на слабом VPS); партиционирование даёт маленькие горячие партиции; DROP выполняет reconciler Шага 5 под maintenance-ролью; второй контур — мониторинг размера журнальных таблиц с ранним алертом (ловит, если reconciler упал); разнесение томов и ротация логов PG — из Шага 5. XID wraparound на insert-only журналах: целевая PostgreSQL 17 (фоллбэк 16), per-table autovacuum_vacuum_insert_threshold, мониторинг age(relfrozenxid).

Приватность и эрейж: реализуется разрывом связки participant_id ↔ chat_id в identity_map; живая БД обезличивается мгновенно (в журналах остаётся суррогат, восстановить личность нельзя). Признанное ограничение: бэкапы 3-2-1 содержат прежнюю связку до истечения своего срока; снимки не вскрываем (это ломает целостность), полагаемся на вымывание ретеншеном. Соответствует инварианту «erasure > identity». Retention — механизм двух раздельных рычагов, но не юридические числа (сроки ПДн — правовой блок): срок identity_map (прямой идентификатор) короткий; срок обезличенных журналов длинный под детекцию (дефолт-заглушка 12 месяцев). Развязка: обезличенные журналы не ПДн в смысле storage limitation, поэтому могут храниться дольше без конфликта с 152-ФЗ, тогда как прямой идентификатор живёт по короткому сроку — одно решение (суррогат) закрывает и приватность, и потребность детекции в истории.

## YAML — Шаг 8

```yaml
block_15:

  # ================================================================
  step_8:
    title: "Формат логов"
    status: closed
    target_db: {engine: postgresql, version: 17, fallback: 16, reason: "insert-vacuum из коробки (XID wraparound), 5y support, VPS-friendly"}
    journals:
      issuance_log:
        purpose: "каждый факт выдачи ТЕКСТА; сырьё детектора + источник правды окна 3/24h"
        criticality: critical
        write: "synchronous, same tx as issuance"
        batching: forbidden
        append_only: true
        fields: {issuance_id: pk, participant_id: surrogate, stage: int, day: int, issued_at: timestamptz, window_seq: int, direction_hint: "enum[asc,desc,none]"}
        index: ["(participant_id, issued_at)"]
      anomaly_log:
        purpose: "срабатывания детектора Шага 7"
        criticality: critical
        write: synchronous
        batching: forbidden
        append_only: true
        fields: {anomaly_id: pk, participant_id: surrogate, detected_pattern: jsonb, action: "enum[suspension,alert,release]", release_mode: "enum[manual,auto_24h,null]", occurred_at: timestamptz}
      regeneration_log:
        purpose: "повторное построение карточки, НЕ новая выдача нового дня"
        criticality: mixed
        write: "core synchronous; verbose telemetry may be batched"
        batching: allowed_for_noncritical_telemetry_only
        append_only: true
        fields: {regen_id: pk, participant_id: surrogate, stage: int, day: int, regen_reason: "enum[re_entry,restart_recovery,re_render_after_fault]", regenerated_at: timestamptz}
        must_not_merge_with: 152_fz_access_audit
    linked_tables:
      delivery_registry: {link: "issuance_id (FK)", fields: [issuance_id, chat_id, message_id, sent_at], note: "одно из двух мест с chat_id"}
      identity_map: {fields: [participant_id, chat_id], erasure: "разрыв связки -> живая БД обезличена мгновенно"}
    immutability: {method: role_privileges, app_role: [INSERT, SELECT], revoke: [UPDATE, DELETE], maintenance_role: [DROP_PARTITION]}
    retention:
      method: "DROP time-partition (NOT row DELETE)"
      executor: "Step 5 reconciler под maintenance-ролью"
      partition_by: time
      second_guard: "мониторинг размера таблиц, ранний алерт если reconciler упал"
      volume_separation: "см. Step 5 (referenced)"
      levers:
        identity_map_retention: {duration: "SHORT — правовой блок", holds: "прямой идентификатор"}
        anonymized_logs_retention: {duration_default: "12 months", holds: "суррогат-журналы", rationale: "обезличено => не ПДн для storage-limitation => может жить дольше"}
    window_24h: {source_of_truth: issuance_log_postgresql, redis: non_critical_cache_only}
    wraparound_protection: {cause: "insert-only пропускают autovacuum -> deferred freeze -> forced stop", cure: ["PG17 insert-triggered autovacuum", "per-table autovacuum_vacuum_insert_threshold", "monitor age(relfrozenxid)"]}
    privacy_erasure:
      mechanism: "разрыв participant_id<->chat_id в identity_map"
      live_db: anonymized_instantly
      backups: {handling: acknowledged_limitation, detail: "старая связка в 3-2-1 до истечения их ретеншена; снимки не вскрываем (целостность)"}
      invariant: "erasure > identity"
```
