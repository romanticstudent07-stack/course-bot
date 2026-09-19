---
file: 14-data-durability.md
block: 14
title: "Данные, Карта изменений, замеры, publish_stage, ТЗ, «финиша нет», Mini App"
status: закрыт (v3.4)
doc_version: "consolidated v3 + Mini App v3.3 + дельта v3.4"
contains: [14.1–14.17, аксиомы X1–X6, инварианты, Р325–Р385, fail-safe, yaml v3.3, yaml v3.4]
---

# БЛОК 14. ДАННЫЕ, КАРТА ИЗМЕНЕНИЙ, ЗАМЕРЫ, PUBLISH_STAGE, ТЗ, «ФИНИША НЕТ», MINI APP

> **Переопределено ERRATA-UNIFIED.** CSP Mini App: `default-src 'none'` из И4 **отменён**, канонично `default-src 'self'` с явным белым списком + запрет `unsafe-eval` (E2). Владелец `publish_epoch` — этот блок (FIX1); имена `publish_stage` (в теле) и `publish_epoch` (в FIX1) тождеством нигде не зафиксированы — читать как одну сущность до канонизации. Boot-gate по числу ротации бэкапов — ADD5 (при подстановке брать более строгую границу A4 с учётом WAL); плейсхолдер `{s3-domain-ru}` унифицирован с `{s3-domain}` (шлюз ERRATA раздел 6). Outbox, DLQ, `INV-OUTBOX-SENT-AT-COMPACTION` — патч И2 + ADD1 ERRATA. См. [normative/I2-wave-b.md](normative/I2-wave-b.md), [normative/I4-wave-d.md](normative/I4-wave-d.md), [normative/errata-unified.md](normative/errata-unified.md).

Финальная единая выжимка, версия **v3.3 (с Mini App)** + подшитая снизу **дельта v3.4**.

## 14.1. Назначение блока и владение данными

Блок 14 — источник истины по данным трансформации: замеры, Карта изменений, факт публикации Этапа, ТЗ участника, обязательные пост-Этапные срезы. Всё критичное — синхронно в PostgreSQL, append-only, UPDATE/DELETE запрещены навсегда для `measurements_log`, `stage_publish_log`, `metric_catalog_log`, `tz_change_log`, `pii_access_log`, `data_export_event`. Все payload и события несут `schema_version` (совместимость с DLQ A3 Б15). Идемпотентность: `client_op_id` для замеров и Mini App write-операций, `(stage_id, publish_epoch)` для публикаций, `event_id = hash(pid, metric_key, taken_at_ms, source, schema_version)` как natural key. Baseline per `(pid, metric_key)` детерминирован: `MIN(taken_at_ms)`, tie-break `MIN(event_id)`; сквозной от первого входа за всю историю участника, платный рестарт создаёт `restart_marker` (визуальный якорь, не мутация); ошибочный первый ввод правится в 24-часовое окно самим участником, далее только через `author_correction` Автора.

## 14.2. Каталог метрик

Каталог метрик `metric_catalog` — конфиг-driven, храним как append-only лог с материализацией текущего состояния; удаление записи запрещено, только `deprecated_at`-tombstone; исторические трактовки `direction`/`unit` доступны навсегда. Код Б14 не содержит ни одного метрического ключа — всё через каталог; seed-YAML в поставке. Пять слоёв: `anthro` (число), `photo4` (приватное ПДн-медиа), `wellbeing` (шкальные), `functional` (число), `checkup` (15 утверждений × 0–3 + агрегаты). Смена `unit_ref`/`direction`/семантики = только новый ключ. Смена состава Чек-Апа или порогов зон — новая версия `checkup_config`, старые записи читаются в своей версии; сравнение baseline vs текущий по зонам пересчитывается по актуальной версии с пометкой.

## 14.3. Чек-Ап в журнале

Чек-Ап хранится в `measurements_log` детально: 15 строк ответов (`inflammation_q01..q15`, `direction=lower_better`) + производная `inflammation_total` (0..45) + производная `inflammation_zone` (0=green, 1=yellow, 2=red; `direction=lower_better`, `enum_zone`), все 17 строк в одной транзакции; частичное заполнение — только ответы, агрегаты не создаются. Расчёт зоны — `auto_scored_by_bot` в Б5, материализуется в Б14. Слой Чек-Ап в проекции: зона крупно, тренд суммы, раскрывающаяся детализация по 15 утверждениям.

## 14.4. Карта изменений

Карта изменений — инкрементально материализуемая проекция `change_map_cache(pid, layer, window)`, окно K=6 по умолчанию (baseline + 5 последних + текущий), полная история on-demand с пагинацией. Агрегация по локальным дням участника через `tz_at(pid, taken_at)`, хранение UTC. Инвалидация кэша: новая строка по метрике слоя, `author_correction`, `revert_marker`, `refund_notice`, смена версии каталога → метка `stale=true`, ленивый пересчёт при чтении. UI-адресаты Карты: Б6 (карточка Автора), Б10-UI (главный экран бота), Mini App (Telegram WebApp — новый MVP-канал). Автор видит любого (кроме erased); участник — только своё; Помощник — по трёхрежимному флагу `view_participant_photos ∈ {never, on_grant, always}` (default `never`), каждый показ фото Помощнику — `pii_access_log`.

## 14.5. Фото-слой как приватное ПДн-медиа

Фото-слой — приватное ПДн-медиа контура `pii_media`, вынесен из-под аксиомы Б15 «бот не хостит медиа» (та применима только к курсовому контенту). Три канала показа: (1) Mini App через S3 pre-signed URL, TTL 5м, SSE-KMS шифрование, no-referrer, `fetch→blob→URL.createObjectURL` с revoke после закрытия — основной путь MVP; (2) bot `sendPhoto(file_id)` — fallback и канал для чата (когда Mini App недоступен или клиент старый); (3) bot `sendPhoto(InputFile из S3)` — если `file_id` мёртв. Загрузка: два входа — бот и Mini App (pre-signed PUT напрямую в S3, минуя backend), оба через контракт `submit_photo` с `client_op_id`. S3-раскладка `pii/photos/{pid_bucket}/{pid}/{event_id}/{side}.jpg`, versioning + SSE-KMS. EXIF стрипается на входе, JPEG-нормализация max 2048px, hash файла в journal. Фото — приватная категория, требует явного согласия по ст.10 152-ФЗ (чекбокс Б4 при онбординге); отказ → фото-слой скрыт в Mini App и не запрашивается опросом, остальные слои работают.

## 14.6. Erasure и retention фото

Erasure участника: `pid → erased:{hash}`, числовые ряды остаются обезличенными (erasure > identity), TG `file_id` затирается; `blob_ref` (S3 key) передаётся через `erasure_blob_refs(pid)` в `erasure_blacklist` Б15; Б15 удаляет все версии S3-объекта (не delete marker, а `DeleteObjectVersion` для каждой) + обеспечивает re-apply после restore. Object Lock не применяется к фото (только к аудит-логам). Retention фото: активность + 12 месяцев после последнего события, далее auto-erasure только фото-слоя через `photo_retention_worker` (Б15).

## 14.7. Экспорт «Мои данные»

Экспорт «Мои данные» — юридическая обязанность (152-ФЗ ст.14, GDPR Art.15). Два триггера: bot-команда `/export` и `POST /miniapp/v1/export/request`. Единый воркер Б15: формирует zip (JSON + CSV + `photos/` с нормализованными JPEG); доставка — либо bot `sendDocument`, либо signed-URL из S3 (TTL 15м) для скачивания через Mini App; при zip > 50 Мб через bot — раздельная отправка. Отказ участника от согласия не блокирует его собственный экспорт (право доступа). Экспорт для Автора — по обоснованию, аудит-запись в Б6. Аудит `data_export_event` — оба канала, оба вида запросов.

## 14.8. Публикация Этапа и publish_epoch

Публикация Этапа: Б14 единственный владелец `publish_epoch` (монотонно per `stage_id`). Инкремент + вставка в `stage_publish_log` + запись в transactional outbox — одна транзакция. Кнопка «Опубликовать» защищена `publish_intent_token` (TTL 5м). Снятие Этапа = публикация с `withdrawn=true` и `epoch++`; повторный выпуск — ещё `epoch++` с `withdrawn=false`. Событие `publish_stage{stage_id, publish_epoch, withdrawn, published_at, actor_id, schema_version}` уходит at-least-once; потребители (Б10, Б5, Р132, Р143) дедуплицируют по `(stage_id, publish_epoch)`. При `withdrawn=true` Б10 откатывает `content_frontier` у не начавших, сохраняет пройденное у продвинувшихся; `stage_survey.open|partial` → `stalled`; при повторном выпуске — `stage_survey` перевыдаётся с новым epoch. Любой потребитель обязан прочитать фазу Б10 перед персональной доставкой — исключений нет.

## 14.9. stage_survey — обязательный срез

`stage_survey` создаётся только по `stage_completed(pid, stage_id, epoch)` от Б10. Для open_ended-Этапов — Б10 генерирует по команде Автора. Б14 читает `stage_definition.surveys[]` у Б5 и открывает по каждому `kind` запись `stage_survey(status=open)`. Опрос — обязательный гейт с явным opt-out: `done` или `partial_acknowledged` (после ≥1 заполненного слоя) снимают гейт; `open|partial` — не снимают, но жизни не жгут. Гейт — в Б10, факт статуса — у Б14. Незакрытый срез — постоянный CTA в главном экране бота и в Mini App (П-21). Через Mini App срез проходится теми же эндпоинтами (`/survey/*/answer`, `/finalize`); через бот — как раньше. Тексты и частота напоминаний — Б9.

## 14.10. «Тревожная динамика»

«Тревожная динамика» — событие уровня закрытия среза, не замера. При переходе `stage_survey → done|partial_acknowledged` Б14 сравнивает метрики текущего среза с предыдущим (первый срез не сравнивается); при разнице > `metric_catalog.dynamics_threshold` в худшую сторону по `direction` эмитит `dynamics_alert` в outbox; текст — Б9, доставка — Б15, тема — `dynamics` (Б8); guard по фазе Б10 на стороне тракта. Коррекция задним числом → компенсирующее `dynamics_alert_revised`.

## 14.11. ТЗ участника (таймзона)

ТЗ участника — IANA-строка, собирается в онбординге (Б4 → Б14 `set_tz`), история — append-only `tz_change_log`. Правило «со следующего дня» — валидатор `effective_from = date(requested_at, new_tz)+1`; читатели используют `tz_at(pid, ts)`, хардкод оффсета запрещён. Fallback — IANA `Europe/Moscow` с `tz_source=fallback`. DST — только IANA.

## 14.12. Refund и revert — иммунитет журнала

Refund Этапа: `measurements_log` и `stage_survey` сохраняются (append-only); Карта продолжает показывать. Revert (Б13): `revert_marker`, записи не откатываются, `stage_survey` помечается `reverted=true`, при повторном прохождении перевыдаётся с новым epoch. Ни refund, ни revert не мутируют журнал.

## 14.13. Mini App-интеграция (v3.3)

Mini App — новый read+write канал, не заменяющий бот, а дополняющий; вход через Menu Button `web_app` (Б10 переключает `F_TG_5_prime`). Auth: `POST /miniapp/auth` валидирует Telegram `initData` (HMAC-SHA256 с `secret_key = HMAC("WebAppData", bot_token)`), проверяет `auth_date` TTL 5м (write) / 60м (read) — анти-replay; выдаёт `session_jwt` HS256 TTL 60м с `sub=pid`, `role`, `photo_consent`, `helper_perms`. Маппинг `tg_user_id ↔ pid` — Б1; несуществующий `tg_user_id` → 403 (участник создаётся только через bot-онбординг). Rate-limit: 60/мин/pid на API, 10/мин на unauth `/auth`. Все Mini App-запросы проходят тот же resolver видимости Б14 (участник → своё, Автор → все кроме erased, Помощник → по флагу). API v1: `/map/summary`, `/map/layer/{layer}`, `/map/layer/{layer}/full`, `/checkup/latest`, `/survey/current`, `/survey/*/answer`, `/survey/*/finalize`, `/photo/upload`, `/photo/{event_id}/url`, `/export/request`, `/export/status`. Версионирование через префикс `/miniapp/v{N}/`; breaking change = новый major; v1 поддерживается ≥6 месяцев после v2. Feature flag `miniapp_enabled` per pid → cohort → global (владелец — Б1). Bot-fallback работает всегда: если Mini App выключен или клиент устарел — текст+фото в чат (П-21). Оффлайн: последний snapshot кэшируется в IndexedDB (TTL 24ч), write-операции — очередь с retry по `client_op_id`; фото офлайн не грузятся. Уведомления — только через бота (у Mini App нет своих push); Mini App использует `Telegram.WebApp.HapticFeedback` и `showAlert` для in-app обратной связи. Безопасность: строгий CSP (`default-src 'self'`, no `unsafe-eval`, `frame-ancestors https://web.telegram.org https://telegram.org`, `img-src 'self' https://{s3-domain} data:`), `Referrer-Policy: no-referrer`, signed-URL никогда не в `<a href>`/history — только `fetch→blob→URL.createObjectURL` с `revokeObjectURL`; все user-generated тексты HTML-escape; логирование CSP-нарушений в security-audit.

## 14.14. Delivery-health и durability

Delivery-health: Б14 обеспечивает поля (`outbox.created_at`, `outbox.sent_at`, `dlq.reason`) + новые метрики Mini App (`auth_success_rate`, `api_p95_latency`, `s3_signed_url_error_rate`, `csp_violation_reports`); экспозиция и алёрты — Б15. Durability — полностью Б15: WAL, backup 3-2-1 для PG (tier-1: `measurements_log`, `stage_publish_log`, `metric_catalog_log`), PITR, S3 versioning + SSE-KMS + cross-region replication + weekly snapshot в другой провайдер, `erasure_blacklist` с re-apply для PG и S3.

## 14.15. Философия «финиша нет»

`stage_id={track}.{ord}` — расширяемая строка, границ на количество Этапов/слоёв/замеров/версий каталога нет; партиционирование `measurements_log` по `pid_bucket` (hash 64); каталог — append-only с tombstone; отставший участник видит свой текущий Этап, не финальный. Mini App отражает эту логику — нет экрана «курс окончен», есть «текущий Этап N» и «пройденное».

## 14.16. Межблочные контракты

`active_participants_for_broadcast` — read-only проекция в схеме Б14, читающая `b10.participant_state`; смена модели Б10 → обязательное обновление view (CI `view_integrity_check`). Все потребители `publish_stage` и `dynamics_alert` обязаны читать фазу Б10 перед доставкой. Маппинг `tg_user_id ↔ pid` — Б1, Б14 только читает. Feature flag `miniapp_enabled` — Б1.

## 14.17. Дельта v3.3 → v3.4 (подшита снизу, тело v3.3 не переписано)

Дельта v3.3 → v3.4 закрывает 11 выявленных проблем и 8 упущений собственного аудита. Ключевое:

**Фото-загрузка перестроена в двухбакетную схему.** Mini App и бот теперь пишут в staging-bucket по pre-signed PUT с TTL 5м и хардлимитом 10Мб/whitelist MIME; S3 Event Notification триггерит `photo_ingest_worker` в Б15, который валидирует magic bytes, стрипает EXIF, конвертирует HEIC/PNG/WebP → JPEG progressive ≤2048px, считает hash, кладёт в `pii-photos` с ключом `pii/photos/RU/{pid_bucket}/{pid}/{event_id}/{side}.jpg` и удаляет staging. Только после успешного ingest создаётся запись в `measurements_log` с `blob_ref`. Ingest идемпотентен по `client_op_id`; staging чистится lifecycle-политикой 24ч. Ни один байт фото не попадает в основной bucket без прохождения ingest — архитектурная гарантия EXIF-strip.

**Локализация ПДн.** Вся ПДн-инфраструктура (primary + replica + snapshot) физически на территории РФ; в S3-ключ вписывается `region_tag`, воркеры Б15 отклоняют репликацию с несовпадающим тегом. Cross-region в другую юрисдикцию — hard-block; трансграничная передача возможна только по явному согласию участника + уведомлению РКН (не MVP-сценарий).

**Baseline-integrity через override.** Физическая первая запись остаётся неприкосновенной (`is_baseline_physical=true`, INV-B14-BASELINE в силе); над ней — append-only таблица `baseline_override_log` с записями от Автора (`target_event_id`, `reason`, аудит). Проекция Карты использует эффективный baseline = последний override, либо физическая первая при отсутствии override. Участник видит исходное значение как «исторический факт» + иконку «i» с пояснением коррекции. Права на override — только Автор (не участник, чтобы избежать злоупотреблений после 24ч-окна правки).

**Thundering herd на инвалидации каталога** снят через тройную защиту: stale-while-revalidate (устаревшие данные с флагом `revalidating`, пересчёт в фон), single-flight lock на `(pid, layer)`, фоновый прогрев для активных (`b10.last_seen_at ≤ 24ч`) с приоритизацией по recency; неактивные — по факту следующего чтения. Read-latency Карты гарантирована ≤500мс.

**Withdrawn semantics для survey уточнены.** Старые `stage_survey` от снятого Этапа → `status=stalled`, ответы в `measurements_log` сохраняются как факт (не мешают Карте); при повторной публикации того же `stage_id` с новым epoch — новая пустая запись `stage_survey(status=open)`, чистый лист для участника, старая доступна в истории с меткой «Этап был снят и переопубликован».

**Оффлайн UX замкнут.** `GET /miniapp/v1/sync/status?since={ts}` возвращает `accepted`/`rejected`/`pending` — Mini App синхронизирует IndexedDB-очередь на старте и показывает баннер о несохранённом; коды причин отказа (`value_out_of_range`, `unknown_metric_key`, `consent_missing`, `quota_exceeded`, `schema_version_unsupported`, `duplicate_op`, `unsupported_format`) — тексты Б9. Rejected хранятся 30 дней, dedup — 24ч. IndexedDB очищается на закрытие Mini App и при смене `tg_user_id`.

**WebView OOM обход.** Файлы ≤10Мб — blob через `URL.createObjectURL` (Р343); файлы >10Мб (архивы экспорта) — прямая навигация `window.location.href` со `Content-Disposition: attachment` и обфусцированным именем, скачивание системным диалогом.

**Silent re-auth JWT.** Refresh каждые 45 минут в фоне и за 5 минут до `exp`; перед критичной write-операцией (finalize survey, upload photo, export) — форс-проверка `exp-now > 60с`. При неудаче refresh — не разлогинивание, а накопление write-очереди в IndexedDB до следующего успешного auth.

**CSP уточнён под официальный `telegram-web-app.js`:** `script-src 'self' https://telegram.org`; никаких `unsafe-eval`; `img-src` расширен на `data: blob:` для галерей; `connect-src` ограничен собственным API и S3-доменом РФ; CSP-нарушения репортятся на `/security/csp-report` (эндпоинт Б15).

**Экспорт защищён от CSV injection и file-name leakage.** Строки с `=+-@\t\r` префиксуются `'`; авторитетный формат — JSON + XLSX (type=text); CSV — только по явному запросу с warning. Файлы в архиве именуются `photo_{event_id_short8}.jpg`, `note_{event_id_short8}.txt` — семантика имён вынесена в `manifest.json` внутри архива с hash-верификацией.

**Дополнительно закрыто:** отзыв `photo_consent` триггерит erasure только фото-слоя (числа сохраняются); `photo_ingest_worker` — saga с идемпотентным retry; HEIC/WebP допустимы, SVG hard-block; клиентский `taken_at` валидируется расхождением с `server_received_at` (≥24ч → сервер authoritative + метка `client_time_untrusted=true`); уведомление участника при смене порогов Чек-Апа; миграционный воркер проставляет `region_tag=RU` legacy-объектам.

## 🛡 Блок 14 — Fail-safe

Целостность данных держится на запрете мутаций: шесть журналов (`measurements_log`, `stage_publish_log`, `metric_catalog_log`, `tz_change_log`, `pii_access_log`, `data_export_event`) append-only навсегда, поэтому ни refund, ни revert, ни коррекция Автора не переписывают историю — они добавляют маркеры и override-записи. Каталог метрик не удаляется, только tombstone через `deprecated_at`, что гарантирует читаемость исторических трактовок `direction`/`unit`. Baseline защищён двухслойно: физическая первая запись иммутабельна SQL-триггером, а исправления живут в отдельном append-only override-логе с обязательным аудитом и доступны только Автору.

Идемпотентность закрывает повторы на всех входах: `client_op_id` для замеров, Mini App write-операций и photo-ingest, `(stage_id, publish_epoch)` для публикаций, natural key `event_id` на замерах. Публикация Этапа атомарна вместе с outbox-записью в одной транзакции, событие уходит at-least-once, а дедупликацию обеспечивают потребители. Сквозной consumer-guard: любой потребитель `publish_stage` и `dynamics_alert` обязан прочитать фазу Б10 перед персональной доставкой — исключений нет.

Отказоустойчивость каналов построена на паритете: любая функция Mini App имеет bot-путь, feature flag выключает Mini App мгновенно, при недоступности signed-URL срабатывает deep-link в бот с `sendPhoto(file_id)`, а пустое состояние отдаётся туториалом, а не пустым экраном (П-21). Истечение JWT не приводит к потере записи — write-операции накапливаются в локальной очереди до успешного refresh; оффлайн-расхождения разрешаются через `/sync/status` с явными кодами причин отказа. Read-latency Карты ограничена сверху тройной защитой от thundering herd: stale-while-revalidate, single-flight lock на `(pid, layer)` и фоновый прогрев активных.

Приватный контур защищён по конструкции: ни один байт фото не попадает в основной bucket без `photo_ingest_worker`, что делает EXIF-strip архитектурной гарантией, а не дисциплиной; signed-URL никогда не попадает в `<a href>` или history; репликация ПДн вне РФ — hard-error по `region_tag`. Erasure удаляет все версии S3-объекта с re-apply после restore, при этом числовые ряды остаются обезличенными (erasure > identity), а отзыв согласия на фото стирает только фото-слой. Экспорт не исполняется как формула ни в одном формате, а имена файлов в архиве не несут семантики — связь только через `manifest.json` с hash-верификацией.

## Долги и стыки

Блок 14 владеет фактами и контрактами, но почти вся инфраструктура вынесена наружу. Ниже — что кому передано.

| Что вынесено | Куда | Состояние |
|---|---|---|
| WAL, backup 3-2-1 для PG (tier-1), PITR | Блок 15 | ⏳ не начат |
| S3 bucket, versioning, SSE-KMS, lifecycle | Блок 15 | ⏳ не начат |
| S3 3-2-1 внутри РФ: primary + replica + weekly snapshot (Р352) | Блок 15 | ⏳ не начат |
| `erasure_blacklist` + restore re-apply (PG + S3, A4) | Блок 15 | ⏳ не начат |
| `blob_ref_materializer` (TG → S3) | Блок 15 | ⏳ не начат |
| `photo_ingest_worker` (staging → pii-photos, saga, EXIF-strip) | Блок 15 | ⏳ не начат |
| `photo_retention_worker` (object tag → lifecycle) | Блок 15 | ⏳ не начат |
| `signed_url_service` (pre-sign, TTL 5м фото / 15м экспорт) | Блок 15-инфра | ⏳ не начат |
| `export_worker` (два триггера, две доставки) | Блок 15 | ⏳ не начат |
| Мониторинг Mini App: `auth_success_rate`, `api_p95`, `s3_url_errors`, `csp_violations` | Блок 15 | ⏳ не начат |
| Хостинг фронта Mini App, доставка CSP-заголовков, TLS, `/security/csp-report` | Блок 15-инфра | ⏳ не начат |
| DLQ A3 (совместимость по `schema_version`), notification transport, DLQ-алёрты | Блок 15 | ⏳ не начат |
| Реестр `tg_user_id ↔ pid`; feature flag `miniapp_enabled` (pid → cohort → global); `helper.permissions.view_participant_photos` | Блок 1 | ⚠️ входящий долг в закрытый блок |
| Menu Button → `web_app` (`F_TG_5_prime`), кнопка «📊 Карта» в главном меню, сохранение bot-fallback выдачи Карты | Блок 10 | ⚠️ конфликт с L1 Recovery Ladder, см. ниже |
| Гейт жизненного цикла по незакрытому срезу | Блок 10 | ✅ модель фаз есть (Б10, шаги 5–8) |
| `stage_definition.surveys[]`, `checkup_config`, `auto_scored_by_bot` | Блок 5 | ✅ опора существует |
| Чекбокс `photo_consent` (ст.10 152-ФЗ) при онбординге | Блок 4 | ⏳ дописать в Б4 |
| Тексты: напоминания о срезе, готовность экспорта, `dynamics_alert`, коды отказов sync, уведомление о смене порогов Чек-Апа | Блок 9 | ⏳ дописать в Б9 |
| Тема `dynamics` | Блок 8 | ⏳ дописать в Б8 |
| Композиция рассылки (Р132) | Блок 5 / Блок 10 | ⏳ парковка |
| Карточка Автора с фото-слоем + аудит экспорта по обоснованию | Блок 6 | ⏳ дописать в Б6 |
| Основание для signed-URL на ПДн-медиа, TTL, логирование доступа, экспорт как реализация Art.15, политика локализации РФ, отзыв согласия retro, ежегодная сверка с реестром РКН | Юридический блок | ⏳ не начат |
| `refund_event`, `revert_event` — только чтение | Блок 16, Блок 13 | ✅ опоры существуют |

## YAML — единый контракт Блока 14 (v3.3, финальный)

```yaml
block: 14
title: "Данные, Карта изменений, замеры, publish_stage, ТЗ, финиша нет, Mini App"
version: v3.3

axioms:
  X1: "metric_catalog конфиг-driven; код Б14 не хранит ключей/единиц"
  X2: "фото — приватное ПДн-медиа контура pii_media; отдельная политика от аксиомы Б15 'бот не хостит медиа'; видят участник (свои) и Автор"
  X3: "baseline сквозной от первого входа; рестарт не переопределяет"
  X4: "Mini App — дополнительный канал; bot-fallback работает всегда; ни одна фича не требует Mini App эксклюзивно"

owns:
  - measurements_log
  - metric_catalog_log + metric_catalog_current
  - unit_dict (immutable)
  - change_map_cache
  - stage_survey
  - stage_publish_log
  - publish_epoch
  - participant.tz + tz_change_log
  - outbox.publish_stage
  - outbox.dynamics_alert + outbox.dynamics_alert_revised
  - restart_marker + revert_marker + refund_marker
  - data_export_event
  - pii_access_log
  - checkup_config
  - miniapp_session (session_jwt state, короткоживущее)
  - miniapp_client_op_dedup (client_op_id TTL 24ч)

reads_only:
  - b10.participant_state
  - stage_definition (Б5), checkup_config (совм. с Б5)
  - author.whitelist (Б1)
  - helper.permissions (Б1)
  - feature_flags.miniapp_enabled (Б1)
  - tg_user_id_to_pid mapping (Б1)
  - refund_event (Б16), revert_event (Б13)
  - photo_consent_flag (правовой блок / Б4)

does_not_own:
  - WAL / backup_3_2_1 PG / PITR                  # → Б15
  - S3 bucket / versioning / SSE-KMS / lifecycle  # → Б15
  - S3 cross-region replication + snapshot        # → Б15
  - erasure_blacklist + restore_reapply (PG+S3)   # → Б15 (A4)
  - blob_ref_materializer (TG→S3)                 # → Б15
  - photo_retention_worker                        # → Б15
  - signed_url_service (S3 pre-sign)              # → Б15-инфра
  - export_worker (zip + доставка)                # → Б15
  - notification_transport / DLQ_alerts           # → Б15
  - dynamics topic (тема Б8)                      # → Б8
  - alert_text_composition                        # → Б9
  - lifecycle_gate_on_survey                      # → Б10
  - broadcast_composition (Р132)                  # → Б5/Б10
  - menu_button_web_app_config                    # → Б10
  - tg_user_id_to_pid_mapping + feature_flags     # → Б1
  - legal_basis + photo_consent_text              # → правовой блок
  - miniapp_frontend_code + CSP_headers_delivery  # → Б15-инфра

invariants:
  INV-B14-APPEND
  INV-B14-BASELINE
  INV-B14-EPOCH-MONOTONIC
  INV-B14-EPOCH-ON-ANY-CHG
  INV-B14-TX-OUTBOX
  INV-B14-TZ-NEXTDAY
  INV-B14-TZ-VIA-FN
  INV-B14-DIRECTION-CATALOG
  INV-B14-UNIT-IMMUTABLE
  INV-B14-CATALOG-APPEND
  INV-B14-NO-FINISH
  INV-B14-ERASURE (PG + S3 all versions)
  INV-B14-SCHEMA-VERSION
  INV-B14-CONSUMER-GUARD
  INV-B14-REFUND-REVERT-IMMUNE
  INV-B14-SURVEY-TRIGGER (только Б10)
  INV-B14-NO-CODE-METRICS
  INV-B14-PII-MEDIA-VIA-INFRA: "фото — либо sendPhoto бота, либо signed-URL от Б15-инфры; веб-слой самого бота фото не отдаёт"
  INV-B14-EXPORT-RIGHT
  INV-B14-DYNAMICS-SURVEY (уровень среза)
  INV-B14-PII-ACCESS-AUDIT
  INV-B14-MINIAPP-BOT-PARITY: "любая функция Mini App имеет bot-путь (fallback)"
  INV-B14-MINIAPP-SAME-RESOLVER: "Mini App проходит тот же resolver видимости, что и бот"
  INV-B14-INITDATA-TTL: "auth_date ≤5м на write, ≤60м на read"
  INV-B14-SIGNED-URL-TTL: "signed-URL к фото ≤5м; к export-архиву ≤15м"
  INV-B14-CSP-STRICT: "CSP без unsafe-eval; frame-ancestors только Telegram domains"
  INV-B14-NO-URL-LEAK: "signed-URL никогда не в <a href> / history; только fetch→blob→revoke"

decisions:
  # v3.2 сохранены (Р200–Р324) — не повторяю; ниже только Mini App-дельты

  # Auth
  R325: "auth_date TTL: 5м (write), 60м (read); авто-refresh через Telegram.WebApp.ready()"
  R326: "session_jwt HS256 TTL 60м; sub=pid, role, photo_consent, helper_perms"
  R327: "tg_user_id→pid маппинг в Б1; несуществующий → 403; авто-создание участника через Mini App запрещено"
  R328: "rate-limit: 60/мин/pid на API, 10/мин на unauth /auth; 429 при превышении"

  # API surface
  R329: "API v1 endpoints: /map/summary, /map/layer/{layer}, /map/layer/{layer}/full, /checkup/latest, /survey/current, /survey/*/answer, /survey/*/finalize, /photo/upload, /photo/{event_id}/url, /export/request, /export/status"
  R330: "два входа фото — bot и Mini App; Mini App через pre-signed PUT в S3; идемпотентность по client_op_id"

  # S3 контур
  R331: "S3 layout: pii/photos/{pid_bucket}/{pid}/{event_id}/{side}.jpg; versioning+SSE-KMS; pid_bucket = hash64(pid)%256"
  R332: "fallback при 5xx на signed-URL: deep-link в бот → sendPhoto(file_id)"
  R333: "signed-URL включает response-cache-control: private, max-age=300; CDN между Mini App и S3 запрещён"
  R334: "erasure S3 = DeleteObjectVersion для всех версий; erasure_blacklist хранит s3_key+pid"
  R335: "Object Lock применяется только к аудит-логам (stage_publish_log, pii_access_log, data_export_event); к фото — нет"
  R336: "S3 3-2-1: primary + cross-region replica + weekly snapshot к другому провайдеру (90д retention)"
  R337: "photo_retention_worker: воркер помечает object tag to_delete → S3 lifecycle физически удаляет"

  # UX / Product
  R338: "пустое состояние = туториал с demo=true, не пустой экран (П-21)"
  R339: "оффлайн: IndexedDB кэш snapshot (TTL 24ч, stale-flag), write-очередь с retry по client_op_id; фото офлайн не грузятся"
  R340: "Mini App не имеет собственных push; уведомления только через бота; HapticFeedback + showAlert для in-app"

  # Security
  R341: "CSP: default-src 'self'; no unsafe-eval; frame-ancestors только Telegram domains; img-src 'self' https://{s3-domain} data:"
  R342: "все user-generated тексты HTML-escape; никакого innerHTML"

  R343: "Referrer-Policy: no-referrer; signed-URL через fetch→blob→URL.createObjectURL; revoke после закрытия"
  R344: "utility-проверка initData.user.id vs query_id origin; логирование несоответствий в security-audit"

  # Экспорт
  R345: "экспорт — единый воркер Б15, два триггера (bot + Mini App); доставка либо sendDocument, либо signed-URL S3 TTL 15м"

  # Совместимость и релиз
  R346: "API префикс /miniapp/v{N}/; breaking change = major; v1 ≥6мес после v2; X-MiniApp-Client-Version + X-Server-API-Version"
  R347: "feature_flag miniapp_enabled per pid → cohort → global (Б1); мгновенное выключение; bot-fallback всегда работает"
  R348: "mobile-first; Telegram.WebApp.platform-check; graceful degradation недоступных фич"

contracts_out:
  # v3.2 сохранены + новые:
  signed_url_request:
    to: Б15-infra (signed URL service)
    payload: {s3_key, ttl, response_headers, actor_pid, purpose}
  export_archive_key:
    to: Б15-infra
    payload: {pid, requested_by, format}

contracts_in:
  # v3.2 сохранены + новые:
  miniapp_auth:
    from: Mini App клиент
    payload: {initData (raw), client_op_id}
    returns: {session_jwt, pid, role, photo_consent, helper_perms, api_version}
  miniapp_api_call:
    from: Mini App клиент
    payload: {session_jwt, ...endpoint-specific}
    guard: [jwt_valid, rate_limit, feature_flag, visibility_resolver]
  csp_violation_report:
    from: Mini App браузер
    payload: {blocked-uri, violated-directive, ...}
    to_log: security-audit
  tg_user_id_to_pid:
    direction: in
    from: Б1
    payload: {tg_user_id → pid}

publish_epoch_owner: block14

api_surface:
  base: /miniapp/v1
  auth: POST /auth (initData → session_jwt)
  endpoints:
    - GET  /map/summary
    - GET  /map/layer/{layer}
    - GET  /map/layer/{layer}/full     # cursor pagination
    - GET  /checkup/latest
    - GET  /survey/current
    - POST /survey/{id}/answer         # idempotent by client_op_id
    - POST /survey/{id}/finalize       # done | partial_acknowledged
    - POST /photo/upload               # pre-signed PUT via S3
    - GET  /photo/{event_id}/url       # signed-URL TTL 5м
    - POST /export/request
    - GET  /export/status
  rate_limits:
    /auth: 10 rpm unauth
    default: 60 rpm per pid

db_hints:
  partitioning: "measurements_log by pid_bucket (hash 64)"
  s3_layout:    "pii/photos/{pid_bucket}/{pid}/{event_id}/{side}.jpg"
  indexes: [(pid, metric_key, taken_at_ms DESC), (stage_id, publish_epoch), hash(event_id) unique, partial (is_baseline=true), (pid, layer)]
  cache: "change_map_cache incremental; miniapp_client IndexedDB TTL 24ч"

security:
  initData_validation: "HMAC-SHA256 с secret_key = HMAC('WebAppData', bot_token)"
  auth_date_ttl: {write: 300, read: 3600}
  session_jwt: {alg: HS256, ttl: 3600, claims: [sub, role, photo_consent, helper_perms, exp, iat]}
  csp: "strict; frame-ancestors: [https://web.telegram.org, https://telegram.org]"
  referrer: no-referrer
  signed_url_ttl: {photo: 300, export: 900}
  rate_limits: above
  csp_violation_reporting: /security/csp-report

boundaries:
  left:  "Б4 (set_tz, submit_measurement, photo_consent), Б5 (stage_definition, checkup_config), Б10 (stage_completed, menu_button web_app), Б13 (revert), Б16 (refund), Б1 (tg_user_id↔pid, helper.permissions, feature_flags), правовой блок, Автор (publish, correction, catalog_upsert, export), Mini App клиент (auth, API calls)"
  right: "Б10 (publish_stage, gate-факт), Б5 (витрина), Р132 (рассылка), Б6 (карточка Автора + фото), Б10-UI (участник), Mini App (Карта, фото, срез, экспорт), тракт уведомлений (Б9+Б15+Б8) для dynamics_alert, Б15-инфра (S3 signed-URL, export worker, blob materializer, retention, erasure, durability)"
  top:   "нет выпускника (философия финиша нет)"

stub_tails:
  # v3.2 сохранены + Mini App-дельты
  - {to: Б1,  what: "tg_user_id↔pid registry; feature_flags.miniapp_enabled per pid/cohort/global; helper.permissions.view_participant_photos"}
  - {to: Б10, what: "Menu Button → web_app (F_TG_5_prime); кнопка '📊 Карта' в главном меню; bot-fallback выдача Карты сохраняется"}
  - {to: Б15, what: "S3 bucket с versioning + SSE-KMS; layout pii/photos/{pid_bucket}/{pid}/{event_id}/{side}.jpg"}
  - {to: Б15, what: "signed-URL сервис (TTL 5м фото, 15м экспорт); pre-signed PUT для upload"}
  - {to: Б15, what: "erasure S3 = DeleteObjectVersion всех версий; интеграция с erasure_blacklist + restore-reapply"}
  - {to: Б15, what: "S3 бэкап 3-2-1: primary + cross-region replica + weekly snapshot к другому провайдеру"}
  - {to: Б15, what: "photo_retention_worker: object tag to_delete → S3 lifecycle"}
  - {to: Б15, what: "blob_ref_materializer (TG→S3)"}
  - {to: Б15, what: "export worker (два триггера, две доставки)"}
  - {to: Б15, what: "мониторинг Mini App: auth_success_rate, api_p95, s3_url_errors, csp_violations"}
  - {to: Б15-infra, what: "хостинг Mini App фронта; строгий CSP; TLS; CSP violation reporting endpoint"}
  - {to: Б4,  what: "чекбокс photo_consent (ст.10 152-ФЗ) при онбординге"}
  - {to: Б9,  what: "тексты Mini App-нотификаций в бота (напоминания о срезе, готовность экспорта, dynamics)"}
  - {to: правовой блок, what: "основание signed-URL для ПДн-медиа; TTL; логирование доступа; экспорт как реализация Art.15"}

patch:
  from_version: v3.3
  to_version:   v3.4
  scope:        "закрытие 11 замечаний аудита + 8 внутренних находок"

new_axioms:
  X5: "EXIF-strip и нормализация фото — архитектурная гарантия через staging + photo_ingest_worker; ни один байт в pii-photos без ingest"
  X6: "вся ПДн-инфраструктура физически в юрисдикции РФ; трансграничная передача — только по явному согласию (не MVP)"

new_or_updated_invariants:
  INV-B14-EXIF-VIA-INGEST:      "фото попадает в pii-photos только через photo_ingest_worker"
  INV-B14-DATA-LOCALITY-RU:     "любая ПДн-копия физически в РФ; region_tag обязателен на S3-объектах"
  INV-B14-BASELINE-PHYSICAL:    "is_baseline_physical immutable; effective_baseline вычисляется поверх append-only override-лога"
  INV-B14-BASELINE-OVERRIDE-AUTHOR-ONLY: "baseline_override — только Автор, никогда не сам участник"
  INV-B14-READ-LATENCY-BOUND:   "Карта отдаётся ≤500мс всегда (stale-while-revalidate + single-flight)"
  INV-B14-SURVEY-STALLED-DATA-KEPT: "ответы stalled-survey остаются в measurements_log как факт"
  INV-B14-JWT-NO-DATALOSS:      "истечение JWT не приводит к потере write; локальная очередь до успешного refresh"
  INV-B14-EXPORT-NO-INJECTION:  "экспорт не выполняется как формула ни в одном формате"
  INV-B14-EXPORT-FILENAMES-OPAQUE: "имена файлов в архиве не несут семантики; связь только через manifest.json"
  INV-B14-CLIENT-TIME-BOUNDED:  "расхождение taken_at и server_received_at >24ч → сервер authoritative"
  INV-B14-INGEST-IDEMPOTENT:    "photo_ingest_worker идемпотентен по client_op_id; staging TTL 24ч"

updates_v33_decisions:
  # правки существующих
  R330_updated: "фото через Mini App: pre-signed PUT в staging (не в pii-photos), TTL 5м, ≤10Мб, MIME whitelist"
  R336_replaced_by: R352
  R343_updated: "blob-путь только для ≤10Мб; >10Мб → прямая навигация (Р368)"
  R341_replaced_by: R372  # CSP с telegram.org в script-src

new_decisions:
  # F1 — EXIF/staging
  R349: "двухбакетная схема: staging (pre-signed PUT, TTL 5м, ≤10Мб, MIME whitelist) → photo_ingest_worker → pii-photos"
  R350: "polling /photo/{client_op_id}/status до готовности; rejected с reason_code"
  R351: "bot-загрузка идёт тем же ingest-путём (getFile → staging)"

  # F2 — Локализация ПДн
  R352: "S3 3-2-1 полностью в РФ: primary (ru-central1-a) + replica (ru-central1-b или второй РФ-провайдер) + snapshot (третий РФ-контур)"
  R353: "region_tag=RU в S3-ключах; репликация вне РФ — hard-error"
  R354: "правовой блок фиксирует политику локализации; ежегодная сверка с реестром РКН"

  # F3 — Baseline override
  R355: "разделение: is_baseline_physical (SQL-триггер, immutable) vs effective_baseline (вычисляемая проекция)"
  R356: "baseline_override_log (pid, metric_key, target_event_id, actor, reason, at, schema_version)"
  R357: "baseline_override — только Автор; аудит обязателен"
  R358: "UI: иконка 'i' на baseline-точке с raison и датой; исходное значение видно как исторический факт"
  R359: "baseline_override инвалидирует change_map_cache(pid, layer)"

  # F4 — Thundering herd
  R360: "stale-while-revalidate + single-flight lock + фоновый прогрев для active pids (b10.last_seen_at ≤24ч)"
  R361: "UI-флаг revalidating=true с индикатором, экран не блокируется"
  R362: "sem-recalc = 8 параллельных на инстанс; SLA пересчёта K=6 ≤30с"

  # F5 — Withdrawn survey
  R363: "withdrawn → stalled; ответы в journal сохранены; новая публикация → новый stage_survey(status=open), чистый лист"
  R364: "ответы stalled-survey участвуют в Карте (данные, не черновик)"

  # F6 — Sync status
  R365: "GET /miniapp/v1/sync/status?since={ts} → {accepted, rejected, pending}"
  R366: "reason_code enum: value_out_of_range, unknown_metric_key, consent_missing, quota_exceeded, schema_version_unsupported, duplicate_op, unsupported_format"
  R367: "dedup client_op_id 24ч; rejected retention 30 дней"

  # F7 — WebView OOM
  R368: "порог 10Мб: ≤10Мб blob-путь, >10Мб прямая навигация с Content-Disposition attachment"
  R369: "экспорт всегда через прямую навигацию"

  # F8 — Silent re-auth
  R370: "refresh каждые 45м + за 5м до exp; не разлогинивать при неудаче — очередь"
  R371: "перед finalize/upload/export — форс-проверка exp-now>60с"

  # F9 — CSP уточнение
  R372: "CSP: script-src 'self' https://telegram.org; img-src добавлен data: blob:; connect-src S3-домен РФ; report-uri /security/csp-report"
  R373: "SRI для собственных бандлов; telegram-web-app.js без SRI"

  # F10 — CSV injection
  R374: "экспорт CSV: префикс ' для строк с =+-@\\t\\r; двойное экранирование кавычек"
  R375: "приоритетный формат JSON+XLSX(text); CSV только по явному запросу с warning"

  # F11 — Обфусцированные имена
  R376: "имена файлов в архиве: photo_{event_id_short8}.jpg, note_{event_id_short8}.txt"
  R377: "manifest.json с полным маппингом + hash каждого файла"

  # U-упущения аудита
  R378: "отзыв photo_consent → erasure только фото-слоя (числа остаются); при повторной выдаче — фото собираются с новой baseline (при необходимости через override)"
  R379: "photo_ingest_worker — saga: staging→ingest→measurement→delete staging; идемпотентен по client_op_id; staging GC 24ч"
  R380: "IndexedDB: sensitive ≤24ч; очистка при Telegram.WebApp.close(); очистка при смене tg_user_id"
  R381: "при смене checkup_config — уведомление активным 'пороги обновлены, зона могла измениться'"
  R382: "baseline_override не переписывает исторические dynamics_alert; влияет на следующие сравнения"
  R383: "миграционный воркер: region_tag=RU legacy-объектам; CI-check на все новые"
  R384: "MIME whitelist: jpeg/heic/png/webp; SVG hard-block; конвертация в JPEG progressive ≤2048px"
  R385: "taken_at_ms клиента — hint; при |server_received_at - taken_at| >24ч сервер authoritative + client_time_untrusted=true"

new_contracts_in_out:
  photo_ingest_notification:
    from: S3 (Event Notification)
    to: Б15 photo_ingest_worker
    payload: {bucket=staging, key, client_op_id, pid, size, content_type}
  photo_status:
    endpoint: GET /miniapp/v1/photo/{client_op_id}/status
    returns: {status: uploading|ingesting|ready|rejected, event_id?, reason_code?}
  sync_status:
    endpoint: GET /miniapp/v1/sync/status?since={ts}
    returns: {accepted[], rejected[], pending[]}
  auth_refresh:
    endpoint: POST /miniapp/v1/auth/refresh
    payload: {initData}  # свежая
    returns: {session_jwt, exp}
  baseline_override:
    from: Автор (через админ-панель Б6)
    payload: {pid, metric_key, target_event_id, reason}
  csp_report:
    endpoint: POST /security/csp-report
    to: Б15 security-audit

updated_boundaries:
  right_additions:
    - "Б15-инфра: photo_ingest_worker (S3 staging → pii-photos), CSP report collector"
    - "правовой блок: политика локализации РФ, отзыв согласия retro"
