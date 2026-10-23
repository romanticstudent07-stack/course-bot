# db-access-1 — таблица access_grants (миграция 0010), права app_bot / app_api, backfill

Пачка Р-2 «доступ по промокоду», карточка (а) из 4: (а) → затем (б) bot-access-1 и (в1) api-access-1
параллельно → (в2) miniapp-access-1. Блокер прода. Код читать по hash main из docs/STATE.md.

## 1. Цель
Новая таблица access_grants хранит флажок доступа по tg_user_id и работает как ввод пароля: заявка,
отказы, пауза. В той же миграции — права ролям app_bot и app_api и «доступ выдан» текущим активным
участникам. Кода бота и API в этой задаче нет.

## 2. Решения (К-6)
- Схема Р-2: Start → промокод → админ-тема → «Выдать / Запретить» → онбординг [STATE Р-2; R-2026-10-1 Р-2].
- Флажок — в НОВОЙ таблице по tg_user_id; tg_user_registry не трогать [поправка ШТАБа 19.10].
- Колонки deny_count, locked_until; статусы pending / granted / denied [Автор 23.10, ответ 4; канон молчит].
- Кодовое слово в БД НЕ хранить [Автор 23.10, ответ 3; минимизация ПДн].
- Права: app_bot — SELECT, INSERT, UPDATE; app_api — только SELECT (tg_user_id, status) [ШТАБ 23.10].
- Backfill granted активным строкам tg_user_registry, created_via = backfill_0010 [ШТАБ 23.10].
- Тест одновременных решений на настоящей БД — здесь, а не в боте: в тестах бота Postgres нет [решил ШТАБ, К-5].
- Имя таблицы access_grants [решил ПРОЕКТИРОВЩИК, К-5: в db-tables-index её нет, см. раздел 11].

## 3. Ветка, коммит, PR
Ветка: feat/db-access-1. Коммит: «feat(db): 0010 access_grants + GRANT + backfill (db-access-1)».
PR: «db-access-1: таблица access_grants (0010), права app_bot/app_api, backfill». Мерж — ШТАБ.

## 4. Что прочитать (≈ 95 КБ)
AGENT-BRIEF.md 17,1 · docs/STATE.md 20,6 · эта карточка ≈ 9 · apps/api/app/db/models.py 11,2 ·
apps/api/migrations/versions/2026_10_17_1200-0009_app_bot_app_bot.py 5,1 (образец GRANT и ролей) ·
apps/api/tests/expected_tables.txt 0,9 · apps/api/tests/test_db_models.py 5,1 ·
apps/api/tests/test_db_roles_0009.py 13,8 (образец теста прав и переключения роли) · apps/api/tests/conftest.py 6,0 ·
docs/DEFECTS-FOUND.md (только последние 2 записи — образец формата).

## 5. Файлы
- новый apps/api/migrations/versions/2026_10_24_1200-0010_access_grants_access_grants.py
  (revision 0010_access_grants, down_revision 0009_app_bot; имя файла — по образцу 0009);
- apps/api/app/db/models.py — модель AccessGrant + константы;
- apps/api/tests/expected_tables.txt — «# 0010_access_grants» и «access_grants» (всего 16);
- apps/api/tests/test_db_models.py — 16 таблиц, TABLES_0010, первый шаг цикла — downgrade до 0009_app_bot;
- новый apps/api/tests/test_db_roles_0010.py;
- apps/api/tests/conftest.py — ТОЛЬКО если он чистит таблицы явным списком: добавить access_grants;
- docs/DEFECTS-FOUND.md — 3 записи (раздел 11); docs/STATE.md — строка (раздел 12).

## 6. Таблица access_grants (в миграции и в модели одинаково)
    tg_user_id        BIGINT PRIMARY KEY, CHECK (tg_user_id > 0)
    status            TEXT NOT NULL, CHECK (status IN ('pending','granted','denied'))
    deny_count        INTEGER NOT NULL DEFAULT 0, CHECK (deny_count >= 0)
    locked_until      TIMESTAMPTZ NULL          -- пауза после N-го отказа; NULL = паузы нет
    admin_message_id  BIGINT NULL               -- id сообщения ПОСЛЕДНЕЙ заявки в админ-теме
    requested_at      TIMESTAMPTZ NULL          -- время последней заявки
    decided_at        TIMESTAMPTZ NULL
    decided_by        BIGINT NULL               -- tg id админа, который решил
    created_via       TEXT NOT NULL, CHECK (created_via IN ('bot_promo','backfill_0010'))
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
    CHECK (status <> 'pending' OR admin_message_id IS NOT NULL)   -- ck_access_grants_pending_msg
    UNIQUE INDEX uq_access_grants_admin_message_id ON (admin_message_id) WHERE admin_message_id IS NOT NULL
Пояснения:
- denied = последнее решение «Запретить»; новые заявки разрешены, если нет паузы.
- admin_message_id после решения НЕ обнуляется: по нему /access_grant находит пользователя через reply
  на последнюю заявку (ответ 4е Автора — выдать можно в любой момент). Новая заявка его перезаписывает.
- Слова, имени, username в таблице нет.
- updated_at пишет код (триггера нет).
- Имена CHECK — по образцу 0008 и 0009 (ck_access_grants_*).

## 7. Права (в той же миграции, по образцу PRIVILEGES из 0009, по колонкам)
    GRANT SELECT (tg_user_id, status, deny_count, locked_until, admin_message_id, requested_at,
                  decided_at, decided_by) ON access_grants TO app_bot
    GRANT INSERT (tg_user_id, status, deny_count, locked_until, admin_message_id, requested_at,
                  created_via) ON access_grants TO app_bot
    GRANT UPDATE (status, deny_count, locked_until, admin_message_id, requested_at, decided_at,
                  decided_by, updated_at) ON access_grants TO app_bot
    GRANT SELECT (tg_user_id, status) ON access_grants TO app_api
- DELETE и TRUNCATE не выдаются никому; app_projector прав не получает.
- Роли — через _create_role_if_missing, как в 0009.
- В docstring миграции перечислить SQL, которому нужно каждое право (как в 0009); SQL — в разделах 8–9
  карточки bot-access-1:
  - SELECT … FOR UPDATE — нужен UPDATE хотя бы на одну колонку, он есть;
  - INSERT … ON CONFLICT (tg_user_id) DO UPDATE — нужны UPDATE на изменяемые колонки, они есть;
  - pg_advisory_xact_lock — прав на таблицу не требует.
- downgrade: DROP TABLE access_grants (права уходят вместе с ней).

## 8. Backfill (в upgrade, после CREATE и GRANT)
    INSERT INTO access_grants (tg_user_id, status, created_via, decided_at)
    SELECT tg_user_id, 'granted', 'backfill_0010', now() FROM tg_user_registry
    WHERE tombstoned_at IS NULL
    ON CONFLICT (tg_user_id) DO NOTHING
Оба тестовых участника на сервере получают «доступ выдан». Реальных ID в репо нет.

## 9. Модель
- Класс AccessGrant(Base), __tablename__ = "access_grants", колонки как в разделе 6.
- Константы: ACCESS_STATUS_PENDING / _GRANTED / _DENIED, ACCESS_STATUSES,
  ACCESS_CREATED_VIA_BOT_PROMO, ACCESS_CREATED_VIA_BACKFILL.
- Абзац в docstring модуля по образцу остальных: миграция 0010, Р-2, слово не хранится,
  app_api читает только (tg_user_id, status).
- Модель обязана пройти test_models_match_live_schema.

## 10. Тесты
test_db_models.py:
- test_expected_tables_count_after_0010 — 16 таблиц, access_grants есть;
- в цикле сначала downgrade «0009_app_bot» → expected − {"access_grants"}, дальше как было
  (из следующих шагов тоже вычесть TABLES_0010).

test_db_roles_0010.py (по образцу test_db_roles_0009.py; роль переключать тем же способом, что там):
- app_bot: INSERT; INSERT … ON CONFLICT (tg_user_id) DO UPDATE SET status, admin_message_id,
  requested_at, deny_count, locked_until, updated_at; SELECT … FOR UPDATE; UPDATE — проходят;
  DELETE → ошибка прав.
- app_api: SELECT tg_user_id, status — проходит; SELECT deny_count, INSERT, UPDATE → ошибка прав.
- app_projector: SELECT → ошибка прав.
- CHECK: status 'x' → ошибка; deny_count −1 → ошибка; pending без admin_message_id → ошибка;
  два ряда с одним admin_message_id → ошибка.
- backfill: на 0009 вставить 2 активные строки tg_user_registry и 1 tombstoned → upgrade head →
  granted ровно у двух активных, created_via = backfill_0010; строки tombstoned нет.
- ГОНКА (перенесено из bot-access-1, решил ШТАБ). Владельцем вставить строку status 'pending',
  admin_message_id 100, deny_count 0. Два отдельных соединения, оба под app_bot:
  - соединение 1: BEGIN; SELECT … WHERE tg_user_id = :id FOR UPDATE (держит строку);
  - соединение 2 в отдельном потоке: BEGIN; SELECT … FOR UPDATE; затем условный
        UPDATE access_grants SET deny_count = deny_count + 1, status = 'denied', updated_at = now()
        WHERE tg_user_id = :id AND status = 'pending' AND admin_message_id = 100
    и COMMIT; поток запоминает rowcount;
  - через ≈ 0,5 с проверить, что поток ещё не закончил (ждёт блокировку);
  - соединение 1: тот же условный UPDATE → rowcount 1; COMMIT;
  - дождаться потока (join с таймаутом 10 с): его rowcount = 0;
  - итог владельцем: deny_count = 1, status = 'denied'.
  На каждое соединение поставить lock_timeout 10 s, чтобы тест не зависал.
- Быстрые тесты: bash tools/check.sh api. Тесты с БД идут только в CI.

## 11. docs/DEFECTS-FOUND.md — 3 записи без номера («D-?», номер даст ШТАБ), формат как у последних
- D-? Канон не знает доступа по промокоду (Р-2): таблицы access_grants нет в build/db-tables-index.md,
  команд /access_grant и /access_deny нет в build/bot-commands-registry.yaml и 17/17-01. Правка DOCS.
- D-? Стирание (erasure, Б15) должно удалять и строку access_grants по tg_user_id; сейчас этого никто не делает.
- D-? К юристу: tg_user_id попадает в access_grants до согласия C1 (152-ФЗ) — заявка идёт раньше
  онбординга. Кодовое слово не хранится, видно только в сообщении админ-темы.

## 12. Строка STATE (внести в PR, раздел «Сейчас» или «Очередь» — как у прошлых задач)
- db-access-1 (Р-2, а): 0010_access_grants — 16 таблиц; права app_bot (SELECT/INSERT/UPDATE по колонкам)
  и app_api (SELECT tg_user_id, status); backfill granted активным участникам. Выкат — после 25.10.

## 13. Сервер, кредиты, CI
- Сервер (после 25.10, задание ШТАБа): migrate → alembic 0010_access_grants, 16 таблиц;
  SELECT status, created_via, count(*) FROM access_grants GROUP BY 1,2 → granted | backfill_0010 | 2.
- Оценка кредитов: 450–750.
- CI НЕ ЖДАТЬ: после push сразу ИТОГ и конец; gh run watch и опрос проверок запрещены.

## 14. РЕВЬЮЕР
Да (роли и GRANT БД). Проверить:
- app_api получил только SELECT (tg_user_id, status);
- DELETE нет ни у кого;
- тест гонки действительно проверяет ожидание блокировки.
