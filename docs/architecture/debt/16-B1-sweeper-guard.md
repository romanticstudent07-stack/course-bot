---
file: debt/16-B1-sweeper-guard.md
block: 16
title: "Артефакт долга B1 — sweeper-guard, три-осевой guard-предикат доставки"
node: B1
attach_to: "подшить под → БЛОК 16"
outcome: CLOSE
status: CLOSE, v3.2
doc_version: "consolidated v3"
contains: [выжимка, инварианты, interface contract yaml, deferred_NR]
---

# [АРТЕФАКТ ДОЛГА · подшить под → БЛОК 16 · узел B1 · CLOSE · v3.2]

осн. адресат Б16; STUB-хвостов нет (тексты no-op не требуются — молчаливое подавление)

## Выжимка

Долг R153: sweeper (background_reconciler) и основной путь delivery_flow до-выдают/выдают доступ по единственному guard'у payment_status == confirmed, не читая фазу Б10. Дыра: после подтверждения оплаты участник в pending_erasure / ban / out_of_scope получал бы контент (нарушение Р109: ban/erasure > доставка) либо создавался бы PII-след в delivery_registry для стираемого участника.

Решение — три-осевой guard-предикат, применённый inline на обоих путях, с семантикой suppress-without-finalize:

Guard на обоих путях. И delivery_flow (перед send_day_1), и background_reconciler (перед re-deliver) проверяют три ортогональные оси Б10: lifecycle_phase, visibility, ban_mod. Провал любой → no-op.

Inline в claim-WHERE (NR). Чтение трёх осей и claim строки — одна атомарная операция в одном WHERE. Отдельная проверка после claim запрещена (TOCTOU). В корпусе Б16 claim/phase-read не разнесены — противоречия нет; inline — новая, но единственно корректная по A1 реализация.

Suppress ≠ Finalize (Р-B1.3, ядро). При провале guard'а выдача подавляется БЕЗ записи в оси доставки: day_delivered не трогается, промежуточных флагов не вводится. Расхождение confirmed AND NOT day_delivered остаётся жить как носитель долга — при возврате в active (разбан / отмена erasure) sweeper переоценит его по актуальной фазе и до-выдаст. Финализация здесь стёрла бы триггер безвозвратно.

Приоритет Р109 > Б16.4. Для pending_erasure запрещено любое создание PII-следа в delivery_registry (согласовано с INV-A3-REF-PURITY и irreversible-erasure из A1).

Два флага, без третьего состояния. delivery_suppressed отклонён как основной механизм: он вводит переход suppressed → queue при возврате в active, который сам требует guard'а и порождает trap-state (разбан без обратного перехода), дублируя фазу как источник истины. Отложен в NR строго как перф-маркер под конкретный триггер (скан тормозит И трёх-осевой индекс исчерпан И горячий путь) — до того YAGNI.

## Инварианты

INV-B1-GUARD-BOTH-PATHS — guard применяется на delivery_flow И background_reconciler; ни один путь выдачи не минует три-осевую проверку.

INV-B1-SUPPRESS-NO-TRACE — подавление по фазе не оставляет следа ни в одной оси доставки (финализация — частный случай нарушения).

INV-B1-PHASE-LOCALITY (наследует INV-A1-PREDICATE-LOCALITY) — все три оси guard'а (lifecycle_phase, visibility, ban_mod) читаются как durable-строки того же Postgres в транзакции claim; вынос фазы Б10 во внешний источник (Redis/сервис) ломает atomicity inline-guard и запрещён.

## Interface Contract (YAML)

```yaml
# Interface Contract · B1 · sweeper-guard
owner: Б16 (delivery_flow + background_reconciler)
depends_on:
  - Б10.lifecycle_phase   # durable в participants (INV-B1-PHASE-LOCALITY)
  - Б10.visibility        # durable
  - Б10.ban_mod           # durable

guard_predicate:
  applied_at: [delivery_flow.before_send_day_1, background_reconciler.before_redeliver]
  form: inline_in_claim_where          # атомарно с захватом строки; отдельная проверка запрещена (TOCTOU)
  pass_condition:
    lifecycle_phase: active
    visibility: NOT out_of_scope
    ban_mod: NOT active
  on_fail: silent_noop                 # без alert; наследует A1 silent_noop

sweeper_scan:
  trigger: [on_bot_start, periodic]
  select: "confirmed = true AND day_delivered = false AND <guard_predicate>"
  action: re-deliver

suppress_semantics:
  finalize_on_suppress: false          # Р-B1.3: day_delivered НЕ трогается
  intermediate_flag: none              # два флага; delivery_suppressed отклонён
  rationale: расхождение = durable-носитель долга; переоценка sweeper'ом по фазе при возврате в active

idempotency: participant_id + day  (наследует Б16.8; ручной/провайдерский confirmed не дублируются)
priority: Р109 (ban/erasure) > Б16.4 (delivery)
pii_rule: pending_erasure → запрет записи в delivery_registry (INV-A3-REF-PURITY)
failure_mode: guard_fail → silent_noop; расхождение сохраняется для повторного скана
schema_version: v3.2
deferred_NR:
  delivery_suppressed: perf-marker only; trigger = scan_slow AND index_exhausted AND hot_path
```
