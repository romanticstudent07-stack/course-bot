---
file: debt/15-A2-background-concurrency.md
block: 15
title: "Артефакт долга A2 — фоновая конкуренция, порядок relay, housekeeping outbox"
node: A2
attach_to: "подшить под → БЛОК 15"
outcome: CLOSE
status: CLOSE, v3.2
doc_version: "consolidated v3"
contains: [выжимка, interface contract yaml, park]
---

# [АРТЕФАКТ ДОЛГА · подшить под → БЛОК 15 · узел A2 · CLOSE · v3.2]

осн. адресат Б15/Инфра;

NR-хвост → Б15/durability (колонка transaction_id xid8 + курсор); PARK → Б15/A3 (гранулярность outbox-строки саги)

## Выжимка

Фоновая обработка строится на трёх раздельных механизмах конкуренции, которые нельзя смешивать: выборка задач через FOR UPDATE SKIP LOCKED (лок tx-scoped, краш воркера освобождает автоматически; advisory для задач отвергнут); защита от второго экземпляра бота через строку-лидер с TTL-lease (renew ~10с / TTL ~30с) + активный self-fence + эксклюзивность webhook (advisory отвергнут); самозащита reconciler через pg_try_advisory_lock (здесь advisory уместен — координация фонов, не бизнес-операция).

Корректность порядка relay обеспечивается не голой сортировкой по id, а вводимой (NR) колонкой transaction_id xid8 (заполняется pg_current_xact_id() при вставке): relay фильтрует transaction_id < pg_snapshot_xmin(pg_current_snapshot()) и ведёт курсор по паре (transaction_id, id). Голый id > last запрещён — теряет строки долгих транзакций, чей id присвоен до коммита. Тип строго xid8 (не оборачивается) — согласовано с защитой от XID wraparound (5.9). id остаётся вторичным ключом сортировки внутри транзакции, что не противоречит id_bigint_identity_only (5.5).

Ни одна транзакция не открыта на время сетевого вызова: паттерн трёх коротких фаз — claim (короткая tx) → внешний вызов вне tx → ack-update (короткая tx). Зависшие in_progress подхватываются reaper'ом по возрасту и startup-recovery по статусу; мониторинг возраста очереди обязателен как мера безопасности.

Outbox партиционирован по sent/unsent; relay сканирует малую unsent-партицию; TRUNCATE sent-партиции разрешён только после подтверждённого переноса message_id в основную таблицу контента (иначе теряется recovery-владелец). DDL-контракт (партиционирование + xid8 + составной индекс (transaction_id, id) на unsent + партиальный индекс таймеров) закладывается сразу — задним числом дорого.

Скан durable-таймеров находит наступившие fire_at, но не триггерит списание жизни напрямую: решение о жизни принадлежит durability-слою (5.6 — re-check/reconciler, заморозка имеет абсолютный приоритет над catch-up, неопределённость → жизнь не списывается). A2 владеет только фактом «таймер наступил».

## Interface Contract (YAML)

```yaml
artifact: A2_background_concurrency
file_under: {block: 15, node: A2, outcome: CLOSE, version: v3.2}
owner: Б15/Инфра

concurrency_mechanisms:   # ТРИ раздельных, не смешивать
  task_dequeue:
    form: "SELECT ... WHERE status=? ORDER BY transaction_id ASC, id ASC FOR UPDATE SKIP LOCKED LIMIT N"
    lock: tx_scoped        # краш воркера освобождает лок
    advisory: rejected_for_tasks
  single_instance_guard:
    form: leader_row_ttl_lease
    renew_sec: 10
    ttl_sec: 30
    self_fence: active     # потеряв аренду, экземпляр самоустраняется
    webhook_exclusivity: true   # fencing со стороны Telegram (409 Conflict)
    advisory: rejected
  reconciler_self_guard:
    form: pg_try_advisory_lock   # advisory УМЕСТЕН (координация фонов)
    cursor: checkpoint_by_id
    timeout: statement_timeout + heartbeat

relay_ordering:            # NR — новое решение, владелец Б15/durability
  new_column: {name: transaction_id, type: xid8, fill: pg_current_xact_id()}
  visibility_filter: "transaction_id < pg_snapshot_xmin(pg_current_snapshot())"
  cursor: "(transaction_id, id)"
  order_by: "transaction_id ASC, id ASC"
  forbid: "bare id > last (silently loses long-tx rows)"
  type_note: "строго xid8 (не xid) — согласовано с XID-wraparound 5.9"
  compat: "id остаётся вторичным ключом → не нарушает id_bigint_identity_only (5.5)"

worker_pattern:
  three_short_phases: [claim_short_tx, external_call_OUTSIDE_tx, ack_update_short_tx]
  invariant: "ни одна tx не открыта на время сетевого вызова (анти-bloat/анти-pool)"
  stuck_inprogress: reaper_by_age + startup_recovery_by_status
  queue_age_monitoring: mandatory_safety_measure

outbox_housekeeping:
  partitioning: {by: sent_unsent, lay_down: immediately_via_ddl}
  relay_scans: unsent_partition_only
  truncate_sent: "разрешён ТОЛЬКО после подтверждённого переноса message_id в основную таблицу"

ddl_contract_upfront:      # всё задним числом дорого → сразу
  - partitioning_sent_unsent
  - column_transaction_id_xid8
  - composite_index_(transaction_id, id)_on_unsent
  - partial_index_timers_where_not_fired   # Р-A2.8

timer_scan_boundary:
  a2_owns: "скан нашёл наступивший fire_at"
  life_decision_owner: durability_5.6   # re-check/reconciler; заморозка > catch-up; неопределённость → не списывать
  invariant: "скан НЕ триггерит списание жизни напрямую"

failure_mode:
  worker_crash_mid_batch: "SKIP LOCKED освобождает лок; startup-recovery + reaper добирают"
  zombie_instance_after_gc: "self-fence + webhook-эксклюзивность (TTL сам по себе недостаточен)"
  lost_long_tx_row: "закрыт xmin-фильтром + (txid,id)-курсором"

park:
  - {to: Б15/A3, what: "гранулярность outbox-строки саги erasure: 1 vs N (не закрыто в архиве)"}
```
