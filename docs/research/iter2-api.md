# Исследование iter2-api: день в API (iter2-api-1, iter2-api-2)

Окно ИССЛЕДОВАНИЕ, З1, 18.10.2026. Ссылки @cfb089d. Карточек нет. Дополняет docs/research/iter2.md и iter2-2.md.
Сокращения: CT = docs/architecture/build/miniapp-api-contract.yaml; DM = docs/architecture/03-day-mechanics.md; MO = apps/api/app/db/models.py; PR = apps/api/app/projector.py; MA = apps/api/main.py; PA = apps/api/app/participants.py; AB = AGENT-BRIEF.md.
Схема 0007–0009 — по указанию ШТАБа; файлы миграций не читал (§9 Н1, Н2).

## 1. Факты
| Что | Факт | Где |
|---|---|---|
| day/current | только summary, тел нет (D-25) | CT |
| day/report/submit | X-Client-Op-Id обязателен, тело TODO; 409 Conflict = «повтор с тем же client_op_id» | CT |
| Отметки | эндпоинта нет (D-26) | CT |
| Модели | DayMark и IdempotencyKey нет; participant_state не моделируется (xid8); kind один — mini_app_first_consent | MO |
| Проектор | пачка читает только id, pid, kind (без at и payload); ON CONFLICT пишет status_flags = '{}'; переход только из pre_registered; неизвестный kind → WARNING, checkpoint сдвигается; заметка «новые писатели — пересмотреть курсор» | PR |
| Роутеры | новые /miniapp/v1 — только через build_miniapp_v1_router (initData → rate_limit) | MA |
| Участник | find_active_participant — без блокировки, tombstoned = «нет участника» | PA |
| Правила дня | 3.3 — 4–5 блоков, переключаемо до отправки, отправка после отметки всех; 3.5 — все ⭐ + N желательных; 3.6 — сдал → счётчики в ноль; 3.9 — время по серверу; 3.10 — повтор игнорируется; 3.11 — П-31; 3.16 — «всё не выполнено»: жизнь цела, день не засчитан; 3.19 — очередь 10–60 мин, зачёт мгновенный | DM |

## 2. Кто ставит позицию дня при входе по флагу
API в participant_state не пишет (AB §7). Поэтому так:
1. API: POST /miniapp/v1/day/test-enter. Флаг выключен → 404 (как будто маршрута нет). Под замком (§4): активный pid; C0 и C1 действуют (consent_status), иначе 409 RECONSENT_REQUIRED; позиция уже есть → 200 {status: already} без события; иначе INSERT в participant_events: kind day_entered, payload {stage_no: 1, module_no: 1, day_no: 1, source: test_flag}, actor system → commit → 202 {status: entering}. Ложного успеха нет: позиция появится после прохода проектора (~1 с), клиент перечитывает GET.
2. Проектор: UPDATE participant_state SET stage_no, module_no, day_no (из payload), day_started_at = e.at, missed_streak = 0, updated_at, projector_version WHERE pid = :pid AND day_no IS NULL RETURNING pid; 0 строк → WARNING и пропуск. e.at — серверное время события: повторная проекция даёт то же значение. Выдачу следующего дня и перевыдачу (В10) этим же kind делает iter2-api-3, условие WHERE — там.
3. Флаг: Settings DAY_TEST_ENTRY_ENABLED: bool = False; в compose у api — ${DAY_TEST_ENTRY_ENABLED:-false}; в .env.example — «только IRONCLAD».

## 3. Новые kinds без затирания status_flags
- mini_app_first_consent не трогать.
- Новые kinds — только UPDATE своих колонок, без INSERT … ON CONFLICT; status_flags, lifecycle_phase, author_pause_reason, last_seen_publish_epoch в SQL не упоминаются.
- В пачку добавить e.at и e.payload; в лог по-прежнему только id и kind (без payload и pid). PROJECTOR_VERSION → 2.
- day_report_submitted: UPDATE … SET missed_streak = 0 WHERE pid AND day_started_at = payload.day_started_at; если день старый — пропуск (В18).
- «Пришёл» и «+1 ч» в participant_state не пишутся: колонок нет. «Часы» (api-3) берут min(day_marks.at) по pid и текущему day_started_at (app_projector SELECT day_marks — 0008). Событие первой отметки не нужно (В19).
- Тест: строка со status_flags = '{block_lives}' → после day_entered и day_report_submitted флаги те же.

## 4. Advisory lock на pid — нужен
Дыра: курсор берёт e.id > last_event_id. Два писателя одного pid: A получил id 10, B — 11; B закоммитил первым, проектор сдвинул checkpoint до 11 → событие 10 не применится никогда.
Решение: каждый писатель participant_events для уже существующего pid берёт pg_advisory_xact_lock(hashtext('participant:' || pid)) ДО INSERT и держит до commit → id одного pid идут в порядке commit. Писатели: test-enter и report/submit (API), «часы» в проекторе (api-3, В9 = А). first-launch не нужен: новый pid до commit никто не видит.
Под тем же замком, в той же транзакции:
- повторная проверка tombstoned_at IS NULL;
- «проектор догнал pid»: нет событий pid с id > checkpoint.last_event_id; иначе 409 DAY_STATE_SYNCING + Retry-After: 1.
Тогда чтение participant_state даёт устойчивые позицию и day_started_at: проектор этот pid не тронет, новых событий нет. FOR UPDATE и FOR SHARE app_api недоступны: им нужно право UPDATE.
В I2B два ключа, 'life:' и 'participant:' (STATE, долги). При двух ключах в разном порядке возможна взаимная блокировка → один ключ (В20).

## 5. Контракт (D-25, D-26) — предложение
Общее: 401, 429, 503 — как сейчас; нет активного pid → 404 PARTICIPANT_NOT_FOUND; позиции нет → 409 DAY_NOT_STARTED (кроме GET).
- GET /miniapp/v1/day/current → 200 {status: not_started | open | submitted, lives: 0..3, test_entry: bool (true только при включённом флаге и пустой позиции), position?: {stage_no, module_no, day_no}, day_started_at?, blocks?: [{block_id, title_key, help_key, critical, mark: done | not_done | null}], min_optional?, can_submit?}. Отметки — только по текущему day_started_at; submitted — есть day_report_submitted с этим day_started_at.
- PUT /miniapp/v1/day/marks (В16): тело {block_id, value: done | not_done}; лишние поля (pid, day_started_at) игнорируются; block_id — ^[a-z0-9_]{1,32}$ и есть среди блоков текущего дня, иначе 422 BLOCK_NOT_IN_DAY; день сдан → 409 DAY_ALREADY_SUBMITTED; UPSERT day_marks (pid и day_started_at — с сервера) → 200 {block_id, value}.
- POST /miniapp/v1/day/report/submit: X-Client-Op-Id uuid обязателен (нет или не uuid → 422). Тело {marks: [{block_id, value}]} — ровно все блоки дня, без повторов, иначе 422 MARKS_INCOMPLETE. Одна транзакция под замком: проверки §4 → idempotency_keys (key = «day_report:{pid}:{op_id}», params_hash) → день уже сдан → 409 DAY_ALREADY_SUBMITTED → UPSERT отметок → вердикт → INSERT day_report_submitted {day_started_at, verdict, stage_no, module_no, day_no} → commit → 200 {verdict, queued: true}. Тот же op_id: те же параметры → тот же 200 (В15), другие → 409 IDEMPOTENCY_CONFLICT. Сбой БД → 503, ложного 200 нет (П-31). Время сдачи — now() сервера (3.9).
- Вердикт: all_not_done — все not_done; passed — все critical = done и done среди остальных ≥ min_optional; иначе not_passed.
- CT — read-only: правка через DOCS PR + sync, как D-22.

## 6. Заглушка контента
apps/api/content/module_1/ — только .gitkeep (iter2.md §2). Файлы day_01.json и day_02.json: {stage_no, module_no, day_no, min_optional, blocks: [{block_id, critical, title_key, help_key}]}; 4–5 блоков, ≥ 1 critical. JSON Schema рядом; проверка при старте api: битый контент → api не стартует. Тексты — ключи text_registry с заглушками (В17); справка — только текст (В7).

## 7. Требования РЕВЬЮЕРА #95 — по карточкам
pid только из initData через tg_user_registry; day_started_at из participant_state в той же транзакции; белый список block_id + длина; tombstoned → не писать; тест «pid и day_started_at из тела игнорируются» — всё в 2a и 2b. «Проектор только по текущему day_started_at» — в 2b и в api-3.

## 8. Разрезка (3 карточки, строго по порядку)
| # | id | Что | Файлов / строк | РЕВЬЮЕР |
|---|---|---|---|---|
| 1 | iter2-api-1 | контент + схема + GET day/current (только чтение) | ≈ 9 / ≈ 450 | нет |
| 2 | iter2-api-2a | замок pid (app/participant_lock.py) + флаг + POST test-enter + PUT marks + kind day_entered | ≈ 10 / ≈ 550 | да (В3, initData → pid) |
| 3 | iter2-api-2b | report/submit + idempotency_keys + kind day_report_submitted | ≈ 8 / ≈ 550 | да |
Почему: api-2 целиком ≈ 14 файлов и > 800 строк. Флаг перенесён из api-1 в 2a: вход требует замка и kind в проекторе, а api-1 с ним ≈ 14 файлов. Миграций нет. 2a и 2b меняют одни и те же routers/day.py и projector.py → только друг за другом.

## 9. Блокеры и «надо дочитать» (решает ШТАБ)
- Н1. GRANT app_api (0006–0008 не читал). Нужны: SELECT participant_state, participant_state_checkpoints, participant_events; INSERT participant_events; SELECT и INSERT idempotency_keys. Чего-то нет → миграция только с GRANT — единственная «крайняя нужда».
- Н2. Типы и CHECK: day_marks.value; idempotency_keys (ttl, result_ref, params_hash) — файлы 0007, 0008.
- Н3. Есть ли jsonschema в apps/api/requirements.txt (И1: «jsonschema — да»).
- Н4. Размеры для чтения КОДЕРА: config.py, consent_status.py, texts.py, routers/onboarding.py, errors.py, compose (api), tests/conftest.py.
- Н5. Список фаз в CHECK lifecycle_phase (0005) — для В21.
- Н6. docs/STATE.md прочитан не целиком (см. «Прочитано»).

## 10. Вопросы Автору
- В15. Повтор отчёта с тем же X-Client-Op-Id. А — 200 тем же телом (как повтор first-launch). Б — 409, как в CT. Мнение: А — после обрыва связи клиент видит правду; на 409 он покажет ошибку, хотя день уже засчитан.
- В16. Отметки. А — PUT /day/marks по одному блоку, без X-Client-Op-Id (повтор ставит то же значение). Б — с X-Client-Op-Id. Мнение: А.
- В17. Названия блоков. А — ключи text_registry + заглушки в config/texts (по ERRATA; на сервере потом texts load). Б — заглушка прямо в JSON дня. Мнение: А.
- В18. missed_streak = 0 после любого отправленного отчёта (и not_passed, и all_not_done)? А — да (3.16: жизнь не горит). Б — только после passed. Мнение: А. Как считать «пришёл, но не отправил» — решается в api-3.
- В19. Событие первой отметки дня. А — не нужно, «часы» читают day_marks. Б — писать событие. Мнение: А (меньше событий и замков).
- В20. Один ключ замка 'participant:' || pid для всех писателей, включая life_op. Мнение: да, расхождение с I2B записать в DEFECTS.
- В21. Фаза участника при входе по флагу. А — остаётся onboarding (вход тестовый). Б — active. Мнение: А.

## 11. Кандидаты в DEFECTS
- D-25, D-26 — закрыть DOCS PR по §5.
- CT «409 = повтор с тем же client_op_id» расходится с first-launch (повтор → тот же ответ) — по В15.
- Инвариант: каждый писатель participant_events (кроме first-launch) берёт замок pid до INSERT (§4).

## 12. Для ШТАБА (строки STATE)
- «Очередь 0: iter2-api — research docs/research/iter2-api.md (PR без мержа); ждём В15–В21 и Н1–Н5.»
- «Разрезка iter2-api: 1 → 2a → 2b (флаг — в 2a), миграций нет (если Н1 не потребует GRANT).»

## 13. Прочитано (КБ, главный факт)
- docs/process/DESIGNER.md 15,4 — ИССЛЕДОВАНИЕ: файл до 15 КБ, PR без мержа.
- docs/STATE.md 32,8 — прочитан ≈ до конца, обрезан в последнем разделе «Учёт кредитов»; требования РЕВЬЮЕРА #95 — в «Мелочах».
- AGENT-BRIEF.md 15,0 — API не пишет participant_state; client_op_id для state-меняющих операций.
- docs/process/README.md 8,7 — до 12 файлов и ~600 строк; миграции по одной.
- docs/research/iter2-2.md 14,6 — Н1 (замок → порядок курсора), Н2 (FOR UPDATE требует UPDATE).
- CT 16,6 — тела day/* — TODO; 409 = повтор op_id.
- DM 26,2 — 3.3–3.19: блоки, гейтинг, П-31, очередь.
- MO 8,8 — нет моделей day_marks и idempotency_keys.
- PR 11,3 — status_flags = '{}', пачка без at и payload.
- Сверх списка: docs/research/iter2.md 17,2 — D-25…D-29, контент пуст (.gitkeep); MA 3,4 — порядок роутеров; PA 4,8 — find_active_participant без блокировки.
