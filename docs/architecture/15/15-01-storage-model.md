---
file: 15/15-01-storage-model.md
block: 15
title: "Шаг 1 — Модель хранения контента"
status: закрыт
doc_version: "consolidated v3"
contains: [Шаг 1, два уровня хранения, реестр выданных сообщений, soft-delete, границы рефанда, yaml step_1]
---

# БЛОК 15 · ШАГ 1 — МОДЕЛЬ ХРАНЕНИЯ КОНТЕНТА

Контент хранится двухуровнево. Логический уровень — «день», определяемый тройкой participant_id + module + day; это смысловая единица прохождения, уровень прогресса и «Пройденного». Физический уровень — конкретные сообщения (message_id) в личном чате; это уровень удаления, лимитов и детекции. Уровни нужно явно связать, а не смешивать: удаление/лимиты/детекция работают по message_id, прогресс — по дню.

Реестр выданных сообщений — одна общая таблица с полями type (контент/служебное) и status (активно/удалено) плюс дата отправки. Единая таблица вместо двух убирает риск рассинхрона: «реестр контента» и «реестр служебных» получаются простой выборкой по type. Удаление всегда soft-delete: строка не стирается физически, а помечается флагом — это даёт идемпотентность и возобновляемость при сбоях, и правило распространяется на все аналогичные операции.

При рефанде бот удаляет только собственные сообщения (type=content). Сообщения участника не удаляются никогда, независимо от возраста; отказ от удаления чужого полностью снимает зависимость от платформенного лимита ~48 ч на удаление чужих сообщений — этой развилки больше не существует. Внутренние логи, реестры, замеры, рефлексии и финансовые записи рефанд не затрагивает: рефанд чистит ленту, но не защищённую память. Reflection_note (приглашение к рефлексии от бота) регистрируется как контент и удаляется при рефанде; ответ участника (сама рефлексия) хранится в неизменяемом логе и не удаляется — это его собственные слова. После чистки ленты бот отправляет одно мягкое завершающее уведомление (механика — Б15, текст делегирован в блок коммуникации). Открытых вопросов нет.

## YAML — Шаг 1

```yaml
block_15:

  # ================================================================
  step_1:
    title: "Модель хранения контента"
    status: closed
    decisions:
      content_levels:
        logical: {unit: day, key: [participant_id, module, day], meaning: "прогресс/'Пройденное'"}
        physical: {unit: message, identifier: message_id, scope: "личный чат", meaning: "удаление/лимиты/детекция"}
        reason_two_levels: "удаление/лимиты — по message_id; прогресс — по дню; связать явно"
      delivery_registry:
        strategy: single_table
        reason: "выборки по type; исключает рассинхрон двух таблиц"
        fields: [participant_id, module, day, message_id, type, sent_at, status]
        type_values: [content, service]
        status_values: [active, deleted]
      deletion_policy: {mechanism: soft_delete, reason: [idempotency, resumability], applies_to: all_similar_operations}
      refund_scope:
        deletes: ["только сообщения бота (type=content)"]
        never_deletes: [participant_messages_any_age, internal_logs, registries, measurements, reflections, financial_records]
        platform_48h_limit: not_applicable
        framing: "чистит ленту (отзыв доступа), не защищённую память"
      reflection_handling:
        reflection_note: {source: bot, type: content, deleted_on_refund: true}
        participant_reply: {source: participant, storage: immutable_log, deleted_on_refund: false}
      final_notification: {mechanism_owner: block_15, tone_intent: "мягко, уважительно, дверь открыта", wording_owner: communication_block}
    open_questions: []
```
