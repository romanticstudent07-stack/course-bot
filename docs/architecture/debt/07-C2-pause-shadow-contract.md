---
file: debt/07-C2-pause-shadow-contract.md
type: артефакт долга
artifact: C2_pause_shadow_contract
file_under_block: 7
node: C2
outcome: CLOSE
version: v3.2
owner: "Б7 (свод Б7.7 + Б2.П11 + Б10-Р119)"
tail_to: [C4]
---

# [АРТЕФАКТ ДОЛГА · подшить под → БЛОК 7 · узел C2 · CLOSE · v3.2]

осн. адресат Б7 (свод); STUB-хвостов нет; хвост → C4 (maintenance-вход, владение Инфра)

**Выжимка.** pause_shadow — единый модификатор (Р57 single_modifier:true) с тремя reason: no_verdict (описан в Б7.7 фаза C), content_frontier (введён Б10-Ш1, caught_up_inside_paid_stage, НЕ в Б7.7), maintenance (глобальный техрежим, НЕ в Б7.7). Резолвер обходится одинаково; выход и текст экрана зависят от reason. C2 сводит в один контракт Б7.7 (фазы A/B/C) + Б2.П11 (квота=0, санкций 0, жизни/таймеры frozen) + Б10-Р119 (выход с остатка дедлайна, авто-триггер).

**Ключевые решения.** Р-C2.1 — три входа/выхода: no_verdict→вердикт Автора; content_frontier→выкладка контента; maintenance→снятие флага. Р-C2.2 — маскировка (Б10): participant_aware:false, «не раскрывать тайность, ноль срочности», Пауза hidden в матрице Ш4. Р-C2.3 — выход авто, не через [Старт] (Р120d); дедлайн размораживается ровно с остатка (анти-сгорание + анти-эксплойт). Р-C2.4 (Скептик) — maintenance перехватывается ДО резолвера (Р68) и имеет визуальный приоритет над экраном pause_shadow; при снятии — возврат к базовому reason. НЕ кладётся в приоритетную лестницу резолвера.

```yaml
artifact: C2_pause_shadow_contract
file_under: {block: 7, node: C2, outcome: CLOSE, version: v3.2}
owner: Б7 (свод Б7.7 + Б2.П11 + Б10-Р119)
model:
  single_modifier: true   # Р57; резолвер одинаков
  reasons: [no_verdict, content_frontier, maintenance]
  quota_impact: none        # Б2.П11
  sanctions: none
  lives_timer: frozen
  participant_aware: false  # маскировка
entries_exits:
  no_verdict:       {source: Б7.7_phase_C, exit: author_verdict}
  content_frontier: {source: Б10-Ш1, exit: content_published}   # NR относительно Б7.7
  maintenance:      {source: infra_global_flag, exit: maintenance_cleared, owner: C4}   # NR
exit_mechanics:    # Б10-Р119
  trigger: auto   # НЕ через [Старт] (Р120d)
  deadline: unfreeze_from_remainder   # анти-сгорание + анти-эксплойт
  edge: "вошёл с горящим дедлайном → вышел с тем же остатком"
invariants:
  INV-C2-MASK: "экран не раскрывает тайность, ноль срочности; Пауза hidden (Ш4)"
  INV-C2-MAINT-PRERESOLVER: "maintenance перехват ДО резолвера (Р68), визуальный приоритет над pause_shadow-экраном; НЕ в лестнице резолвера; снятие→возврат к базовому reason"
tail:
  - {to: C4, what: "maintenance-вход: владение глобальным флагом + техэкран (Инфра); C2 фиксирует только как reason"}
```
