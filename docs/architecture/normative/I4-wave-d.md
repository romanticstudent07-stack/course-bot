---
file: normative/I4-wave-d.md
patch: I4-WAVE-D
title: "Волна D — Mini App, тексты, темы, /graph, кнопки, финал архитектуры"
block: сквозной (нормативный стек)
status: применён
doc_version: "consolidated v3.8-i4"
parent_doc_version: "consolidated v3.7-i3"
depends_on: [I1-WAVE-A, I2-WAVE-B, I3-WAVE-C]
supersedes_partially: [texts deferred_from_i2, texts deferred_from_i3]
applied_at: "2026-07-24"
source_chunks: [09, 10]
contains:
  - text_registry
  - texts_B9
  - texts_from_prior_waves
  - buttons_tone
  - telegram_topics
  - graph_and_moderation
  - mini_app_client
  - csp_header
  - onboarding_finalization
  - qa
  - ci_checks_i4
  - risk_registry_full
  - architecture_100pct_complete
touches_blocks: [2, 4, 5, 7, 8, 9, 10, 13, 14, 15, 16]
yaml_verbatim: true
defects_logged_in: ../appendix/D-source-defects.md
---

# ПАТЧ И4 — ВОЛНА D: MINI APP + ТЕКСТЫ + ТЕМЫ + /GRAPH + КНОПКИ + ФИНАЛ АРХИТЕКТУРЫ

> **Переопределено ERRATA-UNIFIED.** `mini_app_client.csp_header.default_src: 'none'` отменён: канонично `default-src 'self'` с явным белым списком, запрет `unsafe-eval` и ограничение `frame-ancestors` доменами Telegram сохранены (E2). `totals.risk_registry_total: 19` — исторический снимок; каноническое число рисков — 22 (E4, NOTE1). Заявленный статус «финальной волны» и секция `architecture_100pct_complete` не задают порядок чтения: ниже в цепочке стоят Б17, ERRATA-UNIFIED и SEAM-PATCH-1. В реестр текстов добавлена запись `B7.stage_pass_rollback_not_supported_owner` (ADD4), при этом ERRATA называет носитель `text_catalog_b9` — расхождение имён с `text_registry` не снято. Точка создания участника перенесена в first-launch Mini App, конвейер онбординга E3 сохранён как содержание (SEAM-1). См. [errata-unified.md](errata-unified.md) и [seam-patch-1-onboarding.md](seam-patch-1-onboarding.md).

Четвёртая и последняя волна консолидации. Версия документа: `consolidated-v3.7-i3` → `consolidated-v3.8-i4`. Патч замыкает клиентский контур: всё, что в И1–И3 было отложено формулировкой «текст пишется в И4» или «UI-контракт в И4», здесь получает носитель.

Волна делает четыре вещи. Первое: вводит **единый реестр текстов** (`text_registry`) как источник истины для всех сообщений — с версионированием в git, пространствами имён `{домен}.{имя}`, правовым статусом каждой записи и тремя вариантами тона; ни один текст больше не живёт в коде. Второе: закрывает **клиент Mini App** целиком — кэш IndexedDB с очередью записи, тихая переавторизация, безопасное чтение подписанных ссылок, защита от XSS, CSP, хостинг в РФ. Третье: описывает **поверхность Telegram** — привязки тем, зеркало админ-темы с write-ahead-записью и реактивной сверкой, режим паники и обслуживания. Четвёртое: выдаёт **команду `/graph`** с k-анонимностью 5 и защитой от атаки пересечением, финализирует онбординг (E2 поддержка, E3 конвейер согласий) и QA-матрицы G1/G2.

Патч объявляет себя финальным (`is_final_wave: true`) и содержит секцию `architecture_100pct_complete` — сводку закрытия. При этом в нормативном стеке каталога после И4 стоят ещё три файла (Б17, ERRATA-UNIFIED, SEAM-PATCH-1), которые старше по цепочке старшинства. Самообъявление финальности не отменяет старшинства: при расхождении И4 с errata побеждает errata. Это зафиксировано в [normative/README.md](README.md) и продублировано как дефект исходника.

Структурное отличие от И2 и И3: здесь **нет хвостов** `audit_additions_i4` и `risk_registry_additions_i4` — по прямому указанию `meta.consolidation_note` все дополнения аудита встроены в профильные секции по месту. Ссылки вида «см. audit_additions» из других файлов стека к этому патчу неприменимы.

## Порядок чтения

YAML разрезан по верхнеуровневым секциям в порядке оригинала и вшит в разделы ниже без изменений. Проза между блоками — навигационная, частью нормативного текста не является. Дефекты исходника (невалидный YAML, сбитые отступы, висячие ссылки, проза в полях-скалярах) перенесены дословно и заведены долгом в [../appendix/D-source-defects.md](../appendix/D-source-defects.md), раздел «И4 — Волна D (D-23…D-27)».

## Шапка и мета

```yaml
# =============================================================
# ПАТЧ И4 (КОНСОЛИДИРОВАННЫЙ) — ВОЛНА D
# MINI APP + ТЕКСТЫ + ТЕМЫ + /GRAPH + КНОПКИ + ФИНАЛ АРХИТЕКТУРЫ
# Версия документа: consolidated-v3.7-i3 → v3.8-i4
# Дата: 2026-07-24
# Все дополнения аудита (роли + скептик) встроены в секции по месту.
# =============================================================

meta:
  patch_id: I4-WAVE-D
  parent_doc_version: consolidated-v3.7-i3
  new_doc_version: consolidated-v3.8-i4
  applied_at: "2026-07-24"
  depends_on: [I1-WAVE-A, I2-WAVE-B, I3-WAVE-C]
  is_final_wave: true
  consolidation_note: |
    Этот YAML включает все дополнения из аудита И4 внутри профильных секций.
    Отдельных хвостов audit_additions_i4 / risk_registry_additions_i4 нет — всё в теле.
```

## 1. Реестр текстов — единый источник

Тексты хранятся версионированными YAML-файлами в git, по одному файлу на домен, и адресуются ключом `{домен}.{имя}`. У записи есть правовой статус, варианты тона, параметры подстановки, предельная длина и класс адресата. Сборка падает, если код ссылается на несуществующий ключ или если ключи столкнулись в пространствах имён.

Отдельно зафиксирован запрет на универсальный `render()` с ролью в параметре: рендер разделён на три функции по аудитории, чтобы нельзя было забыть роль наблюдателя и показать участнику владельческий вариант текста.

```yaml
# -------------------------------------------------------------
# TEXT REGISTRY — ЕДИНЫЙ ИСТОЧНИК ТЕКСТОВ
# -------------------------------------------------------------

text_registry:
  storage:
    kind: versioned_yaml_in_git
    path: config/texts/*.yaml
    per_domain_files: true  # RISK-L-16 mitigation
    namespacing_rule: "text_key = {domain}.{name}, e.g. B9.stage_survey_reminder_soft"
    schema:
      key: string_unique_with_namespace
      versions: array of {ver, body, changed_at, changed_by}
      legal_status: enum[approved, pre-legal-review, blocked]
      tone_variants: {soft, neutral, dry}
      params: array of {name, type, required}
      length_max: int
      applies_to_class: enum[A, B, C]

  build_time_lint:
    rule: "every text_key referenced in code must exist in registry"
    fail_on_missing: true
    fail_on_namespace_collision: true

  runtime_render_api:
    # UX caveat 1: no generic render() — split by audience to prevent viewer_role forgetting
    functions:
      render_for_participant(key, params, tone_from_cohort): text
      render_for_owner(key, params): text_owner_variant
      render_for_moderator(key, params): text_moderator_variant  # с фильтром pause_shadow
    forbidden: "generic render() with role as runtime parameter"
    fallback_on_missing_translation: neutral tone
    covers: [tone selection foundation, UX caveat from audit]

  ci_check_class_A_no_settings:
    rule: "class A (personal alerts) must NOT include 'настройки уведомлений'"
    grep_forbidden: ["настройки уведомлений", "notification settings"]
    covers: [NR-215]
```

## 2. Тексты блока 9

Коммуникационный слой получает конкретные ключи: три напоминания о незакрытой анкете с нарастающей сухостью тона, алерты динамики с уже переведённой в локальное время метк  й, уведомления о готовности выгрузки с раскрытием TTL ссылки, коды причин отказа с обязательной парой вариантов (мягкий участнику, технический владельцу — релиз блокируется, если пары нет), индикатор пересчёта, тайм-аут мастера параметров, гейт доставки по состояниям, зеркалирование действий владельцев друг другу, недельный дайджест, эскалация решения о блокировке, санитайзер HTML и тексты режима обслуживания.

Отдельно зафиксирован двойной вид анти-пиратского текста: участник видит только «мягкое удержание», истинная причина рендерится исключительно владельцу.

```yaml
# -------------------------------------------------------------
# ТЕКСТЫ БЛОКА 9 (Б9)
# -------------------------------------------------------------

texts_B9:

  R253_unclosed_survey_reminders:
    text_keys:
      - B9.stage_survey_reminder_soft (1st, +12h after gate open)
      - B9.stage_survey_reminder_neutral (2nd, +36h)
      - B9.stage_survey_reminder_final (3rd, +72h, tone=dry)
    envelope:
      carries: parts_meta {k, N}
      no_reassembly_on_consumer_side: true
    legal_status: approved
    covers: [R253, Р253]

  R271_R288_dynamics_alert:
    text_keys:
      - B9.dynamics_alert
      - B9.dynamics_alert_revised
    payload_fields:
      axes: [...]
      delta_human: "..."
      signal_ids: [...]
      n_returns: N
      day_x: X
      local_ts: "..."  # Р257: already tz_at converted
    legal_status: approved
    covers: [R271, R288]

  R283_export_notification_and_templates:
    text_keys:
      - B9.export_ready_notification
      - B9.export_being_prepared
      - B9.export_failed
    ttl_disclosure: "ссылка активна 15 минут"
    legal_status: approved
    covers: [R283, Р249]

  R366_sync_status_reason_codes:
    reason_code_enum:
      - value_out_of_range
      - consent_missing
      - unsupported_format
      - file_too_large
      - staging_expired
      - checksum_mismatch
      - server_busy
      - insufficient_funds
    # UX caveat 2: two variants per code (participant soft / owner technical)
    each_code_has_dual_variants:
      reason_human_participant: soft, plain language
      reason_human_owner: technical with PSP code if applicable
    example:
      code: insufficient_funds
      participant: "недостаточно средств на счёте отправителя"
      owner: "PSP declined: insufficient funds (code E51)"
    release_gate: "reason_code without BOTH variants blocks release"
    covers: [R366, Р238, UX caveat 2]

  R381_thresholds_updated:
    text_key: B9.checkup_thresholds_updated_notification
    trigger: publish_checkup_config event with kind=safety_critical
    audience: all active participants on current epoch
    legal_status: pre-legal-review
    covers: [R381]

  R361_calculating_indicator:
    text_key: B9.recalculating_now
    body_variants:
      short: "Обновляем расчёт…"
      with_eta: "Обновляем расчёт (обычно до 30 секунд)"
    covers: [R361]

  P411_master_timeout_notification:
    context: 10-min inactivity in parameter master
    action_on_timeout:
      - auto_cancel master state
      - emit master_auto_cancelled event
      - notify owner via admin_topic (NOT DM, avoid spam)
      - notification includes "продолжить с того же места" deeplink
    ui_polish_note: |
      Функциональный контракт закрыт в И4.
      UX-полировка мастера как компонента Mini App — sprint-1 после launch.
    covers: [Р411]

  P455_delivery_gate_states:
    contract: |
      Доставка ✉️ через Бота уважает состояния:
        erased    → silent drop, no DLQ (NR-207)
        hard_ban  → drop with operational log
        muted     → defer until mute expires; queue TTL 7d
    ci_test: "✉️ to erased participant produces no outgoing message"
    covers: [Р455]

  P468_peer_alert_admin_actions:
    contract: |
      Действия одного owner видны второму синхронно через admin_topic.
      Формат: "@owner_2, {actor_role} @{actor_name} выполнил {action} для {target}"
    events_covered:
      - block, unblock
      - refund_initiate, refund_rollback
      - publish_stage, publish_checkup_config
      - override_baseline
      - red_zone_review, red_flags_review
      - whitelist_change
    covers: [Р468]

  P470_weekly_digest:
    schedule: "Monday 09:00 (tz_at owner_1)"
    contents: aggregated counts of admin_actions in last week, per owner, per kind
    delivery: DM to each owner
    covers: [Р470]

  P477_block_escalation_text:
    text_key: B9.block_decision_required
    body: "требуется решение о блокировке участника {pid}, причина {reason_class}"
    audience: both owners simultaneously
    dismissal: "первый нажавший фиксирует решение; событие содержит who_resolved"
    covers: [Р477 escalation scope]

  P494_html_sanitizer:
    allow_list: [b, i, u, s, code, pre, br]
    function_signature: sanitize(text) → {clean_text, warnings[], unparseable[]}
    called_from: write_via_bot before preview render
    preview_shows: clean_text
    warnings_shown_to_sender: yes
    covers: [Р494]

  P497_maintenance_texts:
    text_keys:
      - B9.T1-MAINT
      - B9.T1-MAINT-RESUMED
    retry_on_flag_clear: yes
    covers: [Р497 текстовая часть]

  T1_ANTIPIRACY_dual_view:
    text_keys:
      participant_view: B9.soft_hold_participant
      owner_view: B9.piracy_suspected_owner
    routing: via render_for_participant vs render_for_owner (see text_registry.runtime_render_api)
    forbidden: "рендер истинной причины при viewer=participant"
    ci_test: "участник видит только soft_hold текст независимо от контекста"
    covers: [T1-ANTIPIRACY]

  T3_boolean_gates:
    fields:
      noon_nudge_eligible: bool
      stage_digest_eligible: bool
      P4_in_stage_flag: bool
    T3_sent_within_24h_owner_block: Б9 (last_T3_sent_at)
    Б14_role: read-only consumer
    covers: [Р248, Р260]
```

## 3. Тексты, перенесённые из И2 и И3

Здесь получают носитель тексты, которые предыдущие волны объявили отложенными: ошибки операций с жизнями, весь возвратный контур, ошибки приёма фотографий, тела зон Чек-Апа с фиксированной шапкой «Это не медицинский совет» и кнопкой апелляции, уведомление об отзыве согласия C2 с разбивкой возврата, акт об оказании услуг с трёхдневным сроком молчаливого принятия (не применяется к несовершеннолетним), текст финализации стирания в двух вариантах и экстренный текст Red Flags.

Два текста помечены как блокирующие прод: экстренный текст Red Flags (Д-11) и уведомление о завершении стирания (F2). Оба остаются в статусе `pre-legal-review`.

```yaml
# -------------------------------------------------------------
# ТЕКСТЫ ИЗ И2/И3 (перенесённые в И4)
# -------------------------------------------------------------

texts_from_prior_waves:

  life_op_errors:
    keys:
      - B2.life_below_zero (dry, factual)
      - B2.life_above_max (neutral)
      - B2.life_no_change_no_op (dry, brief)
      - B2.life_op_conflict_retry (neutral)
    legal_status: approved
    covers: [И2 life_op deferred texts]

  refund_participant_texts:
    keys:
      - B16.refund_pending_notification
      - B16.refund_completed
      - B16.refund_declined (uses R366 dual variants)
      - B16.refund_partial_review
      - B16.manual_reissue_notification
    legal_status: pre-legal-review
    covers: [И3 refund deferred texts]

  photo_upload_errors:
    keys:
      - B15.mime_rejected (dry)
      - B15.magic_mismatch (dry)
      - B15.size_exceeded (neutral)
      - B15.staging_expired (neutral)
    legal_status: approved
    covers: [И3 photo deferred texts]

  red_zone_body_texts:
    keys:
      - B5.checkup_zone_green_body (approved)
      - B5.checkup_zone_yellow_body (approved after UX review)
      - B5.checkup_zone_red_body (pre-legal-review, verified_by: legal_block required)
    header_fixed: "Это не медицинский совет"
    appeal_button_present: yes
    covers: [Д-09 body, Р241]

  c2_withdrawal_notification:
    text_key: B16.consent_c2_withdrawn_breakdown
    contents: what happens next + refund breakdown
    legal_status: pre-legal-review
    covers: [Д-27 UI]

  service_acceptance_act:
    text_key: B16.service_delivered_act
    fixed_disclaimer: "Не подтверждение — 3 дня. Мотивированный отказ через Support."
    NOT_applicable_to_minors: true
    legal_status: pre-legal-review
    covers: [Д-28 UI]

  F2_close_event_text:
    text_key: B10.erasure_finalized_notification
    variants:
      user_initiated: push_notification, positive_tone
      ban_expiry_or_deadline: no_push, silent, brief
    legal_status: pre-legal-review  # BLOCKING PROD
    delivery_reliability_note: |
      Push может не дойти при удалённом боте (RISK-L-19).
      Логируем delivery_attempt, не delivery_confirmed.
    covers: [F2 text scope]

  red_flags_emergency_text:
    text_key: B5.red_flags_emergency
    legal_status: pre-legal-review  # BLOCKING PROD, Legal drafts NOW (from И3)
    requirements:
      - phone_24_7
      - explicit_bot_pause_disclosure
      - self_action_hint
    forbidden_content:
      - "мы Вам ответим", "ждите", "скоро"
      - медсоветы, диагнозы, препараты
    covers: [Д-11 text scope]
```

## 4. Кнопки и тон

Четыре правила поверхности: эмодзи только как дополнение к тексту и никогда как замена, лейблы безличные, лейбл читается без контекста экрана, а разрушающие операции подтверждаются модальным окном с фиксированным визуальным контрактом — треугольник предупреждения, одна строка о последствии, строка об обратимости, поле ввода фразы с блокировкой вставки. Для пользователей скрин-ридеров предусмотрен голосовой альтернативный путь подтверждения с аудит-следом.

```yaml
# -------------------------------------------------------------
# КНОПКИ И ТОН
# -------------------------------------------------------------

buttons_tone:

  P207_NR213_emoji_dopolnenie:
    rule: "эмодзи только как ДОПОЛНЕНИЕ к тексту, никогда как замена"
    valid: "❌ Отменить", "Отменить"
    invalid: "❌", "🔴"
    ci_grep_forbidden_labels:
      pattern: "^[emoji]+$"
    covers: [Р207, NR-213]

  P258_impersonal_constructions:
    rule: "лейблы кнопок и подписей — безличные"
    valid: "Отменить", "Отменить эту операцию", "Продолжить"
    invalid: "Вы точно хотите отменить?", "Хочу отменить"
    covers: [Р258]

  G2_Access1_self_sufficient_labels:
    rule: "лейбл читается без контекста экрана"
    ci_check: labels reviewed via A11y checklist
    covers: [G2]

  destructive_ops_UI_extension:
    hard_confirm_modal:
      inherits_from: И1 hard_confirm_pattern
      visual_contract:
        icon: warning triangle
        one_line_description: what will happen
        reversibility_line: "необратимо" OR "обратимо в течение {X}ч"
        text_input_field: with placeholder showing required phrase
        paste_blocked: true  # RISK-L-07 mitigation
      accessibility_alt_path:
        # RISK-L-17 mitigation
        trigger: screen-reader detected OR user opts in
        flow: voice-confirmation with audit trail
        review: sprint-1 post-launch (UX/A11y)
    covers: [И1 hard_confirm UI, RISK-L-07 CLOSED, RISK-L-17 mitigation]
```

## 5. Темы Telegram — поверхность блока 8

Привязки тем хранятся в таблице: обязателен только псевдоним `admin`, остальные опциональны, при отсутствии админ-темы система уходит в личные сообщения владельцам по очереди. Зеркало админ-темы получает write-ahead-запись (сначала строка со статусом «ожидает», затем вызов API, затем подтверждение) и двойную сверку — реактивную в течение тридцати секунд после каждой записи и почасовую полным диффом.

Тема динамики пассивна и принимает только алерты. Участник никогда не пишет владельцу напрямую: сообщение идёт через мастера с санитайзером и предпросмотром. Режим паники выключает вебхук, рассылает текст обслуживания и оставляет break-glass только для админ-команд.

```yaml
# -------------------------------------------------------------
# ТЕМЫ TELEGRAM (Б8) — ПОВЕРХНОСТЬ
# -------------------------------------------------------------

telegram_topics:

  topic_bindings_contract:
    table: topic_bindings
    columns: [alias, thread_id, chat_id, bound_at, bound_by]
    mandatory_alias: admin
    optional_aliases: [dynamics, support, red_zone_reviews, red_flags]
    bind_command: /bind_topic {alias} {thread_id}
    fallback_when_admin_missing: DM to owner_1, then owner_2
    covers: [Р493]

  admin_topic_mirror:
    table: admin_topic_mirror
    columns: [id, thread_id, tg_message_id, ts, payload, checksum, state]
    state_enum: [pending, confirmed, missing]

    # Скептик Q1 fix: write-ahead pattern
    write_ahead_pattern:
      step_1: INSERT into mirror WITH state=pending
      step_2: call TG API sendMessage
      step_3: UPDATE mirror SET tg_message_id=..., state=confirmed
      on_step_2_failure: keep pending, retry via background worker
      on_step_3_failure: reconcile via reactive + hourly check

    # Data caveat fix: reactive check in addition to hourly
    reactive_check:
      trigger: on every write to admin_topic_mirror
      action: within 30s query TG API to verify message + checksum
      on_missing: alert immediately (не ждать hourly)

    hourly_check:
      procedure: diff mirror vs TG API messages
      on_divergence: alert both owners with delta

    tg_topic_settings:
      no_delete: enforced via bot admin rights
      no_edit_own_messages: enforced
    covers: [Р481, Data caveat, Скептик Q1]

  dynamics_topic_passive:
    kind: read_only (no manual messages)
    receives: dynamics_alert / dynamics_alert_revised
    covers: [R288]

  write_via_bot_flow:
    trigger: participant taps "написать" on A1-* alert
    steps:
      - open master wizard
      - text input
      - call sanitize(text) [Р494]
      - show preview with warnings
      - participant confirms
      - message posted via bot
    forbidden: direct participant→owner chat
    covers: [Р250]

  muted_state_matrix:
    added_to_participant_fsm: yes (already in И2)
    UI_indicator: "участник ограничен от отправки сообщений"
    duration_default: 1h (configurable)
    escalation_never_to_banned: enforced by CI [Р477]
    covers: [Р479]

  panic_maintenance_broadcast:
    command: /panic_maintenance {reason}
    actions:
      - webhook off
      - broadcast T1-MAINT to admin_topic + fallback DM to both owners
      - break-glass bypass cache for admin commands only
    unpanic:
      command: /unpanic {passphrase}
      passphrase_source: Р498 durable storage
      resume_broadcast: T1-MAINT-RESUMED
    covers: [Р497]
```

## 6. `/graph` и модерация — блок 7

Команда `/graph` работает только по когортам, идентификатор участника не запрашивается никогда, минимальный размер группы — пять. При недостатке данных выдаётся отказ вместо цифры. Защита от атаки пересечением: все запросы пишутся в приватностный аудит с фильтрами и размером выданной когорты, ежемесячно просматриваются вторым владельцем, при превышении двадцати запросов в день — предупреждение без жёсткого запрета.

Наружу отдаётся только класс причины блокировки; сигнатуры детекторов, оценки и векторы признаков остаются в аудите. Причина теневой паузы выбирается из фиксированного списка, свободный ввод отключён. У срочных алертов кнопок нет намеренно — чтобы не провоцировать импульсивные нажатия в кризисной ситуации. Откат уже применённого прохода этапа не поддерживается: компенсация только ручная, и текст ошибки обязан объяснить ручной путь.

```yaml
# -------------------------------------------------------------
# /GRAPH И МОДЕРАЦИЯ (Б7)
# -------------------------------------------------------------

graph_and_moderation:

  P462_P464_graph_command:
    command: /graph {metric} {period}
    scope: cohort_only (participant_id never queried)
    k_anonymity: min_group_size = 5
    on_insufficient_data: "данных недостаточно для агрегата"
    pii_on_points: none
    audit_layer: operational
    ci_test: enumerate filter combinations, assert all output points satisfy k≥5

    # Скептик Q3: intersection attack defense
    intersection_attack_defense:
      log_all_queries: to privacy_audit
      columns: [owner_id, filters, cohort_size_returned, at]
      periodic_review: monthly by owner-2 (peer review)
      soft_limit: 20 /graph queries per owner per day (warn if exceeded)
      hard_limit: none (owner has right to analytics, everything logged)

    covers: [Р462, Р464, Скептик Q3 intersection attack]

  P208_ban_reason_class_only:
    exposed_externally: enum[behavior, payment_fraud]
    hidden_in_audit_only: detector signatures, scores, feature vectors
    ci_grep_forbidden_in_outgoing: ["detector_score", "confidence", "feature_"]
    covers: [Р208]

  P236_shadow_reason_UI:
    dropdown_source: fixed_list (from И2 pause_shadow.reason_codes_i2)
    free_text_disabled: true
    covers: [Р236 UI, Р476 UI]

  P242_urgent_alerts_no_buttons:
    alert_keys:
      - A1-13P-URGENT
      - A1-PENDING-B-URGENT
    UI_contract:
      no_action_buttons: enforced
      channel: DM to owner (personal, not admin_topic)
      reason: "crisis situations discourage impulsive taps"
    covers: [Р242]

  P435_approve_reflection:
    button_label: "Зачесть рефлексию"
    on_tap_confirmation: "проход применится Днём 14"
    revert_window: until Б7.7 (before stage_apply)
    covers: [Р435]

  P437_rollback_applied_stage:
    contract:
      stage_pass_rollback: not_supported
      compensation: manual (owner creates compensating stage_completed or /revert prior day)
      documented_in_UI: yes, error text explains manual path
    covers: [Р437]
```

## 7. Клиент Mini App

Полная реализация клиента. Снимок данных живёт в IndexedDB сутки, при возрасте старше пяти минут помечается устаревшим; очередь записи переживает перезагрузку страницы и повторяется с экспоненциальной задержкой по ключу идемпотентности из И2. При конфликте 409 локальные данные считаются повреждёнными, кэш стирается при следующем открытии, событие пишется в аудит безопасности.

Подписанные ссылки читаются только через `fetch` в blob с обязательным отзывом объектного URL; прямые ссылки, запись в историю и присвоение `window.location` запрещены — с единственным контролируемым исключением для файлов больше десяти мегабайт. Вставка HTML через `innerHTML` и родственные API запрещена, санитайзер общий с ботом. CSP запрещает `unsafe-eval`, хостинг и TLS — в российском контуре.

Здесь же четыре правовых UI-гейта: ссылки на политику приватности в постоянном подвале, модальное согласие при первом запуске с блокировкой интерфейса до отметки, кнопка DSAR-выгрузки в профиле и отзыв согласия на фото с запуском саги стирания. Правка базовой линии владельцем проходит через детектор персональных данных и чёрный список терминологии до отправки.

```yaml
# -------------------------------------------------------------
# MINI APP КЛИЕНТ — ПОЛНАЯ РЕАЛИЗАЦИЯ
# -------------------------------------------------------------

mini_app_client:

  R339_indexeddb_cache:
    snapshot_ttl: 24h
    stale_flag: shown when snapshot older than 5min
    write_queue:
      persistence: IndexedDB (survives page reload)
      retry_policy: exponential backoff, per client_op_id
      idempotency: client_op_id from И2 idempotency_keys

    # Скептик Q2 fix: 409 UX contract
    conflict_ux:
      on_server_409:
        show_error: "локальные данные повреждены; переоткройте Mini App"
        action: full IndexedDB wipe on next open
        log: security_audit event client_op_id_conflict

    covers: [R339, Скептик Q2]

  R380_cleanup:
    on_webapp_close: wipe sensitive fields within 24h TTL guarantee
    on_tg_user_id_change: full wipe immediately
    triggers:
      - Telegram.WebApp.close() event
      - Telegram.WebApp.initDataUnsafe.user.id mismatch on load
    covers: [R380]

  R368_10mb_threshold:
    kind_le_10mb:
      strategy: fetch → blob → URL.createObjectURL → download
      revoke: URL.revokeObjectURL after download click
    kind_gt_10mb:
      strategy: direct navigation via signed-URL with Content-Disposition attachment
    covers: [R368, R369]

  R370_R371_silent_reauth:
    schedule:
      periodic: every 45min
      pre_expiry: 5min before token exp
      pre_action: before finalize/upload/export commands
    on_401_from_reauth:
      # RISK-L-18 mitigation
      action: show explicit reconnect prompt "войдите заново через Telegram"
      never_silent_fail: enforced by test G1
    covers: [R370, R371, RISK-L-18]

  R338_empty_state_tutorial:
    condition: participant has no measurements yet
    show: demo=true tutorial screens (П-21)
    dismiss: on first real action
    covers: [R338]

  R348_mobile_first:
    platform_check: Telegram.WebApp.platform
    graceful_degradation:
      unsupported_platform: show fallback to bot commands
    responsive_breakpoints: mobile (default), tablet (≥768px minor tweaks)
    covers: [R348]

  R343_signed_url_read_safety:
    strategy: fetch(signed_url) → blob → URL.createObjectURL
    revoke_after_use: mandatory
    referrer_policy: no-referrer (meta tag + fetch header)
    forbidden:
      - <a href="signed_url">
      - history.pushState(signed_url)
      - window.location = signed_url (except for >10Mb direct nav, controlled context)
    covers: [R343, NR-234]

  R342_xss_defense:
    escape_all_user_generated: mandatory
    forbidden_api: [innerHTML, insertAdjacentHTML, document.write]
    sanitizer_shared_with_bot: reuse Р494 allow-list [b, i, u, s, code, pre, br]
    covers: [R342]

  R365_sync_banner:
    trigger: unsynced write-queue non-empty on Mini App open
    banner_text_key: mini_app.sync_banner_pending
    dismissible: no (until sync completes or manual "discard local" action)
    covers: [R365, Sync-баннер]

csp_header:
    default_src: "'none'"
    script_src: "'self' https://telegram.org"
    img_src: "'self' https://{s3-domain-ru} data: blob:"
    connect_src: "'self'"
    style_src: "'self' 'unsafe-inline'"
    frame_ancestors: "https://telegram.org"
    forbidden: unsafe-eval
    report_endpoint: /security/csp-report
    covers: [R372, R344]

  hosting_and_tls:
    region: RU (Yandex Cloud primary / Timeweb reserve per Д-29)
    tls_version_min: 1.2
    covers: [R341]

  D_13_privacy_links_UI:
    placement:
      footer: fixed, always visible
      bot_help_command: /help renders links
    covers: [Д-13 UI]

  D_14_first_launch_consent_UI:
    modal_on_first_open:
      checkbox_default: unchecked
      block_all_ui_until_checked: true
      write_before_render: consent_event to outbox, wait for ack up to 3s
      on_ack_timeout: show retry (participant sees checkbox again)
    covers: [Д-14 UI]

  D_15_dsar_export_UI:
    button_location: "Мои данные" in profile
    action: POST /export/request kind=full
    delivery:
      small: sendDocument
      large: signed-URL banner with TTL 15min
    sla_response: 10 working days (152-ФЗ ст.20)
    covers: [Д-15 UI]

  photo_consent_revocation_UI:
    location: profile → "Мои согласия" → C5 row → revoke button
    revoke_flow:
      - hard_confirm modal (phrase: "ОТОЗВАТЬ СОГЛАСИЕ НА ФОТО")
      - consent_event(pid, C5, revoke) written to outbox
      - trigger photo_erasure_saga (from И3 R334)
      - confirmation with 30-day operator response notice
    covers: [U-долг, R378 UI]

  baseline_override_UI_owner_only:
    context: owner viewing participant card
    reason_input:
      free_text: yes
      pii_detector: pre-submit scan for ФИО, phone, email patterns  # RISK-L-11
      fz323_blacklist: pre-submit scan
      on_detection: reject submit + warn owner
    hard_confirm_phrase: "ИЗМЕНИТЬ БАЗУ"
    covers: [R358 UI, Р488 UI, RISK-L-11 CLOSED]

  config_safety_critical_UI:
    trigger: owner publishes checkup_config with kind=safety_critical
    UI_gate:
      hard_confirm_phrase: "ПРИМЕНИТЬ ЗАДНИМ ЧИСЛОМ"
      show_impact_estimate: "затронет X участников на epoch Y"
    covers: [И3 config_change_kind_split UI]
```

## 8. Онбординг — финализация E2 и E3

Поддержка получает вход из бота и из Mini App, отдельную ветку на участника, ручной перехват владельцем через метку и антиспам после пяти сообщений в минуту. Обзорная команда владельца собирает четыре очереди в одном подменю.

Конвейер онбординга задан строгим порядком: возрастной гейт, правовые согласия, оплата, необязательная почта, город, согласие на фото. Каждый шаг логируется в журнал согласий. Тупики перечислены явно, возврат несовершеннолетнего — полный возврат денег и немедленное стирание по протоколу утечки. Повторная регистрация требует предварительного «надгробия», трение при возвращении включается только при обнаружении артефакта антифрода.

```yaml
# -------------------------------------------------------------
# ONBOARDING (Б4) — ФИНАЛИЗАЦИЯ E2/E3
# -------------------------------------------------------------

onboarding_finalization:

  E2_support:
    routing:
      participant_entry: /support command in bot OR "Помощь" in Mini App
      thread_creation: dedicated support_thread per participant
      bot_human_handoff: owner tags thread with `human_active` label
      antispam: mute participant after 5 messages/minute in support
    owner_ui:
      support_overview: /support_inbox command
      submenu: [open_tickets, red_zone_reviews, red_flags_reviews, refund_appeals]
    covers: [E2]

  E3_onboarding_pipeline:
    steps_order: strict [age_18_plus_gate, legal_consents_C0_C6, payment, email_optional, city, photo_C5]
    audit_log_consents:
      table: consent_events (already in И1 R378)
      each_step_logged: yes
    dead_ends:
      Р47: [payment declined 3 times, C2 refused after start attempt, age hard_check fail]
      handling: friendly explanation + retry OR refund path
    minor_return:
      Р48: full refund + immediate erasure (Д-05 leak protocol)
    three_flags: [onboarded, paid, checkup_started]
    reregistration:
      tombstone_required_prior: yes
      T2-RETURN-FRICTION: only if anti-abuse artifact detected (Р243)
    covers: [E3]

  photo_consent_C5_step:
    placement: BEFORE first photo upload attempt
    ui: dedicated screen (not bundled with C1-C4)
    gate: photo upload endpoint returns 403 if C5 not granted
    revocation_channel: mini_app profile
    covers: [R318 UI, R378 UI]
```

## 9. QA — финальная поставка G1 и G2

Матрица разрешений перечисляется по трём измерениям (роль наблюдателя, состояние цели, операция) и требует либо разрешения, либо явного кода ошибки — молчаливый отказ считается дефектом. Добавлены случаи из рисков: явное приглашение переподключиться при 401, отказ `/graph` при недостаточной когорте, логирование паттерна пересечения.

```yaml
# -------------------------------------------------------------
# QA (G1, G2) — ФИНАЛЬНАЯ ПОСТАВКА
# -------------------------------------------------------------

qa:

  G1_resolver_test_cases:
    table: test cases matrix
    dimensions:
      - viewer_role: [participant, owner, moderator, finance]
      - target_state: [active, sleeping, muted, erased]
      - operation: [read_card, write_message, initiate_refund, export]
    expected_outcomes: resolved or explicit_error_code
    forbidden_pair_examples:
      - (participant, other_participant.card, read_card) → 403 explicit
      - (moderator, any_pid, initiate_refund) → 403 explicit
    added_test_cases:
      - (mini_app, 401 from reauth) → explicit reconnect prompt (RISK-L-18)
      - (owner, /graph, insufficient k) → "данных недостаточно"
      - (owner, /graph, intersection pattern) → logged, warn at soft_limit
    covers: [G1, Т4, RISK-L-18 test]

  G2_self_sufficient_labels:
    checklist: A11y labels review
    accessibility_alt_paths:
      hard_confirm_voice: for screen-reader users (RISK-L-17)
    covers: [G2, RISK-L-17]
```

## 10. CI-чеки И4

Девятнадцать проверок: тон и вид лейблов, полнота и уникальность реестра текстов, запрет прямых ссылок и небезопасного HTML в клиенте, k-анонимность и логирование `/graph`, блокировка релиза при неодобренных юристом текстах Red Flags и F2, обязательность парных вариантов кодов причин, запрет универсального `render()`, реактивная сверка зеркала админ-темы, поведение при 409, блокировка вставки в модальном подтверждении и работа детектора персональных данных.

```yaml
# -------------------------------------------------------------
# CI-CHECKS И4 (СВОДКА)
# -------------------------------------------------------------

ci_checks_i4:
  - name: no_emoji_only_button_labels
    grep: labels with only emoji chars
    covers: [Р207, NR-213]
  - name: no_notification_settings_class_A
    grep: "настройки уведомлений" in class A texts
    covers: [NR-215]
  - name: no_first_person_button_labels
    grep: ["Я хочу", "Мой выбор"] в лейблах
    covers: [Р258]
  - name: text_registry_completeness
    build_time: every text_key in code resolves to registry entry
    covers: [text_registry.build_time_lint]
  - name: text_registry_no_namespace_collision
    build_time: unique {domain}.{name} pairs across all YAMLs
    covers: [RISK-L-16]
  - name: no_direct_href_signed_url
    grep_forbidden_in_frontend: '<a href="{signed_url'
    covers: [R343, NR-234]
  - name: no_innerHTML_in_mini_app
    grep_forbidden: [innerHTML, insertAdjacentHTML]
    covers: [R342]
  - name: k_anonymity_graph_output
    unit_test: enumerate filters, verify k≥5
    covers: [Р462]
  - name: graph_query_logged_to_privacy_audit
    unit_test: every /graph invocation writes privacy_audit row
    covers: [intersection attack defense]
  - name: red_flags_text_pre_legal_review_blocks_release
    config_validation: legal_status must be approved
    covers: [Д-11 gate]
  - name: F2_close_text_pre_legal_review_blocks_release
    config_validation: legal_status must be approved
    covers: [F2 gate]
  - name: no_free_text_shadow_reason_UI
    grep: shadow reason input type=text (must be select)
    covers: [Р236, Р476]
  - name: reason_code_dual_variants_exist
    build_time: every reason_code has BOTH participant + owner variants
    covers: [R366 UX caveat 2]
  - name: no_generic_render_call
    grep_forbidden: "render(" without _for_participant/_for_owner/_for_moderator suffix
    covers: [UX caveat 1]
  - name: admin_topic_mirror_reactive_verify
    unit_test: mirror write triggers TG verify within 30s
    covers: [Скептик Q1]
  - name: mini_app_409_ux_shows_correct_error
    unit_test: server 409 → UI shows "локальные данные повреждены"
    covers: [Скептик Q2]
  - name: hard_confirm_paste_blocked
    unit_test: paste event on modal input rejected
    covers: [RISK-L-07]
  - name: pii_detector_baseline_reason
    unit_test: reason containing ФИО/phone/email → rejected
    covers: [RISK-L-11]
```

## 11. Сводный реестр рисков И1…И4

Единственное место в стеке, где реестр рисков собран целиком. Пять базовых операторских рисков свёрнуты в одну запись и отправлены в парковку, дальше идут риски по волнам, часть помечена закрытой ссылкой на конкретную секцию патча, часть — наблюдаемой по метрике. Этот реестр — источник для приложения C: при сборке `appendix/C-registries.md` переносить оттуда, а не собирать заново по файлам.

```yaml
# -------------------------------------------------------------
# РЕЕСТР РИСКОВ — ИТОГ ПО ИТЕРАЦИЯМ И1..И4
# -------------------------------------------------------------

risk_registry_full:

  # Из И1
  RISK-L-01_to_05:
    status: закреплены в reg-архиве Д-38 (парковка OPS)
    detail: 5 baseline рисков оператора

  RISK-L-06:
    title: "Both owners lose keys"
    mitigation: "3-location key storage + notary/bank recovery procedure"
    severity: medium
    from_iteration: И2 (owner recovery)
    status: mitigated

  RISK-L-06_priv_audit:
    title: "Privacy audit lag from S3 outages"
    mitigation: "SLA ≤4h; local WAL fallback"
    severity: medium
    from_iteration: И2
    status: mitigated

  RISK-L-07:
    title: "Owner pastes hard_confirm phrase from clipboard"
    mitigation: "paste event blocked on hard_confirm modal input"
    severity: low
    from_iteration: И2
    status: CLOSED via mini_app_client.destructive_ops_UI_extension

  # Из И2
  RISK-L-08:
    title: "Ordering between outbox_events and outbox_system_events"
    mitigation: "merge by created_at on consumer side"
    severity: medium
    review_frequency: quarterly

  RISK-L-09:
    title: "Hash collision on advisory lock keys at cohort > 10^6"
    mitigation: "acceptable degradation; upgrade to 64-bit at 500k threshold"
    severity: low
    trigger_threshold: 500k participants

  RISK-L-10:
    title: "CI grep false positives on 'banned_'"
    mitigation: "context-aware grep by state=/kind:"
    severity: low

  # Из И3
  RISK-L-11:
    title: "PII leak via baseline_override reason free text"
    mitigation: "PII detector + FZ323 blacklist pre-submit"
    severity: medium
    status: CLOSED via mini_app_client.baseline_override_UI_owner_only

  RISK-L-12:
    title: "Old-epoch participants on outdated checkup_config with bug"
    mitigation: "config_change_kind split (safety_critical vs calibration)"
    severity: medium
    status: mitigated

  RISK-L-13:
    title: "Orphaned staging files if photo saga killed by watchdog"
    mitigation: "staging GC 24h + staging_orphan_rate alert"
    severity: low
    monitored_metric: staging_orphan_rate (>1% warn)

  RISK-L-14:
    title: "Red Flags SLA 24h vs nighttime triggers"
    mitigation: "emergency_text has 24/7 helpline + bot pause disclosure"
    severity: high
    status: CLOSED via texts_from_prior_waves.red_flags_emergency_text
    monitored_metric: red_flags_response_latency (p95)

  RISK-L-15:
    title: "Pillow EXIF strip slow under load"
    mitigation: "monitor ingest_p95_latency; migrate to libvips if >30s"
    severity: low
    trigger_threshold: 30s p95

  # Из И4 (новые)
  RISK-L-16:
    title: "text_key collision in text_registry parallel PRs"
    mitigation: "per-domain YAML files + namespacing ({domain}.{name})"
    severity: low
    status: mitigated via text_registry.storage.namespacing_rule

  RISK-L-17:
    title: "hard_confirm paste-block breaks A11y on iOS Safari VoiceOver"
    mitigation: "voice-confirmation alt path with audit trail; sprint-1 UX/A11y review"
    severity: medium
    review_at: "sprint-1 post-launch"
    status: mitigation planned in buttons_tone.destructive_ops_UI_extension.accessibility_alt_path

  RISK-L-18:
    title: "Silent re-auth doesn't cover TG session revoke"
    mitigation: "on 401 show explicit reconnect prompt; test in G1"
    severity: low
    status: CLOSED via mini_app_client.R370_R371_silent_reauth.on_401_from_reauth

  RISK-L-19:
    title: "erasure_finalized_notification push may not reach if bot deleted"
    mitigation: "log delivery_attempt but not delivery_confirmed; monitor rate <95%"
    severity: low
    monitored_metric: erasure_notification_delivery_rate
    status: monitored
```

## 12. Статус закрытия архитектуры

Итоговая секция объявляет корпус закрытым на версии `consolidated-v3.8-i4` по четырнадцати блокам и сквозным контурам, перечисляет намеренно не закрытое (парковки инфраструктуры, платежей и операций плюс отложенная по решению Автора панель Б17) и фиксирует жёсткие шлюзы прода: юридическая вычитка всех текстов со статусом `pre-legal-review`, из них два критических, уведомление РКН, DPA провайдера, модель угроз УЗ-3 и внешняя правовая экспертиза. Синтетический запуск при этом разрешён — при условии отсутствия реальных персональных данных.

```yaml
# -------------------------------------------------------------
# СТАТУС ЗАКРЫТИЯ АРХИТЕКТУРЫ
# -------------------------------------------------------------

architecture_100pct_complete:
  final_doc_version: consolidated-v3.8-i4
  patch_chain: [I1-WAVE-A, I2-WAVE-B, I3-WAVE-C, I4-WAVE-D]

  closed_100pct_in_i1_to_i4:
    blocks: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 13, 14, 15, 16]
    cross_cutting:
      - Legal (текстовые формулировки под pre-legal-review)
      - Mini App client (full)
      - QA G1/G2
      - Р132 broadcast
      - Правовой контур (152-ФЗ, ЗоЗПП, GDPR compat)

  not_closed_by_design:
    parking_infrastructure:
      debts: [Д-29, Д-30, Д-31, Д-32]
      reason: "выбор облачного провайдера, DPA, модель угроз — при переходе с синтетики"
    parking_payments:
      debts: [Д-33, Д-34, Д-35]
      reason: "income_meter, «Мой налог», токенизация PAN — при подключении реального PSP"
    parking_ops:
      debts: [Д-36, Д-37, Д-38 (finalizing), Д-39, Д-40 (real notification event)]
      reason: "playbooks, календарь ежегодных мероприятий, резервный канал"
    B17_admin_panel:
      status: to be discussed after И4 (per user decision)
      reason: "user-approved deferral"

  totals:
    debts_closed_in_iterations: 250+ identifiers
    ci_checks_total: 40+
    risk_registry_total: 19 (RISK-L-01..19)
    pre_legal_review_texts: 12

  blocking_prod_launch:
    - legal_review_of_all_pre-legal-review_texts (list at prod_launch_gate in И1)
    - CRITICAL: red_flags_emergency_text (Д-11) Legal-approved
    - CRITICAL: F2 erasure_finalized_notification Legal-approved
    - RKN pre-registration (Д-40 real submission)
    - provider DPA (Д-30)
    - threat model УЗ-3 (Д-31)
    - external legal review pass

  ready_for_synthetic_launch:
    conditions_met:
      - I1..I4 patches applied (v3.5-i1 → v3.8-i4)
      - all approved texts in text_registry
      - CI checks all green
      - no real PII yet (synthetic participants only)
    remaining_hard_gates_for_prod: [legal_review, RKN notification, provider DPA, threat model]

  next_scoped_work:
    - Б17 admin panel (per user decision, next after И4)
    - Парковки (Инфра/Платежи/OPS) — по триггерам бизнеса
```

## Что этот патч меняет за пределами своих секций

Три следствия читаются в других файлах каталога. Первое: **тексты больше не принадлежат блокам** — любое сообщение из блоков 2, 5, 9, 10, 15 и 16 адресуется ключом реестра, поэтому тела текстов внутри `03-day-mechanics.md`, `05-checkup.md`, `09-communications.md` и `16-payment.md` следует читать как черновики, а носитель — здесь. Второе: **`hard_ban` в контракте доставки (`P455_delivery_gate_states`) противоречит Р477 из И2**, где состояния `banned_*` удалены; до решения Автора состояние читается через `sleeping` + `author_pause` + owner-review, а сама строка перенесена дословно и заведена дефектом. Третье: **выбор провайдера объявлен дважды** — `hosting_and_tls` называет Yandex Cloud с резервом Timeweb со ссылкой на Д-29, тогда как `not_closed_by_design` держит Д-29 открытым, а И3 держит открытым `D_20_cloud_provider`; до снятия расхождения boot-gate-долг «выбор облачного провайдера» остаётся в [appendix/C-registries.md](../appendix/C-registries.md).

Ещё две записи прода: список текстов со статусом `pre-legal-review` расширен минимум на семь позиций (возвратный контур, тело красной зоны, отзыв C2, акт об оказании услуг, F2, экстренный текст Red Flags, уведомление об изменении порогов), при заявленных в `totals` двенадцати. Точный счёт — открытый долг сверки.

## Связи

Родитель по стеку — [I3-wave-c.md](I3-wave-c.md), таблица старшинства — [normative/README.md](README.md). Следующие по старшинству файлы (Б17, ERRATA-UNIFIED, SEAM-PATCH-1) при расхождении побеждают этот патч, несмотря на `is_final_wave: true`. Обратные ссылки «переопределено E1 / E2 / E3 / E4 / FIX1 / FIX2» будут проставлены в этот файл при обработке ERRATA — до тех пор их отсутствие не означает, что переопределений нет.

Блоки-получатели: [02-access-lives-pause.md](../02-access-lives-pause.md) (тексты life-ops), [04-onboarding.md](../04-onboarding.md) (E2/E3, шаг C5), [05-checkup.md](../05-checkup.md) (тела зон, Red Flags), [07-control-days-moderation.md](../07-control-days-moderation.md) (`/graph`, `muted`, причина теневой паузы), [08-working-group.md](../08-working-group.md) (привязки тем, зеркало), [09-communications.md](../09-communications.md) (реестр текстов), [14-data-durability.md](../14-data-durability.md) (Mini App, CSP), [15-content-antipiracy.md](../15-content-antipiracy.md) (ошибки загрузки, отзыв C5), [16-payment.md](../16-payment.md) (тексты возврата, акт).
