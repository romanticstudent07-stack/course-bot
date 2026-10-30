# db-1 — миграция 0011_day_reflections (лог рефлексий)

## 1. Паспорт
- id: db-1 · PR: «feat(db): 0011_day_reflections — лог рефлексий (db-1)» · ветка: feat/db-1
- Режим: Р0+ (КОДЕР; запасной Р1-П) · зависит: —. down_revision = 0010_access_grants (последняя на 49dd033). Других задач с миграцией параллельно не вести. bot-group-1 и api-refl-1 начинать после мержа и выката db-1.

## 2. Цель
Неизменяемый лог рефлексий дней 6 / 13-M / 13-P: таблица day_reflections, права app_api INSERT/SELECT, app_bot SELECT. Код API и бота не трогать — это api-refl-1 и bot-group-1.

## 3. Решения
- В1 = А [Автор 30.10, К-6]: «отдельная таблица day_reflections, только INSERT/SELECT, миграция 0011, РЕВЬЮЕР» (research iter2-rest.md §9).
- Доставка в группу [ШТАБ, Ш2–Ш3]: «Текст рефлексии бот читает из day_reflections по reflection_id. Для этого в 0011 нужен GRANT SELECT для app_bot»; «ПДн в payload не кладём» (research §3).
- §3 (а): «Текст пишется в day_reflections: только INSERT, история ревёртов — новыми строками»; «после strip в нём меньше 2 символов → 422 REFLECTION_REQUIRED» (проверка API — api-refl-1).
- STATE: «каждая миграция с новой таблицей выдаёт GRANT … в той же миграции»; AGENT-BRIEF §11: новая таблица → expected_tables.txt в том же PR.

## 4. Выдержки канона
03 §3.12 (research §1): «минимум 2 символа; смысл не оценивается; неизменяемый лог «как замеры»; при ревёрте поле снова обязательно, старый текст — в истории; все рефлексии — Автору в Рабочую группу, тема «Рефлексии»».

## Канон и решения
(а) 03 §3.12. (б) Противоречий с DECISIONS нет. Имя и колонки таблицы в normative/ (I1–I4) окно не сверяло — не проверено, сверяет ШТАБ до промпта. (г) Правок канона нет (по проверенному).

## 5. ЧТО ПРОЧИТАТЬ (КОДЕР)
- apps/api/migrations/versions/2026_10_24_1200-0010_access_grants_access_grants.py — 7,5 КБ
- apps/api/migrations/versions/2026_10_17_1200-0009_app_bot_app_bot.py — 5,1 КБ
- apps/api/app/db/models.py — 14,6 КБ
- apps/api/tests/test_db_models.py — 5,4 КБ
- apps/api/tests/test_db_roles_0010.py — 14,3 КБ (образец тестов прав)
- apps/api/tests/expected_tables.txt — 0,6 КБ
- apps/api/tests/conftest.py — 8,1 КБ
Чтение КОДЕРА ≈ 55,6 КБ.

## 6. Файлы
- Создать: apps/api/migrations/versions/2026_10_31_1200-0011_day_reflections_day_reflections.py; apps/api/tests/test_db_roles_0011.py.
- Изменить: apps/api/app/db/models.py; apps/api/tests/expected_tables.txt; apps/api/tests/test_db_models.py.
- expected_tables.txt: в конец блок «# 0011_day_reflections» и строка day_reflections. Полный список (17): participant_state, stage_publish_log, outbox, outbox_dlq, issuance_log, anomaly_log, erasure_blacklist, privacy_audit_log, tg_user_registry, text_registry, consent_events, participant_events, participant_state_checkpoints, idempotency_keys, day_marks, access_grants, day_reflections.

## 7. Контракт
API и бот не меняются. Контракт — таблица и права (раздел 8).

## 8. БД
Миграция: revision "0011_day_reflections", down_revision "0010_access_grants", Create Date 2026-10-31 12:00:00. Docstring-шапка по образцу 0010: зачем; права и SQL, который их требует; «таблиц после миграции — 17».
Таблица day_reflections [колонки — ПРОЕКТИРОВЩИК-тех, К-6]:
| колонка | тип | ограничения |
|---|---|---|
| id | bigint | PK day_reflections_pkey, autoincrement (последовательность day_reflections_id_seq) |
| pid | uuid | NOT NULL, FK tg_user_registry.pid (day_reflections_pid_fkey) |
| stage_no, module_no, day_no | integer | NOT NULL — позиция дня |
| day_started_at | timestamptz | NOT NULL — попытка дня (как в day_marks) |
| body | text | NOT NULL — текст рефлексии |
| created_at | timestamptz | NOT NULL DEFAULT now() |
- CHECK ck_day_reflections_position_positive: stage_no > 0 AND module_no > 0 AND day_no > 0.
- CHECK ck_day_reflections_body_len: char_length(btrim(body)) >= 2 AND char_length(body) <= 2000.
- Индекс day_reflections_pid_day_idx (pid, stage_no, module_no, day_no, created_at), не уникальный.
Почему так: для ревёрта отдельной колонки нет — каждая сдача даёт новую строку; история дня — все строки по (pid, позиция), сортировка по created_at, действующая — последняя; попытку отличает day_started_at. UNIQUE нет: повтор запроса гасит idempotency_keys (api-refl-1), и будущий ревёрт не упрётся в ограничение. updated_at нет — строки не меняются. Имя колонки body, как у атрибута TextRegistry.body.
Лимит 2000 символов [ПРОЕКТИРОВЩИК-тех, вопрос ШТАБу Ш-1]: пост в тему «Рефлексии» (шапка + ссылка + текст) с запасом укладывается в 4096 символов сообщения Telegram. Первым 422 отдаёт API (api-refl-1); CHECK — страховка. btrim режет только пробелы, полный strip делает API.
Права (кортеж PRIVILEGES, одна строка — одно право, как в 0010):
- app_api: INSERT (pid, stage_no, module_no, day_no, day_started_at, body); SELECT (id, pid, stage_no, module_no, day_no, day_started_at, body, created_at); USAGE на SEQUENCE day_reflections_id_seq.
  SQL: INSERT INTO day_reflections (pid, stage_no, module_no, day_no, day_started_at, body) VALUES (:pid, :s, :m, :d, :ds, :body) RETURNING id — для RETURNING нужен SELECT (id), для DEFAULT nextval — USAGE.
- app_bot: SELECT (те же 8 колонок) на day_reflections; SELECT (short_no) на tg_user_registry — метка #NNNNNN в посте bot-group-1 (в 0009 у бота только pid, tg_user_id, tombstoned_at) [ПРОЕКТИРОВЩИК-тех, вопрос ШТАБу Ш-2].
  SQL: SELECT pid, stage_no, module_no, day_no, body, created_at FROM day_reflections WHERE id = :reflection_id; SELECT tg_user_id, short_no FROM tg_user_registry WHERE pid = CAST(:pid AS uuid) AND tombstoned_at IS NULL.
- UPDATE, DELETE, TRUNCATE на day_reflections — никому; app_projector прав не получает.
- Роли app_api и app_bot — _create_role_if_missing, как в 0010.
downgrade: REVOKE SELECT (short_no) ON tg_user_registry FROM app_bot (колоночное право — отдельной строкой, как в 0009); drop_index; drop_table (права на таблицу уходят вместе с ней).
models.py: класс DayReflection по образцу AccessGrant — те же колонки, CheckConstraint и Index с теми же именами; константы REFLECTION_MIN_LEN = 2 и REFLECTION_MAX_LEN = 2000 (их импортирует api-refl-1), в CHECK модели — через f-строку; в docstring модуля — абзац «day_reflections (0011, db-1)»: append-only, права, лимит.

## 9. Тесты
test_db_roles_0011.py (по образцу test_db_roles_0010.py):
1. Статика: revision и down_revision; в PRIVILEGES нет UPDATE, DELETE, TRUNCATE на day_reflections.
2. БД, права (колоночные — через has_any_column_privilege и has_column_privilege): app_api INSERT и SELECT — да, UPDATE — нет, DELETE (has_table_privilege) — нет; app_bot SELECT body — да, INSERT и UPDATE — нет; app_bot SELECT short_no на tg_user_registry — да; app_projector на day_reflections — ничего.
3. БД, CHECK: body 'a', '   a   ', '' и строка из 2001 символа → IntegrityError; 'ab' и 2000 символов — проходят; day_no = 0 → IntegrityError; неизвестный pid → IntegrityError (FK).
4. БД: downgrade до 0010_access_grants → таблицы нет, у app_bot нет SELECT short_no; в finally — upgrade head.
Codespaces: bash tools/check.sh api (тесты с БД пропускаются). Только CI: тесты с БД, alembic upgrade/downgrade, сверка expected_tables.

## Задетые тесты (правило «Т»)
- apps/api/tests/test_db_models.py:
  1. добавить TABLES_0011 = {"day_reflections"};
  2. test_expected_tables_count_after_0010 → переименовать в test_expected_tables_count_after_0011, len == 17, добавить assert TABLES_0011 <= _expected_tables();
  3. test_upgrade_downgrade_upgrade_cycle: первым шагом command.downgrade(cfg, "0010_access_grants"), assert _tables(migrated_db) == expected - TABLES_0011, затем expected = expected - TABLES_0011; следующие шаги не менять;
  4. docstring: «head → 0010 (без day_reflections) → 0009 (без access_grants) → …».
- apps/api/tests/expected_tables.txt — список из раздела 6.
- test_models_match_live_schema — без правки (упадёт, если модель не совпадёт с миграцией).
- Не проверено (ШТАБ, до промпта): test_db_roles.py и test_db_roles_0009.py — нет ли там сверки ПОЛНОГО набора прав app_bot или app_api по всем таблицам. Если есть — добавить в ожидаемый набор day_reflections и tg_user_registry.short_no.

## 10. Живые проверки (после мержа, IRONCLAD, только main, СЕРВЕРНЫЙ)
1. Бэкап before-0011 (pg_dump -Fc, как before-0010 — infra/SERVER-IRONCLAD.md).
2. git pull; DC --profile tools build migrate; DC --profile tools run --rm --no-deps migrate alembic upgrade head.
3. alembic current → 0011_day_reflections (head); таблиц в public без alembic_version — 17.
4. psql владельцем, один запрос:
SELECT has_any_column_privilege('app_api','day_reflections','INSERT'), has_any_column_privilege('app_api','day_reflections','UPDATE'), has_table_privilege('app_api','day_reflections','DELETE'), has_any_column_privilege('app_bot','day_reflections','INSERT'), has_column_privilege('app_bot','day_reflections','body','SELECT'), has_column_privilege('app_bot','tg_user_registry','short_no','SELECT'), has_any_column_privilege('app_projector','day_reflections','SELECT');
Ожидание: t, f, f, f, t, t, f.
5. 7/7 Up, 5 healthy; в логе проектора Traceback 0. Перезапуск api и bot не нужен (кода нет).

## 11. Запреты
AGENT-BRIEF §3. Плюс: одна миграция; не трогать routers, bot, projector; UPDATE и DELETE не выдавать никому; ALTER DEFAULT PRIVILEGES не использовать; кроме текста рефлексии ПДн не хранить (имя, username — нет); миграции ниже 0010 не трогать.

## 12. Критерии готовности
CI 7/7 (upgrade и downgrade, 17 таблиц, модели = схема); РЕВЬЮЕР без блокеров; на сервере 0011, 17 таблиц, права как в п. 4 раздела 10.

## 13. Оценка
Часы Автора 1 (бэкап + выкат). Кредиты 0 (Р0+); в режиме Р1-П — 400–600.

## 14. РЕВЬЮЕР
Да — роли/GRANT БД (B-3). Проверить: колоночные права, нет UPDATE/DELETE, USAGE последовательности, REVOKE short_no в downgrade, CHECK длины.
