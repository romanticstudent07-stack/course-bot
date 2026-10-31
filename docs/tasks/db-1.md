# db-1 — миграция 0011_reflections_log (лог рефлексий)

## 1. Паспорт
- id: db-1 · PR: «feat(db): 0011_reflections_log — лог рефлексий (db-1)» · ветка: feat/db-1
- Режим: Р0+ (КОДЕР; запасной Р1-П) · зависит: —. down_revision = 0010_access_grants. Другие миграции параллельно не вести; bot-group-1 и api-refl-1 — после мержа и выката db-1.

## 2. Цель
Неизменяемый лог рефлексий дней 6 / 13-M / 13-P: таблица reflections_log, app_api INSERT/SELECT, app_bot SELECT. Код API и бота не трогать (api-refl-1, bot-group-1).

## 3. Решения
- В1 = А [Автор 30.10, К-6]: «отдельная таблица, только INSERT/SELECT, миграция 0011, РЕВЬЮЕР» (research iter2-rest.md §9).
- Имя [ШТАБ, канон, К-6]: reflections_log (build/db-tables-index.md, «Таблицы (32)»: «reflections_log | Б7 / Б14 | Append-only лог рефлексий»). research iter2-rest.md называет day_reflections — перекрыто каноном.
- Доставка [ШТАБ, Ш2–Ш3, research §3]: бот читает текст по reflection_id → GRANT SELECT для app_bot; ПДн в payload нет.
- §3 (а): ревёрт — новой строкой; < 2 символов после strip → 422 REFLECTION_REQUIRED (api-refl-1).
- Ш-1 [ШТАБ 30.10]: лимит 2000 символов. Ш-2 [ШТАБ 30.10]: SELECT (short_no) на tg_user_registry для app_bot — в 0011.
- STATE: GRANT — в той же миграции; AGENT-BRIEF §11: expected_tables.txt — в том же PR.

## 4. Выдержки канона
03 §3.12 (research §1): «минимум 2 символа; смысл не оценивается; неизменяемый лог «как замеры»; при ревёрте поле снова обязательно, старый текст — в истории; все рефлексии — Автору в Рабочую группу, тема «Рефлексии»».

## Канон и решения
(а) 03 §3.12; build/db-tables-index.md «Таблицы (32)». (б) Имя сверено с db-tables-index; колонки в каноне не заданы (db-schema.sql — 8 других таблиц) → [ПРОЕКТИРОВЩИК-тех]. Противоречий с DECISIONS нет. (г) Правок канона нет.

## 5. ЧТО ПРОЧИТАТЬ (КОДЕР)
- apps/api/migrations/versions/2026_10_24_1200-0010_access_grants_access_grants.py — 7,5 КБ
- apps/api/migrations/versions/2026_10_17_1200-0009_app_bot_app_bot.py — 5,1 КБ
- apps/api/app/db/models.py — 14,6 КБ
- apps/api/tests/test_db_models.py — 5,4 КБ
- apps/api/tests/test_db_roles_0010.py — 14,3 КБ (образец)
- apps/api/tests/test_db_roles_0009.py — 9,5 КБ
- apps/api/tests/expected_tables.txt — 0,6 КБ
- apps/api/tests/conftest.py — 8,1 КБ
Чтение КОДЕРА ≈ 65,1 КБ.

## 6. Файлы
- Создать: apps/api/migrations/versions/2026_10_31_1200-0011_reflections_log_reflections_log.py; apps/api/tests/test_db_roles_0011.py.
- Изменить: apps/api/app/db/models.py; apps/api/tests/expected_tables.txt; apps/api/tests/test_db_models.py; apps/api/tests/test_db_roles_0009.py.
- expected_tables.txt: в конец «# 0011_reflections_log» и reflections_log. Всего 17: participant_state, stage_publish_log, outbox, outbox_dlq, issuance_log, anomaly_log, erasure_blacklist, privacy_audit_log, tg_user_registry, text_registry, consent_events, participant_events, participant_state_checkpoints, idempotency_keys, day_marks, access_grants, reflections_log.

## 7. Контракт
API и бот не меняются; контракт — таблица и права (раздел 8).

## 8. БД
revision "0011_reflections_log", down_revision "0010_access_grants", Create Date 2026-10-31 12:00:00. Docstring по образцу 0010: зачем; права и SQL; «таблиц после миграции — 17».
Таблица reflections_log [ПРОЕКТИРОВЩИК-тех, К-6]:
| колонка | тип | ограничения |
|---|---|---|
| id | bigint | PK reflections_log_pkey, autoincrement (reflections_log_id_seq) |
| pid | uuid | NOT NULL, FK tg_user_registry.pid (reflections_log_pid_fkey) |
| stage_no, module_no, day_no | integer | NOT NULL — позиция дня |
| day_started_at | timestamptz | NOT NULL — попытка дня (как в day_marks) |
| body | text | NOT NULL |
| created_at | timestamptz | NOT NULL DEFAULT now() |
- CHECK ck_reflections_log_position_positive: stage_no > 0 AND module_no > 0 AND day_no > 0.
- CHECK ck_reflections_log_body_len: char_length(btrim(body)) >= 2 AND char_length(body) <= 2000.
- Индекс reflections_log_pid_day_idx (pid, stage_no, module_no, day_no, created_at), не уникальный.
Почему: каждая сдача — новая строка, действующая — последняя по created_at; UNIQUE нет (повтор гасит idempotency_keys); updated_at нет. 2000 — пост в тему с запасом влезает в 4096 символов Telegram; 422 отдаёт API, CHECK — страховка.
Права (PRIVILEGES, одна строка — одно право, как в 0010):
- app_api: INSERT (pid, stage_no, module_no, day_no, day_started_at, body); SELECT (id, pid, stage_no, module_no, day_no, day_started_at, body, created_at); USAGE на SEQUENCE reflections_log_id_seq.
  SQL: INSERT INTO reflections_log (pid, stage_no, module_no, day_no, day_started_at, body) VALUES (:pid, :s, :m, :d, :ds, :body) RETURNING id — RETURNING требует SELECT (id), nextval — USAGE.
- app_bot: SELECT (те же 8 колонок) на reflections_log; SELECT (short_no) на tg_user_registry — метка #NNNNNN в посте bot-group-1.
  SQL: SELECT pid, stage_no, module_no, day_no, body, created_at FROM reflections_log WHERE id = :reflection_id; SELECT tg_user_id, short_no FROM tg_user_registry WHERE pid = CAST(:pid AS uuid) AND tombstoned_at IS NULL.
- UPDATE, DELETE, TRUNCATE на reflections_log — никому; app_projector — ничего. Роли — _create_role_if_missing, как в 0010.
downgrade: REVOKE SELECT (short_no) ON tg_user_registry FROM app_bot (как в 0009); drop_index; drop_table.
models.py: класс ReflectionLog по образцу AccessGrant — те же колонки, CheckConstraint и Index с теми же именами; константы REFLECTION_MIN_LEN = 2, REFLECTION_MAX_LEN = 2000 (для api-refl-1), в CHECK — через f-строку; в docstring модуля — абзац «reflections_log (0011, db-1)».

## 9. Тесты
test_db_roles_0011.py (по образцу test_db_roles_0010.py):
1. Статика: revision и down_revision; в PRIVILEGES нет UPDATE, DELETE, TRUNCATE на reflections_log.
2. БД, права: app_api INSERT и SELECT — да, UPDATE и DELETE — нет; app_bot SELECT body — да, INSERT и UPDATE — нет; app_bot SELECT short_no на tg_user_registry — да; app_projector на reflections_log — ничего.
3. БД, CHECK: body 'a', '   a   ', '' и 2001 символ → IntegrityError; 'ab' и 2000 символов — проходят; day_no = 0 и неизвестный pid → IntegrityError.
4. БД: downgrade до 0010_access_grants → таблицы нет, у app_bot нет SELECT short_no; в finally — upgrade head.
Codespaces: bash tools/check.sh api. Только CI: тесты с БД, upgrade/downgrade, expected_tables.

## Задетые тесты (правило «Т»)
- apps/api/tests/test_db_models.py:
  1. TABLES_0011 = {"reflections_log"};
  2. test_expected_tables_count_after_0010 → test_expected_tables_count_after_0011, len == 17, плюс assert TABLES_0011 <= _expected_tables();
  3. test_upgrade_downgrade_upgrade_cycle: первым шагом command.downgrade(cfg, "0010_access_grants"), assert _tables(migrated_db) == expected - TABLES_0011, затем expected = expected - TABLES_0011; дальше не менять;
  4. docstring: «head → 0010 (без reflections_log) → 0009 (без access_grants) → …».
- apps/api/tests/expected_tables.txt — список из раздела 6.
- apps/api/tests/test_db_roles_0009.py: из COLUMN_PRIVILEGES_0009 удалить строку ("app_bot", "tg_user_registry", "short_no", "SELECT", False) — после 0011 право есть; проверка True — test_db_roles_0011.py (раздел 9 п.2). test_downgrade_0009 — без правки (downgrade 0011 снимает short_no раньше).
- Без правки (проверено ШТАБом): test_db_roles.py (сверки полного набора прав нет); test_db_roles_0010.py::test_backfill_0010 (TRUNCATE … tg_user_registry CASCADE чистит reflections_log); conftest.db_engine (CASCADE покрывает FK); test_models_match_live_schema.

## 10. Живые проверки (после мержа, IRONCLAD, только main, СЕРВЕРНЫЙ)
1. Бэкап before-0011 (pg_dump -Fc, как before-0010 — infra/SERVER-IRONCLAD.md).
2. git pull; DC --profile tools build migrate; DC --profile tools run --rm --no-deps migrate alembic upgrade head.
3. alembic current → 0011_reflections_log (head); таблиц без alembic_version — 17.
4. psql владельцем:
SELECT has_any_column_privilege('app_api','reflections_log','INSERT'), has_any_column_privilege('app_api','reflections_log','UPDATE'), has_table_privilege('app_api','reflections_log','DELETE'), has_any_column_privilege('app_bot','reflections_log','INSERT'), has_column_privilege('app_bot','reflections_log','body','SELECT'), has_column_privilege('app_bot','tg_user_registry','short_no','SELECT'), has_any_column_privilege('app_projector','reflections_log','SELECT');
Ожидание: t, f, f, f, t, t, f.
5. 7/7 Up, 5 healthy; Traceback в логе проектора — 0. Перезапуск api и bot не нужен.

## 11. Запреты
AGENT-BRIEF §3. Плюс: одна миграция; не трогать routers, bot, projector; UPDATE/DELETE никому; без ALTER DEFAULT PRIVILEGES; ПДн кроме текста рефлексии не хранить; миграции ниже 0010 не трогать.

## 12. Критерии готовности
CI 7/7 (upgrade/downgrade, 17 таблиц, модели = схема); РЕВЬЮЕР без блокеров; на сервере 0011, 17 таблиц, права как в п. 4 раздела 10.

## 13. Оценка
Часы Автора 1 (бэкап + выкат). Кредиты 0 (Р0+); Р1-П — 400–600.

## 14. РЕВЬЮЕР
Да — роли/GRANT БД (B-3). Проверить: колоночные права, нет UPDATE/DELETE, USAGE последовательности, REVOKE short_no в downgrade, CHECK длины.
