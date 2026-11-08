# api-i3-2 — правка DOCS №13: маршруты анкеты в miniapp-api-contract.yaml

Назначение: правка канона для карточки api-i3-2, раздел «Канон и решения» (в). В contract.yaml нет эндпоинтов анкеты (iter3-2 §4, DOCS №13). Путь и поля утверждены ШТАБом 07.11. Применяет ШТАБ PR-ом DOCS до промпта Агенту, затем sync.

Файл · найди · замени:
- файл: architecture/build/miniapp-api-contract.yaml
- найди: «  # ---------------- Согласия (C0–C6) ----------------»
- замени: блок ниже (отступ в файле — 2 пробела на уровень от paths; здесь у каждой строки 6 пробелов для разметки, снять 4), затем найденная строка без изменения.

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
