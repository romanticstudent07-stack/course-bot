---
file: 15/15-06-antipiracy.md
block: 15
title: "Шаг 6 — Анти-пиратство"
status: закрыт
doc_version: "consolidated v3"
contains: [Шаг 6, честная рамка, модель угроз, отвергнутые меры, три меры, стык с детекцией, yaml step_6]
---

# БЛОК 15 · ШАГ 6 — АНТИ-ПИРАТСТВО

Шаг защищает ценность бота — текст заданий. Медиа вне проекта, поэтому DRM/водяные знаки на видео/шифрование файлов неприменимы по конструкции. Фундаментальная честная рамка: защита текста негерметична по природе, и мы это прямо признаём. Съёмку экрана камерой и скриншот предотвратить невозможно в принципе (аналоговая дыра любой системы, включая enterprise-DRM). Шаг решает более узкую реальную задачу: затруднить и удорожить массовое дешёвое копирование средствами платформы и замедлить темп сбора, делая только то, что действительно работает, без имитации защиты.

Модель угроз: курс — конечный актив (нельзя опираться на «объём слишком велик»); главный вектор — сам платящий участник, копирующий и распространяющий контент. Нарушители по усилиям: случайный (переслал другу — режется), бытовой (скриншот/пересказ — недетектируемо), целевой (методичный сбор — замедляется лимитом), технически подкованный (недостижим — признаём честно).

Осознанно отвергнутые меры: текстовые метки любого вида. Невидимые Unicode-метки снимаются в клик и не переживают скриншот; видимые/канареечные ломают модель хранения Шага 1 (единый текст в конфиге), работают только против дословной утечки, бесполезны против пересказа, для десятков участников — усложнение без отдачи. Прямое следствие, зафиксированное без иллюзий: прослеживаемости источника утёкшего текста у системы нет — логи дают прослеживаемость темпа сбора, а не источника утечки.

Три меры (полный и окончательный набор). Первая — protect_content=True на всех выдачах текста: единственный рабочий флаг платформы, блокирует пересылку/сохранение/копирование средствами Telegram; НЕ блокирует скриншот (на iOS возможен), и Bot API не уведомляет о скриншоте (такой возможности в API нет). Вторая — лимит 3/24ч скользящим окном (владелец — Б13): три выдачи контента дня за последние 24 ч; навигация по дереву бесплатна; считаются выдачи, не уникальные дни; технические повторы не тратят (окно дедупликации Шага 4); двухслойная защита (UI-гашение кнопки + серверная проверка); единственная из трёх мер, бьющая по темпу выкачивания. Третья — логирование выдач (детали — Шаг 8) для анализа темпа сбора (не источника утечки), не сливается с аудит-логом 152-ФЗ.

Стык с детекцией: активный ответ (мягкая приостановка при паттерне систематического сбора + алерт) и согласование его порога с лимитом 3/24ч целиком переданы в Шаг 7.

## YAML — Шаг 6

```yaml
block_15:

  # ================================================================
  step_6:
    title: "Анти-пиратство"
    status: closed
    protected_value: task_text_only
    media_protection: not_applicable_by_design
    honest_frame:
      leak_proof: false
      undetectable_vectors: [screenshot, camera_photo, paraphrase]
      goal: raise_cost_and_slow_bulk_collection_not_absolute_prevention
      principle: only_what_actually_works_no_security_theater
    threat_model:
      course_is_finite_asset: true
      primary_vector: paying_user_copies_and_redistributes
      actors: [{casual: "forwarded_to_friend -> cut by protect_content"}, {everyday: "screenshot/paraphrase -> not preventable"}, {targeted: "methodical -> slowed by 3/24h"}, {technical: out_of_scope_honestly}]
    rejected_measures:
      invisible_unicode_watermark: {rejected: true, reason: removed_in_one_click_dies_on_screenshot}
      visible_or_canary_mark: {rejected: true, reason: breaks_step1_storage_only_verbatim_overkill_for_scale}
      consequence: {no_leak_source_attribution: true, logs_trace_pace_not_leaked_text: true}
    measures:
      protect_content: {flag: "protect_content=true", applies_to: all_task_text, blocks: [forwarding, saving_copying], does_not_block: screenshot, screenshot_notification: not_available_in_bot_api}
      rate_limit_3_24h: {owner_block: 13, window: sliding_last_24h, counts: content_day_delivery, free: tree_navigation, accounting: decrement_deliveries, dedup: technical_repeats_dont_consume, two_layers: {ui: button_disabled_on_tap, server: limit_check}, anti_piracy_role: caps_collection_pace}
      logging: {purpose: pace_analysis_not_leak_source, detail_deferred_to: step_8, must_not_merge_with: audit_log_152fz_block6}

    anomaly_detection_seam: {active_response: soft_suspension_plus_admin_alert, threshold_vs_limit: transferred_to_step_7}
```
