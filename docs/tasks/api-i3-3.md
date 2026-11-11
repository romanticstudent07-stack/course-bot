# api-i3-3 — API: Карточка участника (GET /me/card) и Карта изменений (GET /me/change-map)

## 1. Паспорт
- id: api-i3-3 · PR: «feat(api): карточка участника и карта изменений (api-i3-3)» · ветка: feat/api-i3-3-me-card
- Режим: Агент Р1 · РЕВЬЮЕР: нет (§15) · Зависит от: ничего; миграции нет (§8); промпт Агенту — после sync DOCS (§16).
- Основа: PLAN §5 п.10; docs/research/iter3-2.md §2, §6 (К3, Л4 А, Л5 А). «Как сейчас» — по коду @4361f3c.
- Оценка: 520 кредитов (§14). Тесты сверх §9 не добавлять. Упал тест вне §11 — не чинить: «тест X вне списка» в ИТОГ и стоп.

## 2. Цель
- GET /miniapp/v1/me/card — карточка участника свежей из БД: номер, дата регистрации, пояс, позиция дня, жизни, вес и зона Чек-Апа (старт и последнее).
- GET /miniapp/v1/me/change-map — Карта изменений И3 на лету: слои anthro, wellbeing, checkup, functional; baseline + до 5 последних.
- Согласия — только чтение: GET /miniapp/v1/consents уже есть (1e-2), его код не меняется; отзыв — И4.

## 3. Решения Автора
- Р-16: ФИО, телефон, email не собираем; город → только tz, город не хранится. [К-6: Автор]
- Р-3: фото участников нет → слоя photo4 нет. Р-6: настроек уведомлений нет. [К-6: Автор]
- Л4 А (I3 §C.12): согласия в И3 — только просмотр, отзыв — И4. [К-6: Автор]
- Л5 А: пустых экранов нет; где данных нет — «нет данных» (в API: null или []). [К-6: Автор]
- Р-18, 1А: «Признак „Чек-Ап пройден“ даёт сервер.» Участнику — только зона, балла нет (I3 §C.7). [К-6: Автор]
- Р-2: существующих участников гейт доступа не трогает → 403 ACCESS_NOT_GRANTED здесь нет. [К-6: Автор]

## 4. Выдержки (КОДЕР архитектуру не читает)
- 06 §6.1: «Карточка формируется свежей из БД в момент запроса (не хранится готовой).»
- miniapp-screens: me.card — «данные, замеры, позиция, жизни»; contract /me/card — «без секции консентов и юр.данных».
- 14 §14.1: «Baseline per (pid, metric_key) детерминирован: MIN(taken_at_ms), tie-break MIN(event_id)» → у нас MIN(created_at), затем MIN(id).
- 14 §14.2: «Пять слоёв: anthro (число), photo4 (приватное ПДн-медиа), wellbeing (шкальные), functional (число), checkup»; врезка Р-3: фото нет.
- 14 §14.3: «inflammation_zone (0=green, 1=yellow, 2=red; direction=lower_better, enum_zone)».
- 14 §14.4: «окно K=6 по умолчанию (baseline + 5 последних + текущий) … хранение UTC … участник — только своё».
Отличия от канона в И3 (решил ШТАБ / ПРОЕКТИРОВЩИК, К-5):
- пометка улучшение/ухудшение (06 §6.4) — с задачи повторных Чек-Апов после Этапа, по зоне (14 §14.3); поля направления в /me/card нет;
- кэш change_map_cache 14 §14.4 — позже; при чтении на лету; пагинации и полной истории нет;
- слой checkup — только зона: тренда суммы и детализации по 15 утверждениям нет (I3 §C.7, 05 §5.4); photo4 нет (Р-3); functional — нет данных;
- статуса и фазы нет (06: долг Б10; DEFECTS «А1 с позицией дня → онбординг»); оплат, пауз, возвратов нет (Р-1, Р-6а); жизни — только остаток;
- даты — UTC ISO; локальный день считает клиент по tz из /me/card (tz_change_log нет).

## 5. ЧТО ПРОЧИТАТЬ (точный список)
- AGENT-BRIEF.md 17,1 КБ · эта карточка.
- apps/api/main.py 5,7 КБ — правится (импорт, include, docstring).
- apps/api/app/routers/checkup.py 14,6 КБ — образец GET /checkup/status (404, 503, rollback, лог).
- apps/api/app/participants.py 4,8 КБ — find_active_participant.
- apps/api/tests/conftest.py 8,1 КБ; apps/api/tests/test_checkup_submit_db.py 9,1 КБ; apps/api/tests/test_onboarding_form_db.py 9,9 КБ — фикстуры и образцы.
- short_no: формат — как в ответе GET /onboarding/status (apps/api/app/routers/onboarding.py, найти «short_no»; ту же функцию или поле, не своё).
- Чтение КОДЕРА ≈ 70 КБ + карточка.

## 6. Файлы
- Создать: apps/api/app/routers/me.py; apps/api/tests/test_me_db.py.
- Изменить: apps/api/main.py (импорт me, me.router в build_miniapp_v1_router, 2 строки в docstring «Маршруты»).
- Таблиц не добавляем → apps/api/tests/expected_tables.txt не трогать.

## 7. Контракт
Общее для обоих GET (параметров и тела нет; initData и rate-limit — роутер miniapp_v1):
- pid — только find_active_participant(tg_user_id из initData); нет активного участника (или tombstoned) → 404 PARTICIPANT_NOT_FOUND.
- Только чтение, замка нет, согласия не проверяются (как GET /checkup/status); перед ответом — rollback.
- SQLAlchemyError → 503 SERVICE_UNAVAILABLE, в лог — имя класса. 401 TG_INIT_* и 429 RATE_LIMITED — от роутера.
- Лог INFO: «me/card: tg_user_id=%s status=ok|404», «me/change-map: …». Ни pid, ни веса, ни зоны, ни кода самочувствия.
- Чтение (text-SQL, как _STATE_SQL в day.py):
  SELECT created_at FROM tg_user_registry WHERE pid = :pid
  SELECT lives, stage_no, module_no, day_no, tz FROM participant_state WHERE pid = :pid
  SELECT wellbeing_code, created_at FROM onboarding_form WHERE pid = :pid
  SELECT id, kind, occasion, checkup_zone, weight_kg, created_at FROM measurements_log WHERE pid = :pid ORDER BY created_at, id
- checkup_score и checkup_answers не выбирать вообще.

GET /miniapp/v1/me/card → 200, ровно эти ключи:
- short_no: string; registered_at: date-time (tg_user_registry.created_at).
- tz: string | null — participant_state.tz, только если есть строка state И строка onboarding_form; иначе null (DEFAULT колонки до анкеты — не данные; К-5).
- position: {stage_no, module_no, day_no} | null — null, если строки state нет или хоть один номер NULL.
- lives: int — participant_state.lives; строки state нет → 3 (как /day/current, DEFAULT колонки).
- measurements: {weight_start_kg: number|null, weight_current_kg: number|null, checkup_completed: bool, zone_start: green|yellow|red|null, zone_last: …|null}.
  weight — первая и последняя строки kind body (порядок created_at, id), float(weight_kg); zone — первая и последняя kind checkup; checkup_completed — есть строка kind checkup AND occasion onboarding (как GET /checkup/status, Р-18).

GET /miniapp/v1/me/change-map → 200 {layers: [4 объекта, порядок anthro, wellbeing, checkup, functional]}:
- слой: {layer, metric, baseline: Point | null, recent: [Point]}; Point = {value, at: date-time UTC}.
- anthro: metric weight_kg; строки kind body; value — number.
- wellbeing: metric wellbeing_code; baseline — из onboarding_form (value — код, at — created_at); recent всегда [].
- checkup: metric inflammation_zone; строки kind checkup; value — зона (string).
- functional: metric null, baseline null, recent [].
- baseline — первая строка (created_at, затем id); recent — до 5 последних строк после baseline, по возрастанию; baseline в recent не входит.
- Нет данных в слое → baseline null, recent []; слой всё равно есть (Л5).

## 8. БД: миграции нет
- Права есть (по коду): tg_user_registry SELECT (0006); participant_state — роль participant_state_reader (0006, колонки 0007); measurements_log SELECT (id, kind, occasion, checkup_zone, weight_kg, created_at) (0014); onboarding_form SELECT (wellbeing_code, created_at) (0015).
- Миграций, GRANT, expected_tables.txt не трогать.

## 9. Тесты (ровно этот список) — apps/api/tests/test_me_db.py
1. Нет активного участника → /me/card и /me/change-map = 404 PARTICIPANT_NOT_FOUND (parametrize).
2. Только first-launch → /me/card 200: набор ключей ровно §7; tz null, position null, lives 3, веса null, checkup_completed false, зоны null.
3. После POST /onboarding/form и POST /checkup/submit → weight_start_kg = weight_current_kg = вес анкеты; checkup_completed true; zone_start = zone_last; в тексте ответа нет «score», «answers».
4. Строки stage_end (kind body и checkup) вставлены напрямую через db_engine → weight_current_kg и zone_last — новые, стартовые прежние.
5. /me/change-map без замеров → 4 слоя в порядке §7, baseline null, recent [].
6. Анкета + 6 строк stage_end kind body → anthro: baseline = вес анкеты, recent — 5 последних по возрастанию; wellbeing.baseline.value = код анкеты.
7. Две строки kind body с одинаковым created_at → baseline — меньший id.
8. БД недоступна (api_client, как test_submit_valid_db_unavailable_503) → 503 SERVICE_UNAVAILABLE для обоих GET.
9. Лог: есть «tg_user_id=<id>»; нет pid, веса, зоны.
10. Без БД: функция сборки position — None при любом NULL номере, объект при всех трёх.
- check.sh: bash tools/check.sh api. Тесты с БД (DATABASE_URL) гоняет CI.

## 10. Живые проверки (после мержа)
- Миграций нет → бэкап не нужен; alembic current остаётся 0015_onboarding_form.
- curl /healthz → 200; /miniapp/v1/me/card и /miniapp/v1/me/change-map без initData → 401.

## 11. Задетые тесты (правило «Т»)
- Правок не ожидается. apps/api/tests/test_telegram_init_data.py — новые маршруты /miniapp/v1/** проверяются автоматически (401 без заголовка); test_openapi_has_only_expected_public_routes их не задевает. Файл не открывать.
- Поиск: grep «app.routes|openapi()|/miniapp/v1/me» по apps/api/tests (ШТАБ, 11.11) — других совпадений нет. Общих списков (kinds, expected_tables) задача не меняет.

## 12. Запреты
- Балл, ответы Чек-Апа, пол, город — не выбирать и не отдавать; в лог — только tg_user_id и status.
- consent_events, consents.py, initData, rate-limit, роли и GRANT не трогать; participant_state только читать.
- Не писать в БД ничего; participant_events, outbox, idempotency_keys не трогать.
- Тесты сверх §9 не добавлять; тесты вне §11 не чинить. docs/architecture/** не открывать (правка — §16).

## 13. Готово, когда
- check.sh зелёный, CI 7/7; §9 полностью; файлов 3 (§6); отличия от карточки — в описании PR.

## 14. Оценка
- Часы Автора ≈ 0,3. Кредиты 520 (вилка 450–650): ≈ 430 строк — me.py ≈ 220, main.py ≈ 5, test_me_db.py ≈ 200; файлов «Задетых тестов» 0. Урок ×1,6 учтён вилкой.

## 15. РЕВЬЮЕР: нет
- По DESIGNER §14 не трогаются initData, 18+, согласия (B-2), rate-limit (B-1), роли и GRANT (B-3), оплата; оба GET только читают.

## 16. Канон и решения
(а) Используются: 06 §6.1, §6.4, Fail-safe; 05 §5.4; 14 §14.1–§14.4 и врезка Р-3; build/miniapp-screens.md (me.card, me.consents, me.change-map); build/miniapp-api-contract.yaml (Согласия; Карточка / данные участника).
(б) С DECISIONS.md расходятся: contract POST /consents «Обновление / отзыв согласия» без срока — против Л4 А; 14 §14.2 photo4 — против Р-3 (врезка Р-3 уже в 14). 06 §6.4 «Кто» и 05 §5.4 уже исправлены (правок нет). /me/card и /me/change-map — только summary.
(в) Файл DOCS: architecture/build/miniapp-api-contract.yaml. Применяет ШТАБ DOCS-пакетом и sync ДО промпта Агенту. Отступ: в файле у пути 2 пробела, здесь +4 — снять 4.
Правка 1. Найди: «      summary: "Обновление / отзыв согласия"» → замени на «      summary: "Обновление / отзыв согласия — с И4 (I3 §C.12)"».
Правка 2. Найди (6 строк):
      /miniapp/v1/me/card:
        get:
          summary: "Моя карточка (динамическая, без секции консентов и юр.данных)"

      /miniapp/v1/me/change-map:
        get:
          summary: "Моя полная Карта изменений"
Замени на:
      /miniapp/v1/me/card:
        get:
          summary: "Моя карточка (course-bot api-i3-3): данные, замеры, позиция, жизни; без согласий и юр.данных"
          description: |
            Только чтение, свежая из БД (06 §6.1); согласия не проверяются. Нет данных → null (Л5).
            Балла нет (I3 §C.7); статуса, оплат, пауз нет; направления зоны — с повторных Чек-Апов.
          responses:
            "200": { description: "Карточка", content: { application/json: { schema: { type: object, required: [short_no, registered_at, tz, position, lives, measurements], properties: { short_no: { type: string }, registered_at: { type: string, format: date-time }, tz: { type: [string, "null"] }, position: { type: [object, "null"], required: [stage_no, module_no, day_no], properties: { stage_no: { type: integer }, module_no: { type: integer }, day_no: { type: integer } } }, lives: { type: integer, minimum: 0, maximum: 3 }, measurements: { type: object, required: [weight_start_kg, weight_current_kg, checkup_completed, zone_start, zone_last], properties: { weight_start_kg: { type: [number, "null"] }, weight_current_kg: { type: [number, "null"] }, checkup_completed: { type: boolean }, zone_start: { enum: [green, yellow, red, null] }, zone_last: { enum: [green, yellow, red, null] } } } } } } } }
            "401": { $ref: "#/components/responses/Unauthorized" }
            "404": { description: "PARTICIPANT_NOT_FOUND", content: { application/json: { schema: { $ref: "#/components/schemas/Error" } } } }
            "429": { $ref: "#/components/responses/RateLimited" }
            "503": { $ref: "#/components/responses/ServiceUnavailable" }

      /miniapp/v1/me/change-map:
        get:
          summary: "Моя Карта изменений (course-bot api-i3-3): anthro, wellbeing, checkup, functional"
          description: |
            На лету из БД (кэш 14 §14.4 — позже). Baseline — MIN(created_at), затем MIN(id) (14 §14.1);
            recent — до 5 последних после baseline, по возрастанию. checkup — только зона (I3 §C.7);
            photo4 нет (Р-3). Даты UTC; локальный день — на клиенте по tz из /me/card.
          responses:
            "200": { description: "Слои", content: { application/json: { schema: { type: object, required: [layers], properties: { layers: { type: array, items: { type: object, required: [layer, metric, baseline, recent], properties: { layer: { enum: [anthro, wellbeing, checkup, functional] }, metric: { enum: [weight_kg, wellbeing_code, inflammation_zone, null] }, baseline: { type: [object, "null"], required: [value, at], properties: { value: { type: [number, string] }, at: { type: string, format: date-time } } }, recent: { type: array, maxItems: 5, items: { type: object, required: [value, at], properties: { value: { type: [number, string] }, at: { type: string, format: date-time } } } } } } } } } } } }
            "401": { $ref: "#/components/responses/Unauthorized" }
            "404": { description: "PARTICIPANT_NOT_FOUND", content: { application/json: { schema: { $ref: "#/components/schemas/Error" } } } }
            "429": { $ref: "#/components/responses/RateLimited" }
            "503": { $ref: "#/components/responses/ServiceUnavailable" }
(г) Других правок канона в этой карточке нет (iter3-2 §4 п.3, 6, 9 ведёт ШТАБ).
