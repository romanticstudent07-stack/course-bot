# iter2-db-3 — миграция 0009_app_bot: роль app_bot и права доставки из outbox

## 1. Паспорт
- id: iter2-db-3 · область: API/БД · режим: Р0+ (КОДЕР — бесплатный чат, пакет + tools/unpack.py).
- Заголовок PR: feat(db): 0009 — роль app_bot и права на outbox (iter2-db-3)
- Ветка: iter2-db-3 · Зависит от: iter2-db-2 (0008 смержена и на сервере, main = c5715b6).

## 2. Цель
Создать роль app_bot (NOLOGIN) и выдать МИНИМАЛЬНЫЕ права для доставки пушей из outbox (В4 = В):
«часы» в проекторе (app_projector) пишут событие и строку outbox одной транзакцией; бот (app_bot) берёт
строку, шлёт в Telegram, ставит sent_at; сбой → outbox_dlq. Код бота и проектора в этой задаче НЕ меняется.
Новых таблиц нет (их остаётся 15).

## 3. Решения Автора (дословно)
- 16.10: «В4 — В («часы» в проекторе, доставка — бот с ролью app_bot); В8 — А (права прямо app_*, соответствие — комментарием и в DEFECTS)»
- 17.10: «В11 — А (адресат: pid в aggregate_id → tg_user_registry, проверка tombstoned_at в момент отправки)»;
  «В12 — А (текст по text_id собирает бот; SELECT text_registry для app_bot)»;
  «В13 — А (после DLQ — sent_at = now() в той же транзакции; «обработано», не «доставлено» — комментарием и в DEFECTS)»;
  «В14 — А (INSERT outbox для app_projector — в 0009, этой карточкой)».
- Остальные В1–В10 — docs/research/iter2-2.md §1 и карточки iter2-db-1, iter2-db-2.

## 4. Выдержки (КОДЕР 0001 и docs/architecture/** не читает)
Таблицы из 0001_init (= docs/architecture/build/db-schema.sql):
    outbox (id bigserial PRIMARY KEY, aggregate_id text NOT NULL, event_type text NOT NULL,
            payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
            sent_at timestamptz,            -- NULL = не отправлено
            tx_id xid8 NOT NULL)            -- для reconciler
    индекс outbox_unsent_idx ON outbox (created_at) WHERE sent_at IS NULL
    outbox_dlq (id bigserial PRIMARY KEY, original_id bigint NOT NULL, payload jsonb NOT NULL,
                error text NOT NULL, moved_at timestamptz NOT NULL DEFAULT now(),
                replayed_at timestamptz, replayed_by text)
Последовательности: outbox_id_seq, outbox_dlq_id_seq. Роли канона в 0001: outbox_writer (INSERT outbox),
outbox_relay (SELECT, UPDATE outbox); прав на outbox_dlq и на последовательности канон не даёт никому.
tg_user_registry (0002–0006): pid uuid, short_no, tg_user_id, tombstoned_at, created_at, created_via.
PostgreSQL: SELECT … FOR UPDATE требует UPDATE хотя бы на одну колонку таблицы; UPDATE с WHERE требует
SELECT на колонки из WHERE; INSERT со списком колонок требует INSERT только на эти колонки, а DEFAULT nextval —
USAGE последовательности; RETURNING требует SELECT на возвращаемые колонки.

## 5. ЧТО ПРОЧИТАТЬ (КОДЕР)
| Файл | КБ | Зачем |
|---|---|---|
| docs/process/CODER.md | 11,1 | правила окна |
| AGENT-BRIEF.md | 15,0 | факты и запреты |
| docs/STATE.md | ≈ 29 | состояние |
| docs/tasks/iter2-db-3.md (эта карточка) | ≈ 13 | задача |
| apps/api/tests/test_db_roles_0008.py | ≈ 12 | образец тестов и фикстур («>=» и свой _alembic_config там НЕ повторять) |
Чтение КОДЕРА ≈ 80 КБ. По необходимости: миграция 0006 (≈ 5,6) — образец DO-блока уже выдержкой в разделе 8,
открывать только если выдержки не хватает. Файл 0001 не давать: колонки — в разделе 4.

## 6. Файлы
- Создать: apps/api/migrations/versions/2026_10_17_1200-0009_app_bot_app_bot.py
- Создать: apps/api/tests/test_db_roles_0009.py
- НЕ менять: apps/api/tests/test_db_models.py и apps/api/tests/expected_tables.txt — новых таблиц нет, их 15.
- Изменить: docs/STATE.md — только если ШТАБ дал строки (первым файлом пакета).

## 7. Контракт для будущих задач (перенести в их карточки)
iter2-api-3 («часы», app_projector):
- В одной транзакции с INSERT participant_events:
      INSERT INTO outbox (aggregate_id, event_type, payload, tx_id)
      VALUES (:pid_text, :event_type, CAST(:payload AS jsonb), pg_current_xact_id())
  aggregate_id = pid участника в каноническом виде uuid (str(uuid)). created_at и id — DEFAULT; sent_at не задавать.
- RETURNING не использовать; если понадобится — новое право отдельной миграцией. Читать outbox проектор не может.
iter2-send-1 (бот, app_bot):
- Забор: SELECT id, aggregate_id, event_type, payload FROM outbox WHERE sent_at IS NULL
  ORDER BY created_at LIMIT :n FOR UPDATE SKIP LOCKED.
- Адресат: SELECT tg_user_id FROM tg_user_registry WHERE pid = CAST(:aggregate_id AS uuid) AND tombstoned_at IS NULL.
  aggregate_id — text: перед SQL проверить формат uuid в Python. Ошибка CAST прерывает транзакцию с блокировкой.
  Не uuid → строка в DLQ, бот не падает. CHECK на формат в 0009 нет: outbox общий для типов событий канона.
- Текст: SELECT из text_registry по text_id из payload (В12 = А).
- Отправлено: UPDATE outbox SET sent_at = now() WHERE id = :id AND sent_at IS NULL.
- Сбой, одной транзакцией: INSERT INTO outbox_dlq (original_id, payload, error) VALUES (…) и тот же UPDATE sent_at.
  sent_at значит «обработано», а не «доставлено» (В13 = А); сбой видно по outbox_dlq.
- RETURNING не использовать; если понадобится — новое право отдельной миграцией.
- Вне задачи iter2-db-3: LOGIN-пользователь, пароль и DSN бота (iter2-send-1, infra). Драйвера БД в
  apps/bot/requirements.txt нет — это новая зависимость, нужно согласие Автора.

## 8. БД — миграция 0009_app_bot
Create Date: 2026-10-17 12:00:00. Шапка — как в 0006 и 0007 (docstring, затем ровно это; from __future__ НЕ писать):
    from collections.abc import Sequence
    from alembic import op
    revision: str = "0009_app_bot"
    down_revision: str | None = "0008_day_marks"
    branch_labels: str | Sequence[str] | None = None
    depends_on: str | Sequence[str] | None = None
ROLES = ("app_bot",). Функция _create_role_if_missing — копия из 0006 (не импорт):
    DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = '{role}')
    THEN CREATE ROLE {role}; END IF; END $$
PRIVILEGES (кортеж «право, объект, роль», как в 0006; одна строка — одно колоночное право):
    ("SELECT (id, aggregate_id, event_type, payload, created_at, sent_at)", "TABLE outbox", "app_bot"),
    ("UPDATE (sent_at)", "TABLE outbox", "app_bot"),
    ("INSERT (original_id, payload, error)", "TABLE outbox_dlq", "app_bot"),
    ("USAGE", "SEQUENCE outbox_dlq_id_seq", "app_bot"),
    ("SELECT (pid, tg_user_id, tombstoned_at)", "TABLE tg_user_registry", "app_bot"),
    ("SELECT", "TABLE text_registry", "app_bot"),
    ("INSERT (aggregate_id, event_type, payload, tx_id)", "TABLE outbox", "app_projector"),
    ("USAGE", "SEQUENCE outbox_id_seq", "app_projector"),
upgrade: создать роль, затем GRANT по списку. downgrade: REVOKE по reversed(PRIVILEGES) (колоночные — своей
строкой: табличный REVOKE их не снимает); роль НЕ удалять (кластерная, как в 0001 и 0006).
Docstring — права и SQL, который их требует:
- app_bot SELECT 6 колонок outbox + UPDATE (sent_at): забор пачки с FOR UPDATE SKIP LOCKED (FOR UPDATE требует
  UPDATE хотя бы на одну колонку) и отметка sent_at (WHERE по id и sent_at требует SELECT). tx_id не читает —
  колонка для reconciler. INSERT, DELETE, TRUNCATE на outbox нет. Компакция по sent_at (INV-3) — не бот.
- app_bot INSERT 3 колонок outbox_dlq + USAGE outbox_dlq_id_seq: перенос сбоя. SELECT и UPDATE на outbox_dlq
  нет (RETURNING не нужен; replayed_* — действие Автора позже).
- app_bot SELECT (pid, tg_user_id, tombstoned_at) tg_user_registry: адресат и проверка стирания при отправке (В11).
- app_bot SELECT text_registry: текст по text_id (В12); ПДн там нет.
- app_projector INSERT 4 колонок outbox + USAGE outbox_id_seq: «часы» пишут outbox вместе с событием (В14).
  sent_at писать не может; SELECT на outbox нет — RETURNING запрещён (раздел 7).
- В8 = А: права выданы прямо app_*. Соответствие канону: app_bot ≈ outbox_relay (уже по колонкам, плюс DLQ,
  tg_user_registry, text_registry); app_projector ≈ outbox_writer (плюс USAGE последовательности).
- В13 = А: после DLQ sent_at = now() — «обработано», не «доставлено».
- LOGIN, пароль, DSN бота — вне задачи (iter2-send-1, infra). ALTER DEFAULT PRIVILEGES не используется.

## 9. Тесты — apps/api/tests/test_db_roles_0009.py (только CI)
Импорт: from tests.conftest import _alembic_config; from tests.test_db_roles import _assert_denied, _first_launch, role_engine.
Свой _alembic_config не писать. Фикстуры bot_engine, projector_engine, api_engine — role_engine(migrated_db, роль), как в 0008.
Фикстура clean_outbox(db_engine): TRUNCATE outbox, outbox_dlq RESTART IDENTITY (conftest outbox не чистит; conftest не трогать).
Строку outbox вставляет projector_engine или db_engine, НИКОГДА не app_bot. tg_user_id — 3401–3499. Время — только «>».
1. rolcanlogin у app_bot = false (pg_roles).
2. app_projector: INSERT outbox (раздел 7, без RETURNING) — без ошибки; db_engine видит строку: sent_at IS NULL, tx_id не NULL.
3. SKIP LOCKED (две транзакции app_bot): одна строка; соединение 1 begin + забор пачки → 1 строка; соединение 2 begin +
   тот же SELECT → 0 строк. После rollback соединения 1 соединение 2 (новый begin) видит 1 строку.
4. sent_at: INSERT (транзакция A, проектор) и UPDATE sent_at (транзакция B, app_bot) — РАЗНЫЕ транзакции: now()
   внутри одной одинаковый. rowcount = 1; db_engine: sent_at > created_at. Повтор UPDATE → rowcount = 0.
5. DLQ: app_bot одной транзакцией INSERT outbox_dlq (original_id = id, payload, error) + UPDATE sent_at; db_engine: строка DLQ
   с original_id = id, replayed_at IS NULL; у outbox sent_at не NULL.
6. Адресат: _first_launch(db_api_client, 3401) → pid; app_bot SELECT tg_user_id … AND tombstoned_at IS NULL → 3401.
7. Не uuid: app_bot SELECT … CAST('not-a-uuid' AS uuid) → DataError (InvalidTextRepresentation), НЕ 42501.
8. app_bot: SELECT count(*) FROM text_registry > 0 (seed из db_engine).
9. Запреты app_bot (_assert_denied, 42501): SELECT * FROM outbox; SELECT tx_id FROM outbox;
   UPDATE outbox SET payload = '{}'::jsonb; INSERT INTO outbox (aggregate_id, event_type, payload, tx_id)
   VALUES ('x', 't', '{}'::jsonb, pg_current_xact_id()); DELETE FROM outbox; TRUNCATE outbox; SELECT * FROM outbox_dlq;
   UPDATE outbox_dlq SET replayed_at = now(); DELETE FROM outbox_dlq; INSERT INTO outbox_dlq (original_id, payload, error)
   VALUES (1, '{}'::jsonb, 'e') RETURNING id; SELECT * FROM tg_user_registry; SELECT pid FROM participant_state;
   SELECT id FROM participant_events; DELETE FROM text_registry.
10. Запреты app_projector: тот же INSERT outbox … RETURNING id; SELECT id FROM outbox; UPDATE outbox SET sent_at = now();
    DELETE FROM outbox; INSERT outbox со списком (aggregate_id, event_type, payload, tx_id, sent_at) и now();
    INSERT INTO outbox_dlq (original_id, payload, error) VALUES (1, '{}'::jsonb, 'e').
11. Запреты app_api: SELECT id FROM outbox; INSERT outbox (как в п. 9); SELECT id FROM outbox_dlq.
12. has_column_privilege (роль, таблица, колонка, право → ожидание): app_bot outbox sent_at UPDATE → true;
    app_bot outbox payload UPDATE → false; app_bot outbox tx_id SELECT → false; app_bot tg_user_registry tg_user_id SELECT → true;
    app_bot tg_user_registry short_no SELECT → false; app_bot outbox_dlq replayed_by INSERT → false;
    app_projector outbox tx_id INSERT → true; app_projector outbox sent_at INSERT → false.
13. ПОСЛЕДНИМ — downgrade до "0008_day_marks", в finally — command.upgrade(cfg, "head"). До — true, после — false:
    has_any_column_privilege('app_bot','outbox','SELECT'), ('app_bot','outbox_dlq','INSERT'), ('app_bot','tg_user_registry','SELECT'),
    ('app_projector','outbox','INSERT'); has_table_privilege('app_bot','text_registry','SELECT');
    has_sequence_privilege('app_bot','outbox_dlq_id_seq','USAGE'), ('app_projector','outbox_id_seq','USAGE').
    После: роль app_bot есть в pg_roles; целы права 0008 has_column_privilege('app_api','day_marks','value','UPDATE') и
    0007 has_table_privilege('app_api','idempotency_keys','INSERT').
Downgrade-тесты 0006–0008 проходят и через 0009: их проверки app_bot и outbox не касаются, менять их не нужно.
Цель Codespaces: bash tools/check.sh api. Только CI проверит тесты с БД и alembic upgrade/downgrade.

## 10. Сервер (отдельное задание ШТАБа после мержа)
1. git pull main. 2. Бэкап: pg_dump -Fc с именем before-0009. 3. DC --profile tools build migrate.
4. DC --profile tools run --rm --no-deps migrate (alembic upgrade head). 5. Ожидаем: alembic current = 0009_app_bot; таблиц 15;
   SELECT rolcanlogin FROM pg_roles WHERE rolname = 'app_bot' → f; has_column_privilege('app_bot','outbox','tx_id','SELECT') → f;
   7/7 Up, 5 healthy; api, projector, bot не пересобирать (код не менялся). Откат — downgrade до 0008_day_marks (роль остаётся).

## 11. Запреты
- Не трогать: app/**, apps/bot/**, tests/conftest.py, tests/test_db_roles*.py до 0008 включительно, test_db_models.py,
  expected_tables.txt, миграции 0001–0008, ci.yml, docs/architecture/**.
- Права сверх раздела 8 не выдавать. Не использовать: LOGIN, PASSWORD, DROP ROLE, ALTER DEFAULT PRIVILEGES,
  from __future__, RETURNING, CHECK на aggregate_id. Новых зависимостей нет. Запреты AGENT-BRIEF.md, раздел 3.
- Стоп-правило: permission denied на право вне раздела 8 или role_engine не принимает app_bot — права не расширять,
  ошибку отдать ШТАБу.

## 12. Готовность
Миграция с down_revision "0008_day_marks"; роль идемпотентно, NOLOGIN; 8 строк PRIVILEGES; docstring с SQL к каждому праву,
соответствием канону (В8) и смыслом sent_at (В13); тесты 1–13; число таблиц 15; CI 7/7 зелёный; РЕВЬЮЕР — 0 блокирующих.

## 13. Оценка
Автор ≈ 0,8 ч + сервер 1 задание; кредиты 0 (Р0+).

## 14. РЕВЬЮЕР: да — новая роль и GRANT БД (B-3), колоночные права app_bot и app_projector.
