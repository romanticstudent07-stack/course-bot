---
file: debt/15-A1-guarded-transition.md
block: 15
title: "Артефакт долга A1 — guarded_transition (необратимые переходы в erased)"
node: A1
attach_to: "подшить под → БЛОК 15"
outcome: CLOSE
status: CLOSE, v3.2
doc_version: "consolidated v3"
contains: [выжимка, interface contract yaml, stub-хвосты, park]
---

# [АРТЕФАКТ ДОЛГА · подшить под → БЛОК 15 · узел A1 · CLOSE · v3.2]

осн. адресат Б15/Инфра; STUB-хвост → Legal (основание/обратимость system_fraud-erasure); PARK → Б15/A3 (гранулярность outbox-строки саги)

## Выжимка

Все необратимые переходы в терминальное состояние erased выполняются единым примитивом guarded_transition(target, predicate), реализованным как UPDATE participants SET phase=target, … WHERE `<predicate>` RETURNING id. Пустой результат (0 строк) = silent_noop — штатное, не-алертируемое поведение проигравшего CAS-гонку; наблюдаемость только метрикой.

Существует два guard-предиката, сходящихся в одно терминальное erased: condition_pending_erasure (phase==pending_erasure AND cooling_off_expired AND not_cancelled) для трёх initiator-путей (user, author, system_fraud) и condition_ban (ban==active AND not_lifted) для четвёртого пути ban_window_expiry. Различие путей — не «окно/без окна», а владелец отмены и триггер закрытия окна; закрытие окна и старт саги — один атомарный CAS-переход.

Примитив фиксирует только терминальную фазу и ставит задачу erasure_saga_start в outbox в той же транзакции (Outbox-инвариант Б15) — тело саги (run_canonical_deletion → break_identity_irreversible → anonymize_rest) исполняется из outbox и принадлежит зоне A3, не A1.

Корректность конкуренции обеспечена без нового поля: row-lock на строке participants как арбитр (leader_election: NOT_NEEDED), предикатный CAS с обязательным пересечением полей предиката и конкурента, фазовая эксклюзивность (lifecycle_phase: exclusive_enum) и консервация модификаторов при входе в pending_erasure. Все компоненты предиката выводимы из состояния Postgres (таймеры — durable-строки с fire_at, время now() БД; отмена — журналируемый переход фазы), внешний планировщик/Redis как источник истины не используется. Инвариант INV-A1-PREDICATE-LOCALITY требует, чтобы компоненты предиката из отдельных таймер-таблиц читались под FOR UPDATE/SERIALIZABLE/переносом в строку — READ COMMITTED + голый join недостаточен.

Предикаты not_cancelled / cooling_off_expired / not_lifted — юридически обязательные части guard'а (GDPR Art.17 / окно отмены), а не оптимизация: без них код удаляет внутри окна отмены. guard_version НЕ вводится — понижен до опционального усиления на вырост (только при появлении guarded-перехода с предикатом, не пересекающимся по полям ни с одним конкурентом).

## Interface Contract (YAML)

```yaml
artifact: A1_guarded_transition
file_under: {block: 15, node: A1, outcome: CLOSE, version: v3.2}
owner: Б15/Инфра

primitive:
  name: guarded_transition
  form: "UPDATE participants SET phase=:target, ... WHERE :predicate RETURNING id"
  empty_result: silent_noop        # штатное, НЕ алерт; наблюдаемость = метрика cas_noop_count
  concurrency_arbiter: postgres_row_lock_on_participants   # leader_election: NOT_NEEDED
  fencing: predicate_CAS + phase_exclusivity + ban_snapshot_conservation
  new_columns: none                # guard_version НЕ вводится

guards:
  condition_pending_erasure:
    applies_to: [initiator_user, initiator_author, initiator_system_fraud]
    predicate: "phase=='pending_erasure' AND cooling_off_expired AND not_cancelled"
    expected_phase: pending_erasure
  condition_ban:
    applies_to: [ban_window_expiry]
    predicate: "ban=='active' AND not_lifted"   # смотрит на ban_mod, НЕ на phase
    timer: ban_window_fire_at         # cancel_window_days:7 (Р106), не cooling_off

entry_paths:                          # 4 входа != 4 initiator (3 initiator enum + 1 ban-path)
  initiator_user:        {owner: subject, cancel: user_within_cooling_off, reason: gdpr_art17}
  initiator_author:      {owner: author,  cancel: author, reason: admin_delete}
  initiator_system_fraud:{owner: system,  cancel: appeal_until_legal_deadline, reason: fraud, legal: STUB}
  ban_window_expiry:     {owner_rule: Б7, owner_reaction: Б10, cancel: author_unlock_🔓_Р108, reason: ban_window_expiry}

atomicity:
  transition_plus_outbox: same_transaction   # Outbox-инвариант Б15; разрывает dual-write
  saga_start_event:
    type: erasure_saga_start
    fields: {participant_id, entry_path, reason, idempotency_key, v}
    idempotency_key: "<participant_id>-erasure-<entry_path>"   # таймер-безопасно, не update_id
  saga_body_owner: Б15/A3            # A1 не инлайнит тело саги

invariants:
  INV-A1-PREDICATE-LOCALITY:
    rule: "каждый компонент guard-предиката либо поле строки participants (a),
           либо durable-таймер-строка, читаемая под FOR UPDATE / SERIALIZABLE /
           перенесённая в participants (b). READ COMMITTED + голый join = НЕДОСТАТОЧНО."
    rationale: "иначе EPQ-окно между чтением таймера и захватом строки → воскрешает fencing по существу"
  legal_predicates_mandatory: "not_cancelled / cooling_off_expired / not_lifted — юр.обязательны (Art.17)"

failure_mode:
  cas_lost_race: silent_noop         # без алерта
  crash_between_update_and_outbox: impossible   # одна транзакция; повтор через at-least-once таймер
  observability: metric cas_noop_count by entry_path

stub_tails:
  - {to: Legal, what: "основание и обратимость initiator_system_fraud до legal-deadline"}
park:
  - {to: Б15/A3, what: "гранулярность outbox-строки саги: 1 строка-state vs N-per-stage (не закрыто в архиве)"}
```
