# pause-api-a3 — tombstone, замки часов, правило «Т»

Срез `4ea7fd79…`. Все пути — @4ea7fd7. A=apps/api; T=A/tests; M=A/migrations/versions; B=apps/bot/bot; P=docs/process; D=docs/decisions; R=docs/research. Аудит, ACL, GC, номер миграции и IndexedDB — вне окна (старт). Прошлое окно — R/pause-api-a.md@ad1f52b (DDL и права 0018, повторы request, источник pid, порядок замков POST, первая часть «Т»); здесь не перепроверялось.

## 1. tombstoned_at и стирание: кто пишет

[ШТАБ-тех; по коду: `git grep -n -e tombstoned_at -e erase -- apps`] В A/app и B нет ни одного SET/INSERT/DELETE по `tg_user_registry`: все совпадения — чтение (`WHERE … IS NULL`), объявление индекса и тесты.

| Писатель | файл:строка@4ea7fd7 | Замок participant:pid | Риск гонки с POST пауз |
|---|---|---|---|
| штатный писатель `tombstoned_at` в apps | не найден: 0 SET/values в A/app и B | — | нет данных, писателя нет |
| `INSERT tg_user_registry` (новый pid) | A/app/participants.py:69–82, uuid4 — :72 | нет: замок берётся позже, при повторном поиске | высокий: после tombstone тот же tg_user_id даёт новый pid |
| `SELECT … FOR UPDATE` по registry | A/app/participants.py:86–90 | нет (блокировка строки registry, не advisory) | низкий: только first-launch |
| позиционный индекс активной строки | A/app/participants.py:78, A/app/db/models.py:234 (`tombstoned_at IS NULL`) | — | — |
| `erased_at`, `erasure_blacklist`, `pending_erasure` | 0 совпадений в A/app и B (grep -e erased_at -e erasure_blacklist -e pending_erasure) | — | писателя нет |
| `DELETE FROM` | 0 совпадений в A/app и B | — | писателя нет |
| тесты ставят tombstone вручную | T/test_db_roles.py:38; T/test_day_current.py:196; T/test_consents.py:208; T/test_first_launch.py:585,648; T/test_day_marks.py:132; T/test_day_report_submit.py:287; T/test_day_test_enter.py:145; T/test_onboarding_form_db.py:205 | нет (владелец) | только тестовая среда |

Таблица `erasure_blacklist` существует с 0001 (T/expected_tables.txt:12), писателя в apps нет. Итог: ни tombstone, ни стирание в apps не пишутся — источник стирания «не установлено» (вероятно вне apps).

Писатели пауз: `INSERT INTO participant_pauses` — A/app/routers/pause.py:104, под замком (`active_pid_locked` :323) → да. `UPDATE participant_pauses` — A/app/projector.py:569, 578, 590, под своим ключом `participant_state_projector` (A/app/projector.py:253) → замка `participant:pid` нет. Бот паузы не пишет: 0021 даёт только колоночный SELECT (T/test_db_roles_0021.py:80–112, INSERT/UPDATE = False); свой ключ бота — `pause_decide` (B/pause.py:53,62,117), в TTL_BY_KIND его нет.

[ШТАБ-тех; по коду: A/app/day_keys.py:140–152, T/test_db_roles_0018.py:128] Ключ паузы — `pause_{start,end,cancel,resume}:{pid}:{pause_id}`, уникальность строки — `(pid, client_op_id)`. После tombstone и новой регистрации тот же client_op_id попадает в другой pid → другой ключ и вторая строка паузы. Маркера поколения нет (§2).

## 2. Замки часов против POST

| Шаг | A/app/pause_ops.py@4ea7fd7 | A/app/routers/pause.py@4ea7fd7 |
|---|---|---|
| таймаут | `SET LOCAL lock_timeout = '5s'` :321, LOCK_TIMEOUT :67 | своего lock_timeout нет (совпадений нет) |
| замок | `lock_participant` :322 — первый оператор транзакции | `active_pid_locked` :323 (request), :385 (cancel/resume) |
| до замка | ничего | `find_active_participant` — обычный SELECT (A/app/participant_lock.py:54, `_ACTIVE_SQL` :38–40) |
| после замка | перечитывает паузу и состояние, план :278–293 | проверяет, что pid активен :59–62, затем повтор op :333, открытая строка :338 |
| запись | ключ `ON CONFLICT DO NOTHING` :156–163, событие :165–170, один commit :297–327 | ключ + событие :395–407, `INSERT` паузы :104 |
| взаимное исключение | оба под `participant:pid` → POST и часы сериализуются | гонку с часами решает `_KEY_EXISTS_SQL` :395 (ключ `pause_start`/`pause_end`) |

Порядок замков одинаков: сначала advisory, строк registry `FOR UPDATE` нет (A/app/participant_lock.py:17). Отличие: API — `hashtext('participant:' || pid)` (participant_lock.py:34), бот — `hashtextextended('participant:' || %s, 0)` (B/life.py:32). Функции разные (int4 против int8), равенство ключей для одного pid не доказано → взаимное исключение бот↔API не установлено.

InitDataContext: A/app/telegram_init_data.py:80–93 — frozen dataclass `{user: TelegramUser, auth_date, query_id, start_param, chat_type, chat_instance}`; pid внутри НЕТ, только свойство `tg_user_id` → `self.user.id` (:91–93). Привязка к pid — заново в каждом запросе: `active_pid_locked(session, ctx.tg_user_id)` → `find_active_participant` (A/app/participants.py:50–62) → `SELECT pid WHERE tg_user_id = :u AND tombstoned_at IS NULL`. Поля initData (`auth_date`, `query_id`, `start_param`) поколение не кодируют; проверка `auth_date` — только свежесть (:198–202, Р-12).

## 3. Правило «Т»

| Тест | Что сверяет | Правка при новом kind / таблице / правах / полях POST |
|---|---|---|
| T/test_day_current.py::test_kinds_and_ttl (:78–100) | ПОЛНОЕ равенство `TTL_BY_KIND` — 13 видов | новый kind ключа → добавить строку, иначе падает |
| T/test_day_current.py::test_key_formats (:71) | day_enter / day_done / day_report | только при смене этих ключей |
| T/test_day_clock.py::test_day_close_and_queue_keys (:257) | TTL по именам | новый kind не трогает |
| T/test_clocks_1.py:79 | `TTL_BY_KIND["ladder_day2"]` | не трогает |
| T/test_notify_ladder.py:127 | TTL `ladder` + формат key_ladder | не трогает |
| T/test_notify_noon.py:95 | TTL `noon` | не трогает |
| T/test_notify_ops.py:95 | TTL `tasks_open` | не трогает |
| T/test_pause_api.py:66 | TTL `pause_cancel`/`pause_resume` | новый pause-вид ключа → дописать здесь |
| T/test_pause_api_db.py:109 | `TTL_BY_KIND[kind]` в помощнике | новый kind проходит сам |
| T/test_db_models.py::test_expected_tables_count_after_0019 (:79–91) | `len(_expected_tables()) == 23` + наборы | новая таблица → поднять число и добавить TABLES_00xx |
| T/test_db_models.py::test_upgrade_downgrade_upgrade_cycle (:94–156) | ЭТО и есть сверка expected_tables ЦЕЛИКОМ: `assert _tables(migrated_db) == expected` (:97) и (:156) | новая таблица → полный список T/expected_tables.txt |
| T/test_db_models.py::test_expected_tables_file_includes_0001 (:75) | подмножество таблиц 0001 | не трогает |
| T/test_db_models.py::test_models_match_live_schema (:159) | `compare_metadata` моделей и схемы | новая таблица/колонка → A/app/db/models.py |
| T/test_db_roles_0007.py::test_idempotency_keys_under_role (:231), ::test_idempotency_keys_constraints (:269) | INSERT/SELECT/повтор/ON CONFLICT; NOT NULL kind; ttl > 0 | новые поля idempotency_keys (напр. params_hash) → правка; новые kind — нет |
| T/test_db_roles_0021.py::test_privileges_static_0021 (:170) | `PRIVILEGES` = кортеж из 2, ровно один `GRANT ` | новые права бота → НОВАЯ миграция, 0021 не править |
| T/test_db_roles_0021.py::test_privileges_0021 (:188) + PRIVILEGE_CHECKS_0021 (:80–112) | колоночный SELECT и запреты app_bot на participant_pauses/pause_budgets | новое право или колонка → править кортеж |
| T/test_db_roles_0018.py::test_privileges_0018 (:368) + EXPECTED_PRIVILEGES_0018 (:55–79) | точный кортеж прав app_api/app_projector | новая колонка пауз → PP_COLUMNS/PB_COLUMNS и кортеж |
| T/test_db_roles_0018.py::test_api_contract_0018 (:375) | `INSERT … ON CONFLICT (pid, client_op_id)` (:128) | смена уникальности → правка |
| T/test_db_roles_0007.py::test_downgrade_0007 (:293), 0021::test_downgrade_0021 (:253), 0018::test_downgrade_0018 (:785) | downgrade снимает права своей миграции | миграция после 0021 их не трогает |
| T/conftest.py::db_engine (:111–136) | TRUNCATE 6 таблиц + `grant_access` | новая таблица без FK на registry → добавить в TRUNCATE |
| T/conftest.py::wait_for_lock_waiter (:184) | ожидание advisory-замка | готовый инструмент для теста замка |
| A/app/routers/day.py:437, 452 | `TTL_BY_KIND[kind]`; слова pause в файле нет | ключи пауз сюда не входят |

[T/test_db_roles_0007.py:6] `db_engine` НЕ чистит idempotency_keys — ключи в тестах уникальные (uuid4). Фикстуры для списка «задетых»: api_client, db_api_client, db_engine, migrated_db, grant_access, wait_for_lock_waiter (T/conftest.py:51–218).

## Блокеры

1. Писатель `tombstoned_at` и стирания в apps отсутствует (0 совпадений) — источник «не установлено».
2. Ключ замка: `hashtext` (API) против `hashtextextended` (бот) — взаимное исключение бот↔API не доказано.
3. `UPDATE participant_pauses` проектором (:569/578/590) идёт под `participant_state_projector`, не под `participant:pid`.
4. Ключи пауз содержат pid → после стирания тот же client_op_id даёт новую паузу; поля generation нет.

## Вопросы Автору

Нет. По К-4 вопрос не задаётся: канон о стирании и поколении pid в этом окне не читался (его нет в списке ШТАБа) — блокер вынесен в «Надо дочитать», а не в вопрос.

## Надо дочитать

1. Канон стирания: docs/architecture/ по `erasure_blacklist`, `tombstoned_at`, `pending_erasure` — кто пишет и под каким замком.
2. A/app/projector.py:540–600 (контекст трёх UPDATE пауз) — есть ли там `lock_participant`.
3. M/0001 (владелец `erasure_blacklist`) и права на неё — вместе с задачей аудита (окно a2).
4. B/pause_watch.py и B/pause.py:100–170 — полный контракт `pause_decide`.

## Прочитано

Целиком (Б = байты, wc -c):

| Путь | Б | Главный факт |
|---|---:|---|
| D/DECISIONS.md | 7809 | Приоритет решений; Р-6а, Р-12, Р-20. |
| P/DESIGNER.md | 21971 | Бюджет 200 КБ, правило Т, файл исследования. |
| P/PACK.md | 12747 | Метка конца есть; части, END, шаги. |
| P/CANON-CHECK.md | 4856 | К-4 требует строку «Канон: проверено». |
| R/pause-api-a.md@ad1f52b | 14271 | Прошлые выводы; п.3–4 не закрыты. |
| A/app/pause_ops.py | 17425 | Замок первым, SET LOCAL 5s, ключ+событие. |
| A/app/telegram_init_data.py | 10075 | В контексте нет pid и поколения. |
| A/app/participant_lock.py | 3300 | hashtext; FOR UPDATE запрещён. |
| A/app/participants.py | 4791 | Новый pid после tombstone, :72. |
| A/app/day_keys.py | 7759 | 13 видов ключей, TTL_BY_KIND. |
| A/app/day_report.py | 3396 | params_hash, reflection. |
| T/conftest.py | 8063 | Фикстуры, TRUNCATE, ожидание замка. |
| T/expected_tables.txt | 1171 | 23 таблицы, pause-0018, 0019. |
| T/test_db_models.py | 7735 | Сверка целиком — :97 и :156. |
| T/test_db_roles_0007.py | 12307 | Ключи и их права; db_engine не чистит. |
| T/test_db_roles_0021.py | 10748 | Бот паузы только читает. |

Выборки: T/test_db_roles_0018.py (4 фрагмента, ≈114 строк), A/app/routers/pause.py:310–345, 375–400, T/test_day_current.py:55–105, T/test_day_clock.py:255–275, T/test_notify_ladder.py:115–140, T/test_notify_noon.py:85–100, T/test_notify_ops.py:85–115 — ≈12 600 Б.

Целиком 148 424 Б; с выборками и выводом grep ≈ 170 000 Б из 200 000. Репозиторий не менялся, тесты и серверы не запускались.
