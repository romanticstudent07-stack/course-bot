---
file: 15/15-12-addendum-identifier-retention.md
block: 15
title: "Дополнение к Блоку 15 — Retention прямых идентификаторов (уточнение к Крючку 2 и Шагу 8)"
status: закрыт (архитектуру не меняет; число дней — за правовым блоком)
doc_version: "consolidated v3"
contains: [выжимка дополнения, второе место с chat_id, точка отсчёта срока identity_map, yaml block_15_addendum_direct_identifier_retention]
---

# ДОПОЛНЕНИЕ К БЛОКУ 15 — RETENTION ПРЯМЫХ ИДЕНТИФИКАТОРОВ (УТОЧНЕНИЕ К КРЮЧКУ 2 И ШАГУ 8)

## Выжимка

Это дополнение закрывает два вопроса, которые иначе всплыли бы на правовом ревью, и относятся они целиком к крючку 2 (не требуют пересмотра архитектуры).

Первое — второе место с прямым идентификатором. В Шаге 8 прямой идентификатор (chat_id) живёт не только в identity_map, но и в delivery_registry (там chat_id нужен механике «удаление = отзыв доступа» из Шага 3). Политика хранения была явно задана только для identity_map. Фиксируем: при эрейже delivery_registry обезличивается той же операцией — chat_id обнуляется/вычищается, а функционально нужные для истории поля (issuance_id, message_id, sent_at, status) остаются, поскольку они не идентифицируют личность. То есть эрейж рвёт личность в обоих местах сразу, а не только в identity_map. Это прямое следствие аксиомы 2 Шага 3 (удаляем только идентификатор, всё прочее обезличиваем и храним) и инварианта «erasure > identity».

Второе — от какого события считать короткий срок identity_map. «Короткий срок» нельзя отсчитывать от создания связки: chat_id нужен боту для доставки контента всё время активного прохождения курса (месяцы), иначе бот потеряет адрес живого участника. Фиксируем: срок хранения прямого идентификатора отсчитывается от завершения жизненного цикла участника (завершение/выбывание/рефанд последнего Этапа) или от эрейжа — что наступит раньше, — а не от момента создания записи. Пока участник активен, прямой идентификатор живёт по обоснованию «необходим для оказания услуги»; короткий ретеншен-таймер запускается только после того, как участник перестал быть активным. Конкретное число дней после этого события остаётся за правовым блоком (крючок 2).

Оба уточнения — доводка поверх готовой структуры: механика эрейжа и разграничение «идентификатор vs обезличенное» уже заложены, здесь лишь явно названы второе место с chat_id и точка отсчёта срока.

## YAML — дополнение

```yaml
# ================================================================
# ДОПОЛНЕНИЕ К БЛОКУ 15 — Retention прямых идентификаторов
# Уточнение к Шагу 8 и Крючку 2. Архитектуру не меняет.
# ================================================================
block_15_addendum_direct_identifier_retention:
  extends: [block_15.step_8, block_15.product_hooks_checklist.hook_2]
  status: closed

  direct_identifier_locations:
    note: "chat_id (прямой идентификатор) живёт РОВНО в двух местах"
    places:
      - identity_map:
          holds: [participant_id, chat_id]
          retention_lever: identity_map_retention   # SHORT — правовой блок
      - delivery_registry:
          holds_direct_identifier: chat_id
          reason: "нужен механике 'удаление = отзыв доступа' (Шаг 3)"
          previously_missing_policy: true            # раньше срок задан не был
          erasure_behavior: anonymize_in_same_operation   # chat_id вычищается/обнуляется
          kept_after_erasure: [issuance_id, message_id, sent_at, status]  # не идентифицируют личность
    invariant: "erasure рвёт личность в ОБОИХ местах сразу; аксиома_2 Шага 3; erasure > identity"

  identity_map_retention_anchor:
    problem: "короткий срок нельзя считать от создания: chat_id нужен всё время активного прохождения (месяцы)"
    rule: "отсчёт срока = от завершения жизненного цикла участника ИЛИ от эрейжа, что раньше"
    lifecycle_end_events: [course_completed, dropped_out, refund_of_last_stage]
    while_active:
      basis: "необходимо для оказания услуги (доставка контента)"
      timer: not_started
    after_inactive:
      basis: storage_limitation
      timer: started
      exact_days: legal_block   # крючок 2, конкретное число — правовой блок

  ownership:
    architecture: unchanged
    decided_here: [second_chat_id_place_named, erasure_covers_delivery_registry, retention_anchor_from_lifecycle_end]
    still_legal_block: [identity_map_retention_days]
```
