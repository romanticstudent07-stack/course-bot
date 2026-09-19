---
file: 99/99-03-yaml-v2ext.md
block: 99
part: "03"
title: "Юридический блок — YAML-контракт legal_block_v2ext_patch_rebuilt"
status: канон (старшая редакция блока)
doc_version: "consolidated v3"
contains: [yaml v2-ext-r, invariants_final, risks_accepted_by_operator, softened_from_v2]
---

# YAML-КОНТРАКТ БЛОКА — v2-ext-r

> Старшая редакция юрблока: при расхождении с [99/00-digest.md](99-00-digest.md) и [99/02-yaml-v1.md](99-02-yaml-v1.md) побеждает этот файл. Ключ `depends_on` ссылается на артефакт `legal_block_v2_patch`, которого в исходнике нет (в прозе ему соответствует [99/01-patch-v2.md](99-01-patch-v2.md)) — висячая зависимость, см. открытые вопросы в [99-legal.md](../99-legal.md).

```yaml
artifact: legal_block_v2ext_patch_rebuilt
file_under: {block: Legal, node: root, outcome: PATCH-ON-v2, version: v2-ext-r}
depends_on: [legal_block_v1, legal_block_v2_patch]
owner: legal_block
verified_by: legal_block
supersedes: legal_block_v2ext_patch

# === ПРОФИЛЬ ПРОДУКТА ===
product_profile:
  nature: educational_and_informational
  service_naming: "информационно-консультационные образовательные услуги в области wellness и самооценки самочувствия"
  operator_disclaimer_verbatim: |
    Курс носит исключительно образовательный и ознакомительный характер.
    Программа не является медицинской консультацией, постановкой диагноза или планом лечения.
    Автор и кураторы курса не несут ответственности за любые прямые или косвенные последствия,
    возникшие в результате использования материалов курса.
  quality_conditions_for_non_medical_classification:
    - offer_explicitly_educational
    - no_individual_recommendations_under_specific_diagnosis
    - terminology_blacklist_enforced_in_offer_bot_marketing
  fz323_license_required: false  # при выполнении всех трёх условий выше
  medical_review_by_doctor: recommended_not_mandatory

# === ОПЕРАТОР ===
operator_status:
  form: self_employed_npd
  requisites_available: [full_name, inn]
  requisites_absent: [ogrn, ogrnip]
  templates_note: "поля ОГРН/ОГРНИП помечаются 'не применяется для НПД'"
  yearly_cap_rub: 2_400_000
  soft_stop_at_pct: 80
  hard_stop_at_cap: true
  on_hard_stop: [block_new_payments, offer_migration_to_ip_usn, offer_refund_by_art32]
  npd_receipt_deadline: "не позднее 9-го числа месяца, следующего за месяцем дохода"
  labor_hire_of_individuals: forbidden
  helpers_only_ip_or_npd_gph: true
  npd_ex_employer_2y_lockout: enforced

data_protection_responsible:
  role: author_self_appointed
  self_appointment_order_required: true
  minimal_docs_pack_for_self_employed:      # смягчено: 4 документа, не 7
    - policy_pdn_public
    - regulation_pdn_internal
    - order_appointing_responsible_person
    - subject_requests_journal
  removed_from_mandatory_for_this_scale:    # переведено в опциональное на текущем масштабе
    - list_of_ispdn
    - threat_model_formal_document
    - incident_response_written_instruction  # заменяется коротким playbook в reg-архиве
    - media_journal
  rkn_notification_before_start: required
  changes_notify_within_business_days: 15

# === ИНФРА / ПДн ===
infra_state:
  current: local_test_server_ru_underpowered
  real_pdn_on_current: forbidden  # только синтетика
  own_ispdn_attestation: not_required   # ← смягчено, см. rationale
  own_ispdn_attestation_rationale: >
    ПДн размещаются в аттестованном сегменте облачного провайдера,
    аттестат провайдера покрывает требования УЗ; собственная аттестация оператору-самозанятому не требуется.
  provider_selection:
    primary_candidate: yandex_cloud
    fallback_candidate: timeweb_cloud_152fz
    excluded: [reg_ru, own_server_for_prod, foreign_providers]
    decision_deadline: "до первой платной когорты"
  uz_level_target: UZ-3           # ← смягчено с УЗ-2, обоснование ниже
  uz_level_rationale: >
    Модель угроз 3-го типа: не актуальны угрозы, связанные с недекларированными
    возможностями системного и прикладного ПО; спец.категория здоровья < 100 тыс. субъектов → УЗ-3 по ПП №1119.
  encryption_baseline:            # ← смягчено
    provider_at_rest_encryption: relied_upon
    tls_in_transit: required
    photo_s3_sse_kms: required
    application_level_encryption: recommended_not_mandatory
    crypto_shredding: recommended_not_mandatory
    escalate_to_ale_when: "когорта > 1000 участников ИЛИ появление бюджета"
  fsb_378_szki_by_operator: not_required   # ← смягчено, полагаемся на провайдера
  localization_ru: required

# === СОГЛАСИЯ ===
consents:
  C1: {kind: contract, blocking: true, includes_tg_meta: true}
  C2: {kind: health_special_category, blocking: true, gates: [checkup_start, measurements]}
  C3: {kind: photo, blocking: false, on_refuse: hide_photo_layer}
  C4: {kind: marketing, blocking: false, unsubscribe_in_each_broadcast: required}
  C5: {kind: cross_border_transfer, default: absent, requested: false}
  C6: {kind: reflections_research_use, blocking: false, on_refuse: drop_at_lifecycle_end}
  consent_text_dynamic_requisites:
    - operator_full_name
    - operator_status_self_employed
    - inn
    - registration_address
    - contact_email
    - purpose
    - categories_of_data
    - retention_period
    - withdrawal_procedure
  consent_logging: {immutable: true, append_only: true, access_via: command_legal_data}

c2_withdrawal_midcourse:
  effect: [pause_course, offer_refund_by_art32_with_fpr]

# === RED FLAGS (упрощено под механику "тема в Telegram-группе Автора") ===
red_flags_protocol:
  scan_targets: [reflections, checkup_answers, support_messages]
  trigger_categories:
    - suicide_self_harm
    - oncology
    - eating_disorder
    - domestic_violence
    - pregnancy_or_planning
    - acute_pain
  on_trigger_within_seconds: 60
  simultaneous_actions:                       # ключевое: одновременно, не последовательно
    to_participant:
      - set_course_state: sleeping
      - send_emergency_template
    to_author:
      - alert_in_dedicated_topic_in_authors_telegram_group
      - alert_context_included: [participant_pseudonym, matched_category, timestamp, quote_snippet_if_allowed]
  human_reaction_by_author:
    sla_hours_reference: 24              # ориентир, не жёсткая гарантия
    formulation_in_offer: "в разумный срок"
    escalation_on_miss: none_configured_solo_operator   # ← Автор один
    author_decisions: [resume, keep_paused, initiate_refund_art32, escalate_to_specialist]
  logging:
    trigger_log: append_only
    author_reaction_log: append_only
  bot_scope: escalate_only_no_severity_assessment
  emergency_contacts_ru:
    - "112"
    - "Ясное утро (онко): 8-800-100-0191"
    - "Телефон доверия: 8-800-2000-122"
    - "Профильный специалист (для беременности — акушер-гинеколог)"
  legal_risk_addressed:
    - "ст.125 УК: снимается доказуемой мгновенной реакцией бота + append-only логом реакции Автора"
    - "гражданский иск: снимается append-only логом"
  note: "прямого норматива SLA нет; 24ч — индустриальный разумный срок"

# === РЕЗЕРВНЫЙ КАНАЛ ===
backup_channel:
  email:
    status: recommended_not_mandatory
    collected_at: onboarding
    confirmation_by_link: required
    absence_blocks_payment: false           # ← ключевое смягчение
    trigger_for_email_duplication: "подтверждённая недоступность Telegram > 24ч"
    duplicate_within_hours_after_trigger: 72
    who_gets_duplicate: "только участники с подтверждённым e-mail"
    who_gets_material_later: "участники без e-mail — после восстановления Telegram или запуска резервного бота"
  strategic_reserve_bot:
    status: future_work
    platform_candidates: [max, vk]
    obligation_in_offer_wording: "в разумный срок"   # без числа
  forbidden_channels: [whatsapp, signal, discord]

# === ОФЕРТА / ВОЗВРАТЫ ===
offer_mandatory_requisites:
  - operator_full_name
  - operator_status: self_employed
  - inn
  - registration_address
  - contact_channels
  - service_name: "информационно-консультационные образовательные услуги в области wellness и самооценки самочувствия"
  - price_and_change_clause
  - payment_and_fiscalization
  - term_and_delivery_method
  - refunds_section
  - non_medical_and_non_device_disclaimer_verbatim
  - pdn_processing_and_consents_link
  - offer_amendments
  - claims_procedure: {channel: email, response_days: 10}
  - jurisdiction: "по правилам ст.17 ЗоЗПП"
  - anti_piracy_clause: {ref: "ст.450 ГК", limitation: "удержание в пределах ФПР"}
  - ugc_license_clause
  - force_majeure_telegram_clause

refunds:
  applicable_norms:
    art_32_zozpp: "право отказа в любое время, удержание ФПР"
    art_31_zozpp: "срок исполнения требования — 10 дней"
    art_26_1_zozpp: "касается товаров, в оферте курса не заявляется"
  before_stage_start: "100%"
  in_progress: "pro_rata_by_stage_progress"
  defective_service: "100%"
  minor_refund: "100% + refund_stitch_block_16_legal"
  minor_refund_initiators: [participant, legal_representative]
  processing_deadline_days: 10

service_acceptance_presumption:
  rule: "услуга по выданному дню Этапа считается фактически оказанной, если в течение 3 дней после выдачи не поступил мотивированный отказ через Поддержку"
  overrides_art32: false
  log: append_only

ugc_license:
  type: simple_nonexclusive
  gratuitous: allowed_from_individual_to_operator
  scope:
    materials: [reflections_anon_only, photos_only_with_c3]
    purposes: [internal_analytics, anonymized_case_studies]
    territory: RU
    authorship_attribution: forbidden
    sublicense: forbidden
  external_publication_of_non_aggregated: requires_separate_consent

anti_piracy_clause:
  base: "ст.450 ГК РФ — существенное нарушение"
  effect: [unilateral_termination, access_cutoff]
  refund_policy: "в пределах ФПР по фактически оказанной части"

# === МЕД / ТЕРМИНОЛОГИЯ ===
medical_terminology_lists:
  forbidden: [диагноз, лечение, терапия, нозология, болезнь, пациент, клиника, физиотерапия, лимфодренаж, БАД, препарат, дозировка, медицинская процедура]
  allowed: [wellness-оценка, самооценка самочувствия, коучинг, образовательный трекер привычек, практики самомассажа, дыхательные упражнения, мобилизационные упражнения]
  scope: [offer, bot_texts, marketing]
  explicit_disclaimer_phrase_verbatim_ref: product_profile.operator_disclaimer_verbatim

# === ИНЦИДЕНТЫ ===
incident_response:
  law: "ст.21 152-ФЗ, приказ РКН №187"
  primary_notify_hours: 24
  investigation_report_hours: 72
  short_playbook_in_reg_archive: required   # ← вместо тяжёлого формального документа
  triggers: [pii_leak, unauthorized_access, gate_18plus_leak, s3_misconfig, backup_loss]

# === DSAR / ИСПРАВЛЕНИЕ ===
dsar_export:
  channel: "команда 'Мои данные' в боте"
  format: ZIP {JSON, CSV, photos}
  s3_link_ttl_minutes: 15
  deadline_business_days: 10

data_rectification:
  before_course_start: participant_self_service_in_onboarding
  after_course_start: via_support_with_author_manual_verification
  audit_trail: append_only

# === ПРОЧЕЕ ===
pii_access_log:
  scope: any_access_incl_readonly
  fields: [actor, participant_id, purpose, timestamp_utc, action_type]
  append_only: true

payment_data:
  card_pan_storage: forbidden
  tokenization_on: payment_gateway_side

telegram_meta_as_pdn:
  fields: [chat_id, username_if_present, tg_id]
  included_in_c1: true

cross_border_c5_hard_off:
  default: absent
  policy_line_in_offer: "Трансграничная передача персональных данных не осуществляется"

marketing_c4:
  separated_from_system_notifications: true
  unsubscribe_button_in_each_broadcast: required

# === ПРИНЯТЫЕ ОПЕРАТОРОМ РИСКИ ===
risks_accepted_by_operator:
  - id: RISK-L-01
    name: "самостоятельная адаптация юридических шаблонов с ИИ, без разовой валидации живым юристом"
    mitigation_recommended: "разовая ревизия у профильного юриста РФ перед boot-gate"
  - id: RISK-L-02
    name: "медицинская вычитка дисклеймера/красной зоны без человеческого врача, с ИИ-содействием"
    mitigation_recommended: "разовая вычитка врачом-терапевтом/физиотерапевтом перед boot-gate"
  - id: RISK-L-03
    name: "концентрация функций оператора и ответственного за обработку ПДн в одном лице"
    mitigation_implemented: [calendar_reminders, short_checklists]
  - id: RISK-L-04
    name: "использование стандартного шифрования провайдера без Application-Level Encryption на первой стадии"
    mitigation_recommended: "внедрить ALE при когорте >1000 или появлении бюджета"
  - id: RISK-L-05
    name: "собственная аттестация ИСПДн отсутствует; покрытие обеспечивается аттестатом облачного провайдера"
    mitigation_recommended: "выбрать провайдера с УЗ-2/УЗ-3 сегментом и сохранить копию аттестата в reg-архив"

# === BOOT-GATE ===
boot_gate:
  required_verified_texts:
    - offer
    - privacy_policy
    - non_medical_and_non_device_disclaimer_verbatim
    - consents_C1_C2_C3_C4_C6_with_dynamic_requisites
    - red_zone_template
    - red_flags_template_with_emergency_contacts
    - incident_notification_texts_24h_72h
    - ugc_license_clause
    - anti_piracy_clause
    - force_majeure_telegram_clause
  rkn_notification_before_start: submitted

# === ИНВАРИАНТЫ (пересобранные) ===
invariants_final:
  - INV-L-01: "нет C2 ⇒ никакой обработки данных о здоровье"
  - INV-L-02: "отзыв согласия не удаляет прошлые правомерные записи, будущая обработка прекращается"
  - INV-L-03: "identity_map anonymize point = min(lifecycle_end+6m, erasure_request); erasure раньше при коллизии"
  - INV-L-06: "operator-initiated erasure ≥14д окно апелляции; human-in-the-loop"
  - INV-L-08: "данные о здоровье <18 не имеют валидного основания в продукте"
  - INV-L-09: "нет free-form генерации в красной зоне/Red Flags — только шаблоны"
  - INV-L-10: "смена цены не ретро"
  - INV-L-11: "нет верифицированных обязательных текстов ⇒ course_locked"
  - INV-L-13: "consent_logging не удаляется даже при erasure; ФИО → псевдоним"
  - INV-L-14: "иностранный CDN/хостинг/мессенджер — запрещён"
  - INV-L-17: "ст.26.1 ЗоЗПП не декларируется в оферте курса как гарантия (это норма о товарах)"
  - INV-L-18: "оговорка о полном удержании средств за пиратство ничтожна; удержание в пределах ФПР"
  - INV-L-19: "терминологический blacklist ФЗ-323 действует в оферте, боте и маркетинге одновременно"
  - INV-L-21: "Red Flags: auto-pause+emergency template ≤60сек; алерт Автору в тему Telegram-группы; append-only лог; человеческая реакция в разумный срок"
  - INV-L-22: "helpers — только ИП/самозанятые ГПХ, без признаков трудовых"
  - INV-L-23: "hard-stop на 2.4 млн ₽/год НПД с оферой перехода/возврата"
  - INV-L-24: "PAN карт не хранится оператором"
  - INV-L-25: "chat_id/tg_id — ПДн общей категории, в C1"
  - INV-L-28: "любое обращение к ПДн, включая read-only, — append-only в pii_access_log"
  - INV-L-29: "оговорка о подсудности по месту оператора не применяется к потребителю"
  - INV-L-30: "никаких реальных ПДн вне аттестованного сегмента провайдера"
  - INV-L-32: "e-mail — рекомендуемое, не обязательное поле; его отсутствие НЕ блокирует оплату"
  - INV-L-33: "Red Flags: бот не оценивает степень угрозы, только эскалирует"
  - INV-L-34: "поля ОГРН/ОГРНИП в шаблонах помечаются 'не применяется для НПД'"
  - INV-L-35: "иностранные мессенджеры как резервный канал запрещены"
  - INV-L-36: "принятые оператором риски (RISK-L-xx) — часть контракта, пересмотр раз в 6 мес"
  - INV-L-37: "продукт квалифицируется как образовательный при одновременном выполнении 3 условий (см. product_profile)"
  - INV-L-38: "собственная аттестация ИСПДн не требуется при размещении ПДн в аттестованном сегменте провайдера"

# === СНЯТЫЕ / СМЯГЧЁННЫЕ ТРЕБОВАНИЯ v2 ===
softened_from_v2:
  - "УЗ-2 → УЗ-3 (модель угроз 3-го типа)"
  - "ALE + crypto-shredding: с обязательного на рекомендуемое"
  - "приказ ФСБ №378 / собственные СКЗИ: убрано из обязанностей оператора"
  - "полный пакет 7 документов оператора → 4 документа (пропорционально масштабу)"
  - "e-mail с обязательного до оплаты → рекомендуемое, не блокирует оплату"
  - "восстановление резервного бота: '10 рабочих дней' → 'в разумный срок'"
  - "медицинская вычитка врачом: обязательное → рекомендуемое (RISK-L-02)"
  - "разовая юр.ревизия: обязательное → рекомендуемое (RISK-L-01)"
  - "оборотные штрафы 1-3%: применимы к юрлицу/ИП, не к самозанятому-физлицу (штрафы физлица кратно ниже)"
```
