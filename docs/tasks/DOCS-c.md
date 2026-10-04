# DOCS-c — DOCS: контракт first-launch, short_no (course-bot D-12, D-10, D-9 п.(в))

## 1. Паспорт
- id: DOCS-c. Репо: **DOCS-course-bot**. Ветка DOCS: `agent/backend-first-launch-contract`.
- Заголовок PR: `[Backend]: first-launch и short_no по реализации (course-bot D-12, D-10, D-9в)`
- Режим: Р0 «Сайт», 3 файла. КОДЕР не нужен. **Зависит от: DOCS-b смержен** (тот же контракт).
- Номера: в DOCS D-12 — ДРУГОЙ дефект (erasure_blacklist). Писать «course-bot D-12».
  Новая запись в реестре DOCS — только **D-32**.

## 2. Цель
Контракт first-launch описывает то, что принято Автором и работает в course-bot:
согласия в теле, 403/422/429/503, повторный 201, `short_no`. В И1 — врезка «Уточнено
реализацией». YAML И1 не правится (6Б). Модель авторизации (course-bot D-9 п.(а)) не трогаем.

## 3. Решения Автора (дословно)
- course-bot D-12, «Предлагаемое решение»: «в DOCS-course-bot добавить `short_no` в колонки И1,
  описать в контракте 422/503 и семантику повторного 201». Уточнено З2-6Б: «врезка «Уточнено
  реализацией» в шапке И1 + запись в `appendix/D-source-defects.md`, YAML не трогать».
- course-bot D-12: повторный вызов → 201 с тем же телом; после tombstone — новый `pid` и `short_no`
  (И1, Р243); 503 `SERVICE_UNAVAILABLE` в формате `Error`; «сегодня» — `SERVER_TIMEZONE`;
  дата рождения не хранится; пропуски `short_no` допустимы.
- З2-7Б: переписать блок целиком по принятым решениям (course-bot D-10: `consents`, 422;
  course-bot D-9 п.(в): 503 `SERVICE_MISCONFIGURED` в `components.responses`).
- З2-8А: 422 — формат `Error` / `VALIDATION_ERROR` с пометкой «после B-3b» (course-bot D-18).
- Не решено и НЕ пишем как решённое: место оплаты (course-bot D-10), модель TTL (course-bot D-9).

## 4. Факты реализации (`apps/api/app/routers/onboarding.py`, 4cae002)
Тело `{birth_date, consents}`; обязательны C0 и C1; C2–C6 → 422 `CONSENT_NOT_SUPPORTED`;
коды: 401 `TG_INIT_MISSING` / `TG_INIT_INVALID`, 403 `AGE_GATE_UNDERAGE`, 422 `CONSENTS_REQUIRED`
(`details.missing`), `CONSENT_NOT_SUPPORTED` (`details.unsupported`), `BIRTH_DATE_IN_FUTURE`;
429 — rate-limit `/miniapp/v1/**` (course-bot B-1); 503 `SERVICE_UNAVAILABLE` (БД),
`SERVICE_MISCONFIGURED` (пустой `BOT_TOKEN`, неизвестный `SERVER_TIMEZONE`, нет текста согласия).
Неизвестный `tg_user_id` → 403 не отдаётся (SEAM-1). «Было» — дословно из зеркала 4cae002 (= DOCS main).

## 5. ЧТО ПРОЧИТАТЬ
КОДЕРа нет. `architecture/build/miniapp-api-contract.yaml` (около 10 КБ),
`architecture/normative/I1-wave-a.md` (32 КБ — только Ctrl+F, целиком не читать),
`architecture/appendix/D-source-defects.md` (около 9 КБ). Чтение КОДЕРА: 0 КБ.

## 6. Правки
ОТСТУПЫ YAML — пробелами, ровно как в блоках (первый символ строки блока = начало строки в файле).

**Файл 1: `architecture/build/miniapp-api-contract.yaml`**

Правка 1.1 — `components.schemas.PidCreated`. Было:

        PidCreated:
          type: object
          properties:
            pid: { type: string, format: uuid }
            short_no: { type: string, example: "#000123" }

Станет:

        PidCreated:
          type: object
          required: [pid, short_no]
          properties:
            pid: { type: string, format: uuid }
            short_no:
              type: string
              example: "#000123"
              description: "Короткий номер участника (Б6 §6.3): # и не меньше 6 цифр (после 999999 — больше). Выдаётся при создании pid, только для показа; пропуски номеров возможны."

Правка 1.2 — `components.responses`, после `RateLimited`. Было:

        RateLimited:
          description: "Слишком много запросов"

Станет:

        RateLimited:
          description: "Слишком много запросов"
        ServiceUnavailable:
          description: |
            Сервис временно недоступен (fail closed), формат Error:
            SERVICE_UNAVAILABLE — БД недоступна;
            SERVICE_MISCONFIGURED — сервер настроен неверно (пустой BOT_TOKEN,
            неизвестный SERVER_TIMEZONE, нет текста согласия в text_registry).
          content:
            application/json:
              schema: { $ref: "#/components/schemas/Error" }

Правка 1.3 — блок пути first-launch целиком: от строки `/miniapp/v1/onboarding/first-launch:`
до строки с `"403"` включительно (комментарий «Онбординг (SEAM-1)» над ним не трогать).
Было — 20 строк из зеркала: `post:`, `summary`, `description` (2 строки), `requestBody`
с `required: [birth_date]`, ответы 201 / 401 / 403. Первая и последняя строки блока:

      /miniapp/v1/onboarding/first-launch:
            "403": { description: "Возрастной гейт: < 18" }

Станет:

      /miniapp/v1/onboarding/first-launch:
        post:
          summary: "Первый запуск Mini App — создание pid (SEAM-PATCH-1)"
          description: |
            Возрастной гейт → согласия → создание pid (INV-AGE-GATE-BEFORE-PID, ADD3 ERRATA).
            Порядок на сервере: initData → тело запроса → возраст (без БД; < 18 → 403)
            → обязательные согласия C0 и C1 (нет → 422) → одна транзакция: тексты согласий
            из text_registry → участник (pid, short_no) → события согласий give.
            Место оплаты в этом порядке не решено (course-bot D-10).
            «Сегодня» для возраста — дата в часовом поясе сервера (SERVER_TIMEZONE,
            Europe/Moscow): пояс участника на first-launch ещё неизвестен.
            Дата рождения не хранится: проверка только в момент запроса.
            Неизвестный tg_user_id не даёт 403: first-launch — единственная точка
            создания участника (SEAM-PATCH-1).
            Идемпотентность через tg_user_id: повторный вызов → 201 с тем же телом
            (тот же pid и short_no); уже данные согласия повторно не записываются.
            После tombstone тот же tg_user_id получает новый pid и новый short_no (И1, Р243).
            Уточнено реализацией course-bot (course-bot D-10, D-12; appendix/D-source-defects.md, D-32).
          requestBody:
            required: true
            content:
              application/json:
                schema:
                  type: object
                  required: [birth_date, consents]
                  properties:
                    birth_date: { type: string, format: date }
                    consents:
                      type: array
                      uniqueItems: true
                      description: "Обязательны C0 (18+) и C1 (ПДн). C2–C6 на first-launch не принимаются (422 CONSENT_NOT_SUPPORTED). Текст согласия выбирает сервер, клиент шлёт только id."
                      items: { type: string, enum: [C0, C1, C2, C3, C4, C5, C6] }
          responses:
            "201": { description: "Создан или уже существует (тот же pid и short_no)", content: { application/json: { schema: { $ref: "#/components/schemas/PidCreated" }}}}
            "401": { $ref: "#/components/responses/Unauthorized" }
            "403":
              description: "Возрастной гейт: < 18 (AGE_GATE_UNDERAGE). pid не создаётся."
              content:
                application/json:
                  schema: { $ref: "#/components/schemas/Error" }
            "422":
              description: |
                CONSENTS_REQUIRED — нет C0 или C1 (details.missing);
                CONSENT_NOT_SUPPORTED — согласие из C2–C6 (details.unsupported);
                BIRTH_DATE_IN_FUTURE — дата рождения позже «сегодня»;
                VALIDATION_ERROR — тело не по схеме (details.errors: [{loc, type}], без значений полей).
                course-bot: VALIDATION_ERROR — с задачи B-3b; до неё — стандартный ответ FastAPI с полем detail.
              content:
                application/json:
                  schema: { $ref: "#/components/schemas/Error" }
            "429": { $ref: "#/components/responses/RateLimited" }
            "503": { $ref: "#/components/responses/ServiceUnavailable" }

**Файл 2: `architecture/normative/I1-wave-a.md`** — вставка в шапку (YAML не трогать).
Место: Ctrl+F `См. [errata-unified.md](errata-unified.md) и [seam-patch` → ПЕРВОЕ совпадение
(конец абзаца «> **Переопределено ERRATA-UNIFIED.** …», около строки 16). Курсор в конец этой
строки → Enter, Enter → вставить (одна строка). Следующей непустой строкой должен остаться
заголовок «## Место в стеке старшинства».

    > **Уточнено реализацией (course-bot).** В реализации `tg_user_id_pid_registry` (таблица `tg_user_registry`) есть колонка `short_no` — короткий номер участника из Б6 §6.3 (`#000123`), выдаётся при создании `pid`; в `columns` ниже её нет. YAML ниже перенесён дословно и не меняется. См. [../appendix/D-source-defects.md](../appendix/D-source-defects.md) (D-32) и [../build/miniapp-api-contract.yaml](../build/miniapp-api-contract.yaml) (`PidCreated`).

Проверка 4/15 (errata_backrefs_present): строка «> **Переопределено ERRATA-UNIFIED.**» остаётся
на месте; новая строка содержит «Уточнено».

**Файл 3: `architecture/appendix/D-source-defects.md`** — новый раздел перед
«## Что делать с реестром». Ctrl+F `## Что делать с реестром` → курсор в начало этой строки →
вставить блок (3 строки + пустая строка в конце, чтобы заголовок остался отдельным):

    ## Реализация course-bot (D-32)

    - **D-32.** `normative/I1-wave-a.md`, `tg_user_id_pid_registry.columns`: нет колонки `short_no`, хотя `PidCreated.short_no` есть в [../build/miniapp-api-contract.yaml](../build/miniapp-api-contract.yaml), а короткий номер `#000123` — в Б6 §6.3 (`assigned_at: registration`). Реализация (запись course-bot D-12) добавила `short_no` в `tg_user_registry` (`bigint GENERATED ALWAYS AS IDENTITY UNIQUE`, показ `#%06d`; пропуски номеров возможны — номер только для показа). YAML И1 не правится (правило переноса); врезка «Уточнено реализацией» — в шапке И1.

Проверка 14/15: уникальных ID D-01 – D-31 остаётся 31, D-32 — новый номер. Номера 01–31 как новые записи не использовать.

## 7. Контракт: правки 1.1–1.3. ## 8. БД: нет.

## 9. Проверки: `tools/checks.sh` зелёный (4/15, 9/15, 14/15 — см. выше).

## 10. Шаги Автора (сайт GitHub; до старта DOCS-b смержен)
Блоки «станет» копируй кнопкой копирования в правом верхнем углу блока на странице карточки в GitHub (не из Raw: там лишние 4 пробела в начале строк).
Шаг 1. Ты, браузер: открой
https://github.com/romanticstudent07-stack/DOCS-course-bot/blob/main/architecture/build/miniapp-api-contract.yaml
→ карандаш. Правки 1.1 и 1.2: Ctrl+F первой строки «было» → выдели блок → Ctrl+V «станет».
Правка 1.3: Ctrl+F `/miniapp/v1/onboarding/first-launch:` → Esc → клик в самое начало этой строки →
прокрути вниз (около 20 строк, второй Ctrl+F НЕ нажимать) → Shift+клик в конец строки
`"403": { description: "Возрастной гейт: < 18" }` → Ctrl+V «станет».
Строка `/miniapp/v1/onboarding/first-launch:` должна начинаться с 2 пробелов, `post:` — с 4.
Шаг 2. «Commit changes» → `contract: first-launch по реализации (course-bot D-12, D-10, D-9в)` →
«Create a new branch for this commit and start a pull request» → ветка
`agent/backend-first-launch-contract` → «Propose changes».
Шаг 3. Заголовок — из раздела 1, описание — блок ниже → «Create pull request».

    course-bot D-12, D-10, D-9 п.(в) (записи course-bot DEFECTS-*.md; в DOCS свой реестр, новая запись — D-32).
    Читались: build/miniapp-api-contract.yaml, normative/I1-wave-a.md (шапка, tg_user_id_pid_registry),
    normative/errata-unified.md (ADD3), appendix/D-source-defects.md.
    ERRATA: ADD3 (INV-AGE-GATE-BEFORE-PID, порядок age → consents → pid) — описан в first-launch.
    И1 YAML не изменён: врезка «Уточнено реализацией» в шапке + D-32 (правило переноса).
    429 — rate-limit /miniapp/v1 (course-bot B-1).
    Не решено и не описано как решённое: место оплаты (course-bot D-10), модель TTL (course-bot D-9).

Шаг 4. Ты, браузер:
https://github.com/romanticstudent07-stack/DOCS-course-bot/blob/agent/backend-first-launch-contract/architecture/normative/I1-wave-a.md
→ карандаш → вставка файла 2 → «Commit changes» → `I1: врезка «Уточнено реализацией» (course-bot D-12)`
→ «Commit directly to the agent/backend-first-launch-contract branch» → «Commit changes».
Шаг 5. Так же:
https://github.com/romanticstudent07-stack/DOCS-course-bot/blob/agent/backend-first-launch-contract/architecture/appendix/D-source-defects.md
→ вставка файла 3 → коммит `D-source-defects: D-32 short_no (course-bot D-12)` → в ту же ветку.
Шаг 6. `tools/checks.sh` зелёный (красный → «Details» → 60 строк лога → ШТАБ).
Шаг 7. `<адрес PR>.diff` → Ctrl+A, Ctrl+C → в ШТАБ (ШТАБ проверяет и отступы YAML).
Шаг 8. После «ок» ШТАБа: «Merge pull request» → «Create a merge commit» → «Confirm merge» →
«Delete branch» (безопасно). Номер PR — в ШТАБ.

## 11. Запреты
YAML И1 и `errata-unified.md` не трогать. Другие пути контракта и `securitySchemes` (TTL) не трогать.
Не писать решений по оплате и TTL. Тексты курса — нет.

## 12. Критерии готовности
Смержен; `tools/checks.sh` зелёный; в diff ровно 3 файла; отступы YAML совпадают с карточкой.

## 13. Оценка: около 0,4 ч, 0 кредитов. ## 14. РЕВЬЮЕР: нет (документ, кода нет).
