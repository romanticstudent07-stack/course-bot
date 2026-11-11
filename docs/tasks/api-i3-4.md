# api-i3-4 — API: статус Чек-Апа (GET /checkup/status) и 409 CHECKUP_EXISTS

## 1. Паспорт
- id: api-i3-4 · PR: «feat(api): статус Чек-Апа и 409 CHECKUP_EXISTS (api-i3-4)» · ветка: feat/api-i3-4-checkup-status
- Режим: Агент Р1 · РЕВЬЮЕР: нет (§15) · Зависит от: ничего; миграции нет (§8).
- Основа: docs/research/miniapp-i3-1.md §4 и §10; потребитель — docs/tasks/miniapp-i3-1b.md §7.1 и §7.3. «Как сейчас» — по коду @7547732.
- Оценка: 320 кредитов (§14). Тесты сверх §9 не добавлять. Упал тест вне §11 — не чинить: «тест X вне списка» в ИТОГ и стоп.

## 2. Цель
- Новый GET /miniapp/v1/checkup/status → 200 {completed, created_at}: пройден ли Чек-Ап онбординга. Признак даёт сервер (Р-18).
- POST /miniapp/v1/checkup/submit: новый X-Client-Op-Id, когда Чек-Ап онбординга уже есть → 409 CHECKUP_EXISTS.
- Повтор с тем же op_id остаётся как сейчас: 200 с сохранёнными zone, config_version, created_at.

## 3. Решения Автора (дословно)
- Р-18, пункт 1А (DECISIONS.md; research §2): «Признак „Чек-Ап пройден“ даёт сервер.» [К-6: Автор, канон 04 §4.9 проверен]
- Пункт 2А (там же): «Ответы Чек-Апа — только в памяти экрана; закрыл приложение → с вопроса 1.» Частичного прогресса на сервере нет: только «пройден / не пройден». [К-6: Автор]
- Р-16 (DECISIONS.md): «ФИО, телефон, email не собираем, в черновике тоже.» В ответе status — только признак и дата. [К-6: Автор]

## 4. Выдержки (КОДЕР архитектуру и другие карточки не читает)
- docs/tasks/miniapp-i3-1b.md §7.1: ответ GET /checkup/status — {completed, created_at}; §7.3: «409 CHECKUP_EXISTS → дальше» (клиент молча идёт на следующий шаг). Эту карточку не менять.
- 04 §4.9 (цитата по miniapp-i3-1b §3): «Прогресс онбординга сохраняется в БД»; 05 §5.5 (цитата по миграции 0014): Чек-Ап — 15 ответов 0–3, балл, зона, версия конфига, строки append-only (04 §4.8). Признак берётся из measurements_log, не от клиента.

## 5. ЧТО ПРОЧИТАТЬ (точный список, больше ничего не открывать)
- AGENT-BRIEF.md 17,1 КБ · эта карточка.
- apps/api/app/routers/checkup.py 11,2 КБ — правится.
- apps/api/app/routers/onboarding_form.py 16,5 КБ — образец GET /onboarding/form.
- apps/api/tests/test_checkup_submit_db.py 9,1 КБ — правится; apps/api/tests/test_onboarding_form_db.py 9,9 КБ — образец теста 12 «GET-статус».
- apps/api/tests/conftest.py 8,1 КБ — фикстуры db_api_client, db_engine, grant_access, valid_init_data.
- Чтение КОДЕРА ≈ 72 КБ + карточка.

## 6. Файлы
- Изменить: apps/api/app/routers/checkup.py; apps/api/tests/test_checkup_submit_db.py.
- Создать: apps/api/tests/test_checkup_status_db.py.
- Таблиц не добавляем и не удаляем → apps/api/tests/expected_tables.txt не трогать.

## 7. Контракт
GET /miniapp/v1/checkup/status — initData обязательна, параметров и тела нет, только чтение:
- 200 {completed: bool, created_at: date-time | null}; других полей нет — балла, зоны и ответов не отдавать.
- Признак: строка measurements_log с pid участника, kind = 'checkup' AND occasion = 'onboarding'.
- Фильтр по kind обязателен: строки kind = 'body' (вес из анкеты, occasion тоже 'onboarding') в признак НЕ входят. [ШТАБ-тех 3]
- Чек-Апы после Этапа (occasion = 'stage_end', 05 §5.1) не считаются; POST submit их и так не принимает (Literal["onboarding"]). [ШТАБ-тех 3]
- created_at — самая ранняя такая строка: SELECT created_at … ORDER BY created_at LIMIT 1. Строк нет → {completed: false, created_at: null}. [ШТАБ-тех 5]
- Нет активного участника → 404 PARTICIPANT_NOT_FOUND.
- Согласия здесь НЕ проверяются: 409 RECONSENT_REQUIRED маршрут не отдаёт — ровно как GET /onboarding/form (по коду: там только find_active_participant, без consent_status).
- Замок participant_lock не берётся (только чтение, как GET /onboarding/form).
- SQLAlchemyError → rollback, 503 SERVICE_UNAVAILABLE, в лог — имя класса.
- Лог app.checkup, INFO: «checkup/status: tg_user_id=%s status=ok» и «… status=404». Ни pid, ни op_id, ни зоны, ни балла.
- responses маршрута: 404 PARTICIPANT_NOT_FOUND; 503 SERVICE_UNAVAILABLE (ошибка БД).

POST /miniapp/v1/checkup/submit — один новый шаг. Порядок в submit_checkup:
1) active_pid_locked: нет → 404 PARTICIPANT_NOT_FOUND (как сейчас);
2) C0 и C1: нет текста → 503 SERVICE_MISCONFIGURED; причины reconsent → 409 RECONSENT_REQUIRED (как сейчас);
3) строка measurements_log с этим op_id: kind = 'checkup' → 200 с сохранёнными значениями (повтор, как сейчас); kind другой → 409 IDEMPOTENCY_CONFLICT;
4) НОВОЕ: у pid уже есть строка kind = 'checkup' AND occasion = 'onboarding' → 409 CHECKUP_EXISTS, тело только {code, message}, message «Чек-Ап уже пройден.»; created_at в теле 409 не отдавать; [ШТАБ-тех 1, 2]
5) INSERT measurements_log … ON CONFLICT (pid, client_op_id) DO NOTHING RETURNING (как сейчас);
6) commit → 200 {zone, config_version, created_at}; балла в ответе нет никогда.
- Шаг 4 идёт в той же транзакции под замком, взятым на шаге 1 (две одновременные отправки не дадут двух Чек-Апов); приоритет: тот же op_id (шаг 3) проверяется РАНЬШЕ CHECKUP_EXISTS, повтор одной отправки остаётся 200.
- Своей ветки лога для 409 не добавлять: нынешний except HTTPException уже пишет «status=409», как для RECONSENT_REQUIRED. [ШТАБ-тех 4]
- В маршруте обновить responses 409: «RECONSENT_REQUIRED / CHECKUP_EXISTS / IDEMPOTENCY_CONFLICT».
- Обновить докстринг модуля checkup.py: новая нумерация шагов 1–6 и строка про GET /checkup/status. [ШТАБ-тех 6]

## 8. БД: миграции нет
- По 0014 (2026_11_07_1200-0014_measurements_log_measurements_log.py) у measurements_log единственная уникальность — UNIQUE (pid, client_op_id) (measurements_log_pid_client_op_id_key); индекс (pid, kind, created_at) неуникальный. Уникальности (pid, occasion) нет.
- Новых ограничений и индексов не добавляем: от второго Чек-Апа защищает проверка под замком (§7, шаг 4); миграции, GRANT и expected_tables.txt не трогаются. Права есть: 0014 дал app_api SELECT по measurements_log (в т. ч. occasion и created_at).

## 9. Тесты (ровно этот список; сверх — не добавлять)
Новый файл apps/api/tests/test_checkup_status_db.py (с БД, по образцу test_onboarding_form_db.py):
1. Нет активного участника → GET /checkup/status = 404 PARTICIPANT_NOT_FOUND.
2. Участник есть, Чек-Апа нет → 200 {completed: false, created_at: null}; других ключей в теле нет.
3. После успешного POST /checkup/submit → 200, completed = true, created_at не пустой; в тексте ответа нет «zone», «score», «green», «red».
4. Есть строка kind = 'body' (POST /onboarding/form), Чек-Апа нет → completed = false: фильтр по kind работает.
5. БД недоступна (api_client, как test_submit_valid_db_unavailable_503) → 503 SERVICE_UNAVAILABLE.
6. Лог app.checkup: есть «tg_user_id=<id>», нет pid и нет зоны.
Правка apps/api/tests/test_checkup_submit_db.py (точная — §11):
7. Второй Чек-Ап с НОВЫМ op_id → 409 CHECKUP_EXISTS; строка в measurements_log остаётся одна.
- check.sh: bash tools/check.sh api. Тесты с БД (DATABASE_URL) гоняет CI.

## 10. Живые проверки на сервере (после мержа)
- Миграций нет → бэкап перед выкатом не нужен; alembic current остаётся 0015_onboarding_form.
- После выката: curl -s -o /dev/null -w "%{http_code}" https://<host>/healthz → 200; тот же curl на /miniapp/v1/checkup/status без заголовка initData → 401.

## 11. Задетые тесты (правило «Т»)
- apps/api/tests/test_checkup_submit_db.py :: test_repeat_op_id_returns_same_without_new_row — правка хвоста: три последние строки («other = _submit(db_api_client, 5301, [3] * 15)», проверка 200 и зоны «red», «len(_rows(clean_measurements, pid)) == 2») заменить на проверку 409 CHECKUP_EXISTS и «len(_rows(clean_measurements, pid)) == 1». Начало теста (повтор того же op_id → 200, одна строка) не трогать.
- apps/api/tests/test_telegram_init_data.py :: test_every_miniapp_v1_route_requires_init_data — правок НЕТ: тест перебирает маршруты /miniapp/v1/** из OpenAPI, новый GET подхватится сам и даст 401 (зависимость роутера miniapp_v1). Файл не открывать. [ШТАБ-тех 7]
- Не задеты: apps/api/tests/test_checkup_config.py (без БД, до проверки Чек-Апа дело не доходит — 503) и apps/api/tests/test_onboarding_form_db.py :: test_op_id_taken_by_checkup_409 (там один Чек-Ап на участника).
- Поиск по репо выполнен в окне З1: других тестов, которые сверяют маршруты или ответы checkup целиком, нет.

## 12. Запреты
- Миграций, правок GRANT и expected_tables.txt в этой задаче нет.
- Ответы, балл и зону в GET /checkup/status не отдавать; в лог — только tg_user_id и status (данные о здоровье).
- participant_events, outbox, idempotency_keys не трогать; participant_state не читать и не писать.
- initData, согласия, rate-limit, 18+, роли и GRANT не трогать.
- Тесты сверх §9 не добавлять; тесты вне §11 не чинить.
- docs/architecture/** не открывать и не править: правка контракта — дело ШТАБа (§16).

## 13. Готово, когда
- check.sh зелёный, CI 7/7; §9 выполнен полностью; §11 исправлен ровно по списку; файлов — 3 (§6); отличия от карточки — в описании PR.

## 14. Оценка
- Часы Автора ≈ 0,3. Кредиты 320 (вилка 280–350): ≈ 280 строк — checkup.py +90, новый тест ≈ 150, правка теста ≈ 40; один файл «Задетых тестов».

## 15. РЕВЬЮЕР: нет
- По DESIGNER §14 ничего из списка не трогается: initData, 18+, согласия (B-2), rate-limit (B-1), роли и GRANT БД (B-3), оплата; GET только читает, новых прав не нужно.

## 16. Канон и решения
(а) Используются: docs/architecture/build/miniapp-api-contract.yaml, раздел «Чек-Ап (Блок 5)»; 04 §4.8 и §4.9; 05 §5.1 и §5.5; DECISIONS.md Р-16 и Р-18.
(б) Противоречий канона с DECISIONS.md нет. Контракт молчит: у /checkup/submit нет кодов ответов, маршрута /checkup/status нет совсем → правка (в).
(в) Файл DOCS: architecture/build/miniapp-api-contract.yaml. Применяет ШТАБ DOCS-пакетом и sync ДО промпта Агенту.
Найди (4 строки подряд; в файле у пути 2 пробела, здесь +4 для разметки — снять 4):
      /miniapp/v1/checkup/submit:
        post:
          summary: "Отправить ответы Чек-Апа"
          parameters: [{ in: header, name: X-Client-Op-Id, required: true, schema: { type: string, format: uuid }}]
Замени на (те же +4 пробела — снять 4):
      /miniapp/v1/checkup/status:
        get:
          summary: "Пройден ли Чек-Ап онбординга (course-bot api-i3-4, Р-18)"
          description: |
            Только чтение, без замка; параметров и тела нет. Признак даёт сервер (Р-18):
            measurements_log kind='checkup' AND occasion='onboarding', created_at — самая ранняя
            такая строка. Строки kind='body' (вес анкеты) и Чек-Апы после Этапа
            (occasion='stage_end') не считаются. Балла, зоны и ответов в ответе нет.
            Согласия не проверяются (как GET /miniapp/v1/onboarding/form).
          responses:
            "200": { description: "Состояние Чек-Апа", content: { application/json: { schema: { type: object, required: [completed, created_at], properties: { completed: { type: boolean }, created_at: { type: [string, "null"], format: date-time } } } } } }
            "401": { $ref: "#/components/responses/Unauthorized" }
            "404": { description: "PARTICIPANT_NOT_FOUND", content: { application/json: { schema: { $ref: "#/components/schemas/Error" } } } }
            "429": { $ref: "#/components/responses/RateLimited" }
            "503": { $ref: "#/components/responses/ServiceUnavailable" }

      /miniapp/v1/checkup/submit:
        post:
          summary: "Отправить ответы Чек-Апа (один раз за онбординг; Р-18)"
          description: |
            Повтор с тем же X-Client-Op-Id → 200 с сохранёнными значениями. Новый op_id, когда
            Чек-Ап онбординга уже есть → 409 CHECKUP_EXISTS (тело — только code и message).
          parameters: [{ in: header, name: X-Client-Op-Id, required: true, schema: { type: string, format: uuid }}]
          responses:
            "200": { description: "Принято или повтор", content: { application/json: { schema: { type: object, required: [zone, config_version, created_at], properties: { zone: { type: string, enum: [green, yellow, red] }, config_version: { type: string }, created_at: { type: string, format: date-time } } } } } }
            "401": { $ref: "#/components/responses/Unauthorized" }
            "404": { description: "PARTICIPANT_NOT_FOUND", content: { application/json: { schema: { $ref: "#/components/schemas/Error" } } } }
            "409": { description: "RECONSENT_REQUIRED / CHECKUP_EXISTS / IDEMPOTENCY_CONFLICT", content: { application/json: { schema: { $ref: "#/components/schemas/Error" } } } }
            "422": { description: "VALIDATION_ERROR (details.errors: [{loc, type}], без значений полей)", content: { application/json: { schema: { $ref: "#/components/schemas/Error" } } } }
            "429": { $ref: "#/components/responses/RateLimited" }
            "503": { $ref: "#/components/responses/ServiceUnavailable" }
(г) Других правок канона нет.
