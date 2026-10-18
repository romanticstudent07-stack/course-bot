# Исследование iter2-api: день в API (iter2-api-1, iter2-api-2)

Окно ИССЛЕДОВАНИЕ, З2, 18.10.2026. Ссылки @cfb089d. Карточек нет. Дополняет docs/research/iter2.md и iter2-2.md.
Сокращения: CT = docs/architecture/build/miniapp-api-contract.yaml; DM = docs/architecture/03-day-mechanics.md; MO = apps/api/app/db/models.py; PR = apps/api/app/projector.py; MA = apps/api/main.py; PA = apps/api/app/participants.py; AB = AGENT-BRIEF.md.
Права и типы 0006–0008 — по сверке ШТАБа (З2); файлы миграций не читал.

## 1. Решения Автора 18.10
В15 — А; В16 — А; В17 — А; В18 — А; В19 — А; В20 — да; В21 — А. Открыт В22 (§10).

## 2. Факты
| Что | Факт | Где |
|---|---|---|
| day/current, report/submit | тела TODO (D-25); у submit X-Client-Op-Id обязателен; «409 = повтор op_id» | CT |
| Отметки | эндпоинта нет (D-26) | CT |
| Модели | нет DayMark, IdempotencyKey; один kind — mini_app_first_consent | MO |
| Проектор | пачка без at и payload; ON CONFLICT → status_flags = '{}'; неизвестный kind → WARNING, checkpoint сдвигается | PR |
| Роутеры | /miniapp/v1 — только через build_miniapp_v1_router | MA |
| Участник | find_active_participant без блокировки; tombstoned = «нет» | PA |
| Права app_api | participant_events: INSERT, SELECT (id); checkpoints — нет; participant_state — SELECT (participant_state_reader); idempotency_keys — SELECT, INSERT; day_marks — SELECT, INSERT, UPDATE (value, at); UPDATE и DELETE idempotency_keys — ни у кого | ШТАБ |
| Типы | day_marks.value boolean (done = true); idempotency_keys: key text PK (<> ''), kind text, created_at, ttl interval DEFAULT 1 h (> 0), result_ref, params_hash | ШТАБ |
| jsonschema | 4.26.0 уже в requirements | ШТАБ |
| Правила | 3.3 — 4–5 блоков, переключаемо до отправки; 3.5 — все ⭐ + N; 3.9 — время сервера; 3.10 — повтор игнор; 3.11 — П-31; 3.16 — «всё не выполнено»: жизнь цела; 3.19 — очередь, зачёт мгновенный | DM |

## 3. Ключи idempotency_keys (общий модуль app/day_keys.py)
| key | kind | ttl | Зачем |
|---|---|---|---|
| day_enter:{pid} | day_enter | 3650 days | вход по флагу был |
| day_done:{pid}:{dsa} | day_done | 3650 days | день сдан; PK — одна сдача на день |
| day_report:{pid}:{op_id} | day_report | 1 h | повтор запроса (В15); result_ref = вердикт, params_hash = sha256 отметок |
{dsa} = day_started_at в UTC, datetime.isoformat() с микросекундами; ключи строит одна функция для GET и submit. result_ref пишется при INSERT. Долгий ttl — признак, а не повтор: будущая очистка — только по created_at + ttl (§11).

## 4. Замок, вход и отставание проектора
Замок: каждый писатель participant_events для существующего pid, а также PUT отметок, берёт pg_advisory_xact_lock(hashtext('participant:' || pid)) до первой записи и держит до commit. Тогда id событий одного pid идут в порядке commit, и курсор проектора не теряет событие. Ключ один для всех, включая будущий life_op (В20). first-launch замок не берёт: новый pid до commit никто не видит.
Под замком, в той же транзакции: повторная проверка tombstoned_at IS NULL; чтение participant_state (позиция, day_started_at). Проверки «проектор догнал» нет: у app_api нет прав (В22).
Вход по флагу, POST /miniapp/v1/day/test-enter:
- флаг DAY_TEST_ENTRY_ENABLED выключен → 404;
- C0 и C1 не действуют → 409 RECONSENT_REQUIRED;
- позиция уже есть → 200 {status: already};
- есть day_enter:{pid} → 202 {status: entering}, без события;
- иначе INSERT ключа, затем событие day_entered {stage_no: 1, module_no: 1, day_no: 1, source: test_flag}, actor system → 202 {status: entering}.
Фаза участника не меняется (В21).
Проектор: UPDATE participant_state SET позиция, day_started_at = e.at, missed_streak = 0 WHERE pid AND day_no IS NULL; 0 строк → WARNING.
Выкат: api и проектор выкатываются вместе (иначе kind неизвестен → событие пропущено → вечное entering); флаг включать после выката.
Отставание проектора (≈ 1 с), если отчёт отправлен до применения day_entered:
- А (рекомендую): у участника ещё нет позиции → 409 DAY_NOT_STARTED, GET показывает entering, клиент повторит. Ложного успеха нет. Риск переходит в api-3: при выдаче следующего дня или перевыдаче (В10) API может прочитать старый день и засчитать его, а проектор потом пропустит отчёт с «чужим» day_started_at.
- Б: в 2a/2b то же самое (позиции нет → 409). Плюс только в api-3: 409 DAY_STATE_SYNCING + Retry-After: 1. Цена: 0010, отдельная карточка, РЕВЬЮЕР, app_api читает payload всех событий (шире права).
- В: лучше не нашёл. Направление для api-3: «часы» проектора пишут day_entered и сразу применяют его к participant_state в одной транзакции под тем же замком; API под замком видит свежий день. Проверить там: повторный проход курсора не должен откатывать позицию к старому событию.

## 5. Новые kinds без затирания status_flags
- mini_app_first_consent не трогать.
- Новые kinds — только UPDATE своих колонок, без ON CONFLICT; status_flags, lifecycle_phase, author_pause_reason в SQL не упоминаются.
- В пачку добавить e.at и e.payload; в лог — только id и kind. PROJECTOR_VERSION → 2.
- day_report_submitted: SET missed_streak = 0 WHERE pid AND day_started_at = payload.day_started_at (любой вердикт, В18); старый день → пропуск.
- «Пришёл» и «+1 ч» считаются в api-3 по min(day_marks.at) для текущего day_started_at; событие первой отметки не нужно (В19).
- Тест: status_flags = '{block_lives}' после обоих kinds не меняются.

## 6. Контракт (D-25, D-26)
Общее: 401, 429, 503 — как сейчас. Нет активного pid → 404 PARTICIPANT_NOT_FOUND. Позиции нет → 409 DAY_NOT_STARTED (кроме GET). Лишние поля тела (pid, day_started_at) игнорируются.
- GET /miniapp/v1/day/current (без замка) → 200 {status: not_started | entering | open | submitted, lives: 0..3, test_entry: bool, position?, day_started_at?, blocks?: [{block_id, title_key, help_key, critical, mark: done | not_done | null}], min_optional?, can_submit?}. Статусы: entering — есть day_enter, позиции нет; submitted — есть day_done:{pid}:{dsa}. Отметки берутся только по текущему day_started_at.
- PUT /miniapp/v1/day/marks (В16 = А, без op_id, под замком): тело {block_id, value: done | not_done}. Проверки: block_id — ^[a-z0-9_]{1,32}$ и есть среди блоков текущего дня, иначе 422 BLOCK_NOT_IN_DAY; есть day_done → 409 DAY_ALREADY_SUBMITTED. Затем UPSERT day_marks (value boolean) → 200 {block_id, value}.
- POST /miniapp/v1/day/report/submit: X-Client-Op-Id — uuid, иначе 422. Тело {marks: [{block_id, value}]} — ровно все блоки дня, без повторов, иначе 422 MARKS_INCOMPLETE. Порядок в одной транзакции:
  1. pid из initData;
  2. замок, проверка tombstoned_at;
  3. есть day_report:{pid}:{op_id}: тот же params_hash → 200 тем же телом (В15 = А), другой → 409 IDEMPOTENCY_CONFLICT;
  4. позиция и day_started_at из participant_state;
  5. есть day_done → 409 DAY_ALREADY_SUBMITTED;
  6. UPSERT отметок, вердикт;
  7. INSERT day_done и day_report;
  8. событие day_report_submitted {day_started_at, verdict, stage_no, module_no, day_no};
  9. commit → 200 {verdict, queued: true}.
  Сбой → 503, ложного 200 нет (П-31). Время — now() сервера.
- Вердикт: all_not_done — все not_done; passed — все critical done и прочих done ≥ min_optional; иначе not_passed.
- CT read-only: DOCS PR + sync (как D-22) — тела выше, «409 = повтор op_id» → «повтор = тот же 200».

## 7. Заглушка контента
apps/api/content/module_1/day_01.json, day_02.json: {stage_no, module_no, day_no, min_optional, blocks: [{block_id, critical, title_key, help_key}]}; 4–5 блоков, ≥ 1 critical. Рядом JSON Schema; проверка при старте api (битый контент → не стартует). Тексты — ключи text_registry + заглушки в config/texts (В17); справка — только текст (В7).

## 8. Требования РЕВЬЮЕРА #95
- pid из initData через tg_user_registry; day_started_at из participant_state в той же транзакции; белый список block_id + длина; tombstoned → не писать; тест «pid и day_started_at из тела игнорируются» — в 2a и 2b.
- «Проектор только по текущему day_started_at» — в 2b и api-3.

## 9. Разрезка
При В22 = А (3 карточки, строго по порядку, миграций нет):
| # | id | Что | Файлов / строк | РЕВЬЮЕР |
|---|---|---|---|---|
| 1 | iter2-api-1 | контент + схема + модели DayMark, IdempotencyKey + GET day/current (+ entering, submitted) | ≈ 10 / ≈ 480 | нет |
| 2 | iter2-api-2a | app/participant_lock.py + app/day_keys.py + флаг + test-enter + PUT marks + kind day_entered | ≈ 10 / ≈ 550 | да |
| 3 | iter2-api-2b | report/submit + kind day_report_submitted | ≈ 8 / ≈ 500 | да |
При Б — 4 карточки: iter2-db-4 (0010, только GRANT, РЕВЬЮЕР) → 1 → 2a → 2b; в 2a/2b добавить проверку «догнал».
2a и 2b меняют routers/day.py и projector.py → только друг за другом.

## 10. Вопрос Автору
- В22. Как API узнаёт «день сдан» и отставание проектора. А — ключ day_done в idempotency_keys, проверки «догнал» нет, риск — в api-3. Б — 0010 с GRANT на чтение событий и checkpoint. В — свой: не нашёл, есть только направление для api-3 (§4). Мнение: А — в 2a/2b Б ничего не добавляет, а права расширяет.

## 11. Кандидаты в DEFECTS
- D-25, D-26 — закрыть DOCS PR по §6.
- CT «409 = повтор op_id» ↔ В15 = А (повтор → тот же 200).
- I2B: ключи 'life:' и 'participant:' → один 'participant:' || pid (В20).
- Инвариант: писатели participant_events (кроме first-launch) и PUT отметок берут замок pid.
- idempotency_keys хранит долгие признаки (day_enter, day_done): очистка — только по created_at + ttl.

## 12. Для ШТАБА (строки STATE)
- «iter2-api: research З2 готов (PR без мержа); В15–В21 решены, ждём В22.»
- «Разрезка: 1 → 2a → 2b без миграций (В22 = А) или db-4 (0010) → 1 → 2a → 2b (Б).»

## 13. Прочитано (З1, в З2 новых нет)
DESIGNER.md, STATE.md (без хвоста «Учёт кредитов» — по Н6 не нужен), AB, process/README.md, iter2-2.md, CT, DM, MO, PR; сверх списка: iter2.md, MA, PA.
