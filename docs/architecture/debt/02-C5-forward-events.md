---
file: debt/02-C5-forward-events.md
type: артефакт долга
artifact: C5_b2_forward_events
file_under_block: 2
node: C5
outcome: "CLOSE(события)"
version: v3.2
owner: Б2
forward_to: Б10
tail_to: Б9
---

# [АРТЕФАКТ ДОЛГА · подшить под → БЛОК 2 · узел C5 · CLOSE(события) · v3.2]

осн. адресат Б2; адресат-форвард Б10; STUB-хвост → Б9 (тексты всех событий)

**Выжимка.** C5 — замок эшелона C: сводит полный каталог форвард-событий Б2→Б10 (смена состояния), не вводя новых сущностей. Каталог: pause_start / pause_end(early_exit) / pause_reschedule (Б2 П.1–П.8, модификатор pause_user, не фаза); restart_paid (C3, multi-field atomic); revive_by_author (C3, композиция жизнь+откат); lives_reached_zero→block_lives и block_lives_cleared (следствие life_delta, не сама дельта). Каждое — абсолютный идемпотентный guarded_transition (Р-A1) с log_reason.

**Ключевые решения.** Р-C5.1 — в Б10 приходит следствие life_delta (переход модификатора block_lives), НЕ сырая дельта; счётчик 1/2/3 = status, не state (b10_reads_facts_not_computes). Р-C5.2 — pause_reschedule = правка (Б2.П7 consumes_limit:false), обновление атрибутов, не новый переход; extra_pause(П.9) = pause_start с атрибутом, не новое событие. Р-C5.3 (граница-замок) — системные заморозки НЕ в каталоге Б2: sleeping/archive=Б16 (freeze_unpaid+visibility), pause_shadow=C2 (Б7/Инфра), maintenance=C4, erasure=A1/Legal. Чистая граница владения, не пробел.

```yaml
artifact: C5_b2_forward_events
file_under: {block: 2, node: C5, outcome: "CLOSE(события)", version: v3.2}
owner: Б2
forward_to: Б10
catalog:   # полон; новых сущностей нет
  pause_start:      {source: Б2.П1-8, effect: set_modifier(pause_user)}
  pause_end:        {source: early_exit, note: "Б10 просит, Б2 исполняет; b10_removes_itself:false"}
  pause_reschedule: {source: Б2.П7, is: edit, consumes_limit: false}   # не новый переход
  restart_paid:     {source: C3, type: multi_field_atomic}
  revive_by_author: {source: C3, type: composition_life_plus_revert}
  lives_reached_zero: {source: Б2/Б7 Р56, effect: set_modifier(block_lives)}
  block_lives_cleared: {source: revive/restart, effect: remove_modifier}
life_delta_note: "±жизнь = операция над status-счётчиком; в Б10 приходит СЛЕДСТВИЕ (block_lives ±), не дельта"
transport: {form: guarded_transition_Р-A1, idempotent: true, on_race: silent_noop, carries: log_reason}
boundary_not_b2:   # замок: чужие контракты
  sleeping_archive: Б16   # freeze_unpaid + visibility
  pause_shadow: C2        # Б7/Инфра
  maintenance: C4
  erasure: A1/Legal
tail: {to: Б9, what: "тексты всех форвард-событий"}
```
