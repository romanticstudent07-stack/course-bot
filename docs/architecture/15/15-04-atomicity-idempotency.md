---
file: 15/15-04-atomicity-idempotency.md
block: 15
title: "Шаг 4 — Атомарность и идемпотентность (в связке с Шагом 5)"
status: закрыт
doc_version: "consolidated v3"
contains: [Шаг 4, порции 4.1–4.3, dual-write, transactional outbox, каталог операций, пять мест ожидания, решение 4.2.a, фоновые процессы, recovery-асимметрия, парковка в Шаг 5, yaml step_4]
---

# БЛОК 15 · ШАГ 4 — АТОМАРНОСТЬ И ИДЕМПОТЕНТНОСТЬ (В СВЯЗКЕ С ШАГОМ 5)

Шаг 4 решает главную проблему системы — dual-write: PostgreSQL (истина о состоянии) и Telegram (сообщения) не могут участвовать в одной транзакции, между записью в БД и отправкой есть щель для сбоя. Решение — транзакционный Outbox: доменный эффект и намерение внешнего действия пишутся одной PG-транзакцией, фактическая отправка — отдельной фазой фоновым polling-воркером. Недостижимая «exactly-once для dual-write» меняется на достижимую пару «БД атомарна» + «внешнее действие at-least-once, но идемпотентно». Идемпотентность — не опция, а условие корректности.

## Фундаментальная модель (4.1)

Outbox без внешнего CDC — in-process polling-реле (один воркер), без Debezium; путь миграции на CDC документирован. Проблема упорядоченности polling решена: событие обрабатывается только если нет более старых незакоммиченных транзакций (подход no-older-in-flight / xmin) плюс сортировка строго по возрастанию id. Два механизма идемпотентности сведены к одному через outbox: ручной триггер → ключ `<update_id>-<action_seq>` (Telegram гарантирует стабильность update_id); таймерный/детерминированный → ключ `<user>-<day>-<op>`. Область идемпотентности — все эффекты с последствиями (Lives, контент, платежи, прощальное уведомление, шаги erasure), не только отправка. Конкурентность check-then-act (лимит мест, списание Lives) решается атомарным UPDATE … WHERE condition RETURNING, а не изоляцией (READ COMMITTED не защищает от lost update); FOR UPDATE точечно; глобальный SERIALIZABLE отвергнут. Гонка видимости незакоммиченного намерения закрыта двумя инвариантами: фоновые процессы работают только с закоммиченными строками; координация бизнес-tx ↔ фоновик только через durable-состояние в БД, никогда через память. Для необратимых эффектов ключ ставится перед действием (deleteMessage: «уже удалено» = успех; sendMessage: «already sent = success» по наличию message_id). Решение по message_id (одобрено): хранить message_id, но переносить из outbox в основную таблицу контента после подтверждения sent, а outbox-запись чистить; до переноса recovery-владелец — outbox, после — основная таблица.

## Каталог операций (4.2)

Сквозные инварианты: per-user ordering (внутри участника строгий порядок, между участниками параллелизм — урок #5 не раньше #4); атомарный статус-переход UPDATE … WHERE status=ожидаемый RETURNING (пустой RETURNING = «уже обработано» = no-op) для всех check-then-act и вердиктов Автора; двухэшелонная идемпотентность (tier-1 короткий ключ против дребезга + tier-2 durable UNIQUE-констрейнт/статус против долгого повтора после истечения TTL; у каждого эффекта обязан быть tier-2); мгновенный durable-зачёт против отложенного показа (зачёт дня мгновенен и durable, показ — отдельная механика, сбой в ожидании не теряет зачёт).

Пять мест ожидания участника: эффект очереди (после каждой сдачи, рандом 10–60 мин, зачёт мгновенный, жизнь не теряется); вердикт рефлексии Дня 13 (авто-прохода НЕТ; фаза A — вердикт применяется, фаза B — тихое ожидание до 21:00 ТЗ участника + срочный алерт Автору, фаза C — тайная пауза с заморозкой прогресса/жизней/таймеров без санкций); проверка оплаты (статус-сообщение всегда, ложного успеха нет); запрос паузы (одобрение одним тапом, молчание Автора до даты начала = авто-разрешение в пользу участника + алерт — единственное место ожидания с авто-действием).

Ключевое решение 4.2.a: при таймерной проверке дедлайна списание Lives и разблокировка следующего дня — одна транзакция, не две операции (обе чисто внутри-БД, нет внешнего side-effect между ними, БД гарантирует атомарность; дробление оправдано только при внешнем вызове между шагами). Механика попыток: провал дня → attempt+1, те же задания на следующую дату; append-only журнал попыток (арбитр) + проекция «Карта Изменений» (пересобирается из журнала). Пять инфраструктурных защит: poison message → dead-letter после порога (non-transient 403/chat not found → сразу dead-letter); 429 → wait retry_after + retry, не расходует retry-квоту; двухэшелонная идемпотентность; застрявшие человеко-вердикты → механики ожидания, не авто-решение за человека; дрейф проекции → мандат сверщика.

## Фоновые процессы и recovery-асимметрия (4.3)

Единый шаблон воркера: SELECT … WHERE `<статус>` ORDER BY created_at LIMIT N FOR UPDATE SKIP LOCKED → обработать → пометить результат только после подтверждения внешней системой → commit. Даёт разом: нет двойного захвата (SKIP LOCKED), краш в середине батча не теряет работу, порядок. Leader election не нужен — арбитр конкуренции сама БД через row-lock. Старт бота — не спец-процедура, а обычный запуск воркеров, подхватывающих всё незавершённое по статусу; устойчивость к рестарту бесплатна. Инвентарь: relay-досыльщик (per-user ordering, 429, приоритет критичных), доудалятель (pending_delete → deleted, «не найдено» = success), сверщик (проекции против журнала, мониторит dead-letter), dead-letter-монитор, durable-таймеры (строки с fire_at, скан находит наступившие, краш не «проспит» дедлайн, всё время из now() БД). На старте — один воркер с задачами по расписанию, не 5 деплой-единиц. Планировщик: pg_cron (fallback — application-loop), pgAgent исключён. Recovery-асимметрия пооперационно: фиксация/доставка — только вперёд; удаление (refund, restart) — назад до коммита, вперёд после; erasure — только вперёд, необратим. Защиты от прод-проблем: ни одна tx не открыта на время сетевого вызова (анти-bloat); малые батчи + короткие tx (анти-pool-exhaustion); UNIQUE + ON CONFLICT DO NOTHING (анти-race); быстрый 200 вебхуку + асинхронная обработка (анти-дубль); экспоненциальный backoff с джиттером + catch-up порциями (анти-thundering-herd); advisory locks отвергнуты в пользу SKIP LOCKED; мониторинг возраста очереди обязателен как мера безопасности. Тонкость catch-up: после долгого downtime нельзя списать N дедлайнов залпом без поправки на то, что участник не мог действовать, пока бот лежал (калибруется порогом «неполного дня» → Шаг 5).

## YAML — Шаг 4

```yaml
block_15:

  # ================================================================
  step_4:
    title: "Атомарность и идемпотентность (в связке с Шагом 5)"
    status: closed
    core_problem: dual_write
    solution: transactional_outbox
    correctness_tradeoff: "недостижимая exactly-once -> 'БД атомарна' + 'внешнее at-least-once, но идемпотентно'"
    portion_4_1:
      d1_outbox_no_cdc: {decision: "in-process polling relay (single worker)", ordering_fix: "no-older-in-flight (xmin) + сортировка по возрастанию id", migration_path: "CDC при росте"}
      d2_single_idempotency: {key: "<update_id>-<action_seq>", unique_constraint: "UNIQUE(idempotency_key)", status_flow: "pending -> sent(message_id)"}
      d3_scope_all_effects: [контент, Lives, платёжные_подтверждения, прощальное_уведомление, шаги_erasure]
      d4_per_user_ordering: {partition_key: user_id, rule: "внутри участника строгий порядок; между — параллелизм"}
      d5_composite_erasure: {state: "feed_cleaned -> identity_broken -> done", recovery: forward}
      d6_concurrency: {decision: "UPDATE ... WHERE condition RETURNING", for_update: "точечно", rejected: [global_serializable]}
      d7_irreversible: ["already deleted = success", "already sent = success (по message_id)", "ключ ПЕРЕД необратимым действием"]
      race_uncommitted_intent: {inv_1: "фоновики только с committed строками", inv_2: "координация только через durable-состояние, не память"}
      message_id_decision: {value: "хранить message_id, перенести из outbox в основную таблицу после sent, outbox чистить", recovery_owner_before: outbox, recovery_owner_after: main_content_table}
    portion_4_2:
      cross_cutting: {per_user_ordering: true, atomic_status_transition: "empty RETURNING = no-op", two_tier_idempotency: "tier-1 короткий ключ + tier-2 durable у каждого эффекта", instant_credit_vs_deferred_show: true}
      waiting_mechanics:
        - {id: queue_effect, when: "после каждой сдачи", timing: "рандом 10-60 мин", guarantee: "зачёт мгновенный; очередь тормозит показ; жизнь не теряется"}
        - {id: reflection_verdict_day13, auto_pass: NEVER, phases: {A: "применить", B: "тихое ожидание до 21:00 ТЗ + алерт Автору", C: "тайная пауза: заморозка без санкций"}}
        - {id: payment_verification, ux: "'проверяем оплату' — ложного успеха нет"}
        - {id: pause_request, auto: "молчание Автора до даты начала -> авто-разрешение + алерт"}
      resolved_4_2_a: {question: "дедлайн: списание Lives + разблокировка next_day", decision: "ОДНА транзакция", rationale: "обе внутри-БД, нет внешнего side-effect между ними"}
      history_projection_split: {journal: "append-only, арбитр", projection: "Карта Изменений, пересобирается", revert_day13: "возврат на день Автора; дни переигрываются attempt+1"}
      blind_spot_defenses:
        poison_message: "> N retry -> dead-letter; non-transient (403 blocked, chat not found) -> сразу dead-letter"
        rate_limit_429: "wait retry_after; НЕ расходует retry-квоту"
        stuck_verdict: "waiting_mechanics, не авто-решение за человека"
        projection_drift: "мандат сверщика; журнал = арбитр"
    portion_4_3:
      unified_worker: {query: "SELECT ... WHERE <status> ORDER BY created_at LIMIT N FOR UPDATE SKIP LOCKED", mark_result: "только после подтверждения внешней системой", leader_election: NOT_NEEDED}
      startup_recovery: "старт = обычный запуск воркеров, подхватывают незавершённое по статусу; устойчивость к рестарту бесплатно"
      processes: [relay_dispatcher, deleter, reconciler, dead_letter_monitor, durable_timers]
      durable_timers: {storage: "строки БД с fire_at", crash_safety: "краш не проспит дедлайн; catch-up", time_source: "now() БД"}
      scheduler: {preferred: pg_cron, fallback: application_loop, excluded: pgAgent, at_start: "один воркер, не 5 деплой-единиц"}
      recovery_asymmetry: {forward_only: [issue_day, deadline_processing, submit_report, confirm_payment], back_then_forward: [refund_deletion, restart_deletion], forward_only_irreversible: [erasure]}
      stability_defenses:
        anti_bloat: "ни одна tx не открыта на время сетевого вызова"
        anti_pool_exhaustion: "малые батчи, короткие tx"
        anti_race: "UNIQUE + ON CONFLICT DO NOTHING"
        anti_webhook_duplicate: "быстрый 200 + async обработка"
        anti_thundering_herd: "backoff с джиттером; catch-up порциями"
        advisory_locks: "отвергнуты в пользу SKIP LOCKED"
        queue_monitoring: {status: MANDATORY, reason: "безопасность: отставание маскирует потерю критичных эффектов"}
      catchup_nuance: {problem: "нельзя списать N дедлайнов залпом задним числом", calibration: "порог 'неполного дня' -> Шаг 5"}
    parked_to_step_5: [dedup_key_ttl, worker_retry_count_threshold, incomplete_day_threshold, verdict_escalation_timer, reconciler_interval, queue_effect_window_10_60min, scan_batch_size, backoff_params, queue_age_alert_threshold]
```
