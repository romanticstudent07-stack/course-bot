# api-i3-2 — анкета (api): конфиг, GET и POST /onboarding/form, вес, пояс событием

## 1. Паспорт
- id: api-i3-2 · ветка: api/i3-2-onboarding-form · режим: Р1 (Агент; промпт пишет ШТАБ по карточке) · PLAN §5 п.10, первая часть · РЕВЬЮЕР: да (раздел 14).
- Заголовок PR: «api: анкета — GET form/config, GET и POST /onboarding/form (api-i3-2)».
- Зависит от: cities-1 (cities.csv в main) и projector-i3-2 (EVENT_KIND_TZ_SET в main, тест 14). До промпта — PR DOCS №13 и sync. Выкат: projector-i3-2 раньше api (неизвестный kind сдвигает checkpoint — tz_set потеряется; по коду projector.py).
- Не входит: /me/card, /me/change-map, согласия (api-i3-3); экран и фильтр по буквам (miniapp-1); стирание (PLAN §5 п.22).

## 2. Цель
Mini App получает конфиг анкеты (пол, вопрос и коды самочувствия, границы веса, 11 запасных поясов, ≈1 100 городов) и один раз отправляет анкету: пол и код — в onboarding_form, вес — в measurements_log (kind body), пояс — событием tz_set для проектора. GET /onboarding/form отвечает, отправлена ли анкета. Все тексты — заглушки, каждый начинается с «Заглушка».

## 3. Решения (метки К-6)
- Р-16 [Автор, DECISIONS]: «город → только tz (IANA), сам город не храним; пол; вопрос „самочувствие“ (текст даст Автор); стартовые замеры — в таблицу Чек-Апа. ФИО, телефон, email не собираем, в черновике тоже.»
- А2 [Автор 05.11]: пол male / female, обязательно. В3 [Автор 07.11]: вес обязателен.
- Р-17 [Автор 07.11; запись в DECISIONS — ШТАБ]: город — ввод с подсказками, засчитывается только выбор из подсказок; ≈1 100 городов; «Моего города нет» → текст-заглушка и 11 кнопок по поясам РФ; на сервер уходит только tz.
- В1 [Автор 07.11]: стирание — не здесь; требования — раздел «Требования к п.22».
- Ш-2…Ш-6 [ШТАБ-тех 07.11, К-5]: три маршрута; роутер app/routers/onboarding_form.py, onboarding.py не трогать; вес Decimal 30–300, больше 1 знака → 422 без округления; tz — только из набора поясов файла городов и 11 запасных; экран — miniapp-1.
- П-1 [ПРОЕКТИРОВЩИК, К-5]: города — в GET form/config ([город, регион, i], i — индекс в timezones), ≈ 75 КБ без gzip, один раз за онбординг; отдельного статического файла нет — один источник (cities.csv) и для клиента, и для проверки.
- П-2 [ПРОЕКТИРОВЩИК, К-5]: анкета один раз (04 §4.8): анкета уже есть, а op_id другой → 409 ONBOARDING_FORM_EXISTS.
- П-3 [ПРОЕКТИРОВЩИК, К-5]: GET /onboarding/form без участника → 404 PARTICIPANT_NOT_FOUND (как checkup); гейта согласий нет — отдаются только факт и дата.

## 4. Выдержки архитектуры
- 04 §4.4 (врезка Р-16): «часовой пояс … хранится только IANA-пояс (participant_state.tz через проектор), название города не хранится; пол — male / female, обязательно; самочувствие — код ответа (формулировку даст Автор); стартовые замеры — только вес, в measurements_log вместе с Чек-Апом».
- 04 §4.8 yaml: «reask: none», «new_measurements: append_to_journal».
- 14 §14.11: пояс — со следующего дня; до первого дня проектор пишет сразу (projector-i3-2, WHERE day_no IS NULL).
- E1 / INV-1: participant_state пишет только проектор (tests/test_projector_static.py).
- 0015 (по коду): app_api — INSERT (pid, gender, wellbeing_code) и SELECT; UPDATE и DELETE нет; CHECK gender, wellbeing_code ^[a-z0-9_]{1,32}$.
- 0014 (по коду): measurements_log, kind body — weight_kg, occasion onboarding, stage_no NULL; UNIQUE (pid, client_op_id).

## 5. ЧТО ПРОЧИТАТЬ (Агент)
app/routers/checkup.py 11,2 КБ (образец целиком); app/checkup_config.py 8,9 (файл, кэш, ошибка → 503); app/consent_status.py 5,4; app/participant_lock.py (размер не проверен); app/participants.py 4,8; main.py 4,1; app/db/models.py — только классы OnboardingForm и MeasurementLog; tests/test_checkup_submit_db.py 9,1; tests/test_checkup_config.py 7,7; tests/conftest.py 8,1; config/onboarding/cities.csv — первые 5 строк. Чтение ≈ 85 КБ.

## 6. Файлы
- Создать: apps/api/config/onboarding/form.json; apps/api/app/onboarding_form_config.py; apps/api/app/routers/onboarding_form.py; apps/api/tests/test_onboarding_form_config.py; apps/api/tests/test_onboarding_form_db.py.
- Изменить: apps/api/main.py (импорт; роутер в build_miniapp_v1_router; три строки в докстринге).
- Миграций нет; expected_tables.txt не меняется.

## 7. Контракт и логика (схемы — DOCS №13 ниже)
- form.json: version «onboarding-form-stub-1»; wellbeing_question «Заглушка: вопрос о самочувствии»; wellbeing — коды option_1, option_2, option_3, option_4 с текстами «Заглушка: вариант N»; weight {min 30, max 300, step 0.1}; fallback_title «Заглушка: выберите подходящий по часовому поясу город»; timezones по порядку: Калининград Europe/Kaliningrad, Москва Europe/Moscow, Самара Europe/Samara, Екатеринбург Asia/Yekaterinburg, Омск Asia/Omsk, Новосибирск Asia/Novosibirsk, Иркутск Asia/Irkutsk, Якутск Asia/Yakutsk, Владивосток Asia/Vladivostok, Магадан Asia/Magadan, Петропавловск-Камчатский Asia/Kamchatka.
- Загрузчик onboarding_form_config.py: form.json и cities.csv читаются один раз (кэш, как checkup_config). Проверяет: коды уникальны и по шаблону; 11 timezones, каждый открывается ZoneInfo; каждый tz из cities.csv есть в timezones. allowed_tz — множество поясов. Ошибка файла → как в checkup_config (503 SERVICE_MISCONFIGURED).
- GET /onboarding/form/config: БД не нужна; 200 по схеме; cities — [city, region, индекс в timezones].
- GET /onboarding/form: активный pid без замка, только чтение (функция — по коду participants.py) → нет → 404; иначе SELECT created_at FROM onboarding_form WHERE pid → 200 {submitted, created_at}.
- POST /onboarding/form: заголовок X-Client-Op-Id Annotated[UUID4, Header] (как checkup). Тело (pydantic): tz — str 1–64 и в allowed_tz; gender — Literal male / female; wellbeing_code — из кодов конфига; weight_kg — Decimal ge 30, le 300, max_digits 4, decimal_places 1. Лишние поля (city, name, phone, email) отбрасываются и нигде не пишутся. Ошибка → 422 VALIDATION_ERROR (обработчик errors.py, без значений полей).
- Транзакция POST:
  1. active_pid_locked; нет → 404 PARTICIPANT_NOT_FOUND.
  2. C0 и C1 (consent_status): нет текста → 503 SERVICE_MISCONFIGURED; есть причины → 409 RECONSENT_REQUIRED.
  3. SELECT created_at FROM onboarding_form WHERE pid; SELECT kind FROM measurements_log WHERE pid = :pid AND client_op_id = :op.
  4. Анкета есть: строка op с kind body → повтор, commit, 200 {created_at анкеты}; иначе → 409 ONBOARDING_FORM_EXISTS.
  5. Анкеты нет, а строка op есть → 409 IDEMPOTENCY_CONFLICT.
  6. INSERT onboarding_form (pid, gender, wellbeing_code) ON CONFLICT (pid) DO NOTHING RETURNING created_at (пусто → 409 ONBOARDING_FORM_EXISTS); INSERT measurements_log (pid, kind, occasion, stage_no, weight_kg, client_op_id) VALUES (:pid, 'body', 'onboarding', NULL, :w, :op) ON CONFLICT (pid, client_op_id) DO NOTHING RETURNING id (пусто → 409 IDEMPOTENCY_CONFLICT); INSERT participant_events (pid, kind, payload, actor, actor_role) VALUES (:pid, 'tz_set', CAST(:payload AS jsonb), 'participant', 'participant'), payload {"schema_version": 1, "tz": tz}.
  7. commit → 200 {created_at}. Записываются все три строки или ни одной.
- Любая SQLAlchemyError (и на commit) → rollback, 503 SERVICE_UNAVAILABLE; в лог — имя класса.
- Лог app.onboarding_form: INFO только tg_user_id и status (created / repeat / exists). pid, op_id, пола, кода, веса и tz в логе нет.
- participant_state не читать и не писать (INV-1); outbox и idempotency_keys не используются.

## 8. БД
Миграций нет. Права уже есть: 0015 (onboarding_form INSERT, SELECT), 0014 (measurements_log INSERT, SELECT, последовательность), participant_events INSERT — как у first-launch (по коду).

## 9. Тесты (сверх этого списка не добавлять)
test_onboarding_form_config.py (без БД; check.sh api):
1. GET form/config → 200: ключи по схеме; genders [male, female]; 11 timezones; cities > 1 000, индексы 0–10.
2. Все тексты form.json начинаются с «Заглушка»; коды по шаблону и уникальны.
3. Каждый tz из cities.csv есть в timezones; все 11 открываются ZoneInfo.
4. Тело до БД (api_client, БД недоступна): tz Europe/London, «Moscow», '' → 422; gender «other» → 422; код не из конфига → 422; weight 72.55, 29.9, 300.1, «abc», true → 422; нет X-Client-Op-Id или он не v4 → 422; годное тело → 503 SERVICE_UNAVAILABLE.
test_onboarding_form_db.py (только CI; вызов функции, как test_checkup_submit_db.py):
5. Первый POST: 200; строка onboarding_form; строка body (72.5, onboarding, stage_no NULL); одно событие tz_set с нужным payload; до run_once participant_state.tz прежний.
6. После run_once проектора participant_state.tz = отправленный.
7. Повтор с тем же op_id → 200, тот же created_at, строк и событий не прибавилось.
8. Другой op_id после анкеты → 409 ONBOARDING_FORM_EXISTS, ничего не прибавилось.
9. op_id занят строкой checkup → 409 IDEMPOTENCY_CONFLICT, анкеты нет.
10. Без C0 / C1 → 409 RECONSENT_REQUIRED; нет участника или tombstone → 404; ничего не записано.
11. Сбой вставки события (monkeypatch → OperationalError) → 503; нет ни onboarding_form, ни body.
12. GET /onboarding/form: до анкеты {false, null}; после — true и дата; без участника 404; в теле нет gender, weight, tz.
13. В caplog после POST нет pid, tz, веса и кода самочувствия.
14. Константа kind в роутере == app.projector.EVENT_KIND_TZ_SET.

## 10. Живые проверки (СЕРВЕРНЫЙ; порядок выката — §1)
Сначала выкат projector-i3-2, потом api. GET /miniapp/v1/onboarding/form/config без initData → 401. Живой POST — с экраном miniapp-1. Бэкап не нужен.

## 11. Запреты
AGENT-BRIEF §3. Не трогать onboarding.py, projector.py, миграции, participant_state. Город, ФИО, телефон, email в модель не брать и не писать. Тексты — только заглушки; cities.csv не править; данные анкеты не логировать; CI не ждать (А-CI).

## 12. Критерии готовности
Три маршрута по DOCS №13; тесты 1–14 зелёные (1–4 в check.sh, все в CI); отличия от карточки — в описании PR.

## 13. Оценка
Автор ≈ 1 ч. Кредиты по объёму: 6 файлов ≈ 1 050 строк (form.json 50, загрузчик 160, роутер 320, main 10, тесты 170 + 340); ставка api-i3-1 905 / 1 204 ≈ 0,75 → ≈ 790, диапазон 700–900.

## 14. РЕВЬЮЕР
Да: ПДн; пол, самочувствие, вес — данные о здоровье; гейт C0 / C1.

## Задетые тесты
Не ожидается. Общие списки проверены: test_telegram_init_data.py::test_every_miniapp_v1_route_requires_init_data сам обходит OpenAPI — новые маршруты попадут без правки; test_openapi_has_only_expected_public_routes смотрит только маршруты вне /miniapp/v1; kind tz_set добавляет projector-i3-2 (его раздел); ролей, text_id, таблиц, TTL_BY_KIND задача не добавляет.

## Требования к п.22 (код стирания здесь не пишется) [Автор 07.11, В1 = А]
- onboarding_form (пол, код самочувствия): DELETE строк по pid после паузы 14 дней. Роль — новый GRANT DELETE ON onboarding_form роли стирания (в 0001 есть erasure_worker; выбор роли — п.22). app_api DELETE не получает. Канон: 99-02 erasure, 99-03 — про анкету молчат (таблица наша) → решение Автора.
- measurements_log (вес, Чек-Ап) и participant_events (payload tz_set): не удаляются, обезличиваются через tombstone (tg_user_registry.tombstoned_at) и erasure_blacklist. Канон (выдержки из З1): 14 §14.1 «UPDATE/DELETE запрещены навсегда для measurements_log»; 14 §14.6 «pid → erased:{hash}, числовые ряды остаются обезличенными»; 99-02 / 99-03 INV-L-02 — отзыв согласия не удаляет прошлые правомерные записи. Роль tombstone — по указанию ШТАБа проектор (GRANT UPDATE (tombstoned_at)); в 0001 erasure_worker пишет erasure_blacklist.
- participant_state.tz → Europe/Moscow: событием через проектор (INV-1), не прямым UPDATE.
- Сроки: пауза 14 дней [Автор]; по канону при запросе участника — обезличить не позже 30 дней (99-02 retention: 30 дней после min(lifecycle_end + 6 мес., erasure_request)). Пауза плюс обработка — не больше 30 дней. Окно 14 дней в каноне — operator_initiated.appeal_window (99-02 erasure), это не отзыв участником.
- Бэкапы: erasure_blacklist не даёт вернуть pid из бэкапа (0001, ADD5) — п.22 проверяет и onboarding_form.

## Канон и решения
(а) 04 §4.4, §4.8; 14 §14.11; E1 / INV-1; build/miniapp-api-contract.yaml; 99-02, 99-03 (п.22).
(б) В contract.yaml нет маршрутов анкеты (DOCS №13). 04 §4.4 «кнопки-города» противоречит Р-17 — правка в cities-1 (в). 14 §14.11 tz_change_log против истории в participant_events — кандидат в DEFECTS (ШТАБ).
(в) DOCS №13 · architecture/build/miniapp-api-contract.yaml · найди: «  # ---------------- Согласия (C0–C6) ----------------» · замени: блок ниже, затем та же строка без изменения.

      # ---------------- Анкета онбординга (Шаг 4; Р-16, Р-17; course-bot api-i3-2) ----------------
      /miniapp/v1/onboarding/form/config:
        get:
          summary: "Конфиг анкеты: пол, самочувствие, вес, пояса, города (Р-16, Р-17)"
          description: |
            Без БД; участник не обязателен. Тексты — заглушки до юр-ревью.
            cities: [город, регион, i], i — индекс в timezones. Город на сервер не уходит (Р-16).
          responses:
            "200":
              description: "Конфиг анкеты"
              content:
                application/json:
                  schema:
                    type: object
                    required: [version, genders, wellbeing_question, wellbeing, weight, timezones, fallback_title, cities]
                    properties:
                      version: { type: string }
                      genders: { type: array, items: { type: string, enum: [male, female] } }
                      wellbeing_question: { type: string }
                      wellbeing: { type: array, items: { type: object, required: [code, text], properties: { code: { type: string, pattern: "^[a-z0-9_]{1,32}$" }, text: { type: string } } } }
                      weight: { type: object, required: [min, max, step], properties: { min: { type: number }, max: { type: number }, step: { type: number } } }
                      timezones: { type: array, description: "11 кнопок «Моего города нет»", items: { type: object, required: [tz, city], properties: { tz: { type: string }, city: { type: string } } } }
                      fallback_title: { type: string }
                      cities: { type: array, items: { type: array, prefixItems: [{ type: string }, { type: string }, { type: integer }], minItems: 3, maxItems: 3 } }
            "401": { $ref: "#/components/responses/Unauthorized" }
            "429": { $ref: "#/components/responses/RateLimited" }
            "503": { $ref: "#/components/responses/ServiceUnavailable" }
      /miniapp/v1/onboarding/form:
        get:
          summary: "Отправлена ли анкета (без пола, веса, пояса)"
          responses:
            "200": { description: "Состояние", content: { application/json: { schema: { type: object, required: [submitted, created_at], properties: { submitted: { type: boolean }, created_at: { type: [string, "null"], format: date-time } } } } } }
            "401": { $ref: "#/components/responses/Unauthorized" }
            "404": { description: "PARTICIPANT_NOT_FOUND", content: { application/json: { schema: { $ref: "#/components/schemas/Error" } } } }
            "429": { $ref: "#/components/responses/RateLimited" }
            "503": { $ref: "#/components/responses/ServiceUnavailable" }
        post:
          summary: "Отправить анкету один раз (04 §4.8)"
          description: |
            Одна транзакция: onboarding_form (пол, код самочувствия) + measurements_log (kind body, вес)
            + событие tz_set (проектор пишет participant_state.tz до начала первого дня; INV-1).
            Город, ФИО, телефон, email не принимаются и не хранятся (Р-16). Нужны действующие C0 и C1.
            Повтор с тем же X-Client-Op-Id → 200 с тем же created_at, новых строк нет.
          parameters: [{ in: header, name: X-Client-Op-Id, required: true, schema: { type: string, format: uuid }}]
          requestBody:
            required: true
            content:
              application/json:
                schema:
                  type: object
                  required: [tz, gender, wellbeing_code, weight_kg]
                  properties:
                    tz: { type: string, minLength: 1, maxLength: 64, description: "IANA из form/config (timezones или cities)" }
                    gender: { type: string, enum: [male, female] }
                    wellbeing_code: { type: string, pattern: "^[a-z0-9_]{1,32}$", description: "Код из form/config" }
                    weight_kg: { type: number, minimum: 30, maximum: 300, multipleOf: 0.1, description: "Не больше 1 знака после запятой; без округления" }
          responses:
            "200": { description: "Анкета принята или повтор", content: { application/json: { schema: { type: object, required: [created_at], properties: { created_at: { type: string, format: date-time } } } } } }
            "401": { $ref: "#/components/responses/Unauthorized" }
            "404": { description: "PARTICIPANT_NOT_FOUND", content: { application/json: { schema: { $ref: "#/components/schemas/Error" } } } }
            "409": { description: "RECONSENT_REQUIRED / ONBOARDING_FORM_EXISTS / IDEMPOTENCY_CONFLICT", content: { application/json: { schema: { $ref: "#/components/schemas/Error" } } } }
            "422": { description: "VALIDATION_ERROR (details.errors: [{loc, type}], без значений полей)", content: { application/json: { schema: { $ref: "#/components/schemas/Error" } } } }
            "429": { $ref: "#/components/responses/RateLimited" }
            "503": { $ref: "#/components/responses/ServiceUnavailable" }
