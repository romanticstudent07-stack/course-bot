---
file: 15/15-07-tempo-detection-suspension.md
block: 15
title: "Шаг 7 — Детекция подозрительного темпа и мягкая приостановка"
status: закрыт
doc_version: "consolidated v3"
contains: [Шаг 7, инвариант, критерий триггера, реакция, guard-паттерн, алерт, снятие, разграничение, крючки, yaml step_7]
---

# БЛОК 15 · ШАГ 7 — ДЕТЕКЦИЯ ПОДОЗРИТЕЛЬНОГО ТЕМПА И МЯГКАЯ ПРИОСТАНОВКА

Шаг 7 — сигнальная надстройка над жёстким лимитом Шага 6: распознаёт конкретный паттерн — методичный последовательный обход дерева заданий. Не герметичен: против съёмки камерой, нелинейного перечитывания и медленного сбора «по чуть-чуть» бессилен — осознанный компромисс из Шага 6.

Железный инвариант: приоритет — не наказать честного участника; любая неоднозначность — в пользу пользователя. Поэтому критерий узкий: честный ученик перечитывает нелинейно, «сборщик» идёт сплошной последовательностью.

Критерий триггера (все условия одновременно): пользователь запрашивает задания «Пройденного» строго сплошным рядом без пропусков — каждый следующий номер = предыдущий ±1 в одном направлении (возрастание 1,2,3… или убывание N…3,2,1); смена направления или любой пропуск сбрасывает счётчик. Паттерн подтверждается на протяжении 2 календарных дней подряд (в часовом поясе проекта), и первый запрос третьего дня — прямое продолжение того же ряда; в этот момент приостановка срабатывает немедленно. Пример срабатывания: день 1 — 1,2,3; день 2 — 4,5,6; день 3 — 7 → приостановка. Пример НЕ-срабатывания: день 1 — 1,2,3; день 2 — 9,4 → сброс.

Реакция: мягкая приостановка — доступ к «Пройденному» закрывается, остальной функционал работает (это не бан). Пользователю — нейтральное «Технические неполадки. Уже устраняем» (не раскрывает анти-фрод, не обвиняет). Одновременно — алерт админу в спец-тему рабочей группы с деталями и кнопкой [Восстановить]. Реализация через guard-паттерн: флаг is_suspended в БД (не перестройка клавиатуры); клавиатура не меняется, кнопки видимы; каждый обработчик раздела первым шагом проверяет флаг и при активной приостановке возвращает то же сообщение без данных; guard идемпотентен и устойчив к устаревшим кнопкам.

Снятие: по одному из двух событий, что раньше — админ жмёт [Восстановить] (снятие немедленно) или истекает 24 ч без реакции (auto-release). Автоснятие — прямое следствие инварианта: система не держит честного участника бесконечно из-за молчания админа. Повторное срабатывание — идентично первому: счётчик сброшен, при повторном подтверждении приостановка снова; специальной «памяти о рецидиве» в базовой версии нет. Разграничение: Б13 — лимит и логирование (сырьё); Б15 — анализ, решение, алерт, кнопка, авто-снятие. Крючки за пределами шага: этичность/окончательный текст сообщения; механика памяти о рецидиве и эскалация.

## YAML — Шаг 7

```yaml
block_15:

  # ================================================================
  step_7:
    title: "Детекция подозрительного темпа и мягкая приостановка"
    status: closed
    meta: {owner_block: 15, data_source_block: 13, scope: "Пройденное", hermetic: false, invariant: default_in_favor_of_user}
    trigger:
      pattern: strict_contiguous_sequence
      directions: [ascending, descending]
      direction_lock: true
      gap_tolerance: 0
      confirmation: {days_required: 2, timezone: project_tz, fire_on: first_request_of_day_3}
      reset_conditions: [gap_in_sequence, direction_change, day_without_matching_request]
      example_fire: "d1:1,2,3 | d2:4,5,6 | d3:7 -> приостановка"
      example_nofire: "d1:1,2,3 | d2:9,4 -> сброс"
    reaction: {type: soft_suspension, ban_user: false, gated_section: "Пройденное", rest_of_bot: fully_operational, user_message: "Технические неполадки. Уже устраняем", reveals_antifraud: false}
    suspension:
      storage: db_flag
      keyboard_behavior: unchanged
      enforcement: gate_on_handler_entry
      guard: {first_step: check_is_suspended, on_active: "return user_message, emit no data", idempotent: true, stale_button_safe: true}
      fields: {is_suspended: bool, suspended_at: timestamptz, suspend_reason: suspicious_tempo, trigger_snapshot: json}
    admin_alert: {destination: work_group_special_topic, contents: [user_id, detected_pattern, timestamps_per_day], inline_buttons: [{label: "Восстановить", action: manual_release}]}
    release: {modes: {manual: "clear immediately", auto: "24h -> clear automatically"}, whichever_first: true, auto_release_hours: 24, rationale: "не держать честного участника из-за молчания админа"}
    re_trigger: {after_release: identical_to_first_run, sequence_counter: reset_on_release, recidivism_memory: false}
    responsibility: {block_13: "лимит + логирование (сырьё)", block_15: "анализ, решение, алерт, кнопка, авто-снятие"}
    deferred: [user_message_ethics_review, recidivism_escalation]
```
