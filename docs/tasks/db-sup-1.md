# db-sup-1 — таблица support_questions, миграция 0017

## 1. Паспорт
- id: db-sup-1 (PLAN §5 п.13, Р-19). Заголовок PR: feat(db): support_questions — вопросы поддержки, миграция 0017 (db-sup-1)
- Ветка: feat/db-sup-1. Режим: Агент Р1. РЕВЬЮЕР: да (GRANT, B-3).
- Зависит от: последней миграции в main. down_revision = "0015_onboarding_form" — сверяет ШТАБ перед промптом: если раньше смержена 0016 — она.
- Начинать после мержа всех открытых PR с миграциями (миграции по одной).

## 2. Цель
Таблица вопросов в поддержку (Р-19): текст вопроса хранится в БД, в outbox идёт только id (DLQ копирует payload целиком). Код темы — в строке; номер темы группы — в .env бота, в БД его нет. API (api-sup-1) пишет, бот (bot-sup-1) читает для поста. Кода API и бота в задаче нет.

## 3. Решения Автора (дословно)
- Р-19 (13.11): «поддержка: кнопка «Помощь» — после 18+ и согласий, всегда внизу Mini App и пунктом «Меню»; экран: тема кнопкой → вопрос (черновик хранится) → пост в тему группы этой темы (подпись Р-15, «Карточка»). Тем 8: «Поддержка 1»…«Поддержка 7» и «Другое», у каждой своя тема группы; названия — заглушки, заменить до показа участникам курса.»
- Номер 0016 зарезервирован за журналом списаний (решение Автора 12.11, по старту ШТАБа).
- PLAN §5 п.22: «22. Erasure с cooling-off 14 дней + GRANT tombstone проектору. А 1, Р 1.»
- onboarding_form (Автор 07.11, В1 = А, по старту ШТАБа): DELETE строк по pid после паузы 14 дней; GRANT DELETE роли стирания — в п.22; app_api DELETE не получает.

## 4. Выдержки (КОДЕР канон не читает)
- docs/research/bot-i3-3.md §3 п.4: POST /miniapp/v1/support/question, X-Client-Op-Id; одна транзакция под active_pid_locked: частота → INSERT support_questions ON CONFLICT (pid, client_op_id) DO NOTHING RETURNING id → если вставлено, INSERT outbox → commit. Повтор с тем же id → 201 без новой строки.
- §3 п.5: outbox event_type support_question, payload {"pid", "question_id"}; текста в payload нет. Ключ идемпотентности — UNIQUE (pid, client_op_id); idempotency_keys не трогаем.
- §3 п.6: не чаще 1 вопроса в 30 с на pid — max(created_at) под замком.
- §5: образцы — reflections_log (текст в своей таблице, CHECK 2…2000) и measurements_log (UNIQUE (pid, client_op_id), client_op_id 1…64).

## 5. ЧТО ПРОЧИТАТЬ (по hash из промпта)
- AGENT-BRIEF.md; эта карточка (≈ 15 КБ).
- apps/api/app/db/models.py — 25,6; apps/api/migrations/versions/2026_11_08_1200-0015_onboarding_form_onboarding_form.py — 4,5;
  apps/api/migrations/versions/2026_10_31_1200-0011_reflections_log_reflections_log.py — 5,8;
  apps/api/tests/test_db_roles_0015.py — 14,8; apps/api/tests/expected_tables.txt — 1,0;
  apps/api/tests/test_db_models.py — 5,5.
- Чтение Агента ≈ 57,5 КБ + карточка + AGENT-BRIEF.

## 6. Файлы
- Создать: apps/api/migrations/versions/2026_11_14_1200-0017_support_questions_support_questions.py (≈ 120 строк, образец 0015 + последовательность и индекс из 0011).
- Создать: apps/api/tests/test_db_roles_0017.py (≈ 260 строк, образец test_db_roles_0015.py).
- Изменить: apps/api/app/db/models.py (+≈ 55: блок docstring, константы, класс SupportQuestion).
- Изменить: apps/api/tests/expected_tables.txt — полный новый список (раздел 8).
- Изменить: apps/api/tests/test_db_models.py (≈ +8 строк, раздел 10).

## 7. Контракт SQL (его проверяют тесты; код — api-sup-1 и bot-sup-1)
- app_api, запись:
    INSERT INTO support_questions (pid, topic_code, body, client_op_id)
    VALUES (:pid, :topic, :body, :op) ON CONFLICT (pid, client_op_id) DO NOTHING RETURNING id
- app_api, частота: SELECT max(created_at) FROM support_questions WHERE pid = :pid
- app_bot, пост: SELECT pid, topic_code, body, created_at FROM support_questions WHERE id = :question_id
Эндпоинтов в задаче нет.

## 8. БД
- revision = "0017_support_questions"; down_revision — раздел 1. TABLE = "support_questions"; ROLES = ("app_api", "app_bot").
- Колонки: id bigint PK автоинкремент (последовательность support_questions_id_seq, PK support_questions_pkey); pid uuid NOT NULL, FK → tg_user_registry.pid (support_questions_pid_fkey); topic_code text NOT NULL; body text NOT NULL; client_op_id text NOT NULL; created_at timestamptz NOT NULL DEFAULT now(). updated_at нет.
- CHECKS (имя, условие) — у каждого явный IS NOT NULL (У3):
  - ck_support_questions_topic_code: topic_code IS NOT NULL AND topic_code IN ('s1', 's2', 's3', 's4', 's5', 's6', 's7', 'other') [ШТАБ-тех]
  - ck_support_questions_body_len: body IS NOT NULL AND char_length(btrim(body)) >= 2 AND char_length(body) <= 2000
  - ck_support_questions_client_op_id: client_op_id IS NOT NULL AND char_length(client_op_id) BETWEEN 1 AND 64
- UNIQUE (pid, client_op_id) — support_questions_pid_client_op_id_key. Индекс support_questions_pid_created_idx (pid, created_at), не уникальный.
- PRIVILEGES (право, объект, роль), одна строка — одно право, GRANT только в цикле:
  - ("INSERT (pid, topic_code, body, client_op_id)", "TABLE support_questions", "app_api")
  - ("SELECT (id, pid, client_op_id, created_at)", "TABLE support_questions", "app_api") — RETURNING id, ON CONFLICT, частота
  - ("USAGE", "SEQUENCE support_questions_id_seq", "app_api") — DEFAULT nextval
  - ("SELECT (id, pid, topic_code, body, created_at)", "TABLE support_questions", "app_bot")
- app_projector прав не получает. UPDATE, DELETE, TRUNCATE не выданы никому. ALTER DEFAULT PRIVILEGES и PUBLIC не используются. Роли — _create_role_if_missing, как в 0015.
- models.py: SUPPORT_TOPIC_CODES = ("s1", "s2", "s3", "s4", "s5", "s6", "s7", "other"); SUPPORT_BODY_MIN_LEN = 2; SUPPORT_BODY_MAX_LEN = 2000; SUPPORT_CLIENT_OP_ID_MAX_LEN = 64. Класс SupportQuestion: колонки, имена ограничений и тексты CHECK — буква в букву как в миграции (topic_code — через _in_list).
- Docstring миграции и блок в docstring models.py — по образцу 0015: SQL раздела 7, «Таблиц после миграции — 20» (если раньше смержена 0016 с таблицей — 21).
- downgrade: DROP INDEX, затем DROP TABLE (права и последовательность уходят с таблицей; на чужих таблицах 0017 прав не выдаёт); роли не удаляются.
- expected_tables.txt: весь текущий список без изменений, в конце две строки: «# 0017_support_questions» и «support_questions». Если раньше смержена 0016 — её строки остаются.

## 9. Тесты (apps/api/tests/test_db_roles_0017.py; tg_user_id 4201–4299)
Статика (без БД):
- test_revision_0017: revision, down_revision.
- test_privileges_static_0017: ROLES; PRIVILEGES == EXPECTED; нет app_projector; нет UPDATE/DELETE/TRUNCATE; нет ALTER DEFAULT PRIVILEGES и «PUBLIC» в коде без docstring; «GRANT » в коде ровно 1 раз.
- test_models_match_checks_0017: CHECKS миграции == строки из констант models; набор колонок SupportQuestion == {id, pid, topic_code, body, client_op_id, created_at}.
С БД (только CI):
- test_api_contract_0017: INSERT под app_api → id > 0; повтор с тем же (pid, client_op_id) → None, строка одна; тот же client_op_id у другого pid проходит; запрос частоты под app_api отдаёт не NULL.
- test_bot_reads_0017: запрос бота раздела 7 под app_bot → pid, topic_code, body, created_at.
- test_privileges_0017 (has_column_privilege / has_any_column_privilege / has_sequence_privilege): api INSERT topic_code да; api INSERT id и created_at нет; api SELECT body и topic_code нет; api seq USAGE да; bot SELECT body и topic_code да; bot SELECT client_op_id нет; bot INSERT нет; projector SELECT и INSERT нет; public SELECT нет.
- test_no_update_delete_truncate_0017: has_table_privilege — у app_api, app_bot, app_projector нет UPDATE/DELETE/TRUNCATE.
- Отказы через _assert_denied: api — SELECT body, UPDATE, DELETE, TRUNCATE; bot — INSERT, SELECT client_op_id, UPDATE, DELETE; projector — SELECT id.
- test_check_rejected_0017 (CheckViolation + имя): topic «s0», «s8», «S1», «», «other » (пробел); body «a», «   a   », «», 2001×«x», 2001×«я»; client_op_id «», 65×«x».
- test_check_accepted_0017: каждый из 8 кодов; body «ab», 2000×«x», 2000×«я»; client_op_id 64×«x».
- test_not_null_0017: NULL в pid, topic_code, body, client_op_id → NotNullViolation и diag.column_name (NOT NULL срабатывает раньше CHECK).
- test_duplicate_op_rejected_0017 (UniqueViolation, имя UNIQUE); test_unknown_pid_rejected_0017 (FK, имя); test_index_0017 (pg_indexes: имя, колонки pid, created_at).
- test_downgrade_0017 — ПОСЛЕДНИМ: downgrade до down_revision → таблицы нет, onboarding_form и право app_api INSERT на ней целы; upgrade head → таблица есть; finally — upgrade head.
Цели: bash tools/check.sh api. Только CI: тесты с БД, alembic upgrade/downgrade, сверка expected_tables.

## 10. Задетые тесты (правило «Т»)
- apps/api/tests/expected_tables.txt — полный новый список (раздел 8).
- apps/api/tests/test_db_models.py: константа TABLES_0017 = {"support_questions"}; тест test_expected_tables_count_after_0015 переименовать в test_expected_tables_count_after_0017, внутри == 20 и TABLES_0017 <= _expected_tables(); test_upgrade_downgrade_upgrade_cycle начинается с command.downgrade(cfg, "0015_onboarding_form") и проверки expected - TABLES_0017, дальше expected = expected - TABLES_0017 и прежние шаги без изменений; docstring модуля: «head → 0015 (без support_questions) → 0014 …». Если раньше смержена 0016 с таблицей — 21 и шаг через неё (сверяет ШТАБ перед промптом). Остальные тесты файла не трогать.
- Проверено, правка не нужна: test_db_roles_0009.py — права по своим таблицам, полного набора прав нет; test_db_roles_0011.py — фильтр по reflections_log; test_db_roles_0013.py и test_db_roles_0015.py — сверяют PRIVILEGES своего модуля. Их downgrade-тесты от head проходят через downgrade 0017 — он обязан работать.
- Упал тест вне списка → не чинить, «тест X вне списка» в ИТОГ, стоп.

## 11. Живые проверки (после мержа, при выкате; PLAN §4)
- Бэкап before-0017 и build migrate — как перед 0015 (STATE «Норма сервера»); потом migrate.
- alembic current = 0017_support_questions; \d support_questions — колонки, 3 CHECK, UNIQUE, индекс; has_column_privilege('app_api', 'support_questions', 'body', 'INSERT') = t, а для 'SELECT' = f.
- Порядок выката пачки: migrate → бот → api → miniapp (исследование §4 Б4).

## 12. Запреты
- AGENT-BRIEF §3: не править docs/architecture/**, .github/**, .githooks/**, .env; не пушить в main.
- Не выдавать UPDATE, DELETE, TRUNCATE никому и права app_projector; не выдавать права на другие таблицы.
- Не трогать код API, бота, idempotency_keys, day_keys; номер 0016 не занимать.

## 13. Критерии готовности
Файлы раздела 6; тесты раздела 9; check.sh api зелёный; в PR — «Прочитано» и таблица проверок. Тесты с БД и alembic зелёные — в CI, их смотрит Автор.

## 14. Оценка
Часы Автора ≈ 0,5. Кредиты ≈ 450 строк × 0,75–1,0 + 2 файла «Задетых» × 60–100 = 460–650.

## Канон и решения
(а) Канон: P4 §4.6 (через исследование §1), DECISIONS Р-19. Таблица support_questions в каноне (99-02, 99-03, db-tables-index) — не проверено в этом окне.
(б) Р-19 перекрывает P4 §4.6 в механике поддержки; таблицы касается только «Тем 8» → topic_code [ШТАБ-тех]. Структура таблицы и права — [ШТАБ-тех] (исследование §5).
(в) Правок канона в этой задаче нет. Правки по Р-19 — исследование §8 (в), они идут перед bot-sup-1 и miniapp-sup-1.

## Требования к п.22 (стирание; кода в этой задаче нет)
- Факты: body — свободный текст участника, может содержать ПДн; topic_code ПДн не несёт; outbox и DLQ хранят только pid и question_id (FK нет). Пост уже в теме группы: стирание в БД его не удаляет.
- Вопрос Автору (К-4 а): после сверки 99-02 и 99-03, сейчас не задан. Варианты:
  А — DELETE строк по pid после 14 дней, как у onboarding_form; GRANT DELETE роли стирания в п.22; app_api DELETE не получает. Плюс: текст исчезает. Минус: ещё один GRANT DELETE.
  Б — обезличивание через tombstone (строка остаётся у стёртого pid). Плюс: без DELETE. Минус: текст с ПДн остаётся; затереть его нельзя без UPDATE, а пустой body запрещён CHECK.
  Мнение: А.
- Что делать с постами в группе при стирании — к п.22 и юристу (К-4 в).
