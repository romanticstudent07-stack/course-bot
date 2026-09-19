---
file: normative/seam-patch-1-onboarding.md
patch: SEAM-PATCH-1
title: "Стык онбординга — канал создания участника"
status: применён
doc_version: "consolidated-v3.10.5-onboarding-seam"
parent: "consolidated-v3.10.4-errata-unified"
precedence: "below_errata_unified — ниже единого ERRATA-слоя; уточняет один шов"
contains: [SEAM1_onboarding_channel, known_typo_for_manual_fix, final_state, yaml]
---

# ПАТЧ SEAM-PATCH-1 — СТЫК ОНБОРДИНГА (КАНАЛ СОЗДАНИЯ УЧАСТНИКА)

> **Канонический источник старшинства** — [README.md](README.md), раздел «Две оси: порядок присоединения ≠ ступень старшинства». Цепочка ниже в этом файле — порядок **присоединения**, а не ступень старшинства. Ступень старшинства: `корпус v3 → И1 → И2 → И3 → И4 → Б17 → SEAM-PATCH-1 → ERRATA-UNIFIED (высшая)`.

## Природа слоя

Патч прикрепляется один раз после единого ERRATA-слоя и закрывает единственный шов: канал создания участника. Природа — уточнение стыка, не новая архитектура; конфликтов с предыдущими слоями исходник за собой не признаёт, новых сущностей не заявляет. Старшинство — ниже [errata-unified.md](errata-unified.md).

Полная цепочка присоединения после патча (не ступень старшинства — по старшинству этот файл ниже ERRATA-UNIFIED):

```
корпус v3 → И1 → И2 → И3 → И4 → Б17 → ERRATA-UNIFIED → SEAM-PATCH-1 (этот файл)
```

## Существо шва

В корпусе одновременно жили две несведённые модели входа. Блок 4 (шаги 0–5) и шаг 2 блока 10 описывали создание участника и возрастной гейт внутри диалога с ботом. Патч И1 (`autocreate_source: mini_app_only`) и добор ADD3 единого ERRATA-слоя фиксировали создание только через форму первого запуска Mini App с гейтом внутри неё. Ни одна из моделей другой явно не отменялась.

## Решение

Каноническая точка создания участника — первый запуск Mini App. Обоснование: возрастной гейт Д-05 (мягкий чек-бокс плюс жёсткая проверка даты рождения) требует формы, которую надёжно даёт только Mini App, а создание `pid` привязано к прохождению этой жёсткой проверки инвариантом `INV-AGE-GATE-BEFORE-PID` из ADD3.

Блок 4 при этом не отменяется: его шаги — согласия C1–C6, оплата, анкета, Чек-Ап, правила — остаются каноническим **содержанием** онбординга. Меняется только точка входа и создания `pid`. Экраны блока 4 могут отрисовываться и в Mini App, и как бот-фолбэк, но само создание `pid` и жёсткая проверка возраста — только через путь Mini App. Шаг 2 блока 10 остаётся верен как логика перехода `pre_road → active`: порядок гейтов «возраст → правовое → оплата» не меняется, уточняется лишь, что этот переход исполняется в форме первого запуска, а не в диалоге бота.

Граница бот-фолбэка задана прямо: фолбэк покрывает доставку контента и экранов при недоступности Mini App, но не создание участника. Если Mini App недоступен на самом первом контакте, участник не создаётся до восстановления Mini App либо до реализации резервного бота (парковка OPS). Исходник называет это осознанным компромиссом: возрастной гейт важнее раннего создания `pid`. Отсюда следствие для чтения каталога — регистрационный тупик, который тянулся долгом из И1 и И2, теперь не дефект, а зафиксированное проектное решение; при выключенном kill-switch `miniapp_enabled` регистрация невозможна по определению.

Проверка канала — статический анализ `pid_creation_only_via_mini_app_first_launch`: любой путь создания строки `tg_user_registry` с реальным `pid` вне обработчика первого запуска Mini App блокирует релиз. Она усиливает `no_pid_before_age_hardcheck` из ADD3 со стороны канала.

## Известная опечатка исходника

Патч сам сообщает об опечатке в разделе 8 единого ERRATA-слоя: «отмель text_registry» вместо «отмена text_registry», влияние на смысл — нулевое, действие — ручная правка при удобном случае. По правилу 7 нарезки текст в каталоге не исправлен: он перенесён дословно в [errata-unified.md](errata-unified.md), а правка заведена долгом в [../appendix/D-source-defects.md](../appendix/D-source-defects.md), пункт D-31 «Опечатка "отмель"».

## Связи с каталогом

Ревизия по этому патчу нужна в `04-onboarding.md` (точка входа переносится, содержание остаётся), `10-lifecycle-return.md` (шаг 2 исполняется в форме первого запуска), `14-data-durability.md` (граница бот-фолбэка и паритет Mini App ↔ бот) и [I1-wave-a.md](I1-wave-a.md) (`autocreate_source: mini_app_only` подтверждён и не откатывается).

## YAML — SEAM-PATCH-1 (дословно)

```yaml
# =============================================================
# ERRATA-UNIFIED · SEAM-PATCH-1 (онбординг-канал)
# Прикрепляется ОДИН раз, ПОСЛЕ errata_unified.
# Природа: НЕ новая архитектура. Один шов: канал создания участника.
#          Тело содержит две несведённые модели входа; фиксируем
#          каноничную и роль корпусного Б4 при ней.
# ПРАВИЛО СТАРШИНСТВА: ниже errata_unified; только уточняет шов.
# Версия: consolidated-v3.10.4 → v3.10.5-onboarding-seam
# =============================================================

errata_unified_seam_patch_1:

  meta:
    parent: consolidated-v3.10.4-errata-unified
    new_version: consolidated-v3.10.5-onboarding-seam
    precedence: below_errata_unified
    nature: single_seam_clarification_onboarding_channel
    conflicts_with_prior: none
    net_new_entities: 0

  # -----------------------------------------------------------
  # SEAM1. Канал создания участника: bot-онбординг (корпус Б4/Б10-Ш2)
  # vs Mini App-only-создание (И1 tg_user_id_pid_registry + ADD3).
  # Тело содержит ОБЕ модели, ни одна не супёрсиднута явно.
  # -----------------------------------------------------------
  SEAM1_onboarding_channel:
    conflict: >
      Корпус Б4 (шаги 0–5) и Б10-Ш2 (onboarding_join: age_18plus → legal → payment)
      описывают создание участника и возрастной гейт в bot-flow.
      И1 (tg_user_id_pid_registry: autocreate_source=mini_app_only) и ADD3
      фиксируют создание ТОЛЬКО через Mini App first-launch с гейтом внутри Mini App.
      Две модели входа не были сведены явным решением.
    final_decision: mini_app_first_launch_is_canonical_creation_point
    reason: >
      Возрастной гейт Д-05 (soft-checkbox + hard-check ДР) требует формы,
      которую надёжно даёт Mini App first-launch (ADD3 INV-AGE-GATE-BEFORE-PID).
      Создание pid привязано к прохождению hard-check возраста — это уже
      зафиксировано в И1/ADD3 и не откатывается.
    b4_role_reconciliation: >
      Корпусный Блок 4 (Онбординг) НЕ отменяется: его шаги (согласия C1–C6,
      оплата, анкета, Чек-Ап, правила) остаются каноничным СОДЕРЖАНИЕМ онбординга.
      Меняется только ТОЧКА ВХОДА/создания pid: она в Mini App first-launch,
      а не в bot-flow. Экраны Б4 могут рендериться и в Mini App, и как
      bot-fallback (INV-B14-MINIAPP-BOT-PARITY), но САМО создание pid и
      возрастной hard-check — только через Mini App-путь (ADD3).
    b10_step2_reconciliation: >
      Б10-Ш2 onboarding_join остаётся верен как ЛОГИКА перехода pre_road→active
      (порядок age→legal→payment сохранён). Уточняется лишь, что этот join
      исполняется в Mini App first-launch форме, а не в bot-диалоге.
      Порядок гейтов [age → legal → payment] не меняется.
    supersedes:
      - "Б4 (implicit): создание участника в bot-flow как точка входа"
      - "Б10-Ш2 (implicit): onboarding_join исполняется в bot-диалоге"
    keeps_intact:
      - "Б4 содержание онбординга (согласия, оплата, анкета, Чек-Ап, правила)"
      - "Б10-Ш2 порядок гейтов age→legal→payment"
      - "И1 autocreate_source: mini_app_only"
      - "ADD3 INV-AGE-GATE-BEFORE-PID"
      - "INV-B14-MINIAPP-BOT-PARITY (bot-fallback для контента, НЕ для создания pid)"
    bot_fallback_boundary: >
      Bot-fallback (П-21, INV-B14-MINIAPP-BOT-PARITY) покрывает ДОСТАВКУ
      контента/экранов при недоступности Mini App, но НЕ создание участника:
      если Mini App недоступен на самом первом контакте, участник не создаётся
      до восстановления Mini App (либо до реализации резервного бота, парковка OPS).
      Это осознанный компромисс: возрастной гейт важнее раннего создания pid.
    ci_check:
      name: pid_creation_only_via_mini_app_first_launch
      kind: static_analysis
      scenario: >
        Поиск путей создания строки tg_user_registry с реальным pid вне
        Mini App first-launch handler → block release.
      note: "усиливает ADD3.no_pid_before_age_hardcheck со стороны канала"
    rationale: >
      Без явного сведения двух моделей возможна двойная реализация онбординга
      (bot и Mini App) с расходящимся возрастным гейтом — прямой риск протечки
      гейта Д-05. Фиксируем единую точку создания, сохраняя Б4 как содержание.

  # -----------------------------------------------------------
  # Известная косметика (не слой, для ручной правки)
  # -----------------------------------------------------------
  known_typo_for_manual_fix:
    location: "errata_unified · Раздел 8 · rejected_explicitly.from_document_A · последний пункт"
    text: "'отмель text_registry' → должно быть 'отмена text_registry'"
    impact: none_semantic
    action: manual_edit_at_convenience

  final_state:
    doc_version: consolidated-v3.10.5-onboarding-seam
    normative_stack_final:
      [корпус_v3, И1, И2, И3, И4, Б17, ERRATA_UNIFIED, SEAM-PATCH-1(this)]
    net_new_entities: 0
    architecture_changes: 0
    resolved: [SEAM1_onboarding_channel]
    new_ci_checks: [pid_creation_only_via_mini_app_first_launch]
    ready_for_synthetic_launch: yes
```
