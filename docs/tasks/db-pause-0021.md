# T4-0 db-pause-0021 — SELECT строк паузы и INSERT (ttl) ключей для app_bot
Hash main c0c5288. Основа: docs/tasks/bot-pause-1.md §5 (SQL бота). Образец — миграция 0020 и apps/api/tests/test_db_roles_0020.py (docs/tasks/db-revive-0020.md). Правило К — docs/process/CANON-CHECK.md. Сначала прочитай docs/decisions/DECISIONS.md целиком.

## 1. Паспорт
- id: T4-0 db-pause-0021 · PR: «db-pause-0021: SELECT participant_pauses и INSERT (ttl) idempotency_keys для app_bot» · ветка: feat/bot-pause-1 (общая с bot-pause-1; миграция — первым коммитом, отдельным промптом).
- Режим: Р1 (Агент). Зависит от 0020_bot_events_select (в main). Схему пауз не меняет, поэтому может идти до api-pause-3. Промпт бота — только после api-pause-3 в main.

## 2. Цель
Боту (bot-pause-1) нужно видеть заявку паузы участника и её статус, чтобы:
- выложить карточку заявки Автору;
- перед решением проверить status = 'requested' AND now() < start_at (api-pause-1a §5);
- уведомлять участника о смене статуса.
Сейчас у app_bot прав на participant_pauses и pause_budgets нет (по коду: 0018; test_db_roles_0018 — DENIED_CHECKS_0018, test_bot_select_pauses_denied_0018). Миграция выдаёт два колоночных права и больше ничего. Таблицы не добавляются, apps/api/tests/expected_tables.txt не меняется.

## 3. Решения (К-6)
- Канал — права в 0021, не outbox; projector.py и outbox не трогаем [ШТАБ З2 Ш1, К-5].
- revision "0021_bot_pauses_select", down_revision "0020_bot_events_select"; файл apps/api/migrations/versions/2026_11_19_1200-0021_bot_pauses_select.py; ROLES = ("app_bot",) [ПРОЕКТИРОВЩИК-тех, образец 0020].
- INSERT (ttl) на idempotency_keys: ключи бота пишутся с ttl interval '30 days' вместо DEFAULT 1 ч из 0007 [ШТАБ З2 Ш3, К-5].
- SELECT (key) на idempotency_keys НЕ выдаётся: у app_bot уже есть SELECT (key, result_ref) (по коду: 0018 FOREIGN_PRIVILEGES; test_db_roles_0018 EXPECTED_FOREIGN_PRIVILEGES_0018). ШТАБ сверит по коду до промпта; если права нет — добавить строку ("SELECT (key)", "TABLE idempotency_keys", "app_bot").
- client_op_id, ended_at, stage_no, restart_no и вся pause_budgets боту не нужны и не выдаются [ПРОЕКТИРОВЩИК-тех, минимум прав].

## 4. Выдержки (по коду)
- 0018 participant_pauses: id bigserial (participant_pauses_id_seq), pid uuid FK tg_user_registry, kind IN ('user','author','shadow'), status IN ('requested','approved','active','ended','cancelled','rejected'), start_at, planned_end_at (> start_at; у user ≤ start_at + 169 h), ended_at, stage_no, restart_no, client_op_id (1..64), created_at.
- Права app_bot до 0021 (по коду 0018, 0020; docstring revive.py, card.py):
  - participant_events: INSERT (pid, kind, payload, actor, actor_role), SELECT (id, pid, kind); participant_events_id_seq USAGE;
  - idempotency_keys: INSERT (key, kind, result_ref), SELECT (key, result_ref);
  - tg_user_registry: SELECT (pid, tg_user_id, tombstoned_at, short_no);
  - participant_state: SELECT (…, tz) — точный список в docstring card.py.
- idempotency_keys.ttl — DEFAULT 1 ч (0007, по docstring revive.py). Если тип колонки не interval — стоп, вопрос ШТАБу.

## 5. Миграция
    PRIVILEGES: tuple[tuple[str, str, str], ...] = (
        ("SELECT (id, pid, kind, status, start_at, planned_end_at, created_at)",
         "TABLE participant_pauses", "app_bot"),
        ("INSERT (ttl)", "TABLE idempotency_keys", "app_bot"),
    )
- upgrade: один цикл по PRIVILEGES — op.execute(f"GRANT {privilege} ON {target} TO {role}").
- downgrade: reversed(PRIVILEGES) — REVOKE ровно того же.
- Docstring: зачем (bot-pause-1); что выдано; чего нет (запись в паузы, pause_budgets, client_op_id, ended_at, stage_no, restart_no, последовательность); фраза docstring 0018 «app_bot прав на participant_pauses не получает» для SELECT этих колонок больше не верна. 0018 не править.
- Нет ALTER DEFAULT PRIVILEGES, PUBLIC, USAGE на participant_pauses_id_seq.

## 6. Тест apps/api/tests/test_db_roles_0021.py (образец test_db_roles_0020)
1. Статика: revision, down_revision, ROLES, PRIVILEGES == EXPECTED. В коде без docstring нет «ALTER DEFAULT PRIVILEGES» и «PUBLIC»; «GRANT » встречается ровно 1 раз.
2. Права (has_column_privilege, has_any_column_privilege, has_table_privilege, has_sequence_privilege).
   - True: каждая выданная колонка.
   - False для app_bot:
     - participant_pauses: SELECT client_op_id, ended_at, stage_no, restart_no; INSERT и UPDATE (любая колонка); DELETE, TRUNCATE;
     - participant_pauses_id_seq: USAGE;
     - pause_budgets: SELECT, INSERT, UPDATE; DELETE, TRUNCATE;
     - idempotency_keys: UPDATE (любая колонка).
3. Контракт под app_bot: _bot_role_engine из test_db_roles_0009; строки вставляет владелец; tg_user_id 4401–4499. SQL — WATCH, DECIDE_ROW, DECIDE_CHECK, KEY_TTL из bot-pause-1 §5, в стиле :param. Проверить:
   - WATCH отдаёт заявку (start_at в будущем) с полями §5, open = True; строка kind 'author' не попадает;
   - DECIDE_CHECK = False, если start_at уже наступил (владелец вставляет start_at = now() − 1 h, planned_end_at = now() + 23 h);
   - KEY_TTL второй раз даёт rowcount 0; ttl строки, прочитанный владельцем, = interval '30 days'.
4. Отказы 42501 (_assert_denied): «SELECT client_op_id FROM participant_pauses», «SELECT pid FROM pause_budgets».
5. ПОСЛЕДНИМ — downgrade до 0020:
   - SELECT status на participant_pauses и INSERT ttl на idempotency_keys → False;
   - SELECT id на participant_events (0020) и INSERT key на idempotency_keys (0018) → True;
   - в finally — upgrade head.

## 7. Задетые тесты
- apps/api/tests/test_db_roles_0018.py (проверено чтением окна):
  - в DENIED_CHECKS_0018 генератор bot-{verb}-{table} пропускает только пару (participant_pauses, SELECT), остальные 5 случаев остаются False;
  - в test_bot_select_pauses_denied_0018 запрос меняется на «SELECT client_op_id FROM participant_pauses»;
  - остальное в файле не менять (test_downgrade_0018 проходит через 0021 без правок).
- Кандидаты, сверяет ШТАБ до промпта:
  - head "0020_bot_events_select" в test_migration_init.py или conftest.py — заменить на "0021_bot_pauses_select";
  - полные сверки прав app_bot в test_db_roles_0009, 0013, 0020 (INSERT ttl idempotency_keys → False; отсутствие SELECT на participant_pauses).
  Если что-то найдено, ШТАБ вписывает файл в §8 и в правку.

## 8. Чтение Агента (≈ 80 КБ из 140; размеры с «?» проставляет ШТАБ)
AGENT-BRIEF.md 17,1; docs/decisions/DECISIONS.md 7,7; эта карточка ≈ 10; docs/tasks/db-revive-0020.md 8,2; миграция 0020 ?; apps/api/tests/test_db_roles_0020.py ?; apps/api/tests/test_db_roles_0018.py ≈ 24 (оценка окна); кандидаты §7 — после подтверждения ШТАБом.

## 9. Запреты
Не трогать: миграции 0018–0020, projector.py, outbox, apps/bot, ci.yml, права app_api и app_projector. Без RETURNING.

## 10. Проверка
tools/check.sh api зелёный. CI не ждать (А-CI).

## 11. Стоп-условия
Тип ttl не interval; у app_bot нет SELECT (key) на idempotency_keys; кандидат §7 падает вне перечисленного. Во всех случаях — стоп и вопрос в ИТОГ.

## 12. Готово
Миграция и тест есть; правки test_db_roles_0018 по §7 сделаны; downgrade снимает ровно выданное.

## 13. Оценка
≈ 50 строк миграции + 160 строк теста → ≈ 200 кредитов; задетые 1–3 файла × 60–100. Часы Автора — в общем выкате.

## 14. РЕВЬЮЕР: да
Роли и GRANT БД (B-3).

## Канон и решения
(а) Канон в карточке не используется; права — по коду 0007, 0018, 0020.
(б) Противоречий с DECISIONS.md нет. Docstring 0018 расходится с api-pause-1a §5 (бот должен проверять статус) — 0021 это закрывает (кандидат DEFECTS — у ШТАБа).
(в)–(г) Правок канона нет.
