---
file: debt/infra-C4-maintenance-contract.md
block: "Инфра (трёхзвенный контракт Инфра ↔ Б15 ↔ Б10)"
title: "Артефакт долга C4 — контракт maintenance (заморозка дедлайнов)"
node: C4
attach_to: "подшить под → БЛОК Инфра (связан с Блоком 15, Шаг 5.6, и Блоком 10)"
outcome: CLOSE
status: CLOSE, v3.2
doc_version: "consolidated v3"
contains: [выжимка, ключевые решения Р-C4.1–Р-C4.4, границы, interface contract yaml, stub-хвост Б9]
---

# [АРТЕФАКТ ДОЛГА · подшить под → БЛОК Инфра · узел C4 · CLOSE · v3.2]

осн. адресат Инфра; STUB-хвост → Б9 (текст техэкрана)

## Выжимка

Maintenance = трёхзвенный контракт: Инфра ставит глобальный флаг + durable-окно [maintenance_start, maintenance_end] → Б15 гарантирует незгорание дедлайнов через reconciler catch-up (семантическая заморозка, БЕЗ bulk-сдвига fire_at) → Б10 читает флаг и рисует Р68-техэкран (перехват до резолвера, выше ban_mod). Новых таймерных сущностей сверх Б15-Ш5 нет — переиспользуется durable-таймеры + механизм 2 catch-up (Ш5.6).

## Ключевые решения

Р-C4.1 — заморозка семантическая: окно downtime исключается из расчёта дедлайна при re-check (не физическая мутация fire_at). Р68 «дедлайны заморожены» истинен, т.к. reconciler при снятии гарантирует незгорание. Р-C4.2 — catch-up вместо bulk-UPDATE: избегает тяжёлой записи по горячей таблице, риска частичного сбоя, и идемпотентен (окно — факт, повторное применение no-op). Р-C4.3 (Скептик, NR-инвариант) — вычитается пересечение окна maintenance с интервалами активности таймера, не полная длительность maintenance. Для замороженного (pause_user/shadow) участника пересечение=0 → нет двойной заморозки. Наследует hard_rule «заморозка > catch-up» (Ш5.6). Р-C4.4 (Скептик) — maintenance_end фиксируется по now() БД в момент фактического снятия флага, не по плану (затянувшийся maintenance считается по факту). Границы: maintenance-reason (C2) = тот же флаг на per-user экране, Р68 перехватывает раньше shadow-маски; R151 (Postgres down) ортогонален плановому maintenance.

## Interface Contract (YAML)

```yaml
artifact: C4_maintenance_contract
file_under: {block: infra, node: C4, outcome: CLOSE, version: v3.2}
three_tier:
  infra:  {owns: [global_maintenance_flag, durable_window], contract: to_infra_maintenance}
  block15: {guarantees: no_deadline_burn, via: reconciler_catchup_Ш5.6, new_entity: none}
  block10: {reads: flag, draws: Р68_screen, intercept: before_resolver_above_ban_mod, computes: false}
freeze_model:
  type: semantic   # НЕ bulk-UPDATE fire_at
  window: [maintenance_start, maintenance_end]   # durable
  recheck: reconciler_on_clear   # окно исключается из расчёта дедлайна
  idempotent: true   # окно = факт, повторное применение no-op
invariants:
  INV-C4-INTERSECTION: "вычитать пересечение(окно, активные_интервалы_таймера), НЕ полную длительность; замороженный участник → пересечение=0 (анти-двойная-заморозка; наследует 'freeze > catch-up' Ш5.6)"
  INV-C4-END-BY-FACT: "maintenance_end = now() БД при фактическом снятии, не по плану"
  INV-C4-Р68-TRUE: "ни один дедлайн не горит внутри окна — гарантия reconciler при снятии, не мутация fire_at"
boundaries:
  c2_maintenance_reason: "тот же флаг; Р68 перехват раньше shadow-маски"
  r151_postgres_down: orthogonal   # не смешивать с плановым maintenance
tail: {to: Б9, what: "текст техэкрана maintenance (Р68)"}
```
