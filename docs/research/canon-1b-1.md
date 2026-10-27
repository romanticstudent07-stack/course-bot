# canon-1b-1 — хвосты Р-3, Р-4, Р-5 в normative I3, I4 (ЧЕРНОВИК З1)

Hash: f80a81d (main). Правило К: К-2 пройден — STATE «Решения, перекрывающие канон» (Р-3, Р-4, Р-5), normative/README, I3, I4. Метка К-6 у решений таблицы: [Автор против канона → STATE Р-3/Р-4/Р-5]. Метод: тело не переписывать; врезка в шапку + запись OVERRIDES.yaml.

## 0. Блокер: файлы прочитаны не целиком
Инструмент чтения отдаёт только первые ~10 000 токенов; raw/API/CDN дальше — ошибка gzip.
- I3@f80a81d (70,8 КБ, 877 строк): прочитаны шапка, врезки, проза C.1–C.12, начало Fail-safe. НЕ прочитаны: конец Fail-safe и весь YAML (refund_saga, photo_ingest_saga, capability, ci_checks_i3, deferred_from_i3, audit_additions_i3, RISK-L-11–15).
- I4@f80a81d (58,5 КБ): прочитано по §7 (mini_app_client) включительно. НЕ прочитаны: §8 онбординг E2/E3 (конвейер согласий C0–C6), QA, ci_checks_i4, risk_registry_full, architecture_100pct_complete.
- Итог: таблица и OVERRIDES неполные; YAML-пути И3 — предварительные. Решение — В-0.

## 1. Таблица мест (решение · что править)
| # | Место | Цитата | Решение | Править |
|---|---|---|---|---|
| 1 | I3 вступление | «без согласия C5 фото не принимается» | Р-3 убрать (C5 = фото) | врезка |
| 2 | I3 §C.1 | «Возврат — многошаговая сага с координатором refund_orchestrator» | Р-4 на потом | врезка + OVERRIDES |
| 3 | I3 §C.1 | «refund_reconciliation_watcher раз в час опрашивает статусы возвратов» | Р-4 на потом | OVERRIDES |
| 4 | I3 §C.1 | «/finance_summary [period] отдаёт только агрегаты» | неясно (В-5) | — |
| 5 | I3 §C.2 | «Банковские реквизиты (IBAN, имя, БИК) живут в отдельной таблице refund_details» | Р-4 на потом (retention) | врезка + OVERRIDES |
| 6 | I3 §C.2 | «только если есть активный возврат — отсрочка 14 дней» | неясно (В-4) | — |
| 7 | I3 §C.3 Д-25–Д-28 | «Четыре записи, все со статусом pre-legal-review» | неясно (В-2) | — |
| 8 | I3 §C.4 R318 | «без согласия C5 (photo_consent, R318) эндпоинт отвечает 403» | Р-3 убрать (C5 = фото) | врезка + OVERRIDES |
| 9 | I3 §C.4 | «Приём фото — сага из восьми шагов» | Р-3 убрать (и Р-5) | врезка + OVERRIDES |
| 10 | I3 §C.5 R334 | «erasure_blob_refs(pid) отдаёт список ключей вместе со всеми version_id» | Р-3 убрать | OVERRIDES |
| 11 | I3 §C.5 R335 | «на бакетах с фото блокировка отключена принудительно» | Р-3 убрать; WORM COMPLIANCE аудита — оставить | OVERRIDES |
| 12 | I3 §C.5 | «чтение фото — 5 минут, экспорт — 15 минут» | фото — Р-3 убрать; экспорт — неясно (В-3) | врезка |
| 13 | I3 §C.6 | «Фото в выгрузке обезличиваются по имени» | Р-3 убрать | OVERRIDES |
| 14 | I3 §C.6 Ш21 | «Уведомление PSP идёт вызовом /notify_erasure {payment_ref}» | Р-4 на потом | врезка |
| 15 | I3 §C.11 Д-20 | «SSE-KMS для фото обязателен» | Р-3 убрать | врезка |
| 16 | I3 §C.12 права | «Роль finance может инициировать возврат» | Р-4 на потом (+ OPEN-5) | ничего |
| 17 | I3 §C.12 CI | «проверка magic bytes до обработки (тест на SVG в одежде JPEG)» | Р-3 убрать (+ Object Lock фото, кросс-регион) | OVERRIDES |
| 18 | I3 §C.12 CI | «идемпотентность каждого шага саги возврата» | Р-4 на потом (+ сохранность refund_details) | OVERRIDES |
| 19 | I3 §C.12 переносы | «загрузка фото с прогрессом, панель «Мои согласия» вместе с кнопкой отзыва C5» | Р-3 убрать (C5 = фото); «Мои согласия» — оставить | врезка |
| 20 | I3 §C.12 переносы | «из Mini App — инициация возврата» | Р-4 на потом (и Р-1) | врезка |
| 21 | I3 §C.12 риски | «осиротевшие файлы staging»; «медленное снятие EXIF под нагрузкой» | Р-3 убрать | OVERRIDES (номер — после дочитки) |
| 22 | I3 §C.12 риски | «утечка ПДн через свободный текст причины при правке базы» | неясно (В-1) | — |
| 23 | I3 Fail-safe | «ни один шаг возврата не выполняется дважды» | Р-4 на потом; абзац «Данные» — Р-3 | врезка |
| 24 | I3 врезка ERRATA A3 | «собственном сроке хранения PSP (до 5 лет по 115-ФЗ)» | Р-4 на потом | ничего |
| 25 | I4 §2 R366 | «unsupported_format, file_too_large, staging_expired, checksum_mismatch» | Р-3 убрать | OVERRIDES |
| 26 | I4 §2 R366 | «PSP declined: insufficient funds (code E51)» | Р-4 на потом | OVERRIDES |
| 27 | I4 §2 P468 | «refund_initiate, refund_rollback» | rollback — Р-4 на потом; initiate — неясно (В-5) | OVERRIDES |
| 28 | I4 §3 | «B16.refund_pending_notification», «B16.manual_reissue_notification» | Р-4 на потом | OVERRIDES |
| 29 | I4 §3 | «B15.mime_rejected (dry)», «B15.magic_mismatch (dry)» | Р-3 убрать | OVERRIDES |
| 30 | I4 §3 | «what happens next + refund breakdown»; «Не подтверждение — 3 дня» | неясно (В-2) | — |
| 31 | I4 §7 csp_header | «img_src: "'self' https://{s3-domain-ru} data: blob:"» | Р-3/Р-5 убрать S3-домен | OVERRIDES |
| 32 | I4 вступл., R283, R343, R368, D_15 | «strategy: fetch(signed_url) → blob → URL.createObjectURL» | фото/медиа — Р-3/Р-5; экспорт — неясно (В-3) | — |
| 33 | I4 §7 | «location: profile → "Мои согласия" → C5 row → revoke button» | Р-3 убрать (C5 = фото) | врезка + OVERRIDES |
| 34 | I4 §7 | «trigger photo_erasure_saga (from И3 R334)» | Р-3 убрать | OVERRIDES (та же запись) |
| 35 | I4 §7 baseline_override_UI | «RISK-L-11 CLOSED» | неясно (В-1) | — |

Классификация C5 в прочитанном: 5 мест (стр. 1, 8, 19, 33, 34) — все «фото»; «трансграничка» — 0; «неясно» — 0. Непрочитанное (I4 §8 E3) — проверить. bot_never_serves в прочитанном не встречен.

## 2. Врезки в шапку (по образцу 14-data-durability — форму сверяет ШТАБ, файл вне списка)

I3:
> **Переопределено решениями Автора Р-3, Р-4, Р-5** (course-bot docs/decisions/R-2026-10-1.md; реестр — [OVERRIDES.yaml](OVERRIDES.yaml)).
> Р-3: приём фото отменён — §C.4 Photo Ingest Saga, фото-часть §C.5 (R334; R335 для бакетов фото; чтение фото), фото в выгрузке §C.6, SSE-KMS фото (Д-20), фото-CI и фото-риски §C.12 не применяются. Убирается только «C5 = фото» (photo_consent, R318); юридическое C5 (трансграничная передача) остаётся.
> Р-4: Refund Saga (§C.1), refund_reconciliation_watcher, retention refund_details (§C.2), уведомление PSP по Ш21 — на потом; возвраты — вручную, /refund Панели — учётная операция без PSP.
> Р-5: медиа — только внешний Telegram-канал; S3 pre-signed для материалов не делаем.
> Без изменений: WORM COMPLIANCE бакетов аудита (R335), Чек-Ап, Красная зона, Red Flags, Revert, F1.

I4:
> **Переопределено решениями Автора Р-3, Р-4, Р-5** (course-bot docs/decisions/R-2026-10-1.md; реестр — [OVERRIDES.yaml](OVERRIDES.yaml)).
> Р-3: photo_consent_revocation_UI (строка C5 «фото», фраза «ОТОЗВАТЬ СОГЛАСИЕ НА ФОТО», photo_erasure_saga), тексты B15.* и фото-коды R366 не применяются; юридическое C5 (трансграничная передача) остаётся.
> Р-4: тексты B16.refund_*, B16.manual_reissue_notification, код insufficient_funds, событие refund_rollback — на потом.
> Р-5: S3-домен в csp_header.img_src и чтение подписанных ссылок для медиа не нужны; bot_never_serves: [media, file_id, images, files] остаётся.

## 3. Будущие записи OVERRIDES.yaml (формат path → canonical_value)
I4 — пути из прочитанного YAML:
- O-1 I4.mini_app_client.photo_consent_revocation_UI → not_applicable · Р-3
- O-2 I4.texts_from_prior_waves.photo_upload_errors → not_applicable · Р-3
- O-3 I4.texts_B9.R366_sync_status_reason_codes.reason_code_enum → без unsupported_format, file_too_large, staging_expired, checksum_mismatch (Р-3); insufficient_funds → deferred (Р-4)
- O-4 I4.texts_from_prior_waves.refund_participant_texts → deferred · Р-4
- O-5 I4.texts_B9.P468_peer_alert_admin_actions.events_covered → refund_rollback deferred · Р-4 (refund_initiate — по В-5)
- O-6 I4.csp_header.img_src → "'self' data: blob:" · Р-3, Р-5 (поверх E2)
I3 — пути предварительные (ключи из contains; сверить с YAML после В-0):
- O-7 I3.photo_ingest_saga → not_applicable · Р-3, Р-5
- O-8 I3.photo_erasure (R334; R335 для фото-бакетов) → not_applicable; WORM аудита без изменений · Р-3
- O-9 I3.refund_saga (+ reconciliation_watcher) → deferred; /refund = учётная операция без PSP · Р-4
- O-10 I3.refund_details_retention → deferred · Р-4
- O-11 I3.ci_checks_i3: фото-чеки → not_applicable (Р-3); refund-чеки → deferred (Р-4)
- O-12 I3 RISK фото (staging-сироты, EXIF) → withdrawn · Р-3 (номера после В-0 и В-1)
- O-13 I3.export_worker: фото в выгрузке → not_applicable · Р-3
- O-14 R318 photo_consent (C5 = фото) → withdrawn; C5 = трансграничная передача без изменений · Р-3 + уточнение ШТАБа В-1 А

## 4. Вопросы
В-0 (ШТАБу, блокер). Дочитка: I3 от «## 🛡 И3 — Fail-safe» до конца, I4 от «## 8.» до конца. А — Автор вставляет эти куски в З2; Б — окно ПРОДОЛЖЕНИЕ. Мнение: А, если влезет в лимит; иначе Б.
В-1 (Автору; К-4 б). Р-3: «RISK-L-11 снимается». В каноне RISK-L-11 — не фото. Канон: проверено I3 §C.12 (первый новый риск — «утечка ПДн через свободный текст причины при правке базы»), I4 §7 baseline_override_UI_owner_only («# RISK-L-11», «RISK-L-11 CLOSED») — противоречит Р-3. А — оставить L-11, снять фото-риски (staging, EXIF; номера после В-0); Б — снять L-11. Мнение: А.
В-2 (Автору; право, деньги). Возвраты ручные — что с Д-25–Д-28 (сетка ЗоЗПП Д-26, авто-пауза при отзыве C2 Д-27, акт приёмки Д-28)? Канон: проверено I3 §C.3, I4 §3 c2_withdrawal_notification, service_acceptance_act — молчит о ручном пути. А — правовые нормы оставить для ручного /refund, механику саги — на потом; Б — всё на потом. Мнение: А (к юристу).
В-3 (Автору; архитектура). Экспорт/DSAR подписанной ссылкой 15 мин. Канон: проверено I3 §C.5, §C.6; I4 R283, R343, R368, D_15_dsar_export_UI — требует signed URL; STATE Р-10 «S3 прода — только бэкапы и WORM-аудит», Р-5 запрещает pre-signed только для материалов. А — экспорт только sendDocument, ссылки не делать; Б — оставить signed URL для экспорта (тогда уточнить Р-10). Мнение: А.
В-4 (ШТАБу). Отсрочка стирания 14 дн. (I3 §C.2) завязана на «активный возврат» саги; саги нет — считать ли активным ручной /refund? Связано с OPEN-3.
В-5 (ШТАБу, тех). /finance_summary (I3 §C.1) и refund_initiate в P468 (I4 §2) — оставить как учёт ручного /refund?
В-6 (ШТАБу, вне пачки). I4 §7 hosting_and_tls «Yandex Cloud primary / Timeweb reserve» против Р-9; I4 §1 text_registry «versioned_yaml_in_git» против Р-8 (seed JSON) — в трекер DOCS-CANON.

## 5. Прочитано
- docs/process/DESIGNER.md — 12 КБ — ИССЛЕДОВАНИЕ: файл ≤ 15 КБ, вопросы по К-4.
- docs/STATE.md — 20 КБ — Р-3/Р-4/Р-5 перекрывают канон; DOCS #15 внёс Р-1/3/4/5, в I3/I4 врезок нет.
- AGENT-BRIEF.md — 14 КБ — §7: в Mini App нет фото, C5, pre-signed.
- docs/process/README.md — 6 КБ — канон правится в DOCS, docs/architecture — зеркало.
- docs/process/CANON-CHECK.md — 4 КБ (указан в старте) — К-4: строка «Канон: проверено».
- docs/process/CODER.md — 8 КБ (указан в старте) — блок «Под пакетом З1».
- docs/architecture/normative/README.md — 10 КБ — «прочитал YAML → применил OVERRIDES»; коллизия C5 (И1/И3 фото против юрблока, Д-10).
- docs/architecture/normative/I3-wave-c.md — 70,8 КБ, прочитано около 45 % — четыре контура: refund, photo, Чек-Ап, Красная зона.
- docs/architecture/normative/I4-wave-d.md — 58,5 КБ, прочитано около 65 % — photo_consent_revocation_UI = C5 «фото»; RISK-L-11 = правка базы.
