# T7b-0 db-revive-0020 — SELECT (id, pid, kind) на participant_events для app_bot
Hash main f87bc27. Основа: docs/tasks/bot-revive-1.md §7 (запрос :after); образец — миграция 0019 и apps/api/tests/test_db_roles_0019.py. Правило К — docs/process/CANON-CHECK.md. Сначала прочитай docs/decisions/DECISIONS.md целиком.

## 1. Паспорт
- id: T7b-0 db-revive-0020 · PR: «db-revive-0020: SELECT (id, pid, kind) participant_events для app_bot» · ветка: feat/bot-revive-1 (общая с bot-revive-1, миграция — первым коммитом)
- Режим: Р1 (Агент). Зависит от: 0019_life_writeoffs (в main). Один промпт с bot-revive-1, эта карточка — первой (PLAN §3 п.3).

## 2. Цель
Бот (bot-revive-1) считает точку отката :after — id последнего revive_by_author или restart_paid этого pid. Сейчас у app_bot на participant_events есть только INSERT (по коду: 0018, FOREIGN_PRIVILEGES; тест test_db_roles_0018 «bot-select-payload-events» → False). Миграция выдаёт колоночный SELECT (id, pid, kind) и больше ничего. Таблицы не добавляются.

## 3. Решения (метка К-6)
- ШТАБ 18.11 (З1-2): миграция 0020 нужна; revision "0020_bot_events_select", down_revision "0019_life_writeoffs"; колоночный GRANT, как в 0019; downgrade — REVOKE ровно того же [ШТАБ, К-5].
- ШТАБ 18.11: :after = coalesce(max(id), 0) по kind IN ('revive_by_author', 'restart_paid') этого pid [ШТАБ, канон 02 §2.4 и §2.6 — см. bot-revive-1].

## 4. Выдержки
- 0005 participant_events: id bigserial (последовательность participant_events_id_seq), pid uuid NOT NULL, kind text NOT NULL, payload jsonb NOT NULL, at DEFAULT now(), actor text NOT NULL, actor_role text NOT NULL (по bot-life-1 §4).
- Права app_bot на participant_events до 0020: INSERT (pid, kind, payload, actor, actor_role) и USAGE participant_events_id_seq (0018).
- Образец 0019: ROLES, PRIVILEGES — кортеж (право, объект, роль); _create_role_if_missing; GRANT выдаётся одним циклом; ALTER DEFAULT PRIVILEGES и PUBLIC не используются.

## 5. ЧТО ПРОЧИТАТЬ (Агент)
apps/api/migrations/versions/2026_11_17_1200-0019_life_writeoffs_life_writeoffs.py 5,8; apps/api/tests/test_db_roles_0019.py ≈14 (образец: _load_migration, _migration_code, bot_engine, тест downgrade последним). AGENT-BRIEF и DECISIONS — общие с bot-revive-1. Итого по этой карточке ≈ 20 КБ плюс карточка ≈ 6.

## 6. Файлы
- Создать: apps/api/migrations/versions/2026_11_18_1200-0020_bot_events_select_bot_events_select.py; apps/api/tests/test_db_roles_0020.py.
- Изменить: только файлы из «Задетых тестов», если ШТАБ их подтвердит.
- apps/api/tests/expected_tables.txt не меняется (таблиц по-прежнему 23).

## 7. Контракт: SQL, которому нужно право (пишется в docstring миграции)
    SELECT coalesce(max(id), 0) FROM participant_events
    WHERE pid = %s AND kind IN ('revive_by_author', 'restart_paid')
Запрос выполняет app_bot под замком participant:pid, в одной транзакции с SELECT life_writeoffs и INSERT revive_by_author (bot-revive-1 §7).

## 8. БД
- revision: "0020_bot_events_select"; down_revision: "0019_life_writeoffs".
- ROLES = ("app_bot",)
- PRIVILEGES = (("SELECT (id, pid, kind)", "TABLE participant_events", "app_bot"),)
- upgrade: _create_role_if_missing для каждой роли, затем цикл: GRANT {privilege} ON {target} TO {role}.
- downgrade: цикл по reversed(PRIVILEGES): REVOKE {privilege} ON {target} FROM {role}. Роли не удаляются. Права 0018 (INSERT, USAGE) не трогаются.
- payload, at, actor, actor_role для app_bot не открываются; app_api и app_projector не меняются.
- Docstring: зачем нужно (bot-revive-1, :after), SQL из §7, «права только колоночные; RETURNING в боте по-прежнему не используется»; «0001–0019 не меняются».

## 9. Тесты — apps/api/tests/test_db_roles_0020.py (tg_user_id 5001–5019)
1. Статика, без БД: revision и down_revision; ROLES == ("app_bot",); PRIVILEGES — ровно как в §8; в коде без docstring нет «ALTER DEFAULT PRIVILEGES» и «PUBLIC»; «GRANT » встречается 1 раз, «REVOKE » — 1 раз.
2. Права, CI: has_column_privilege('app_bot', 'participant_events', c, 'SELECT') → True для id, pid, kind и False для payload, at, actor, actor_role. has_table_privilege('app_bot', 'participant_events', 'SELECT') → False. Право INSERT 0018 сохранилось (has_any_column_privilege INSERT → True).
3. Контракт, CI: владелец вставляет у одного pid события restart_paid, life_op, revive_by_author, life_op, а у другого pid — revive_by_author. app_bot выполняет запрос §7 и получает id revive_by_author первого pid. У pid без таких событий запрос возвращает 0.
4. Отказ, CI: app_bot делает «SELECT payload FROM participant_events» → 42501 (_assert_denied).
5. ПОСЛЕДНИМ, CI: downgrade до 0019_life_writeoffs → SELECT id у app_bot False, INSERT 0018 True, life_writeoffs на месте; затем upgrade head; в finally — снова upgrade head.
Цели: bash tools/check.sh api. Только CI: пункты 2–5.

Задетые тесты (кандидаты; ШТАБ сверяет по коду до промпта):
- grep -rn "0019_life_writeoffs" apps/api/tests — тесты, которые сверяют head (test_migration_init.py, conftest.py): если там head == 0019, поставить "0020_bot_events_select".
- grep -rn "app_bot', 'participant_events'" apps/api/tests — проверки has_any_column_privilege(... 'SELECT') → False станут True (test_db_roles_0009/0013/0018). Проверку «bot-select-payload-events» в 0018 не трогать, она остаётся False.
- test_downgrade_0018 и test_downgrade_0019 проходят через downgrade 0020, правки не ожидаются.

## 10. Выкат (отдельный шаг общего выката, до бота)
- Г0: DC ps → 7/7 Up; alembic current → 0019_life_writeoffs; DC logs projector показывает «running (version 7)».
- Бэкап: pg_dump до миграции (как в выкатах 0018, 0019).
- alembic upgrade head → current 0020_bot_events_select.
- Проверка в psql: SELECT has_column_privilege('app_bot','participant_events','kind','SELECT'), has_column_privilege('app_bot','participant_events','payload','SELECT'); → t, f.

## 11. Запреты
AGENT-BRIEF §3. Не выдавать SELECT на payload, at, actor, actor_role; не давать табличный SELECT; не трогать 0001–0019, expected_tables.txt, права app_api и app_projector; без ALTER DEFAULT PRIVILEGES и PUBLIC.

## 12. Готово
Миграция и тест есть; check.sh api зелёный; downgrade снимает ровно выданное.

## 13. Оценка
≈ 50 строк миграции + 150 строк теста → ≈ 200 кредитов; задетые 0–2 файла × 60–100. Часы Автора — в общем выкате.

## 14. РЕВЬЮЕР: да
Задача трогает роли и GRANT БД (B-3).

## Канон и решения
(а) Канон в карточке не используется; права — по коду 0005, 0018, 0019.
(б) Противоречий с DECISIONS.md нет.
(в)–(г) Правок канона нет.
