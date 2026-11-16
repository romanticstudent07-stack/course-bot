# db-pause-1 — миграция 0018_pauses: паузы, бюджет пауз, права (T1)

## 1. Паспорт
- id: db-pause-1 · ветка: feat/db-pause-1 · режим: Р1 (Агент) · РЕВЬЮЕР: да (B-3, GRANT).
- Заголовок PR: «feat(db): 0018_pauses — participant_pauses, pause_budgets, права, бэкфилл (db-pause-1)».
- Зависит от: 0017_support_questions в main. Номера 0016 нет (решил ШТАБ, pause-2 §1). После этой задачи — db-pause-2 (0019).

## 2. Цель
Добавить две таблицы: participant_pauses (заявки и паузы участника) и pause_budgets (бюджет пауз на годовой цикл, I2 user_pause_quota). Выдать колоночные права app_api, app_projector, app_bot. Заполнить pause_budgets для участников, у которых уже есть день. Код пауз (события, проектор, API, бот) — в задачах T2–T5, здесь его нет.

## 3. Решения Автора (дословно, К-6: Автор; R-2026-11-15 §2, pause-2 §8)
- «А3. Паузы: одна на Этап, не дольше 7 дн.; поверх — не больше 14 дн. за годовой цикл; между паузами не меньше 24 ч. Цикл — с 00:00 первого дня задания по поясу (после рестарта — заново); бюджет снова 14 в годовщину, 00:00; 29.02 → 28.02. … Досрочный выход: дни назад в бюджет, пауза Этапа потрачена. Отменённая до старта (П.7) не считается. Пауза относится к Этапу, где началась. author_pause и тайная бюджет не тратят. Рестарт обнуляет оба лимита (C3 reset_pause_quota).»
- Решения ШТАБа (К-5): access_grants в 0018 не трогаем (pause-2-check п.1); app_projector — UPDATE (status, stage_no, restart_no, ended_at) (п.4); статус паузы пишет только проектор, бот и API пишут события (Ш2, Ш3); cycle_start_at — 00:00 по поясу в дату первой 04:00 первого дня (п.6); моделей в app/db/models.py нет (Ш7).

## 4. Выдержки (архитектуру не читать)
- I2 user_pause_quota (через pause-2 §2): «14 дн./год per cohort; (pid, days_budget_remaining_annual, cycle_start_at)»; client_op_id обязателен; семантики user / author / shadow.
- pause-2 §6: «Почему индекс, а не счётчик: … счётчик в pause_budgets пишет проектор, он может отстать — индекс по строке паузы защищает в самой БД (две вкладки). stage_no пишется при старте…; отменённая до старта в индекс не входит; досрочный выход = ended…; restart_no открывает паузу того же Этапа без удаления истории.»
- По коду day_clock.py: active_from — «первая 04:00 по поясу, которая ≥ started_at»; last_midnight — «последняя 00:00 по поясу, которая ≤ now»; zone — пустой или неизвестный пояс → Europe/Moscow.
- По коду test_projector_day_entered.py (сверил ШТАБ): day_started_at == participant_events.at события day_entered.

## 5. ЧТО ПРОЧИТАТЬ (≈ 64 КБ + AGENT-BRIEF 17,1 + карточка ≈ 11 → ≈ 92 КБ)
- apps/api/migrations/versions/2026_11_14_1200-0017_support_questions_support_questions.py 5,8 — образец целиком.
- apps/api/migrations/versions/2026_10_16_1200-0007_day_state_day_state.py 7,5 — idempotency_keys, participant_state.tz.
- apps/api/migrations/versions/2026_10_05_1200-0005_participant_events_participant_events.py 4,5 — колонки participant_events.
- apps/api/tests/test_db_roles_0017.py 17,4 — образец теста. apps/api/tests/test_db_roles.py 9,4 — role_engine, _assert_denied.
- apps/api/app/day_clock.py 11,2 — active_from, last_midnight. apps/api/tests/test_db_models.py 6,9. apps/api/tests/expected_tables.txt 1,1.

## 6. Файлы
- Создать: apps/api/migrations/versions/2026_11_16_1200-0018_pauses_pauses.py; apps/api/tests/test_db_roles_0018.py.
- Изменить: apps/api/tests/expected_tables.txt; apps/api/tests/test_db_models.py.
- Полный новый expected_tables.txt: шапка и все строки как есть, в конец дописать
      # 0018_pauses
      participant_pauses
      pause_budgets
  Таблиц после миграции — 22.

## 7. Контракт (SQL, ради которого выданы права; код — T2–T4)
- app_api (T3): запрос и чтение. Второй открытый запрос с другим op даёт UniqueViolation по participant_pauses_one_open_user_uq; T3 отвечает 409.
      INSERT INTO participant_pauses (pid, kind, status, start_at, planned_end_at, client_op_id)
      VALUES (:pid, 'user', 'requested', :start, :end, :op)
      ON CONFLICT (pid, client_op_id) DO NOTHING RETURNING id
      SELECT * FROM participant_pauses WHERE pid = :pid ORDER BY id DESC
      SELECT days_budget_remaining_annual, cycle_start_at, restart_no FROM pause_budgets WHERE pid = :pid
- app_projector (T2): смена статуса и бюджет.
      UPDATE participant_pauses SET status = 'active', stage_no = :s, restart_no = :r
      WHERE id = :id AND status = 'approved'
      INSERT INTO pause_budgets (pid, days_budget_remaining_annual, cycle_start_at, restart_no)
      VALUES (:pid, :d, :c, :r) ON CONFLICT (pid) DO UPDATE SET days_budget_remaining_annual = EXCLUDED.days_budget_remaining_annual,
      cycle_start_at = EXCLUDED.cycle_start_at, restart_no = EXCLUDED.restart_no
- app_bot (T4, T6b, T7): событие и ключ идемпотентности, без RETURNING.
      INSERT INTO idempotency_keys (key, kind, result_ref) VALUES (:key, :kind, :ref) ON CONFLICT (key) DO NOTHING
      SELECT result_ref FROM idempotency_keys WHERE key = :key
      INSERT INTO participant_events (pid, kind, payload, actor, actor_role) VALUES (:pid, :kind, :payload, :actor, :role)

## 8. БД: миграция
- revision "0018_pauses", down_revision "0017_support_questions". ROLES = ("app_api", "app_bot", "app_projector"), каждая через _create_role_if_missing, как в 0017.
- participant_pauses: id bigint PK автоинкремент (participant_pauses_pkey); pid uuid NOT NULL FK tg_user_registry.pid (participant_pauses_pid_fkey); kind text NOT NULL; status text NOT NULL; start_at timestamptz NOT NULL; planned_end_at timestamptz NOT NULL; ended_at timestamptz NULL; stage_no smallint NULL; restart_no smallint NULL; client_op_id text NOT NULL; created_at timestamptz NOT NULL DEFAULT now(). UNIQUE (pid, client_op_id) — participant_pauses_pid_client_op_id_key.
- CHECKS_PAUSES (имя → условие строкой буква в букву; У3 — NULL обработан явно):
  ck_participant_pauses_kind → kind IS NOT NULL AND kind IN ('user', 'author', 'shadow')
  ck_participant_pauses_status → status IS NOT NULL AND status IN ('requested', 'approved', 'active', 'ended', 'cancelled', 'rejected')
  ck_participant_pauses_period → start_at IS NOT NULL AND planned_end_at IS NOT NULL AND planned_end_at > start_at
  ck_participant_pauses_user_max → kind IS NOT NULL AND start_at IS NOT NULL AND planned_end_at IS NOT NULL AND (kind <> 'user' OR planned_end_at <= start_at + interval '169 hours')
  ck_participant_pauses_user_stage → kind IS NOT NULL AND status IS NOT NULL AND (kind <> 'user' OR status NOT IN ('active', 'ended') OR (stage_no IS NOT NULL AND restart_no IS NOT NULL))
  ck_participant_pauses_ended_at → status IS NOT NULL AND (status <> 'ended' OR ended_at IS NOT NULL)
  ck_participant_pauses_stage_no → stage_no IS NULL OR stage_no >= 1
  ck_participant_pauses_restart_no → restart_no IS NULL OR restart_no >= 0
  ck_participant_pauses_client_op_id → client_op_id IS NOT NULL AND char_length(client_op_id) BETWEEN 1 AND 64
- Почему 169 часов, а не 7 дней (решил ПРОЕКТИРОВЩИК): граница паузы — 00:00 местного пояса, при переводе часов 7 суток = 167–169 ч; «interval '7 days'» зависит от TimeZone сессии. Точные 7 местных суток проверяет код T2.
- Индексы (частичные UNIQUE): participant_pauses_one_active_uq (pid) WHERE status = 'active'; participant_pauses_one_open_user_uq (pid) WHERE kind = 'user' AND status IN ('requested', 'approved'); participant_pauses_stage_taken_uq (pid, stage_no, restart_no) WHERE kind = 'user' AND status IN ('active', 'ended').
- pause_budgets: pid uuid PK (pause_budgets_pkey) FK tg_user_registry.pid (pause_budgets_pid_fkey); days_budget_remaining_annual smallint NOT NULL; cycle_start_at timestamptz NOT NULL; restart_no smallint NOT NULL DEFAULT 0. Верхней границы бюджета нет — это конфиг потока.
- CHECKS_BUDGETS: ck_pause_budgets_days_remaining → days_budget_remaining_annual IS NOT NULL AND days_budget_remaining_annual >= 0; ck_pause_budgets_restart_no → restart_no IS NOT NULL AND restart_no >= 0.
- PRIVILEGES (права на новые таблицы; одна строка — одно право; PP — все 11 колонок participant_pauses по порядку выше; PB — pid, days_budget_remaining_annual, cycle_start_at, restart_no):
  ("INSERT (pid, kind, status, start_at, planned_end_at, client_op_id)", "TABLE participant_pauses", "app_api")
  ("SELECT (PP)", "TABLE participant_pauses", "app_api"); ("USAGE", "SEQUENCE participant_pauses_id_seq", "app_api")
  ("SELECT (PB)", "TABLE pause_budgets", "app_api")
  ("SELECT (PP)", "TABLE participant_pauses", "app_projector")
  ("UPDATE (status, stage_no, restart_no, ended_at)", "TABLE participant_pauses", "app_projector")
  ("SELECT (PB)", "TABLE pause_budgets", "app_projector"); ("INSERT (PB)", "TABLE pause_budgets", "app_projector")
  ("UPDATE (days_budget_remaining_annual, cycle_start_at, restart_no)", "TABLE pause_budgets", "app_projector")
- FOREIGN_PRIVILEGES (на таблицах прошлых миграций; ни в одной миграции их нет — сверил ШТАБ, Ш1):
  ("INSERT (pid, kind, payload, actor, actor_role)", "TABLE participant_events", "app_bot")
  ("USAGE", "SEQUENCE participant_events_id_seq", "app_bot")
  ("INSERT (key, kind, result_ref)", "TABLE idempotency_keys", "app_bot") — по 0007 NOT NULL без DEFAULT только key и kind
  ("SELECT (key, result_ref)", "TABLE idempotency_keys", "app_bot")
- GRANT — одна строка кода в цикле по (*PRIVILEGES, *FOREIGN_PRIVILEGES). Нельзя: app_api UPDATE на participant_pauses, app_bot — любые права на participant_pauses и pause_budgets, DELETE и TRUNCATE кому-либо, ALTER DEFAULT PRIVILEGES, PUBLIC.
- Бэкфилл (после GRANT), константа BACKFILL. Формула = day_clock.last_midnight(day_clock.active_from(at, tz), tz); пояс не из pg_timezone_names → Europe/Moscow, как zone:
      WITH first_day AS (SELECT DISTINCT ON (pe.pid) pe.pid, pe.at FROM participant_events pe
                         WHERE pe.kind = 'day_entered' ORDER BY pe.pid, pe.id),
      src AS (SELECT fd.pid, fd.at,
                     CASE WHEN EXISTS (SELECT 1 FROM pg_timezone_names n WHERE n.name = ps.tz)
                          THEN ps.tz ELSE 'Europe/Moscow' END AS tz
              FROM first_day fd JOIN participant_state ps ON ps.pid = fd.pid
              JOIN tg_user_registry r ON r.pid = fd.pid WHERE r.tombstoned_at IS NULL),
      act AS (SELECT pid, tz, CASE WHEN CAST(at AT TIME ZONE tz AS time) <= time '04:00'
                                   THEN CAST(at AT TIME ZONE tz AS date)
                                   ELSE CAST(at AT TIME ZONE tz AS date) + 1 END AS d FROM src)
      INSERT INTO pause_budgets (pid, days_budget_remaining_annual, cycle_start_at, restart_no)
      SELECT pid, 14, CAST(d AS timestamp) AT TIME ZONE tz, 0 FROM act ON CONFLICT (pid) DO NOTHING
  Нет day_entered → строки нет, её создаст проектор в T2 (pause-2-check п.7). В sleeping 0 участников (п.9), отдельной ветки нет.
- downgrade: REVOKE по reversed(FOREIGN_PRIVILEGES) — каждое право своей строкой, колоночные тоже (как в 0012); затем DROP трёх индексов, DROP TABLE pause_budgets, DROP TABLE participant_pauses. Права на новые таблицы уходят вместе с ними; роли не удаляются.
- Docstring миграции: права и SQL раздела 7, как в 0017; «Таблиц после миграции — 22».

## 9. Тесты — apps/api/tests/test_db_roles_0018.py (tg_user_id 4301–4399)
1. Статика без БД: revision и down_revision; ROLES; PRIVILEGES и FOREIGN_PRIVILEGES равны ожидаемым кортежам; dict(CHECKS_PAUSES) и dict(CHECKS_BUDGETS) — строки раздела 8; «ALTER DEFAULT PRIVILEGES» и «PUBLIC» нет в коде без docstring; code.count("GRANT ") == 1.
2. Права: has_column_privilege / has_any_column_privilege / has_sequence_privilege — выданное True; отказ False: app_api UPDATE на participant_pauses; app_bot на обеих новых таблицах; app_projector INSERT на participant_pauses; app_bot SELECT payload на participant_events; DELETE и TRUNCATE на новых таблицах у всех трёх ролей.
3. Контракт раздела 7 под ролями (role_engine, _bot_role_engine из test_db_roles_0009): app_api — INSERT с ON CONFLICT (повтор того же op → None), SELECT; app_projector — UPDATE approved → active и UPSERT бюджета; app_bot — ключ и событие. Отказы через _assert_denied: app_api UPDATE participant_pauses; app_bot SELECT participant_pauses; app_api INSERT pause_budgets.
4. CHECK (вставка владельцем, имя в diag.constraint_name): kind 'User'; status 'paused'; planned_end_at = start_at; user на 170 ч; user active без stage_no; ended без ended_at; stage_no 0; restart_no −1; op '' и 65 символов; бюджет −1; restart_no бюджета −1. Проходят: author на 170 ч; user requested без stage_no; user active со stage_no 1 и restart_no 0; user на 169 ч; op 64.
5. Индексы: второй active у pid; второй user requested или approved; второй user ended с тем же (stage_no, restart_no) → UniqueViolation с именем индекса. Проходят: requested + cancelled; ended со следующим restart_no; author active после user ended.
6. FK pid (participant_pauses_pid_fkey, pause_budgets_pid_fkey); NOT NULL по каждой NOT NULL колонке без DEFAULT.
7. Бэкфилл: данные владельцем при схеме 0017 (command.downgrade до 0017_support_questions → вставка → upgrade 0018_pauses → upgrade head). Случаи: Europe/Moscow, at 03:59 → 00:00 той же даты; 04:00 → та же дата; 04:01 → следующая дата; пояс 'Mars/Base' → по Москве; два day_entered → по меньшему id; tombstoned_at задан → строки нет; нет participant_state → строки нет; нет day_entered → строки нет. Для каждой созданной строки cycle_start_at == last_midnight(active_from(at, tz), tz) из day_clock; остаток 14, restart_no 0. Колонки participant_state для вставки — по 0001 (не проверено, достаточно ли pid).
8. ПОСЛЕДНИМ test_downgrade_0018: downgrade до 0017_support_questions → обеих таблиц нет; права app_bot на participant_events и idempotency_keys False; INSERT participant_events у app_projector (0007) True; support_questions на месте; в finally upgrade head.
- Цели: bash tools/check.sh api. С БД — только CI.

## 10. Задетые тесты (правило «Т»; ШТАБ сверяет до промпта)
- apps/api/tests/expected_tables.txt — +2 таблицы (раздел 6).
- apps/api/tests/test_db_models.py — test_expected_tables_count_after_0017 переименовать в test_expected_tables_count_after_0018: len == 22, добавить TABLES_0018 = ("participant_pauses", "pause_budgets"); в test_upgrade_downgrade_upgrade_cycle первый шаг — downgrade 0017_support_questions (сейчас 0015) (по коду, Ш7).
- test_db_roles.py и test_db_roles_0017.py — правок нет: их downgrade проходит через downgrade 0018 (REVOKE до DROP таблиц 0007 и 0005) — проверено.
- test_migration_init.py — правок нет: сверяет только 0001 с db-schema.sql — проверено.
- Прочие тесты, где head — 0017 или таблиц 20, — не проверено, сверяет ШТАБ.

## 11. Живые проверки после мержа (Автор, сервер)
- До миграции — бэкап БД, как в прошлых выкатах (STATE). Миграция — той же командой, что для 0017.
- psql: SELECT version_num FROM alembic_version → 0018_pauses.
- SELECT pid, days_budget_remaining_annual, cycle_start_at, restart_no FROM pause_budgets; — строк столько, сколько pid с day_entered без tombstone (по отчёту 15.11 ожидается А1 — не проверено); остаток 14, restart_no 0, cycle_start_at — 00:00 по Москве.
- SELECT count(*) FROM participant_pauses; → 0.

## 12. Запреты
AGENT-BRIEF раздел 3. Плюс: 0001–0017 не менять; access_grants, participant_state и status_flags не трогать; моделей не добавлять; ci.yml не трогать; кода пауз (projector, routers, bot) нет; прав сверх раздела 8 не выдавать. Permission denied в тесте контракта → права не расширять, вопрос ШТАБу в ИТОГЕ.

## 13. Готово, когда
Миграция и тест по разделам 8–9; expected_tables.txt и test_db_models.py по разделу 10; tools/check.sh api зелёный; описание PR — права и SQL раздела 7, список отличий от карточки.

## 14. Оценка
Часы Автора: 0,5 (PR, выкат, psql). Кредиты: ≈ 650 + 2 задетых файла × 60–100 → ≈ 780.

## 15. Канон и решения
(а) I2 user_pause_quota и user_pause (через pause-2 §2); 10-02 legality — запрет при block_lives проверяет код T2, не схема. (б) Противоречий с DECISIONS.md (Р-6а, Р-20 → R-2026-11-15 А3) нет: схема хранит «пауза Этапа» и бюджет 14. (г) Правок канона нет. DOCS-кандидаты pause-2 §7 относятся к T6a и T7.
