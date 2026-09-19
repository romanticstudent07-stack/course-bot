---
file: 15/15-05-durability.md
block: 15
title: "Шаг 5 — Durability (надёжность хранения)"
status: закрыт
doc_version: "consolidated v3"
contains: [Шаг 5, 5.1–5.12, дополнение 5.14–5.21, пороги, защита жизни, catch-up, runbook, yaml step_5, связанные артефакты долга]
---

# БЛОК 15 · ШАГ 5 — DURABILITY (НАДЁЖНОСТЬ ХРАНЕНИЯ)

Шаг 5 — парный к Шагу 4: тот обеспечил атомарность на уровне приложения, этот — чтобы это не обесценилось потерей данных на уровне хранилища. То, что база подтвердила записанным, должно пережить сбой питания, порчу диска, потерю сервера и переезд на VPS. Профиль: self-hosted PostgreSQL, самостоятельное обслуживание, старт на своём сервере, плановый бесшовный переезд на VPS. Всему шагу подчинён инвариант «жизнь сгорает только по вине участника».

Переносимость (5.1): вся правда только в PostgreSQL (перенести систему = перенести одну базу; Redis не переносим, потеря безопасна); конфигурация вынесена в env-переменные; все таймеры — строки с fire_at, переезжают вместе с базой. Миграция — минуты простоя: стоп бота (Telegram повторит апдейты) → убедиться, что старый экземпляр мёртв → pg_dump → копия на VPS → pg_restore → перенос конфига → deleteWebhook + новый webhook → старт (startup-recovery + reconciler добирают наступившие fire_at). pg_dump логический (переносим между версиями PG), pg_basebackup — только для базовых бэкапов под PITR.

WAL и базовая durability (5.2): WAL всегда включён; synchronous_commit = on и fsync = on не отключаем — durability важнее скорости, нагрузка мала. Бэкапы 3-2-1 (5.3): pg_dump по cron + архив WAL; pgBackRest отвергнут как избыточный (путь миграции при росте); три копии (живая + локальная + offsite), offsite — второй диск/NAS на старте, S3-совместимое после VPS; golden rule: бэкап, не проверенный восстановлением, не считается существующим. PITR (5.4): базовый бэкап + непрерывный архив WAL; на тестовой фазе опционален, к боевому запуску обязателен; archive_timeout порядка минут.

Критичная поправка к outbox (5.5): сортировка/выборка строго по id bigint (не по времени); партиционирование outbox по «отправлено/не отправлено» (relay сканирует маленькую unsent-партицию); регулярный TRUNCATE отправленной партиции (housekeeping безопасен, т.к. message_id уже перенесён). Структуру партиционирования закладываем сразу — превратить таблицу в партиционированную задним числом тяжело.

Защита жизни — два механизма catch-up (5.6, сердце шага). Жизнь жжёт только полное молчание (2 календарных дня подряд на обычных днях или 1 пропущенный день рефлексии); прочие таймеры мотивационные. Риск стека: планировщик по умолчанию выполняет просроченную misfired-задачу немедленно — проснувшийся бот спишет жизнь за дедлайн, прошедший, пока бот лежал. Механизм 1 (короткие простои): misfire_grace_time = 1 час + re-check по БД (списание только если подтверждено настоящее полное молчание — логическая инверсия «зачёт только по подтверждённой записи»). Механизм 2 (длинные простои): reconciler при старте без верхней границы по времени, идёт по append-only журналу и durable-состоянию за весь период недоступности, обрабатывает пропущенные дни строго последовательно (по одному −1, «−2 не бывает»). Три жёстких правила reconciler: заморозка (пауза/тайная пауза/неоплата) имеет абсолютный приоритет над catch-up; любая неопределённость → техсбой → жизнь не списывается; первый пропуск бесплатный + re-check достаточно, отдельный грейс на досдачу не вводим. Число misfire = 1 час не критично: длинные окна ловит reconciler по фактам. Порог incomplete_day как карательное число упразднён (любой ненулевой создаёт несправедливую серую зону); остаётся только как параметр мониторинга heartbeat.

Восстановление как runbook (5.7): не воевать с процессом восстановления PostgreSQL — дать ему завершиться (стоп базы → полная очистка каталога → восстановление начисто → дать проиграть WAL → потом проверять); никогда не удалять backup_label/recovery.signal; тестовое восстановление — полная репетиция на изолированной машине.

Защита от pg_wal-переполнения (5.8, краш №1): при сломанном archive_command старые WAL копятся и валят базу; удалять руками нельзя. archive_command пишет сначала в локальный архив, отдельный процесс синхронизирует в offsite (WAL «в безопасности» после локальной записи — не связываем живучесть боевой базы с резервным диском); мониторинг pg_stat_archiver.failed_count и диска pg_wal > 80%. XID wraparound (5.9, краш №2): high-churn таблицы (outbox, таймеры, журнал попыток, реестр) + партиционирование + агрессивный autovacuum + мониторинг возраста старейшего незамороженного XID. Single-instance-guard (5.10, краш №4): защита от 409 Conflict через строку-лидер с TTL (advisory locks отвергнуты); шаги миграции «убедиться, что старый мёртв» и deleteWebhook до нового. Защита пула (5.11, краш №5): жёсткий верхний лимит + все фоновые задачи в одном процессе; PgBouncer как путь миграции. Мониторинг (5.12): pg_stat_archiver, возраст старейшей неотправленной outbox-строки, dead-letter, возраст XID, успех последнего тест-восстановления, heartbeat воркера; алерт на failed_count > 0 обязателен.

Дополнение (5.14–5.21). Reconciler на найденной ошибке действует по dead-letter-принципу: безопасное расхождение дочиняет идемпотентно, неоднозначное → needs_manual_review + алерт, порог = 5; пока needs_manual_review и касается жизни — жизнь не списывается. Самозащита reconciler: pg_try_advisory_lock против пересечения прогонов (здесь advisory уместен — координация фонов, не бизнес-операция), checkpoint-курсор по id против падения на середине, atomic status + SKIP LOCKED против гонки за запись, statement_timeout + heartbeat против зависания. Провал архива WAL — трёхуровневая лестница (ранний алерт при failed_count>0/неактивных слотах → срочный при диске>80% → аварийный runbook), max_slot_wal_keep_size как предохранитель. Single-instance — TTL-lease с продлением (renew ~10 с, TTL ~30 с) + fencing (потеряв аренду, экземпляр самоустраняется) + эксклюзивность webhook. DST/tz: всё время в UTC (timestamptz), tz участника накладывается только при вычислении дедлайна и отображении; Россия — фиксированный UTC+3; спящая способность (окно вокруг перехода трактует неоднозначность в пользу участника) активируется только при появлении DST-участника. Тихий провал pg_dump: проверка exit code + еженедельная репетиция restore + метрика «возраст последнего проверенного бэкапа». Медленная утечка соединений: контекст-менеджер гарантированного возврата + мониторинг активных соединений; reconciler служит страховкой при залипшем планировщике. Autovacuum настраивается per-table только на high-churn, на слабом железе — умеренный cost_delay.

## YAML — Шаг 5

```yaml
block_15:

  # ================================================================
  step_5:
    title: "Durability (надёжность хранения)"
    status: closed
    paired_with: step_4
    profile: {hosting: self_hosted_postgresql, maintenance: self_managed, lifecycle: local_server_then_vps, managed_postgres: rejected}
    core_invariant: {life_loss_only_by_user_fault: true, tech_failure_never_costs_life: true, default_in_favor_of_user: true}
    portability:
      single_source_of_truth: postgresql
      redis_role: ephemeral_dedup_cache_only
      config_external: env_vars_only
      timers_as_db_rows: true
      migration_procedure: [stop_bot, ensure_old_instance_dead, pg_dump_logical, copy_to_vps, pg_restore, move_external_config, delete_old_webhook_then_set_new, start_bot]
      dump_tool: pg_dump_logical_portable_across_versions
    wal_and_base_durability: {wal: always_on, synchronous_commit: on, fsync: on, rationale: durability_over_speed}
    backups_3_2_1:
      tool_start: pg_dump_cron_plus_wal_archive
      pgbackrest: rejected_overkill_reserved_for_growth
      copies: [live_db, local_backup, offsite_copy]
      offsite: {start: second_disk_or_nas, after_vps: s3_compatible}
      golden_rule: backup_unverified_by_restore_does_not_exist
    pitr: {definition: base_backup_plus_continuous_wal, archive_mode: on, archive_timeout_minutes: [1, 5], test_phase: optional, production: mandatory_before_launch}
    outbox_durability_fix:
      order_by: id_bigint_identity_only
      forbid_order_by_created_at: true
      partitioning: by_published_flag
      housekeeping: truncate_sent_partition
      truncate_safe_because: message_id_moved_to_content_table_first
      lay_structure_now: true
    life_protection_catchup:
      only_life_burning_event: {normal_days: two_consecutive_full_silence, reflection_days: one_missed}
      non_punitive_timers: [reminder_ladder, midday_nudge, queue_effect]
      stack_risk: default_scheduler_runs_misfired_job_immediately
      mechanism_1_short: {misfire_grace_time_hours: 1, behavior: recheck_db_before_deduct, logic: inverse_of_credit_only_on_confirmed_record}
      mechanism_2_long: {component: startup_reconciler, upper_time_bound: none, sequential_days: true, one_deduction_at_a_time: true}
      hard_rules: {freeze_over_catchup_priority: true, default_in_favor_of_user: true, first_miss_free_plus_recheck_sufficient: true}
      incomplete_day_threshold: {as_punitive_number: removed, reason: recheck_by_fact_covers_any_downtime, remaining_use: heartbeat_monitoring_only}
    restore_runbook: {golden_rule: let_postgres_recover_itself, never_delete: [backup_label, recovery_signal], flow: [stop_db, wipe_data_dir, restore_clean, let_wal_replay, then_verify], test_restore: full_rehearsal_on_isolated_machine}
    pg_wal_overflow_guard:
      archive_command_target: local_archive_first
      offsite_sync: separate_process
      wal_safe_after: local_write
      monitoring: {pg_stat_archiver_failed_count_alert: ">0", pg_wal_disk_alert_pct: 80}
      emergency: documented_expand_volume_never_delete_files_manually
    xid_wraparound_guard: {high_churn_tables: [outbox, durable_timers, attempt_journal, message_registry], autovacuum: aggressive, monitoring: oldest_unfrozen_xid_age}
    single_instance_guard: {mechanism: ttl_lease, advisory_locks: rejected, prevents: telegram_409, migration_steps: [ensure_old_dead, delete_old_webhook_before_new]}
    connection_pool_guard: {pool_hard_upper_limit: true, all_background_single_process: true, growth_path: pgbouncer}
    monitoring:
      metrics: [pg_stat_archiver_lag_and_failed_count, oldest_unsent_outbox_row_age, dead_letter_size, oldest_unfrozen_xid_age, last_test_restore_success, unified_worker_heartbeat]
      mandatory_alert: wal_archive_failed_count_gt_0
    addendum:
      reconciler_error_handling: {safe_fix: missed_deduction_idempotent_recheck, unsafe: needs_manual_review, retry_threshold: 5, life_rule: no_deduction_while_needs_manual_review}
      reconciler_self_protection: {overlap_guard: pg_try_advisory_lock, advisory_scope: background_coordination_only, crash_resume: checkpoint_cursor_by_id, row_race_guard: atomic_status_plus_skip_locked, hang_guard: statement_timeout, liveness: reconciler_heartbeat}
      wal_archive_failure_ladder:
        level_1_early: {trigger: [archiver_failed_count_gt_0, inactive_replication_slots], action: alert_fix_today}
        level_2_urgent: {trigger: pg_wal_disk_pct_gt_80, action: alert_act_now}
        level_3_catastrophe: {trigger: disk_full_or_panic, action: emergency_runbook}
        golden_rule: never_delete_wal_manually
        db_after_panic: not_corrupted_recoverable
        future_safeguard: max_slot_wal_keep_size
      single_instance_lease: {model: ttl_lease_with_renewal, renew_interval_seconds: 10, ttl_seconds: 30, split_brain_guard: fencing_check_before_critical_action, zombie_behavior: lost_lease_self_terminate, second_layer: telegram_webhook_exclusivity}
      timezone_dst: {storage: utc_timestamptz_always, apply_user_tz: only_at_deadline_eval_and_display, russia: fixed_offset_utc_plus_3, future_dst_user: auto_via_tzdata_per_user, dormant_capability: {dst_transition_window: punitive_ops_favor_user, active_only_if: dst_user_exists}}
      pg_dump_silent_failure_guard: {check_exit_code: true, delayed_check: weekly_test_restore, metric: age_of_last_verified_backup, alert_if: older_than_1_day}
      connection_leak_guard: {hygiene: context_manager_guaranteed_return, monitor: active_connections_metric, reconciler_as_safety_net: true}
      autovacuum_refinement: {scope: per_table_high_churn_only, not_global: true, weak_server: moderate_cost_delay}
    thresholds:
      derived: {dedup_key_ttl_seconds: few, scan_batch_size: 100, scan_batch_max: 1000, worker_retry_count_threshold: 5, backoff: exponential_with_jitter, archive_timeout_minutes: [1, 5], misfire_grace_time_hours: 1, heartbeat_interval_seconds: 30, heartbeat_alert_consecutive_misses: 5}
      product_open: {backup_frequency: daily_recommended, reconciler_interval: startup_mandatory_periodic_optional_minutes, verdict_escalation_timer_b_to_c: wait_until_21_00_user_tz, queue_effect_window_10_60min: architecture_given}
```

## Связанные артефакты долга

- [`../debt/15-A2-background-concurrency.md`](../debt/15-A2-background-concurrency.md) — узел A2, CLOSE, v3.2.
  Здесь durability выступает нормативным владельцем NR-решения из A2:
  колонка `transaction_id xid8` (fill `pg_current_xact_id()`), фильтр
  видимости `transaction_id < pg_snapshot_xmin(pg_current_snapshot())`,
  курсор по паре `(transaction_id, id)`. Голый `id > last` запрещён.
  Обратная граница: скан таймеров в A2 владеет только фактом
  «`fire_at` наступил» — решение о списании жизни принадлежит 5.6
  (re-check/reconciler; заморозка > catch-up; неопределённость → не списывать).

