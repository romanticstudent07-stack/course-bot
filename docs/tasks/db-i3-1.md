# db-i3-1 — миграция 0013_bot_card: права app_bot для /card и аудита

## 1. Паспорт
- id: db-i3-1 · ветка: db/i3-1-bot-card · режим: Р0+ (КОДЕР) · РЕВЬЮЕР: да (раздел 14).
- Заголовок PR: «db(0013): права app_bot — аудит /card и чтение карточки (db-i3-1)».
- Зависит от: db-2 (0012_outbox_api, уже в main). Начинать после мержа PR docs/tasks-i3-k1 и PR правок DOCS №10, №11 (раздел «Канон и решения»).
- Миграции по одной: db-i3-2 (0014) — только после мержа этой задачи и выката 0013 на сервер.

## 2. Цель
Бот сам читает БД для /card (Л6) и до отправки карточки пишет строку аудита в privacy_audit_log (06 fail-safe, 152-ФЗ). Миграция 0013 — только колоночные GRANT роли app_bot; таблиц, колонок, индексов не меняет, таблиц остаётся 17.

## 3. Решения (дословно, метки К-6)
- Р-16 (04.11) [Автор, DECISIONS]: «Делаем: город → только tz (IANA), город не храним; пол; вопрос «самочувствие» (текст даст Автор); стартовые замеры — в таблицу Чек-Апа. ФИО, телефон, email не собираем, в черновике тоже.»
- Р-15 (01.11) [Автор, DECISIONS]: «имя и username не берём».
- Л6 [ШТАБ, К-5]: бот читает БД сам; права — колоночные, как в 0012, только колонки карточки 06 §6.4 после Р-16 (без ФИО, телефона, email, возраста, @username).
- Ш-3 [ШТАБ-тех, К-5]: аудит без metadata — INSERT (actor_id, actor_role, action, participant_id) + USAGE последовательности.
- [ШТАБ-тех, К-5]: членства app_bot в participant_state_reader НЕТ (это SELECT на всю таблицу) — только колоночные GRANT.

## 4. Выдержки архитектуры
- 06 §6.1: «Карточка формируется свежей из БД в момент запроса (не хранится готовой).»
- 06 §6.4: «Кто: …, часовой пояс, кликабельная ссылка tg://user?id=, …, короткий №» (после Р-16 — только эти три); «Текущая позиция: Этап, модуль.день, статус»; «Жизни: осталось + журнал списаний»; «Дата регистрации».
- 06 fail-safe: «Аудит-лог доступа обязателен (кто, когда, чью карточку смотрел) — 152-ФЗ.» «Карточка мигрированного не падает при отсутствии данных (показывает «нет данных»).»
- 0001 (= build/db-schema.sql): privacy_audit_log (id bigserial, actor_id text NOT NULL, actor_role text NOT NULL, action text NOT NULL, participant_id uuid, occurred_at DEFAULT now(), metadata jsonb); SELECT — только audit_reader.
- 0001 + 0007 (проверено ШТАБом): participant_state — pid, lifecycle_phase, status_flags, author_pause_reason, updated_at, projector_version, last_seen_publish_epoch; 0007 добавила lives, stage_no, module_no, day_no, day_started_at, missed_streak, tz (text NOT NULL DEFAULT 'Europe/Moscow'). Права 0001 — на всю таблицу, колоночных нет.
- У app_bot на tg_user_registry уже есть: SELECT (pid, tg_user_id, tombstoned_at) — 0009; SELECT (short_no) — 0011.

## 5. ЧТО ПРОЧИТАТЬ (КОДЕР)
- apps/api/migrations/versions/2026_11_03_1200-0012_outbox_api_outbox_api.py — 3,0 КБ (образец: ROLES, PRIVILEGES, upgrade, downgrade).
- apps/api/migrations/versions/2026_10_17_1200-0009_app_bot_app_bot.py — 5,1 КБ (колоночные права app_bot).
- apps/api/tests/test_db_roles_0011.py — 14,1 КБ (образец теста); apps/api/tests/test_db_roles.py — 9,4 КБ (_assert_denied); apps/api/tests/test_db_roles_0009.py — 13,9 КБ (_bot_role_engine, BOT_DENIED_0009).
- AGENT-BRIEF.md — 17,1 КБ. Чтение КОДЕРА ≈ 63 КБ + карточка.

## 6. Файлы
- Создать: apps/api/migrations/versions/2026_11_06_1200-0013_bot_card_bot_card.py (дату в имени можно поставить фактическую).
- Создать: apps/api/tests/test_db_roles_0013.py.
- Изменить: apps/api/tests/test_db_roles_0009.py (раздел «Задетые тесты»).
- Не трогать: apps/api/tests/expected_tables.txt (таблиц 17), apps/api/app/db/models.py (participant_state не моделируется).

## 7. Контракт (SQL бота; код — bot-1, окно К5)
- Аудит ДО отправки карточки, без RETURNING:
  INSERT INTO privacy_audit_log (actor_id, actor_role, action, participant_id) VALUES (:actor_tg_id_text, 'owner', 'view', :pid)
- По #NNNNNN: SELECT pid, tg_user_id, created_at FROM tg_user_registry WHERE short_no = :n AND tombstoned_at IS NULL
- По reply или кнопке: SELECT pid, short_no, created_at FROM tg_user_registry WHERE tg_user_id = :tg AND tombstoned_at IS NULL
- Состояние: SELECT lifecycle_phase, status_flags, stage_no, module_no, day_no, lives, tz FROM participant_state WHERE pid = :pid
- Нет строки participant_state → «нет данных» (06 fail-safe, Л5). Вес и зона Чек-Апа — права в 0014 (db-i3-2).

## 8. БД: миграция 0013_bot_card
- revision = "0013_bot_card"; down_revision = "0012_outbox_api" (файл 2026_11_03_1200-0012_outbox_api_outbox_api.py).
- ROLES = ("app_bot",); роль создаётся, если её нет (как в 0012).
- PRIVILEGES (одна строка — одно право, роль везде app_bot):
  1) INSERT (actor_id, actor_role, action, participant_id) — TABLE privacy_audit_log;
  2) USAGE — SEQUENCE privacy_audit_log_id_seq (DEFAULT nextval требует USAGE);
  3) SELECT (created_at) — TABLE tg_user_registry (дата регистрации);
  4) SELECT (pid, lifecycle_phase, status_flags, stage_no, module_no, day_no, lives, tz) — TABLE participant_state.
- НЕ выдаются app_bot: SELECT на privacy_audit_log (RETURNING запрещён), INSERT (id, occurred_at, metadata), UPDATE, DELETE, TRUNCATE; на participant_state — author_pause_reason, updated_at, projector_version, last_seen_publish_epoch, day_started_at, missed_streak и любая запись; tg_user_registry.created_via.
- Без ALTER DEFAULT PRIVILEGES, без PUBLIC, без GRANT роли participant_state_reader.
- downgrade: REVOKE каждого права из PRIVILEGES в обратном порядке, своей строкой (табличный REVOKE колоночное право не снимает). Права 0009 и 0011 остаются; роль не удаляется.
- Докстринг — как в 0012: каждое право и SQL раздела 7, который его требует.

## 9. Тесты (apps/api/tests/test_db_roles_0013.py, образец test_db_roles_0011)
- Статика: revision и down_revision; все PRIVILEGES — роль app_bot; права на TABLE только колоночные «(…)», USAGE — только на SEQUENCE; в коде (без докстринга) нет ALTER DEFAULT PRIVILEGES, PUBLIC, participant_state_reader.
- SQL раздела 7 под app_bot: INSERT аудита проходит, владелец видит строку (occurred_at не NULL, metadata NULL); SELECT tg_user_registry по short_no и по tg_user_id; SELECT participant_state по случайному pid — 0 строк без ошибки (строку participant_state тест не создаёт).
- Отказы app_bot (42501): SELECT * FROM participant_state; SELECT missed_streak FROM participant_state; SELECT author_pause_reason FROM participant_state; UPDATE participant_state SET tz = 'UTC'; SELECT id FROM privacy_audit_log; INSERT аудита с RETURNING id; INSERT с metadata; UPDATE privacy_audit_log SET action = 'x'; DELETE FROM privacy_audit_log; SELECT created_via FROM tg_user_registry; SELECT * FROM tg_user_registry.
- Функции прав: has_column_privilege по каждой выданной колонке → true; has_any_column_privilege('app_bot', 'privacy_audit_log', 'SELECT') → false; has_table_privilege DELETE и TRUNCATE на privacy_audit_log и participant_state → false; pg_has_role('app_bot', 'participant_state_reader', 'MEMBER') → false; has_sequence_privilege USAGE → true.
- ПОСЛЕДНИМ — downgrade до 0012_outbox_api: все 4 права 0013 → false; SELECT (tg_user_id) и (short_no) у app_bot → true; в finally upgrade head.
- tg_user_id тестов — 3801–3899; перед коммитом grep -rn "38[0-9][0-9]" apps/api/tests — пересечений нет.
- tools/check.sh api — статика; тесты с БД — только CI.

## Задетые тесты (правило «Т»)
- apps/api/tests/test_db_roles_0009.py, BOT_DENIED_0009: строку «SELECT pid FROM participant_state» заменить на «SELECT * FROM participant_state» (app_bot получает не все колонки — отказ остаётся) и добавить строку «SELECT missed_streak FROM participant_state». Строка «SELECT * FROM tg_user_registry» остаётся отказом (created_via не выдан).
- Downgrade-тесты test_db_roles.py, test_db_roles_0009/0010/0011/0012.py, test_db_models.py идут через downgrade 0013 — он обязан быть чистым (раздел 8); правки не нужны.
- test_db_roles_0010.py и test_db_roles_0012.py не задеты (проверено ШТАБом); expected_tables.txt не меняется.

## 10. Живые проверки на сервере (СЕРВЕРНЫЙ, по заданию ШТАБа)
- Бэкап before-0013 → alembic upgrade head → alembic current = 0013_bot_card.
- Владельцем: SELECT has_column_privilege('app_bot', 'participant_state', 'tz', 'SELECT'), has_column_privilege('app_bot', 'participant_state', 'missed_streak', 'SELECT'), has_table_privilege('app_bot', 'privacy_audit_log', 'SELECT') → t, f, f.
- Бот не перезапускается (код /card — bot-1).

## 11. Запреты
- AGENT-BRIEF §3 — целиком; ci.yml и чужие миграции не трогать.
- Права вне раздела 8 не выдавать; permission denied в тестах на право вне раздела 8 — права не расширять, вопрос ШТАБу.
- Реальных ID и ПДн в тестах нет; тексты — заглушки.

## 12. Готово, когда
- 0013 в main; CI зелёный (7 проверок); РЕВЬЮЕР без блокеров; сервер: current = 0013_bot_card, проверки раздела 10 совпали.

## 13. Оценка
- Р0+ КОДЕР: кредитов 0, часы Автора ≈ 1. Почему не Агент: 4 GRANT по образцу 0012, один задетый файл с точной правкой, тест по образцу 0011; Агент ≈ 250 + 80 кредитов без выигрыша.

## 14. РЕВЬЮЕР: да
- Роли и GRANT БД (B-3), ПДн: ровно 4 права раздела 8; нет SELECT на privacy_audit_log; нет членства в participant_state_reader; downgrade снимает каждое право отдельно.

## Канон и решения
- (а) Использует: 06 §6.1, §6.4, fail-safe; build/db-schema.sql (privacy_audit_log); build/db-tables-index.md (privacy_audit_log, participant_state).
- (б) Противоречит DECISIONS: 06 §6.4 «Кто» и YAML who — ФИО, возраст, регион, @username, телефон (Р-16, Р-15; @username — Автор 04.11, Л3).
- (в) Правка DOCS №10 (iter3-2 §4), architecture/06-participant-card.md:
  найди: «- **Кто:** ФИО, возраст, откуда (регион), часовой пояс, кликабельная ссылка tg://user?id=, @username, телефон, короткий №.»
  замени: «- **Кто:** часовой пояс, кликабельная ссылка tg://user?id=, короткий № (ФИО, возраст, регион, @username, телефон не собираются — Р-16, Р-15).»
  найди: «    - who: [name, age, region, timezone, "tg://user?id=", username, phone, short_no]»
  замени: «    - who: [timezone, "tg://user?id=", short_no]   # Р-16, Р-15»
- (в) Правка DOCS №11 (врезка в 04, текст по Р-16 и ответам Автора 05.11) — общая для db-i3-1…3, полный текст в db-i3-3.
- Правка №9 (@username в 06 §6.2) нужна bot-1, к этой миграции не относится.
