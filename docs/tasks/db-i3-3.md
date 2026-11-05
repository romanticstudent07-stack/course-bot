# db-i3-3 — миграция 0015_onboarding_form: анкета по Р-16

## 1. Паспорт
- id: db-i3-3 · ветка: db/i3-3-onboarding-form · режим: Р0+ (КОДЕР) · РЕВЬЮЕР: да (раздел 14).
- Заголовок PR: «db(0015): onboarding_form — пол и самочувствие по Р-16 (db-i3-3)».
- Зависит от: db-i3-2. Начинать после мержа задачи db-i3-2 (0014_measurements_log в main и на сервере).
- Дальше: api-2 (анкета) — после этой задачи.

## 2. Цель
Таблица onboarding_form (в db-tables-index имени для анкеты нет → onboarding_form, Ш-1): одна строка на участника — пол и код ответа «самочувствие». Часовой пояс сюда не входит (событие через проектор → participant_state.tz, задача api-2), вес — в measurements_log (0014). Таблиц станет 19.

## 3. Решения (метки К-6)
- Р-16 [Автор, DECISIONS]: «город → только tz (IANA), город не храним; пол; вопрос «самочувствие» (текст даст Автор); стартовые замеры — в таблицу Чек-Апа. ФИО, телефон, email не собираем, в черновике тоже.»
- А2 [Автор 05.11; канон 04 §4.4 — молчит]: пол — коды male / female, поле обязательное.
- Ш-1 [ШТАБ-тех, К-5]: вариант А — отдельная таблица анкеты (pid PK, gender, wellbeing_code, created_at).
- Ш-2 [ШТАБ-тех, К-5]: wellbeing_code text, CHECK ^[a-z0-9_]{1,32}$; тексты вариантов — заглушки, не в этой задаче.
- [ШТАБ, К-5]: tz из анкеты идёт событием через проектор (api-2), колонки в миграции нет.

## 4. Выдержки архитектуры
- 04 §4.1: «Шаг 4 — Анкета (ФИО, дата рождения, пол, телефон, часовой пояс, стартовые замеры, др. поля).» После Р-16 — пояс, пол, самочувствие, вес.
- 04 §4.4: «Пол → кнопки.» «Часовой пояс → кнопки-города.» «Самочувствие → кнопки-шкалы.»
- 04 §4.8: «Исходная анкета (ФИО, дата рождения, регион) НЕ спрашивается заново.» → одна строка на pid, без UPDATE.
- 06 §6.4: пола и самочувствия в карточке нет → app_bot прав не получает.
- 0001 (E1, INV-1): participant_state пишет только проектор → API не пишет tz напрямую.

## 5. ЧТО ПРОЧИТАТЬ (КОДЕР)
- Миграция 0011 (5,8 КБ) — образец; apps/api/app/db/models.py — 17,4; в apps/api/tests/: test_db_roles_0011.py — 14,1, test_db_roles.py — 9,4, test_db_models.py — 5,8, expected_tables.txt — 0,8.
- Миграция 0014 (db-i3-2, ≈ 6 КБ) — для down_revision; AGENT-BRIEF.md — 17,1. Чтение КОДЕРА ≈ 77 КБ + карточка.

## 6. Файлы
- Создать: apps/api/migrations/versions/2026_11_08_1200-0015_onboarding_form_onboarding_form.py.
- Изменить: apps/api/app/db/models.py (класс OnboardingForm, константы GENDERS = ("male", "female") и WELLBEING_CODE_PATTERN, абзац 0015 в докстринге).
- Изменить: apps/api/tests/expected_tables.txt — в конец «# 0015_onboarding_form» и «onboarding_form»; всего 19 = список 18 из db-i3-2 + onboarding_form.
- Создать: apps/api/tests/test_db_roles_0015.py. Изменить: apps/api/tests/test_db_models.py.

## 7. Контракт (SQL; код — api-2)
- INSERT INTO onboarding_form (pid, gender, wellbeing_code) VALUES (:pid, :gender, :wb) ON CONFLICT (pid) DO NOTHING RETURNING pid
- Повтор и чтение: SELECT gender, wellbeing_code, created_at FROM onboarding_form WHERE pid = :pid
- Список кодов самочувствия — в конфиге api-2 (заглушки); БД проверяет только формат.

## 8. БД: миграция 0015_onboarding_form
- revision = "0015_onboarding_form"; down_revision = "0014_measurements_log".
- onboarding_form: pid uuid PK (onboarding_form_pkey), FK → tg_user_registry.pid (onboarding_form_pid_fkey); gender text NOT NULL; wellbeing_code text NOT NULL; created_at timestamptz NOT NULL DEFAULT now(). updated_at нет; ФИО, телефона, email, города нет.
- CHECK: ck_onboarding_form_gender — gender IN ('male', 'female'); ck_onboarding_form_wellbeing_code — wellbeing_code ~ '^[a-z0-9_]{1,32}$'.
- Права (одна строка — одно право; роль создаётся, если её нет): app_api INSERT (pid, gender, wellbeing_code); app_api SELECT (pid, gender, wellbeing_code, created_at). Последовательности нет.
- app_bot и app_projector прав не получают; UPDATE, DELETE, TRUNCATE не получает никто; без ALTER DEFAULT PRIVILEGES и PUBLIC.
- downgrade: DROP TABLE (права уходят вместе с таблицей); права 0013 и 0014 остаются.
- models.py: OnboardingForm по схеме выше, те же имена CHECK; значения констант — те же, что в CHECK.

## 9. Тесты (apps/api/tests/test_db_roles_0015.py, образец test_db_roles_0011)
- Статика: revision и down_revision; в PRIVILEGES только app_api, нет UPDATE, DELETE, TRUNCATE; в коде нет ALTER DEFAULT PRIVILEGES и PUBLIC.
- SQL раздела 7 под app_api: INSERT ('male', 'ok') → pid; повтор с ('female', 'bad') → 0 строк, в таблице прежние 'male', 'ok'; SELECT читает строку.
- Отказы (42501): app_api — UPDATE onboarding_form SET gender = 'female', DELETE, TRUNCATE; app_bot — SELECT pid, SELECT gender, INSERT; app_projector — SELECT pid.
- Функции прав: has_any_column_privilege SELECT у app_bot и app_projector → false; UPDATE у app_api → false; has_column_privilege('app_api', 'onboarding_form', 'created_at', 'INSERT') → false; has_table_privilege('public', 'onboarding_form', 'SELECT') → false.
- CHECK (вставка владельцем): gender 'other', 'Male', '' → ck_onboarding_form_gender; wellbeing 'Bad', '', 'a-b', 33 символа 'x', кириллица → ck_onboarding_form_wellbeing_code; проходят 'ok', 'scale_3', 32 символа 'x'; NULL в gender или wellbeing_code → NotNullViolation; второй INSERT того же pid без ON CONFLICT → onboarding_form_pkey; чужой pid → onboarding_form_pid_fkey.
- ПОСЛЕДНИМ — downgrade до 0014_measurements_log: onboarding_form нет, measurements_log есть; в finally upgrade head.
- tg_user_id — 4001–4099 (grep -rn "40[0-9][0-9]" apps/api/tests — пересечений нет). tools/check.sh api — статика; тесты с БД — CI.

## Задетые тесты (правило «Т»)
- apps/api/tests/test_db_models.py::test_expected_tables_count_after_0014 (имя после db-i3-2) → переименовать в test_expected_tables_count_after_0015: len == 19; добавить TABLES_0015 = {"onboarding_form"} и assert TABLES_0015 <= _expected_tables().
- test_db_models.py::test_upgrade_downgrade_upgrade_cycle: новым первым шагом command.downgrade(cfg, "0014_measurements_log") и assert _tables == expected - TABLES_0015; затем expected = expected - TABLES_0015; дальше — шаг «0013» из db-i3-2 и как было. В докстринг дописать head → 0014.
- test_db_models.py::test_models_match_live_schema сверит OnboardingForm — правка нужна только в models.py.
- Downgrade-тесты test_db_roles*.py идут через downgrade 0015 — правки не нужны (downgrade чистый).

## 10. Живые проверки на сервере
- Бэкап before-0015 → alembic upgrade head → current = 0015_onboarding_form; в схеме public 19 таблиц.
- has_any_column_privilege('app_bot', 'onboarding_form', 'SELECT') → f; has_column_privilege('app_api', 'onboarding_form', 'gender', 'INSERT') → t.

## 11. Запреты
- AGENT-BRIEF §3 — целиком; ci.yml и чужие миграции не трогать; права только из раздела 8.
- Город, ФИО, телефон, email не хранить (Р-16); тексты вопросов — не здесь (api-2, заглушки).

## 12. Готово, когда
- 0015 в main; CI зелёный; РЕВЬЮЕР без блокеров; сервер: current = 0015_onboarding_form, 19 таблиц, проверки раздела 10 совпали.

## 13. Оценка
- Р0+ КОДЕР: кредитов 0, часы Автора ≈ 1. Маленькая таблица по образцу 0011 и 0014, один задетый файл; Агент ≈ 250 + 80 кредитов — неоправданно.

## 14. РЕВЬЮЕР: да
- GRANT БД и ПДн (пол, самочувствие = данные о здоровье): только app_api, без UPDATE; бот и проектор прав не получают.

## Канон и решения
- (а) Использует: 04 §4.1, §4.4, §4.8; 06 §6.4; db-tables-index (имени таблицы анкеты нет); 0001 (E1, INV-1).
- (б) Противоречат DECISIONS и ответам Автора: 04 §4.1 шаг 4 и §4.4 — ФИО, телефон, объёмы, город (Р-16, А1); варианты пола в каноне не указаны (А2).
- (в) Правка DOCS №11 (iter3-2 §4, текст обновлён по Р-16 и ответам 05.11), architecture/04-onboarding.md, врезка в шапку:
  найди: «> Коллизия нумерации C5 (Д-10) закрыта решением Р-3: «C5 = фото» убрано; C5 — только трансграничная передача (выключена), набор C0–C6 не меняется.»
  замени: эту же строку, затем пустая строка, затем новая строка:
  «> **Уточнено решением Автора Р-16 (04.11.2026) и ответами 05.11.** Анкета (Шаг 4, §4.4): часовой пояс — кнопки-города, хранится только IANA-пояс (participant_state.tz через проектор), название города не хранится; пол — male / female, обязательно; самочувствие — код ответа (формулировку даст Автор); стартовые замеры — только вес, в measurements_log вместе с Чек-Апом. ФИО, телефон, email и объёмы не собираются, в черновике тоже.»
- Правка №4 (miniapp-screens onb.form) — уточнить тем же составом; её делает карточка miniapp-1 (см. «Для ШТАБА»).
