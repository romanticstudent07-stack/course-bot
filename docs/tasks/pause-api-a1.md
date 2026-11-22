# pause-api-a1 — таблица security_events (0022) и запись события в отдельной транзакции

## 1. Шапка
- id: pause-api-a1 · заголовок PR: «feat(api): 0022 security_events + record_security_event (pause-api-a1)»
- ветка: feat/pause-api-a1 · режим: Р0+ (КОДЕР, бесплатно; кредиты 0) · РЕВЬЮЕР: да (B-3)
- зависит от: нет (0021 в main). Миграция 0022 — номер назначил ШТАБ. A2 (вызов из POST пауз) — после мержа A1.
- Почему КОДЕР: образцы 0018 и test_db_roles_0021.py покрывают всё; тесты с БД идут только в CI.
- Бюджет чтения КОДЕРА (SHTAB.md 3-Б): CODER.md (размер — ШТАБ) + PACK.md 12,7 + AGENT-BRIEF.md 17,1 + DECISIONS.md 7,8 + карточка ≈10 + файлы раздела 5 (без models.py) 34,1 + models.py (размер — ШТАБ) = 81,7 КБ + CODER.md + models.py; цель ≤ 135 КБ. Если models.py с CODER.md больше 53 КБ — ШТАБ кладёт в карточку выдержку класса IdempotencyKey вместо models.py.

## 2. Цель
Долговечная запись события client_op_id_conflict: новая таблица security_events (миграция 0022), права ролей, функция record_security_event, которая пишет в СВОЁМ соединении и своей транзакции — откат транзакции запроса перед 409 запись не стирает. Вызов из POST пауз и сверка параметров повтора — НЕ здесь (A2).

## 3. Решения Автора (дословно)
R-2026-11-21.md, «Носитель события client_op_id_conflict (22.11.2026)»: «событие client_op_id_conflict пишется долговечной записью в новую отдельную таблицу security_events, в отдельной транзакции, чтобы запись не терялась при откате транзакции запроса перед ответом 409. privacy_audit_log (152-ФЗ, доступ к ПДн) для этого не используется; строка серверного лога без записи в БД аудитом не считается.» «Не утверждены: колонки, права ролей, срок хранения, политика отказа записи, номер миграции — решают ПРОЕКТИРОВЩИК и ШТАБ в карточке A1. Триггер — только доказанная коллизия op-id.» Метка: [Автор, канон молчит].

## 4. Выдержки архитектуры
- И2 §idempotency_keys.behavior_on_collision: «conflicting_params: return 409 + log conflict event».
- И4 §mini_app_client.R339_indexeddb_cache.conflict_ux: «log: security_audit event client_op_id_conflict».
- OVERRIDES.yaml §AD-01: аудит — только доказанная коллизия op-id; бизнес-409 — без аудита.
- Носитель события, колонки и права в каноне не заданы (db-schema.sql — только privacy_audit_log).

## 5. ЧТО ПРОЧИТАТЬ (целиком)
- apps/api/migrations/versions/2026_11_16_1200-0018_pauses_pauses.py — 14,5 (образец DDL, CHECK, PRIVILEGES, роли)
- apps/api/tests/test_db_roles_0021.py — 10,7 (образец ролевого теста: статика, has_*_privilege, downgrade последним)
- apps/api/tests/test_db_models.py — 7,7 (правка счётчика и цикла)
- apps/api/tests/expected_tables.txt — 1,2
- apps/api/app/db/models.py — размер впишет ШТАБ (новый класс по стилю IdempotencyKey)
Итог раздела без models.py — 34,1 КБ. conftest.py не читать: нужны только фикстуры migrated_db и db_engine (как в 0021) и константа UNREACHABLE_DSN = "postgresql+psycopg://nobody:nopass@127.0.0.1:1/none" из tests.conftest.

## 6. Файлы
Создать:
- apps/api/migrations/versions/2026_11_22_1200-0022_security_events_security_events.py
- apps/api/app/security_events.py
- apps/api/tests/test_db_roles_0022.py
- apps/api/tests/test_security_events.py
Изменить:
- apps/api/app/db/models.py — класс SecurityEvent
- apps/api/tests/expected_tables.txt — в конец две строки «# 0022_security_events» и «security_events» (итого 24 таблицы; остальные строки файла как есть)
- apps/api/tests/test_db_models.py — раздел «Задетые тесты»

## 7. Контракт функции (app/security_events.py)
Эндпоинтов нет. Модуль:

    CLIENT_OP_ID_CONFLICT = "client_op_id_conflict"
    INSERT_SQL = text("INSERT INTO security_events (event_type, pid, op_kind, client_op_id) "
                      "VALUES (:event_type, :pid, :op_kind, :client_op_id)")
    def record_security_event(engine: Engine, *, event_type: str, pid: uuid.UUID,
                              op_kind: str, client_op_id: str) -> bool

- Пишет через `with engine.begin() as conn:` — новое соединение из пула, НЕ сессия запроса; commit внутри. В A2 engine берётся через app.db.session.get_engine(settings).
- Без RETURNING и без SELECT: у app_api нет SELECT.
- Успех → True. Любое исключение → logger.error("security_event_write_failed (%s)", type(exc).__name__) и False; исключение наружу не выходит, поэтому 409 в A2 не ломается [ШТАБ-тех].
- Логгер "app.security_events". В лог и в исключения не попадают pid, op_kind, client_op_id, initData, токены, tg_user_id (AGENT-BRIEF §3; как session.py, D-18 — только имя класса).
- Функция не проверяет коллизию и не решает, писать ли событие: это A2.

## 8. БД: миграция 0022
- revision = "0022_security_events"; down_revision = "0021_bot_pauses_select" (сверено по test_db_roles_0021.py::test_revision_0021).
- Таблица security_events (стиль 0018, op.create_table):
  - id BigInteger PK autoincrement (последовательность security_events_id_seq), PK name security_events_pkey;
  - event_type Text NOT NULL;
  - pid UUID(as_uuid=True) NOT NULL, БЕЗ FK (стирание участника не упирается в ограничение) [ШТАБ-тех];
  - op_kind Text NOT NULL (вид операции, например pause_start);
  - client_op_id Text NOT NULL (тип и границы — как ck_participant_pauses_client_op_id в 0018);
  - created_at DateTime(timezone=True) NOT NULL server_default now().
- CHECKS (У3, имя → условие):
  - ck_security_events_event_type → "event_type IS NOT NULL AND event_type IN ('client_op_id_conflict')"
  - ck_security_events_op_kind → "op_kind IS NOT NULL AND char_length(op_kind) BETWEEN 1 AND 64"
  - ck_security_events_client_op_id → "client_op_id IS NOT NULL AND char_length(client_op_id) BETWEEN 1 AND 64"
- Индекс security_events_created_at_idx (created_at), не уникальный.
- ROLES = ("app_api", "audit_reader"); _create_role_if_missing — как в 0018.
- PRIVILEGES (вид 0018, одна строка — одно право; GRANT только в цикле upgrade):
  - ("INSERT (event_type, pid, op_kind, client_op_id)", "TABLE security_events", "app_api")
  - ("USAGE", "SEQUENCE security_events_id_seq", "app_api")
  - ("SELECT", "TABLE security_events", "audit_reader")
- Не выдаётся никому: SELECT app_api, UPDATE, DELETE, TRUNCATE; ALTER DEFAULT PRIVILEGES и слово PUBLIC в коде не использовать [ШТАБ-тех].
- Без FOREIGN_PRIVILEGES. downgrade: drop_index, затем drop_table (права уходят с таблицей); роли не удаляются.
- Срок хранения и очистка: в A1 нет (GC отдельно, «Для ШТАБА») [ШТАБ-тех].
- Модель SecurityEvent: те же колонки, типы, nullable и индекс (compare_metadata сверяет индексы и типы; CHECK — для документа).
- Таблиц после миграции — 24.

## 9. Тесты
test_db_roles_0022.py (образец test_db_roles_0021.py; отказы — SQLSTATE 42501):
- test_revision_0022: revision и down_revision.
- test_privileges_static_0022: ROLES, PRIVILEGES == ожидаемый кортеж; "GRANT " в коде без docstring ровно 1; нет ALTER DEFAULT PRIVILEGES и PUBLIC.
- test_privileges_0022 (parametrize): app_api INSERT event_type/pid/op_kind/client_op_id = True; INSERT id и created_at = False; has_any_column_privilege SELECT и UPDATE = False; has_table_privilege DELETE и TRUNCATE = False; has_sequence_privilege USAGE = True; audit_reader SELECT = True, has_any_column_privilege INSERT = False; app_bot и app_projector — has_any_column_privilege SELECT/INSERT/UPDATE = False, DELETE = False; has_table_privilege('public', …, 'SELECT') = False.
- test_api_insert_contract_0022: под владельцем `SET LOCAL ROLE app_api` в транзакции → INSERT_SQL проходит; SELECT под app_api → 42501 (psycopg exc.orig.sqlstate).
- test_checks_0022 (parametrize, владелец): NULL и пустые event_type/op_kind/client_op_id, event_type 'other', client_op_id из 65 символов → IntegrityError.
- test_downgrade_0022 ПОСЛЕДНИМ: downgrade до "0021_bot_pauses_select" → to_regclass('security_events') IS NULL; в finally upgrade head.
test_security_events.py (БД — только CI):
- test_record_survives_outer_rollback: внешнее соединение начинает транзакцию, внутри вызывается record_security_event(engine, …), внешняя транзакция откатывается → строка с этим pid есть (count = 1).
- test_record_returns_true_and_row_fields: поля строки совпадают, created_at не NULL.
- test_record_failure_no_raise: engine на UNREACHABLE_DSN → False, без исключения; в caplog запись уровня ERROR "security_event_write_failed"; в caplog.text нет str(pid), op_kind, client_op_id.
- test_record_check_violation_returns_false: client_op_id из 65 символов → False, строки нет.
Изоляция: db_engine security_events не очищает — в каждом тесте новый pid uuid4 и фильтр по pid (как idempotency_keys).
Цели: bash tools/check.sh api. Только CI: всё с БД (REQUIRE_DB_TESTS=1).

## Задетые тесты (правило «Т»; git grep @afd898a по information_schema, has_table_privilege, has_column_privilege, pg_class, pg_tables, audit_reader, expected_tables)
- apps/api/tests/test_db_models.py:
  - добавить TABLES_0022 = ("security_events",);
  - test_expected_tables_count_after_0019 переименовать в test_expected_tables_count_after_0022: 23 → 24, первой строкой проверок assert set(TABLES_0022) <= _expected_tables();
  - test_upgrade_downgrade_upgrade_cycle: после первой проверки равенства (:97) первым шагом command.downgrade(cfg, "0021_bot_pauses_select"); assert _tables(migrated_db) == expected - set(TABLES_0022); затем expected = expected - set(TABLES_0022); дальше шаги как есть;
  - docstring: цикл начинается с «head → 0021 (без security_events) → 0018 …».
- test_models_match_live_schema — проходит при классе SecurityEvent в models.py.
- Не задеты: ролевые test_db_roles.py и test_db_roles_0007…0021 зовут has_*_privilege по таблицам из своих кортежей (security_events там нет). Сплошной перебор каталога потребовал бы information_schema.tables или pg_class по всем таблицам — таких мест нет: information_schema есть только в 0007:302 (колонки participant_events), pg_class — в 0019:413 (индекс life_writeoffs). audit_reader в тестах встречается 0 раз. test_downgrade_00xx проходят через downgrade 0022 — он должен быть чистым (раздел 8).
- conftest.py::db_engine не меняется (изоляция по pid, раздел 9).
Тест вне списка упал → не чинить, «тест X вне списка» в ИТОГ.

## Канон и решения
(а) И2 §idempotency_keys.behavior_on_collision; И4 §R339.conflict_ux; OVERRIDES.yaml §AD-01, §AD-02 (status closed — по старту ШТАБа и pause-api-a2 §1).
(б) Противоречий с DECISIONS.md нет: R-2026-11-21 задаёт носитель, канон его не определяет.
(в) —
(г) Правок канона нет.

## 10. Живые проверки (после мержа; выкат позже, по очереди SHTAB-DEBTS §1, после 0020 и 0021)
- Перед миграцией — бэкап before-0022 и DC --profile tools build migrate (норма STATE).
- После upgrade: alembic current = 0022_security_events; таблиц в public без alembic_version — 24; права \dp security_events: app_api — INSERT по 4 колонкам, audit_reader — SELECT.

## 11. Запреты
AGENT-BRIEF §3; не трогать pause.py, participant_lock.py и прочие миграции; не писать в privacy_audit_log; без новых зависимостей; без SELECT/RETURNING под app_api; в логах нет pid, op, initData, токенов, tg_user_id.

## 12. Критерии готовности
Файлы раздела 6; check api зелёный; CI api зелёный (24 таблицы, цикл, роли, модели); описание PR по AGENT-BRIEF §10.

## 13. Оценка
Часы Автора ≈ 0,5; кредиты 0 (КОДЕР).

## 14. РЕВЬЮЕР
Да — новые GRANT и роли (B-3): проверить PRIVILEGES, отсутствие SELECT у app_api и отказ записи без утечки данных в лог.
