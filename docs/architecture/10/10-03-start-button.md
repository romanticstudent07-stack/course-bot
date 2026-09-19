---
file: 10/10-03-start-button.md
block: 10
title: "Шаг 3 — Кнопка [Старт]"
status: закрыт (артефакт шага)
doc_version: "consolidated v3"
contains: [выжимка — природа кнопки, идемпотентность, карта поведения, анти-абьюз возврата; YAML — контракт кнопки + сквозная модель удаления данных]
---

# ВЫЖИМКА — Шаг 3: Кнопка [Старт] (артефакт, без ролей)

Кнопка [Старт] в Блоке 10 — это не кнопка с фиксированным действием, а триггер пересчёта. При каждом нажатии бот перечитывает актуальное состояние участника (фазу и набор модификаторов, прогоняет их через resolver) и выполняет то действие, которое соответствует состоянию в этот момент, а не в момент, когда кнопка была нарисована. Это устраняет класс багов «вчерашняя кнопка применяет вчерашнее действие к сегодняшнему состоянию». Команда `/start` и кнопка [Старт] — это два входа в один и тот же механизм: разница лишь в канале ответа (`/start` приходит текстом и отвечается новым сообщением, [Старт] приходит callback'ом и требует быстрого подтверждения).

Идемпотентность обеспечивается на двух уровнях. Быстрое подтверждение callback (в пределах 1–2 секунд, до запуска логики) снимает ошибку Telegram «query is too old» и не даёт спиннеру висеть во время длительной обработки (эффект очереди до 10–60 минут). Защита от двойного эффекта строится на ключе (участник + намерение + позиция), который атомарно захватывается одной командой Redis; но Redis здесь — только оптимизация: подлинный источник истины против двойных списаний и двойных оплат живёт в базе (в Б16 для денег, в Б2 для жизней и рестарта), поэтому при недоступности Redis кнопка продолжает работать корректно на одном Postgres. Резолвер читает состояние и применяет эффект в одной транзакции, что закрывает гонку с событиями Автора, приходящими в момент нажатия.

Поведение кнопки определено для каждого состояния без единой пустой клетки. Глобальный режим техобслуживания перехватывает нажатие раньше всего и показывает технический экран, который снимает тревогу (прогресс сохранён, дедлайны заморожены). Забаненному показывается экран бана с причиной и каналом апелляции и никаких действий прогресса; если бан наложен во время процесса удаления, экран бана не останавливает таймеры удаления. При нулевом балансе жизней кнопка ведёт не прямо в оплату, а через промежуточный экран с объяснением и мягким путём к платному рестарту. При заморозке за неоплату кнопка ведёт к оплате, но с разными экранами и тоном для первой покупки, для перехода на следующий этап и для повторной покупки после возврата. В тайной паузе показывается нейтральный экран ожидания без раскрытия механики и без создания ощущения срочности. В пользовательской паузе — честный экран со сроком и кнопкой досрочного выхода, которая лишь отправляет запрос владельцу (Б2), не снимая паузу сама. В обычном состоянии кнопка делает основную работу — ведёт к текущему невыполненному дню, никогда не прыгая вперёд. В терминальной фазе (аккаунт удалён) кнопка не является тупиком: она предлагает начать заново как новый участник.

Возврат после удаления защищён от злоупотребления мягко. Поскольку удаление в проекте — это де-идентификация (стирается только привязка к личности, а обезличенные данные остаются), защита от бесконечных бесплатных повторов реализуется обезличенным анти-абьюз-артефактом (хэш идентификатора + факт удаления + счётчик циклов), что юридически опирается на законный интерес и на то, что право на удаление не распространяется на данные, создаваемые в будущем. Фингерпринтинг устройств сознательно не внедряется как избыточный и рискованный в ЕС. Первый честный возврат считается нормой; трение (отказ в повторном триале или скидке, но не запрет доступа) включается только при частых повторах — с третьего цикла в пределах двенадцати месяцев.

# YAML — Шаг 3 (контракт кнопки [Старт])

```yaml
start_button:
  nature: trigger_reevaluate        # не хранит действие; перечитывает состояние
  unified_entry:                    # Р67
    command_/start: {reply: new_message}
    button_[start]: {reply: fast_ack_then_action}
  core: reread_state_and_apply_now  # Р61 (фаза + resolver, Р53)

  idempotency:
    fast_ack:                       # Р62
      answer_callback_query_within_sec: 2
      never_hold_open_during: queue_effect   # 10-60 мин, Ф-Б7.5
    lock:                           # Р63
      key: [participant_id, intent, position]
      acquire: "SET key val NX PX ttl"       # атомарно, одной командой
      release: owner_checked_only
    source_of_truth:                # Р63.1
      money: block_16               # Ф-Б16.8
      lives_restart: block_2        # Ф-Б2.2.5
      redis: optimization_only
      degraded_mode: works_on_postgres_alone
    transaction: read_and_effect_atomic       # Р73 (V35)

  resilience:
    stale_callback_after_downtime: redraw_fresh_screen   # Р69
    repeat_press_soft_ack: "уже обрабатываю"             # Р70
    during_queue_effect: "ты в очереди"                  # Р65 (жизнь не горит)

  label: task_focused_per_state     # Р66

  behavior_map:                     # Р64 — порядок = приоритет резолвера Р50
    maintenance_global:             # Р68 — перехват ДО резолвера
      screen: tech_maintenance
      message: [works_in_progress, progress_saved, deadlines_frozen, eta]
    ban_mod:                        # верх приоритета
      screen: ban
      shows: [reason, appeal_channel]
      progress_actions: none
      note_R64a: ban_during_erasure_does_not_stop_erasure_timers
    block_lives:                    # Р71 (V34)
      screen: zero_lives_options    # промежуточный, НЕ прыжок в оплату
      leads_to: paid_restart
      vs_freeze_unpaid: block_lives_wins
    freeze_unpaid:                  # Р19
      by_scope:
        pre_first:   "начни курс, оплати Этап 1"
        pre_next:    "завершил Этап N, оплати N+1"   # тон: поздравление
        after_refund:"купить Этап N заново"          # Ф-Б16.6
    pause_shadow:                   # Ф-Б7.2 — не раскрывать тайность, ноль срочности
      by_reason:
        no_verdict:       "отчёт на проверке у автора"
        content_frontier: "дошёл до края, ждём материал"
        maintenance:      handled_by_R68_earlier
    pause_user:                     # V37
      screen: honest_pause_info     # срок + остаток
      early_exit_button:
        action: send_event_to_block_2   # Б10 просит, Б2 исполняет (Ф-Б3.d)
        b10_removes_itself: false
    normal:
      leads_to: current_undone_day  # позиция модуль.день, Ф-П1
      forward_jump: forbidden       # Ф-Б3.e
      if_day_done_next_gated: queue_or_review_screen   # Р65
    erased:                         # Р74 (V38) — НЕ trap
      screen: account_deleted_restart
      leads_to: pre_road_as_new     # join 18+→юр→оплата, Р46

  anti_reregistration_abuse:        # erased → re-register
    artifact:                       # Р75 — обезличенный, часть общей модели удаления
      fields: [hash_telegram_user_id, was_erased, date, cycle_count]
      legal_basis: [legitimate_interest, erasure_not_cover_future_data]
    device_fingerprint: not_implemented          # Р76
    policy: friction_not_ban                      # Р77
    friction_trigger:                             # V39-решено
      after_cycles: 3
      within_months: 12
      action: no_repeat_trial_or_discount         # доступ НЕ запрещаем
    artifact_only_for: former_adult_18plus        # Р78
    retention: min(trial_offer_lifetime, financial_records_7_8y)

  invariants:
    no_empty_screens: true          # Ф-Б16.8
    b10_reads_facts_not_computes: true
    time_reference: participant_tz

data_deletion_model:                # сквозная, уточнена пользователем
  erasure_type: de_identification   # НЕ удаление содержимого
  removed: identity_link_only
  retained_anonymized: [progress, metrics, answers, behavioral]
  anonymized_status: outside_gdpr_scope   # хранение бессрочно
  requirement: anonymization_must_be_non_reidentifiable   # ДОЛГ→Юр/Б15
  financial_records: kept_by_tax_law_7_8y
```
