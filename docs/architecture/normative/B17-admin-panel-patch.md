---
file: normative/B17-admin-panel-patch.md
patch: B17-ADMIN-PANEL
title: "Патч Б17 — Панель Автора (административный UI-слой)"
status: применён
doc_version: "consolidated-v3.9-b17"
parent_version: "consolidated-v3.8-i4"
applied_at: "2026-07-24"
depends_on: [I1-WAVE-A, I2-WAVE-B, I3-WAVE-C, I4-WAVE-D]
nature: thin_orchestration_layer
contains: [meta, command_registry, participant_card_actions, audit_log_interface, owner_dashboard, command_palette, broadcast_inspector, b17_ui_invariants, ci_checks_b17, stub_closure, amendments, risk_registry_b17_additions, architecture_final_state_after_b17]
supersedes: none
not_to_be_merged_with: "17-author-panel.md (блок 17, v3.4, NR-17.1…23)"
---

# ПАТЧ Б17 — ПАНЕЛЬ АВТОРА

> **Канонический источник старшинства** — [README.md](README.md), раздел «Две оси: порядок присоединения ≠ ступень старшинства». Цепочка ниже в этом файле — порядок **присоединения**, а не ступень старшинства. Ступень старшинства: `корпус v3 → И1 → И2 → И3 → И4 → Б17 → SEAM-PATCH-1 → ERRATA-UNIFIED (высшая)`.

Пятый файл нормативного стека. Применяется поверх корпуса `consolidated v3` и волн И1–И4 без переписывания их тела; версия документа после применения — `consolidated-v3.9-b17`.

**Это не блок 17.** Блок 17 «Панель Автора / командный режим» — часть корпуса, лежит в [17-author-panel.md](../17-author-panel.md) (v3.4, требования NR-17.1…23) и описывает командный режим как продуктовую поверхность. Патч Б17 — надстройка над волнами И1–И4, которая собирает уже существующие права в единый реестр команд и задаёт интерфейсы. Файлы не сливаются: при расхождении побеждает этот файл как **более старший слой** — он подшит позже И1–И4 (порядок присоединения `корпус v3 → И1 → И2 → И3 → И4 → Б17 → ERRATA-UNIFIED → SEAM-PATCH-1`), а над ним самим стоят SEAM-PATCH-1 и ERRATA-UNIFIED.

Природа патча заявлена самим исходником: `nature: thin_orchestration_layer` — тонкий слой оркестрации, не вводящий новых прав.

## Навигация по патчу (проза — служебная)

Исходный кусок не содержит прозы: он целиком YAML. Раздел ниже — навигационное описание, добавленное при нарезке. Нормативный текст — только дословный YAML в конце файла; при любом расхождении между описанием и YAML читать YAML.

### Инвариант патча

`invariant_B17`: Б17 не вводит новых capability. Каждая команда и каждая кнопка ссылается на существующее право из `role_capability_matrix` (И1, дополнения И2 и И3). Команда в UI без соответствия в матрице блокирует релиз на сборке. Это ключевое утверждение патча и одновременно его самое слабое место: путь к матрице в стеке нигде не назван, а сам реестр команд живёт в git по пути `config/commands/*.yaml` — отсюда RISK-L-20 (доступ к репозиторию обходит модель прав).

### Реестр команд

`command_registry` — версионируемый YAML в git, правило имён `command = /{domain}_{action}`. Схема одной команды объявляет 15 полей: право, поверхности выдачи (`bot_slash`, `mini_app_button`, `card_button`, `command_palette`), схему параметров, требование hard-confirm и ссылку на фразу из `hard_confirm_phrases` (И2/И3), требование причины и её источник (свободный текст либо фиксированный перечень), валидаторы причины (детектор ПДн, чёрный список терминологии по 323-ФЗ), слой аудита (операционный либо приватностный), допустимые состояния участника, SLA ответа владельца и признак оповещения второго владельца после исполнения.

Каталог содержит 35 команд, сгруппированных по шести темам: жизненный цикл участника (`/pause_author`, `/unpause_author`, `/unpause_user`, `/set_shadow`, `/unset_shadow`, `/life`, `/block`, `/unblock`), этапы и откат (`/approve`, `/revert`, `/complete_stage`, `/publish_stage`, `/withdraw_stage`, `/publish_checkup_config`), финансы (`/refund`, `/refund_rollback`, `/finance_summary`), ПДн и медиа (`/override_baseline`, `/export`, `/view_photos`, `/view_change_map`, `/erasure_initiate`, `/erasure_finalize_before_cooling_off`), модерация и поддержка (`/support_inbox`, `/red_zone_review`, `/red_flags_review`), инфраструктура и OPS (`/whitelist_change`, `/panic_maintenance`, `/unpanic`, `/dlq_view`, `/dlq_replay`, `/unfreeze_piracy`, `/bind_topic`, `/audit`, `/legal`). Сам патч в двух местах называет число 25 — расхождение зафиксировано долгом.

Четыре чека сборки: право существует в матрице; фраза hard-confirm существует в реестре фраз; множество прав реестра — подмножество матрицы; красная зона требует hard-confirm.

### Кнопки Карточки участника

`participant_card_actions` раскладывает команды по шести секциям Карточки (состояние, жизненный цикл, финансы, данные, модерация, опасная зона) и задаёт три контура ограничений: по роли, по состоянию участника и по стилю. Опасная секция всегда на красном фоне, остальные команды красной зоны — красная рамка и предупреждающая иконка. Отдельно задан вывод трёх полос паузы (`user_pause`, `author_pause`, `pause_shadow`) с указанием инициатора и кода причины, где теневая пауза видна только владельцу, и три профиля просмотра (`owner_full`, `moderator_reduced`, `finance_financial`).

Поправка патча: стёртые участники не появляются в списках и поиске и доступны только по прямому `pid` с указанием причины обращения.

### Единый интерфейс аудита

`audit_log_interface` разделён на два вида. Операционный собирает журналы админ-действий, переходов состояний, операций с жизнями и саги возврата; приватностный — журнал доступа к ПДн, просмотров фото, событий выгрузки, переопределений базовой линии и показов красной зоны. Приватностный вид доступен только владельцу, оба хранятся бессрочно.

Мета-правило: само открытие `/audit` или `/legal` является событием приватностного аудита и пишется в `pii_access_log`. Экспорт аудита идёт через тот же `export_worker` (И3), требует причины и запрещает формат CSV (защита от Excel-инъекций). Защита от атаки пересечением, введённая в И4 для `/graph`, распространяется на все запросы аудита: логирование всех запросов и мягкий лимит 100 запросов на владельца в сутки.

### Дашборд и палитра

`owner_dashboard` — материализованная read-only проекция `owner_dashboard_state` с семью виджетами: здоровье когорты, очередь `pending_ops_review` из саги возврата, ожидающие разбора red-flags и красные зоны с обратным отсчётом SLA 24 часа, здоровье outbox, здоровье приёма фото и здоровье согласий с алертом на всплеск отзывов C5. Обновление — опрос раз в 30 секунд, при событиях смены состояния до 5 секунд; поправка патча ограничивает поток push-событий до одного в две секунды со склейкой в окне 500 мс.

`command_palette` — вызов по Ctrl+K в Mini App, нечёткий поиск по реестру команд, отфильтрованному правами пользователя. Недоступные команды не показываются вовсе: показ их в виде заблокированных запрещён, чтобы не раскрывать состав полномочий. Выбор команды открывает мастер параметров, который применяет hard-confirm, требование причины и валидаторы прямо из реестра, а исполнение идёт по тем же путям, что и слэш-команда. Поправка патча добавляет подтверждение открытия для `/audit`, `/legal` и `/view_photos` и меняет хранение поисковых запросов с хеша на открытый текст (RISK-L-22).

### Broadcast-инспектор

`broadcast_inspector` — одно окно для состояния асинхронной инфраструктуры: последние записи зеркала админ-темы с признаком расхождения по реактивной сверке из И4, лаг outbox по потребителям, сводка DLQ и здоровье staging-бакета с ручной сборкой мусора. Доступ только владельцу, слой аудита операционный. Поправка добавляет режимы окна и детектор аномалий: превышение медианы событий за семь дней втрое поднимает баннер «нештатная активность» со ссылкой в аудит с предфильтром.

### Инварианты и CI

`b17_ui_invariants`: панель не может ввести действие вне матрицы прав (I_B17_1); все фразы подтверждения берутся из реестра фраз, inline-фразы в коде панели запрещены (I_B17_2); проекция дашборда только на чтение, роль БД для рендера — `SELECT` (I_B17_3); запросы аудита логируются и наблюдаются на паттерны пересечения (I_B17_4). Поправка добавляет I_B17_5 — runtime-проверку, падающую при попытке отрисовать кнопку красной зоны без hard-confirm, с четырьмя воротами (pre-commit, PR, merge, runtime).

`ci_checks_b17` — девять записей, из которых четыре ссылаются на чеки реестра формулировкой «covered above»; собственные пять: права роли дашборда, скрытие недоступных команд в палитре, запись мета-доступа к аудиту, отключение действий для стёртого участника, отрисовка трёх полос паузы.

### Закрытие STUB и статус

`stub_closure` закрывает исходный STUB блока 17 («свод админ-команд, командные кнопки Карточки, аудит-лог доступа») и записывает три компонента сверх него: дашборд, палитру и broadcast-инспектор. Заявлено `remaining_open_after_b17: none` при трёх открытых парковках в той же секции — расхождение заведено долгом.

`architecture_final_state_after_b17` объявляет цепочку из пяти патчей, закрытыми блоки 1–10 и 13–17, готовность к синтетическому запуску и условия прод-запуска: одобрение всех текстов со статусом `pre-legal-review`, Д-40 (РКН), Д-30 (DPA) и Д-31 (модель угроз УЗ-3). Это самооценка исходника: ниже Б17 в цепочке старшинства стоят ERRATA-UNIFIED и SEAM-PATCH-1.

## Что читать за пределами блока 17

Реестр команд Б17 — единственное место в каталоге, где админ-команды собраны в один список со схемой. При работе с блоками 2, 5, 6, 7, 8, 13, 15 и 16 набор доступных владельцу действий и требования к подтверждению читаются отсюда, а не из тел блоков.

Слой аудита у команды — нормативный признак: `/set_shadow`, `/unset_shadow`, `/publish_checkup_config`, `/override_baseline`, `/export`, `/view_photos`, `/view_change_map`, `/erasure_initiate`, `/erasure_finalize_before_cooling_off`, `/red_zone_review`, `/red_flags_review`, `/whitelist_change`, `/unfreeze_piracy`, `/audit` и `/legal` пишутся в приватностный аудит, остальные — в операционный. Это дополняет разделение слоёв из И1 и И2 конкретной привязкой к действиям.

Тексты интерфейса, введённые этим патчем в виде строк (`«Открытие фиксируется в privacy_audit forever. Продолжить?»`, баннер «нештатная активность», ярлык «участник в паузе», подпись `ui_label: "Зачесть рефлексию"`), носителя в `text_registry` (И4) не получили и ключей вида `{домен}.{имя}` не имеют. По старшинству носителем текстов остаётся реестр из И4, поэтому эти строки читаются как черновики, подлежащие переносу.

Три противоречия со стеком выходят за пределы патча и требуют решения Автора, а не чтения по старшинству, поскольку внутри одного файла записаны несовместимые утверждения: команды `/block` и `/unblock` получили hard-confirm, красную зону и оповещение второго владельца при том, что носитель состояния удалён Р477 (И2); роль `moderator` по правилам видимости получает секцию 1 (включая теневую паузу, видимую только владельцу) и секцию 4 «только просмотр» (включая просмотр фото, право на который по умолчанию `never`); `/erasure_finalize_before_cooling_off` позволяет пропустить охлаждение, тогда как И3 требует отсрочки стирания на 14 дней при активном возврате. полный перечень — в [../appendix/D-source-defects.md](../appendix/D-source-defects.md), раздел «Б17 (D-28…D-30)».

## Найденные дефекты исходника

Дефекты не исправлены: YAML ниже перенесён дословно, включая невалидные конструкции, элизию `# ... (все секции выше …)`, псевдотипы прозой, ссылки на отсутствующие в каталоге документы «Решение 2/4/5», «Скептик Q1…Q6», «Data caveat», «UX caveat», «Legal caveat 2» и счётные расхождения. Перечень заведён долгом в [../appendix/D-source-defects.md](../appendix/D-source-defects.md).

## YAML — ПАТЧ Б17 (дословно, без изменений)

```yaml
# =============================================================
# ПАТЧ Б17 — ПАНЕЛЬ АВТОРА
# Версия документа: consolidated-v3.8-i4 → v3.9-b17
# Дата: 2026-07-24
# Природа: UI-slay-слой над И1-И4, без новых capability.
# =============================================================

meta:
  patch_id: B17-ADMIN-PANEL
  parent_doc_version: consolidated-v3.8-i4
  new_doc_version: consolidated-v3.9-b17
  applied_at: "2026-07-24"
  depends_on: [I1-WAVE-A, I2-WAVE-B, I3-WAVE-C, I4-WAVE-D]
  nature: thin_orchestration_layer
  invariant_B17: |
    B17 не вводит новых capability. Каждая команда/кнопка ссылается на
    существующий capability из role_capability_matrix.
    CI: команды в UI Б17 без соответствия в matrix блокируют релиз.

# -------------------------------------------------------------
# COMMAND REGISTRY — ЕДИНЫЙ РЕЕСТР АДМИН-КОМАНД
# -------------------------------------------------------------

command_registry:
  storage:
    kind: versioned_yaml_in_git
    path: config/commands/*.yaml
    namespacing_rule: "command = /{domain}_{action}, e.g. /pause_author"

  schema_per_command:
    name: string
    capability_ref: string (must exist in role_capability_matrix)
    surfaces: array of [bot_slash, mini_app_button, card_button, command_palette]
    params_schema: JSON schema
    hard_confirm_required: bool
    hard_confirm_phrase_ref: nullable (from И2 hard_confirm_phrases)
    reason_required: bool
    reason_source: enum[free_text, fixed_list, none]
    reason_validators: array [pii_detector, fz323_blacklist]
    audit_layer: enum[operational, privacy]
    applies_to_participant_states: array of states
    sla_owner_response: nullable duration
    peer_alert_after_execution: bool

  build_time_lint:
    - "capability_ref must exist in role_capability_matrix"
    - "hard_confirm_phrase_ref must exist in hard_confirm_phrases if required"
    - "reason_validators only applicable when reason_source=free_text"

  commands_catalog:

    # --- Жизненный цикл участника ---
    - name: /pause_author
      capability_ref: pause_author
      surfaces: [bot_slash, card_button]
      params_schema: {pid, duration, reason_code}
      hard_confirm_required: false
      reason_source: fixed_list  # Р476-style
      audit_layer: operational
      applies_to_participant_states: [active, sleeping]
      peer_alert_after_execution: true
      covers: [I2 pause_author]

    - name: /unpause_author
      capability_ref: pause_author  # same right
      surfaces: [bot_slash, card_button]
      params_schema: {pid}
      audit_layer: operational
      peer_alert_after_execution: true

    - name: /unpause_user
      capability_ref: unpause_user
      surfaces: [bot_slash, card_button]
      params_schema: {pid}
      audit_layer: operational
      applies_to_participant_states: [sleeping]
      note: "Возвращает неистраченный остаток квоты user_pause в бюджет"
      peer_alert_after_execution: true
      covers: [Р475]

    - name: /set_shadow
      capability_ref: set_shadow
      surfaces: [bot_slash, card_button]
      params_schema: {pid, duration, reason_code}
      reason_source: fixed_list
      audit_layer: privacy  # shadow — sensitive
      applies_to_participant_states: [active, sleeping]
      peer_alert_after_execution: true
      covers: [Р450, Р476]

    - name: /unset_shadow
      capability_ref: set_shadow
      surfaces: [bot_slash, card_button]
      params_schema: {pid}
      audit_layer: privacy

    - name: /life
      capability_ref: life_op
      surfaces: [bot_slash, card_button]
      params_schema: {pid, delta}
      audit_layer: operational
      note: "Границы [0..3] enforced в И2 life_ops"
      covers: [Р419, Р420]

    - name: /block
      capability_ref: block_participant
      surfaces: [bot_slash, card_button]
      params_schema: {pid, reason_class}
      reason_source: fixed_list
      reason_class_enum: [behavior, payment_fraud]  # Р208
      hard_confirm_required: true
      hard_confirm_phrase_ref: block_participant
      audit_layer: operational
      peer_alert_after_execution: true
      red_zone_ui: true

    - name: /unblock
      capability_ref: unblock_participant
      surfaces: [bot_slash, card_button]
      params_schema: {pid}
      hard_confirm_required: true
      hard_confirm_phrase_ref: unblock_participant
      audit_layer: operational
      peer_alert_after_execution: true
      red_zone_ui: true
      note: "См. Р424 downgrade path при закрытом PITR-окне"
      covers: [Р482]

    # --- Этапы и revert ---
    - name: /approve
      capability_ref: approve_reflection
      surfaces: [bot_slash, card_button]
      params_schema: {pid, reflection_id}
      audit_layer: operational
      ui_label: "Зачесть рефлексию"
      revert_window_until: "Б7.7"
      covers: [Р435]

    - name: /revert
      capability_ref: revert_stage
      surfaces: [bot_slash, card_button]
      params_schema: {pid, from_stage, to_stage}
      audit_layer: operational
      data_mutation: none  # только visible_frontier
      covers: [R258, R259]

    - name: /complete_stage
      capability_ref: complete_stage_manual
      surfaces: [bot_slash, card_button]
      params_schema: {pid, stage_id}
      applies_to_completion_kind: [open_ended]
      audit_layer: operational
      covers: [R324]

    - name: /publish_stage
      capability_ref: publish_stage
      surfaces: [bot_slash, command_palette]
      params_schema: {stage_id}
      audit_layer: operational
      peer_alert_after_execution: true
      broadcast_to_admin_topic: true
      covers: [И2/И3 publish_epoch flow]

    - name: /withdraw_stage
      capability_ref: publish_stage  # same right
      surfaces: [bot_slash, command_palette]
      params_schema: {stage_id}
      audit_layer: operational
      peer_alert_after_execution: true
      broadcast_to_admin_topic: true

    - name: /publish_checkup_config
      capability_ref: publish_checkup_config
      surfaces: [command_palette]
      params_schema: {version_id, kind}
      kind_enum: [safety_critical, calibration]
      hard_confirm_required_when: "kind=safety_critical"
      hard_confirm_phrase_ref: publish_config_safety_critical
      audit_layer: privacy  # threshold changes are sensitive
      peer_alert_after_execution: true
      red_zone_ui_when: "kind=safety_critical"
      covers: [Р489, И3 config_change_kind_split]

    # --- Финансовые операции ---
    - name: /refund
      capability_ref: refund_initiate
      surfaces: [bot_slash, card_button]
      params_schema: {payment_id, amount?, reason}
      reason_source: free_text
      reason_validators: [pii_detector, fz323_blacklist]
      audit_layer: operational
      peer_alert_after_execution: true
      covers: [Р421, Р442 saga entry point]

    - name: /refund_rollback
      capability_ref: refund_rollback_manual_reissue
      surfaces: [command_palette]
      params_schema: {payment_id}
      hard_confirm_required: true
      hard_confirm_phrase_ref: refund_rollback
      audit_layer: operational
      peer_alert_after_execution: true
      red_zone_ui: true
      note: "rollback не изменяет prior refund; создаёт manual_reissue flow"
      covers: [Р465, Р467]

    - name: /finance_summary
      capability_ref: view_payment_data
      surfaces: [bot_slash, command_palette]
      params_schema: {period}
      audit_layer: operational
      covers: [Р491]

    # --- ПДн и медиа ---
    - name: /override_baseline
      capability_ref: override_baseline
      surfaces: [card_button, command_palette]
      params_schema: {pid, field, new_value, reason}
      reason_source: free_text
      reason_required: true
      reason_validators: [pii_detector, fz323_blacklist]  # RISK-L-11
      hard_confirm_required: true
      hard_confirm_phrase_ref: override_baseline
      audit_layer: privacy
      peer_alert_after_execution: true
      covers: [R358, Р488]

    - name: /export
      capability_ref: export_participant_data
      surfaces: [card_button, command_palette]
      params_schema: {pid, kind, reason}
      kind_enum: [json, xlsx, csv, photos, full]
      reason_source: free_text
      reason_required: true  # R298
      audit_layer: privacy
      covers: [R297, R298, R299, R345, R374, R375]

    - name: /view_photos
      capability_ref: view_participant_photos
      surfaces: [card_button]
      params_schema: {pid}
      audit_layer: privacy  # each view logged (Д-22)
      note: "capability default=never; per-owner grant via /grant_photos_access"
      covers: [R314, Д-22]

    - name: /view_change_map
      capability_ref: view_change_map_numbers
      surfaces: [card_button]
      params_schema: {pid, kind}
      kind_enum: [numbers, photos]
      audit_layer: privacy
      covers: [R282, R273, R274]

    - name: /erasure_initiate
      capability_ref: erasure_initiate_by_owner
      surfaces: [command_palette]
      params_schema: {pid, cooling_off_hours?}
      hard_confirm_required: true
      hard_confirm_phrase_ref: erasure_initiate
      audit_layer: privacy
      cooling_off_default: 48h
      peer_alert_after_execution: true
      covers: [T1-ERASURE-INITIATE from И2]

    - name: /erasure_finalize_before_cooling_off
      capability_ref: erasure_finalize_before_cooling_off
      surfaces: [command_palette]
      params_schema: {pid, override_reason}
      reason_source: free_text
      reason_required: true
      hard_confirm_required: true
      hard_confirm_phrase_ref: erasure_finalize_before_cooling_off
      audit_layer: privacy
      peer_alert_after_execution: true
      red_zone_ui: true

    # --- Модерация и Support ---
    - name: /support_inbox
      capability_ref: support_inbox_view
      surfaces: [bot_slash, command_palette]
      params_schema: {filter?}
      filter_enum: [open_tickets, red_zone_reviews, red_flags_reviews, refund_appeals]
      audit_layer: operational
      covers: [E2 from И4]

    - name: /red_zone_review
      capability_ref: red_zone_review_response
      surfaces: [command_palette, card_button]
      params_schema: {ticket_id, decision, note}
      sla_owner_response: 24h
      audit_layer: privacy
      covers: [Д-10]

    - name: /red_flags_review
      capability_ref: red_flags_review
      surfaces: [command_palette, card_button]
      params_schema: {event_id, decision, note}
      decision_enum: [false_positive, confirmed_escalate, needs_more_info]
      sla_owner_response: 24h
      audit_layer: privacy
      peer_alert_after_execution: true
      covers: [Д-11]

    # --- Инфраструктура / OPS ---
    - name: /whitelist_change
      capability_ref: whitelist_change
      surfaces: [command_palette]
      params_schema: {action, target_role, target_user}
      action_enum: [add, remove, change_role]
      hard_confirm_required: true
      hard_confirm_phrase_ref: whitelist_change
      audit_layer: privacy
      peer_alert_after_execution: true
      red_zone_ui: true
      note: "требует подписание нового bootstrap-файла (И1 И-5)"
      covers: [Р459, Р461]

    - name: /panic_maintenance
      capability_ref: panic_maintenance
      surfaces: [command_palette]
      params_schema: {reason}
      audit_layer: operational
      broadcast_to_admin_topic: true
      red_zone_ui: true
      covers: [Р497]

    - name: /unpanic
      capability_ref: panic_maintenance  # same right
      surfaces: [command_palette]
      params_schema: {passphrase}
      audit_layer: operational
      covers: [Р497 unpanic]

    - name: /dlq_view
      capability_ref: dlq_view
      surfaces: [command_palette, broadcast_inspector]
      params_schema: {reason_filter?}
      audit_layer: operational
      covers: [Р490]

    - name: /dlq_replay
      capability_ref: dlq_replay
      surfaces: [command_palette]
      params_schema: {dlq_id}
      audit_layer: operational
      idempotent_by: dlq_id
      covers: [Р490]

    - name: /unfreeze_piracy
      capability_ref: unfreeze_piracy
      surfaces: [command_palette]
      params_schema: {pid}
      hard_confirm_required: true
      hard_confirm_phrase_ref: unfreeze_piracy
      audit_layer: privacy
      peer_alert_after_execution: true
      red_zone_ui: true
      covers: [Р487]

    - name: /bind_topic
      capability_ref: bind_topic
      surfaces: [command_palette]
      params_schema: {alias, thread_id}
      audit_layer: operational
      covers: [Р493]

    - name: /audit
      capability_ref: audit_view
      surfaces: [command_palette]
      params_schema: {layer, filters}
      layer_enum: [operational, privacy]
      audit_layer: privacy  # meta-access itself is privacy-audited (Р427)
      covers: [Р427, Р433]

    - name: /legal
      capability_ref: legal_view
      surfaces: [command_palette]
      params_schema: {pid}
      audit_layer: privacy
      note: "медданные + reflections для юр.контекста; каждое чтение → privacy_audit"
      covers: [Р433]

  ci_checks_registry:
    - name: every_capability_ref_exists
      build_time: capability_ref must resolve in role_capability_matrix
    - name: every_hard_confirm_phrase_exists
      build_time: hard_confirm_phrase_ref must resolve in hard_confirm_phrases
    - name: no_new_capability_introduced_in_registry
      build_time: capability_ref list ⊆ role_capability_matrix keys
      covers: [invariant_B17]
    - name: red_zone_ui_requires_hard_confirm
      build_time: red_zone_ui=true → hard_confirm_required=true

# -------------------------------------------------------------
# КАРТОЧКА УЧАСТНИКА — КОМАНДНЫЕ КНОПКИ
# -------------------------------------------------------------

participant_card_actions:
  layout:
    section_1_state_management: [/pause_author, /unpause_author, /unpause_user, /set_shadow, /unset_shadow, /life]
    section_2_lifecycle: [/approve, /revert, /complete_stage]
    section_3_finance: [/refund]
    section_4_data: [/export, /view_photos, /view_change_map, /override_baseline]
    section_5_moderation: [/block, /unblock, /red_zone_review, /red_flags_review]
    section_6_danger: [/erasure_initiate, /erasure_finalize_before_cooling_off]

  visibility_rules:
    by_role:
      owner: all sections visible
      moderator: sections 1, 2 (approve/revert only), 4 (view only)
      finance: sections 3, 4 (view_change_map for payment context only)
    by_participant_state:
      erased: only /audit trail visible; all actions disabled
      sleeping: full palette but marked "участник в паузе"
      muted: mute-related actions highlighted
      active: default

  red_zone_ui_styling:
    section_6_danger: always red background
    other_red_zone_commands: red border + warning icon
    covers: [Решение 5]

  three_pause_indicators:
    display: three separate strips (user_pause, author_pause, pause_shadow)
    per_strip_info: [set_at, set_until, initiator, reason_code]
    shadow_visibility: owner_only (from И2 Б6 profile rules)
    covers: [Р454]

  view_profile_enforcement:
    owner: owner_full
    moderator: moderator_reduced  # hides sensitive_health + pause_shadow
    finance: finance_financial
    covers: [Р480, Р484]

# -------------------------------------------------------------
# АУДИТ-LOG ЕДИНЫЙ ИНТЕРФЕЙС
# -------------------------------------------------------------

audit_log_interface:
  views:
    operational_view:
      source_tables: [admin_action_log, state_transition_log, life_op_log, refund_saga_log, ...]
      filters: [actor, action_kind, target_pid, time_window]
      access: owner, moderator (limited), finance (payment-related only)
      retention: forever

    privacy_view:
      source_tables: [pii_access_log, photo_view_log, export_event_log, baseline_override_log, red_zone_show_log]
      filters: [actor, target_pid, field_accessed, time_window]
      access: owner_only
      retention: forever

  meta_access_recording:
    rule: |
      Открытие /audit или /legal owner-ом само является событием privacy-audit-а.
      Пишется в pii_access_log(actor=owner, action=audit_meta_view, target=self).
    covers: [Р427, Р433]

  export_of_audit:
    channel: same export_worker (И3)
    reason_required: true
    formats: [json, xlsx]
    csv: not allowed for audit exports  # защита от Excel-injection
    covers: [R298 pattern for audit]

  intersection_defense_extension:
    inherited_from: И4 graph_intersection_attack_defense
    applies_to: all /audit queries
    log_all_audit_queries: to privacy_view itself (мета-запись)
    soft_limit_daily: 100 audit queries per owner
    covers: [audit safety]

# -------------------------------------------------------------
# ДАШБОРД СОСТОЯНИЙ
# -------------------------------------------------------------

owner_dashboard:
  storage:
    kind: materialized_projection
    table: owner_dashboard_state
    refresh_strategy: incremental from events
    read_only_for_ui: true
    covers: [Решение 4]

  widgets:
    cohort_health:
      metrics: [total_active, total_sleeping, total_muted, total_erased_last_30d, avg_lives]

    pending_ops_review:
      source: refund saga pending_ops_review queue
      count + top_5_oldest: displayed
      click_action: open respective ticket

    red_flags_awaiting:
      source: red_flag_event WHERE decision IS NULL
      count + SLA countdown per event: displayed
      sla_reference: 24h from event.at

    red_zone_reviews_awaiting:
      source: red_zone_review_tickets WHERE decision IS NULL
      count + SLA countdown: displayed

    outbox_health:
      metrics: [outbox_lag_seconds, notification_dlq_rate, delivery_latency_p95]
      alert_indicators: green/yellow/red per И2 metric thresholds

    photo_ingest_health:
      metrics: [ingest_success_rate, ingest_p95_latency, staging_orphan_rate]

    consent_health:
      metrics: [C1..C6 grant_rate over cohort, C5_revoke_rate_last_30d]
      alert_on_C5_spike: rate > 5% → warn (possible UX issue)

  refresh_interval: 30s soft (client polling); ≤ 5s on state change events

# -------------------------------------------------------------
# COMMAND PALETTE (MINI APP)
# -------------------------------------------------------------

command_palette:
  location: mini_app top-right; keyboard shortcut Ctrl+K (desktop TG)
  behavior:
    fuzzy_search: over command_registry filtered by user's capabilities
    display_per_command: [name, one_line_description, hotkey?]
    hidden_commands: those where user lacks capability
    forbidden_display: showing commands as disabled (avoid discovery of unavailable powers)

  input_flow:
    - user types command name or intent
    - autocomplete from allowed subset
    - selection opens params wizard
    - wizard applies hard_confirm / reason_required / validators from registry
    - execution goes through same paths as bot_slash surface

  audit: privacy layer (mere search history может выявить намерения)
  note: search queries hashed before storage

  covers: [Решение 2 delivery surface]

# -------------------------------------------------------------
# BROADCAST-ИНСПЕКТОР
# -------------------------------------------------------------

broadcast_inspector:
  purpose: single-pane view of async infrastructure health
  panels:
    admin_topic_mirror_recent:
      display: last 100 records with state (pending/confirmed/missing)
      divergence_banner: when И4 reactive_check detected TG↔mirror mismatch
      action_per_record: [replay, view_details]

    outbox_lag_by_consumer:
      display: lag_seconds per registered consumer
      alert_style: yellow >60s, red >300s

    dlq_summary:
      display: total_size + top_5_reasons + oldest_entry_age
      action: [/dlq_view, /dlq_replay per row]

    staging_bucket_health:
      display: staging_orphan_rate + oldest_orphan_age
      action: trigger_manual_gc (with hard_confirm)

  access: owner_only
  audit_layer: operational

# -------------------------------------------------------------
# UI SURFACE INVARIANTS (Б17-специфичные)
# -------------------------------------------------------------

b17_ui_invariants:

  I_B17_1_no_capability_creation:
    rule: "Панель Б17 не может ввести действие вне role_capability_matrix"
    enforcement: CI ci_checks_registry.no_new_capability_introduced_in_registry
    covers: [invariant_B17]

  I_B17_2_hard_confirm_uniformity:
    rule: "Все hard_confirm-фразы из hard_confirm_phrases (И2 + И3 additions), никаких inline-фраз в UI Б17"
    enforcement: grep forbidden inline confirm phrases in Б17 code

  I_B17_3_dashboard_read_only:
    rule: "owner_dashboard_state — read-only проекция; никаких прямых UPDATE"
    enforcement: DB role for dashboard render = SELECT only

  I_B17_4_intersection_defense_for_audit:
    rule: "Аудит-запросы logged в privacy_audit + мониторинг за intersection patterns"
    inherited_from: И4 graph_intersection_attack_defense
    covers: [audit safety]

# -------------------------------------------------------------
# CI-CHECKS Б17
# -------------------------------------------------------------

ci_checks_b17:
  - name: command_registry_capability_ref_exists
    build_time: covered above
  - name: command_registry_no_new_capabilities
    build_time: covered above
  - name: hard_confirm_phrase_registry_referenced
    build_time: covered above
  - name: red_zone_ui_requires_hard_confirm
    build_time: covered above
  - name: dashboard_read_only_role
    infra_test: DB role permissions verified
  - name: command_palette_hides_unavailable
    unit_test: user without capability X sees no command with capability_ref=X
  - name: audit_meta_access_logged
    unit_test: /audit invocation writes pii_access_log(action=audit_meta_view)
  - name: erased_participant_actions_disabled
    unit_test: card_actions for erased pid show only /audit trail
  - name: three_pause_strips_rendered
    unit_test: card renders three separate pause indicators when applicable

# -------------------------------------------------------------
# ПЕРЕНОСЫ / STUB CLOSURE
# -------------------------------------------------------------

stub_closure:
  original_stub: "STUB Б17 — свод админ-команд, командные кнопки Карточки, аудит-лог доступа"
  closed_by_this_patch:
    - "свод админ-команд" → command_registry (25 команд)
    - "командные кнопки Карточки" → participant_card_actions
    - "аудит-лог доступа" → audit_log_interface
    - "дашборд состояний" → owner_dashboard (бонус, естественное расширение)
    - "command palette" → command_palette
    - "broadcast-инспектор" → broadcast_inspector

  remaining_open_after_b17: none
  next_scoped_work:
    - парковки (Инфра/Платежи/OPS) — по бизнес-триггерам
# =============================================================
# ПАТЧ Б17 (КОНСОЛИДИРОВАННЫЙ) — все дополнения аудита встроены
# consolidated-v3.8-i4 → v3.9-b17
# =============================================================

# ... (все секции выше — command_registry, participant_card_actions, 
#      audit_log_interface, owner_dashboard, command_palette,
#      broadcast_inspector, b17_ui_invariants, ci_checks_b17, stub_closure) ...
# С встроенными правками:

command_registry_amendments:
  /legal:
    reason_required: true  # Legal caveat 2
    reason_source: free_text
    reason_validators: [pii_detector, fz323_blacklist]

owner_dashboard_amendments:
  push_rate_limit:
    per_owner: max 1 event per 2s
    batching: coalesce events within 500ms window
    covers: [Data caveat]

participant_card_actions_amendments:
  erased_visibility_rule:
    rule: "erased participants НЕ появляются в списках/поиске; доступны только по прямому pid+audit_reason"
    covers: [UX caveat, Р496 UI extension]

command_palette_amendments:
  audit_privacy_heavy_open_confirm:
    applies_to_commands: [/audit, /legal, /view_photos]
    ui_step: "Открытие фиксируется в privacy_audit forever. Продолжить?"
    confirm_button: single tap
    distinct_events:
      audit_meta_search: retention 30d
      audit_meta_view: retention forever
    covers: [Скептик Q1]
  audit_note_amendment:
    search_queries_storage: plaintext  # was: hashed, corrected per Скептик Q6

b17_ui_invariants_amendments:
  I_B17_5_runtime_red_zone_assert:
    rule: "runtime assertion: rendering red_zone button without hard_confirm → throw"
    gates: [pre_commit_hook, pr_ci, main_merge_gate, runtime_assert]
    covers: [Скептик Q2 defense in depth]

broadcast_inspector_amendments:
  admin_topic_mirror_recent_extended:
    display_modes: [last_100, last_1h, last_24h, custom_range]
    anomaly_detection:
      rule: "events_per_min > 3x median of last 7d → banner 'нештатная активность'"
      action: link to /audit with pre-filter
    covers: [Скептик Q3]

# -------------------------------------------------------------
# РЕЕСТР РИСКОВ Б17 (продолжение из И1-И4)
# -------------------------------------------------------------

risk_registry_b17_additions:
  RISK-L-20:
    title: "Git-доступ к config/commands/ обходит capability model"
    mitigation: "branch protection на config/commands/ + peer-review вторым owner для capability_ref changes"
    severity: medium
    parking: OPS

  RISK-L-21:
    title: "Быстрая последовательность privacy-actions одним owner до peer_alert"
    mitigation: "≥3 privacy-actions за <5 мин → авто-эскалация: пауза 60s + DM owner-2"
    severity: medium
    implementation: sprint-1 post-launch

  RISK-L-22:
    title: "Command palette query hashing pointless (25-command dict)"
    mitigation: "хранить plaintext (уже применено в patch amendments)"
    severity: low
    status: CLOSED

# -------------------------------------------------------------
# ФИНАЛЬНЫЙ СТАТУС АРХИТЕКТУРЫ
# -------------------------------------------------------------

architecture_final_state_after_b17:
  final_doc_version: consolidated-v3.9-b17
  patch_chain: [I1-WAVE-A, I2-WAVE-B, I3-WAVE-C, I4-WAVE-D, B17-ADMIN-PANEL]

  blocks_closed: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 13, 14, 15, 16, 17]

  totals:
    debts_closed: 250+ from initial delta + Б17 STUB
    ci_checks: 50+ (40 из И1-И4 + 10 из Б17)
    risks_registry: 22 (RISK-L-01..22)
    pre_legal_review_texts: 12

  parkings_open:
    - Infrastructure (Д-29..32)
    - Payments (Д-33..35)
    - OPS (Д-36..40 finalize + Б17 risks 20/21)

  ready_for_synthetic_launch: yes
  ready_for_prod_launch: after all pre_legal_review_texts approved + Д-40 RKN + Д-30 DPA + Д-31 threat model
```
