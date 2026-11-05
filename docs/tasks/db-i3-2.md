# db-i3-2 — миграция 0014_measurements_log: Чек-Ап и стартовый вес

## 1. Паспорт
- id: db-i3-2 · ветка: db/i3-2-measurements-log · режим: Р0+ (КОДЕР) · РЕВЬЮЕР: да (раздел 14).
- Заголовок PR: «db(0014): measurements_log — Чек-Ап и стартовый вес, права app_api / app_bot (db-i3-2)».
- Зависит от: db-i3-1. Начинать после мержа задачи db-i3-1 (0013_bot_card в main и на сервере).
- Дальше: db-i3-3 (0015) — только после мержа этой задачи; api-1 (Чек-Ап) — после неё.

## 2. Цель
Append-only таблица measurements_log (имя из db-tables-index): результат Чек-Апа (15 ответов, балл, зона, версия конфига) и стартовый вес — отдельными строками (kind). app_api пишет и читает, app_bot читает только то, что нужно карточке (вес, зона). Таблиц станет 18.

## 3. Решения (метки К-6)
- Р-16 [Автор, DECISIONS]: «стартовые замеры — в таблицу Чек-Апа».
- А1 [Автор 05.11; канон 04 §4.4, 06 §6.4, TI — молчит]: стартовые замеры — ТОЛЬКО вес (weight_kg). Объёмов нет.
- Р-7 [Автор, DECISIONS]: конфиг Чек-Апа меняется через эпохи → связь балл↔зона в CHECK НЕ кладём.
- Л2 [ШТАБ, К-5; по выдержке iter3-2]: до Панели конфиг — файл в репо с версией, версия пишется в результат; участнику — только зона, балл не показываем.
- [ШТАБ-тех, К-5]: kind = checkup / body; у body только weight_kg; CHECK checkup_score = сумма 15 ответов; occasion = onboarding / stage_end; app_bot SELECT (pid, kind, occasion, checkup_zone, weight_kg, created_at), checkup_score боту не даём.
- [ШТАБ-тех, К-5]: stage_no — для Карты изменений (stage_end), onboarding — NULL.
- Ш-4 [ШТАБ-тех, К-5]: CHECK диапазонов (вес 30–300 кг).

## 4. Выдержки архитектуры
- 05 §5.1: «15 утверждений, шкала 0–3, максимум 45 баллов. Проводится: на старте (Шаг 4.5 онбординга) + после каждого Этапа.»
- 05 §5.3: «🟢 0–9 — Зелёная», «🟡 10–22 — Жёлтая», «🔴 23–45 — Красная»; «границы включительные, жёстко в конфиге».
- 05 §5.5: «Храним все 15 ответов (не только сумму/зону) + балл + зона + дата.»
- 05 fail-safe: «Идемпотентность кнопок. Серверный пересчёт суммы из сохранённых ответов (не доверяем клиенту).»
- 04 §4.8: «добавочная запись в журнал замеров, старая неприкосновенна».
- 04 §4.1: анкета — Шаг 4, Чек-Ап — Шаг 4.5: разные запросы → разные строки, без UPDATE.
- 06 §6.4: «Было → стало: вес (старт → текущий), Чек-Ап-зона (старт → последняя, с пометкой улучшение/ухудшение).»
- db-tables-index: «measurements_log | Б5 / Б14 | Append-only лог замеров (Чек-Ап, антропометрия)».

## 5. ЧТО ПРОЧИТАТЬ (КОДЕР)
- apps/api/migrations/versions/2026_10_31_1200-0011_reflections_log_reflections_log.py — 5,8 КБ (образец таблицы и GRANT).
- apps/api/app/db/models.py — 17,4 КБ (ReflectionsLog — образец модели).
- apps/api/tests/test_db_roles_0011.py — 14,1; test_db_roles.py — 9,4; test_db_models.py — 5,8; expected_tables.txt — 0,8 (все в apps/api/tests/).
- Миграция 0013 (db-i3-1, ≈ 4 КБ) — для down_revision; AGENT-BRIEF.md — 17,1. Чтение КОДЕРА ≈ 75 КБ + карточка.

## 6. Файлы
- Создать: apps/api/migrations/versions/2026_11_07_1200-0014_measurements_log_measurements_log.py.
- Изменить: apps/api/app/db/models.py (класс MeasurementsLog, константы, абзац 0014 в докстринге).
- Изменить: apps/api/tests/expected_tables.txt — в конец две строки: «# 0014_measurements_log» и «measurements_log».
- Полный список после правки (18): participant_state, stage_publish_log, outbox, outbox_dlq, issuance_log, anomaly_log, erasure_blacklist, privacy_audit_log, tg_user_registry, text_registry, consent_events, participant_events, participant_state_checkpoints, idempotency_keys, day_marks, access_grants, reflections_log, measurements_log.
- Создать: apps/api/tests/test_db_roles_0014.py. Изменить: apps/api/tests/test_db_models.py.

## 7. Контракт (SQL; код — api-1, api-2, bot-1)
- API, Чек-Ап (балл и зону сервер считает сам по ответам и конфигу):
  INSERT INTO measurements_log (pid, kind, occasion, stage_no, checkup_answers, checkup_score, checkup_zone, checkup_config_version, client_op_id) VALUES (:pid, 'checkup', :occ, :stage, :answers, :score, :zone, :ver, :op) ON CONFLICT (pid, client_op_id) DO NOTHING RETURNING id
- API, вес (анкета, api-2): INSERT INTO measurements_log (pid, kind, occasion, stage_no, weight_kg, client_op_id) VALUES (:pid, 'body', :occ, :stage, :w, :op) ON CONFLICT (pid, client_op_id) DO NOTHING RETURNING id
- :stage — номер этапа для stage_end; для onboarding — NULL.
- Повтор (RETURNING дал 0 строк): SELECT id, checkup_score, checkup_zone, created_at FROM measurements_log WHERE pid = :pid AND client_op_id = :op → тот же 200.
- Бот (карточка): SELECT kind, occasion, checkup_zone, weight_kg, created_at FROM measurements_log WHERE pid = :pid ORDER BY created_at — старт = первая строка своего kind, текущее = последняя.

## 8. БД: миграция 0014_measurements_log
- revision = "0014_measurements_log"; down_revision = "0013_bot_card".
- Таблица measurements_log:
  id bigint (bigserial, measurements_log_id_seq), PK measurements_log_pkey;
  pid uuid NOT NULL, FK → tg_user_registry.pid (measurements_log_pid_fkey);
  kind text NOT NULL; occasion text NOT NULL; stage_no smallint NULL;
  checkup_answers smallint[] NULL; checkup_score smallint NULL; checkup_zone text NULL; checkup_config_version text NULL;
  weight_kg numeric(5,1) NULL; client_op_id text NOT NULL; created_at timestamptz NOT NULL DEFAULT now(); updated_at нет.
- UNIQUE (pid, client_op_id) — measurements_log_pid_client_op_id_key; индекс measurements_log_pid_kind_idx (pid, kind, created_at), не уникальный.
- CHECK (имена точно такие):
  ck_measurements_log_kind: kind IN ('checkup', 'body');
  ck_measurements_log_occasion: occasion IN ('onboarding', 'stage_end');
  ck_measurements_log_stage: (occasion = 'onboarding' AND stage_no IS NULL) OR (occasion = 'stage_end' AND stage_no >= 1);
  ck_measurements_log_kind_checkup: kind <> 'checkup' OR (checkup_answers IS NOT NULL AND checkup_score IS NOT NULL AND checkup_zone IS NOT NULL AND checkup_config_version IS NOT NULL AND weight_kg IS NULL);
  ck_measurements_log_kind_body: kind <> 'body' OR (weight_kg IS NOT NULL AND checkup_answers IS NULL AND checkup_score IS NULL AND checkup_zone IS NULL AND checkup_config_version IS NULL);
  ck_measurements_log_answers: checkup_answers IS NULL OR (array_ndims(checkup_answers) = 1 AND array_lower(checkup_answers, 1) = 1 AND cardinality(checkup_answers) = 15 AND array_position(checkup_answers, NULL) IS NULL AND 0 <= ALL (checkup_answers) AND 3 >= ALL (checkup_answers));
  ck_measurements_log_score_sum: checkup_score IS NULL OR checkup_score = checkup_answers[1] + checkup_answers[2] + checkup_answers[3] + checkup_answers[4] + checkup_answers[5] + checkup_answers[6] + checkup_answers[7] + checkup_answers[8] + checkup_answers[9] + checkup_answers[10] + checkup_answers[11] + checkup_answers[12] + checkup_answers[13] + checkup_answers[14] + checkup_answers[15] (все 15 слагаемых выписаны: подзапрос в CHECK нельзя);
  ck_measurements_log_score_range: checkup_score IS NULL OR checkup_score BETWEEN 0 AND 45;
  ck_measurements_log_zone: checkup_zone IS NULL OR checkup_zone IN ('green', 'yellow', 'red');
  ck_measurements_log_config_version: checkup_config_version IS NULL OR char_length(btrim(checkup_config_version)) BETWEEN 1 AND 64;
  ck_measurements_log_weight: weight_kg IS NULL OR weight_kg BETWEEN 30 AND 300 [ШТАБ-тех];
  ck_measurements_log_client_op_id: char_length(client_op_id) BETWEEN 1 AND 64.
- Связи балл↔зона в CHECK нет (Р-7): границы зон лежат в конфиге, их проверяет api-1 (тест 9/10/22/23).
- Права (одна строка — одно право; роли создаются, если их нет):
  app_api INSERT (pid, kind, occasion, stage_no, checkup_answers, checkup_score, checkup_zone, checkup_config_version, weight_kg, client_op_id);
  app_api SELECT (id, pid, kind, occasion, stage_no, checkup_answers, checkup_score, checkup_zone, checkup_config_version, weight_kg, client_op_id, created_at);
  app_api USAGE — SEQUENCE measurements_log_id_seq;
  app_bot SELECT (pid, kind, occasion, checkup_zone, weight_kg, created_at) — stage_no боту не выдаётся (карточке не нужен).
- UPDATE, DELETE, TRUNCATE не получает никто; app_projector прав не получает; без ALTER DEFAULT PRIVILEGES и PUBLIC.
- downgrade: DROP INDEX, затем DROP TABLE (права на таблицу и последовательность уходят вместе с ней; на чужих таблицах 0014 прав не выдаёт). Права 0013 остаются.
- models.py: MeasurementsLog по схеме выше, включая stage_no (SmallInteger, nullable) (ARRAY(SmallInteger), Numeric(5, 1), те же имена CHECK); константы MEASUREMENT_KINDS, MEASUREMENT_OCCASIONS, CHECKUP_ZONES, CHECKUP_ANSWERS_COUNT = 15, CHECKUP_ANSWER_MAX = 3, WEIGHT_MIN_KG = 30, WEIGHT_MAX_KG = 300 — те же значения, что в CHECK.

## 9. Тесты (apps/api/tests/test_db_roles_0014.py, образец test_db_roles_0011)
- Статика: revision и down_revision; в PRIVILEGES нет UPDATE, DELETE, TRUNCATE и app_projector; у app_bot нет checkup_score и checkup_answers; в коде нет ALTER DEFAULT PRIVILEGES и PUBLIC.
- SQL раздела 7 под app_api: checkup → id; повтор того же client_op_id → 0 строк, в таблице одна строка; body (вес 72.5) → id. Под app_bot SELECT карточки возвращает обе строки.
- Отказы app_bot (42501): SELECT checkup_score; SELECT checkup_answers; SELECT checkup_config_version; SELECT client_op_id; SELECT stage_no; SELECT *; INSERT; UPDATE. Отказы app_api: UPDATE, DELETE, TRUNCATE. app_projector: SELECT id.
- Функции прав, как PRIVILEGE_CHECKS_0011, плюс нет DELETE и TRUNCATE у app_bot, app_api, app_projector.
- CHECK (вставка владельцем, имя ограничения в diag): 14 и 16 ответов; элементы 4 и −1; NULL-элемент; нижняя граница массива 0 (литерал '[0:14]={…}'); балл ≠ сумме; zone 'blue'; kind 'x'; occasion 'x'; checkup с весом; body без веса; body с ответами; вес 29.9 и 300.1; версия '' и '   '; client_op_id ''; ck_measurements_log_stage — onboarding со stage_no 1, stage_end без stage_no, stage_end со stage_no 0. Проходят: вес 30 и 300; баллы 9, 10, 22, 23 с любой зоной (связи нет, Р-7); stage_end со stage_no 2. Дубль (pid, client_op_id) → UniqueViolation measurements_log_pid_client_op_id_key; чужой pid → measurements_log_pid_fkey.
- ПОСЛЕДНИМ — downgrade до 0013_bot_card: таблицы нет, SELECT (tz) на participant_state у app_bot (право 0013) → true; в finally upgrade head.
- tg_user_id — 3901–3999 (grep -rn "39[0-9][0-9]" apps/api/tests — пересечений нет). tools/check.sh api — статика; тесты с БД — CI.

## Задетые тесты (правило «Т»)
- apps/api/tests/test_db_models.py::test_expected_tables_count_after_0011 → переименовать в test_expected_tables_count_after_0014: len == 18; добавить TABLES_0014 = {"measurements_log"} и assert TABLES_0014 <= _expected_tables().
- test_db_models.py::test_upgrade_downgrade_upgrade_cycle: первым шагом command.downgrade(cfg, "0013_bot_card") и assert _tables == expected - TABLES_0014; затем expected = expected - TABLES_0014; дальше как было. Без этого шаг «0010» упадёт: вместе с таблицей 0011 уйдёт и measurements_log. В докстринг цикла дописать head → 0013.
- test_db_models.py::test_models_match_live_schema сверит MeasurementsLog с живой схемой — правка нужна только в models.py.
- Downgrade-тесты test_db_roles*.py идут через downgrade 0014 — правки не нужны (downgrade чистый).

## 10. Живые проверки на сервере
- Бэкап before-0014 → alembic upgrade head → current = 0014_measurements_log; в схеме public 18 таблиц.
- has_column_privilege('app_bot', 'measurements_log', 'checkup_score', 'SELECT') → f; то же для 'checkup_zone' → t.

## 11. Запреты
- AGENT-BRIEF §3 — целиком; ci.yml и чужие миграции не трогать; права только из раздела 8.
- Объёмы, город, ФИО, телефон, email не хранить (Р-16, А1). Тексты вопросов и зон — не здесь (api-1, заглушки).

## 12. Готово, когда
- 0014 в main; CI зелёный; РЕВЬЮЕР без блокеров; сервер: current = 0014_measurements_log, 18 таблиц, проверки раздела 10 совпали.

## 13. Оценка
- Р0+ КОДЕР: кредитов 0, часы Автора ≈ 1,5. Таблица по образцу 0011 и один задетый файл с точными правками; Агент ≈ 350 + 80 кредитов — неоправданно.

## 14. РЕВЬЮЕР: да
- GRANT БД и данные о здоровье (Чек-Ап = ПДн + здоровье, 06 fail-safe): app_bot без балла и ответов; CHECK ответов и суммы не обойти (NULL-элемент, нижняя граница); append-only.

## Канон и решения
- (а) Использует: 05 §5.1, §5.3, §5.5, fail-safe, YAML storage; 04 §4.1, §4.4, §4.8; 06 §6.4; db-tables-index (measurements_log).
- (б) Противоречат DECISIONS и ответам Автора: 04 §4.4 «Вес / объёмы → число» (А1: только вес); 05 §5.4 и YAML to_participant «балл + зона» (Л2: балл не показываем) — это правка №8, её делает карточка api-1.
- (в) Правка DOCS №11 (с «только вес») — полный текст в db-i3-3.
- (г) Р-7 и 05 §5.3 «жёстко в конфиге» не противоречат: границы зон — в конфиге, не в CHECK. Своих правок у 0014 нет.
