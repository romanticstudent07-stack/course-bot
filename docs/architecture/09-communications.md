---
file: 09-communications.md
block: 9
title: "Коммуникации / Уведомления (тексты, тон, 3-тир, автор-канал)"
source: "Архитектура(1).docx, от заголовка «ЕДИНАЯ ВЫЖИМКА БЛОКА 9» до конца «YAML-патч» (включая «ПАТЧ К ЕДИНОЙ ВЫЖИМКЕ БЛОКА 9 (v3-consolidated-3.1)»)"
doc_version: "consolidated v3 / блок: v3-consolidated-3.1"
status: закрыт
---

# БЛОК 9. КОММУНИКАЦИИ / УВЕДОМЛЕНИЯ

> **Переопределено ERRATA-UNIFIED.** Носитель всех текстов перенесён в `text_registry` патча И4 (пространства имён `{домен}.{имя}`, три тона, правовой статус). ERRATA добавляет запись `B7.stage_pass_rollback_not_supported_owner` (ADD4), но называет носитель `text_catalog_b9` — расхождение имён с `text_registry` **не снято**, действует под именем `text_registry`. Универсальный `render()` с ролью в параметре запрещён — рендер разделён на три функции по аудитории. См. [normative/I4-wave-d.md](normative/I4-wave-d.md), [normative/errata-unified.md](normative/errata-unified.md).

## ЕДИНАЯ ВЫЖИМКА БЛОКА 9

Блок 9 владеет всеми текстами системы, единым тоном продукта и внутренним 3-тир классификатором сообщений. Он не управляет доставкой (Б15), не хранит идентичность участника (Б2/Б10), не решает бизнес-логику событий. Пользовательских тумблеров отключаемости уведомлений не существует и не может быть введено (Р123-FINAL, NR-215); экрана «Настройки уведомлений» нет; инвентарь класса A остаётся размером 5.

3-тир — внутренний атрибут, влияющий только на приоритет в очереди Б15, drop-policy при перегрузке и юр.флаг обязательности.

**T1 системные** (юр./финансовые/жизненные): бан, апелляции, оплата, maintenance, DLQ, refund/erasure, красная зона Чек-Апа, minaapp reject, оплатная рефлексия Автору — недропаемые, никогда не коалесятся, T1-Автору для 13-P/pending-B/апелляций/DLQ идут «личным алертом без кнопок» (канон 7.8).

**T2 операционные**: пауза-события, форвард смен состояний Б2, вердикт рефлексии, новый Этап «ждущим на границе», Чек-Ап-нуджи, экспорты, empty-фолбэки, pause_shadow — must_deliver в TTL, семантический коалесинг у продюсера (окна заданы по классам).

**T3 мотивационные**: полуденный нудж, «день не задался», return-reminder, компаньоны к вердиктам/оживлению — droppable, гейтятся правилами Б9 через реальные сигналы канона (throttle, состояние участника, факт P-4 в этапе), без синтетического флага motivation_suppress.

Тон единый: обращение на «Вы», факт + путь, без вины; «наказание» → «возврат для закрепления» (3.20); «блокировка» → «пауза»; «провал» → «материал требует пересдачи»; «удаление аккаунта» → «полное обезличивание данных»; «жизнь сгорела» → «одна попытка использована». Эмодзи — максимум одно, никогда как единственный носитель смысла (Р152); ⚠️ разрешено только в T1-алертах Автору. Кризисные тексты (бан, erasure, refund, anti-piracy, красная зона) — юр-нейтральны, без раскрытия детекторов, без медицинских терминов; wording красной зоны утверждает Legal (5.7).

pause_shadow (Ф-Б7.2, 7.7 Фаза C) маскируется тремя разновидностями текстов по shadow_reason ∈ {no_verdict, content_frontier, maintenance_overlap}; стоп-лист слов (пауза, вердикт, проверка, наблюдение, случай, рассматривается, решение) проверяется линтером; ни один текст Б9 не намекает на тайность. Возврат после erasure = welcome нового участника (identity_break irreversible, match_to_old_trace forbidden); отдельный T2-RETURN-FRICTION появляется только при срабатывании обезличенного анти-абьюз-артефакта (третий цикл в 12 мес), без раскрытия «мы Вас узнали». Автору-безмолвие не имеет «синтетического T_silence»: система работает по канону — авто-разрешение только паузы (П.2), рефлексии идут через фазы A/B/C с усиленным личным алертом в фазе B и тайной паузой в фазе C.

Автор-канал использует канонический формат обращения (8.5): Имя (@username · ID 12345) → [написать] с кликабельной ссылкой через tg://user?id=…; кнопка «написать» реализуется потоком write_via_bot (8.8). Утренняя сводка Автору — 09:00 по ТЗ Автора (P-2), dm_to_author, ядро — счётчики рефлексий по типам Чек/Переход/Рубеж с явной датой и приоритетом 13-P (3.15); скелет рисуется всегда, даже при нулях; расширения (апелляции, DLQ-digest, экспорты, пороги, паузы, платежи) добавляются приложением к сводке.

Технический контракт формы обязателен: parse_mode=HTML единственный (MarkdownV2 запрещён), разрешённый набор тегов ограничен, все подстановки проходят html_escape (соответствует Б14-R342 «HTML-escape всех user-generated»); лимит 4096 символов — жёсткий, T1/T2 разбиваются по границе абзаца с суффиксом (часть k из N), T3 усекается до 900 символов; caption медиа ≤1024. Все числовые плейсхолдеры несут plural-ru тройку one|few|many через функцию plural_ru() (сырые формы запрещены). Экспорт по каналу T2/A1: TTL signed-URL 15 минут (не 24 часа) — тексты сформулированы под срочность без давления; export_kind ∈ {json, xlsx, csv, photos, full}, для CSV — отдельный warning про служебный префикс (R374/R375).

Каталог id — стабильный append-only. Изменение любого T1-текста требует апрува Автора; тексты красной зоны и erasure — апрув Legal. Fail-closed дефолты: пропущенный тир → T1; невозможность собрать шаблон → отправка plain-text без parse_mode. Гейт erased=true блокирует любую эмиссию после T1-ERASURE-*. Полная матрица «событие → id → тир → адресат → триггер» содержит ~75 текстовых id и покрывает все входящие STUB-хвосты закрытых блоков (Б2, Б7, Б8, Б10, Б14, Б15, Б16).

## YAML-КОНТРАКТ БЛОКА 9

Канонический YAML-контракт блока приведён ниже одним потоком вместе с YAML-патчем v3-consolidated-3.1 — так он идёт в оригинале: базовые секции (block/ownership/invariants/tiers/…/contracts_out) и патч-секции (patch/added_rules/added_nr/text_catalog_delta/…) в одном блоке. См. раздел «YAML-патч».

## ПАТЧ К ЕДИНОЙ ВЫЖИМКЕ БЛОКА 9 (v3-consolidated-3.1)

Дополнение к v3-consolidated-3.0. Не отменяет ничего, кроме явно указанных замен.

### Выжимка (дополнение)

Технический контракт формы усилен под реальные ограничения Telegram HTML-парсера. В <a> разрешены только схемы https/http/tg (Р252, NR-234); mailto:/tel: в HTML-режиме запрещены — контакты выводятся plain-текстом либо inline-кнопкой. Разбиение сообщений длиннее 4096 идёт по ближайшему пробелу до 4000-го байта UTF-8 с обязательным закрытием стека HTML-тегов на границе части и открытием тех же тегов в следующей (Р253); в конце — суффикс (часть k из N). Fallback при parse-ошибке — strip_tags c развёрткой ссылок в формат текст (URL), чтобы адрес не терялся (Р254). Функция plural_ru(n) формализована по CLDR: one при n%10==1 && n%100!=11; few при n%10∈[2..4] && n%100∉[12..14]; иначе many — 11–14 всегда «many» (Р255, NR-235). Правило команд: /xxx не выводится в тексте участнику как единственный способ действия — только inline-кнопка или явная инструкция «нажмите кнопку [X] в меню бота» (Р256, NR-236). Дедлайновые тексты обязаны нести якорь «по Вашему времени» когда речь о времени действия участника (Р257).

Тон-регламент расширен принципом гендерно-нейтральной формулировки: в шаблонах используются безличные, пассивные и инфинитивные конструкции («Задание выполнено», «Попытка использована», «Требуется подтвердить»); хранение пола ради грамматики уведомлений запрещено — противоречит минимизации ПДн (Р258, NR-237). Эмодзи не может выступать маркером списка: булеты — • или <b>1.</b> (Р259, NR-238); Р152/Р207 в силе.

Мотивационные сообщения получают жёсткую крышу: не более одного T3-сообщения на участника за 24 часа, независимо от количества триггеров; при конкуренции выигрывает более ранний по расписанию, остальные подавляются (Р260, NR-239). Это правило — продюсерский rate-limit, не пользовательский тумблер, NR-231 не нарушен. Профилактика 152-ФЗ/GDPR-давления.

### Добавлены/заменены формулировки

**T1-ANTIPIRACY** (замещает старую) — честнее и без шаблонного «Технические неполадки»: «Раздел временно недоступен. Мы уже работаем над восстановлением доступа. Ваш прогресс сохранён.» Автор в админ-панели по-прежнему видит истинную причину soft_hold (долг к Б15 в силе).

**T1-MINIAPP-SESSION-EXPIRED** (новый, замещает подпункт session_expired в словаре T1-MINIAPP-REJECT) — «Для Вашей безопасности сессия обновлена. Пожалуйста, закройте и откройте этот раздел заново.»

**T2-EXPORT-CSV-WARN** (переформулировка) — «Внимание: файл содержит служебные данные. При открытии в Excel используйте режим «Импорт текста», чтобы избежать автоматического исполнения формул. Служебный префикс «'» в некоторых ячейках — часть защиты.»

**T1-CONSENTS-SCREEN** (новый, «Мои согласия» — экран, Б10-D2) — рамка: перечень согласий, статус, дата, ссылка на политику; каждая строка — самодостаточный лейбл, кнопка отзыва рядом.

**T1-ERASURE-INITIATE** (новый, инициация удаления ПДн из «Мои согласия», Б10-D2) — «Удаление персональных данных — необратимое действие. После подтверждения бот больше не сможет писать Вам, а восстановить прежний прогресс будет невозможно. У Вас есть {n:hours} на отмену запроса — после этого удаление будет выполнено.» (cooling-off: n:hours определяет Б10; текст готов к 24/48/72).

**T1-ERASURE-COOLING-CANCEL** (новый) — «Запрос на удаление отменён. Всё сохранено, продолжаем обычную работу.»

Reason-словарь T1-MINIAPP-REJECT дополнен: старый session_expired изъят из общей обёртки — теперь у него отдельный id T1-MINIAPP-SESSION-EXPIRED с собственной формулировкой; остальные 6 кодов работают через общую обёртку без изменений.

## YAML-патч

```yaml
block: 9
title: Коммуникации / Уведомления (тексты, тон, 3-тир, автор-канал)
version: v3-consolidated-3.0
supersedes: [v3-consolidated (prev)]

ownership:
  owns:
    - wordings
    - tone_policy
    - tier_classifier
    - emoji_discipline
    - text_catalog_versioned_append_only
    - producer_semantic_coalescing_rules
    - text_form_technical_contract  # HTML, escape, 4096, plural-ru
    - author_channel_wordings
    - morning_summary_composition
  reads_from: [block2.events, block7.events, block8.channels, block10.events, block14.events, block15.events, block16.events]
  does_not_own: [transport, dedup_at_transport, retry, dlq_mechanics, user_toggles_absent, participant_identity, business_logic]

invariants:
  - R123_FINAL_no_user_notification_toggles
  - class_A_inventory_size == 5
  - tone_formal_polite_vy
  - term_filter: {наказание: "возврат для закрепления", блокировка: "пауза", провал: "материал требует пересдачи", удаление_аккаунта: "полное обезличивание данных", жизнь_сгорела: "одна попытка использована"}
  - R152_emoji_never_sole_carrier
  - erasure_gt_identity_gate_on_emit
  - identity_break_after_erasure_irreversible
  - match_to_old_trace_forbidden
  - auto_pass_NEVER  # решения по рефлексии не автоматизируются
  - only_auto_is_pause_grant_in_favor_of_participant  # П.2
  - fail_closed_defaults: {tier_missing: T1, template_broken: plain_text_send}
  - no_empty_screens
  - append_only_catalog
  - html_escape_all_placeholders  # соответствует Б14-R342

tiers:
  T1_system:
    priority: P0
    must_deliver: true
    drop_on_overload: false
    coalesce: false
    legal_audit: true
  T2_operational:
    priority: P1
    must_deliver: within_ttl
    drop_on_overload: false
    coalesce: producer_side_semantic_window
  T3_motivational:
    priority: P2
    must_deliver: false
    drop_on_overload: true
    gates:
      - not_in_states: [ban, erased, refund_final, shadow_pause_active]
      - throttle_or_context_rule_per_id: true

producer_coalescing_windows:
  pause_reschedule: 5m
  empty_fallback.*: 60s
  stage.published: 10m
  miniapp.reject: 30s
  reflection.verdict: none  # never coalesce
  checkup.dynamics_alert: 30m  # aggregate axes
  dlq.alert: 15m  # aggregate by reason
  strategy:
    pause_reschedule: last_wins
    dlq.alert: aggregate_counter_by_reason
    checkup.dynamics_alert: aggregate_axes_list
    others: last_wins

tone_policy:
  address: "Вы"
  banned_terms: [наказание, наказан, провал, фейл, сгорело, просрочка, долг, недоплата, штраф, диагноз, состояние, болезнь, риск]
  crisis_texts_rule: fact_plus_path_no_blame
  ban_texts_rule: no_detector_disclosure
  redzone_texts_rule: soft_recommend_doctor_no_medical_diagnosis  # 5.7 Legal-wording
  shadow_stopwords: [пауза, вердикт, проверка, наблюдение, случай, рассматривается, решение]
  emoji:
    max_per_message: 1
    position: after_key_word
    never_sole_carrier: true
    warn_emoji_allowed_only_in_T1_to_author: ["⚠️"]

text_form_technical_contract:
  parse_mode: HTML  # MarkdownV2 forbidden
  allowed_tags: [b, i, u, s, code, pre, a, blockquote]
  escape_placeholders: html_escape
  max_length_message: 4096
  max_length_caption: 1024
  long_message_policy:
    T1: split_by_paragraph, suffix: "(часть k из N)"
    T2: split_by_paragraph, suffix: "(часть k из N)"
    T3: truncate_to_900, no_parts_suffix
  placeholder_format: "{name:type}"
  plural_ru:
    function: plural_ru(n, one, few, many)
    forms:
      n:days:         {one: день,    few: дня,    many: дней}
      n:hours:        {one: час,     few: часа,   many: часов}
      n:minutes:      {one: минута,  few: минуты, many: минут}
      n:attempts:     {one: попытка, few: попытки, many: попыток}
      n:returns:      {one: возврат, few: возврата, many: возвратов}
      n:participants: {one: участник, few: участника, many: участников}
      n:appeals:      {one: апелляция, few: апелляции, many: апелляций}
      n:reflections:  {one: рефлексия, few: рефлексии, many: рефлексий}
      n:tasks:        {one: задача, few: задачи, many: задач}
      n:paused:       {one: участник, few: участника, many: участников}
    forbidden: "any raw plural form via string concat"
  fail_safe_send:
    on_html_parse_error: plain_text_no_parse_mode

author_channel:
  address_line_format: "<b>{name}</b> (@{username} · ID {tg_user_id}) → [написать]"  # canon 8.5
  deep_link: "tg://user?id={tg_user_id}"
  write_button_flow: write_via_bot  # canon 8.8
  personal_alert_no_buttons: true   # canon 7.8; applies to A1-13P-URGENT, A1-PENDING-B-URGENT, A1-APPEAL-NEW
  priorities:
    instant_dm_priority: {emoji_prefix: "⚠️", pin_topic_min: 60}
    instant_dm: {}
    digest_09: {}

morning_summary:
  time: "09:00 по ТЗ Автора"  # canon 3.15, P-2
  channel: dm_to_author
  draw_skeleton_always: true  # никогда не «молчим» полностью
  core_content:
    - "N× Рефлексия-Чек (день 6) — даты"
    - "N× Рефлексия-Переход (13-M) — даты"
    - "N× Рефлексия-Рубеж (13-P) — даты"
  priority_marker: day_13_P
  appendix_sections:
    - appeals_new
    - reflections_queue_age
    - checkup_dynamics_stages
    - returns_last_24h
    - pauses_active_and_requests
    - payments_ok_checking_rejected
    - dlq_low_freq
    - exports_ready_ttl

text_catalog:
  # ============= T1 =============
  T1:
    - {id: T1-BAN-BEH,                   event: block7.C1.ban.behavior}
    - {id: T1-BAN-PAY,                   event: block7.C1.ban.payment_fraud}
    - {id: T1-APPEAL-OPEN,               event: block10.step6.appeal.open}
    - {id: T1-APPEAL-RESULT-OK,          event: block10.step6.appeal.ok}
    - {id: T1-APPEAL-RESULT-DENY,        event: block10.step6.appeal.deny}
    - {id: T1-MAINT,                     event: infra.C4.maintenance_on, addressee: all_active}
    - {id: T1-ANTIPIRACY,                event: block15.hook1.soft_hold}
    - {id: T1-REFUND-FINAL,              event: block15.step1.refund_finalized}
    - {id: T1-ERASURE-FAREWELL,          event: block15.step3.erasure_finalized, initiator: [admin, policy], terminal: true}
    - {id: T1-ERASURE-CONFIRMED-USER,    event: block10.R144.erasure_confirmed, initiator: user, terminal: true, legal: [GDPR-Art-12-3, 152-FZ]}
    - {id: T1-PAY-CONFIRMED,             event: block16.payment.ok}
    - {id: T1-PAY-RECEIVED-CHECKING,     event: block16.payment.received_checking}
    - {id: T1-PAY-NOT-FOUND,             event: block16.payment.not_found}
    - {id: T1-LIVES-ZERO-SCREEN,         event: block2.C5.lives_reached_zero.screen}
    - {id: T1-UNBAN-RESTORE,             event: block7.unban.restore}
    - {id: T1-UNBAN-FRESH,               event: block7.unban.fresh_start}
    - {id: T1-CHECKUP-ZONE-GREEN,        event: block14.checkup.zone, zone: green,  body_from: config, framing_by: block9}
    - {id: T1-CHECKUP-ZONE-YELLOW,       event: block14.checkup.zone, zone: yellow, body_from: config, framing_by: block9}
    - {id: T1-CHECKUP-ZONE-RED,          event: block14.checkup.zone, zone: red,    body_from: config, wording_by: legal, no_medical_diagnosis: true, soft_recommend_doctor: true}
    - {id: T1-MINIAPP-REJECT,            event: block14.R366.miniapp_reject, dict: reason_human}
  # ============= T2 (участнику) =============
  T2_participant:
    - {id: T2-PAUSE-START,                event: block2.C5.pause_start}
    - {id: T2-PAUSE-END,                  event: block2.C5.pause_end}
    - {id: T2-PAUSE-RESCHEDULE,           event: block2.C5.pause_reschedule}
    - {id: T2-PAUSE-EARLYEXIT,            event: block2.C3.pause_early_exit}
    - {id: T2-PAUSE-ACTIVE,               event: block2.pause.periodic}
    - {id: T2-PAUSE-ENDING-SOON,          event: block2.pause.t_minus_24h}
    - {id: T2-PAUSE-LONG,                 event: block2.pause.over_30d}
    - {id: T2-PAUSE-AUTO-APPROVED,        event: block2.P2.silence_auto_grant}
    - {id: T2-RESTART-PAID,               event: block2.C5.restart_paid}
    - {id: T2-REVIVE,                     event: block2.C3.revive_by_author}
    - {id: T2-STAGE-NEW,                  event: block14.R132.stage_published.waiting}
    - {id: T2-REFL-VERDICT-OK,            event: block10.reflection.ok}
    - {id: T2-REFL-VERDICT-RETURN,        event: block10.reflection.return}
    - {id: T2-RETURN-FOR-REINFORCEMENT,   event: block10.reflection.return.extended}
    - {id: T2-DEADLINE-LADDER-PLUS1H,     event: tz.3.17.step1}
    - {id: T2-DEADLINE-LADDER-MINUS2H,    event: tz.3.17.step2}
    - {id: T2-DEADLINE-LADDER-MINUS30M,   event: tz.3.17.step3}
    - {id: T2-QUEUE-POSITION,             event: tz.3.19}  # также используется как маскирующий текст в фазе C (7.7)
    - {id: T2-CHECKUP-IMPROVE,            event: block14.checkup.dynamics.improve}
    - {id: T2-CHECKUP-STAGNANT,           event: block14.checkup.dynamics.stagnant}
    - {id: T2-CHECKUP-DECLINE,            event: block14.checkup.dynamics.decline}
    - {id: T2-CHECKUP-NUDGE-D1,           event: block14.R253.checkup_nudge.day1}
    - {id: T2-CHECKUP-NUDGE-D2,           event: block14.R253.checkup_nudge.day2}
    - {id: T2-CHECKUP-NUDGE-LAST,         event: block14.R253.checkup_nudge.last}
    - {id: T2-EXPORT-READY,               event: block14.R283.export.ready, ttl_minutes: 15}
    - {id: T2-EXPORT-EXPIRED,             event: block14.R283.export.expired}
    - {id: T2-EXPORT-CSV-WARN,            event: block14.R374.csv_prefix_warn}
    - {id: T2-THRESH-UPDATE-PARTICIPANT,  event: block14.R381.threshold_update.affected}
    - {id: T2-RECALC-INDICATOR,           event: block14.R361.recalc_progress}
    - {id: T2-PAY-REMIND-D1,              event: block16.pay.remind.day1_12}
    - {id: T2-PAY-REMIND-D2,              event: block16.pay.remind.day2_12}
    - {id: T2-PAY-REMIND-D3,              event: block16.pay.remind.day3_12}
    - {id: T2-SHADOW-NO-VERDICT,          event: block7.C2.shadow, reason: no_verdict}
    - {id: T2-SHADOW-CONTENT-FRONTIER,    event: block7.C2.shadow, reason: content_frontier}
    - {id: T2-SHADOW-MAINTENANCE,         event: block7.C2.shadow, reason: maintenance_overlap}
    - {id: T2-CONTENT-FRONTIER-BANNER,    event: R120.banner, return_case: [fresh_wait, after_pause, after_reflection_ok, after_reflection_return, after_ban_appeal, after_refund_partial, after_revive]}
    - {id: T2-EMPTY-FALLBACK-LINK,        event: block14.hook4.link_broken}
    - {id: T2-EMPTY-FALLBACK-CONTENT,     event: block14.hook4.content_absent}
    - {id: T2-EMPTY-LOADING,              event: block14.hook4.loading}
    - {id: T2-EMPTY-RETURNED,             event: block14.hook4.material_returned}
    - {id: T2-EMPTY-STUB-GENERIC,         event: block14.hook4.generic_fallback}
    - {id: T2-LIVES-ZERO-PUSH,            event: block2.C5.lives_reached_zero.push}
    - {id: T2-RETURN-FRICTION,            event: block10.step3.anti_abuse_artifact.friction_only}
  # ============= T2/T1 (автору) =============
  A_author:
    - {id: A1-13P-URGENT,       priority: instant_dm_priority, no_buttons: true,  event: block7.8.day13P.reflection_submitted, canon_wording: "Оплатная рефлексия сдана, требуется проверка"}
    - {id: A1-PENDING-B-URGENT, priority: instant_dm_priority, no_buttons: true,  event: block7.7.phaseB.reflection_pending_21:00}
    - {id: A1-APPEAL-NEW,       priority: instant_dm_priority, no_buttons: true,  event: block10.step6.appeal.open}
    - {id: A1-DYN-ALERT,        priority: instant_dm_priority, event: block14.R271.dynamics_alert}
    - {id: A1-DYN-REVISED,      priority: instant_dm,          event: block14.R288.dynamics_alert_revised}
    - {id: A1-P4-RETURN-N,      priority: instant_dm,          event: appendixA.P-4.return_counter, payload: [n:returns, day_x]}
    - {id: A1-ALL-MISSED,       priority: instant_dm_priority, event: block3.16.all_missed_report, topic: reports}
    - {id: A1-PAUSE-REQ,        priority: instant_dm,          event: block2.pause.requested, buttons: [approve, deny]}
    - {id: A1-DLQ,              priority: instant_dm_priority, event: block15.A3.dlq.poison_threshold}
    - {id: A1-DLQ-DIGEST,       priority: digest_09,           event: block15.A3.dlq.low_freq}
    - {id: A1-REFL-QUEUE,       priority: digest_09,           event: block10.reflections.queue_daily}
    - {id: A1-CHECKUP-DYN-DAILY, priority: digest_09,          event: block14.checkup.daily_agg}
    - {id: A1-EXPORT-READY,     priority: instant_dm,          event: block14.R283.export.ready, ttl_minutes: 15}
    - {id: A1-THRESH-UPDATE,    priority: instant_dm,          event: block14.R381.threshold_update}
    - {id: DIGEST-09,           priority: digest_09,           event: schedule.daily_09_author_tz, draw_skeleton_always: true}
  # ============= T3 =============
  T3:
    - {id: T3-STAGE-DIGEST,     event: block14.R132.stage_published.bulk, gate: no_P4_in_stage}
    - {id: T3-NOON-NUDGE,       event: tz.3.18,       gate: has_open_step AND day_not_13P AND not_shadow}
    - {id: T3-BAD-DAY,          event: tz.3.16,       throttle: 1_per_14d}
    - {id: T3-RETURN-REMINDER,  event: block2.pause.long, gate: pause_not_shadow}
    - {id: T3-REFL-ENCOURAGE,   event: block10.reflection.return, companion_to: T2-REFL-VERDICT-RETURN}
    - {id: T3-REVIVE-WARMTH,    event: block2.C3.revive_by_author, companion_to: T2-REVIVE}

nr_invariants:
  - NR-201: no_user_toggle_for_any_tier
  - NR-202: T1_never_droppable
  - NR-203: no_participant_quiet_mode
  - NR-204: no_emoji_only_headers
  - NR-205: no_word_punishment
  - NR-206: no_addressing_ty
  - NR-207: after_erasure_terminal_no_further_emission
  - NR-208: pause_shadow_never_reveals_shadow
  - NR-209: lives_zero_no_fail_words
  - NR-210: T3_no_metrics_no_comparisons
  - NR-211: T3_gated_by_ban_erased_refund_final_shadow
  - NR-212: text_id_stable_versioned_append_only
  - NR-213: no_emoji_only_meaning
  - NR-214: no_blaming_language
  - NR-215: settings_notifications_screen_cannot_return
  - NR-216: markdown_v2_forbidden_use_html_only
  - NR-217: no_plural_by_string_concat
  - NR-218: no_html_from_unescaped_placeholder
  - NR-219: coalesce_key_never_mixes_event_classes
  - NR-220: no_transport_side_dedup_within_producer_window
  - NR-221: A1_author_messages_never_forwarded_to_participant
  - NR-222: author_address_line_only_canon_8_5
  - NR-223: morning_summary_no_participant_qualifications
  - NR-224: deadline_ladder_no_threat_escalation
  - NR-225: no_explicit_pause_wording_if_shadow_active
  - NR-226: payment_texts_no_debt_words
  - NR-227: shadow_stopwords_lint
  - NR-228: erased_restart_no_prior_progress_reference
  - NR-229: no_medical_terms_without_legal_approval
  - NR-230: personal_alerts_to_author_no_buttons  # canon 7.8
  - NR-231: motivation_suppress_flag_never_introduced  # заменено правилами Р248
  - NR-232: T_silence_synthetic_never_introduced  # единственный «авто-» — П.2
  - NR-233: identity_reidentification_after_erasure_forbidden

fail_safe:
  pre_commit_lint: [stopwords, emoji_quota, vy_check, html_valid, plural_ru_forms_present, escape_placeholders, shadow_stopwords_for_T2_SHADOW]
  tier_default_on_missing: T1
  T3_default_gate_on_missing_signal: suppress
  erased_gate: blocks_all_emission
  T1_change_requires_author_approval: true
  redzone_and_erasure_change_requires_legal_approval: true
  on_template_broken_at_runtime: send_plain_text_no_parse_mode

contracts_out:
  to_block15:
    emit_envelope: {text_id, tier, must_deliver, drop_on_overload, coalesce_key, addressee, payload_vars, parse_mode: HTML, no_buttons?: bool}
    respect_producer_coalescing: true  # no extra dedup within producer window
  to_block10:
    verdict_labels: [ok, return_for_reinforcement]
  to_block14_reads: [checkup.dynamics_signal, R366.reason_code, R381.threshold_update, R283.export_state, R361.recalc_state, T3_gates: {noon_nudge_eligible, stage_digest_eligible, P4_in_stage_flag}]
  to_block7_reads: [ban_reason_class, shadow_reason_enum: [no_verdict, content_frontier, maintenance_overlap]]
  to_block2_reads: [state_transition_events, pause_shadow_active_flag]
  to_block8:
    address_line_format: canon_8_5
    write_button_flow: write_via_bot
  to_block16_reads: [payment_check_window_hours, stage_name_in_payload]

patch:
  base: block9.v3-consolidated-3.0
  version: v3-consolidated-3.1
  supersedes_ids:
    T1-ANTIPIRACY: "text replaced (canon-неутолимый, но новая формулировка честнее)"
    T2-EXPORT-CSV-WARN: "text replaced (added Excel import guidance)"
    T1-MINIAPP-REJECT.session_expired: "moved to dedicated id T1-MINIAPP-SESSION-EXPIRED"

added_rules:
  - R252: html_a_href_allowed_schemes: [https, http, tg]
  - R253:
      long_message_split:
        max_bytes_utf8: 4096
        cut_at_last_whitespace_before: 4000
        close_open_html_tags_at_boundary: true
        reopen_same_tags_in_next_part: true
        suffix: "(часть {k} из {N})"
        suffix_language_note: "'часть' — one|few|many через plural_ru"
  - R254:
      parse_mode_fallback:
        on_html_parse_error: strip_tags_and_send_plain
        preserve_links_as: "{text} ({url})"
        preserve_line_breaks: true
  - R255:
      plural_ru_formula:
        one: "n % 10 == 1 && n % 100 != 11"
        few: "n % 10 in [2,3,4] && (n % 100 < 12 || n % 100 > 14)"
        many: "otherwise"
        rationale: "CLDR; 11..14 всегда many"
  - R256:
      slash_commands_in_text: forbidden_as_sole_action
      preferred: inline_button
      allowed_instruction: "нажмите кнопку [X] в меню бота"
  - R257:
      time_anchor_for_participant_deadlines:
        pattern_suffix: "по Вашему времени"
        applies_to: [deadline_texts, ladder_texts, pause_ending_soon, checkup_nudges]
        does_not_apply_to: [maintenance, dlq, morning_summary]
  - R258:
      gender_neutral_wording:
        prefer_forms: [impersonal, passive, infinitive]
        examples_ok: ["Задание выполнено", "Попытка использована", "Требуется подтвердить"]
        examples_discouraged: ["Вы выполнили", "Вы отправили"]  # допустимы историко-фактически, но не приоритет
        gender_storage_for_grammar: forbidden
  - R259:
      emoji_as_list_marker: forbidden
      allowed_bullets: ["•", "<b>1.</b>", "<b>—</b>"]
  - R260:
      T3_global_rate_limit_per_participant:
        window_hours: 24
        max_messages: 1
        conflict_resolution: earliest_scheduled_wins
        others_in_window: suppressed_silently
        rationale: [anti_spam_fatigue, 152_FZ, GDPR_soft_pressure]

added_nr:
  - NR-234: no_mailto_or_tel_in_html_href
  - NR-235: no_plural_ru_without_canonical_formula
  - NR-236: no_slash_command_as_sole_participant_action
  - NR-237: no_gender_storage_for_notification_grammar
  - NR-238: no_emoji_as_list_marker
  - NR-239: no_more_than_one_T3_per_24h_per_participant
  - NR-240: no_link_loss_on_plain_text_fallback  # ссылки должны сохраняться как text (URL)

text_catalog_delta:
  replace:
    - id: T1-ANTIPIRACY
      text: "Раздел временно недоступен. Мы уже работаем над восстановлением доступа. Ваш прогресс сохранён."
    - id: T2-EXPORT-CSV-WARN
      text: "Внимание: файл содержит служебные данные. При открытии в Excel используйте режим «Импорт текста», чтобы избежать автоматического исполнения формул. Служебный префикс «'» в некоторых ячейках — часть защиты."
  add:
    - id: T1-MINIAPP-SESSION-EXPIRED
      tier: T1
      addressee: participant
      event: block14.miniapp.session_ttl_expired
      text: "Для Вашей безопасности сессия обновлена. Пожалуйста, закройте и откройте этот раздел заново."
    - id: T1-CONSENTS-SCREEN
      tier: T1
      addressee: participant
      event: block10.D2.consents.open
      framing_by: block9
      body_from: config  # список согласий + статусы
      constraints: [self_sufficient_labels, no_emoji_bullets, gender_neutral]
    - id: T1-ERASURE-INITIATE
      tier: T1
      addressee: participant
      event: block10.D2.erasure.initiate
      legal: [152_FZ, GDPR_Art_17]
      text_template: "Удаление персональных данных — необратимое действие. После подтверждения бот больше не сможет писать Вам, а восстановить прежний прогресс будет невозможно. У Вас есть {n:hours} на отмену запроса — после этого удаление будет выполнено."
      requires_legal_approval: true
    - id: T1-ERASURE-COOLING-CANCEL
      tier: T1
      addressee: participant
      event: block10.D2.erasure.cancel_within_cooling_off
      text: "Запрос на удаление отменён. Всё сохранено, продолжаем обычную работу."

miniapp_reject_dict_change:
  removed_from_common_wrapper: [session_expired]
  moved_to_dedicated: {session_expired: T1-MINIAPP-SESSION-EXPIRED}
  remaining_codes_via_common_wrapper: [value_out_of_range, consent_missing, unsupported_format, stage_locked, duplicate_submission, payload_too_large]

lint_additions:
  pre_commit:
    - check_a_href_scheme_in_allowlist
    - check_no_slash_command_as_only_cta
    - check_gender_neutral_preferred_forms  # warning, not hard fail
    - check_no_emoji_as_bullet
    - check_time_anchor_present_in_deadline_ids
    - check_plural_ru_formula_used
  runtime:
    - close_html_tag_stack_at_split_boundary
    - strip_tags_on_parse_error_and_expand_links

contracts_out_updates:
  to_block10:
    reads: [T_cooling_off_hours_for_erasure]  # деф. предложить 24/48; итог у Б10
    provides_wordings: [T1-CONSENTS-SCREEN, T1-ERASURE-INITIATE, T1-ERASURE-COOLING-CANCEL]
  to_block15:
    envelope_extension: {no_mailto_no_tel: true, parts_meta: {k, N}}
  to_block14:
    reads: [miniapp.session_ttl_expired_event]
```
