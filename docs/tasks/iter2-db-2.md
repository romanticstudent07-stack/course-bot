# iter2-db-2 — миграция 0008_day_marks: отметки блоков дня

## 1. Паспорт
- id: iter2-db-2 · область: API · режим: Р0+ (КОДЕР — бесплатный чат, пакет + tools/unpack.py).
- Заголовок PR: feat(db): 0008 — таблица day_marks и права (iter2-db-2)
- Ветка: iter2-db-2 · Зависит от: iter2-db-1. Начинать после мержа iter2-db-1; выкат — после выката 0007 на сервер.

## 2. Цель
Создать таблицу day_marks — отметки «Выполнил / Не выполнил» по блокам дня до отправки отчёта (В1 = Б, В6 = А).
Пишет app_api, читает app_projector («пришёл» и лестница напоминаний). Правило обнуления при перевыдаче дня
закрепить схемой, без DELETE. Код API и проектора в этой задаче не меняется.

## 3. Решения Автора (дословно)
- 16.10: «В2 — А (Europe/Moscow временно, поле пояса сразу); В3 — А (флаг только IRONCLAD, по умолчанию выкл., C0/C1 не пропускает, РЕВЬЮЕР); В5 — как предложено; В6 — А; В7 — да; В1 и В4 — после второго окна ИССЛЕДОВАНИЕ»
- 16.10: «В1 — Б (day_marks отдельно, позиция и жизни в participant_state); В4 — В («часы» в проекторе, доставка — бот с ролью app_bot); В8 — А (права прямо app_*, соответствие — комментарием и в DEFECTS)»
- 16.10 (карточки): «В9 — А (INSERT participant_events + USAGE participant_events_id_seq для app_projector — в 0007).» «В10 — А (day_started_at в ключе day_marks, DELETE ни у кого).»
- ШТАБ 16.10 снял Н2 по docs/architecture/normative/I2-wave-b.md@2be268c: «business_logic: must use reader role except in Б10 projector process».
  Следствие: participant_state пишет только app_projector; app_api его только читает.

## 4. Выдержки архитектуры (КОДЕР docs/architecture/** не читает)
- DM (по docs/research/iter2.md §1 и iter2-2.md §4): 3.3 — в дне 4–5 блоков, у каждого «Выполнил / Не выполнил»;
  отправка доступна, когда отмечены все блоки. 3.4 — три состояния: сдал / пришёл / полное молчание.
  3.7 — при перевыдаче дня отметки обнуляются. 3.9 — время берётся по серверу. 3.11 — галочки без отправки — черновик.
  3.17 — лестница: +1 ч после отметки, ~2 ч и ~30 мин до дедлайна.
- iter2-2.md §4 (вариант Б): day_marks (pid, день, block_id, value, at) пишет API сразу; первое нажатие дня дополнительно
  пишет событие day_first_mark — это делает будущая задача API, не эта.
- 0007 (iter2-db-1): participant_state.day_started_at — начало текущего дня; NULL — дня нет. Пишет только проектор.

## 5. ЧТО ПРОЧИТАТЬ (КОДЕР)
| Файл | КБ | Зачем |
|---|---|---|
| docs/process/CODER.md | 11,1 | правила окна |
| AGENT-BRIEF.md | 15,0 | факты и запреты |
| docs/STATE.md | 25,8 | состояние |
| docs/tasks/iter2-db-2.md (эта карточка) | ≈ 11 | задача |
| apps/api/tests/test_db_roles_0007.py (из iter2-db-1) | ≈ 9, уточнит ШТАБ после мержа | образец тестов и фикстур |
| apps/api/tests/expected_tables.txt | 0,8 | правишь целиком |
Чтение КОДЕРА ≈ 73 КБ. Файл миграции 0007 не давать: образец PRIVILEGES — выдержка в разделе 8.

## 6. Файлы
- Создать: apps/api/migrations/versions/2026_10_16_1300-0008_day_marks_day_marks.py
- Создать: apps/api/tests/test_db_roles_0008.py
- Изменить: apps/api/tests/expected_tables.txt — целиком: текст из iter2-db-1 (14 таблиц) плюс в конце
    # 0008_day_marks
    day_marks
  Итого 15 таблиц.
- Изменить: docs/STATE.md — только если ШТАБ дал строки (первым файлом пакета).

## 7. Контракт
Эндпоинтов нет. Правила для будущей задачи API отметок (iter2-api-2), их надо перенести в её карточку:
- day_started_at для отметки API берёт из participant_state текущего участника, а НЕ из тела запроса:
  клиент может прислать устаревший день.
- Чтение participant_state и запись отметки — в одной транзакции.
- day_started_at IS NULL → дня нет, отметку не писать (код ответа определит карточка API).
- Повторная отметка: INSERT ON CONFLICT (pid, day_started_at, block_id) DO UPDATE SET value = EXCLUDED.value, at = now().
  Время ставить явно, потому что DEFAULT срабатывает только при INSERT. Время — серверное (DM 3.9).
- Первое нажатие дня → событие day_first_mark — тоже в задаче API.

## 8. БД — миграция 0008_day_marks
revision = "0008_day_marks"; down_revision = "0007_day_state". Create Date: 2026-10-16 13:00:00. Шапка — как в 0006 и 0007.
    CREATE TABLE day_marks (
        pid            uuid NOT NULL,
        day_started_at timestamptz NOT NULL,
        block_id       text NOT NULL,
        value          boolean NOT NULL,
        at             timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT day_marks_pkey PRIMARY KEY (pid, day_started_at, block_id),
        CONSTRAINT day_marks_pid_fkey FOREIGN KEY (pid) REFERENCES tg_user_registry (pid),
        CONSTRAINT ck_day_marks_block_id_not_empty CHECK (block_id <> ''))
«День» отметки = day_started_at: метка конкретной выдачи дня. value = true — «Выполнил».
Отдельный индекс не нужен: первичный ключ начинается с pid. Последовательности нет — права USAGE не нужны.
Как обнуляются отметки при перевыдаче (DM 3.7, В10 = А): при перевыдаче проектор пишет новый participant_state.day_started_at.
Текущие отметки — это WHERE pid = :pid AND day_started_at = <текущее значение>. Старые строки остаются историей
и больше не попадают в выборку. Удалять ничего не нужно, права DELETE нет ни у кого.
Побочный плюс: отметка, записанная в момент перевыдачи со старым днём, просто станет невидимой — вреда нет.
PRIVILEGES — как в 0006 и 0007 (кортеж «право, объект, роль»; REVOKE в обратном порядке; колоночные права отзывать
отдельной строкой — табличный REVOKE их не снимает):
    ("SELECT, INSERT", "TABLE day_marks", "app_api"),
    ("UPDATE (value, at)", "TABLE day_marks", "app_api"),
    ("SELECT", "TABLE day_marks", "app_projector"),
Образец из 0006 (выдержка):
    for privilege, target, role in PRIVILEGES:
        op.execute(f"GRANT {privilege} ON {target} TO {role}")
    # downgrade:
    for privilege, target, role in reversed(PRIVILEGES):
        op.execute(f"REVOKE {privilege} ON {target} FROM {role}")
Обоснование для docstring:
- app_api INSERT — новая отметка. UPDATE только колонок value и at — участник может передумать
  (ON CONFLICT DO UPDATE требует UPDATE на колонки из SET). pid, day_started_at и block_id менять нельзя.
- app_api SELECT — нужен для ON CONFLICT DO UPDATE (чтение колонок конфликта и EXCLUDED), для RETURNING и для показа
  текущих отметок. Это право есть, отдельно добавлять ничего не нужно.
- app_projector SELECT — для «пришёл» (DM 3.4) и шага лестницы «+1 ч после отметки» (DM 3.17). Писать проектор не может.
- DELETE и TRUNCATE не получает никто (В10). FK проверяет владелец таблицы. В8: в каноне ролей day_marks нет, права выданы прямо app_*.
- FK без ON DELETE: стирание участника (erasure) позже должно учитывать day_marks — это задача erasure, не эта.
downgrade: REVOKE в обратном порядке (колоночное право — своей строкой), затем DROP TABLE IF EXISTS day_marks.

## 9. Тесты — apps/api/tests/test_db_roles_0008.py (только CI)
Фикстуры — как в test_db_roles_0007.py (копия api_engine, projector_engine, api_as_app_api). Из tests.test_db_roles импортировать
только role_engine, _assert_denied, _first_launch. db_engine чистит day_marks через TRUNCATE tg_user_registry CASCADE.
tg_user_id в тестах — 3301–3399.
1. app_api: first-launch → INSERT отметки (pid, фиксированный day_started_at, 'b1', true) → повтор через ON CONFLICT DO UPDATE
   SET value = EXCLUDED.value, at = now() с false → строка одна, value = false.
2. Перевыдача (В10): отметка с новым day_started_at — отдельная строка; выборка по новому дню до вставки пустая, старая строка цела.
3. app_projector: SELECT pid, block_id, value FROM day_marks — без ошибки, видит отметку из теста 1.
4. Запреты app_api (_assert_denied): UPDATE day_marks SET pid = gen_random_uuid(); UPDATE day_marks SET block_id = 'x';
   UPDATE day_marks SET day_started_at = now(); DELETE FROM day_marks; TRUNCATE day_marks.
5. Запреты app_projector: INSERT INTO day_marks (pid, day_started_at, block_id, value) VALUES (gen_random_uuid(), now(), 'b1', true);
   UPDATE day_marks SET value = true; DELETE FROM day_marks; TRUNCATE day_marks.
6. Ограничения (под db_engine): повтор INSERT без ON CONFLICT → UniqueViolation; неизвестный pid → ForeignKeyViolation;
   value NULL → NotNullViolation; at NULL → NotNullViolation; block_id '' → CheckViolation.
7. Права по колонкам: has_column_privilege('app_api','day_marks','value','UPDATE') и (…'at'…) — True;
   (…'pid'…), (…'block_id'…), (…'day_started_at'…) — False.
8. ПОСЛЕДНИМ — downgrade до "0007_day_state", в finally — command.upgrade(cfg, "head").
   to_regclass('public.day_marks') IS NOT NULL: до — True, после — False.
   Права 0007 целы и до, и после: has_table_privilege('app_api','idempotency_keys','INSERT') = True.
test_downgrade_revokes_privileges (до 0005) и downgrade-тест 0007 (до 0006) теперь проходят и через 0008:
их проверки day_marks не касаются, менять их не нужно. Упадут — стоп-правило, отдать ШТАБу.
Цель Codespaces: bash tools/check.sh api. Только CI проверит: тесты с БД и alembic upgrade/downgrade.

## 10. Сервер (отдельное задание ШТАБа после мержа и после выката 0007)
1. git pull main. 2. Бэкап: pg_dump -Fc с именем before-0008. 3. DC --profile tools build migrate (новый код миграции).
4. alembic upgrade head — только через DC run --rm migrate. 5. Ожидаем: alembic current = 0008_day_marks; таблиц 15;
   has_column_privilege('app_api','day_marks','pid','UPDATE') = false; 7/7 Up, 5 healthy; api и projector не пересобирать.
   Откат — downgrade до 0007_day_state, пока отметки никто не пишет (до iter2-api-2); после этого — только из бэкапа.

## 11. Запреты
- Не трогать: app/**, tests/conftest.py, tests/test_db_roles.py, test_db_roles_0007.py, миграции 0001–0007, ci.yml, docs/architecture/**.
- DELETE и TRUNCATE на day_marks не выдавать. Права сверх раздела 8 не выдавать. ALTER DEFAULT PRIVILEGES не использовать.
- Новых зависимостей нет. Запреты из AGENT-BRIEF.md, раздел 3. Стоп-правило — как в iter2-db-1.

## 12. Готовность
Миграция с down_revision "0007_day_state"; 3 строки PRIVILEGES (одна колоночная); docstring с обоснованием SELECT для ON CONFLICT
и правилом DM 3.7; expected_tables.txt — 15 таблиц; CI 7/7 зелёный; РЕВЬЮЕР — 0 блокирующих.

## 13. Оценка
Автор ≈ 0,8 ч + сервер 1 задание; кредиты 0 (Р0+).

## 14. РЕВЬЮЕР: да — роли и GRANT БД (B-3), колоночное право UPDATE у app_api.
