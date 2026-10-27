# canon-1b-1 — хвосты Р-3, Р-4, Р-5 в normative I3, I4

Hash: f80a81d (main). Правило К: К-2 пройден — STATE «Решения, перекрывающие канон» (Р-3, Р-4, Р-5), normative/README, I3, I4. Метка К-6 в таблице: [Автор против канона → STATE Р-3/Р-4/Р-5], если не указано иное. Метод: тело не переписывать; врезка в шапку + запись OVERRIDES.yaml.

## 0. Чтение
I3, I4 прочитаны целиком (концы — вставкой Автора): I3 от «## 🛡 И3 — Fail-safe» до конца, I4 от «## 8.» до конца, оба из main f80a81d.

## 1. Таблица мест (решение · что править)
| # | Место | Цитата | Решение | Править |
|---|---|---|---|---|
| 1 | I3 вступление; Fail-safe «Открытые стыки» | «без согласия C5 фото не принимается»; «C5 здесь — фото (R318), а в юрблоке C5 — трансграничная передача» | Р-3: убрать C5 = фото; юр-C5 оставить | врезка |
| 2 | I3 §C.1; refund_saga (step_0–4, rollback_policy, new_card_after_decline); revert_contract.compensating_step_for_refund | `coordinator: refund_orchestrator` | Р-4 на потом | врезка, O-9 |
| 3 | I3 §C.1; audit_additions_i3.refund_psp_reconciliation | `worker: refund_reconciliation_watcher` | Р-4 на потом | O-16 |
| 4 | I3 §C.1; refund_saga.finance_summary | «/finance_summary [period] отдаёт только агрегаты» | оставить: учёт ручного /refund (В-5) | — |
| 5 | I3 refund_saga.sh14_payment_confirmation_window, saga_no_banned_states | `n_hours_reconciliation_window`; «неоплата в срок → sleeping» | не возврат — оставить (В-8) | — |
| 6 | I3 §C.2; refund_details_retention | «реквизиты (IBAN, имя, БИК) — отдельная таблица refund_details» | Р-4 на потом | врезка, O-10 |
| 7 | I3 §C.2; audit_additions_i3.erasure_deferral_precedence | `refund_finalization_deferral: 14d AFTER cooling_off IF active refund` | Р-4 на потом вместе с O-10 (В-4) | O-15 |
| 8 | I3 §C.3; legal_refund D_25–D_28; legal_pack_i3_clarifications D_25, D_28; I4 §3 тексты Д-27/Д-28; I4 §8 minor_return Р48 | `legal_status: pre-legal-review`; `full refund + immediate erasure` | неясно (В-2) | — |
| 9 | I3 §C.4; photo_ingest_saga (gate, gc_and_retention, region_localization_enforcement); audit_additions_i3.exif_strip_post_verify | `required_consent: C5 (photo_consent, R318)` | Р-3 убрать (и Р-5) | врезка, O-7, O-14, O-17 |
| 10 | I3 §C.5; photo_erasure.R334_delete_all_versions, R335_object_lock_scope | `photo_buckets: Object_Lock=DISABLED` | Р-3 убрать; audit_log_buckets COMPLIANCE оставить | O-8 |
| 11 | I3 §C.5; photo_erasure.signed_url_service | «чтение фото — 5 минут, экспорт — 15 минут»; `upload_url_kind: pre-signed PUT` | фото, upload — Р-3/Р-5; экспорт — В-3 | врезка, O-18 |
| 12 | I3 §C.6; export_worker.export_kind_enum, photo_naming_and_manifest | `[json, xlsx, csv, photos, full]` | photos — Р-3 убрать | O-13 |
| 13 | I3 export_worker.delivery.large_files | `signed-URL TTL 15min` | неясно (В-3) | — |
| 14 | I3 §C.6 Ш21; export_worker.sh21_third_party_notification; Sh21_psp_notification_wording | `/notify_erasure {payment_ref}` | Р-4 на потом | врезка, O-19 |
| 15 | I3 §C.11; legal_pack_i3.D_20_cloud_provider | `sse_kms_for_photos: mandatory` | Р-3 убрать | врезка, O-20 |
| 16 | I3 §C.12 права; role_capability_matrix_i3_additions | `refund_initiate`; `refund_rollback_manual_reissue` | initiate оставить (В-5; finance не определена — OPEN-5); rollback — Р-4 на потом | O-21 |
| 17 | I3 §C.12 CI; ci_checks_i3 | `photo_ingest_magic_bytes_before_processing`, `no_photo_bucket_object_lock`; `refund_saga_idempotency`, `refund_details_retention_separate` | фото — Р-3; refund — Р-4 | O-11 |
| 18 | I3 ci_checks_i3.no_cross_region_replication | `denies replication targets outside RU` | неясно (В-9) | — |
| 19 | I3 §C.12 переносы; deferred_from_i3 | `C5 revoke button`; `photo upload UI + progress`; `photo_upload_errors`; `refund initiation`; refund-тексты | фото, C5-кнопка — Р-3 (панель «Мои согласия» оставить); refund — Р-4 (и Р-1); `DSAR export button` — В-3 | врезка, O-22 |
| 20 | I3 §C.12 риски; risk_registry_additions_i3 | `Orphaned staging files`; `Pillow EXIF strip` | Р-3 снять RISK-L-13, RISK-L-15 | O-12 |
| 21 | I3 RISK-L-11; I4 §7 baseline_override_UI; I4 §10 pii_detector_baseline_reason | «утечка ПДн через свободный текст причины»; «RISK-L-11 CLOSED» | не фото — оставить (В-1) | — |
| 22 | I3 Fail-safe «Деньги» / «Данные» | «ни один шаг возврата не выполняется дважды» | «Деньги» — Р-4 на потом; «Данные» — Р-3 | врезка |
| 23 | I3 врезка ERRATA A3 | «срок хранения PSP (до 5 лет по 115-ФЗ)» | Р-4 на потом | — |
| 24 | I4 §2 R366 | «unsupported_format, file_too_large, staging_expired, checksum_mismatch»; «insufficient funds (E51)» | фото — Р-3; E51 — Р-4 на потом | O-3 |
| 25 | I4 §2 P468 | «refund_initiate, refund_rollback» | rollback — Р-4; initiate оставить (В-5) | O-5 |
| 26 | I4 §3 | «B16.refund_pending_notification», «B16.manual_reissue_notification» | Р-4 на потом | O-4 |
| 27 | I4 §3 | «B15.mime_rejected (dry)», «B15.magic_mismatch (dry)» | Р-3 убрать | O-2 |
| 28 | I4 §7 csp_header | «img_src: "'self' https://{s3-domain-ru} data: blob:"» | Р-3/Р-5 убрать S3-домен | O-6 |
| 29 | I4 вступл., R283, R343, R368, D_15; §10 no_direct_href_signed_url | «fetch(signed_url) → blob → URL.createObjectURL» | медиа — Р-3/Р-5; экспорт — В-3; страж оставить | — |
| 30 | I4 §7 photo_consent_revocation_UI | «"Мои согласия" → C5 row → revoke button»; «trigger photo_erasure_saga» | Р-3 убрать (C5 = фото) | врезка, O-1 |
| 31 | I4 §8 E3 steps_order; photo_consent_C5_step | `legal_consents_C0_C6, …, photo_C5`; `returns 403 if C5 not granted` | photo_C5 — Р-3 убрать; C0_C6 оставить | врезка, O-24, O-25 |
| 32 | I4 §8 E2 submenu; §9 G1 | `refund_appeals`; `(moderator, any_pid, initiate_refund) → 403` | оставить: ручной /refund (В-5) | — |
| 33 | I4 §11 risk_registry_full | RISK-L-13, RISK-L-15 | Р-3 снять | O-23 |
| 34 | I4 §12 architecture_100pct_complete | `blocks: [..., 15, 16]`; `risk_registry_total: 19` | «закрыт» ≠ «делаем»: фото Б15 — Р-3, сага Б16 — Р-4 | врезка |
| 35 | I4 «Что патч меняет…» | «pre-legal-review … минимум на семь позиций, при заявленных двенадцати» | возвратные тексты — Р-4 на потом; счёт — долг сверки | — |

C5 в I3 и I4 целиком. «Фото» — 12: I3 вступление, §C.4 R318, §C.12 переносы, Fail-safe «Открытые стыки» (×2), photo_ingest_saga.overview.gate, deferred_from_i3; I4 §7 C5 row, §8 проза «согласие на фото», steps_order photo_C5, photo_consent_C5_step, «Связи» «отзыв C5». «Трансграничка» — 1: Fail-safe «в юрблоке C5 — трансграничная передача». «Неясно» — 1: `legal_consents_C0_C6` (диапазон включает номер C5 при отдельном `photo_C5`; по Р-3 читается как юр-C5). C6 = рефлексии (Д-21) — в единый реестр C0–C6 (стык И1, normative/README).
bot_never_serves: в I3 и I4 нет (оба прочитаны целиком). Из врезки I4 убрано (В-7).

## 2. Врезки в шапку (форма — по образцу 14-data-durability, сверяет ШТАБ)

I3:
> **Переопределено решениями Автора Р-3, Р-4, Р-5** (course-bot docs/decisions/R-2026-10-1.md; реестр — [OVERRIDES.yaml](OVERRIDES.yaml)).
> Р-3: приём фото отменён. Не применяются: photo_ingest_saga (§C.4), exif_strip_post_verify, photo_erasure и signed_url_service для фото (§C.5), фото в export_worker (§C.6), SSE-KMS фото (Д-20), фото-CI, фото-переносы, RISK-L-13, RISK-L-15. Убирается только «C5 = фото» (photo_consent, R318); юридическое C5 (трансграничная передача) остаётся.
> Р-4: на потом — refund_saga (кроме finance_summary и sh14), refund_psp_reconciliation, refund_details_retention и отсрочка стирания 14 дн. (§C.2), уведомление PSP по Ш21, refund_rollback_manual_reissue. Возвраты — вручную; /refund Панели — учётная операция без PSP; /finance_summary и refund_initiate — её учёт.
> Р-5: медиа — только внешний Telegram-канал; S3 pre-signed для материалов не делаем.
> Без изменений: WORM COMPLIANCE бакетов аудита (R335), RISK-L-11, Чек-Ап, Красная зона, Red Flags, Revert (кроме компенсации возврата), F1.

I4:
> **Переопределено решениями Автора Р-3, Р-4, Р-5** (course-bot docs/decisions/R-2026-10-1.md; реестр — [OVERRIDES.yaml](OVERRIDES.yaml)).
> Р-3: не применяются photo_consent_revocation_UI (строка C5 «фото», фраза «ОТОЗВАТЬ СОГЛАСИЕ НА ФОТО», photo_erasure_saga), шаг photo_C5 и photo_consent_C5_step (§8), тексты B15.*, фото-коды R366, RISK-L-13 и RISK-L-15 (§11). Юридическое C5 (трансграничная передача) в legal_consents_C0_C6 остаётся.
> Р-4: на потом — тексты B16.refund_*, B16.manual_reissue_notification, код insufficient_funds, событие refund_rollback. refund_initiate (P468, G1) и refund_appeals — учёт ручного /refund.
> Р-5: S3-домен в csp_header.img_src и чтение подписанных ссылок для медиа не нужны.
> §12: блоки 15 и 16 «закрыты» как документ; фото-часть Б15 (Р-3) и сага Б16 (Р-4) не делаются.

## 3. Записи OVERRIDES.yaml (path → canonical_value · основание)
I4:
- O-1 I4.mini_app_client.photo_consent_revocation_UI → not_applicable · Р-3
- O-2 I4.texts_from_prior_waves.photo_upload_errors → not_applicable · Р-3
- O-3 I4.texts_B9.R366_sync_status_reason_codes.reason_code_enum → без unsupported_format, file_too_large, staging_expired, checksum_mismatch (Р-3); insufficient_funds → deferred (Р-4)
- O-4 I4.texts_from_prior_waves.refund_participant_texts → deferred · Р-4
- O-5 I4.texts_B9.P468_peer_alert_admin_actions.events_covered → refund_rollback deferred; refund_initiate без изменений (В-5) · Р-4
- O-6 I4.csp_header.img_src → "'self' data: blob:" · Р-3, Р-5 (поверх E2)
- O-23 I4.risk_registry_full.RISK-L-13, .RISK-L-15 → withdrawn · Р-3
- O-24 I4.onboarding_finalization.E3_onboarding_pipeline.steps_order → [age_18_plus_gate, legal_consents_C0_C6, payment, email_optional, city] · Р-3
- O-25 I4.onboarding_finalization.photo_consent_C5_step → not_applicable · Р-3

I3 (пути сверены с YAML):
- O-7 I3.photo_ingest_saga → not_applicable · Р-3, Р-5
- O-8 I3.photo_erasure.R334_delete_all_versions, I3.photo_erasure.R335_object_lock_scope.photo_buckets → not_applicable; audit_log_buckets COMPLIANCE и erasure_blacklist (И1 Д-18) без изменений · Р-3
- O-9 I3.refund_saga (кроме finance_summary, sh14_payment_confirmation_window, saga_no_banned_states — В-8), I3.revert_contract.compensating_step_for_refund → deferred; /refund = учётная операция без PSP · Р-4
- O-10 I3.refund_details_retention → deferred · Р-4
- O-11 I3.ci_checks_i3: photo_ingest_magic_bytes_before_processing, no_photo_bucket_object_lock → not_applicable (Р-3); refund_saga_idempotency, refund_details_retention_separate → deferred (Р-4); no_cross_region_replication — по В-9
- O-12 I3.risk_registry_additions_i3.RISK-L-13, .RISK-L-15 → withdrawn · Р-3
- O-13 I3.export_worker.export_kind_enum → [json, xlsx, csv, full] (full без фото); I3.export_worker.photo_naming_and_manifest → not_applicable · Р-3
- O-14 R318 photo_consent (C5 = фото): I3.photo_ingest_saga.overview.gate, I4 photo_consent_C5_step → withdrawn; C5 = трансграничная передача без изменений · Р-3
- O-15 I3.audit_additions_i3.erasure_deferral_precedence.refund_finalization_deferral → deferred (с O-10); cooling_off, no_active_refund без изменений · Р-4 (В-4)
- O-16 I3.audit_additions_i3.refund_psp_reconciliation → deferred · Р-4
- O-17 I3.audit_additions_i3.exif_strip_post_verify → not_applicable · Р-3
- O-18 I3.photo_erasure.signed_url_service.photo_url_ttl, .upload_url_kind → not_applicable · Р-3, Р-5; export_url_ttl — по В-3
- O-19 I3.export_worker.sh21_third_party_notification, I3.legal_pack_i3_clarifications.Sh21_psp_notification_wording → deferred · Р-4
- O-20 I3.legal_pack_i3.D_20_cloud_provider.sse_kms_for_photos → not_applicable · Р-3
- O-21 I3.role_capability_matrix_i3_additions: refund_rollback_manual_reissue (owner, finance) → deferred · Р-4
- O-22 I3.deferred_from_i3.to_i4_wave_D: photo_upload_errors, «photo upload UI + progress», «C5 revoke button» → not_applicable (Р-3); refund_saga_participant_texts, manual_reissue_notification, «client-side flows for refund initiation» → deferred (Р-4)

## 4. Вопросы
Решено (ответы ШТАБа):
- В-0 → Б: дочитка в этом окне ПРОДОЛЖЕНИЕ, концы — вставкой Автора. [ШТАБ-тех]
- В-4 → отсрочка 14 дн. уходит вместе с retention refund_details (O-10, O-15). [ШТАБ, Р-4]
- В-5 → /finance_summary и refund_initiate — без правок, как учёт ручного /refund. [ШТАБ, Р-4]
- В-6 → в трекер DOCS-CANON, пакет 2 (Р-8, Р-9); туда же I4 «Что патч меняет…»: hosting_and_tls против открытых Д-29 и D_20_cloud_provider. [ШТАБ]

Открыто:
В-1 (Автору; К-4 б). В Р-3 сказано «RISK-L-11 снимается», но L-11 — не фото.
Канон: проверено I3 risk_registry_additions_i3 (L-11 «PII leak через baseline_override reason free text»; фото — L-13 staging, L-15 EXIF), I4 §11 (L-11 «CLOSED via mini_app_client.baseline_override_UI_owner_only»), I4 §10 pii_detector_baseline_reason (covers RISK-L-11) — противоречит Р-3.
А — L-11 оставить, снять L-13 и L-15, номер в STATE Р-3 поправить; Б — снять и L-11 (pii_detector_baseline_reason остаётся без риска). Мнение: А.

В-2 (Автору; право, деньги). Возврат ручной — что делать с правом Д-25–Д-28 и Р48?
Канон: проверено I3 legal_refund D_25–D_28, legal_pack_i3_clarifications (D_25 формулировка, D_28 исключение для несовершеннолетних), I4 §8 minor_return Р48, I4 §3 c2_withdrawal_notification, service_acceptance_act — о ручном пути молчит: D_25 «refund_stitch_block_16_legal», D_27 «initiate refund saga».
А — нормы (сетка ЗоЗПП, 10 дн., акт 3 дн. с исключением для несовершеннолетних, полный возврат по Р48) оставить для ручного /refund, саговые шаги — на потом; Б — всё на потом. Мнение: А, к юристу (все записи pre-legal-review).

В-3 (Автору; архитектура). Отдавать экспорт подписанной ссылкой на 15 мин?
Канон: проверено I3 photo_erasure.signed_url_service.export_url_ttl, export_worker.delivery.large_files (>10 МБ — signed URL), deferred_from_i3 «DSAR export button»; I4 R283, R343, R368, D_15, §10 no_direct_href_signed_url — ссылку требует; STATE Р-10 «S3 прода — только бэкапы и WORM-аудит».
А — только sendDocument (≤10 МБ; без фото json/xlsx в лимит укладываются), страж оставить; Б — signed URL для экспорта, уточнить Р-10. Мнение: А.

В-7 (ШТАБу). Строки bot_never_serves: [media, file_id, images, files] в I3 и I4 нет.
Канон: проверено I3, I4 целиком — молчит. Из врезки I4 убрано. Откуда строка — ШТАБу. Мнение: сверить в окне КАРТОЧКИ по 15-content-antipiracy.md.

В-8 (ШТАБу, тех). refund_saga.sh14_payment_confirmation_window (окно подтверждения оплаты) и saga_no_banned_states (неоплата → sleeping) — это не возврат.
Канон: проверено I3 refund_saga (sh14 — payload подтверждения оплаты; запрет banned — «covered by И2 R477 guard»). А — исключить из O-9 (оставить); Б — отложить всю refund_saga. Мнение: А.

В-9 (Автору; право, архитектура). Локализация в RU и запрет репликации описаны только для фото.
Канон: проверено I3 photo_ingest_saga.region_localization_enforcement, ci_checks_i3.no_cross_region_replication (R352, R353), Fail-safe «Данные» — о бакетах бэкапов и аудита (Р-10) молчит.
А — перенести no_cross_region_replication на бакеты бэкапов и аудита; Б — снять вместе с фото. Мнение: А (ПДн в бэкапах; к юристу).

## 5. Прочитано
- docs/process/DESIGNER.md — 12 КБ — файл исследования ≤ 15 КБ, вопросы по К-4.
- docs/STATE.md — 20 КБ — Р-3/Р-4/Р-5 перекрывают канон; врезок в I3/I4 нет.
- AGENT-BRIEF.md — 14 КБ — §7: в Mini App нет фото, C5, pre-signed.
- docs/process/README.md — 6 КБ — канон правится в DOCS, docs/architecture — зеркало.
- docs/process/CANON-CHECK.md — 4 КБ — К-4: строка «Канон: проверено».
- docs/process/CODER.md — 8 КБ — блок «Под пакетом З1».
- docs/architecture/normative/README.md — 10 КБ — «прочитал YAML → применил OVERRIDES»; коллизия C5.
- docs/architecture/normative/I3-wave-c.md — 70,8 КБ, целиком (конец — вставкой Автора) — C5 = фото (Fail-safe); фото-риски L-13, L-15; reconciliation в audit_additions_i3.
- docs/architecture/normative/I4-wave-d.md — 58,5 КБ, целиком (конец — вставкой Автора) — E3: photo_C5 после legal_consents_C0_C6; bot_never_serves нет; L-11 = правка базы.
