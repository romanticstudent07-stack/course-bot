# api-sup-1 — POST /miniapp/v1/support/question

## 1. Паспорт
- id: api-sup-1 (PLAN §5 п.13, Р-19). Заголовок PR: feat(api): POST /miniapp/v1/support/question — вопрос в поддержку (api-sup-1)
- Ветка: feat/api-sup-1. Режим: Агент Р1. РЕВЬЮЕР: да (ПДн в body; B-1 — своя частота рядом с rate_limit; B-3 — работа строго в правах 0017).
- Зависит от: db-sup-1 (миграция 0017, #215, уже в main). Миграций в задаче нет. Выкат: migrate → бот (bot-sup-1) → api → miniapp (docs/research/bot-i3-3.md §4 Б4: старый бот отправит support_question в DLQ).

## 2. Цель
Mini App отправляет вопрос участника: тема кнопкой и текст. API пишет строку в support_questions и строку outbox support_question в одной транзакции; пост в тему группы делает бот (bot-sup-1). В payload outbox нет текста: DLQ копирует payload целиком.

## 3. Решения Автора (дословно)
- Р-19 (13.11): «поддержка: кнопка «Помощь» — после 18+ и согласий, всегда внизу Mini App и пунктом «Меню»; экран: тема кнопкой → вопрос (черновик хранится) → пост в тему группы этой темы (подпись Р-15, «Карточка»). Тем 8: «Поддержка 1»…«Поддержка 7» и «Другое», у каждой своя тема группы; названия — заглушки, заменить до показа участникам курса.»
- Решение Р-19 «после 18+ и согласий» → нужен активный участник с действующими согласиями (404 / 409 ниже) [Автор против канона → DECISIONS Р-19].

## 4. Выдержки (КОДЕР и Агент канон не читают)
- docs/research/bot-i3-3.md §3 п.4 (с поправкой Р-19: тело {topic_code, text}): X-Client-Op-Id; initData → rate_limit → проверка текста → активный участник (нет → 404; reconsent → 409) → одна транзакция под active_pid_locked: частота → INSERT support_questions ON CONFLICT (pid, client_op_id) DO NOTHING RETURNING id → если вставлено, INSERT outbox → commit → 201. Повтор с тем же id → 201 без новой строки.
- §3 п.5: event_type support_question; aggregate_id str(pid); payload {"pid": str(pid), "question_id": id}; idempotency_keys и day_keys.TTL_BY_KIND не трогаем.
- §3 п.6: не чаще 1 вопроса в 30 с на pid (max(created_at) под замком), иначе 429 SUPPORT_TOO_FREQUENT + Retry-After; rate_limit не меняем.
- docs/tasks/db-sup-1.md §7–§8 (права app_api на support_questions): INSERT (pid, topic_code, body, client_op_id); SELECT (id, pid, client_op_id, created_at); USAGE support_questions_id_seq. SELECT body и topic_code у app_api НЕТ. Константы models.py: SUPPORT_TOPIC_CODES = ("s1", "s2", "s3", "s4", "s5", "s6", "s7", "other"); SUPPORT_BODY_MIN_LEN = 2; SUPPORT_BODY_MAX_LEN = 2000; SUPPORT_CLIENT_OP_ID_MAX_LEN = 64. CHECK body: «char_length(btrim(body)) >= 2 AND char_length(body) <= 2000».
- По коду: apps/api/app/notify_ops.py — _INSERT_OUTBOX (без RETURNING), параметры :aggregate_id, :event_type, :payload (строка json.dumps):
    INSERT INTO outbox (aggregate_id, event_type, payload, tx_id)
    VALUES (:aggregate_id, :event_type, CAST(:payload AS jsonb), pg_current_xact_id())
  Право app_api на INSERT outbox — миграция 0012_outbox_api (его использует reflection_submitted в day.py); в этом окне текст 0012 не открывался — сверяет ШТАБ.
- По коду: apps/api/app/errors.py — HTTPException с detail {"code", "message"} отдаётся как есть, вместе с exc.headers (Retry-After доходит до клиента); RequestValidationError → 422 VALIDATION_ERROR (только loc и type, без значений).

## 5. ЧТО ПРОЧИТАТЬ (по hash из промпта)
- AGENT-BRIEF.md 17,1; эта карточка ≈ 12.
- apps/api/app/routers/onboarding_form.py 16,5 — образец: POST + X-Client-Op-Id (UUID4), _error, _released, submit_form, 503 ветки, лог.
- apps/api/app/participant_lock.py 3,3; apps/api/main.py 6,0; apps/api/app/errors.py 3,3.
- apps/api/tests/test_onboarding_form_db.py 9,9 — образец тестов с БД (участник, reconsent, tombstone, initData); apps/api/tests/conftest.py 8,1 — фикстуры.
- notify_ops.py и models.py не читать: нужное — в разделе 4 (импорт по именам).
- Чтение Агента ≈ 76 КБ.

## 6. Файлы
- Создать: apps/api/app/routers/support.py (≈ 190 строк).
- Создать: apps/api/tests/test_support_db.py (≈ 280 строк).
- Изменить: apps/api/main.py — импорт support в «from app.routers import (…)», support.router последним аргументом build_miniapp_v1_router(…) в create_app, строка в докстринге после me/change-map:
    POST /miniapp/v1/support/question        — вопрос в поддержку (api-sup-1, Р-19): support_questions + outbox, X-Client-Op-Id

## 7. Контракт
POST /miniapp/v1/support/question. Заголовки: X-Telegram-Init-Data (роутер main.py), X-Client-Op-Id — UUID v4, обязателен (Annotated[UUID4, Header(alias=…)], как в onboarding_form.py).
Тело FormIn-модель SupportQuestionIn: topic_code: str (max_length 16), text: str. Лишние поля отбрасываются (pydantic по умолчанию). Номера темы группы в API нет.
Ответы:
- 201 {"status": "sent"} — и для новой строки, и для повтора того же X-Client-Op-Id.
- 401 TG_INIT_MISSING / TG_INIT_INVALID и 429 RATE_LIMITED — роутер main.py (не менять).
- 422 VALIDATION_ERROR — нет или не-v4 X-Client-Op-Id, нет поля, не строка.
- 422 SUPPORT_TOPIC_INVALID — topic_code не из SUPPORT_TOPIC_CODES (регистр важен: «S1» — ошибка) [ШТАБ-тех: отдельный код, клиент различает тему и текст].
- 422 SUPPORT_TEXT_INVALID — len(text.strip()) < 2, или len(text) > 2000, или в тексте «\x00» (Postgres text не принимает NUL → иначе было бы 503) [ШТАБ-тех].
- 404 PARTICIPANT_NOT_FOUND; 409 RECONSENT_REQUIRED — тексты и коды как в onboarding_form.py.
- 429 SUPPORT_TOO_FREQUENT + заголовок Retry-After (целое, 1…30).
- 503 SERVICE_MISCONFIGURED (нет текста согласия), 503 SERVICE_UNAVAILABLE (любая SQLAlchemyError, и на commit).
Сообщения ошибок (служебные, не тексты курса): SUPPORT_TOPIC_INVALID «Неизвестная тема.»; SUPPORT_TEXT_INVALID «Вопрос — от 2 до 2000 символов.»; SUPPORT_TOO_FREQUENT «Слишком часто. Подождите немного и отправьте снова.»
Порядок (по коду: onboarding_form.py, participant_lock.py; метка [ШТАБ-тех] где отмечено):
0. FastAPI: зависимости роутера (initData → rate_limit) раньше разбора заголовка и тела → 401 раньше 422.
1. До БД: topic → 422 SUPPORT_TOPIC_INVALID; затем text → 422 SUPPORT_TEXT_INVALID. body = text.strip() (Python strip режет больше, чем btrim Postgres → CHECK не сработает) [ШТАБ-тех].
2. Одна транзакция: pid = active_pid_locked(session, tg_user_id) → None → 404 (через _released).
3. current_texts(session, STATUS_KINDS) → ConsentTextMissingError → 503 SERVICE_MISCONFIGURED; reasons(load_events(session, pid), texts, STATUS_KINDS) не пусто → 409 RECONSENT_REQUIRED. Как в submit_form шаг 2.
4. Повтор [ШТАБ-тех: раньше частоты, иначе повтор в первые 30 с получил бы 429]: _SELECT_OP_SQL «SELECT id FROM support_questions WHERE pid = :pid AND client_op_id = :op» → есть → commit, 201, outbox не пишется. Тело повтора с новой темой или текстом не сравнивается (SELECT body у app_api нет) — это нормально.
5. Частота: _FREQ_SQL «SELECT max(created_at) AS last, now() AS now FROM support_questions WHERE pid = :pid» (время БД, не часы api). last не NULL и now − last < SUPPORT_MIN_INTERVAL_S = 30 → 429, Retry-After = max(1, ceil(30 − elapsed)).
6. _INSERT_SQL — буква в букву db-sup-1 §7: INSERT … (pid, topic_code, body, client_op_id) VALUES (:pid, :topic, :body, :op) ON CONFLICT (pid, client_op_id) DO NOTHING RETURNING id. None (гонка, которую замок уже исключил) → commit, 201 как повтор.
7. session.execute(_INSERT_OUTBOX, {"aggregate_id": str(pid), "event_type": "support_question", "payload": json.dumps({"pid": str(pid), "question_id": id})}). Импорт: «from app.notify_ops import _INSERT_OUTBOX» на уровне модуля (циклов нет: notify_ops не импортирует роутеры).
8. commit → 201. Строка и outbox — обе или ни одной.
Константы модуля: EVENT_TYPE = "support_question"; SUPPORT_MIN_INTERVAL_S = 30; CLIENT_OP_ID_HEADER = "X-Client-Op-Id". Модуль не пишет idempotency_keys, day_keys, participant_events, participant_state.
Лог (logger "app.support"): INFO только tg_user_id и status (created / repeat / код ошибки). Нет pid, op_id, topic_code, текста; ошибки БД — имя класса.
Докстринг support.py — порядок 0–8, права app_api, «текста в outbox нет».

## 8. БД
Миграций нет. Только права 0017 (раздел 4) и INSERT outbox (0012). Новых GRANT нет.

## 9. Тесты — apps/api/tests/test_support_db.py (tg_user_id 4301–4399; БД-маркеры, фикстуры, создание участника, reconsent и tombstone — как в test_onboarding_form_db.py)
- t1 маршрут в main.app: POST /miniapp/v1/support/question есть; без initData → 401 TG_INIT_MISSING.
- t2 422 VALIDATION_ERROR: без X-Client-Op-Id; X-Client-Op-Id не v4; нет text; text — число.
- t3 422 SUPPORT_TOPIC_INVALID: «s0», «s8», «S1», «», «other » (пробел). Строки в БД нет.
- t4 422 SUPPORT_TEXT_INVALID: «a», «   a   », «\n\na», 2001×«x», «ab\x00». Строки в БД нет.
- t5 201 новая: {"status": "sent"}; под владельцем: строка с topic_code, body = strip(text), client_op_id = str(op); в outbox ровно 1 строка event_type support_question, aggregate_id = str(pid), payload == {"pid": str(pid), "question_id": id}; текста вопроса нет в json payload.
- t6 приём: «ab», 2000×«я», topic «other» и «s7» (между вызовами сдвигать created_at владельцем на −31 с).
- t7 повтор того же op сразу → 201, строк 1, outbox 1.
- t8 частота: второй op сразу → 429 SUPPORT_TOO_FREQUENT, Retry-After — целое 1…30; строк 1. Сдвиг created_at на −31 с → 201, строк 2.
- t9 404 PARTICIPANT_NOT_FOUND: нет участника; участник tombstoned.
- t10 409 RECONSENT_REQUIRED (как в образце); строк и outbox нет.
- t11 откат: monkeypatch support._INSERT_OUTBOX на text("SELECT 1/0") → 503 SERVICE_UNAVAILABLE; строки в support_questions нет.
- t12 лог (caplog "app.support"): нет текста вопроса, pid, op_id, topic_code.
- t13 статика: SUPPORT_MIN_INTERVAL_S == 30; EVENT_TYPE == "support_question"; модуль импортирует SUPPORT_TOPIC_CODES из app.db.models (не копия списка).
Цели: bash tools/check.sh api. Только CI: тесты с БД (REQUIRE_DB_TESTS=1).

## 10. Задетые тесты (правило «Т»)
Не ожидается. Где искал (@b8d5d67): список apps/api/tests/ (jsdelivr, все имена файлов) — файлов про OpenAPI или список маршрутов нет; test_api.py — только отдельные маршруты (healthz, first-launch, csp-report); test_rate_limit.py — свой ping-роутер и main.app по /healthz и /texts, полного списка маршрутов нет. Общего списка event_type outbox в api нет: типы — константы модулей (notify_ops, notify_ladder, day.py); test_notify_*.py по именам проверяют свои модули (не открывались). Не проверено: тесты packages/shared и miniapp на контракт. Упал тест вне списка → не чинить, «тест X вне списка» в ИТОГ, стоп.

## 11. Живые проверки (при выкате, PLAN §4; после bot-sup-1)
- curl без initData: POST /miniapp/v1/support/question → 401. Вопрос с Mini App тестового участника → 201; в БД: строка support_questions, outbox support_question с payload без текста; повтор за 30 с → 429.
- Логи api: нет текста вопроса.

## 12. Запреты
- AGENT-BRIEF §3. Не менять rate_limit, main.build_miniapp_v1_router, notify_ops.py, models.py, миграции, права.
- Не писать idempotency_keys, day_keys, participant_events, participant_state. Не класть текст или topic_code в outbox. Не читать body из БД (прав нет).
- Не логировать текст вопроса, pid, op_id.

## 13. Критерии готовности
Файлы раздела 6; тесты раздела 9; check.sh api зелёный; в PR — «Прочитано» и таблица проверок. Тесты с БД — в CI, смотрит Автор.

## 14. Оценка
Часы Автора ≈ 0,3. Кредиты ≈ 475 строк × 0,75–1,0 + 0 файлов «Задетых» = 355–475.

## Канон и решения
(а) build/miniapp-api-contract.yaml — маршрута нет (указание ШТАБа; тело контракта в этом окне не читалось); 04-onboarding §4.6 — через исследование §1; DECISIONS Р-19.
(б) 04 §4.6 (механика поддержки) перекрыт Р-19 — правка 1 исследования §8 (в), идёт перед bot-sup-1 и miniapp-sup-1, не здесь. Контракту задача не противоречит, а дополняет его.
(в) Правка DOCS (маленький PR и sync ДО промпта Агенту):
architecture/build/miniapp-api-contract.yaml · найди: НАДО ДОЧИТАТЬ (последний маршрут в paths, имя схемы ошибки — по errors.py «components.schemas.Error», есть ли общий параметр X-Client-Op-Id в components) · вставь после него (отступы — по соседям):
    /miniapp/v1/support/question:
      post:
        summary: Вопрос в поддержку (Р-19, api-sup-1)
        parameters:
          - name: X-Client-Op-Id
            in: header
            required: true
            schema: {type: string, format: uuid}
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required: [topic_code, text]
                properties:
                  topic_code: {type: string, enum: [s1, s2, s3, s4, s5, s6, s7, other]}
                  text: {type: string, minLength: 2, maxLength: 2000}
        responses:
          '201': {description: sent — новая строка или повтор X-Client-Op-Id}
          '401': {description: TG_INIT_MISSING / TG_INIT_INVALID}
          '404': {description: PARTICIPANT_NOT_FOUND}
          '409': {description: RECONSENT_REQUIRED}
          '422': {description: VALIDATION_ERROR / SUPPORT_TOPIC_INVALID / SUPPORT_TEXT_INVALID}
          '429': {description: RATE_LIMITED / SUPPORT_TOO_FREQUENT, заголовок Retry-After}
          '503': {description: SERVICE_UNAVAILABLE / SERVICE_MISCONFIGURED}
Метки: тело и коды — [ШТАБ-тех] по исследованию §3 и Р-19; «Тем 8» → enum — [Автор против канона → DECISIONS Р-19].
