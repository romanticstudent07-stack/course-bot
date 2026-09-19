---
file: 15/15-99-yaml-full.md
block: 15
title: "Единый YAML Блока 15 — монолит целиком (контрольный эталон)"
status: канон
doc_version: "consolidated v3"
contains: [единый YAML block_15 без нарезки, YAML дополнения]
---

# ЕДИНЫЙ YAML БЛОКА 15 — МОНОЛИТ ЦЕЛИКОМ

Этот файл хранит YAML Блока 15 ровно в том виде, в котором он лежит в оригинале — одним неразрезанным монолитом. Он существует для побайтовой сверки: секции, разложенные по файлам частей `15/15-00…15-12`, должны совпадать с соответствующими фрагментами этого монолита. При любом расхождении истиной считается этот файл (и, выше него, оригинальный `Архитектура(1).docx`).

## Единый YAML

```yaml
# ================================================================
# БЛОК 15 — ЕДИНАЯ ПОЛНАЯ СБОРКА (Шаги 0–10 + крючки)
# Несущий инженерный блок-исполнитель: хранение, доставка, удаление,
# durability, анти-пиратство, детекция, логи, fail-safe.
# Все связи с блоками-владельцами правил — одностороннее чтение.
# ================================================================
block_15:

  # ----------------------------------------------------------------
  # СКВОЗНЫЕ ИНВАРИАНТЫ ВСЕГО БЛОКА
  # ----------------------------------------------------------------
  global_invariants:
    - "критичное синхронно в PostgreSQL; Redis — только некритичный ускоритель"
    - "нет висячих ссылок"
    - "каркас курса неизменен после запуска"
    - "все переносы данных/владения между блоками фиксируются явно"
    - "нет пустых экранов: у участника всегда осмысленный выход, бот не падает"
    - "жизнь сгорает только по вине участника; техсбой никогда не стоит жизни"
    - "любая неоднозначность трактуется в пользу участника"

  content_model:
    external_channel: {type: public, scope: out_of_project, holds: [media, video], protected_by_block_15: false}
    bot_serves: ["текст задания (генерация из YAML-конфига)", "ссылки на посты публичного канала"]
    bot_never_serves: [media, file_id, images, files]
    protected_value: "текст заданий (методология, структура, последовательность, инструкции)"
    antipiracy_target: task_text_not_media

  # ================================================================
  step_0:
    title: "Аудит входящих ссылок и контракт Блока 15"
    status: closed
    purpose: >
      Установить зону ответственности/границы и собрать реестр обязательств из
      закрытых блоков. Б15 — исполнитель: даёт механизмы, не бизнес-правила.
    decisions:
      durability_transfer: {value: "block_14 -> block_15", reason: "исторически за Б14; без переноса — рассинхрон", register_ref: "1.10", principle: "все переносы владения фиксируются явно"}
      refund_deletion_nature:
        value: "отзыв доступа, не стирание"
        approved: true
        reasons: ["съёмка камерой непредотвратима", "лимиты платформы на удаление"]
        note: "protect_content запрещает пересылку/сохранение → легальных копий нет"
        goal: "Б16 и правовой блок не строят ложных гарантий"
      course_frame_immutability:
        value: immutable_after_launch
        reason: "стабильные узлы дерева 'Пройденного' не осиротеют"
        mutable_only: "текст внутри существующего дня"
        nature: "организационное обещание, не техническая невозможность"
        fallback: "неподдерживаемое действие → без краха, мягкий фоллбэк"
      antipiracy_depth: {value: full, includes: [threat_model, detection, user_protection]}
      logs_separation:
        entries: [{log: regeneration_log, owner: block_15}, {log: card_access_audit_152fz, owner: block_6}]
        rule: "разные основания хранения, не сливаются"
      coupled_steps: {pair: [step_4_atomicity, step_5_durability], reason: "единая модель транзакций"}
    incoming_obligations:
      from_block_1: ["durability: WAL, бэкапы 3-2-1, PITR, персистентность", "критичное синхронно в PG; Redis некритичное"]
      from_blocks_3_and_7: ["эффект очереди как отложенная задача (Celery/APScheduler), переживает перезапуск"]

      from_block_13: ["атомарность/идемпотентность commit/refund/restart", "recovery-асимметрия: commit вперёд; refund/restart назад",
                      "формат логов регенераций", "механика реакции на аномалии", "валидация протухших ссылок",
                      "окно дедупликации (случай 7.7)", "медиа-водяные знаки неприменимы"]
      from_block_16: ["физическое удаление контента при рефанде по participant_id+stage+message_id",
                      "фоновый сверщик 'confirmed-но-не-delivered'", "'пересланное/сохранённое' — зона защиты Б15"]
      from_appendices: ["описание Б15", "инвариант Redis-durability"]
    not_owned:
      - {area: "навигация до 'Пройденное'", owner: block_10}
      - {area: "правила Пройденного, committed/pending, 'нет сирот', приоритеты refund>commit_guard, erasure>identity", owner: block_13}
      - {area: "бизнес-флоу оплаты/рефанда", owner: block_16, block_15_gives: "вызов 'удалить контент stage=N'"}
      - {area: "состав Карты изменений", owner: block_14}
      - {area: "юр. сроки удаления ПДн и обезличивание", owner: legal_scope, block_15_gives: "техспособность удалить/обезличить"}
    link_direction: {mode: read_only, reads_from: [block_13, block_16], emits_outward: ["лимит исчерпан", "контент недоступен"], does_not_control: "логику показа"}
    open_questions: []

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

  # ================================================================
  step_2:
    title: "Адресация и доставка контента"
    status: closed
    fork_1_delivery_protocol:
      phases: [{pending: "намерение атомарно с бизнес-логикой в одной tx PG; без message_id"}, {send: "физическая отправка"}, {active: "вписывается message_id"}]
      unfinished_pending: picked_up_by_background_relay
      never_delete_row: true
      pattern: transactional_outbox + polling_relay
      realizes_parked_hook: "сверщик confirmed-но-не-delivered (Б16)"
      delivery_guarantee: at_least_once
    fork_2_unit_and_classifier:
      model: B
      day_composition: {blocks: 5, per_block: "отдельное сообщение + свои кнопки", fifth_block_extra: "кнопка 'Отправить отчёт'"}
      reason_model_B: "Telegram не привязывает кнопки к середине; + обход длины + гранулярность"
      block_numbering: {required: true, roles: ["проверка отчёта по блокам", "логический адрес для идемпотентности/досылки"], logical_address: [participant_id, module, day, block_number]}
      classifier:
        content: {items: [task_blocks, links_inside, reflection_note, author_replies, author_reactions], deleted_on_refund: true}
        service: {items: [reminders, queue_notices, motivational], deleted_on_refund: false}
        transactional: {items: [payment_confirmations, refund_facts, consents], storage: immutable, deletable: false}
        implemented_as: single_field_type
    fork_3_idempotency_vs_limit:
      order: [dedup_first, limit_second]
      rule: "технический повтор никогда не расходует лимит"
      dedup_three_levels:
        level_1_client: "деактивация кнопки + обязательный answerCallbackQuery (UI не зависает)"
        level_2_server: {key: [participant_id, day, purpose], store: fast_short_ttl, on_duplicate: [empty_ack, no_delivery, no_limit_charge], closes: "окно дедупликации 7.7"}
        level_3_boundary: "'дубль vs новый' = факт списания лимита"
      limit:
        budget: 3
        unit: "полная выдача задания дня (текст из конфига, без кнопок)"
        counts: outputs_not_unique_days
        window: rolling_24h
        timezone: participant_tz
        reason_rolling: "закрывает эксплойт полуночи; для честного участника незаметно"
        implementation: "COUNT за now-24h..now; без ночного обнулятора; переживает перезапуск"
        charge: atomic
        detection_fields: [participant_id, day, timestamp, counts_in_limit]
        single_source_for: [limit, future_anti_fraud]
      source_of_truth: postgresql
      redis: "только некритичный ускоритель дедупликации"
    fork_4_partial_delivery_failure:
      approach: idempotent_partial_retries
      relay_behavior: {picks: only_pending_rows, order: ascending_block_number, does_not_touch: [delivered_blocks, participant_checkmarks]}
      submit_button_rule: "'Отправить отчёт' только с доставкой 5-го блока"
      recovery_principle: forward_complete
      flood_control_429: {treat_as: normal_not_failure, on_429: [read_retry_after, wait_exactly, retry_same_block], not_counted: true, note: "≈1 msg/sec в чат"}
      select_for_update_skip_locked: true
      retry_count_threshold: {real_errors_only: true, on_threshold: [mark_failed, alert_manual_review]}
      outbox_lag_metric: {meaning: "возраст старейшей pending-строки", on_exceed: alert, detail_hook: step_5}
      rejected_overkill: {cdc_debezium: "polling latency некритична", kafka: "потребитель = Bot API, не микросервисы"}
    cross_block: {submit_button_gating: {owner: block_3, block_15_role: "довезти 5-й блок с кнопкой"}}
    open_questions: []

  # ================================================================
  step_3:
    title: "Удаление контента и защита истории"
    status: closed
    axiom_1_content_protection:
      status: closed_forever
      protection_enabled: maximum_available_on_platform
      mechanisms: [{protect_content: true}, {no_media_inside_bot: true}, {hidden_marker_ref: step_6}]
      platform_limitation: {ios_text_screenshot: "не блокируется (нач. 2026)", screenshot_notification: not_available_in_bot_api}
      out_of_project_forever: {external_camera_capture: true, rationale: "физический предел любой платформы"}
      never_reraise: true
    axiom_2_deletion_vs_anonymization:
      status: closed_forever
      physically_deleted: {scope: identity_only, fields: [name, birthdate, phone, tg_user_id, tg_username, photos, region, "любые идентифицирующие"]}
      anonymized_and_kept_forever: {items: [measurements, checkup, reflections_anon_corpus, progress, lives_journal, payment_stats, analytics], attachment_to_identity: none}
      identity_break: irreversible
      returning_user: from_scratch_no_restore
      append_only_compat: "журнал физически цел; вырезается только привязка к личности"
      default_on_ambiguity: "идентификатор -> удалить; прочее -> обезличить и хранить"
      never_reraise: true
    deletion_triggers:
      refund: {deletes: committed_and_pending_content_of_stage_N, removes_commit_guard: true, changes_payment_status: true, never_touches: [other_stages, participant_messages, reflection_replies, measurements, financial, service]}
      restart: {deletes: current_stage_content_all_days, never_touches: committed_of_completed_stages, mechanics: identical_to_refund_deletion, differs: "не снимает guard, работает по pending"}
      revert: {chat_deletion: none, affects: visibility_tree_only, dupes_cleanup: false}
      erasure: {by: identity, priority: absorbs_all, deletes_from_chat: all_bot_content_all_stages, then: [break_identity_irreversible, anonymize_rest]}
    canonical_deletion_procedure:
      stage_0_remove_guard: {when: zone_is_committed, action: remove_commit_guard, else: noop}
      stage_1_mark_intent: {action: "set_status(pending_delete)", atomic_with: business_decision, mirror_of: delivery_intent_phase}
      stage_2_physical_delete: {api: deleteMessages, batch_up_to: 100, on_batch_success: "set_status(deleted)", flood_control_429: {treat_as: normal, on_429: [read_retry_after, wait, retry_same_batch]}}
      stage_3_final_notification: {mechanism_owner: block_15, wording_owner: communication_block, principle: no_empty_screens}
    failure_recovery:
      point_of_no_return: stage_1_intent_committed
      before_intent: {action: rollback_backward, state: [nothing_deleted, business_unchanged]}
      after_intent: {action: forward_complete, worker: background_deleter, finds: "rows(status==pending_delete)"}
      reconciliation_with_b13: "'refund/restart назад' — про бизнес-состояние; у физудаления граница отката = фиксация намерения"
      security_guarantee: "нет состояния с навсегда доступным возвращённым контентом"
    erasure_procedure:
      composition: ["run_canonical_deletion(all_stages)", break_identity_irreversible, anonymize_rest]
      order_rule: "сначала вычистить ленту (нужен адрес чата), потом рвать идентичность"
      farewell_notification: {sent: last_action_before_identity_break, wording_owner: communication_block}
    trigger_races: {resolution: [idempotent_deletion, erasure_absorbs_all]}
    open_questions: []

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

  # ================================================================
  step_7:
    title: "Детекция подозрительного темпа и мягкая приостановка"
    status: closed
    meta: {owner_block: 15, data_source_block: 13, scope: "Пройденное", hermetic: false, invariant: default_in_favor_of_user}
    trigger:
      pattern: strict_contiguous_sequence
      directions: [ascending, descending]
      direction_lock: true
      gap_tolerance: 0
      confirmation: {days_required: 2, timezone: project_tz, fire_on: first_request_of_day_3}
      reset_conditions: [gap_in_sequence, direction_change, day_without_matching_request]
      example_fire: "d1:1,2,3 | d2:4,5,6 | d3:7 -> приостановка"
      example_nofire: "d1:1,2,3 | d2:9,4 -> сброс"
    reaction: {type: soft_suspension, ban_user: false, gated_section: "Пройденное", rest_of_bot: fully_operational, user_message: "Технические неполадки. Уже устраняем", reveals_antifraud: false}
    suspension:
      storage: db_flag
      keyboard_behavior: unchanged
      enforcement: gate_on_handler_entry
      guard: {first_step: check_is_suspended, on_active: "return user_message, emit no data", idempotent: true, stale_button_safe: true}
      fields: {is_suspended: bool, suspended_at: timestamptz, suspend_reason: suspicious_tempo, trigger_snapshot: json}
    admin_alert: {destination: work_group_special_topic, contents: [user_id, detected_pattern, timestamps_per_day], inline_buttons: [{label: "Восстановить", action: manual_release}]}
    release: {modes: {manual: "clear immediately", auto: "24h -> clear automatically"}, whichever_first: true, auto_release_hours: 24, rationale: "не держать честного участника из-за молчания админа"}
    re_trigger: {after_release: identical_to_first_run, sequence_counter: reset_on_release, recidivism_memory: false}
    responsibility: {block_13: "лимит + логирование (сырьё)", block_15: "анализ, решение, алерт, кнопка, авто-снятие"}
    deferred: [user_message_ethics_review, recidivism_escalation]

  # ================================================================
  step_8:
    title: "Формат логов"
    status: closed
    target_db: {engine: postgresql, version: 17, fallback: 16, reason: "insert-vacuum из коробки (XID wraparound), 5y support, VPS-friendly"}
    journals:
      issuance_log:
        purpose: "каждый факт выдачи ТЕКСТА; сырьё детектора + источник правды окна 3/24h"
        criticality: critical
        write: "synchronous, same tx as issuance"
        batching: forbidden
        append_only: true
        fields: {issuance_id: pk, participant_id: surrogate, stage: int, day: int, issued_at: timestamptz, window_seq: int, direction_hint: "enum[asc,desc,none]"}
        index: ["(participant_id, issued_at)"]
      anomaly_log:
        purpose: "срабатывания детектора Шага 7"
        criticality: critical
        write: synchronous
        batching: forbidden
        append_only: true
        fields: {anomaly_id: pk, participant_id: surrogate, detected_pattern: jsonb, action: "enum[suspension,alert,release]", release_mode: "enum[manual,auto_24h,null]", occurred_at: timestamptz}
      regeneration_log:
        purpose: "повторное построение карточки, НЕ новая выдача нового дня"
        criticality: mixed
        write: "core synchronous; verbose telemetry may be batched"
        batching: allowed_for_noncritical_telemetry_only
        append_only: true
        fields: {regen_id: pk, participant_id: surrogate, stage: int, day: int, regen_reason: "enum[re_entry,restart_recovery,re_render_after_fault]", regenerated_at: timestamptz}
        must_not_merge_with: 152_fz_access_audit
    linked_tables:
      delivery_registry: {link: "issuance_id (FK)", fields: [issuance_id, chat_id, message_id, sent_at], note: "одно из двух мест с chat_id"}
      identity_map: {fields: [participant_id, chat_id], erasure: "разрыв связки -> живая БД обезличена мгновенно"}
    immutability: {method: role_privileges, app_role: [INSERT, SELECT], revoke: [UPDATE, DELETE], maintenance_role: [DROP_PARTITION]}
    retention:
      method: "DROP time-partition (NOT row DELETE)"
      executor: "Step 5 reconciler под maintenance-ролью"
      partition_by: time
      second_guard: "мониторинг размера таблиц, ранний алерт если reconciler упал"
      volume_separation: "см. Step 5 (referenced)"
      levers:
        identity_map_retention: {duration: "SHORT — правовой блок", holds: "прямой идентификатор"}
        anonymized_logs_retention: {duration_default: "12 months", holds: "суррогат-журналы", rationale: "обезличено => не ПДн для storage-limitation => может жить дольше"}
    window_24h: {source_of_truth: issuance_log_postgresql, redis: non_critical_cache_only}
    wraparound_protection: {cause: "insert-only пропускают autovacuum -> deferred freeze -> forced stop", cure: ["PG17 insert-triggered autovacuum", "per-table autovacuum_vacuum_insert_threshold", "monitor age(relfrozenxid)"]}
    privacy_erasure:
      mechanism: "разрыв participant_id<->chat_id в identity_map"
      live_db: anonymized_instantly
      backups: {handling: acknowledged_limitation, detail: "старая связка в 3-2-1 до истечения их ретеншена; снимки не вскрываем (целостность)"}
      invariant: "erasure > identity"

  # ================================================================
  step_9:
    title: "Валидация ссылок"
    status: closed
    post_liveness_check:
      enabled: false
      reason: ["Bot API не читает чужой канал без прав админа", "Автор владеет свежестью; ссылки в конфиге гарантированы"]
      background_checker: none
      http_ping_tme: none
      freshness_owner: author
    format_validation:
      when: [config_load_on_start, config_reload]
      network: false
      checks: ["не пустое", "не плейсхолдер (TODO/dash/whitespace)", "синтаксически похоже на ссылку"]
      purpose: "поймать опечатку/обрыв до того, как участник увидит дыру"
      invariant: no_empty_screens
    on_format_failure: {crash: false, author_signal: "точное место (stage/day, поле)", log: "-> Step 8", participant_fallback: "задание без сломанного элемента / нейтральная пометка; экран не пуст", scope_guard: "одна ссылка не блокирует всё задание/бота"}
    out_of_scope: ["периодический фоновый чекер", "t.me HTTP ping / трактовка кодов", "клиентская невозможность открыть валидную ссылку -> Block 10"]

  # ================================================================
  step_10:
    title: "Fail-safe, граничные сценарии, финальная сверка"
    status: closed
    method: "FMEA / design-for-failure; каждое состояние имеет мягкий выход; фоллбэк проще заменяемого"
    edge_cases:
      crash_between_issue_and_log: "transactional atomicity (Step 8)"
      downtime_over_punishment_deadline: "reconciler re-check в пользу участника (Step 5)"
      two_bot_instances: {resolved_by: "TTL-lease + fencing (Step 5)", fencing_rule: "критичные действия проверяют актуальность лизы прямо перед записью"}
      reconciler_did_not_run: "startup alert 'reconciler не отработал' как второй контур"
      erasure_during_downtime_vs_recheck: "erasure аннулирует отложенные наказания; reconciler закрывает задачи обезличенного как неактуальные"
      partial_refund_crash: "рефанд — идемпотентная сага; reconciler докатывает в безопасном порядке (guard снят, потом удаление)"
      forever_vs_refund_deletion: "разные части ленты: оплаченное-пройденное навсегда; возвращённый Этап отозван; публичный канал не трогаем"
      legit_hit_3_24h_limit: "приостановка требует строгого сплошного обхода 2+ дня; честный участник нелинеен -> нет приостановки"
      suspension_admin_never_saw_alert: "auto-release через 24h; факт в anomaly_log"
    invariant_seams_resolved:
      erasure_vs_life: "erasure аннулирует отложенные наказания"
      refund_vs_erasure: "рефанд докатывается по суррогату; личность обезличена; сумма в обезличенном append-only денежном журнале"
      forever_vs_refund: "разные части одной ленты"
      critical_sync_vs_batching: "батчинг только для некритичной телеметрии"
      append_only_vs_retention: "DROP-партиций, не DELETE"
      no_empty_screens_vs_no_crash: mutually_reinforcing
    no_empty_screens_pass:
      config_link_defect: "задание без сломанного элемента + нейтральная пометка"
      suspension: "'Технические неполадки'"
      refunded_stage: "явная пометка 'возвращён/недоступен', не молчаливая дыра"
      during_restart: "критичные обработчики ждут / нейтральное 'загружаюсь', никогда пусто/краш"
      missing_content_broken_frame: "нейтральная заглушка + сигнал Автору"
    acknowledged_limitations:
      - "reconciler — сердце восстановления -> мониторинг критичен"
      - "erasure не трогает бэкапы до их ротации"
      - "съёмка камерой непредотвратима"
      - "точные flood-лимиты Telegram неизвестны -> реагируем (retry_after), не предсказываем"
    product_hook_non_architectural: ["финальная формулировка 'Технические неполадки' -> product copy review"]
    status_note: "Стыки Блока 15 сверены; противоречий инвариантов не найдено"

  # ================================================================
  # ЧЕК-ЛИСТ ПРОДУКТОВЫХ КРЮЧКОВ
  # ================================================================
  product_hooks_checklist:
    - id: 1
      title: "Формулировка 'Технические неполадки. Уже устраняем'"
      steps: [7, 10]
      decide: "окончательный текст при мягкой приостановке; этичность на ревью (редкое ложное срабатывание)"
      owner: product_copy
      priority: desirable_before_launch_not_blocking
      recommendation: "сохранить смысл (нейтрально, без обвинения, без раскрытия детектора), выверить тон"
    - id: 2
      title: "Срок хранения identity_map"
      steps: [8]
      decide: "сколько живёт прямой идентификатор до обезличивания; механизм заложен, число правовое"
      owner: legal_block
      priority: mandatory_before_launch
      recommendation: "короткий срок, привязанный к цели обработки, в политике"
    - id: 3
      title: "Срок хранения обезличенных логов"
      steps: [8]
      decide: "глубина хранения под детекцию; заглушка 12 месяцев"
      owner: [legal_block, product]
      priority: desirable_before_launch
      recommendation: "12 мес как старт, скорректировать по факту"
    - id: 4
      title: "Тексты нейтральных заглушек 'нет пустых экранов'"
      steps: [9, 10]
      decide: "формулировки: дефект ссылки, отсутствие контента, 'загружаюсь', 'возвращён/недоступен'"
      owner: product_copy
      priority: desirable_before_launch
      recommendation: "единый спокойный тон без техножаргона"
    - id: 5
      title: "Пометка 'возвращён/недоступен' у отозванного при рефанде Этапа"
      steps: [10]
      decide: "визуальная форма и текст пометки; механика есть"
      owner: product
      priority: desirable_before_launch
      recommendation: "явная, не пугающая формулировка про отзыв доступа из-за возврата"
    - id: 6
      title: "Целевая версия PostgreSQL 17 в окружении VPS"
      steps: [8]
      decide: "подтвердить доступность PG 17 у провайдера/в репозитории (иначе фоллбэк 16)"
      owner: infrastructure
      priority: mandatory_before_deployment
      recommendation: "проверить 17 в PGDG до старта, иначе зафиксировать 16"
    - id: 7
      title: "Пороги мониторинга и алертов"
      steps: [5, 8, 10]
      decide: "числа: бэкап > 24ч, диск/pg_wal, размер журнальных таблиц, heartbeat, 'reconciler не отработал'"
      owner: operations
      priority: mandatory_before_launch
      recommendation: "старт с рекомендованных (бэкап > 24ч, диск > 80%), калибровать по факту"
    priority_summary:
      mandatory_before_launch: [2, 6, 7]
      desirable_not_blocking: [1, 3, 4, 5]
      note: "все семь — доводка поверх готовой структуры; ни один не требует пересмотра архитектуры Блока 15"

  # ================================================================
  final_status:
    steps_closed: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    architecture: frozen
    invariants_check: "взаимно непротиворечивы; проверено в Шаге 10"
    coverage: [partial_failure, crash_restart, idempotency, recovery_asymmetry, durability, anti_piracy, anomaly_detection, log_format, erasure, no_empty_screens]
    open_questions: []
```

## YAML дополнения (монолит дополнения, без нарезки)

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
