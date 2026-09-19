---
file: normative/errata-unified.md
patch: ERRATA-UNIFIED
title: "Единый ERRATA-слой (консолидированный)"
status: применён
doc_version: "consolidated-v3.10.4-errata-unified"
parent: "consolidated-v3.9-b17"
precedence: "highest_over_body_and_patches — выше корпуса v3 и патчей И1–И4/Б17"
supersedes_layers:
  - "errata_layer (v3.10)"
  - "errata_addendum (v3.10.1)"
  - "debts_closure_disposition (v3.10.2)"
  - "errata_addendum_2 (v3.10.3)"
  - "errata_addendum_3 (v3.10.4)"
contains: [E1–E4, A1–A3, ADD1–ADD5, FIX1–FIX2, NOTE1–NOTE2, placeholder_gate, disposition_A_B, rejected_explicitly, exhaustiveness_check, final_state, yaml]
---

# ПАТЧ ERRATA-UNIFIED — ЕДИНЫЙ ERRATA-СЛОЙ

> **Канонический источник старшинства** — [README.md](README.md), раздел «Две оси: порядок присоединения ≠ ступень старшинства». Цепочка ниже в этом файле — порядок **присоединения**, а не ступень старшинства. Ступень старшинства: `корпус v3 → И1 → И2 → И3 → И4 → Б17 → SEAM-PATCH-1 → ERRATA-UNIFIED (высшая)`.

## Природа слоя

Слой прикрепляется один раз в самый конец, после патча Б17, и заменяет собой всю прежнюю цепочку из пяти отдельных errata-слоёв (v3.10, v3.10.1, v3.10.2, v3.10.3, v3.10.4). По собственному определению это не новая архитектура: разрешение конфликтов, доборы, зачистка швов и судьба внешних Документов А и Б. Корпус v3 (блоки 1–16) не переписывается, реестр команд Б17, роли и три семантики паузы не трогаются.

Правило старшинства слоя — `highest_over_body_and_patches`: при расхождении с телом корпуса или с любым из патчей И1–И4/Б17 побеждает этот файл. Внутри слоя порядок разделов соответствует хронологии принятия решений, но все решения объявлены действующими одновременно.

## Порядок присоединения после слоя

```
корпус v3 → И1 → И2 → И3 → И4 → Б17 → ERRATA-UNIFIED (этот файл) → SEAM-PATCH-1
```

SEAM-PATCH-1 стоит ниже этого слоя и уточняет единственный шов — канал создания участника, см. [seam-patch-1-onboarding.md](seam-patch-1-onboarding.md).

## Разрешённые конфликты (E1–E4)

**E1 — носитель `participant_state`.** Спор «материализованное представление против обычной таблицы с проектором», тянувшийся внутри И2, решён в пользу обычной таблицы, наполняемой проектором: `REFRESH MATERIALIZED VIEW` берёт блокировку и останавливает читателей, что неприемлемо на горячем пути. Запись разрешена только роли `participant_state_projector`, чтение — `participant_state_reader`, проектор живёт в блоке 10. Строка `projection.kind: materialized_view` из И2 отменена; инвариант единственного источника состояния (И-1) в силе.

**E2 — `default-src` в CSP.** Значение `'none'` из И4 отменено: оно ломает загрузку `telegram-web-app.js`, blob-галереи фото и fetch к подписанным ссылкам S3. Канонична схема `'self'` плюс явный белый список, совпадающая с блоком 14; сохранён запрет `unsafe-eval` и ограничение `frame-ancestors` только домена Telegram. Домен S3 остаётся плейсхолдером — см. плейсхолдер-шлюз.

**E3 — фразовый hard-confirm сохранён.** Попытка отозвать фразовый ввод целиком отклонена: к нему привязаны закрытия RISK-L-07 (блокировка вставки) и RISK-L-17 (голосовой альтернативный путь). Двухшаговое подтверждение и фразовый ввод объявлены не конкурентами, а слоями: обратимые операции — только двухшаг, необратимые разрушающие — двухшаг плюс фраза из реестра `hard_confirm_phrases`.

**E4 — реестр рисков сохранён целиком.** Попытка оставить только RISK-L-01…05 отклонена: среди выпадавших есть риск уровня high (RISK-L-14, Red Flags ночью) и безопасность-критичный RISK-L-06 (потеря ключей владельцами). Канонический состав — RISK-L-01…22, источник истины: `risk_registry_full` из И4 плюс `risk_registry_b17_additions` из Б17.

## Доборы (A1–A3)

A1 вводит почасовую синтетическую пробу идемпотентности консьюмеров `dedup_self_check` с метрикой `dedup_self_check_ok` и оповещением обоих владельцев в админ-тему: у И2 есть метрики отставания и DLQ, но нет активной проверки, что дедупликация действительно работает. A2 требует durable-артефакт ежегодных обязательств (обновление уведомления РКН, ревизия модели угроз, учебная тревога по инцидент-плейбуку, ежегодная сверка реестра провайдеров) — приоритет «желательно до запуска, не блокирует». A3 усиливает уведомление PSP при стирании честной формулировкой для участника о том, что срок хранения платёжных данных у провайдера регулируется его собственными правилами (до 5 лет по 115-ФЗ) и удаление у провайдера не гарантируется; статус текста — `pre-legal-review`.

## Швы (ADD1–ADD5)

ADD1 сводит две разнесённые формулировки защиты outbox в один именованный инвариант `INV-OUTBOX-SENT-AT-COMPACTION`: строка с пустым `sent_at` не удаляется никогда, независимо от возраста, и это проверяется отдельным юнит-тестом. ADD2 достраивает набор метрик широковещательной рассылки пятью новыми показателями (глубина очереди, доли ответов 403 и 429, p95-возраст строки outbox, частота обнаруженных дублей доставки) и явно перечисляет уже существующие, чтобы их не задвоить. ADD3 связывает возрастной гейт и создание участника явным порядком: `pid` не создаётся до прохождения жёсткой проверки даты рождения в форме первого запуска Mini App (`INV-AGE-GATE-BEFORE-PID`); ошибочная формулировка Документа Б о запрете автосоздания через Mini App при этом отклонена. ADD4 добавляет владельцу текст отказа при попытке откатить уже применённый проход Дня, называющий конкретный ручной путь компенсации. ADD5 поднимает незаданное число полного цикла ротации бэкапов до явного блокера boot-gate: пока оно не подставлено, срок хранения `erasure_blacklist` неопределён, а при подстановке берётся более строгая граница из артефакта долга A4 (с учётом WAL), а не нижний порог юрблока.

## Финальные фиксы (FIX1–FIX2)

FIX1 снимает расхождение о владельце `publish_epoch`: строка И1, отдававшая владение блоку 10, отменена, владелец — блок 14, блок 10 остаётся только потребителем с дедупликацией по паре `(stage_id, publish_epoch)`. FIX2 снимает висячую ссылку на приложение трассируемости долгов: приложение переведено в статус внешнего необязательного справочника, хранимого вне архитектурного документа, и при любом расхождении с телом побеждает тело.

## Канонизации (NOTE1–NOTE2)

NOTE1 фиксирует: общее число рисков — 22, число 19 в И4 остаётся историческим снимком и не переписывается. NOTE2 повторяет правило более строгой границы для срока хранения `erasure_blacklist` (сохранено в исходнике намеренно, «для явности», дублируя правило внутри ADD5).

## Плейсхолдер-шлюз

Два плейсхолдера домена S3 (`{s3-domain}` в блоке 14 и `{s3-domain-ru}` в И4) объявлены одним и тем же РФ-доменом, подлежащим унификации в `{s3-domain-ru}` и подстановке на boot-gate; CSP не проходит валидацию, пока плейсхолдер не заменён. Решение не архитектурное — привязано к выбору провайдера (парковка Инфра Д-29…32).

## Судьба Документов А и Б

Оба документа отклонены нормативно. Документ Б снимал бы патчи И1–И4 и Б17, откатывал носитель `participant_state` и отзывал фразовый hard-confirm — то есть давал бы регресс по E1 и E3; его пункт X-DEBT-14 признан фактически неверным. Документ А в нормативной части повторяет те же отзывы. Спасён только справочник «долг → канонический маркер» — как внешний, необязательный, reference-only артефакт с оговорёнными неточностями.

## Связи с каталогом

Ни один из внешних артефактов, на которые слой ссылается (Документ А, Документ Б, «Первый», «Второй», пять исходных errata-слоёв, `reg_archive/annual/calendar.md`, `reg_archive/nav/`), в каталоге `architecture/` не лежит и в него не переносится. Внутрикаталожные адреса решений: E1 и SEAM-1 читаются вместе с [I2-wave-b.md](I2-wave-b.md) и `10-lifecycle-return.md`; E2 и FIX1 — с [I4-wave-d.md](I4-wave-d.md) и `14-data-durability.md`; E3 — с реестром фраз И2/И3 и реестром команд [B17-admin-panel-patch.md](B17-admin-panel-patch.md); E4 и NOTE1 — с `appendix/C-registries.md`; ADD1, ADD2 и A1 — с `15-content-antipiracy.md` и `debt/15-A3-outbox-dlq-saga-granularity.md`; ADD3 — с [I1-wave-a.md](I1-wave-a.md) и `04-onboarding.md`; ADD4 — с `07-control-days-moderation.md` и реестром текстов И4; ADD5 и A3 — с `99-legal.md` и `debt/15-A4-nonreidentifiability-backup-erasure.md`.

Идентификаторы `A1`, `A3` и `A4` в этом слое означают разное в разных разделах: `A1` и `A3` в разделе доборов — новые пункты слоя, тогда как `A4` в ADD5 — артефакт долга блока 15 (`debt/15-A4-…`), а в каталоге уже есть `debt/15-A1-…` и `debt/15-A3-…`. Ссылаться следует с указанием источника: «ERRATA A1» против «долг A1».

## Что слой не закрывает

Заметка каталога, а не утверждение исходника. Три несовместимости патча Б17 этот слой не рассматривает: команды `/block` и `/unblock` при удалённом Р477 носителе состояния, видимость Карточки для роли `moderator` и `/erasure_finalize_before_cooling_off` против отсрочки стирания из И3. Роли `finance` и `moderator` по-прежнему не определены. Состояние `hard_ban` в контракте доставки И4 не вычеркнуто. До решения Автора действуют более строгие требования И2 и И3.

## YAML — единый ERRATA-слой (дословно)

```yaml
# =============================================================
# ЕДИНЫЙ ERRATA-СЛОЙ (КОНСОЛИДИРОВАННЫЙ)
# Прикрепляется ОДИН раз в самый конец, ПОСЛЕ Б17-патча.
# Заменяет собой всю прежнюю цепочку из пяти отдельных слоёв:
#   ERRATA(v3.10) + ADDENDUM(v3.10.1) + DISPOSITION(v3.10.2)
#   + ADDENDUM-2(v3.10.3) + ADDENDUM-3(v3.10.4).
# Природа: НЕ новая архитектура. Разрешение конфликтов, доборы,
#          зачистка швов, судьба Документов А/Б. Ноль новых сущностей
#          сверх обоснованных инвариантов/метрик/текстов/CI.
# ПРАВИЛО СТАРШИНСТВА: при расхождении этот слой ПОБЕЖДАЕТ тело/патчи.
#          Внутри слоя порядок разделов = хронология принятия,
#          но все решения действуют одновременно и непротиворечиво.
# Версия документа: consolidated-v3.9-b17 → v3.10.4-errata-unified
# =============================================================

errata_unified:

  meta:
    parent: consolidated-v3.9-b17
    new_version: consolidated-v3.10.4-errata-unified
    supersedes_prior_errata_layers:
      - errata_layer (v3.10)
      - errata_addendum (v3.10.1)
      - debts_closure_disposition (v3.10.2)
      - errata_addendum_2 (v3.10.3)
      - errata_addendum_3 (v3.10.4)
    consolidation_note: >
      Пять ранее раздельных errata-слоёв сведены в один документ БЕЗ ПОТЕРЬ.
      Каждое решение (E1-E4), добор (A1-A3, ADD1-ADD5), fix (FIX1-FIX2),
      заметка (NOTE1-NOTE2), отклонение и disposition сохранены дословно
      по смыслу. Устранены только повторные преамбулы и перекрёстные
      ссылки «см. слой выше».
    precedence: highest_over_body_and_patches
    nature: conflict_resolution + adopted_addons + seam_cleanup + AB_disposition
    normative_stack_final:
      [корпус_v3, И1, И2, И3, И4, Б17, ERRATA_UNIFIED(this)]
    rule_of_precedence: >
      Источник истины по спорным местам — тело + этот единый ERRATA.
      Любой внешний артефакт закрытия долгов (Документы А/Б) ниже приоритетом.
    does_not_touch:
      - "корпус v3 (блоки 1-16) — не переписывается"
      - "Б17 command_registry / роли / три паузы — не трогаются"
    net_new_entities: 0
    architecture_changes: 0
    ready_for_synthetic_launch: yes

  # ===========================================================
  # РАЗДЕЛ 1. РАЗРЕШЕНИЕ ВНУТРЕННИХ САМОПРАВОК И КОНФЛИКТОВ (E1-E4)
  # (из ERRATA v3.10, часть 1)
  # ===========================================================

  resolutions:

    E1_participant_state_storage:
      conflict: >
        И2 сначала объявил participant_state как materialized_view,
        затем в audit_additions_i2 переопределил в regular_table_populated_by_projector.
        Первый (v3.5) пытался откатить обратно к 'read-only проекции' без уточнения.
      final_decision: regular_table_populated_by_projector
      reason: >
        REFRESH MATERIALIZED VIEW берёт блокировку и останавливает читателей —
        неприемлемо для горячего пути. Regular-таблица + INSERT..ON CONFLICT
        от роли projector даёт MVCC-consistent чтение без блокировок.
      enforcement:
        write_role: participant_state_projector   # SELECT + INSERT/UPDATE только тут
        read_role: participant_state_reader        # SELECT only
        projector_lives_in: Б10
        ci_check: no_UPDATE_participant_state_outside_projector   # уже в И2
      supersedes: [И2.participant_state_contract.storage.projection.kind=materialized_view]
      keeps_invariant: "И-1 (single source of state) в силе"

    E2_csp_default_src:
      conflict: >
        И4 mini_app_client.csp_header задал default_src: 'none'.
        Корпус Б14 (v3.3/v3.4) и Первый требуют default-src 'self' + явные исключения.
      final_decision: default_src_self_with_explicit_allowlist
      csp_final:
        default-src: "'self'"
        script-src: "'self' https://telegram.org"      # официальный telegram-web-app.js (Б14 R372)
        img-src: "'self' https://{s3-domain-ru} data: blob:"   # галереи фото
        connect-src: "'self' https://{s3-domain-ru}"   # API + pre-signed S3 РФ
        style-src: "'self' 'unsafe-inline'"
        frame-ancestors: "https://web.telegram.org https://telegram.org"
        forbidden: [unsafe-eval]
        report-uri: /security/csp-report
      reason: >
        default-src 'none' ломает загрузку telegram-web-app.js, blob-галереи фото
        (R343/R368) и fetch к pre-signed S3. 'self'+allowlist — рабочий минимум,
        совпадает с Б14 v3.4. 'none' в этом стеке нерабочий, не «строже».
      supersedes: [И4.mini_app_client.csp_header.default_src='none']
      keeps: [INV-B14-CSP-STRICT (no unsafe-eval, frame-ancestors только Telegram)]
      placeholder_note: "унификация домена {s3-domain}/{s3-domain-ru} — см. Раздел 6 placeholder_gate"

    E3_hard_confirm_kept:
      conflict: >
        Первый (v3.5) отзывал фразовый hard_confirm целиком.
        Но к нему привязаны закрытия RISK-L-07 (paste-block) и RISK-L-17 (A11y voice-path).
      final_decision: keep_hard_confirm_phrase_input   # НЕ отзываем
      reason: >
        Отзыв фразового ввода оставляет RISK-L-07 и RISK-L-17 без митигации.
        Двухшаг (канон Приложения B) и фразовый ввод — не конкуренты, а слои:
        двухшаг = защита от инерционного тапа; фраза = защита от clipboard-автоматизации
        необратимых операций (whitelist_change, erasure_before_cooling_off,
        unfreeze_piracy, refund_rollback).
      layering:
        reversible_ops: two_step_only            # 1 тап + подтверждение
        irreversible_destructive_ops: two_step + phrase_input
        phrase_registry: hard_confirm_phrases (И2/И3, все фразы уникальны)
        paste_blocked: true                       # RISK-L-07 CLOSED
        a11y_alt_path: voice_confirmation_with_audit   # RISK-L-17, sprint-1
      rejects: [v3.5.retractions_from_prior_patches.hard_confirm_pattern_retracted]

    E4_risk_registry_full_kept:
      conflict: >
        Первый (v3.5) сохранял только RISK-L-01..05; RISK-L-06..22 молча выпадали.
      final_decision: keep_all_risks_RISK-L-01_to_22
      reason: >
        Среди выпадавших есть severity=high (RISK-L-14: Red Flags ночью) и
        безопасность-критичные (RISK-L-06: потеря ключей owner). Терять нельзя.
      source_of_truth: "Второй.risk_registry_full (RISK-L-01..19) + Б17.risk_registry_b17_additions (20..22)"
      total: 22
      note: "RISK-L-07, 11, 14, 18 остаются CLOSED именно через механики Второго (не отзывать — см. E3)"
      canonical_ref: "точный счётчик и снятие рассинхрона с И4 — см. Раздел 5 NOTE1"

  # ===========================================================
  # РАЗДЕЛ 2. ДОБОР ПОЛЕЗНЫХ ПУНКТОВ ИЗ ПЕРВОГО v3.5 (A1-A3)
  # (из ERRATA v3.10, часть 2)
  # ===========================================================

  adopted_from_v3_5:

    A1_dedup_self_check:            # из X-DEBT-10
      block: B15
      what: "синтетическая почасовая проба идемпотентности консьюмеров"
      probe:
        name: dedup_self_check
        frequency: hourly
        action: "inject duplicate event → assert consumer processes exactly once"
        on_fail: alert both owners (admin_topic)
      metric: dedup_self_check_ok   # alert_on_false: true
      rationale: >
        У Второго есть outbox-метрики (lag/dlq/latency), но нет активной пробы,
        что дедуп реально работает. Проба ловит регресс до удара по участнику.
      complements: [И2.outbox_contract.metrics, И2.audit_additions_i2.consumer_idempotency_rule]

    A2_annual_calendar:             # из X-DEBT-13
      block: Parking_OPS
      what: "durable-артефакт ежегодных обязательств"
      artifact: reg_archive/annual/calendar.md
      mandatory_events:
        - {name: rkn_notification_refresh, anchor: "date_of_initial_rkn_notification (Д-40)"}
        - {name: threat_model_review, anchor: "date_of_initial_threat_model_uz3 (Д-31)"}
        - {name: incident_playbook_drill, anchor: "date_of_initial_incident_playbook (Д-36)"}
        - {name: provider_registry_sync, anchor: "date_of_provider_dpa (Д-30)"}   # R354 ежегодная сверка
      owner: operator (owner-role)
      priority: desirable_before_launch_not_blocking
      rationale: >
        Во Втором Д-37 только 'упомянут в parking'. Без явного календаря ежегодные
        юр-обязанности (РКН, threat-model, incident-drill) молча протухают.

    A3_psp_erasure_disclosure:      # уточнение X-DEBT-16 поверх Второго sh21
      block: B15/Legal
      what: "явная правовая формулировка в уведомлении PSP при erasure"
      strengthens: [И3.export_worker.sh21_third_party_notification]
      contract:
        psp_notified_not_obligated: true
        participant_disclosure_text: >
          "Передача платёжных данных провайдеру регулируется его собственным
           сроком хранения (115-ФЗ, до 5 лет). Удаление у провайдера не гарантируется."
        legal_basis: "GDPR Art.19 (нерезиденты); 152-ФЗ ст.20 (резиденты)"
        surfaces_in: [dsar_response, "legal_data_command (⚖️ Юр.данные)"]
      rationale: >
        sh21 Второго говорит 'уведомить PSP', но не даёт участнику честную
        формулировку про PSP-retention. Это всплывёт на DSAR/юр-ревью.
      legal_status: pre-legal-review

  # ===========================================================
  # РАЗДЕЛ 3. МИКРО-ДОБОРЫ И ЗАЧИСТКА ШВОВ (ADD1-ADD5)
  # (из ADDENDUM v3.10.1: ADD1-ADD2; из ADDENDUM-2 v3.10.3: ADD3-ADD5)
  # ===========================================================

  seam_additions:

    # --- ADD1 (из ADDENDUM v3.10.1) ---
    ADD1_outbox_compaction_sent_at_invariant:
      strengthens:
        - Б15.retention.rule            # dispatched_at IS NULL guard
        - "Б15.ci_check assert compaction never removes undispatched events"
        - И2.outbox_contract.retention  # never_touch dispatched_at IS NULL
        - И2.ci_checks_i2.outbox_compaction_never_removes_undispatched
      invariant:
        name: INV-OUTBOX-SENT-AT-COMPACTION
        rule: >
          Компакция/удаление строки outbox допустимы ТОЛЬКО когда
          sent_at IS NOT NULL AND all_required_consumers_acked.
          Строка с sent_at IS NULL (эквивалент dispatched_at IS NULL) —
          НИКОГДА не удаляется, независимо от возраста и от consumer_offsets.
        rationale: >
          Формулировки тела (dispatched_at IS NULL / consumer_offsets missing)
          семантически верны, но разнесены по двум патчам и выражены
          по-разному. Единый именованный инвариант закрывает регресс
          "неотправленная строка удалена по возрасту" одной CI-проверкой.
        note_field_alias: "sent_at == dispatched_at (одно и то же поле в разных патчах; при расхождении имён — это одно поле outbox)"
      ci_check:
        name: no_compaction_of_unsent_outbox_rows
        kind: unit_test
        scenario: >
          Вставить строку с sent_at IS NULL и created_at старше retention-окна;
          прогнать компактор; assert строка на месте.
        on_fail: block release
      covers: [R221, "И2 outbox compaction hardening"]
      not_a_new_entity: true

    # --- ADD2 (из ADDENDUM v3.10.1) ---
    ADD2_broadcast_health_metrics:
      extends: И2.outbox_contract.metrics
      already_present_do_not_duplicate:
        - outbox_lag_seconds        # И2
        - notification_dlq_rate     # И2
        - delivery_latency_p95      # И2
        - dedup_self_check_ok       # errata A1 (Раздел 2)
      new_metrics:
        broadcast_queue_depth:
          formula: "count(outbox rows WHERE sent_at IS NULL)"
          alert_threshold: {warn: 1000, critical: 10000}
        tg_403_rate:
          formula: "count(tg_send WHERE http_status=403) / count(tg_send) over 5min"
          semantics: "бот заблокирован участником / чат недоступен"
          alert_threshold: {warn: 0.02, critical: 0.10}
          note: "403 → non-transient, маршрут в DLQ (И2 dlq routing), не retry"
        tg_429_rate:
          formula: "count(tg_send WHERE http_status=429) / count(tg_send) over 5min"
          semantics: "flood-control; ожидание retry_after — НЕ провал"
          alert_threshold: {warn: 0.05, critical: 0.20}
          note: "429 не расходует retry-квоту (И2)"
        outbox_row_age_p95:
          formula: "p95(now() - created_at WHERE sent_at IS NULL)"
          alert_threshold: {warn: 60s, critical: 300s}
          note: "дополняет outbox_lag_seconds: тот про min, этот про p95-хвост"
        duplicate_delivery_detected_rate:
          formula: "count(consumer dedup hits) / count(dispatched) over 5min"
          semantics: "at-least-once сработал; растущий тренд = проблема консьюмера"
          alert_threshold: {warn: 0.01, critical: 0.05}
      surfaces_in:
        - Б15 monitoring panel
        - Б17 broadcast_inspector.outbox_lag_by_consumer   # уже существует, дополняется
        - Б17 owner_dashboard.outbox_health                 # уже существует, дополняется
      alert_channel: admin_topic   # канон Б8
      covers: [Р130]
      not_a_new_entity: true

    # --- ADD3 (из ADDENDUM-2 v3.10.3) ---
    ADD3_age_gate_before_pid_creation:
      provenance: "Документ Б X-DEBT-14 — взято ПРАВИЛЬНОЕ направление, не ошибочная формулировка Б"
      corrects_document_B: >
        Формулировка X-DEBT-14 ('автосоздание через Mini App запрещено, только bot')
        ОТКЛОНЕНА как противоречащая И1 (autocreate_source: mini_app_only).
        Берётся только указанный ею шов, в правильную сторону.
      strengthens: [И1.tg_user_id_pid_registry, "Д-05 age_gate", И4.D_14_first_launch_consent_UI]
      contract:
        rule: >
          Создание pid при первом запуске Mini App происходит ТОЛЬКО ПОСЛЕ
          прохождения возрастного гейта Д-05 внутри Mini App first-launch формы:
          soft-checkbox 18+ И hard-check по дате рождения (today - ДР >= 18y,
          дата через tz_at(pid_candidate) на локальную дату).
        ordering: [age_soft_checkbox, age_hard_check_dob, legal_consents, pid_creation]
        pid_not_created_until: age_hard_check passed
        on_underage: ["no_pid_created", "Д-05 leak_protocol NOT triggered (pid ещё нет)", "show gentle_block"]
        autocreate_source: mini_app_only   # подтверждается, НЕ откатывается к bot
      invariant:
        name: INV-AGE-GATE-BEFORE-PID
        rule: "ни одна строка tg_user_registry с реальным pid не создаётся до прохождения hard-check возраста в Mini App"
      ci_check:
        name: no_pid_before_age_hardcheck
        kind: unit_test
        scenario: "first-launch с ДР < 18 → assert pid не создан, tg_user_registry пуст для этого tg_user_id"
      implementation_caveat: >
        Если pid технически необходим для сессии Mini App до проверки возраста,
        инвариант ослабляется до: pid создан, но помечен pending_age_verification,
        не несёт ПДн и не активируется до прохождения hard-check. Вопрос имплементации Б1/Б14.
      rationale: >
        Шов между 'создание участника только через Mini App' (И1) и
        'возрастной гейт' (Д-05) не был связан явным порядком. Без этого
        возможно создание pid до проверки возраста → протечка гейта с уже
        существующим профилем несовершеннолетнего.

    # --- ADD4 (из ADDENDUM-2 v3.10.3) ---
    ADD4_rollback_error_text_names_manual_path:
      provenance: "Документ Б X-DEBT-15 — добор текста ошибки для owner про manual path"
      strengthens: [Б17.commands_catalog./revert, И4.graph_and_moderation.P437_rollback_applied_stage]
      contract:
        target: text_catalog_b9
        add_text_id:
          id: B7.stage_pass_rollback_not_supported_owner
          audience: owner
          must_state:
            - "откат уже применённого прохода Дня не поддерживается"
            - "ручной путь компенсации: эмитировать компенсирующий stage_completed ИЛИ /revert предыдущего Дня"
          tone: dry_factual
          legal_status: approved
        distinct_from:
          participant_plate: "И4 revert_ui hidden_with_plate 'День уже перевыдан' — это участнику, НЕ owner"
      rationale: >
        Тело даёт правило 'rollback not_supported' и участническую плашку,
        но НЕ даёт owner-у текст, называющий конкретный ручной путь.
        Без этого owner упирается в отказ без инструкции.
      not_a_new_entity: true   # только text_id в существующем text_catalog Б9

    # --- ADD5 (из ADDENDUM-2 v3.10.3, уточнён NOTE2 из ADDENDUM-3) ---
    ADD5_backup_rotation_number_boot_gate:
      provenance: "Документ А, 5-й уровень, A4 — boot-gate-зависимость числа ротации бэкапов"
      strengthens: [Legal.retention.erasure_blacklist, A4.erasure_blacklist.retention, "A4.stub_tails Legal S4"]
      contract:
        unresolved_value: full_backup_rotation_cycle   # число в теле = плейсхолдер
        dependency: >
          erasure_blacklist.retention зависит от полного цикла ротации бэкапов+WAL.
          Пока full_backup_rotation_cycle не подставлено реальным числом
          (владелец: Б15/Infra durability), retention blacklist неопределён.
        two_formulas_in_body:
          legal_v1: "max(90d, full_backup_rotation_cycle)"
          a4_b15:   ">= max(retention всех бэкапов + WAL)"
        stricter_bound_rule: >
          При подстановке реального числа брать БОЛЕЕ СТРОГУЮ границу (A4,
          с учётом WAL), т.к. restore-reapply зависит от полного цикла
          бэкапов+WAL, а не только календарного числа. Legal-формула —
          нижний порог; A4 — фактический порог для корректности erasure.
        boot_gate_rule: >
          Прод-launch БЛОКИРУЕТСЯ, пока full_backup_rotation_cycle не задано
          конкретным числом И retention erasure_blacklist не пересчитан.
          Иначе restore-reapply (INV-A4-REAPPLY-BEFORE-SERVE) может недоочистить
          стёртых субъектов из воскрешённого бэкапа.
        owner_of_number: "Б15/Infra (durability rotation policy)"
        legal_note: >
          Legal-STUB A4 (S4) остаётся: правовая достаточность срока — на юриста;
          но САМО ЧИСЛО ротации — техническое, владелец Б15/Infra, и оно
          блокирует boot-gate независимо от Legal-вычитки.
      ci_check:
        name: no_placeholder_in_blacklist_retention_at_launch
        kind: config_validation
        scenario: "erasure_blacklist.retention содержит незамещённый full_backup_rotation_cycle → block prod launch"
        note: "проверка работает при любой из двух формул"
      rationale: >
        Тело фиксирует ЗАВИСИМОСТЬ retention от цикла ротации, но не поднимает
        незаданное число до явного boot-gate-блокера. Документ А (5-й уровень)
        назвал этот хвост прямо; связываем его с boot-gate.
      adds_to_boot_gate: true

# ===========================================================
  # РАЗДЕЛ 4. ФИНАЛЬНАЯ ЗАЧИСТКА ШВОВ (FIX1-FIX2)
  # (из ADDENDUM-3 v3.10.4)
  # ===========================================================

  final_fixes:

    FIX1_publish_epoch_owner:
      conflict: >
        И1.glossary_patch.new_entities_v3_5.publish_epoch.owner_block = B10
        ПРОТИВОРЕЧИТ Б14 ('единственный владелец publish_epoch'),
        Б10-Ш7 (publish_epoch_owner: block14, Б10 = подписчик) и
        И2.contracts_in.publish_epoch_owner: block14.
      final_decision: owner_block = B14
      reason: >
        Три источника (Б14-дельта, Б10-Ш7, И2) против одной строки И1.
        Б14 монотонно инкрементит epoch per stage_id и пишет в outbox
        в одной транзакции с stage_publish_log; Б10 — потребитель,
        снимающий content_frontier и эмитящий уведомление. Владение
        сущностью принадлежит эмитенту (Б14), не потребителю (Б10).
      supersedes: [И1.glossary_patch.new_entities_v3_5.publish_epoch.owner_block]
      b10_role: consumer_only   # подписывается на publish_stage, дедуп по (stage_id, publish_epoch)
      ci_check:
        name: publish_epoch_single_owner_b14
        kind: static_analysis
        scenario: "инкремент publish_epoch разрешён только в коде Б14; попытка из Б10 → block release"
      not_a_new_entity: true

    FIX2_traceability_appendix_status:
      problem: >
        DISPOSITION.salvaged_as_reference_only ссылается на traceability
        Документа Б как non-normative appendix, но Документ Б физически
        НЕ вклеен в архитектуру (и не должен быть — он несовместим).
        Ссылка повисла: содержимого приложения в документе нет.
      resolution:
        appendix_status: external_optional
        rule: >
          debts_traceability_appendix — ВНЕШНИЙ необязательный справочник,
          НЕ часть архитектурного документа. Если нужен для навигации —
          хранится отдельным файлом в reg_archive/nav/, помечен reference-only.
          Отсутствие приложения в теле НЕ является дырой: вся трассировка
          'долг → маркер' восстановима из тела + errata напрямую.
        binding: "при расхождении приложения с телом — побеждает тело"
      net_effect: "висячая ссылка снята; приложение переведено в статус внешнего опционального"

  # ===========================================================
  # РАЗДЕЛ 5. КАНОНИЗАЦИИ-ЗАМЕТКИ (NOTE1-NOTE2)
  # (из ADDENDUM-3 v3.10.4)
  # ===========================================================

  canonical_notes:

    NOTE1_risk_registry_canonical:
      historical_snapshots:
        i4_totals: 19        # RISK-L-01..19 на момент И4 (НЕ переписываем — снимок)
      canonical_current: 22  # RISK-L-01..22 (после Б17), источник истины = этот ERRATA (E4)
      rule: "при любой ссылке на 'общее число рисков' использовать 22; 19 в И4 — исторический снимок"

    NOTE2_blacklist_retention_stricter_bound:
      clarifies: seam_additions.ADD5_backup_rotation_number_boot_gate
      two_formulas_in_body:
        legal_v1: "max(90d, full_backup_rotation_cycle)"
        a4_b15:   ">= max(retention всех бэкапов + WAL)"
      rule: >
        При подстановке реального числа брать БОЛЕЕ СТРОГУЮ границу (A4,
        с учётом WAL). Legal-формула — нижний порог; A4 — фактический
        порог для корректности erasure. (Дублирует stricter_bound_rule
        внутри ADD5 — сохранено для явности.)
      boot_gate_check_unchanged: true

  # ===========================================================
  # РАЗДЕЛ 6. ПЛЕЙСХОЛДЕР-ШЛЮЗ
  # (из ADDENDUM v3.10.1)
  # ===========================================================

  placeholder_gate:
    unresolved_in_body:
      - "{s3-domain} (Б14 CSP)"
      - "{s3-domain-ru} (И4 CSP)"
    rule: "оба — один и тот же РФ-домен S3-провайдера; унифицировать в единый {s3-domain-ru} и подставить реальное значение на boot-gate"
    ci_check: "CSP не проходит валидацию, если содержит незаменённый плейсхолдер {s3-domain*}"
    owner: boot_gate
    note: "не архитектурное решение; подстановка при выборе провайдера (парковка Инфра Д-29..32)"

  # ===========================================================
  # РАЗДЕЛ 7. СУДЬБА ДОКУМЕНТОВ А и Б (DISPOSITION)
  # (из DISPOSITION v3.10.2)
  # ===========================================================

  documents_A_B_disposition:

    document_B_closure_of_debts:
      status: REJECTED_as_normative
      reasons:
        - "meta.supersedes_prior_patches сносит И1..И4+Б17, которые решено сохранить"
        - "retractions.participant_state_as_regular_table_retracted конфликтует с E1 (regular_table — обоснованное решение; view с REFRESH MV блокирует читателей). Регресс."
        - "retractions.hard_confirm_pattern_retracted конфликтует с E3; вскрывает RISK-L-07 и RISK-L-17. Регресс безопасности."
        - "addons X-DEBT-01..17: инженерная сверка — 0 реально новых пунктов; 09/10 уже в seam_additions ADD1/ADD2; 14 фактически неверен; прочие — дубли тела."
      factual_error_flagged:
        X-DEBT-14: >
          Документ Б утверждает 'автосоздание участника через Mini App ЗАПРЕЩЕНО,
          только bot-онбординг'. Тело (И1 tg_user_id_pid_registry) фиксирует
          autocreate_source: mini_app_only (из-за возрастного гейта Д-05).
          Прав — И1. Формулировку Документа Б не принимать.
          (Правильный шов взят в ADD3.)

    document_A_text:
      status: REJECTED_as_normative
      reason: "3-й уровень = retractions Документа Б (те же конфликты с E1/E3)."

    salvaged_as_reference_only:
      artifact: debts_traceability_appendix
      source: "Документ Б, раздел traceability (+ 1-й уровень Документа А)"
      status: NON_NORMATIVE_APPENDIX_EXTERNAL   # уточнено FIX2: внешний опциональный
      role: "справочная карта 'долг → канонический маркер в теле'; предотвращает переоткрытие закрытого"
      binding_rule: >
        reference-only. При ЛЮБОМ расхождении с телом/ERRATA побеждает
        тело/ERRATA. Приложение не может служить основанием для изменения
        архитектуры. Физически хранится вне архитектурного документа
        (reg_archive/nav/), см. FIX2.
      known_inaccuracies_in_appendix:
        - "X-DEBT-14 mapping неверен (см. factual_error_flagged) — не использовать как подтверждение"
        - "X-DEBT-03/08/15/16/17 помечены как addons, но фактически уже закрыты телом/ERRATA — считать закрытыми"

  # ===========================================================
  # РАЗДЕЛ 8. ЯВНО ОТКЛОНЁННОЕ (чтобы не всплыло повторно)
  # (объединяет rejected_from_v3_5 из ERRATA + rejected_from_document_A из ADDENDUM)
  # ===========================================================

  rejected_explicitly:

    from_v3_5_first:
      - {item: hard_confirm_pattern_retracted, why: "ломает RISK-L-07/17 — см. E3"}
      - {item: text_registry_new_entity_retracted, why: "text_registry Второго уже согласован с text_catalog Б9 через namespacing; отзыв не нужен"}
      - {item: command_registry_new_entity_retracted, why: "command_registry Б17 не изобретает capability (invariant_B17); полезен как единый UX-слой"}
      - {item: csp_default_src_none_retracted, why: "Первый прав ПО НАПРАВЛЕНИЮ (нужен 'self'), но само значение задано в E2; отдельный retract не нужен"}
      - {item: own_invariants_I_1_to_I_6_retracted, why: "И-1..И-6 дают enforcement (CI-checks); дублирование с INV-* безвредно, отзыв убрал бы проверки"}
      - {item: participant_state_as_regular_table_retracted, why: "regular_table — ПРАВИЛЬНОЕ решение (E1), Первый ошибался"}

    from_document_A:
      - item: "3-й уровень: participant_state как view Б10 (откат regular_table)"
        why: "прямой конфликт с E1. Регресс."
      - item: "3-й уровень: отмена hard_confirm_phrase_input, использовать только двухшаг"
        why: "конфликт с E3. Вскрывает RISK-L-07 (paste-block) и RISK-L-17 (A11y). Регресс безопасности."
      - item: "2-й уровень: enum checkup_zones / repeat_policy / completion_kind как доклейка"
        why: "уже в теле: repeat_policy_enum и completion_kind_enum дословно в И3; зоны в checkup.zones (Б5/И3). Дубль."
      - item: "2-й уровень: review_button в red_zone_template"
        why: "уже в теле: И3 red_zone_templates.appeal_button с меткой red_zone_review. Дубль."
      - item: "2-й уровень: sync-баннер R365"
        why: "уже в теле: И4 mini_app_client.R365_sync_banner. Дубль."
      - item: "2-й уровень: Д-14 write-before-render"
        why: "уже в теле: И2 d14_write_before_render + И4 D_14_first_launch_consent_UI. Дубль."
      - item: "2-й уровень: календарь Д-37"
        why: "принесён A2 annual_calendar (Раздел 2). Дубль."
      - item: "A1/A3 Документа А (dedup_self_check, psp_erasure_disclosure)"
        why: "принесены A1/A3 (Раздел 2). Дубль."
      - item: "3-й уровень: отмель text_registry / command_registry / И-1..И-6 / refund saga"
        why: "уже разрешено в rejected_from_v3_first; повторная отмена избыточна и рискует рассинхроном."

  # ===========================================================
  # РАЗДЕЛ 9. НЕЗАКРЫТОЕ ЗАВИСИМОСТЬЮ ОТ ВНЕШНЕГО ФАЙЛА
  # (из ADDENDUM v3.10.1)
  # ===========================================================

  blocked_pending_document_B:
    - "X-DEBT-01..17 (4-й/5-й уровни Документа А) ссылались на Документ Б (YAML), которого нет в поставке. Документ Б отклонён нормативно (Раздел 7). Реально ценные швы из него уже вычерпаны в ADD3/ADD4/ADD5. Дальнейших зависимостей от Документа Б нет."

  # ===========================================================
  # РАЗДЕЛ 10. ПОДТВЕРЖДЕНИЕ ПОЛНОТЫ ВЫЧЕРПЫВАНИЯ ДОКУМЕНТОВ А/Б
  # (из ADDENDUM-2 v3.10.3)
  # ===========================================================

  exhaustiveness_check:
    method: "построчная сверка X-DEBT-01..17 + все 5 уровней Документа А против тело + этот ERRATA"
    taken_into_errata:
      A1_dedup_self_check: [X-DEBT-10 частично]
      A2_annual_calendar: [X-DEBT-13]
      A3_psp_erasure_disclosure: [X-DEBT-16]
      ADD1_outbox_sent_at: [X-DEBT-09]
      ADD2_broadcast_metrics: [X-DEBT-10]
      ADD3_age_gate: [X-DEBT-14 правильное направление]
      ADD4_rollback_owner_text: [X-DEBT-15]
      ADD5_rotation_boot_gate: ["Документ А 5-й уровень A4 rotation number"]
    confirmed_true_duplicates_not_taken:
      - X-DEBT-01: "repeat_policy_enum/checkup zones — И3/Б5"
      - X-DEBT-02: "completion_kind_enum — И3"
      - X-DEBT-03: "appeal_button tag=red_zone_review — И3"
      - X-DEBT-04: "R253 reminders soft/neutral/final — И4 texts_B9"
      - X-DEBT-05: "R283 export texts — И4 texts_B9"
      - X-DEBT-06: "R381 threshold text — И4"
      - X-DEBT-07: "R361 recalc text — И4 T2-RECALC-INDICATOR"
      - X-DEBT-08: "T3_sent_within_24h owner=Б9 — И4 T3_boolean_gates"
      - X-DEBT-11: "R365 sync_banner — И4"
      - X-DEBT-12: "Д-14 write-before-render + mini_app_first_consent event — И1+И2+И4"
      - X-DEBT-17: "red_flags_emergency_text — И3/И4 legal-gate"
    result: "из Документов А/Б вычерпано полностью; остаток — только дубли уже закрытого"

  # ===========================================================
  # РАЗДЕЛ 11. СВОДНЫЙ ФИНАЛЬНЫЙ СТАТУС
  # ===========================================================

  final_state:
    doc_version: consolidated-v3.10.4-errata-unified
    normative_stack_final:
      [корпус_v3, И1, И2, И3, И4, Б17, ERRATA_UNIFIED(this)]

    conflicts_resolved: [E1, E2, E3, E4, FIX1_publish_epoch, FIX2_traceability_dangling_ref]
    adopted_from_first: [A1, A2, A3]
    seam_additions: [ADD1, ADD2, ADD3, ADD4, ADD5]
    canonized: [NOTE1_risk_registry_total=22, NOTE2_blacklist_retention_stricter_bound]

    net_new_entities: 0
    architecture_changes: 0

    new_invariants:
      - INV-OUTBOX-SENT-AT-COMPACTION      # ADD1
      - INV-AGE-GATE-BEFORE-PID            # ADD3
    new_ci_checks:
      - no_compaction_of_unsent_outbox_rows           # ADD1
      - no_pid_before_age_hardcheck                   # ADD3
      - no_placeholder_in_blacklist_retention_at_launch  # ADD5
      - publish_epoch_single_owner_b14                # FIX1
      - "CSP placeholder validation (Раздел 6)"       # placeholder_gate
    new_text_ids:
      - B7.stage_pass_rollback_not_supported_owner    # ADD4
    new_metrics:
      - broadcast_queue_depth, tg_403_rate, tg_429_rate, outbox_row_age_p95, duplicate_delivery_detected_rate  # ADD2
      - dedup_self_check_ok                            # A1
    boot_gate_additions:
      - "full_backup_rotation_cycle must be resolved (ADD5)"
      - "CSP {s3-domain*} placeholder must be resolved (Раздел 6)"

    risk_registry_total: 22
    documents_A_B_disposition: "A/B отклонены нормативно; ценное вычерпано; traceability — внешний reference"

    blocking_prod_launch:
      - legal_review всех pre-legal-review текстов
      - "red_flags_emergency_text (Д-11) Legal-approved"
      - "F2 erasure_finalized_notification Legal-approved"
      - "A3 psp_erasure_disclosure Legal-approved"
      - "Д-40 РКН, Д-30 DPA, Д-31 threat-model UZ-3"
      - "full_backup_rotation_cycle задано числом + retention blacklist пересчитан (ADD5)"
      - "CSP-плейсхолдер {s3-domain-ru} подставлен реальным доменом (Раздел 6)"

    ready_for_synthetic_launch: yes
```
