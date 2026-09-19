---
file: normative/I1-wave-a.md
block: normative
patch_id: I1-WAVE-A
title: "Патч И1 — Волна A: правовой фундамент + инварианты"
status: канон (нормативный стек)
precedence: 1
doc_version: "consolidated v3.5-i1"
parent_doc_version: "consolidated v3"
contains: [meta, invariants I-1…I-6, glossary_patch, role_capability_matrix, hard_confirm_pattern, tg_user_id_pid_registry, feature_flags_miniapp, legal_pack, reg_archive_i1, deferred_from_i1, prod_launch_gate]
---

# ПАТЧ И1 — ВОЛНА A. Правовой фундамент + инварианты

> **Канонический источник старшинства** — [README.md](README.md), раздел «Две оси: порядок присоединения ≠ ступень старшинства». Цепочка ниже в этом файле — порядок **присоединения**, а не ступень старшинства. Ступень старшинства: `корпус v3 → И1 → И2 → И3 → И4 → Б17 → SEAM-PATCH-1 → ERRATA-UNIFIED (высшая)`.

> **Переопределено ERRATA-UNIFIED.** `publish_epoch.owner_block` в `glossary_patch.new_entities_v3_5` отменён: владелец сущности — блок 14, блок 10 только потребляет (FIX1). Возрастной гейт и создание `pid` связаны явным порядком: `pid` не создаётся до жёсткой проверки даты рождения в first-launch Mini App, инвариант `INV-AGE-GATE-BEFORE-PID` (ADD3); при этом `autocreate_source: mini_app_only` подтверждён и не откатывается, а сам регистрационный тупик канонизирован патчем SEAM-1 как проектное решение. Инварианты И-1…И-6 сохранены (попытка их отзыва отклонена). Каноническое число рисков — 22 (E4, NOTE1). Плейсхолдер `{s3-domain-ru}` унифицирован и блокирует прод (раздел 6). См. [errata-unified.md](errata-unified.md) и [seam-patch-1-onboarding.md](seam-patch-1-onboarding.md).

## Место в стеке старшинства

Первый уровень нормативного стека. При расхождении с корпусом `consolidated v3`
(файлы `00`–`17`, `99`) побеждает этот файл. Над ним по старшинству стоят И2, И3,
И4, Б17, SEAM-PATCH-1 и ERRATA-UNIFIED (высшая). Порядок присоединения к документу
был другим:

```
корпус v3 → И1 → И2 → И3 → И4 → Б17 → ERRATA-UNIFIED → SEAM-PATCH-1
```

Патч поднимает версию документа `consolidated v3` → `consolidated v3.5-i1`.
В отличие от поправок v2.1 и v3.1 (только убавляющие), И1 — **добавляющий и
переопределяющий**: он вводит новые сущности, инварианты и CI-чеки, а также
меняет ролевую модель. Формулировка «упоминания миграции и `/place`
недействительны» из корневого README на нормативный стек не распространяется.

## Шлюз перед prod-launch

Все поля со `legal_status: pre-legal-review` блокируют prod-launch
(`meta.legal_gate.required_before_prod_launch: true`). Тексты согласий,
приказ Д-01, договоры помощников, экран ⚖️ Юр.данные и Mini App-ссылки
уходят на внешний ревью (DPO/юрист) до первого реального участника.

## Куда подшивается (перекрёстные ссылки)

| Что вводит И1 | Куда бьёт |
|---|---|
| I_1 `participant_state` — read-only проекция, единственный писатель Б10 | [10-lifecycle-return.md](../10-lifecycle-return.md), все блоки-источники событий |
| I_2 три семантики паузы (`user_pause`, `author_pause`, `pause_shadow`) | [02-access-lives-pause.md](../02-access-lives-pause.md), [debt/02-C3-lives-pause-mercy.md](../debt/02-C3-lives-pause-mercy.md), [debt/07-C2-pause-shadow-contract.md](../debt/07-C2-pause-shadow-contract.md) |
| I_3 outbox + idempotency_keys | [15-content-antipiracy.md](../15-content-antipiracy.md), [16-payment.md](../16-payment.md), [09-communications.md](../09-communications.md) |
| I_4 двухслойное время (UTC + `tz_at`) | [09-communications.md](../09-communications.md), [03-day-mechanics.md](../03-day-mechanics.md) |
| I_5 подписанный bootstrap-whitelist | [17-author-panel.md](../17-author-panel.md), `normative/B17-admin-panel-patch.md` |
| I_6 два слоя аудита | [14-data-durability.md](../14-data-durability.md), [99-legal.md](../99-legal.md) |
| `glossary_patch` (роли owner/moderator/finance, `partner` → deprecated) | [00-glossary.md](../00-glossary.md), [17-author-panel.md](../17-author-panel.md) |
| `role_capability_matrix` | [06-participant-card.md](../06-participant-card.md), [17-author-panel.md](../17-author-panel.md) |
| `tg_user_id_pid_registry` (R327) | [01-architecture.md](../01-architecture.md) — снимает входящий долг из Б14 |
| `feature_flags_miniapp` (R347) | [01-architecture.md](../01-architecture.md), [14-data-durability.md](../14-data-durability.md) |
| `legal_pack` D-/R-серия, `reg_archive_i1` | [99-legal.md](../99-legal.md) и части [99/99-00-digest.md](../99/99-00-digest.md)…[99/99-03-yaml-v2ext.md](../99/99-03-yaml-v2ext.md) |
| `deferred_from_i1` | `normative/I2-wave-b.md`, `I3-wave-c.md`, `I4-wave-d.md` |

Обратные ссылки «переопределено E1/E2/E3/E4/FIX1/FIX2» проставляются в этот
файл при обработке ERRATA-UNIFIED (куски 12a/12b).

## Найденные дефекты исходника (перенесены дословно, не исправлены)

1. `invariants.I_1_single_source_of_state.enforcement` — строка
   `ci_grep_forbidden: "UPDATE participant_state" вне Б10` невалидна как YAML:
   текст после закрывающей кавычки. Парсер падает.
2. `invariants.I_4_two_layer_time.ci_checks` — та же ошибка:
   `grep_forbidden: "по МСК" hardcoded in message templates`.
3. Ключи `closes_debts` и `helper` лежат внутри маппингов `glossary_patch.roles`
   и `glossary_patch.new_entities_v3_5` на одном уровне с элементами: при
   переборе ролей/сущностей `closes_debts` будет прочитан как роль/сущность.
4. Префиксы долгов смешаны в двух алфавитах: латинские `R316`, `R327`, `R347`
   и кириллические `Р400`, `Р443`, `Р477_partial`. Визуально неразличимы,
   `grep` по одному алфавиту теряет половину ссылок.
5. **Коллизия нумерации согласий.** В И1 `C5` = `photo_consent` (спец. категория,
   ст.10 152-ФЗ). В юрблоке `C5` = трансграничная передача (в актуальной
   редакции v2-ext не запрашивается). Также появляется `C0` (возраст 18+) и
   `C6` (в `D_05.leak_protocol` → `revoked`), при этом `D_07` описывает набор
   как «C1-C6». Требуется решение Автора: единый реестр согласий C0–C6.
6. `D_18_erasure_blacklist`: TTL blacklist задан как «≥ полного цикла ротации
   бэкапов», а само число `full_backup_rotation_cycle` — открытый долг юрблока
   (см. [appendix/C-registries.md](../appendix/C-registries.md)). Долг теперь
   блокирует и erasure-контур.
7. `tg_user_id_pid_registry.autocreate_source: mini_app_only` + глобальный
   kill-switch `feature_flags_miniapp.miniapp_enabled` = при выключенном Mini App
   регистрация невозможна вовсе; резервного пути создания участника нет.
   Плюс расхождение с онбордингом через `/start` в Б4/Б10. Кандидат в ERRATA.
8. `hard_confirm_pattern.closes_debts: [self-standing; связано с owner-моделью И1]`
   — в поле списка долгов лежит проза, а не идентификаторы.
9. `I_2` использует нестандартное имя `closes_debts_scope_only`; сборщик реестра
   долгов должен знать оба имени поля.
10. `role_capability_matrix.storage` объявляет колонки
    `(role, capability, allow, reason_required, hard_confirm_required)`, но записи
    `entries_i1` содержат также `mode` и `audit_layer` — схема таблицы не покрывает
    фактические поля.
11. `D_16` закрывает `Д-24`, но Д-24 нигде не описан. В `legal_pack` пропущены
    Д-03, Д-04, Д-06, Д-08…Д-12, Д-15, Д-19…Д-21, Д-25…Д-39 (Д-23 описан только
    внутри `D_05.leak_protocol`, Д-30/Д-31/Д-38 — только в шлюзах).
12. `partner: status: deprecated` требует миграции существующих упоминаний роли
    в Б6/Б17 — задача не заведена ни долгом, ни CI-чеком.

## YAML — патч И1, Волна A (дословно)

```yaml
# ПАТЧ И1 — ВОЛНА A: ПРАВОВОЙ ФУНДАМЕНТ + ИНВАРИАНТЫ
# Версия документа: consolidated v3 → v3.5-i1
# Дата: 2026-07-24
# Статус юр.текстов: pre-legal-review (обязательный ревью до prod-launch)
# =============================================================

meta:
  patch_id: I1-WAVE-A
  parent_doc_version: consolidated-v3
  new_doc_version: consolidated-v3.5-i1
  applied_at: "2026-07-24"
  owners: [owner_1, owner_2]  # два партнёра, равные права
  legal_gate:
    required_before_prod_launch: true
    blocking_fields:
      - "*.legal_status == pre-legal-review"

# -------------------------------------------------------------
# ИНВАРИАНТЫ ПЛАТФОРМЫ (И-1…И-6) — сквозные, обязательны для всех блоков
# -------------------------------------------------------------
invariants:

  I_1_single_source_of_state:
    description: |
      participant_state — единственная read-only проекция состояния участника.
      Пишет только Б10. Все остальные блоки шлют события в Б10 через outbox.
    enforcement:
      - ci_check: view_integrity_check (периодический)
      - ci_grep_forbidden: "UPDATE participant_state" вне Б10
    closes_debts: [R316, R317, Р477_partial]

  I_2_three_pause_semantics:
    description: |
      user_pause, author_pause, pause_shadow — три отдельных поля.
      Раздельные API, раздельные логи, раздельные квоты.
      Приоритет доставки: pause_shadow > author_pause > user_pause.
    fields:
      user_pause: {owner: participant, quota_source: annual_days_budget}
      author_pause: {owner: whitelist_owner, quota_source: none}
      pause_shadow: {owner: whitelist_owner, quota_source: none, visible_to_participant: false}
    closes_debts_scope_only: [Р450, Р454]  # semantics only; full logic in И2

  I_3_outbox_and_idempotency:
    description: |
      Все внешние эффекты (Telegram send, S3, PSP) идут через outbox.
      Каждая операция имеет idempotency key.
    tables:
      idempotency_keys:
        columns: [key, kind, created_at, ttl, result_ref]
        ttl_by_kind:
          financial_ops: 24h
          erasure: forever
          default: 1h
        stable_key_rule: "for one-shot ops, key excludes mutable params"
    closes_debts: [Р443, Р445, Р446_scope, Р447_scope]

  I_4_two_layer_time:
    description: |
      UTC в БД, tz_at(pid, ts) для рендера.
      Ни один текст, уходящий участнику, не собирается без tz_at.
    ci_checks:
      - grep_forbidden: "по МСК" hardcoded in message templates
      - grep_forbidden: raw UTC strftime in outgoing envelope
    closes_debts: [R216_scope, R276_scope, Р257_scope]

  I_5_signed_bootstrap_whitelist:
    description: |
      Whitelist owner-ов хранится в durable-файле, подписанном асимметричным ключом.
      Приватный ключ — офлайн, у обоих owner-ов.
      Верификация подписи при старте бота; несовпадение → panic-mode.
    storage:
      primary_region: RU-Center
      replica_region: RU-North
      signature_algo: Ed25519
      version_field: required
    change_process:
      - propose_change (any owner)
      - sign_new_file (offline, at least one owner key)
      - deploy → audit-sync verify
    closes_debts: [Р459, Р461]

  I_6_dual_audit_layers:
    description: |
      Операционный аудит — транзакционный (in-line с бизнес-транзакцией).
      Приватностный аудит (pii_access_log) — best-effort через outbox.
      Оба — retention forever.
    layers:
      operational_audit:
        write: transactional
        retention: forever
        tables: [state_transition_log, admin_action_log, life_op_log, ...]
      privacy_audit:
        write: best_effort_via_outbox
        retention: forever
        tables: [pii_access_log, photo_view_log, export_event_log, baseline_override_log]
    closes_debts: [Р425, Р426, Р429]

# -------------------------------------------------------------
# ГЛОССАРИЙ v3.4 → v3.5 (Р400/Р473, Р486-Р498)
# -------------------------------------------------------------
glossary_patch:

  roles:
    owner:
      description: "Полные права. В системе строго два owner-а с равными правами."
      max_count: 2
      hard_confirm_required_for: [whitelist_change, refund_rollback, unfreeze_piracy, erasure_finalize_before_cooling_off]
    moderator:
      description: "Помощник Автора, ограниченный view + ограниченные capability."
      view_profile: moderator_reduced  # см. Б6
    finance:
      description: "Только финансовые операции и финансовый view."
      view_profile: finance_financial
    partner:
      description: "DEPRECATED. Мигрировать в owner или moderator."
      status: deprecated
    helper: "Синоним moderator, оставлен как обратно совместимый alias."
    closes_debts: [Р400, Р473]

  new_entities_v3_5:
    publish_epoch:
      owner_block: B10
      type: monotonic_integer
      description: "Инкрементируется на publish_stage / withdraw_stage. Все консьюмеры проверяют epoch."
    dlq_id:
      owner_block: B15
      type: uuid
      description: "Идентификатор записи в DLQ. Используется /dlq_view /dlq_replay."
    is_suspended:
      owner_block: B17
      type: boolean
      description: "Флаг заморозки участника по подозрению (piracy, system_fraud). Снимается только owner-ом."
    visibility:
      owner_block: B16
      enum: [normal, out_of_scope]
      description: "Refund preflight ставит out_of_scope; sweeper-guard уважает."
    modifier:
      owner_block: B16
      enum: [none, freeze_refund]
      description: "Отдельный флаг freeze во время активного refund."
    passphrase:
      owner_block: B15
      description: "Пароль-фраза для /unpanic. Хранится в bootstrap-архиве. Ротация — отдельный контракт."
    topic_alias:
      owner_block: B8
      type: string
      description: "Именованный alias темы (admin, dynamics, support). /bind_topic связывает с thread_id."
    closes_debts: [Р486, Р487, Р488, Р489, Р490, Р491, Р492, Р493, Р494, Р495, Р496, Р497, Р498]

# -------------------------------------------------------------
# МАТРИЦА CAPABILITY (базовая) — раскрывается по блокам
# -------------------------------------------------------------
role_capability_matrix:
  storage: table role_capabilities (role, capability, allow, reason_required, hard_confirm_required)
  ci_check: "no `if role == 'owner'` in business logic; only via matrix"

  entries_i1:
    - {role: owner, capability: whitelist_read, allow: true}
    - {role: owner, capability: whitelist_change, allow: true, hard_confirm_required: true, audit_layer: privacy}
    - {role: owner, capability: view_participant_photos, allow: true, mode: on_grant, audit_layer: privacy}
    - {role: owner, capability: view_change_map_numbers, allow: true, audit_layer: privacy}
    - {role: owner, capability: view_change_map_photos, allow: false}  # default; можно поднять до on_grant
    - {role: moderator, capability: view_participant_photos, allow: false}
    - {role: moderator, capability: view_change_map_numbers, allow: true, audit_layer: privacy}
    - {role: moderator, capability: view_change_map_photos, allow: false}
    - {role: finance, capability: view_payment_data, allow: true, audit_layer: operational}
    - {role: finance, capability: view_health_data, allow: false}
  closes_debts: [R314, R282]

# -------------------------------------------------------------
# HARD-CONFIRM ПАТТЕРН (адаптация под "два owner-а без ко-подписи")
# -------------------------------------------------------------
hard_confirm_pattern:
  description: |
    Механическая страховка от случайных destructive-ops.
    Модальное окно с текстовым вводом фразы, не кнопкой.
    Заменяет отсутствующую ко-подпись второго owner-а.
  ui_contract:
    modal_shows:
      - operation_name
      - operation_effect (в терминах "что станет с данными")
      - reversibility: irreversible | reversible_within_Xh
    input_required: типизация точной фразы (например, "УДАЛИТЬ", "ОТКАТИТЬ ВОЗВРАТ")
    cancel: single_tap
  destructive_ops_list_i1:
    - whitelist_change
    - erasure_finalize_before_cooling_off
    - unfreeze_piracy
    - refund_rollback  # семантика "manual_reissue" — см. Б16
  ci_check: "destructive ops mimo этого списка блокируют релиз"
  closes_debts: [self-standing; связано с owner-моделью И1]

# -------------------------------------------------------------
# REGISTRY TG ↔ PID (R327)
# -------------------------------------------------------------
tg_user_id_pid_registry:
  table: tg_user_registry
  columns: [tg_user_id, pid, created_via, created_at, tombstoned_at]
  autocreate_source: mini_app_only  # /start в боте НЕ создаёт участника
  autocreate_source_reason: "Возрастной гейт Д-05 требует Mini App form"
  tombstone_semantics:
    - "После erasure старая пара (tg_user_id, pid) tombstoned"
    - "Новая регистрация того же tg_user_id → новый pid (Р243)"
    - "T2-RETURN-FRICTION применяется только по анти-абьюз-артефакту"
  closes_debts: [R327]

# -------------------------------------------------------------
# FEATURE FLAGS MINI APP (R347)
# -------------------------------------------------------------
feature_flags_miniapp:
  table: feature_flags
  columns: [scope, scope_id, key, value, ttl, changed_by, changed_at]
  scopes_priority: [global, cohort, pid]  # global выигрывает на выключение
  key_i1: miniapp_enabled
  kill_switch:
    global_off_propagation: immediate
    audit_layer: operational
  closes_debts: [R347, Р486_scope]

# -------------------------------------------------------------
# ПРАВОВОЙ ПАКЕТ — Д-серия и R-серия
# -------------------------------------------------------------
legal_pack:

  D_01_operator_self_appointment:
    description: |
      Приказ Автора о самоназначении ответственным за обработку ПДн (ст.18.1 152-ФЗ).
    artifact: reg_archive/orders/D-01_operator_appointment.pdf
    signed_by: [owner_1, owner_2]
    legal_status: pre-legal-review
    closes_debts: [Д-01]

  D_02_helpers_contracts:
    description: |
      Помощники — только ИП или самозанятые (НПД). Договор ГПХ без признаков трудовых.
      Проверка статуса ИП/НПД перед подписанием + при продлении.
      НПД-ограничение 2 года на одного контрагента.
    checks:
      - inn_status_check_before_contract: required
      - inn_status_recheck_frequency: quarterly
      - npd_two_year_alarm: 22 months → owner alert
    legal_status: pre-legal-review
    closes_debts: [Д-02]

  D_05_age_gate:
    description: |
      Двухуровневый возрастной гейт 18+.
    layers:
      soft_gate:
        type: checkbox
        text_key: consent_C0_age_18_plus
        legal_status: pre-legal-review
      hard_check:
        type: date_of_birth
        rule: "today - date_of_birth >= 18 years"
        rule_check_date_source: "current UTC → tz_at(pid) → local date"
    leak_protocol:  # см. Д-23
      trigger: underage_detected_event
      actions:
        - state → sleeping
        - identity_map_ttl → 7d (вместо 30)
        - deidentification → immediate
        - consent_C6 → revoked
        - rkn_notify → within_24h
    closes_debts: [Д-05, Д-23]

  D_07_legal_data_command:
    description: |
      Команда ⚖️ Юр.данные — доступна участнику из главного меню.
    sections:
      - my_consents_and_versions   # какие C1-C6 даны/отозваны, когда, версия текста
      - retention_policy            # что хранится, сколько, когда обезличивается
      - operator_contacts           # реквизиты, email, ФИО отв. за ПДн
      - third_parties               # PSP, S3-провайдер, tg
      - appeal_channel              # кнопка → Support с меткой legal_appeal
      - politika_pdn_link           # ссылка на публичную политику
    legal_status: pre-legal-review
    closes_debts: [Д-07]

  D_13_mini_app_privacy_links:
    description: "Ссылки на Политику ПДн и Cookie в футере Mini App и в описании бота."
    placement:
      mini_app_footer: required
      bot_help_command: required
    closes_debts: [Д-13]

  D_14_mini_app_explicit_consent:
    description: |
      При первом запуске Mini App — явный чекбокс согласия на обработку ПДн.
      Модель "продолжение использования = согласие" запрещена.
    ui_contract:
      unchecked_by_default: true
      block_all_ui_until_checked: true
      log_event: mini_app_first_consent(pid, ver_of_text, at, ip, ua)
    closes_debts: [Д-14]

  D_16_deidentification_point:
    description: |
      Точка обезличивания identity_map: min(lifecycle_end + 6мес, erasure_request).
      Срок обезличивания: 30 суток от точки.
    table: deidentification_schedule
    columns: [pid, target_at, actual_at, status]
    closes_debts: [Д-16, Д-24]

  D_17_deidentified_logs_retention:
    description: |
      Обезличенные логи — 24 месяца.
      DLQ-обезличенная — 90 суток.
    lifecycle_workers:
      - deidentified_logs_gc: monthly
      - dlq_gc: weekly
    closes_debts: [Д-17]

  D_18_erasure_blacklist:
    description: |
      erasure_blacklist ≥ полного цикла ротации бэкапов.
      При restore из бэкапа — вычистка blacklist-совпадений ДО открытия сервиса.
      Append-only лог операций erasure_blacklist_apply.
    tables:
      erasure_blacklist:
        columns: [pid, erased_at, reason, initiator, ttl_forever]
      erasure_blacklist_apply_log:
        columns: [restore_id, pid, applied_at, blob_refs_deleted[]]
    integration_with_B15: R334_reapply_hook
    closes_debts: [Д-18]

  D_22_pii_access_log:
    description: |
      Любое обращение owner к ПДн участника (включая read-only) логируется.
      Попытка выгрузки данных пользователем не из whitelist блокируется.
    table: pii_access_log
    columns: [actor_role, actor_id, action, target_pid, fields_accessed[], reason, at, ip]
    write_layer: privacy_audit  # best-effort через outbox
    outbound_export_gate:
      whitelist_check: required
      failure_action: block + alert both owners
    closes_debts: [Д-22, Р427_scope, Р433_scope]

  D_40_rkn_pre_registration:
    description: |
      Уведомление РКН как оператора ПДн до начала обработки первого реального участника.
      Портал: pd.rkn.gov.ru.
    gate:
      before_first_real_participant: required
      artifact: reg_archive/rkn/D-40_notification_confirmation.pdf
    closes_debts: [Д-40]

  R_318_photo_consent_spec_category:
    description: |
      Согласие на обработку фото как спец. категории ПДн (ст.10 152-ФЗ).
      Чекбокс C5 (photo_consent). До первой отправки фото — обязателен.
    ui_contract:
      placement: onboarding step, before checkup start
      text_key: consent_C5_photo_special_category
      legal_status: pre-legal-review
      gate: "photo upload endpoint returns 403 if C5 not granted"
    revocation:
      channel: mini_app_profile → "Мои согласия" → отзыв C5
      retro_effect: photo_erasure (S3 layer, см. R334 в Б15)
    closes_debts: [R318, R378_scope]

  R_354_ru_localization:
    description: |
      Локализация всех первичных ПДн и бэкапов в РФ.
      Ежегодная сверка провайдера с реестром РКН операторов, обрабатывающих ПДн в РФ.
    checks:
      annual_provider_review: reg_archive/annual/R-354_provider_review_{year}.pdf
      cross_border_replication: hard_error
    integration_with_B15: [R352, R353, R383]
    closes_debts: [R354]

  R_378_photo_consent_revocation:
    description: |
      Механизм отзыва photo_consent + retro-эффект (erasure фото-слоя).
    tables:
      consent_events:
        columns: [pid, kind, action, at, ip, ua, ver_of_text]
        append_only: true
    revoke_flow:
      - user clicks revoke in Mini App
      - consent_event(pid=..., kind=C5, action=revoke) written
      - photo_erasure_saga triggered (Б15)
      - user sees confirmation with 30-day operator response window
    closes_debts: [R378]

  R_379_staging_bucket_legal:
    description: |
      Правовое обоснование временной обработки фото в staging-bucket:
      исполнение договора (ст.6 ч.1 п.5 152-ФЗ).
      Staging GC 24ч; lifecycle policy обязательна.
    integration_with_B15: [R349, R350, R351, R379_full]
    closes_debts: [R379_legal_scope]

# -------------------------------------------------------------
# REG-АРХИВ (Д-38 частично, полная схема в парковке OPS)
# -------------------------------------------------------------
reg_archive_i1:
  root: reg_archive/
  structure_v1:
    orders/:
      - D-01_operator_appointment.pdf
    policies/:
      - politika_pdn_v1.pdf
      - cookie_policy_v1.pdf
      - retention_policy_v1.pdf
    contracts/:
      - helpers/  # ГПХ шаблон
      - providers/  # DPA с cloud, PSP
    rkn/:
      - D-40_notification.pdf
    consents/:
      - C0_C1_C2_C3_C4_C5_C6_texts_v1.md  # мастер-файл всех текстов согласий
    signature_keys/:
      - whitelist_public_key.pem  # приватный офлайн
  audit:
    all_changes_logged: true
    change_actor: whitelist_owner
  closes_debts: [Д-38_partial]

# -------------------------------------------------------------
# ЯВНЫЕ ПЕРЕНОСЫ В СЛЕДУЮЩИЕ ИТЕРАЦИИ
# -------------------------------------------------------------
deferred_from_i1:
  to_i2_wave_B:
    - Р419: life-ops FOR UPDATE
    - Р420: life-ops border texts
    - Р450: три семантики паузы, полная реализация
    - Р454: три строки паузы в карточке
    - Р475: квота user_pause против цикла
    - Р477: полная ревизия banned_ (CI-guard)
    - R212: outbox-relay
    - R221: outbox retention/compaction
    - R222: метрики delivery-health
    - R226: tier-1 backup RPO≤5м
    - R263: DLQ unknown schema_version
    - R280: DDL/партиции pid_bucket
    - R281: индексы pid_bucket
    - R285: PITR координация
    - R286: единственный триггер stage_completed
    - R316: participant_state read-only проекция (contract only; enforcement И2)
    - R317: view_integrity_check (contract only)
  to_i3_wave_C:
    - refund_saga_full: [Р421, Р442, Р443_saga, Р457, Р458, Р465, Р467, Р496]
    - photo_ingest_saga: [R295, R331, R334, R335, R349, R350, R351, R352, R353, R379_full, R383, R384]
    - checkup: [R234, R235, R236, R237, R279, R284, R305, R306, R307, R308, R324]
    - red_zone: [Д-09, Д-10, Д-11, Д-12]
  to_i4_wave_D:
    - mini_app_client: [R338, R339, R342, R343, R348, R368, R370, R371, R372, R380]
    - texts_B9: [R253, R271, R283, R361, R366, R381]
    - themes: [R288, Р481, Р493, Р497]
    - graph: [Р462, Р464, Р476]
    - buttons_tone: [Р207, Р258, NR-213, NR-215]

# -------------------------------------------------------------
# DUE-DILIGENCE ПЕРЕД PROD LAUNCH (шлюз всех итераций)
# -------------------------------------------------------------
prod_launch_gate:
  legal_review:
    required: true
    scope: "all fields with legal_status == pre-legal-review"
    executor: external_dpo_or_lawyer
    approval_artifact: reg_archive/reviews/legal_review_{date}.pdf
  rkn_notification:
    debt_ref: Д-40
    required: true
  provider_dpa:
    required: true
    debt_ref: Д-30
  threat_model:
    required: true
    debt_ref: Д-31
    level: UZ-3
```
