# db-2 — права app_api на INSERT в outbox: миграция 0012 и тесты
Правило К — docs/process/CANON-CHECK.md. Карточка по решению Автора 03.11 (вариант А), ответам ШТАБа 03.11 и коду @fbaa460.

## 1. Паспорт
- id: db-2. Заголовок PR: «feat(db): права app_api на INSERT в outbox — миграция 0012 (db-2)». Ветка: feat/db-2.
- Режим: Р0+ (КОДЕР, 0 кредитов). РЕВЬЮЕР: да (раздел 14).
- Зависит от: db-1 (0011_reflections_log в main). Дальше: api-refl-1, затем miniapp-refl-1.
- Миграция в задаче одна. Параллельных задач с миграциями нет; down_revision = последняя миграция main.

## 2. Цель
API (роль app_api) должен писать строку outbox reflection_submitted в одной транзакции с INSERT в reflections_log (api-refl-1, раздел 7, Т7). Сейчас прав на outbox у app_api нет: в 0009 INSERT на outbox выдан только app_projector.
Миграция 0012_outbox_api выдаёт app_api ровно два права: колоночный INSERT (aggregate_id, event_type, payload, tx_id) на outbox и USAGE на outbox_id_seq — один в один как у app_projector в 0009.
Новых таблиц нет (их 17), expected_tables.txt не трогаем. Плюс в эту же задачу — тесты 0011 от РЕВЬЮЕРА (PR #157) и новый файл тестов 0012.

## 3. Решения Автора и ШТАБа
- Решение Автора 03.11, вариант А [К-6: Автор, канон проверен — 0001 роль outbox_writer «пишет в outbox (транзакционно с доменом)»; 0009 docstring В14; кто пишет reflection_submitted — канон молчит]: строку outbox reflection_submitted пишет API (app_api) в той же транзакции, что и INSERT reflections_log.
- ШТАБ 03.11 (К-5): SELECT на outbox роли app_api не давать (RETURNING запрещён контрактом); sent_at писать нельзя; UPDATE, DELETE, TRUNCATE нет; ALTER DEFAULT PRIVILEGES не использовать; роль не удалять в downgrade.
- ШТАБ 03.11 (К-5): тесты 0011 от РЕВЬЮЕРА #157 идут в существующий apps/api/tests/test_db_roles_0011.py, нового файла не создавать.

## 4. Выдержки архитектуры и кода (КОДЕР архитектуру не читает)
- docs/architecture/build/db-schema.sql, раздел «РОЛИ», дословно: CREATE ROLE outbox_writer;   -- пишет в outbox (транзакционно с доменом)
- По коду, apps/api/migrations/versions/2026_10_17_1200-0009_app_bot_app_bot.py (docstring, В4 = В): права выданы прямо ролям app_*; app_projector пишет outbox и получил INSERT (aggregate_id, event_type, payload, tx_id) + USAGE outbox_id_seq; SELECT на outbox у app_projector нет, поэтому RETURNING запрещён; sent_at ставит только app_bot.
- По коду, docs/tasks/api-refl-1.md, раздел 7, Т7: INSERT в outbox из API идёт без RETURNING, tx_id = pg_current_xact_id().

## 5. ЧТО ПРОЧИТАТЬ (файлы кода, по hash main из docs/STATE.md)
- apps/api/migrations/versions/2026_10_17_1200-0009_app_bot_app_bot.py — 5,1 КБ (образец миграции прав: ROLES, PRIVILEGES, _create_role_if_missing, downgrade через reversed).
- apps/api/migrations/versions/2026_10_31_1200-0011_reflections_log_reflections_log.py — 5,8 КБ (образец оформления и docstring).
- apps/api/tests/test_db_roles.py — 9,4 КБ (role_engine, _assert_denied).
- apps/api/tests/test_db_roles_0009.py — 13,7 КБ (правка: API_DENIED_0009; образец файла тестов прав).
- apps/api/tests/test_db_roles_0011.py — 12,5 КБ (правка: пункты РЕВЬЮЕРА #157).
- apps/api/tests/conftest.py — 8,1 КБ (migrated_db, db_engine, _alembic_config).
Чтение КОДЕРА ≈ 55 КБ.

## 6. Файлы
Создать:
- apps/api/migrations/versions/2026_11_03_1200-0012_outbox_api_outbox_api.py
- apps/api/tests/test_db_roles_0012.py
Изменить:
- apps/api/tests/test_db_roles_0009.py
- apps/api/tests/test_db_roles_0011.py
Удалить: нет. expected_tables.txt не трогать (таблиц миграция не добавляет и не удаляет).

## 7. Контракт (SQL, который должен работать под app_api после 0012)
Контракт api-refl-1, раздел 7, Т7 — без RETURNING, одна транзакция с INSERT в reflections_log:

    INSERT INTO outbox (aggregate_id, event_type, payload, tx_id)
    VALUES (:pid_text, 'reflection_submitted', CAST(:payload AS jsonb), pg_current_xact_id())

Запрещено и должно давать 42501 под app_api: тот же INSERT с RETURNING id; INSERT со столбцом sent_at; любой SELECT, UPDATE, DELETE, TRUNCATE на outbox; любое обращение к outbox_dlq.

## 8. БД: миграция 0012_outbox_api
- Файл: apps/api/migrations/versions/2026_11_03_1200-0012_outbox_api_outbox_api.py (шаблон имени — как у 0009 и 0011).
- revision = "0012_outbox_api"; down_revision = "0011_reflections_log"; branch_labels = None; depends_on = None.
- Таблиц, колонок, индексов, ограничений миграция не меняет. Только GRANT.
- ROLES = ("app_api",) и функция _create_role_if_missing — скопировать из 0011 (роль кластерная, повторный прогон не должен падать).
- PRIVILEGES — ровно две строки, формат кортежа (привилегия, цель, роль) как в 0009:

    ("INSERT (aggregate_id, event_type, payload, tx_id)", "TABLE outbox", "app_api")
    ("USAGE", "SEQUENCE outbox_id_seq", "app_api")

- upgrade: сначала цикл по ROLES с _create_role_if_missing, затем цикл по PRIVILEGES с GRANT <привилегия> ON <цель> TO <роль>.
- downgrade: цикл for privilege, target, role in reversed(PRIVILEGES) с REVOKE <привилегия> ON <цель> FROM <роль>. Колоночный REVOKE идёт своей строкой (табличный REVOKE колоночное право не снимает). Роль не удаляется.
- ALTER DEFAULT PRIVILEGES не использовать. Слова PUBLIC в миграции нет.
- В docstring миграции: ссылка на решение Автора 03.11 (вариант А), на контракт api-refl-1 раздел 7 Т7 (INSERT без RETURNING) и строка «новых таблиц нет, их 17».

## 9. Тесты
Новый файл apps/api/tests/test_db_roles_0012.py — по образцу 0009 и 0011 (role_engine и _assert_denied из tests.test_db_roles, _alembic_config из tests.conftest, фикстуры api_engine и projector_engine на migrated_db):
1. Статика (образец test_privileges_static_0011): revision и down_revision; в PRIVILEGES только роль app_api; первое слово привилегии только INSERT или USAGE; «ALTER DEFAULT PRIVILEGES» не встречается в коде миграции (сравнение через .upper()); «PUBLIC» не встречается в коде миграции (без .upper()).
2. Контракт: под app_api проходит INSERT из раздела 7 без RETURNING со своим aggregate_id = str(uuid.uuid4()); строку читаем под db_engine по этому aggregate_id и проверяем event_type = 'reflection_submitted', payload совпал, sent_at IS NULL, tx_id не NULL. TRUNCATE outbox в тестах не делать: conftest outbox не чистит, RESTART IDENTITY мешает соседним тестам (как в test_notify_ops.py — поиск по своему aggregate_id).
3. Отказы под app_api (кортеж API_DENIED_0012, каждый своим соединением через _assert_denied): тот же INSERT с RETURNING id; INSERT с колонкой sent_at; SELECT id FROM outbox; SELECT * FROM outbox; UPDATE outbox SET sent_at = now(); UPDATE outbox SET payload = '{}'::jsonb; DELETE FROM outbox; TRUNCATE outbox; SELECT id FROM outbox_dlq; INSERT INTO outbox_dlq (original_id, payload, error) VALUES (1, '{}'::jsonb, 'e').
4. Права (параметризация по строкам SQL под db_engine, как PRIVILEGE_CHECKS_0011): has_column_privilege('app_api','outbox',c,'INSERT') = true для aggregate_id, event_type, payload, tx_id; то же = false для id, created_at, sent_at; has_any_column_privilege('app_api','outbox','SELECT') = false; то же для 'UPDATE' = false; has_table_privilege('app_api','outbox','DELETE') и ('app_api','outbox','TRUNCATE') = false; has_sequence_privilege('app_api','outbox_id_seq','USAGE') = true; has_sequence_privilege('public','outbox_id_seq','USAGE') = false; has_table_privilege('public','outbox','INSERT') = false; права 0009 целы: has_any_column_privilege('app_projector','outbox','INSERT') = true и has_sequence_privilege('app_projector','outbox_id_seq','USAGE') = true.
5. ПОСЛЕДНИМ в файле test_downgrade_0012: до downgrade права app_api из пункта 4 true; command.downgrade(cfg, "0011_reflections_log") — колоночный INSERT и USAGE у app_api стали false, а права app_projector из 0009 остались true; в finally command.upgrade(cfg, "head").
Правки в apps/api/tests/test_db_roles_0011.py (пункты РЕВЬЮЕРА, PR #157):
6. В test_privileges_static_0011 добавить: «PUBLIC» не встречается в _migration_code(module) — без .upper() (в коде 0011 есть слово public в именах и импортах, .upper() дал бы ложное срабатывание). Существующая строка про ALTER DEFAULT PRIVILEGES с .upper() остаётся как есть.
7. В PRIVILEGE_CHECKS_0011 добавить строки: ("public-select", "has_table_privilege('public', 'reflections_log', 'SELECT')", False); ("api-insert-id", "has_column_privilege('app_api', 'reflections_log', 'id', 'INSERT')", False); ("api-insert-created-at", "has_column_privilege('app_api', 'reflections_log', 'created_at', 'INSERT')", False).
8. Кириллица: в test_body_len_rejected_0011 добавить параметр "я" * 2001 с id len-2001-cyrillic, в test_body_len_accepted_0011 — "я" * 2000 с id len-2000-cyrillic. Над параметрами одна строка комментария: CHECK считает char_length (символы), не байты.
9. В test_downgrade_0011 (остаётся последним в файле) добавить: после downgrade до 0010 права 0009 у app_bot на tg_user_registry целы по колонкам pid и tombstoned_at (обе проверки true, рядом с имеющейся проверкой tg_user_id); затем в теле теста command.upgrade(cfg, "head") и проверка, что таблица reflections_log снова есть и SELECT (short_no) у app_bot вернулся (обе true). Блок finally с command.upgrade(cfg, "head") оставить без правок, upgrade идемпотентен.
Цели tools/check.sh: api.
Только CI (нужна БД): всё, кроме статических тестов пункта 1 и пункта 6.

## Задетые тесты (правило «Т»)
Правка нужна одному файлу:
- apps/api/tests/test_db_roles_0009.py — из кортежа API_DENIED_0009 убрать элемент INSERT_OUTBOX_LITERAL (после 0012 этот INSERT проходит). Остаются "SELECT id FROM outbox" и "SELECT id FROM outbox_dlq". Саму константу INSERT_OUTBOX_LITERAL не удалять: её используют BOT_DENIED_0009 и PROJECTOR_DENIED_0009. GRANTED_0009 и COLUMN_PRIVILEGES_0009 про app_api не утверждают ничего — не трогать.
Правок 0, но эти тесты теперь проходят через новый downgrade 0012 (упал такой тест — это дефект downgrade, не правь тест, напиши в ИТОГ):
- test_db_roles_0009.py::test_downgrade_0009; test_db_roles_0010.py::test_backfill_0010; test_db_roles_0011.py::test_downgrade_0011; test_db_roles.py::test_downgrade_revokes_privileges; test_db_models.py::test_upgrade_downgrade_upgrade_cycle; фикстура migrated_db в conftest.py (downgrade base, upgrade head).
Сверено ШТАБом, правок 0: test_notify_ops.py (outbox только под владельцем и app_projector), .github/workflows/ci.yml (зашитых ревизий нет), test_db_roles.py кортеж API_DENIED (outbox там нет), test_db_models.py и test_migration_init.py, expected_tables.txt (17 таблиц).

## 10. Живые проверки на сервере после мержа (делает СЕРВЕРНЫЙ по заданию ШТАБа)
- Бэкап БД с меткой before-0012 до миграции.
- Сборка и прогон контейнера миграций (профиль tools), затем alembic upgrade head; ожидаемая текущая ревизия — 0012_outbox_api.
- Проверка прав под владельцем:

    SELECT has_column_privilege('app_api','outbox','aggregate_id','INSERT'),
           has_column_privilege('app_api','outbox','sent_at','INSERT'),
           has_sequence_privilege('app_api','outbox_id_seq','USAGE'),
           has_table_privilege('app_api','outbox','SELECT');

  Ожидаемо: t, f, t, f.
- Аккаунты и тестовые участники не нужны: задача прав не создаёт данных.
- Выкат один общий: migrate 0012, затем api (api-refl-1), затем miniapp (miniapp-refl-1). Задание серверу даёт ШТАБ.

## 11. Запреты
- Права шире раздела 8 не выдавать. Получил permission denied на право вне раздела 8 — права не расширять, остановиться и написать в ИТОГ.
- SELECT на outbox роли app_api не давать ни в каком виде; RETURNING в контрактном SQL не появляться.
- ALTER DEFAULT PRIVILEGES, GRANT TO PUBLIC, GRANT ALL — нельзя.
- Роли в downgrade не удалять; чужие права (0009, 0010, 0011) не трогать.
- expected_tables.txt, ci.yml, docs/architecture/**, .github/**, .githooks/**, .env — не трогать.
- Вторую миграцию в этой задаче не создавать. Код API (запись в outbox) — это api-refl-1, здесь его нет.
- Секретов, реальных ID, IP и ПДн в коде и тестах нет; тексты курса — только заглушки.

## 12. Критерии готовности
- tools/check.sh api зелёный; CI зелёный (7 проверок), включая сверку expected_tables (17 таблиц).
- Контрактный INSERT под app_api проходит, все запреты раздела 9 пункта 3 дают 42501.
- test_downgrade_0012 проходит и возвращает схему на head; downgrade-тесты 0009, 0010, 0011 и цикл test_db_models зелёные.
- В API_DENIED_0009 нет INSERT_OUTBOX_LITERAL, прочие запреты на месте; пять пунктов РЕВЬЮЕРА #157 в test_db_roles_0011.py закрыты.
- Отличия от карточки, если они есть, перечислены в описании PR.

## 13. Оценка
Часы Автора: ≈ 0,5–0,7 (раскладка, check.sh, PR, живая проверка). Кредиты: 0 (режим Р0+).

## 14. РЕВЬЮЕР
Да. Основание — B-3 (роли и GRANT в БД). Одно окно на этот PR, стартовое сообщение даёт ШТАБ.

## Канон и решения
(а) Задача использует docs/architecture/build/db-schema.sql, раздел «РОЛИ» (роль outbox_writer — «пишет в outbox (транзакционно с доменом)»); остальное — по коду 0009 и по карточке api-refl-1 раздел 7.
(б) Противоречий с docs/decisions/DECISIONS.md нет: страница решений про outbox и роли БД молчит.
(в) Кто пишет событие reflection_submitted — канон молчит, действует решение Автора 03.11 (вариант А), метка К-6. Выдача права прямо роли app_api, а не роли outbox_writer, — уже принятая практика 0006 и 0009, нового расхождения нет.
(г) Правок канона нет.

## Вне задачи
Код API, который пишет строку outbox, и 422 REFLECTION_REQUIRED — api-refl-1. Доставка события в тему «Рефлексии» — bot-group-1. Таблица reflections_log и её права — db-1 (0011). Поле рефлексии в Mini App — miniapp-refl-1. Компакция outbox по sent_at (INV-3) — не эта задача.
