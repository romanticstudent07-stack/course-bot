---
file: debt/15-A3-outbox-dlq-saga-granularity.md
block: 15
title: "Артефакт долга A3 — dead-letter outbox и гранулярность саги erasure"
node: A3
attach_to: "подшить под → БЛОК 15"
outcome: CLOSE
status: CLOSE, v3.2
doc_version: "consolidated v3"
contains: [выжимка, interface contract yaml, stub-хвосты, снятый PARK]
---

# [АРТЕФАКТ ДОЛГА · подшить под → БЛОК 15 · узел A3 · CLOSE · v3.2]

осн. адресат Б15/Инфра; STUB-хвосты → Б9 (тексты алертов DLQ), Legal (основание/срок удержания обезличенной DLQ-записи после erasure); PARK — снят (гранулярность саги закрыта моделью А)

## Выжимка

Задача уходит в dead-letter по одной из трёх различаемых причин, и стратегия обработки для каждой разная: poison_threshold — исчерпаны 5 retry транзиентных ошибок; non_transient — 403/chat-not-found, сразу минуя счётчик, ретрай бессмысленен; unknown_schema — неизвестная schema_version (R146, Д-Б15-schema), никогда не выбрасывается автоматически, переигрывается после апгрейда читающего кода. Смешивать причины нельзя: non_transient и poison не авто-реплеятся (иначе fail-forever loop), unknown_schema обязан породить алерт (иначе тихо накапливается) и сохраняется до деплоя.

Формы DLQ-записи в корпусе Б15 не было — она вводится этим узлом (NR). Запись — durable-строка со ссылочной (ref) моделью payload: хранит participant_id + payload-ref (логический адрес над суррогатами), но НЕ сырой chat_id/PII. Это вынужденно следует из инварианта Б15 direct_identifier_locations (прямой идентификатор живёт ровно в двух местах — identity_map и delivery_registry, оба обезличиваются при erasure); полный payload создал бы запрещённое третье место PII. После break_identity (A1) ссылка становится нерезолвимой автоматически — PII не переживает erasure без единого дополнительного шага саги. Инвариант INV-A3-REF-PURITY запрещает любой прямой идентификатор в любом поле записи.

Reprocessing идёт через тот же relay-путь с сохранением оригинального idempotency_key; tier-2 UNIQUE (закрытый дедуп, Шаг 4.2) защищает от двойного эффекта при переигрывании — дедуп используется, не вскрывается. DLQ-запись, чей субъект прошёл erasure, переходит в статус orphaned_by_erasure: остаётся для аудита обезличенной, но исключена из reprocessing и из actionable-алертов dead_letter_monitor — это отличает «легитимно нерезолвимо» от «застряло».

Гранулярность саги erasure закреплена как модель А: одна сага-строка с полем state (forward-recovery feed_cleaned→identity_broken→done), а не N задач на стадию. Внутри стадии run_canonical_deletion физическое удаление ленты дробится пачками до 100 по delivery_registry — это отдельный курсор исполнения, не гранулярность саги. Два курсора, один уровень саги. Это закрывает PARK, тянувшийся из A1 и A2.

Алерт-канал переиспользует уже зафиксированный admin_alert → work_group_special_topic (Шаг 7 Б15); тексты алертов — STUB(Б9). Дедупликация не трогается (status: closed). Фантом-решение R130 вычеркнуто из плана.

## Interface Contract (YAML)

```yaml
artifact: A3_outbox_dlq_and_saga_granularity
file_under: {block: 15, node: A3, outcome: CLOSE, version: v3.2}
owner: Б15/Инфра

dead_letter_reasons:        # три различаемые, стратегия reprocessing разная
  poison_threshold:  {trigger: "5 retry исчерпаны (worker_retry_count_threshold)", auto_replay: false}
  non_transient:     {trigger: "403 blocked / chat not found", to_dlq: immediately, auto_replay: false}
  unknown_schema:    {trigger: "неизвестная schema_version (R146)", auto_discard: never, alert: mandatory, replay: after_reader_upgrade}
  on_dead_letter: [mark_failed, alert_manual_review]

dlq_record:                 # NR — формы в корпусе не было, вводится A3
  model: reference          # НЕ полный payload
  fields:
    participant_id: surrogate
    payload_ref: logical_address   # participant_id + module + day + block_number (Шаг 2)
    original_transaction_id: xid8  # курсор порядка при reprocessing (из A2)
    dead_letter_reason: enum
    retry_count: int
    error_detail: text_no_pii
    schema_version: original
    status: [new, investigating, replayed, discarded, orphaned_by_erasure]
    dead_lettered_at: timestamptz
    last_error_at: timestamptz
  invariant_INV-A3-REF-PURITY: "ни одно поле не содержит chat_id/тело/прямой идентификатор;
     payload_ref = логический адрес над суррогатами. Нарушение = 3-е место PII = violates direct_identifier_locations"

reprocessing:
  path: same_relay
  preserve: original_idempotency_key   # tier-2 UNIQUE ловит двойной эффект (использует закрытый дедуп)
  poison_non_transient: manual_only    # авто-реплей запрещён (fail-forever)
  unknown_schema: replay_after_upgrade

erasure_interaction:
  ref_becomes_unresolvable_after: break_identity_irreversible   # A1
  no_extra_saga_step: true             # PII не хранился → чистить нечего
  post_erasure_status: orphaned_by_erasure   # исключён из reprocessing + actionable-алертов монитора

saga_granularity:           # CLOSE-as-NR, модель А — закрывает PARK A1/A2
  model: single_saga_row_with_state
  state: "feed_cleaned -> identity_broken -> done"   # d5_composite_erasure
  recovery: forward
  cursors:
    saga_stage_cursor: state
    feed_deletion_cursor: per_message_batch_100   # delivery_registry, исполнение ВНУТРИ стадии
  rejected: N_rows_per_stage   # противоречит d5_composite_erasure

alert_channel: admin_alert_work_group_special_topic   # переиспользован (Шаг 7 Б15)

not_touched:
  dedup: {status: closed, note: "tier-1/tier-2, dedup_three_levels, anti_webhook_duplicate — регресс запрещён"}
phantom_removed: R130

stub_tails:
  - {to: Б9, what: "тексты алертов DLQ"}
  - {to: Legal, what: "основание удержания и срок жизни обезличенной DLQ-записи после erasure (аналог retention обезличенных логов)"}
```
