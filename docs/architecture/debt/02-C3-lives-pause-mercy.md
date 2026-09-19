---
file: debt/02-C3-lives-pause-mercy.md
type: артефакт долга
artifact: C3_lives_pause_mercy
file_under_block: 2
node: C3
outcome: CLOSE
version: v3.2
owner: Б2
tail_to: Б9
---

# [АРТЕФАКТ ДОЛГА · подшить под → БЛОК 2 · узел C3 · CLOSE · v3.2]

осн. адресат Б2; STUB-хвостов нет; тексты экранов выхода/милосердия → Б9

**Выжимка.** Милосердие = два ортогональных примитива Автора: (а) ±жизнь (Б2.5 manual_life_ops, atomic, границы [0,3], работает всегда — независимая операция над счётчиком); (б) ±позиция/откат (предохранитель, /revert по правилам Б2.6). Примитивы применяются независимо. revive_by_author = их атомарная композиция (жизнь + обязательный откат) как выход из block_lives, отличная от restart_paid (полный сброс: reset_progress_to: current_stage_start, restore_lives:3, reset pause_quota, сохранение payment+measurements). Два разных выхода из block_lives — разные события/экраны/метки журнала.

**Ключевые решения.** Р-C3.1 — два ортогональных примитива, независимы как инструменты Автора. Р-C3.2 — revive_by_author = композиция жизнь+откат; обязателен именно из block_lives (иначе жизнь на застрявшем дне сгорит снова циклом «2 пропуска»). Р-C3.3 (Скептик, NR-инвариант) — композиция revive_by_author атомарна одной транзакцией Б2 (жизнь+позиция вместе); иначе окно между ними даёт повторное сгорание. atomicity_owner: block_2 (симметрично restart_paid). Р-C3.4 — событие «досрочный выход из паузы»: Б10 просит (send_event_to_block_2), Б2 исполняет, b10_removes_itself:false. Р-C3.5 (разграничитель) — две модели выхода: pause_user → ближайший 00:00 (Б2.П6, чистые таймеры); pause_shadow → остаток дедлайна (C2/Р119). C3 владеет только pause_user-выходом. Граница: Б10 = переход block_lives→active (remove_modifier, set_active, refresh_screen_and_start, log_reason), принимает позицию (b10_reads_facts_not_computes), метит restart_paid|revive_by_author. Атомарность всех операций с жизнями — Б2.

```yaml
artifact: C3_lives_pause_mercy
file_under: {block: 2, node: C3, outcome: CLOSE, version: v3.2}
owner: Б2
mercy_primitives:   # ортогональны, независимы
  life_delta:    {source: Б2.5, atomic: true, bounds: [0,3], scope: always}
  position_revert: {source: Б2.6, is: /revert, standalone: true}
block_lives_exits:   # два разных, разные события/метки
  revive_by_author:
    composition: [life_delta, mandatory_position_revert]
    atomicity: single_transaction   # Р-C3.3 NR — жизнь+позиция вместе
    atomicity_owner: block_2
    why_mandatory_revert: "иначе жизнь на застрявшем дне сгорит снова (2-пропуска)"
  restart_paid:
    type: multi_field_atomic
    effects: [reset_progress_to_current_stage_start, restore_lives_3, reset_pause_quota]
    preserve: [payment, measurements_journal]
pause_early_exit:
  request: Б10 send_event_to_block_2
  execute: Б2
  b10_removes_itself: false
  exit_models:   # Р-C3.5 разграничитель
    pause_user: nearest_00_00   # Б2.П6, чистые таймеры
    pause_shadow: from_remainder   # C2/Р119, НЕ в зоне C3
boundary:
  Б10_owns: "block_lives→active: remove_modifier/set_active/refresh/log_reason; принимает позицию, НЕ вычисляет"
  Б2_owns: "атомарность всех операций с жизнями; lives_race out_of_scope_for_Б10"
tail: {to: Б9, what: "тексты экранов miloserdie/выхода из паузы"}
```
