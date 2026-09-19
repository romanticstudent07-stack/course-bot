---
file: 10/10-02-transition-matrix.md
block: 10
title: "Шаг 2 — Матрица переходов"
status: закрыт (артефакт шага)
doc_version: "consolidated v3"
contains: [выжимка — слой фаз и слой модификаторов, YAML — контракт переходов]
---

# АРТЕФАКТ ШАГА 2 — ВЫЖИМКА (матрица переходов)

Блок 10 моделирует участника как одну эксклюзивную ось-фазу плюс набор модификаторов-статусов, и переходы устроены в двух независимых слоях, которые вычисляются в строго фиксированном порядке: сначала слой фаз, затем слой модификаторов. Этот порядок — жёсткий инвариант против гонок: любое событие сначала проверяется против фазы («можно ли вообще что-то делать»), и только потом против модификаторов («в каком режиме»).

Фаз четыре. Стартовая — `pre_road`, узел до выхода на дорогу курса. Выход из неё в `active` — это не одиночное событие оплаты, а join трёх условий в обязательном порядке: подтверждение совершеннолетия, принятие юридических дисклеймеров и подтверждённая оплата. Порядок обязателен, проверка возраста стоит первой, до сбора данных и оплаты, и каждый шаг логируется для аудита. Если участник не подтверждает возраст или отказывается от дисклеймеров, он не переходит в `active`, а видит осмысленный экран-тупик; если оплата прошла, но возраст или согласие не подтверждены, деньги возвращаются, поскольку услуга не может быть оказана. Сама механика онбординга (экраны, тексты, способ проверки) принадлежит блоку онбординга — Блок 10 владеет только фазой, условиями выхода и исходами-тупиками.

Фаза `active` — рабочее состояние участника на дороге курса. Именно в ней живут все модификаторы и почти вся динамика. Внутренние переходы день→день, модуль→модуль и этап→этап происходят внутри `active` и Блоку 10 как смены фазы не принадлежат: бот гейтит переходы по проверке заданий, а решение по рефлексии на границах модуля и этапа принимает автор; авто-прохода нет нигде. Отсутствие вердикта автора на границе не даёт авто-прохода, а переводит участника в теневую паузу.

Фаза `pending_erasure` — замороженный предбанник удаления по запросу GDPR. При входе в неё все модификаторы не стираются, а консервируются снимком в журнал, активный резолвер отключается, экран становится единым. Фаза различает инициатора удаления: при пользовательском запросе есть окно отмены с кнопкой, при удалении по инициативе автора или системы (фрод) окна отмены нет и экран иной. Работают два разных таймера: короткое cooling-off окно, внутри которого возможна отмена, и юридический дедлайн, к которому удаление обязано завершиться. Отмена возможна только внутри cooling-off и только при пользовательском инициаторе — либо кнопкой, либо неявно через оплату (оплата восстанавливает договорное правовое основание, при котором право на erasure не действует, и модификаторы восстанавливаются из снимка). Оплата, пришедшая после cooling-off, отмены не даёт и возвращается. Финансовые записи erasure не стирает — они удерживаются по налоговому праву; стирается только учебный контент и персональные данные.

Фаза `erased` — легитимный терминал, не ловушка.

Модификаторы образуют множество, а не единственный слот, и эффективный модификатор для экрана и гейтинга вычисляется чистой функцией-резолвером по фиксированному приоритету: `ban_mod` выше `block_lives`, выше `freeze_unpaid`, выше `pause_shadow`, выше `pause_user`, выше `normal`. Приоритет обоснован природой каждого: бан — единственный осознанный ручной модераторский акт (и он у нас явный, видимый участнику, со снятием только вручную автором; скрытых банов мы сознательно не делаем); блокировка по жизням первичнее денежного вопроса; неоплата снимает договор, поэтому паузы под ней неприменимы; системная теневая пауза важнее пользовательской.

Легальность пар модификаторов задана явной матрицей. Запрещены две пары: пауза пользователя с заморозкой по неоплате (пауза неприменима к неоплаченному) и пауза пользователя с блокировкой по жизням (блокировка требует активного разрешения, пауза поверх неё бессмысленна и эксплуатируема). Остальные пары легально сосуществуют в множестве, а резолвер выбирает верхний по приоритету. Запрещённая пара не выбирается молча — резолвер обязан кинуть явную ошибку.

Переходы модификаторов определены событиями с внешними владельцами, а Блок 10 только реагирует. Потеря третьей жизни (счёт ведут Блоки 2 и 7) навешивает блокировку по жизням. Выход из блокировки — либо платный рестарт по умолчанию, либо авторское милосердие, обязательно с откатом позиции как предохранителем от бесконечной потери жизни на застрявшем дне. Платный рестарт — многополевой переход, атомарность которого обеспечивает Блок 2 в одной транзакции: снимается блокировка, прогресс обнуляется на начало текущего этапа с восстановлением трёх жизней, при этом оплата и журнал замеров сохраняются, а квота паузы сбрасывается; предыдущие оплаченные и пройденные этапы не затрагиваются. Рестарт как событие отличается от оплаты следующего этапа — это разные события, экраны и метки журнала. Теневая пауза — единый модификатор с полем причины (достижение фронта контента, отсутствие вердикта, техработы); резолвер обходится с ней одинаково, но выход и текст экрана зависят от причины.

Надёжность переходов обеспечена тремя правилами. События несут уникальный идентификатор и обрабатываются идемпотентно, а упорядочивание требуется только в рамках одного участника, не глобально. Блок 10 при каждом показе экрана перечитывает актуальное множество модификаторов из базы и заново прогоняет резолвер, а не доверяет порядку прихода событий — поэтому временный глитч вроде показа экрана блокировки тому, кому уже вернули жизнь, невозможен. Гонки самих жизней вне зоны Блока 10: списание и возврат атомарны на стороне Блока 2, а Блок 10 читает итог. Откат «вдогонку» невозможен по построению Блока 7.

# АРТЕФАКТ ШАГА 2 — YAML (контракт переходов)

```yaml
block_10_step2_transitions:
  computation_order: [phase_region, modifier_region]   # Р39: ворота→комната
  phases:
    pre_road:
      is_start: true
      transitions:
        - event: onboarding_join
          guard: age_confirmed AND legal_accepted AND payment_confirmed  # Р46 join
          order: [age_18plus, legal_disclaimers, payment]                # фикс.порядок
          audit_log: per_step
          to: active
        - event: age_or_legal_failed          # Р47
          to: pre_road
          screen: dead_end_explained
        - event: payment_but_blocked_underage # Р48
          to: pre_road
          action: refund_payment
      owner: onboarding + block_16
    active:
      note: "внутр. день/модуль/этап переходы — не фаза Б10 (Ф-Б7.4/7). Авто-прохода нет."
      transitions:
        - event: erasure_request
          initiator: user
          to: pending_erasure
        - event: erasure_forced
          initiator: [author, system_fraud]
          to: pending_erasure
    pending_erasure:
      frozen: true
      resolver_active: false          # Р37: модификаторы законсервированы snapshot
      modifiers_snapshot: preserved
      initiator_field: [user, author, system_fraud]   # Р40
      timers:
        cooling_off_window: {editable: true, default_days: 7}   # Р41/V25
        legal_erase_deadline: {basis: gdpr_undue_delay}
      transitions:
        - event: cancel_button
          guard: initiator==user AND within(cooling_off) AND snapshot_intact  # Р38 join
          to: active
          action: restore_modifiers_from_snapshot
        - event: payment_confirmed
          guard: initiator==user AND within(cooling_off)      # Р42 неявная отмена
          to: active
          action: [restore_modifiers_from_snapshot, notify_user]  # Р43
          log_reason: erasure_cancelled_by_payment
        - event: payment_confirmed
          guard: NOT within(cooling_off)     # Р45
          action: refund_payment
        - event: deadline_reached
          guard: within(cooling_off)==false
          to: erased
      retained_forever: [financial_records, metrics, card]   # налоговое право
    erased:
      is_terminal: true
      trap_state: false

  modifiers:
    set_model: true                    # Р29: множество, не слот
    priority: [ban_mod, block_lives, freeze_unpaid, pause_shadow, pause_user, normal]  # Р50
    resolver:
      type: pure_function              # Т4
      illegal_pair_behavior: raise_explicit_error   # Т4, не тихий выбор
      screen_rule: reread_state_then_resolve         # Р53 анти-гонка
    legality_matrix:
      forbidden:
        - [pause_user, freeze_unpaid]  # Р11 / Ф-Б2.П12
        - [pause_user, block_lives]    # Р55 / V28
      legal_coexist:
        - [block_lives, freeze_unpaid]
        - [ban_mod, "*"]
        - [pause_user, pause_shadow]
        - [freeze_unpaid, pause_shadow]
    definitions:
      ban_mod:
        type: explicit_moderator_ban   # Р51: НЕ hellban/slowban
        visible_to_user: true
        removal: manual_by_author_only
        unlock_button: "🔓 (КУ.6) снимает ТОЛЬКО ban_mod"   # Р36
        attrs: [reason, appeal]
      block_lives:
        entry_event: lives_reached_zero   # Р56 / V14, владелец Б2/Б7
        exit:
          - restart_paid                  # Р31 дефолт
          - revive_by_author              # Р32/Р33 с откатом позиции (предохранитель)
        b10_reaction: [remove_modifier, set_active, refresh_screen_and_start, log_reason]  # Р35
      freeze_unpaid:
        scope: [pre_first, pre_next]
        exit_event: payment_confirmed
      pause_shadow:
        single_modifier: true            # Р57 / V24
        reason: [content_frontier, no_verdict, maintenance]
        owner: block_7 (7.7 фаза C)
        quota_impact: none
      pause_user:
        owner: block_2
        freezes: [timers, lives]         # Ф-Б2.П3 как есть
        quota: 1_per_stage               # Ф-Б2.П8
      normal: {}

  restart_paid:                          # Р58 / Р60 / V15+V29
    type: multi_field_atomic
    atomicity_owner: block_2_single_transaction
    effects:
      - remove: block_lives
      - reset_progress_to: current_stage_start   # Р60: тек.этап, НЕ курс
      - restore_lives: 3
      - preserve: [payment, measurements_journal]
      - reset: pause_quota
      - keep_intact: previous_paid_stages
    distinct_from: payment_confirmed_next_stage  # Р59
    b10_role: subscribe_to_result_event_and_react

  events:
    delivery: at_least_once
    idempotency: event_id_dedup_by_pk    # Р53 / cockroachlabs
    ordering: per_participant_id_only    # не глобально
    lives_race: out_of_scope_handled_in_block_2   # Р54 / Ф-Б2.2.5

  invariants_proven:
    T1_every_state_has_exit: true
    T2_no_unreachable: true
    T5_graduate_not_trap: true
```
