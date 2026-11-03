# api-refl-1 — рефлексия в отчёте дня: поле, лог, outbox
Правило К — docs/process/CANON-CHECK.md. Карточка по docs/research/iter2-rest.md (§3 а, §4, §9: В1 = А, В3 = Б), ответам ШТАБа 03.11 и коду @e4069b0.
Примечание: в iter2-rest таблица названа day_reflections; в коде (0011) — reflections_log. Верно — reflections_log.

## 1. Паспорт
- id: api-refl-1. Заголовок PR: «feat(api): рефлексия в отчёте дня — поле, лог, outbox (api-refl-1)». Ветка: feat/api-refl-1.
- Режим: Р1 (Агент), запасной Р0+ — решит ШТАБ перед стартом. Карточка годится обоим.
- Зависит от: db-1, bot-group-1, clocks-1, db-2 (0012 смержена). Миграции в задаче нет. Дальше: miniapp-refl-1.

## 2. Цель
POST /day/report/submit принимает поле reflection. В день рефлексии (6 и 13) без поля или с текстом короче 2 символов после strip — 422 REFLECTION_REQUIRED.
Принятая рефлексия — строка в reflections_log и строка outbox reflection_submitted в той же транзакции (бот публикует её в тему «Рефлексии»).
GET /day/current отдаёт reflection_required.

## 3. Решения Автора и ШТАБа
- В1 = А (Автор 30.10): неизменяемый лог; каждая сдача — новая строка (только INSERT), действующая — последняя по created_at (0011 docstring).
- В3 = Б (Автор 30.10): 13-M / 13-P без Панели: поле, минимум 2 символа, лог, пост в тему без кнопок модерации; контент дня 13 не добавлять (iter2-rest §4).
- Решение Автора 03.11 (вариант А) [Автор, канон проверен: 0001 роль outbox_writer «пишет в outbox (транзакционно с доменом)»; кто пишет reflection_submitted — канон молчит]: права app_api на outbox — миграция 0012 задачи db-2; здесь миграции нет.
- Т1–Т9 [ПРОЕКТИРОВЩИК-тех, принято ШТАБом 03.11] — в §7.

## 4. Выдержки архитектуры (через iter2-rest §1 @e4069b0)
- 03 §3.12: «рефлексия — обязательное поле отчёта дней 6, 13-M, 13-P; без поля "Отправить" нельзя; минимум 2 символа; смысл не оценивается; неизменяемый лог "как замеры"; при ревёрте поле снова обязательно, старый текст — в истории; все рефлексии — Автору в Рабочую группу, тема "Рефлексии"».
- 03 §3.14: авто-прохода нет — поэтому контента дня 13 нет (passed на 13 увёл бы на 14).
- 08 §8.2: тема «Рефлексии» — очередь на проверку (дни 6 / 13-M / 13-P).
- Бот (bot-group-1 §7, шаг 5): payload reflection_submitted — dict; payload.pid (строка UUID) == aggregate_id; reflection_id — int > 0, не bool; иначе bad_payload в DLQ. Текст бот читает из reflections_log по reflection_id.

## 5. ЧТО ПРОЧИТАТЬ
- apps/api/app/routers/day.py — 39,2 (правка).
- apps/api/app/day_report.py — 2,7 (правка).
- apps/api/migrations/versions/2026_10_31_1200-0011_reflections_log_reflections_log.py — 5,8 (контракт INSERT).
- apps/api/app/notify_ops.py — только константа _INSERT_OUTBOX (образец INSERT outbox).
- apps/api/tests/test_day_report_submit.py — 22,3 (образец фикстур, _fail_insert).
- apps/api/tests/test_day_current.py — 11,3 (образец _state: позиция «день 6» строкой владельца).
- apps/api/tests/test_db_roles_0011.py — размер не мерил, ШТАБу (образец role_engine для Д2).
- Чтение КОДЕРА ≈ 82 КБ + test_db_roles_0011.py + notify_ops (одна константа).
- day_clock.is_reflection_day(day_no) — импортировать, файл не читать (True для 6 и 13).

## 6. Файлы
- Изменить: apps/api/app/routers/day.py, apps/api/app/day_report.py.
- Создать: apps/api/tests/test_day_reflection.py.

## 7. Контракт
Тело POST /day/report/submit: {marks: [...], reflection?: string}.
- Т1: в DayReportIn поле reflection: str | None = Field(default=None, max_length=2000). Длиннее 2000 или не строка → 422 VALIDATION_ERROR (как у marks).
- Т3: символ NUL (\x00) в reflection → 422 VALIDATION_ERROR (валидатор модели; PostgreSQL не хранит NUL в text).
- Т2: нормализация norm = reflection.strip() (Python strip). В БД и в хеш идёт norm. len(norm) ≥ 2 → CHECK 0011 (btrim ≥ 2, ≤ 2000) выполнен всегда.
- Т5: day_report.params_hash(marks, reflection: str | None = None). reflection is None → тот же хеш, что сейчас (тот же JSON списка пар). Иначе sha256 канонического JSON объекта {"marks": <тот же отсортированный список>, "reflection": norm}. Шаг 2 (повтор op_id) считает хеш с norm, если поле есть.
- Т4, новый шаг 5а (после 5 DAY_ALREADY_SUBMITTED, до 6 UPSERT отметок и 7 вердикта): is_reflection_day(day_no) и (поля нет или len(norm) < 2) → rollback, 422 {code: "REFLECTION_REQUIRED", message: «Нужна рефлексия: минимум 2 символа.»}; формат ошибки — как у 422 MARKS_INCOMPLETE в day.py. all_not_done тоже требует поле. Повтор того же op_id с тем же телом — раньше, на шаге 2 (200).
- Т6: день не рефлексии — поле принимается, в лог и outbox не пишется; в хеш входит, если есть.
- Т7, новый шаг 8б (после 8а ключа day_queue, до 9 события), только в день рефлексии, та же транзакция:
  1) контракт 0011 дословно — константа модуля _INSERT_REFLECTION:
       INSERT INTO reflections_log (pid, stage_no, module_no, day_no, day_started_at, body)
       VALUES (:pid, :s, :m, :d, :ds, :body) RETURNING id
     позиция — из прочитанной строки participant_state, :ds — текущий day_started_at, :body — norm;
  2) константа _INSERT_REFLECTION_OUTBOX по образцу notify_ops._INSERT_OUTBOX, БЕЗ RETURNING (у app_api нет SELECT на outbox):
       INSERT INTO outbox (aggregate_id, event_type, payload, tx_id)
       VALUES (:pid_text, 'reflection_submitted', CAST(:payload AS jsonb), pg_current_xact_id())
     :pid_text = str(pid); :payload = json.dumps({"pid": str(pid), "reflection_id": id}); id — int из RETURNING. Приведения колонок — точно как в _INSERT_OUTBOX.
  Текста рефлексии и ПДн в payload нет. Ответ — прежний {verdict, queued: true}.
- Ошибка БД на 8б (в том числе CHECK) → rollback, 503 SERVICE_UNAVAILABLE, ничего не записано (П-31).
- Т8, GET /day/current: поле reflection_required: bool = is_reflection_day(day_no) — только в ветках с позицией: open, submitted, closed. В queued и в ветках без позиции поля нет — тем же способом, каким в day.py сейчас опускаются поля, которых нет в ветке. Если модель так не умеет и поле появится в ответах not_started / entering / queued — СТОП, вопрос ШТАБу (test_day_current сверяет ответы целиком).
- Т9: новый вид ключа не нужен (повтор гасит ключ day_report); TTL_BY_KIND не трогать.
- Логи: body, pid и op_id в лог не идут; INFO-строки submit — прежние.
- Docstring day.py: дописать поле, шаги 5а и 8б, reflection_required в GET (ссылка «api-refl-1»).

## 8. БД
Миграции нет. Таблица и права — 0011 (db-1). INSERT в outbox от app_api — 0012 (db-2). UPDATE/DELETE reflections_log не выданы никому — в коде их нет.

## 9. Тесты — новый apps/api/tests/test_day_reflection.py
Позиция «день 6» (module_1): строка participant_state владельцем, как _state в test_day_current.py; «сейчас» — monkeypatch day_clock.utcnow внутри окна, как в test_day_report_submit.py. Контент дней 1–6 module_1 есть (content-1).
1. День 6, без поля → 422 REFLECTION_REQUIRED; нет события, ключей, отметок, строк reflections_log и outbox.
2. День 6, reflection " а " и "\t\n" → 422 REFLECTION_REQUIRED.
3. День 6, все not_done без поля → 422 (проверка до вердикта).
4. День 6, "  ок  " → 200; reflections_log: 1 строка, body "ок", stage/module/day и day_started_at совпадают; outbox: 1 строка reflection_submitted, aggregate_id = str(pid); событие day_report_submitted — 1.
5. Д3: payload outbox == {"pid": str(pid), "reflection_id": <id строки лога>}, reflection_id — int; caplog (все записи) не содержит body.
6. 2000 символов кириллицы → 200; 2001 → ValidationError модели; NUL → ValidationError.
7. Тот же op_id и то же тело → 200 тот же ответ, по 1 строке в логе и outbox; тот же op_id, другой reflection → 409 IDEMPOTENCY_CONFLICT.
8. Т4: после сдачи дня 6 новый op_id без поля → 409 DAY_ALREADY_SUBMITTED.
9. День 1 с reflection → 200; reflections_log и outbox этого pid пусты.
10. Сбой INSERT reflections_log (_fail_insert) → 503, ничего не записано.
11. params_hash: params_hash(pairs) == params_hash(pairs, None); с "ок" — другой; порядок marks не влияет.
12. GET: день 6 open → reflection_required true; день 1 open → false.
13. Д2: под role_engine app_api (tests.test_db_roles, как в test_db_roles_0011.py) в одной транзакции выполнить _INSERT_REFLECTION и _INSERT_REFLECTION_OUTBOX, импортированные из app.routers.day (текст не копировать) → без 42501, id — int. Единственный тест прав (CI работает суперпользователем).
Цели check.sh: api (имя цели сверит ШТАБ). С БД — только CI.

## 10. Живая проверка (после мержа)
Выкат один на три задачи: migrate 0012 (db-2, бэкап до миграции) → api (эта задача) → miniapp (miniapp-refl-1).
1. Любой аккаунт на дне 1–5: GET /day/current → reflection_required false; сдача как раньше.
2. Аккаунт на дне 6 (метку А1–А4 и время назначит ШТАБ; тестовый день А1 без указания ШТАБа не трогать): submit без поля → 422 REFLECTION_REQUIRED; с текстом → 200.
3. В БД: 1 новая строка reflections_log; строка outbox reflection_submitted доставлена; пост в теме «Рефлексии».
4. До дня 6 надо дойти (около 4–5 суток, iter2-rest §5) — сроки решает ШТАБ.

## 11. Запреты
- AGENT-BRIEF §3. participant_state не писать (E1 / INV-1). Миграций нет.
- Не дублировать is_reflection_day; контент дня 13 не добавлять; бот, life_ops, notify_* не трогать.
- Body, pid, op_id — не в лог; текст рефлексии — не в payload. UPDATE/DELETE reflections_log — нет.
- Упал тест вне «Задетых тестов» → не чинить, стоп и ИТОГ.

## 12. Готово, когда
Тесты §9 зелёные в CI; старые тесты submit/current без правок; docstring обновлён; PR описывает отличия от карточки.

## 13. Оценка
Р1: 700–900 кредитов (iter2-rest §6); Р0+: 0. Часы Автора: ≈ 1 (PR, выкат вместе с db-2 и miniapp).

## 14. РЕВЬЮЕР
Нет: GRANT меняет db-2 (там РЕВЬЮЕР); ПДн закрыты тестами 5 и 13.

## Задетые тесты (сверено ШТАБом @e4069b0)
- test_day_report_submit.py, test_day_current.py, test_day_report_unit.py, test_day_queue.py, test_day_window.py, test_day_writers.py, test_clocks_1.py — правок 0 (день не рефлексии; params_hash одним списком — совместимо с Т5; новых видов ключей нет).
- Тестов OpenAPI ↔ packages/shared нет. test_db_roles_0009.py — задача db-2.

## Канон и решения
(а) 03 §3.12, 03 §3.14, 08 §8.2 (через iter2-rest §1). (б) Противоречий с DECISIONS.md нет. (г) Правок канона нет.

## Вне задачи
Контент дня 13 и модерация 13-M / 13-P (iter2-rest §4); −1 жизнь за пропуск дня рефлексии — clocks-1 (#164); доставка в тему — bot-group-1 (#161); таблица и права — db-1 (0011); права outbox и тесты 0011 от РЕВЬЮЕРА #157 — db-2; поле в Mini App — miniapp-refl-1.
