---
file: normative/I2-wave-b.md
block: normative
patch_id: I2-WAVE-B
title: "Патч И2 — Волна B: durability + participant_state + паузы + life-ops"
status: канон (нормативный стек)
precedence: 2
doc_version: "consolidated v3.6-i2"
parent_doc_version: "consolidated v3.5-i1"
depends_on: [I1-WAVE-A]
contains: [meta, outbox_contract, backup_contract, participant_state_contract, stage_flow, pause_semantics, life_ops, idempotency_keys, advisory_locks, erasure_lifecycle, role_capability_matrix_i2_additions, hard_confirm_phrases, whitelist_recovery_procedure, privacy_audit_sla, d14_write_before_render, deferred_from_i2, ci_checks_i2, audit_additions_i2, risk_registry_additions_i2]
---

# ПАТЧ И2 — ВОЛНА B. Durability, participant_state, паузы, life-ops

> **Канонический источник старшинства** — [README.md](README.md), раздел «Две оси: порядок присоединения ≠ ступень старшинства». Цепочка ниже в этом файле — порядок **присоединения**, а не ступень старшинства. Ступень старшинства: `корпус v3 → И1 → И2 → И3 → И4 → Б17 → SEAM-PATCH-1 → ERRATA-UNIFIED (высшая)`.

> **Переопределено ERRATA-UNIFIED.** Спор о носителе `participant_state` решён окончательно: обычная таблица, наполняемая проектором (`regular_table_populated_by_projector`), — строка `projection.kind: materialized_view` в этом файле недействительна (E1). Запись только роли `participant_state_projector`, чтение — `participant_state_reader`, проектор в блоке 10, инвариант И-1 в силе. Фразовый hard-confirm сохранён (E3): двухшаг и фраза — слои, а не альтернативы. Компакция outbox усилена именованным инвариантом `INV-OUTBOX-SENT-AT-COMPACTION` (ADD1), метрики дополнены пятью новыми показателями и почасовой пробой дедупликации (ADD2, A1). `publish_epoch_owner: block14` из `contracts_in` подтверждён (FIX1). См. [errata-unified.md](errata-unified.md).

## Место в стеке старшинства

Второй уровень нормативного стека. Опирается на И1 (`depends_on: [I1-WAVE-A]`) —
инварианты И-1…И-6 обязательны как база. При расхождении с корпусом
`consolidated v3` и с И1 побеждает этот файл; над ним стоят И3, И4, Б17,
ERRATA-UNIFIED, SEAM-PATCH-1:

```
корпус v3 → И1 → И2 → И3 → И4 → Б17 → ERRATA-UNIFIED → SEAM-PATCH-1
```

Патч поднимает версию документа `consolidated v3.5-i1` → `consolidated v3.6-i2`.
Тип патча — добавляющий и **переопределяющий**: он даёт enforcement для
инвариантов И-1 и И-3 (которые в И1 были только контрактом), а также удаляет
из FSM участника состояния `banned_soft` и `banned_hard`.

## Главное переопределение: Р477 — состояния `banned_*` удалены

`participant_state_contract.fsm_participant` объявляет шесть состояний:
`pre_registered`, `onboarding`, `active`, `sleeping`, `muted`, `erased`.
Состояний `banned_soft` и `banned_hard` больше нет. Hard-block заменён на
`sleeping` + `author_pause` + owner-review; «бан навсегда» становится отдельной
процедурой через `hard_confirm`. Переходы `any → banned_soft` и
`any → banned_hard` внесены в `forbidden_automatic_transitions` и закрыты
CI-чеком `no_automatic_banned_transitions`, который блокирует релиз.

Это бьёт по блоку 7 и по артефакту долга
[debt/07-C1-ban-sanction-contract.md](../debt/07-C1-ban-sanction-contract.md)
(CLOSE(mech)/STUB, v3.2): всё, что там описано в терминах состояний `banned_*`,
читается через новую модель. Механика санкции сохраняется, носитель состояния
меняется. Требует ревизии текстов и команд в
[07-control-days-moderation.md](../07-control-days-moderation.md).

## Куда подшивается (перекрёстные ссылки)

| Что вводит И2 | Куда бьёт |
|---|---|
| `outbox_contract` (relay, retention, метрики, DLQ, партиции `pid_bucket`) | [14-data-durability.md](../14-data-durability.md), [09-communications.md](../09-communications.md), [appendix/B-failsafe-registry.md](../appendix/B-failsafe-registry.md) |
| `backup_contract` (tier-1 RPO 5м / RTO 60м, PITR-протокол) | [14-data-durability.md](../14-data-durability.md), [99-legal.md](../99-legal.md) |
| `participant_state_contract` (журнал `participant_events` + проекция, `view_integrity_check`) | [10-lifecycle-return.md](../10-lifecycle-return.md), [debt/10-D1-back-tree-transport.md](../debt/10-D1-back-tree-transport.md), [debt/10-D2-transport-passed-consents.md](../debt/10-D2-transport-passed-consents.md) |
| FSM участника без `banned_*` (Р477, Р479) | [07-control-days-moderation.md](../07-control-days-moderation.md), [debt/07-C1-ban-sanction-contract.md](../debt/07-C1-ban-sanction-contract.md), [00-glossary.md](../00-glossary.md) |
| `stage_flow` (единый триггер `stage_completed`, `publish_epoch`, withdrawn-логика) | [15-content-antipiracy.md](../15-content-antipiracy.md), [13-past-material-access.md](../13-past-material-access.md), [03-day-mechanics.md](../03-day-mechanics.md) |
| `pause_semantics` — три паузы, квота 14 дней/год, анти-цикл 24ч | [02-access-lives-pause.md](../02-access-lives-pause.md), [debt/02-C3-lives-pause-mercy.md](../debt/02-C3-lives-pause-mercy.md), [debt/07-C2-pause-shadow-contract.md](../debt/07-C2-pause-shadow-contract.md) |
| `life_ops` (границы 0…3, `FOR UPDATE` + advisory lock, ноль жизней → `sleeping`) | [02-access-lives-pause.md](../02-access-lives-pause.md), [06-participant-card.md](../06-participant-card.md) |
| `idempotency_keys`, `advisory_locks` (fencing-токен) | [16-payment.md](../16-payment.md), [15-content-antipiracy.md](../15-content-antipiracy.md), [debt/15-A3-outbox-dlq-saga-granularity.md](../debt/15-A3-outbox-dlq-saga-granularity.md) |
| `erasure_lifecycle` (cooling-off 48ч, `/unblock` без тихого downgrade) | [99-legal.md](../99-legal.md), [I1-wave-a.md](I1-wave-a.md) (Д-18), [debt/15-A4-nonreidentifiability-backup-erasure.md](../debt/15-A4-nonreidentifiability-backup-erasure.md) |
| `role_capability_matrix_i2_additions`, `hard_confirm_phrases` | [17-author-panel.md](../17-author-panel.md), `B17-admin-panel-patch.md` |
| `whitelist_recovery_procedure`, `privacy_audit_sla` (закрывают RISK-L-06/07 из И1) | [I1-wave-a.md](I1-wave-a.md), [14-data-durability.md](../14-data-durability.md) |
| `deferred_from_i2` | `I3-wave-c.md`, `I4-wave-d.md` |

Обратные ссылки «переопределено E1/E2/E3/E4/FIX1/FIX2» проставляются в этот
файл при обработке ERRATA-UNIFIED (куски 12a/12b). В `audit_additions_i2`
уже есть forward-ссылка на E2 («appeal_channel: Support (см. E2 в И3)») —
проверить при обработке И3 и ERRATA.

## Найденные дефекты исходника (перенесены дословно, не исправлены)

1. **Дублирующийся ключ.** `participant_state_contract.read_only_enforcement`
   содержит `db_role` дважды в одном маппинге. Строгий YAML-парсер падает,
   нестрогий молча оставляет только вторую роль (`participant_state_projector`),
   и роль `participant_state_reader` теряется целиком.
2. **Два противоречащих утверждения в одном файле.**
   `participant_state_contract.projection.kind: materialized_view` (со
   `refresh_strategy: incremental`), а ниже
   `audit_additions_i2.participant_state_storage_clarification.kind:
   regular_table_populated_by_projector` — прямо с обоснованием, почему
   materialized view не подходит. По расположению в файле побеждает второе,
   но первое не вычеркнуто.
3. `ci_checks_i2` → `no_free_text_shadow_reason`:
   `grep: "set_shadow.*reason=[^enum]"`. `[^enum]` — это класс символов
   «любой символ, кроме e, n, u, m», а не «кроме перечисления». Чек не делает
   того, что заявлено, и при этом помечен как покрывающий Р476.
4. **Пороги алертов в трёх разных форматах прозой**, машинно не разбираются:
   `60s → warn, 300s → critical`, `0.01 warn, 0.05 critical`,
   `10s warn, 60s critical`. Плюс `region: RU-Center (primary), RU-North (replica)`
   и `visible_to_participant: true (с плашкой "пауза от Автора")` — последнее
   парсится как строка, а не как булево, в отличие от одноимённых полей
   в `pause_shadow` и `user_pause`.
5. `erasure_lifecycle.P482_unblock_authorization` — ключи `/unblock (any branch)`
   и `/block` с пробелами, скобками и слэшем; в остальном файле ключи —
   идентификаторы. Плюс `/unblock` и `/block` существуют, а состояния
   `banned_*` удалены: чем именно управляют эти команды, в файле не сказано.
6. `pause_semantics.user_pause.removal.by_participant: allowed, refunds
   remainder to budget` — проза в значении, тогда как соседний
   `by_owner_via_unpause_user` — маппинг.
7. **Проза в полях списка долгов** (тот же дефект, что в И1):
   `closes_debts: [И-1 enforcement]`, `[RISK-L-07 mitigation]`,
   `[RISK-L-06 SLA]`, `[UX caveat from И1]`, `[D14 scepticism]`,
   `[Data caveat 1]`, `[Data caveat 2]`, `[Р446 hardening, RISK-L из скептика]`.
8. `outbox_contract.columns_add: [dlq_id (uuid), reason_code, ...]` — тип
   указан прозой внутри элемента списка, тогда как основные `columns` заданы
   маппингами `{name, type}`. Одна таблица описана двумя способами.
9. **Висячая таблица.** `outbox_system_events` упомянута только в комментарии
   внутри `partitioning` и в `RISK-L-08`; собственного контракта (колонки,
   retention, consumers) нет. При этом RISK-L-08 требует мержа двух потоков
   по `created_at` — это не даёт порядок при одинаковых метках времени.
10. `backup_contract.tier_1` включает `pii_access_log` с RPO 5 минут, но по
    И1 (`I_6`) приватностный аудит пишется best-effort через outbox. Гарантия
    бэкапа строже, чем гарантия записи; при падении outbox терять будет нечего,
    но SLA формально невыполним. `privacy_audit_sla` с порогом 4ч этот разрыв
    не снимает, а фиксирует.
11. Расхождение имён полей с И1: в capability-записях И2 используется
    `reason_source`, а схема таблицы в И1 объявляла `reason_required`.
    Ни одно из них не покрывает `mode` и `audit_layer` (дефект тянется из И1).
12. `life_ops` жёстко зашивает максимум жизней: `boundary: [0, 3]` и
    `IF current + delta > 3` прямо в SQL. Число не вынесено в конфигурацию,
    хотя по блоку 1 «контент и параметры — в конфигурации».
    Требует сверки с [02-access-lives-pause.md](../02-access-lives-pause.md).
13. `user_pause.annual_budget_default: 14` и `max_duration_per_activation: 7d` —
    требуют сверки с числами Паузы в блоке 2; в И2 они введены без ссылки на
    то, что там уже записано.
14. Артефакты `T1-ERASURE-INITIATE` и `F2` (`F2_close_event`) закрываются, но
    нигде в присланных частях не определены. `NR-17.4` в `P424` ссылается на
    нумерацию блока 17 — перекрёстную ссылку нужно проставить в обе стороны.
15. `hard_confirm_phrases.ui_contract.paste_event_blocked: true` заявлено как
    закрытие RISK-L-07, но в Telegram Mini App блокировка вставки не
    гарантируется платформой (клавиатурные и системные пути обходят
    `paste`-событие). Мера ослабляющая, а не запрещающая.
16. FSM подтверждает регистрационный тупик из И1: единственный вход —
    `pre_registered → onboarding` по триггеру `mini_app_first_consent`.
    Пути от `/start` в FSM нет, а глобальный kill-switch `miniapp_enabled`
    из И1 выключает единственный вход. Кандидат в ERRATA.
17. Состояние `muted` вводится впервые и отсутствует в
    [00-glossary.md](../00-glossary.md); `pre_registered` — тоже.
18. `closes_debts` внутри `outbox_contract.partitioning` вложен на уровень
    подсекции, а не рядом с остальными — сборщик реестра долгов, идущий по
    фиксированной глубине, его не увидит.
19. `stage_flow.R251_R252_survey_gate.penalty_for_unclosed_survey: none` со
    ссылкой «Р477 частный случай» — Р477 про состояния `banned_*`, а не про
    списание жизней; обоснование не по адресу.

## YAML — патч И2, Волна B (дословно)

```yaml
# =============================================================
# ПАТЧ И2 — ВОЛНА B: DURABILITY + PARTICIPANT STATE + ПАУЗЫ + LIFE-OPS
# Версия документа: consolidated-v3.5-i1 → v3.6-i2
# Дата: 2026-07-24
# =============================================================

meta:
  patch_id: I2-WAVE-B
  parent_doc_version: consolidated-v3.5-i1
  new_doc_version: consolidated-v3.6-i2
  applied_at: "2026-07-24"
  depends_on: [I1-WAVE-A]  # инварианты И-1…И-6 обязательны как база

# -------------------------------------------------------------
# DURABILITY LAYER — OUTBOX / DLQ / BACKUP / PARTITIONS
# -------------------------------------------------------------

outbox_contract:
  table: outbox_events
  columns:
    - {name: id, type: bigserial, pk: true}
    - {name: kind, type: text, index: true}          # e.g. publish_stage, stage_completed, refund_notice
    - {name: payload, type: jsonb}
    - {name: schema_version, type: int, not_null: true}
    - {name: publish_epoch, type: bigint, nullable: true}
    - {name: coalesce_key, type: text, nullable: true, index: true}
    - {name: created_at, type: timestamptz, default: now()}
    - {name: dispatched_at, type: timestamptz, nullable: true}
    - {name: consumer_offsets, type: jsonb, default: "{}"}   # {consumer_id: processed_at}
    - {name: pid, type: bigint, nullable: true, index: partial-not-null}
  partitioning:
    strategy: hash
    key: pid  # для событий без pid — отдельная non-partitioned таблица outbox_system_events
    partitions: 64
    partition_alias: pid_bucket
    closes_debts: [R280, R281]

  relay:
    mode: at_least_once
    dispatcher: outbox_relay_worker
    poll_interval_ms: 100
    batch_size: 500
    fair_share_across_consumers: true
    closes_debts: [R212]

  retention:
    rule: "delete WHERE all registered consumers acked AND created_at < now() - 30d"
    never_touch: "dispatched_at IS NULL OR consumer_offsets missing any required consumer"
    ci_check: "assert compaction never removes undispatched events"
    closes_debts: [R221]

  metrics:
    outbox_lag_seconds:
      formula: "now() - min(created_at) WHERE consumer_offsets incomplete"
      alert_threshold: 60s → warn, 300s → critical
    notification_dlq_rate:
      formula: "count(dlq) / count(dispatched) over 5min window"
      alert_threshold: 0.01 warn, 0.05 critical
    delivery_latency_p95:
      formula: "p95(dispatched_at - created_at)"
      alert_threshold: 10s warn, 60s critical
    alert_channel: admin_topic  # см. Б8
    closes_debts: [R222]

  dlq:
    table: outbox_dlq
    routing_rules:
      - trigger: "unknown schema_version"
        action: move_to_dlq
        reason_code: schema_unknown
    columns_add: [dlq_id (uuid), reason_code, first_failure_at, retry_count]
    replay_contract:
      command: /dlq_replay {dlq_id}
      idempotency: "keyed by dlq_id; result linked to operation_key"
    view_contract:
      command: /dlq_view [filter reason]
      access: owner_only
    closes_debts: [R263, Р490]

backup_contract:
  tier_1:
    rpo: 5min
    rto: 60min
    tables:
      - measurements_log
      - stage_publish_log
      - metric_catalog_log
      - pii_access_log
      - data_export_event
      - participant_events         # ← НОВОЕ, критично для FSM restore
      - outbox_events
      - erasure_blacklist
    strategy: continuous_archive + streaming_replica + hourly_snapshot
    region: RU-Center (primary), RU-North (replica)  # см. R352
    closes_debts: [R226]

  pitr:
    protocol:
      - identify_target_ts: manual by owner
      - stop_writes: maintenance mode via /panic_maintenance
      - restore_to_ts: pg_restore --target-time
      - reapply_erasure_blacklist: mandatory before service open  # Д-18
      - replay_outbox_from_target: at_least_once from consumer offsets
      - mark_recovery: audit event pitr_completed
    closes_debts: [R285]

# -------------------------------------------------------------
# PARTICIPANT STATE — READ-ONLY PROJECTION
# -------------------------------------------------------------

participant_state_contract:
  storage:
    event_log:
      table: participant_events
      append_only: true
      partitioned_by: pid_bucket
      columns: [id, pid, kind, payload, publish_epoch, at, actor, actor_role]
      indexes: [(pid, at), (kind, at)]
    projection:
      kind: materialized_view
      name: participant_state
      access: read_only  # RDBMS revoke UPDATE from all roles except projector
      refresh_strategy: incremental (event → apply → checkpoint)
      checkpoint_table: participant_state_checkpoints (pid, last_event_id, at)
    closes_debts: [R316]

  view_integrity_check:
    kind: scheduled_job
    frequency: hourly
    procedure: |
      For each pid sample (10% random or all if size < 10k):
        - replay events from last checkpoint
        - compare with current projection
        - divergence → alert both owners + freeze projection writes for pid
    log_table: state_integrity_check_log
    closes_debts: [R317]

  fsm_participant:
    states: [pre_registered, onboarding, active, sleeping, muted, erased]
    # Р477: banned_soft/banned_hard УДАЛЕНЫ из состояний
    #       hard-block заменён на sleeping с author_pause + owner-review
    #       ban как «навсегда» → отдельная процедура через ко-подпись (сейчас — hard_confirm)
    transitions:
      pre_registered → onboarding: {trigger: mini_app_first_consent, actor: system}
      onboarding → active: {trigger: onboarding_completed_and_paid, actor: system}
      active → sleeping: {trigger: any_of[user_pause, author_pause, pause_shadow, no_life, red_flag], actor: system_or_owner}
      sleeping → active: {trigger: pause_removed_and_lives_ok, actor: system_or_owner}
      active → muted: {trigger: antiflood_or_antispam, actor: system}
      muted → active: {trigger: mute_ttl_expired_or_owner_unmute, actor: system_or_owner}
      any → erased: {trigger: erasure_finalized, actor: owner_or_system_deadline}
      # ЗАПРЕЩЁННЫЕ переходы (CI enforced):
    forbidden_automatic_transitions:
      - any → banned_soft   # состояние удалено
      - any → banned_hard   # состояние удалено
      - active → erased without cooling_off_completed
    ci_guard_R477:
      grep_forbidden: ["UPDATE participant_state SET state='banned", "insert.*participant_events.*banned"]
      failure_action: block release
    closes_debts: [Р477, Р479]

  read_only_enforcement:
    db_role: participant_state_reader (SELECT only)
    db_role: participant_state_projector (SELECT + INSERT on projection tables)
    business_logic: "must use reader role except in Б10 projector process"
    ci_check: application code cannot connect with projector role outside Б10
    closes_debts: [И-1 enforcement]

# -------------------------------------------------------------
# STAGE FLOW & TRIGGERS
# -------------------------------------------------------------

stage_flow:
  R286_single_trigger:
    event: stage_completed
    schema:
      pid: int
      stage_id: text
      publish_epoch: bigint
      completion_kind: enum[time_based, task_based, open_ended]
      initiator: enum[system, owner_manual]
      at: timestamptz
    contract: "все пути к следующему этапу проходят ТОЛЬКО через stage_completed"
    consumers_in_i2: [Б14 (via outbox), participant_state projector]
    closes_debts: [R286]

  R220_new_module_availability:
    kind: materialization
    source_event: publish_stage
    target: new_module_availability_fact(pid, stage_id, since_epoch, until_epoch)
    producer_coalescing:
      owner_block: Б9
      key: (pid, stage_id, publish_epoch)
      window: 5s  # producer collapses; Б9 doesn't dedup further (Р204)
    closes_debts: [R220, Р220_producer_coalescing]

  R227_R228_R230_withdrawn:
    trigger: publish_stage{withdrawn: true, publish_epoch: E}
    actions:
      - "for participants with current_epoch < E and not started stage: rollback content_frontier"
      - "for participants who started stage: preserve progress (не откатываем)"
      - "for participants in stage_survey status: mark 'stalled'"
      - "on subsequent publish_stage{withdrawn: false, publish_epoch: E+1}: retrigger stage_completed for eligible"
    race_condition_note: "epoch comparison protects от race при одновременном старте участника и withdrawn"
    closes_debts: [R227, R228, R230]

  R251_R252_survey_gate:
    rule: "stage transition allowed IF stage_survey.status IN {done, partial_acknowledged}"
    penalty_for_unclosed_survey: none  # жизни не горят (Р477 частный случай)
    closes_debts: [R251, R252]

  R324_completion_kind_contract:
    # Полная логика в И3 (Чек-Ап)
    # В И2 фиксируем только FSM-контракт:
    open_ended:
      auto_completion: none
      manual_trigger_required: true
      manual_trigger_command: "/complete_stage {pid} {stage_id}"
      manual_trigger_actor: owner_only
      event_meta: {initiator: owner_manual}
    closes_debts: [R324_fsm_scope]

# -------------------------------------------------------------
# ТРИ СЕМАНТИКИ ПАУЗЫ (Р450/Р454) — ПОЛНАЯ РЕАЛИЗАЦИЯ
# -------------------------------------------------------------

pause_semantics:

  user_pause:
    fields_in_participant_state: [user_pause_at, user_pause_until, user_pause_reason_free]
    quota:
      table: user_pause_quota
      columns: [pid, days_budget_remaining_annual, cycle_start_at]
      annual_budget_default: 14  # дней; конфигурируется per cohort
      grant_events: [onboarding_bonus, refund_partial_makeup]
    activation:
      channel: mini_app_or_bot
      max_duration_per_activation: 7d
      min_gap_between_activations: 24h  # анти-цикл
      client_op_id_required: true  # для идемпотентности
    removal:
      by_participant: allowed, refunds remainder to budget
      by_owner_via_unpause_user:
        allowed: true
        rule: "unused portion RETURNS to budget; used days do NOT return"
        anti_cycle_rule: |
          Если Автор снял user_pause в момент T, следующий user_pause того же участника
          возможен не ранее T + 24h. Обход через shadow пауза Автором не блокируется
          (это разные механизмы).
    visible_to_participant: true
    closes_debts: [Р475]

  author_pause:
    fields: [author_pause_at, author_pause_until, author_pause_reason_code]
    activation:
      command: /pause_author {pid} {duration} {reason_code}
      actor: owner_only
      quota: none
      hard_confirm_required: false  # обратимая операция
    removal:
      command: /unpause_author {pid}
      actor: owner_only
    visible_to_participant: true (с плашкой "пауза от Автора")

  pause_shadow:
    fields: [shadow_pause_at, shadow_pause_until, shadow_pause_reason_code]
    activation:
      command: /set_shadow {pid} {duration} {reason_code}
      actor: owner_only
      reason_code_source: fixed_list  # Р476, свободный текст запрещён
      reason_codes_i2:
        - no_verdict          # Р236
        - content_frontier    # Р236
        - maintenance_overlap # Р236
        - review_pending      # ожидание решения Автора
        - safeguard_hold      # мягкая защитная пауза без объяснения участнику
    removal:
      command: /unset_shadow {pid}
      actor: owner_only
    visible_to_participant: false
    visible_to_moderator: false  # см. Б6, moderator_reduced
    audit_layer: privacy_audit
    closes_debts: [Р450, Р454, Р476]

  priority_for_delivery:
    order: [pause_shadow, author_pause, user_pause]
    semantics: |
      Если у участника активны любые две паузы одновременно (например, user + shadow),
      блок доставки применяется с приоритетом shadow. UI участнику показывает user_pause
      (shadow невидим). Плашки в карточке owner-а — три отдельные строки (Р454).

  ci_check_R477_pause:
    grep_forbidden: ["participant_state SET state='banned"]
    positive_check: "all 'no lives' branches lead ONLY to sleeping"
    closes_debts: [Р477_pause_scope]

# -------------------------------------------------------------
# LIFE-OPS (Р419/Р420) — ПОЛНАЯ РЕАЛИЗАЦИЯ
# -------------------------------------------------------------

life_ops:
  storage:
    field: participant_state.lives
    boundary: [0, 3]
  transaction_pattern:
    sql: |
      BEGIN;
      PERFORM pg_advisory_xact_lock(hashtext('life:' || pid));
      SELECT lives INTO current FROM participant_state WHERE pid = ? FOR UPDATE;
      -- delta check
      IF current + delta > 3 THEN RAISE 'life_above_max'; END IF;
      IF current + delta < 0 THEN RAISE 'life_below_zero'; END IF;
      -- event
      INSERT INTO participant_events (pid, kind, payload) VALUES (?, 'life_op', ?);
      COMMIT;
    idempotency: client_op_id required (Р443, 1h TTL)
  error_texts_key_only:  # тексты в И4 (UX-редактор)
    - life_below_zero
    - life_above_max
    - life_no_change_no_op
    - life_op_conflict_retry
  on_zero_lives_action: transition to sleeping (Р477 enforcement)
  closes_debts: [Р419, Р420]

# -------------------------------------------------------------
# IDEMPOTENCY & ADVISORY LOCKS — ПОЛНАЯ РЕАЛИЗАЦИЯ
# -------------------------------------------------------------

idempotency_keys:
  table: idempotency_keys
  columns: [key, kind, created_at, ttl, result_ref, params_hash_optional]
  primary_key: key
  ttl_by_kind:
    financial_ops: 24h
    erasure: forever
    life_op: 1h
    default: 1h
  stable_key_recipes:
    life_op: "life_op:{pid}:{client_op_id}"
    user_pause_grant: "user_pause:{pid}:{client_op_id}"
    stage_completed: "stage_completed:{pid}:{stage_id}:{publish_epoch}"
    refund: "refund:{payment_id}"  # one-shot; см. И3
  behavior_on_collision:
    same_result: return cached result_ref
    conflicting_params: return 409 + log conflict event
  gc:
    frequency: hourly
    action: DELETE WHERE created_at + ttl < now() AND kind != erasure
  closes_debts: [Р443, Р445]

advisory_locks:
  short_lived:
    kind: pg_advisory_xact_lock
    key_recipe: "hashtext('participant:' || pid)"
    scope: single_transaction
    use_cases: [life_op, pause_change, single_event_write]
  long_lived:
    kind: heartbeat_table
    table: long_running_ops
    columns: [op_id, pid, kind, started_at, last_heartbeat_at, expires_at]
    heartbeat_interval: 10s
    watchdog:
      frequency: 30s
      rule: "expires_at < now() → mark orphaned, release, alert operator"
    use_cases: [photo_ingest_saga, refund_saga, export_generation]
  closes_debts: [Р446, Р447]

# -------------------------------------------------------------
# ERASURE DURABILITY (расширяет Д-18 из И1)
# -------------------------------------------------------------

erasure_lifecycle:

  T1_erasure_initiate:
    trigger_channels: [participant_via_mini_app, owner_via_command, deadline_after_ban]
    cooling_off_hours:
      default: 48
      configurable_per_cohort: [24, 48, 72]
    event_on_initiate: erasure.initiated
    event_on_cancel_within_cooling_off: erasure.cancel_within_cooling_off
    event_on_finalize: erasure.finalized
    hard_confirm_required_for_owner_initiate: true  # из И1
    hard_confirm_required_for_bypass_cooling_off: true
    closes_debts: [T1-ERASURE-INITIATE]

  F2_close_event:
    kind: CLOSE
    push_policy:
      user_initiated: push_notification
      ban_expiry_or_deadline: silent
    text_source: legal_pack (pre-legal-review)  # F2 STUB закрывается юристом
    closes_debts: [F2_contract_scope]  # текст — на legal review

  P424_unblock_downgrade:
    context: "/unblock после того как PITR-окно доступно к восстановлению закрылось"
    forbidden: silent downgrade to fresh participant
    required_flow:
      - show_confirmation_screen (NR-17.4)
      - text: "Восстановить данные нельзя. Продолжить как новая регистрация?"
      - on_confirm: create new pid, link to tombstone(old_pid)
      - on_cancel: no-op, participant remains erased
    closes_debts: [Р424]

  P482_unblock_authorization:
    /unblock (any branch): owner_only
    /block: owner_only
    ci_check: "symmetry enforced; moderator role forbidden"
    closes_debts: [Р482]

# -------------------------------------------------------------
# АПДЕЙТ CAPABILITY MATRIX (расширяет И1)
# -------------------------------------------------------------

role_capability_matrix_i2_additions:
  - {role: owner, capability: unpause_user, allow: true}
  - {role: owner, capability: pause_author, allow: true}
  - {role: owner, capability: set_shadow, allow: true, reason_source: fixed_list}
  - {role: owner, capability: unblock_participant, allow: true, hard_confirm_required: true}
  - {role: owner, capability: block_participant, allow: true, hard_confirm_required: true}
  - {role: owner, capability: complete_stage_manual, allow: true, applies_to: open_ended_only}
  - {role: owner, capability: dlq_replay, allow: true, audit_layer: operational}
  - {role: owner, capability: dlq_view, allow: true, audit_layer: operational}
  - {role: moderator, capability: unpause_user, allow: false}
  - {role: moderator, capability: set_shadow, allow: false}
  - {role: moderator, capability: block_participant, allow: false}

# -------------------------------------------------------------
# HARD_CONFIRM ФРАЗЫ — уникальные per operation (замечание UX из И1)
# -------------------------------------------------------------
hard_confirm_phrases:
  table: hard_confirm_phrase_config
  columns: [operation_key, phrase, ver]
  entries_i2:
    whitelist_change: "ИЗМЕНИТЬ ДОСТУП"
    erasure_finalize_before_cooling_off: "УДАЛИТЬ БЕЗ ОТСРОЧКИ"
    unfreeze_piracy: "СНЯТЬ ЗАМОРОЗКУ"
    refund_rollback: "ОТКАТИТЬ ВОЗВРАТ"      # см. И3
    block_participant: "ЗАБЛОКИРОВАТЬ"
    unblock_participant: "СНЯТЬ БЛОКИРОВКУ"
  ui_contract:
    input_manual_typing_required: true
    paste_event_blocked: true  # закрывает RISK-L-07
    ci_check: "no operation reuses phrase; all phrases unique per version"
  closes_debts: [RISK-L-07 mitigation]

# -------------------------------------------------------------
# ЗАКРЫТИЕ СКЕПТИЧЕСКИХ ЗАМЕЧАНИЙ ИЗ И1
# -------------------------------------------------------------

whitelist_recovery_procedure:  # RISK-L-06 scoped
  key_storage:
    location_1: owner_1 offline (encrypted USB or password manager with 2FA)
    location_2: owner_2 offline (same)
    location_3: notary_deposit_or_bank_safe_deposit_box
  recovery_flow_if_both_owners_lose_keys:
    - written_application_to_operator (legal entity of owner_1 or owner_2)
    - identity_verification (notarized)
    - generate new keypair by both parties
    - re-sign whitelist bootstrap file with new key
    - publish new public key to service
    - audit event whitelist_recovery_completed
  slas:
    from_incident_to_recovery: "up to 30 days (external legal steps)"
    service_state_during: panic_mode (webhook off, only /status responds)
  closes_debts: [RISK-L-06]

privacy_audit_sla:
  metric: privacy_audit_lag_seconds
  threshold_warn: 60s
  threshold_critical: 4h  # RISK-L-06 requirement
  fallback_on_s3_outage:
    write_locally: append to local WAL file on host
    resync_when_available: batch flush + verify + delete local WAL
  closes_debts: [RISK-L-06 SLA]

d14_write_before_render:
  contract: |
    Явный чекбокс согласия при первом запуске Mini App (Д-14) записывает
    consent_event в outbox ДО показа участнику подтверждения. Если outbox
    не подтвердил в течение 3s, участник видит чекбокс снова (write-before-render).
  ci_check: "no confirmation screen renders without prior outbox ack"
  closes_debts: [D14 scepticism]

# -------------------------------------------------------------
# ЯВНЫЕ ПЕРЕНОСЫ В И3/И4
# -------------------------------------------------------------
deferred_from_i2:
  to_i3_wave_C:
    - refund_saga_full (Р421, Р442, Р443_saga, Р457, Р458, Р465, Р467, Р496)
    - photo_ingest_saga (R295, R331, R334, R335, R349, R350, R351, R379_full, R383, R384)
    - checkup_full (R234, R235, R236, R237, R279, R284, R305, R306, R307, R308, R324_logic)
    - red_zone (Д-09, Д-10, Д-11, Д-12)
    - baseline_override (R358, Р488)
    - stage_survey_open (R234/R235 continue)
    - stage_publish_epoch_full (Р489)
  to_i4_wave_D:
    - error_texts life_ops (life_below_zero, life_above_max, life_no_change_no_op, life_op_conflict_retry)
    - error_texts idempotency_conflict
    - texts_B9_all (R253, R271, R283, R361, R366, R381)
    - mini_app_full (R338-R380)
    - themes (R288, Р481, Р493, Р497)
    - graph (Р462, Р464)
    - buttons_tone (Р207, Р258, NR-213, NR-215)

# -------------------------------------------------------------
# CI-CHECKS СВОДКА ПО И2 (все обязательны в pipeline)
# -------------------------------------------------------------
ci_checks_i2:
  - name: no_automatic_banned_transitions
    grep: ["banned_soft", "banned_hard", "state='banned"]
    scope: exclude tests
    on_match: block release
    covers: [Р477]
  - name: no_direct_participant_state_update_outside_projector
    grep: "UPDATE participant_state"
    exclude_paths: [Б10/projector/]
    on_match: block release
    covers: [И-1, R316]
  - name: no_free_text_shadow_reason
    grep: "set_shadow.*reason=[^enum]"
    covers: [Р476]
  - name: outbox_compaction_never_removes_undispatched
    kind: unit_test
    covers: [R221]
  - name: destructive_ops_have_hard_confirm
    kind: static_analysis
    covers: [И1 hard_confirm]
  - name: all_hard_confirm_phrases_unique
    kind: config_validation
    covers: [UX caveat from И1]
# -------------------------------------------------------------
# ДОПОЛНЕНИЯ ПО РЕЗУЛЬТАТАМ АУДИТА И2
# -------------------------------------------------------------

audit_additions_i2:

  projector_lag_metric:
    name: projector_lag_events
    formula: "participant_events.max(id) - participant_state_checkpoints.max(last_event_id)"
    alert_warn: 1000
    alert_critical: 10000
    covers: [Data caveat 1]

  consumer_idempotency_rule:
    rule: "all outbox consumers must dedup by event.id in addition to idempotency_keys"
    ci_check: "consumer implementations register dedup on init"
    covers: [Data caveat 2]

  pause_anti_cycle_scope:
    rule: "anti-cycle 24h применяется только к user_pause↔unpause_user циклу"
    cross_semantics: "author_pause и pause_shadow — независимые механизмы"
    appeal_channel: Support (см. E2 в И3)
    covers: [Р475 clarification]

  advisory_locks_fencing:
    long_lived_lock_returns: {lock_id, fencing_token: monotonic_int}
    external_ops_carry_token: true
    external_writes_verify_token: "reject if incoming_token < current_max for lock_id"
    covers: [Р446 hardening, RISK-L из скептика]

  participant_state_storage_clarification:
    kind: regular_table_populated_by_projector
    reason: "MVCC гарантирует consistent read; REFRESH MATERIALIZED VIEW блокирует читателей"
    writes: "INSERT ... ON CONFLICT (pid) DO UPDATE by projector role only"
    covers: [R316 hardening]

# -------------------------------------------------------------
# РЕЕСТР РИСКОВ (продолжение из И1: RISK-L-06/07)
# -------------------------------------------------------------
risk_registry_additions_i2:
  RISK-L-08:
    title: "Порядок событий между outbox_events и outbox_system_events"
    mitigation: "merge by created_at on consumer side"
    severity: medium
    review_frequency: quarterly
  RISK-L-09:
    title: "Хеш-коллизии advisory lock keys при cohort > 10^6"
    mitigation: "acceptable degradation; upgrade to 64-bit hash при триггере"
    severity: low
    trigger_threshold: 500k participants
  RISK-L-10:
    title: "CI grep false positives по banned_"
    mitigation: "контекстный grep по state=/kind:"
    severity: low
```
