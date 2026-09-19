---
file: 17/17-99-yaml-full.md
block: 17
part: "99"
title: "Единый YAML-контракт block_17"
status: закрыт (v3.4)
doc_version: "consolidated v3 + патч v3.4"
contains: [полный YAML-контракт block_17, перенос дословный из исходника]
---

> **Переопределено/уточнено ERRATA-UNIFIED и OVERRIDES.** Этот файл — часть Блока 17, нормы которого перекрываются нормативным стеком (`И1 → И2 → И3 → И4 → Б17 → SEAM-PATCH-1 → ERRATA-UNIFIED`). При парсинге YAML применяются машиночитаемые переопределения: [../normative/OVERRIDES.yaml](../normative/OVERRIDES.yaml) (E1, E2, E4, FIX1, R477_TARGET, N02 и др.). Единый список открытых несовместимостей — [../normative/README.md](../normative/README.md), раздел «Открытые несовместимости». Правило чтения — [../CANONICAL-SOURCES.md](../CANONICAL-SOURCES.md).

# Блок 17 — Часть 99. Единый YAML-контракт `block_17`

> Источник — [../17-author-panel.md](../17-author-panel.md), раздел
> «ЕДИНЫЙ YAML-КОНТРАКТ БЛОКА 17». Перенос **дословный**, без сокращений и переформатирования.
> Исполняемая форма реестра команд — [../build/bot-commands-registry.yaml](../build/bot-commands-registry.yaml).

```yaml
block_17:
  name: "Панель Автора / командный режим"
  version: v3.3
  role: executor
  principle: "Б10 просит — владелец исполняет (расширено на все домены)"

  roles_final:
    owner:
      count_expected: 2
      access: [read_ops, moderation_ops, financial_ops, privacy_ops, admin_ops, ban_ops, mute_ops]
      card_view: owner_full
    moderator:
      access: [read_ops_reduced, moderation_ops_reduced, mute_ops]
      moderation_ops_reduced:
        includes: [life_plus, life_minus, pause, unpause, unpause_user, approve, revert, message_via_bot, mute, unmute]
        excludes: [pause_grant, set_shadow, unshadow, block, unblock, confirm_payment, reject_payment, refund, legal_view, audit_view, admin_ops]
      card_view: moderator_reduced
    finance:
      access: [read_ops_financial, financial_ops]
      financial_ops: [confirm_payment, reject_payment, refund]
      excludes: [moderation_ops, mute_ops, legal_view, audit_view, admin_ops, block, unblock, set_shadow, unshadow, pause_grant]
      card_view: finance_financial
    partner_deprecated: true

  whitelist:
    schema: {tg_user_id, role, added_by, added_at}
    gate_on: [reply_cmd, button_shortcut, callback, info_only_view]
    non_whitelisted: {action: ignore, notify_user: false, audit: true}
    cache:
      miss_policy: force_read_db_then_deny
      db_timeout_s: 3
      bootstrap_fallback: enabled
    min_owner_invariant: 1                     # NR-17.1
    mgmt:
      executor: single_owner
      co_confirmation: false
      peer_broadcast: mandatory
      broadcast_channel: admin_topic
      broadcast_policy: {delete: forbidden, edit: forbidden, mirror_to: b14_durable}
      weekly_digest_to: [owner_all]
      on_broadcast_delivery_fail: rollback_via_compensation

  bootstrap_mode:
    trigger: cache_and_db_miss
    source: durable_signed_bootstrap_file       # Б14/Б15
    contains: [owner_ids_max_2, signature, version]
    allowed_ops: [read_ops, admin_add]
    denied_ops: all_destructive                # NR-17.10
    alert_on_enter_exit: [owner_all]
    local_audit: durable_sync_on_recovery

  banning_invariant:
    NR_17_14: "БОТ НИКОГДА НЕ БАНИТ УЧАСТНИКА. Банит и разбанивает ТОЛЬКО owner."
    who_can_block: [owner]
    who_can_unblock: [owner]
    # Р477 (И2): состояния banned_* из FSM удалены — запрет ниже сохранён как исторический инвариант
    forbidden_auto_transitions_to: [banned_soft, banned_hard]
    allowed_auto_states: [sleeping, erased_by_b15, muted]
    auto_ban_attempt_policy:
      execute: false
      audit_event: auto_ban_blocked
      alert_owners: mandatory
      router_hard_reject: true
    escalation_when_ban_needed:
      auto_action: notify_owners
      message: "требуется решение о блокировке участника X, причина Y"
      decision_by: owner
      decision_via: /block
    domain_translations:
      lives_exhausted_b2: sleeping
      payment_missed_b16: sleeping
      reflection_incident_b7: sleeping_or_reject
      group_flood_b8: muted
      group_spam_b8: muted
      storage_expired_b15: erased

  muted_state:
    kind: temporary_group_emission_off
    is_ban: false
    setter: [auto_antiflood, auto_antispam, moderator, owner]
    unsetter: [moderator, owner]
    does_not_affect: [course_access, lives, payment, reflections]
    escalation_path: "moderator/owner может эскалировать до /block (решает owner)"

  pauses:
    types:
      user_pause:   {setter: participant, consumes_quota: true}
      author_pause: {setter: owner_moderator, consumes_quota: false}
      pause_shadow: {setter: auto_b7_or_owner_manual, visible_to_participant: false}
    unpause_user:
      quota_policy: preserve_remainder
      cooldown_after_force_unpause: none
      ux_confirm_note: "у участника остаётся X дней квоты паузы"
      cycle_prevention_owner: b2
    set_shadow:
      role_required: owner
      two_step: true
      reason: {required: true, source: fixed_code_list_from_b7, free_text: forbidden}
      peer_broadcast: mandatory
      disclaimer_on_confirm: "тайная пауза скрыта от участника; исключительная мера"
      auto_setter_still_allowed_by_b7: true
    unshadow:
      role_required: owner
      two_step: true

  commands:
    revert:          {domain: b7,  button: "↩ Revert",          params: [day?],           irreversible: true,  two_step: true,  scope: participant}
    life_plus:       {domain: b2,  button: "❤️ +Жизнь",          params: [reason?],        irreversible: true,  two_step: true,  scope: participant, expected: [lives]}
    life_minus:      {domain: b2,  button: "💔 −Жизнь",          params: [reason?],        irreversible: true,  two_step: true,  scope: participant, expected: [lives]}
    pause:           {domain: b2,  button: "⏸ Пауза",            params: [],               irreversible: true,  two_step: true,  scope: participant}
    unpause:         {domain: b2,  button: "▶️ Снять паузу",     params: [],               irreversible: true,  two_step: true,  scope: participant, targets: author_pause}
    unpause_user:    {domain: b2,  button: "▶️ Снять user_pause",params: [],               irreversible: true,  two_step: true,  scope: participant, targets: user_pause, quota: preserve}
    pause_grant:     {domain: b2,  button: "➕ Доп.пауза",       params: [grant_no, reason], irreversible: true, two_step: true, scope: participant, role: owner_only, expected: [pause_state]}
    set_shadow:      {domain: b7,  button: "🕶 Тайная пауза",    params: [reason_code!],   irreversible: true,  two_step: true,  scope: participant, role: owner_only, peer_broadcast: true}
    unshadow:        {domain: b7,  button: "☀ Снять shadow",     params: [],               irreversible: true,  two_step: true,  scope: participant, role: owner_only}
    approve:         {domain: b7,  button: "✅ Зачесть рефлексию", params: [],             irreversible: true,  two_step: true,  scope: participant, expected: [reflection_id, verdict_version=pending]}
    confirm_payment: {domain: b16, button: "✅ Подтвердить",       params: [],             irreversible: true,  two_step: true,  scope: participant, expected: [payment_id, status]}
    reject_payment:  {domain: b16, button: "✖ Отклонить",          params: [reason],       irreversible: true,  two_step: true,  scope: participant, expected: [payment_id, status]}
    refund:          {domain: b16, button: "↩️ Refund",            params: [reason!],      irreversible: true,  two_step: true,  scope: participant, saga: true, idempotency: one_shot, expected: [payment_id=confirmed]}
    block:           {domain: b10, button: "🔒",                   params: [reason?],      irreversible: true,  two_step: true,  scope: participant, role: owner_only}
    unblock:         {domain: b10, button: "🔓",                   params: [mode: restore|fresh], irreversible: true, two_step: true, scope: participant, role: owner_only, expected: [ban_mod, window_open]}
    mute:            {domain: b8,  button: "🔇",                   params: [duration?],    irreversible: false, two_step: false, scope: participant}
    unmute:          {domain: b8,  button: "🔊",                   params: [],             irreversible: false, two_step: false, scope: participant}
    card:            {domain: b6,  button: "📇 Карточка",           read_only: true,       two_step: false, scope: participant, view_profile_by_role: true}
    legal:           {domain: legal, button: "⚖️ Юр.данные",        read_only: true,       two_step: false, scope: participant, role: owner_only}
    message_via_bot: {domain: b8,  button: "✉️",                   params: [text!],        irreversible: after_send, two_step: preview_confirm, scope: participant, shadow_lint: true}
    graph:           {domain: b7,  button: null,                   params: [window: 7|14], read_only: true,   two_step: false, scope: cohort}
    audit:           {domain: b14, params: [participant_id?],      read_only: true,        two_step: false, scope: participant_or_global, role: owner_only, self_log: true}
    admin_add:       {domain: b17, params: [tg_id, role],          irreversible: true,     two_step: true,  scope: global, role: owner_only, peer_broadcast: true}
    admin_remove:    {domain: b17, params: [tg_id],                irreversible: true,     two_step: true,  scope: global, role: owner_only, peer_broadcast: true, guard: min_owner_1}
    admin_role:      {domain: b17, params: [tg_id, role],          irreversible: true,     two_step: true,  scope: global, role: owner_only, peer_broadcast: true, guard: min_owner_1}

  removed_forever:
    place:
      status: removed_v3_1
      router_policy: hard_reject
      legacy_callback_prefix: "place_*"
      on_attempt: {execute: false, audit: place_attempted, notify_group: v3_1_reminder}

  input_hybrid:
    buttons_for: [frequent_simple]
    reply_cmd_for: [parametric, rare]
    button_binds_participant_from: message_context
    reply_without_target: {execute: false, hint: "укажите участника (reply)"}

  wizard:
    stages: [confirm_participant_if_scope_participant, params, two_step_confirm]
    timeout_min: 10
    on_timeout: {execute: false, audit: dialog_timeout}
    concurrency: one_active_per {actor_id, cmd, participant_id}
    per_participant_advisory_lock: {ttl_min: 10, heartbeat: true, applies_to: destructive_ops}
    owner_preempt: {command: "⛔ Перехватить", two_step: true, audit: wizard_preempted_by_owner}
    callback_payload: {cmd, participant_id, dialog_id, step, schema_version, nonce}

  two_step_confirm:
    required_when: [irreversible, money, lives, privilege_change, ban_ops]
    yes_button_position: "not_at_first_button_slot"
    on_state_change_between_steps:
      restore_fresh_downgrade: new_confirm_screen        # NR-17.4
      stale_expected: {execute: false, audit: stale_state_reject}   # NR-17.3
    read_only_actions: one_tap
    post_execute_ui: disable_buttons_edit_message

  idempotency:
    one_shot_ops: [refund, admin_remove, admin_role, pause_grant]
    one_shot_key: "hash(actor_id, cmd, resource_id)"        # params EXCLUDED
    repeatable_key: "hash(actor_id, cmd, participant_id, dialog_id)"
    ttl_financial_h: 24
    ttl_other_h: 1
    repeat_within_ttl: returns_previous_result
    storage: b14_durable

  refund_saga:
    coordinator: b16
    steps:
      - {block: b16, action: "payment: confirmed -> refund_pending"}
      - {block: b10, action: "state -> sleeping"}
      - {block: b13, action: "revoke_access_to_completed_materials"}
      - {block: b15, action: "physical_delete_personal_artifacts", timeout_h: 24}
      - {block: b16, action: "payment: refund_pending -> refunded"}
    ui_cascade_disclosure_required: true
    partial_failure_status: pending_ops_review              # NR-17.7
    auto_rollback_of_steps_1_2: false
    manual_resolution_by: owner
    idempotent_resume: true

  refund_when_banned:
    # Р477 (И2): состояний banned_* в FSM нет — две строки ниже читаются как sleeping + author_pause
    banned_soft: allowed_with_warning
    banned_hard: allowed_with_warning
    erased: hard_reject
    warning_text: "участник забанен; деньги вернутся, доступ к курсу не восстановится"
    retention_debt: [b15, b16]

  approve_revert_semantics:
    approve_button_label: "✅ Зачесть рефлексию"
    approve_writes: "verdict: pending -> approved (b7.6)"
    approve_does_not_apply_pass: true
    pass_applies_at: b7.7
    revert_window: "до применения перехода Дня 14 (b7.7)"
    after_pass_applied:
      revert_ui: hidden_with_plate "День уже перевыдан"
      day_rollback: debt_b7

  message_via_bot_gate:
    active:        OK
    user_pause:    OK
    author_pause:  OK
    sleeping:      WARN
    # Р477 (И2): состояний banned_* в FSM нет — две строки ниже читаются как sleeping + author_pause
    banned_soft:   WARN
    banned_hard:   {block: true, audit: send_blocked_hard_ban}
    erased:        {block: true, audit: send_blocked_erased}
    pause_shadow:  {allow: true, lint_disclosure: true, ack_required: shadow_disclosure_ack}
    idempotency: single_send
    audit_body: hash_only

  reject_new_receipt_flow:
    on_reject: {status: rejected, ui: disable_buttons}
    on_new_receipt: {new_card: true, new_payment_id: true, link_to_previous: "предыдущая попытка отклонена <ts>, причина X"}
    two_receipts_independent: true

  card_view_profiles:
    owner_full: {shows: all}
    moderator_reduced:
      hides: [sensitive_health, pause_shadow]
      replaces_with: "⚖ Данные закрыты. Обратитесь к owner"
    finance_financial:
      shows: [payments, payment_status, access_active, course_start_date]
      hides: [lives, reflections, pauses_details, pause_shadow, sensitive_health]
      shows_flag: "участник неактивен по не-финансовой причине (без деталей)"

  command_role_matrix:
    read:
      card_owner:      [owner]
      card_reduced:    [owner, moderator]
      card_financial:  [owner, finance]
      legal:           [owner]
      graph:           [owner, moderator]
      audit:           [owner]
    moderation:
      life_plus:       [owner, moderator]
      life_minus:      [owner, moderator]
      pause:           [owner, moderator]
      unpause:         [owner, moderator]
      unpause_user:    [owner, moderator]
      approve:         [owner, moderator]
      revert:          [owner, moderator]
      message_via_bot: [owner, moderator]
    privileged_moderation:
      pause_grant:     [owner]
      set_shadow:      [owner]
      unshadow:        [owner]
    finance:
      confirm_payment: [owner, finance]
      reject_payment:  [owner, finance]
      refund:          [owner, finance]
    lifecycle_ban:
      block:           [owner]
      unblock:         [owner]
    group_moderation:
      mute:            [owner, moderator, auto]
      unmute:          [owner, moderator]
    admin:
      admin_add:       [owner]
      admin_remove:    [owner]
      admin_role:      [owner]
    on_role_denied:
      execute: false
      ui_render: hidden_button
      audit_event: role_denied

  audit:
    operational:
      schema: {ts_server, actor_id, actor_role, cmd, participant_id, params, dialog_id, decision, reason, operation_key, schema_version, compensates?}
      decisions: [executed, rejected, ignored, stale_state_reject, dialog_timeout, place_attempted, role_denied, auto_ban_blocked, wizard_preempted_by_owner, send_blocked_hard_ban, send_blocked_erased]
      retention: forever
      transaction: same_as_state_change              # Р429
    privacy_152fz:
      schema: {ts, actor_id, participant_id, view}
      views: [card_owner, card_reduced, card_financial, legal, graph, full_change_map]
      retention: forever
      backpressure: block_view_on_queue_overflow
    audit_read_cmd:
      name: /audit
      access: owner
      self_log: true
    peer_visibility:
      destructive_ops_broadcast: admin_topic
      format: "<actor> · <cmd> · <participant> · <decision>"
    weekly_digest:
      to: owner_all
      contents: [admin_actions_7d_summary_by_class]

  compensation_model:
    rollback_supported: false
    undo_via: semantic_inverse_operation
    audit_link_field: "compensates: <original_operation_key>"
    pairs:
      life_minus: life_plus
      revert: approve_within_b7_7
      block: unblock_restore_if_window_open
      admin_remove: admin_add
      refund_finalized: manual_reissue    # долг Б16
      message_sent: none_apology_only

  atomicity_delegation:
    lives: {block: b2, method: SELECT_FOR_UPDATE, bounds: [0, 3]}
    payment: {block: b16, method: one_shot_refund}
    revert: {block: b7, method: serialized_by_operation_key}
    pause_grant: {block: b2, method: check_then_grant}
    unban: {block: b10, method: window_check_then_mode, no_silent_downgrade: true}

  interfaces_out:
    to_b2:  [life_ops, pause_ops, unpause_user, pause_grant]
    to_b6:  [card_render_by_view_profile, action_buttons_bind]
    to_b7:  [revert, approve, set_shadow, unshadow, graph_render_cohort]
    to_b8:  [message_via_bot, mute, unmute, admin_topic_publish]
    to_b9:  [wizard_timeout_notice, peer_alerts, escalation_ban_request, weekly_digest]
    to_b10: [block_owner_only, unblock_restore_or_fresh_owner_only]
    to_b13: [saga_revoke_access]
    to_b14: [operational_audit, privacy_audit, idempotency_keys, advisory_locks, admin_topic_mirror, bootstrap_file]
    to_b15: [erased_flag_contract, refund_recipient_retention]
    to_b16: [confirm_payment, reject_payment, refund_saga_coordinator]
    to_legal: [legal_view]

  boundaries:
    owns: [command_catalog, button_shortcuts, wizard_ux, whitelist_gate, roles_model, roles_matrix, audit_of_calls, idempotency_wrapper, bootstrap_mode]
    executes_only: [b2_rules, b7_rules, b10_rules, b16_rules, b6_render_rules, b8_group_rules, legal_storage_rules]
    does_not: [introduce_business_rules, restore_place, direct_write_to_participant_domain_state, allow_auto_ban]

  nr_invariants:
    NR_17_1:  "whitelist has >=1 owner"
    NR_17_2:  "participant_id from confirm-step callback only"
    NR_17_3:  "state change requires expected_* match"
    NR_17_4:  "no silent downgrade of irreversible ops"
    NR_17_5:  "/place never restored"
    NR_17_6:  "whitelist mgmt requires peer_broadcast to admin_topic"
    NR_17_7:  "refund saga partial failure => pending_ops_review, no auto rollback of steps 1-2"
    NR_17_8:  "unpause_user preserves user_pause quota; cycle rule owned by b2"
    NR_17_9:  "message_via_bot on pause_shadow requires shadow_disclosure_ack"
    NR_17_10: "bootstrap mode allows only read_ops and admin_add"
    NR_17_11: "undo = compensating action; rollback never"
    NR_17_12: "broadcast in same transaction as audit write"
    NR_17_13: "partner role deprecated; final composition = owner x2 + moderator + finance"
    NR_17_14: "БОТ НИКОГДА НЕ БАНИТ. Банит только owner. Автомат допускает только sleeping/erased/muted"
    NR_17_15: "whitelist and set_shadow broadcasts are not deletable by initiator"
    NR_17_16: "unblock owner-only (symmetry with block)"
    NR_17_17: "finance never sees pause_shadow"

block_17_patch:
  version: v3.4
  supersedes_fragments: [callback_payload_v3_3, refund_saga_steps_v3_3, matrix_approve_shadow_v3_3]

  callback_payload_redesign:
    NR_17_19: "callback_data ≤ 64 байта; состояние мастера в durable-хранилище"
    payload_in_button: {dialog_id_short: "12-16 base62", step: "1 byte", nonce: "4 bytes"}
    payload_max_bytes: 22
    stored_in_durable_state: [cmd, participant_id, actor_id, params, schema_version, expected_state]
    state_storage: {backend: redis_or_pg, key: dialog_id, ttl: wizard_ttl + margin}
    on_dialog_id_not_found: {execute: false, ui: "Мастер устарел или отменён", audit: dialog_expired}
    security_side_effect: "participant_id и cmd физически не в payload — исключает подмену"

  html_sanitizer_message_via_bot:
    NR_17_20: "ввод в write_via_bot проходит через санитайзер Б9 перед предпросмотром"
    stage: before_preview
    owner_of_sanitizer: b9
    escape: ["<", ">", "&"]
    preserve_allowed_tags: by_b9_allowlist
    on_unparseable_html:
      preview_warning: true
      offer_switch_to_plaintext: true
      block_send_until_resolved: true
    guarantee: "мастер не зависает; либо санированный текст, либо явный отказ с диагностикой"

  forum_topic_binding:
    NR_17_21: "форум-темы Б8 адресуются через alias→thread_id маппинг"
    topic_bindings_source: durable_config
    known_aliases: [admin_topic, ...]
    bind_topic_cmd:
      role: owner
      trigger: reply_on_message_in_topic
      two_step_when: rebinding_existing_alias
    fallback_when_admin_topic_unbound:
      broadcasts_go_to: [owner_pm_all]
      system_alert: "admin_topic не привязан, привяжите через /bind_topic admin_topic"
    hardcoded_thread_id_in_yaml: forbidden

  refund_saga_v3_4:
    NR_17_22: "preflight-заморозка выдачи ДО перевода платежа"
    steps:
      - {step: 0, block: b17_coordinator, action: "atomically set visibility=out_of_scope AND modifier=freeze_refund on participant"}
      - {step: 1, block: b16, action: "payment: confirmed -> refund_pending"}
      - {step: 2, block: b10, action: "state -> sleeping"}
      - {step: 3, block: b13, action: "revoke_access_to_completed_materials"}
      - {step: 4, block: b15, action: "physical_delete_personal_artifacts", timeout_h: 24}
      - {step: 5, block: b16, action: "payment: refund_pending -> refunded"}
    sweeper_guard_contract:
      readers: [b15, b16, b10_dispatchers]
      must_check: [visibility, modifier]
      on_flag_set: {emit_content: false, accrue: false, audit: sweeper_blocked_by_refund_freeze}
    flags_cleared_when: [refunded, manual_rollback_from_pending_ops_review]
    partial_failure_status: pending_ops_review

  panic_mode:
    NR_17_23: "panic обходит whitelist-кэш; unpanic требует passphrase"
    panic_maintenance:
      role: owner
      two_step: false
      confirmation_field: tg_username_of_initiator
      bypasses_cache: true
      effects: [maintenance_flag_on, webhook_off, broadcast_T1_MAINT_via_b9]
      broadcast_to_admin_topic: mandatory
      audit_event: panic_activated
    unpanic:
      role: owner
      requires_passphrase: true
      passphrase_source: durable_bootstrap_file
      broadcast_to_admin_topic: mandatory
      audit_event: panic_lifted_by

  new_commands_v3_4:
    miniapp_toggle:      {domain: b14, scope: global_or_cohort, role: owner_only, params: [target, on|off, reason], two_step: true, stub_awaiting_b14: true}
    miniapp_stats:       {domain: b14, scope: global_or_cohort, role: owner_only, read_only: true, stub_awaiting_b14: true}
    force_sync:          {domain: b14, scope: participant,      role: owner_only, params: [pid], two_step: true, stub_awaiting_b14: true}
    unfreeze_piracy:     {domain: b15, scope: participant,      role: owner_only, params: [pid, reason!], two_step: true, effects: [reset_is_suspended, reset_anomaly_log_status], stub_awaiting_b15: true}
    override_baseline:   {domain: b14, scope: participant,      role: owner_only, params: [pid, metric, value, reason!], two_step: true, privacy_audit_view: baseline_override, side_effect: invalidate_b14_cache, stub_awaiting_b14: true}
    publish_stage:       {domain: b14, scope: global,           role: owner_only, params: [stage_id], two_step: true, effects: [emit_publish_epoch], peer_broadcast: mandatory, stub_awaiting_b14: true}
    withdraw_stage:      {domain: b14, scope: global,           role: owner_only, params: [stage_id, reason], two_step: true, effects: [emit_publish_epoch_withdraw], peer_broadcast: mandatory, stub_awaiting_b14: true}
    dlq_view:            {domain: b15, scope: global,           role: owner_only, read_only: true, params: [reason?], stub_awaiting_b15: true}
    dlq_replay:          {domain: b15, scope: dlq_item,         role: owner_only, params: [dlq_id, reason!], two_step: true, idempotency: one_shot_by_dlq_id, audit_link: "compensates: original_op_key", stub_awaiting_b15: true}
    finance_summary:     {domain: b16, scope: global_or_cohort, role: [owner, finance], read_only: true, params: [period?]}
    bind_topic:          {domain: b8,  scope: config,           role: owner_only, params: [alias], trigger: reply_on_topic, two_step_when: rebinding_existing, stub_awaiting_b8: false}
    panic_maintenance:   {domain: b17, scope: global,           role: owner_only, two_step: false, confirmation_field: tg_username_of_initiator, bypasses_cache: true}
    unpanic:             {domain: b17, scope: global,           role: owner_only, params: [passphrase!], peer_broadcast: mandatory}

  matrix_command_state_delta:
    approve_x_pause_shadow: {from: WARN, to: OK, reason: "штатный выход из pause_shadow(no_verdict)"}
    revert_x_pause_shadow:  {from: WARN, to: OK, reason: "штатный откат вердикта в том же состоянии"}

  role_matrix_delta:
    miniapp_toggle: [owner]
    miniapp_stats: [owner]
    force_sync: [owner]
    unfreeze_piracy: [owner]
    override_baseline: [owner]
    publish_stage: [owner]
    withdraw_stage: [owner]
    dlq_view: [owner]
    dlq_replay: [owner]
    finance_summary: [owner, finance]
    bind_topic: [owner]
    panic_maintenance: [owner]
    unpanic: [owner]

  b17_does_not_invent_rule:
    principle: "если владелец не финализировал контракт — обёртка помечена stub_awaiting_<block>"
    stub_audit_decision: stub_not_ready

  new_nr_invariants:
    NR_17_18: "управление Mini App feature flags — только owner"
    NR_17_19: "callback_data ≤ 64 байта; состояние мастера — в durable-хранилище"
    NR_17_20: "ввод в write_via_bot санируется Б9 перед предпросмотром"
    NR_17_21: "форум-темы через alias→thread_id, хардкод запрещён"
    NR_17_22: "refund preflight-freeze выдачи ДО перевода платежа"
    NR_17_23: "panic обходит whitelist-кэш; unpanic требует passphrase из bootstrap"
```
