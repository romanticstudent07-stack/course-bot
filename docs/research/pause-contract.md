# ИССЛЕДОВАНИЕ pause-contract — раздел /pause/* для miniapp-api-contract.yaml
Hash: 062eabd9b2226a8fc38ec08b9edb7caaa2c3c11d · ИССЛЕДОВАНИЕ · 22.11.2026. Факты — pause.py @062eabd (префикс и initData — main.py; pause.py:3,82). Контекст ШТАБа принят: /pause/* в контракте нет.

## 1. Код: 4 маршрута

### GET /pause (pause.py:585-593)
- Заголовки: X-Telegram-Init-Data (pause.py:587); op-id и тела нет.
- 200 PauseStatusOut (pause.py:179-186): budget_days_left, budget_days_total int; cycle_ends_at datetime|null; pause PauseOut|null; can_request bool; refusal str|null. PauseOut (pause.py:172-176): id, status, start_at, planned_end_at (UTC, pause.py:262-272).
- refusal (pause.py:366-371): строка kind user открыта/активна → "already_open" (pause.py:86, только GET); иначе start_refusal("approved", days=1, start_at = следующая 00:00 по поясу).
- Ошибки: 404 PARTICIPANT_NOT_FOUND (pause.py:208-211, 361); 429 RATE_LIMITED + Retry-After (pause.py:580); 503 SERVICE_UNAVAILABLE — любая SQLAlchemyError, вкл. commit (pause.py:570-573).

### POST /pause/request (pause.py:596-628)
- Заголовки: initData; X-Client-Op-Id ОБЯЗАТЕЛЕН (pause.py:612; строка — pause.py:85), UUID4 — не-v4 → 422 (pause.py:611-612).
- Тело PauseRequestIn (pause.py:166-169), оба обязательны: days int 1..7 (pause_rules.py:30); start_date date — местная дата участника.
- 201 {"pause": PauseOut} — «created» и «repeat» (pause.py:188-189, 402-403, 454-456); строка (pid, op) без ключа → 201 без аудита (pause.py:344-345).
- Ошибки: 404 (pause.py:394-395); 409 PAUSE_ALREADY_OPEN (pause.py:222-223) — строка открыта/активна (406-407) или IntegrityError participant_pauses_one_open_user_uq (428-431); 409 PAUSE_REFUSED + details.reason (pause.py:234-237): "start_date_passed" (pause.py:87, 413-415 — серверная дата start_at ≠ start_date, ничего не пишется) и REFUSAL_REASONS (pause_rules.py:47-52): "not_approved", "block_lives", "state", "gap_24h", "stage_taken", "no_budget" (raise 419-421); 409 IDEMPOTENCY_CONFLICT (pause.py:240-245) — доказанная коллизия op-id: ключ pause_request:{pid}:{op} есть, params_hash ≠ sha256({days, start_date}) (pause.py:325-332, 335-342), rollback → record_security_event client_op_id_conflict в security_events (отдельная транзакция, INSERT) → 409 при любом итоге аудита (pause.py:547-562); 422 VALIDATION_ERROR (pause.py:606); 429; 503 — вкл. конфликт ключа, INSERT без ON CONFLICT (pause.py:141, 440-450).

### POST /pause/cancel (pause.py:631-644)
- Только initData; op-id и тела нет (pause-api-a2.md §2). 202 {"status": "accepted"} (pause.py:192-193, 644) — «accepted» и «repeat».
- Ошибки: 404; 409 PAUSE_NOT_CANCELLABLE (pause.py:226-227) — нет строки kind user в requested/approved ИЛИ ключ pause_start (pause.py:517-518, 483-484); 429; 503.
- Успех: INSERT ключа pause_cancel; пусто → 202 без события; иначе событие pause_cancel {"pause_id"} (pause.py:486-508).

### POST /pause/resume (pause.py:647-660)
- Как cancel. Ошибки: 404; 409 PAUSE_NOT_ACTIVE (pause.py:230-231) — нет строки в active ИЛИ ключ pause_end есть; 429; 503.
- Успех: событие pause_ended {"pause_id", "reason": "by_participant"} (pause.py:94-95, 537).

## 2. Сверка с каноном

| Поле/код | Канон § | Итог |
|---|---|---|
| days 1..7, бюджет 14, ≥24 ч (pause_rules.py:29-31) | И2 §user_pause; Р-6а | совпадает |
| op-id обязателен на request (pause.py:612) | И2 §activation client_op_id_required: true | совпадает |
| op-id нет на cancel/resume (pause.py:631-660) | И2 §removal.by_participant | молчит |
| start_date, отказ без сдвига (pause.py:169, 413-415) | R-2026-11-21 «Поздняя доставка: форма»; И2/И4 полей нет | совпадает; молчит |
| 409 PAUSE_REFUSED start_date_passed (pause.py:87, 415) | R-2026-11-21, там же | совпадает |
| 409 IDEMPOTENCY_CONFLICT + аудит (pause.py:547-562) | И2 §behavior_on_collision; И4 §R339.conflict_ux; OVERRIDES §AD-01; R-2026-11-21 | совпадает |
| Бизнес-409 без аудита (pause.py:38) | OVERRIDES §AD-01 business_refusal — коды дословно | совпадает |
| Повтор тех же параметров → 201 (pause.py:399-403) | И2 «same_result: return cached result_ref» | совпадает |
| TTL pause_request 3650 days (pause.py:446) | И2 §ttl_by_kind default: 1h | расходится; уже в pause-api-a2 «Для ШТАБА» |
| Тело ошибки {code, message, details} (pause.py:199-205) | contract.yaml:41-47 Error | совпадает |
| Заголовок UUID4, не-v4 → 422 (pause.py:611-612) | contract.yaml:36-38 ClientOpId format uuid | расходится: код требует v4 |
| Статусы PauseOut (pause.py:90-92, 103-107) | И2 не задаёт перечень | молчит |

## 3. Стиль контракта (contract.yaml @062eabd)
- Общие: schemas.Error (:41-47); responses Unauthorized (:85), Conflict (:90), RateLimited (:95), ServiceUnavailable (:97).
- X-Client-Op-Id — inline-параметр (:230, 266, 290, 321); headers.ClientOpId (:36-38) в путях не применялся. Схемы — inline (как :309, :339); PauseOut — в components (как PidCreated). Место вставки: между «Дневной модуль» (:282) и «Чек-Ап» (:293) — ШТАБ.

## 4. Готовый YAML-блок (только факты кода и решений Автора)

    # ---------------- Паузы (Р-6а, Р-20; R-2026-11-21; course-bot pause-api-a1/a2) ----------------
    /miniapp/v1/pause:
      get:
        summary: "Бюджет пауз и текущая пауза (только чтение)"
        description: "Бюджет — 14 дней на годовой цикл (Р-6а), без записи. refusal: открытая/активная строка kind user → already_open; иначе причина start_refusal."
        responses:
          "200":
            description: "Состояние"
            content:
              application/json:
                schema:
                  type: object
                  required: [budget_days_left, budget_days_total, cycle_ends_at, pause, can_request, refusal]
                  properties: { budget_days_left: { type: integer, minimum: 0 }, budget_days_total: { type: integer }, cycle_ends_at: { type: [string, "null"], format: date-time }, pause: { $ref: "#/components/schemas/PauseOut", nullable: true }, can_request: { type: boolean }, refusal: { type: [string, "null"], enum: [already_open, not_approved, block_lives, state, gap_24h, stage_taken, no_budget] } }
          "401": { $ref: "#/components/responses/Unauthorized" }
          "404": { description: "PARTICIPANT_NOT_FOUND", content: { application/json: { schema: { $ref: "#/components/schemas/Error" } } } }
          "429": { $ref: "#/components/responses/RateLimited" }
          "503": { $ref: "#/components/responses/ServiceUnavailable" }

    /miniapp/v1/pause/request:
      post:
        summary: "Заявка на паузу «с завтра» на 1..7 дней"
        description: |
          Под замком participant:pid, одна транзакция; start_at — следующая 00:00 по поясу,
          planned_end_at — 00:00 местной даты старта + days.
          start_date — местная дата участника (R-2026-11-21): не совпала с серверной →
          409 PAUSE_REFUSED reason start_date_passed, ничего не пишется.
          Идемпотентность: ключ pause_request:{pid}:{op}, сверка params_hash(days, start_date):
          тот же op и параметры → 201 с прежней строкой; другие → 409 IDEMPOTENCY_CONFLICT
          + client_op_id_conflict в security_events (отдельная транзакция). Бизнес-409 —
          без аудита (OVERRIDES AD-01).
        parameters:
          - { in: header, name: X-Client-Op-Id, required: true, description: "UUID v4 — не-v4 → 422 (по коду pause.py)", schema: { type: string, format: uuid } }
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required: [days, start_date]
                properties:
                  days: { type: integer, minimum: 1, maximum: 7 }
                  start_date: { type: string, format: date, description: "местная дата, YYYY-MM-DD" }
        responses:
          "201": { description: "Создана или повтор", content: { application/json: { schema: { type: object, required: [pause], properties: { pause: { $ref: "#/components/schemas/PauseOut" } } } } } }
          "401": { $ref: "#/components/responses/Unauthorized" }
          "404": { description: "PARTICIPANT_NOT_FOUND", content: { application/json: { schema: { $ref: "#/components/schemas/Error" } } } }
          "409":
            description: "PAUSE_ALREADY_OPEN; PAUSE_REFUSED (details.reason: not_approved, block_lives, state, gap_24h, stage_taken, no_budget, start_date_passed); IDEMPOTENCY_CONFLICT."
            content:
              application/json:
                schema: { $ref: "#/components/schemas/Error" }
          "422": { description: "VALIDATION_ERROR (нет поля, не дата, days вне 1..7, op-id не UUID4)", content: { application/json: { schema: { $ref: "#/components/schemas/Error" } } } }
          "429": { $ref: "#/components/responses/RateLimited" }
          "503": { $ref: "#/components/responses/ServiceUnavailable" }

    /miniapp/v1/pause/cancel:
      post:
        summary: "Отмена заявки на паузу до старта (op-id нет, тела нет)"
        description: "Строка kind user в requested/approved, часы не созданы → событие pause_cancel {pause_id}; повтор → тот же 202 без события."
        responses:
          "202": { description: "Принято или повтор" }
          "401": { $ref: "#/components/responses/Unauthorized" }
          "404": { description: "PARTICIPANT_NOT_FOUND", content: { application/json: { schema: { $ref: "#/components/schemas/Error" } } } }
          "409": { description: "PAUSE_NOT_CANCELLABLE", content: { application/json: { schema: { $ref: "#/components/schemas/Error" } } } }
          "429": { $ref: "#/components/responses/RateLimited" }
          "503": { $ref: "#/components/responses/ServiceUnavailable" }

    /miniapp/v1/pause/resume:
      post:
        summary: "Досрочный выход из активной паузы (op-id нет, тела нет)"
        description: "Событие pause_ended {pause_id, reason: by_participant}; повтор → тот же 202."
        responses:
          "202": { description: "Принято или повтор" }
          "401": { $ref: "#/components/responses/Unauthorized" }
          "404": { description: "PARTICIPANT_NOT_FOUND", content: { application/json: { schema: { $ref: "#/components/schemas/Error" } } } }
          "409": { description: "PAUSE_NOT_ACTIVE", content: { application/json: { schema: { $ref: "#/components/schemas/Error" } } } }
          "429": { $ref: "#/components/responses/RateLimited" }
          "503": { $ref: "#/components/responses/ServiceUnavailable" }

    # в components/schemas добавить:
    PauseOut:
      type: object
      required: [id, status, start_at, planned_end_at]
      properties:
        id: { type: integer }
        status: { type: string, enum: [requested, approved, active, ended], description: "пишется как requested; остальные из БД" }
        start_at: { type: string, format: date-time }
        planned_end_at: { type: string, format: date-time }

## 5. Вопросы ШТАБу (не К-4)
1. TTL pause_request 3650 days против И2 §ttl_by_kind default: 1h — уже в pause-api-a2 «Для ШТАБА»; в YAML не выписан.
2. headers.ClientOpId (:36-38) — uuid без версии; код требует UUID4 (в YAML-блоке — в описании параметра). Править ли компонент — ШТАБ.
3. Enum статусов PauseOut — канон молчит; оставить enum или снять.
4. Место раздела — предложение в §3.

## 6. Вопросы Автору — по К-4
Нет. Канон: проверено И2 §user_pause, §idempotency_keys; И4 §R339.conflict_ux, §R380_cleanup; OVERRIDES §AD-01/AD-02; R-2026-11-21 (все разделы) — лимиты, op-id, start_date, 409-коды и носитель аудита покрыты решениями; противоречий, кроме TTL (п.1 ШТАБу), нет.

## Прочитано
- DESIGNER.md 21 971 Б — правила исследования. · PACK.md 12 747 Б — метка конца есть.
- CANON-CHECK.md 4 856 Б — К-4. · STATE.md 17 312 Б — A1 #284, A2 #286 смержены; дальше DOCS → T5-B.
- AGENT-BRIEF.md 17 110 Б — запреты, состав API. · DECISIONS.md 7 809 Б — Р-6а: 7/14/≥24 ч. · DOCS-CANON.md 5 163 Б — цикл правки канона.
- R-2026-11-21.md 7 034 Б — Q1–Q3, security_events, start_date.
- miniapp-api-contract.yaml 27 908 Б — /pause/* нет. · routers/pause.py 26 915 Б — 4 маршрута, коды (раздел 1).
- docs/tasks/pause-api-a2.md 18 146 Б — start_date, params_hash; «Для ШТАБА» — TTL.
- I4-wave-d.md 60 986 Б; grep -c -i "pause" → 7; grep -n -i "pause" | grep -i "R339|R380|##|pause_" → 4; grep -n "R339|R380" → 6 (фильтр вывода — сверх списка). R339 (:590-605), R380 (:607-613), AD (:34, :36).
- I2-wave-b.md 40 437 Б; grep -c -i "pause" → 36; grep -n -i "user_pause_quota|idempotency_keys" → 6. pause_semantics (:377-421), idempotency_keys (:481-494).
- OVERRIDES.yaml 12 618 Б; grep -n "AD-01|AD-02" → 6. AD-01 (:145-168), AD-02 (:169-206).
- pause_rules.py 7 191 Б (сверх списка, по необходимости) — BUDGET_DAYS 14 (:29), MAX_DAYS 7 (:30), MIN_GAP 24 ч (:31), REFUSAL_REASONS 6 причин (:47).
- test_pause_api_db.py 18 864 Б; grep -o кодов → 12 уникальных строк (PAUSE_REFUSED, PAUSE_ALREADY_OPEN ×3, PAUSE_NOT_CANCELLABLE ×2, PAUSE_NOT_ACTIVE ×2, IDEMPOTENCY_CONFLICT ×3, PARTICIPANT_NOT_FOUND, SERVICE_UNAVAILABLE, start_date_passed, already_open ×2) — коды подтверждены.

Чтение ≈ 182 КБ, лимит 200 000.
