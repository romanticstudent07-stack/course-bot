# db-pause-2 — миграция 0019_life_writeoffs: журнал списаний жизней (T1b)

## 1. Паспорт
- id: db-pause-2 · ветка: feat/db-pause-2 · режим: Р1 (Агент) · РЕВЬЮЕР: да (B-3, GRANT).
- Заголовок PR: «feat(db): 0019_life_writeoffs — журнал списаний жизней, права (db-pause-2)».
- Зависит от: db-pause-1. Начинать после мержа db-pause-1 (0018_pauses в main); миграции не параллелить.

## 2. Цель
Журнал списаний жизней: одна строка на событие списания life_ops (delta −1) с позицией дня. Пишет проектор при списании (T6a). Читает бот для revive_by_author (T7): возврат = списания после точки отката (02 §2.6). Код записи и чтения — в T6a и T7, здесь его нет.

## 3. Решения Автора (дословно, К-6: Автор; R-2026-11-15 §2, pause-2 §8)
- «А2. Из block_lives два выхода (C3): рестарт или revive_by_author. revive — одна транзакция (Р-C3.3): жизнь + откат на позицию, выбранную Автором (обычно день 1 текущего модуля); lives = min(3, 1 + возврат по 02 §2.6), больше 3 не бывает. … после 0019; по списаниям до 0019 — только +1.»
- Решения ШТАБа (К-5, Ш6): в журнал идут только списания life_ops (delta −1); /life −N не пишется; event_id — FK на participant_events(id), UNIQUE. Если канон revive окажется иным, правка будет в T7, схема 0019 не меняется.

## 4. Выдержки (архитектуру не читать)
- pause-2 §6: «0019_life_writeoffs: id, pid FK, event_id UNIQUE, stage_no, module_no, day_no, created_at; CHECK каждый номер IS NOT NULL AND >= 1. Пишет проектор при списании (T6a).»
- pause-2 §5: revive — «возврат = списания в 0019 после точки отката (02 §2.6) … Списания до 0019 → только +1».
- По коду 0007: позиция дня в participant_state — stage_no, module_no, day_no smallint, номера >= 1.

## 5. ЧТО ПРОЧИТАТЬ (≈ 42 КБ + AGENT-BRIEF 17,1 + карточка ≈ 7 → ≈ 66 КБ)
- apps/api/migrations/versions/2026_11_14_1200-0017_support_questions_support_questions.py 5,8 — образец.
- Миграция 0018_pauses из main (≈ 9, после db-pause-1) — down_revision и стиль.
- apps/api/tests/test_db_roles_0017.py 17,4 — образец теста. apps/api/tests/test_db_models.py 6,9. apps/api/tests/expected_tables.txt 1,2.

## 6. Файлы
- Создать: apps/api/migrations/versions/2026_11_17_1200-0019_life_writeoffs_life_writeoffs.py; apps/api/tests/test_db_roles_0019.py.
- Изменить: apps/api/tests/expected_tables.txt; apps/api/tests/test_db_models.py.
- Полный новый expected_tables.txt: всё из main после db-pause-1, в конец дописать
      # 0019_life_writeoffs
      life_writeoffs
  Таблиц после миграции — 23.

## 7. Контракт (SQL, ради которого выданы права; код — T6a, T7)
- app_projector (T6a), в транзакции события списания, после INSERT события:
      INSERT INTO life_writeoffs (pid, event_id, stage_no, module_no, day_no)
      VALUES (:pid, :event_id, :s, :m, :d) ON CONFLICT (event_id) DO NOTHING
  ON CONFLICT требует SELECT (event_id); DEFAULT nextval — USAGE последовательности.
- app_bot (T7), под замком участника:
      SELECT event_id, stage_no, module_no, day_no FROM life_writeoffs
      WHERE pid = :pid AND event_id > :after ORDER BY event_id
  :after — id последнего revive или рестарта (правило — карточка T7).

## 8. БД: миграция
- revision "0019_life_writeoffs", down_revision "0018_pauses". ROLES = ("app_bot", "app_projector"), через _create_role_if_missing.
- life_writeoffs: id bigint PK автоинкремент (life_writeoffs_pkey); pid uuid NOT NULL FK tg_user_registry.pid (life_writeoffs_pid_fkey); event_id bigint NOT NULL FK participant_events.id (life_writeoffs_event_id_fkey), UNIQUE (life_writeoffs_event_id_key); stage_no, module_no, day_no smallint NOT NULL; created_at timestamptz NOT NULL DEFAULT now().
- CHECKS (имя → условие буква в букву, У3):
  ck_life_writeoffs_stage_no → stage_no IS NOT NULL AND stage_no >= 1
  ck_life_writeoffs_module_no → module_no IS NOT NULL AND module_no >= 1
  ck_life_writeoffs_day_no → day_no IS NOT NULL AND day_no >= 1
- Индекс life_writeoffs_pid_event_idx (pid, event_id), не UNIQUE — для запроса T7.
- PRIVILEGES (одна строка — одно право):
  ("INSERT (pid, event_id, stage_no, module_no, day_no)", "TABLE life_writeoffs", "app_projector")
  ("SELECT (event_id)", "TABLE life_writeoffs", "app_projector")
  ("USAGE", "SEQUENCE life_writeoffs_id_seq", "app_projector")
  ("SELECT (pid, event_id, stage_no, module_no, day_no)", "TABLE life_writeoffs", "app_bot")
- app_api прав не получает. UPDATE, DELETE, TRUNCATE не выданы никому; ALTER DEFAULT PRIVILEGES и PUBLIC не используются; GRANT — одна строка кода в цикле.
- Бэкфилла нет: списания до 0019 в журнал не попадают (по ним revive даёт только +1, А2).
- downgrade: DROP INDEX, DROP TABLE (права уходят с таблицей; на чужих таблицах 0019 прав не выдаёт).
- Docstring: права и SQL раздела 7, как в 0017; «Таблиц после миграции — 23».

## 9. Тесты — apps/api/tests/test_db_roles_0019.py (tg_user_id 4401–4499)
1. Статика: revision и down_revision; ROLES; PRIVILEGES равен ожидаемому кортежу; dict(CHECKS) — строки раздела 8; нет UPDATE, DELETE, TRUNCATE; «ALTER DEFAULT PRIVILEGES» и «PUBLIC» нет; code.count("GRANT ") == 1.
2. Права: выданное True; False: app_projector SELECT stage_no и UPDATE; app_bot INSERT; app_api любые; DELETE и TRUNCATE у трёх ролей.
3. Контракт раздела 7: app_projector — вставка, повтор того же event_id → 0 строк, без ошибки; app_bot — выборка по pid и event_id > :after в порядке event_id. Событие для FK вставляет владелец в participant_events. Отказы через _assert_denied: app_bot INSERT, app_projector SELECT stage_no, app_api SELECT.
4. CHECK: stage_no, module_no, day_no = 0 → своё имя в diag; номера 1 проходят. NOT NULL по pid, event_id и трём номерам.
5. UNIQUE event_id (life_writeoffs_event_id_key); FK pid и event_id — неизвестный id → ForeignKeyViolation со своим именем; индекс (pid, event_id) не UNIQUE.
6. ПОСЛЕДНИМ test_downgrade_0019: downgrade до 0018_pauses → life_writeoffs нет, participant_pauses и pause_budgets на месте, право app_bot INSERT participant_events из 0018 True; в finally upgrade head.
- Цели: bash tools/check.sh api. С БД — только CI.

## 10. Задетые тесты (правило «Т»; ШТАБ сверяет до промпта, по main после db-pause-1)
- apps/api/tests/expected_tables.txt — +1 таблица (раздел 6).
- apps/api/tests/test_db_models.py — test_expected_tables_count_after_0018 переименовать в ..._after_0019: len == 23, добавить TABLES_0019 = ("life_writeoffs",); в test_upgrade_downgrade_upgrade_cycle первый шаг — downgrade 0018_pauses (по коду, Ш7).
- test_db_roles_0018.py, test_db_roles_0017.py, test_db_roles.py — правок нет: downgrade проходит через 0019 (DROP своей таблицы).
- Прочие тесты, где head — 0018, — не проверено, сверяет ШТАБ.

## 11. Живые проверки после мержа (Автор, сервер)
- Бэкап до миграции, команда — как для 0018.
- psql: SELECT version_num FROM alembic_version → 0019_life_writeoffs; SELECT count(*) FROM life_writeoffs → 0.

## 12. Запреты
AGENT-BRIEF раздел 3. Плюс: 0001–0018 не менять; кода проектора и бота нет (T6a, T7); бэкфилла нет; моделей не добавлять; ci.yml не трогать; прав сверх раздела 8 не выдавать.

## 13. Готово, когда
Миграция и тест по разделам 8–9; задетые файлы по разделу 10; tools/check.sh api зелёный; описание PR — права и SQL раздела 7, список отличий.

## 14. Оценка
Часы Автора: 0,3. Кредиты: ≈ 350 + 2 задетых файла × 60–100 → ≈ 480.

## 15. Канон и решения
(а) 02 §2.6 (возврат по откату — через pause-2 §5); 10-02 revive_by_author «с откатом позиции» (pause-2 §3). (б) Противоречий с DECISIONS.md нет: R-2026-11-15 А2 задаёт min(3, 1 + возврат) и «до 0019 — только +1»; схема это хранит. (г) Правок канона нет. Команда revive в реестре — правка DOCS в T7 (pause-2-check п.10).
