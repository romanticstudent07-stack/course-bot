# B-3a — роли и GRANT БД (D-13): приложение и проектор не под владельцем

Заменяет docs/tasks/B-3.md (удалён в PR docs/tasks-1e-2b: B-3 разрезан на B-3a и B-3b, ответ Автора 4).

## 1. Паспорт
- id: B-3a · PR: «B-3a: роли app_api / app_projector и минимальные GRANT (миграция 0006)» · ветка: feat/b3a-db-roles
- Режим: Р0+ (одна ошибка дважды → Р1-П по стоп-правилу) · зависит от: projector-1, projector-2, projector-3.
- Миграция: revision 0006_app_roles, down_revision 0005_participant_events. Начинать после мержа projector-3.
  Таблиц не добавляет → expected_tables.txt не меняется.
- Первый файл пакета — docs/STATE.md (строки от ШТАБа).

## 2. Цель
Закрыть B-3: API ходит под ролью с минимальными правами, проектор — под своей; писать в participant_state
может только проектор; consent_events и participant_events для API — только добавление.

## 3. Решения Автора (дословно)
- «4А» — миграция создаёт роли NOLOGIN и GRANT; LOGIN-пользователей с паролями из .env создаёт серверный чат
  вручную по инструкции из карточки.
- STATE: «После B-3 каждая миграция с новой таблицей выдаёт GRANT ролям app_api / app_projector в той же миграции.»
- Загрузчик app.texts load берёт MIGRATIONS_DATABASE_URL, если задан (иначе DATABASE_URL).
- 4 (03.10): «B-3 → B-3a (роли/GRANT, миграция, РЕВЬЮЕР да) и B-3b (D-18, обработчик 500, тесты D-15 г).
  DEFECTS-FOUND.md убрать из чтения и правки КОДЕРА в обеих.»

## 4. Выдержки архитектуры
- errata-unified E1: «Запись разрешена только роли participant_state_projector, чтение — participant_state_reader».
- I2 read_only_enforcement: «must use reader role except in Б10 projector process»;
  «ci_check: application code cannot connect with projector role outside Б10».
- DEFECTS D-13: «отдельная роль приложения с минимальными GRANT (tg_user_registry: SELECT, INSERT;
  participant_state: только через reader/projector)».
- 0001_init: роли participant_state_projector (INSERT, UPDATE ON participant_state), participant_state_reader (SELECT);
  роли кластерные, создаются идемпотентным DO-блоком, downgrade их не удаляет.

## 5. ЧТО ПРОЧИТАТЬ (размеры по 18cf0ac)
docs/process/CODER.md 11,1 КБ; AGENT-BRIEF.md 11,2; docs/STATE.md 16,3; эта карточка ≈ 6;
apps/api/migrations/env.py 3,2; migrations/versions/…0001_init_init.py 9,6 (образец DO-блока ролей);
миграция 0005 (появится после projector-1 — размер впишет ШТАБ); apps/api/app/config.py 3,5;
apps/api/app/projector.py (после projector-2); apps/api/app/texts.py 10,2; apps/api/app/db/session.py 1,5;
.env.example 8,4; infra/docker-compose.dev.yml 7,5 (передача переменных в контейнеры);
infra/SERVER-IRONCLAD.md 8,1; apps/api/tests/conftest.py 5,7.
**Чтение КОДЕРА ≈ 102 КБ + 0005 + projector.py.**
Не читать: docs/DEFECTS-FOUND.md; tests/test_texts.py (не меняется); миграции 0002–0004 (имена — в разделе 8).

## 6. Файлы (8 + STATE)
Создать: apps/api/migrations/versions/<дата>-0006_app_roles_app_roles.py; apps/api/tests/test_db_roles.py.
Изменить: apps/api/migrations/env.py (MIGRATIONS_DATABASE_URL, если задан, иначе как сейчас);
apps/api/app/config.py (projector_database_url: str | None; migrations_database_url: str | None);
apps/api/app/projector.py (свой DSN, если задан);
apps/api/app/texts.py (load — MIGRATIONS_DATABASE_URL, если задан, иначе DATABASE_URL; чтение для участника — как было);
.env.example (MIGRATIONS_DATABASE_URL, PROJECTOR_DATABASE_URL — пустые, с комментарием);
infra/SERVER-IRONCLAD.md (раздел «Роли БД (B-3)»: инструкция раздела 10 без паролей + правило GRANT для
новых таблиц + строка «загрузчик текстов python -m app.texts load идёт под MIGRATIONS_DATABASE_URL (владелец)»).
docker-compose.dev.yml менять, только если без этого переменная не доходит до контейнера — записать в PR.
Отметку «B-3 закрыт» в DEFECTS-FOUND.md вносит Автор отдельной docs-задачей по строкам ШТАБа.

## 7. Контракт (переменные окружения)
- DATABASE_URL — API (после ручного шага — пользователь coursebot_api). Логика sqlalchemy_dsn прежняя.
- PROJECTOR_DATABASE_URL — проектор (coursebot_projector); не задан → DATABASE_URL (как до B-3).
- MIGRATIONS_DATABASE_URL — alembic и загрузчик `python -m app.texts load` под владельцем; не задан → DATABASE_URL.
  Преобразование DSN — то же, что sqlalchemy_dsn. Эндпоинты /texts читают под DATABASE_URL.
- Пока сервер не выполнил ручной шаг, всё работает по-старому (безопасный выкат).
- Правило на будущее (в docstring 0006 и в SERVER-IRONCLAD.md): каждая следующая миграция с новой таблицей
  выдаёт GRANT ролям app_api / app_projector в той же миграции; иначе API получит permission denied.

## 8. БД — миграция 0006_app_roles
- Роли NOLOGIN (DO-блок IF NOT EXISTS, как в 0001): app_api, app_projector.
- app_api: SELECT, INSERT ON tg_user_registry; SELECT ON text_registry; SELECT, INSERT ON consent_events;
  INSERT ON participant_events; USAGE ON SEQUENCE consent_events_id_seq, participant_events_id_seq;
  GRANT participant_state_reader TO app_api.
- app_projector: SELECT ON participant_events; SELECT, INSERT, UPDATE ON participant_state_checkpoints;
  GRANT participant_state_projector, participant_state_reader TO app_projector.
- short_no (identity): если CI покажет, что нужен USAGE на последовательность, — добавить и записать в PR.
- Имя последовательности или таблицы не сошлось с 0002–0005 → открыть только нужную миграцию, записать в PR.
- downgrade: REVOKE всё выданное и членство; роли НЕ удалять (кластерные, как в 0001).

## 9. Тесты (с БД — CI; соединение CI суперпользовательское → SET ROLE)
SET ROLE app_api: INSERT tg_user_registry — ок; INSERT/UPDATE participant_state — InsufficientPrivilege;
UPDATE/DELETE consent_events — отказ; INSERT text_registry — отказ; SELECT participant_state — ок.
SET ROLE app_projector: upsert participant_state — ок; INSERT tg_user_registry — отказ.
Сквозной: first-launch-транзакция под app_api и projector once под app_projector — зелёные.
downgrade до 0005 → у app_api нет прав на tg_user_registry.
Без БД (monkeypatch env, соединения нет): загрузчик при заданном MIGRATIONS_DATABASE_URL берёт его DSN,
при пустом — DATABASE_URL; проектор так же с PROJECTOR_DATABASE_URL. Цель check.sh: api.

## 10. Живые проверки и ручной шаг (СЕРВЕРНЫЙ; паролей в чат и в репо не писать)
0. До миграции (D-15 б): активных pid без give C0 или C1 = 0.
1. Бэкап pg_dump -Fc → upgrade head (0006) под владельцем.
2. psql под владельцем: CREATE ROLE coursebot_api LOGIN IN ROLE app_api; CREATE ROLE coursebot_projector LOGIN
   IN ROLE app_projector; пароли — \password coursebot_api и \password coursebot_projector (ввод скрыт).
3. .env на сервере: DATABASE_URL → coursebot_api, PROJECTOR_DATABASE_URL → coursebot_projector,
   MIGRATIONS_DATABASE_URL → владелец. Перезапуск api и projector.
4. psql под владельцем: SELECT usename, count(*) FROM pg_stat_activity WHERE datname = current_database() GROUP BY 1;
   ожидается coursebot_api и coursebot_projector.
5. psql под coursebot_api: INSERT в participant_state → permission denied.
6. exec api python -m app.texts load → «загружено 0, обновлено N, лишних в БД 0», без permission denied.
7. Все сервисы Up, healthy; logs api/projector без ERROR; Автор: живой first-launch проходит.

## 11. Запреты
AGENT-BRIEF §3. Плюс: паролей и LOGIN-ролей в миграции нет; .env не трогать (только .env.example);
существующие GRANT из 0001 не менять; эндпоинты /texts на MIGRATIONS_DATABASE_URL не переводить;
docs/DEFECTS-FOUND.md не читать и не править.

## 12. Готово, когда
CI 7/7; РЕВЬЮЕР без блокирующих замечаний; сервер 0–7. После — docs-задача Автора «B-3 закрыт»
(вместе с B-3b → все три блокера до VPS закрыты).

## 13. Оценка
Часы Автора 2–3 (ручной шаг на сервере); запросов КОДЕРА 2–3; кредиты 0 (Р0+).

## 14. РЕВЬЮЕР: да
Роли и GRANT БД (B-3); смена DSN у api, проектора и загрузчика текстов.
