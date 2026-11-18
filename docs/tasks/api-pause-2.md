# api-pause-2 — T3: эндпоинты паузы для Mini App и чтение бюджета (Р-6а)
Hash main: b6cee31 · Область: API · Одна карточка. Оценка 1 600 кредитов, стоп 2 400. РЕВЬЮЕР: да (§14).
Правило К — docs/process/CANON-CHECK.md. Сначала прочитай docs/decisions/DECISIONS.md целиком.
Миграция: не нужна (права — §3). Контракт T3/T4 — docs/tasks/api-pause-1a.md §5 (нормативный; выдержка — §4).
Источник: api-pause-1a §2, §5; docs/research/pause-2.md §2; ответы ШТАБа З2 (п.1–6) этого окна.

## 1. Зачем
Участник в Mini App берёт паузу курса (с завтра, 1–7 дней), отменяет заявку до старта, выходит досрочно
(«Продолжить») и видит остаток бюджета дней за годовой цикл. API пишет только строку заявки и события;
статус паузы, флаг, бюджет и позицию меняет проектор v8; старт и конец по сроку — часы pause_ops (T2b, в main).

## 2. Решения (метка К-6)
- Д1 Новый app/routers/pause.py, подключить в main.py через build_miniapp_v1_router: initData → общий
  rate_limit; своих лимитов нет. [ШТАБ-тех; по коду main.py, rate_limit.py]
- Д2 GET /miniapp/v1/pause; POST /miniapp/v1/pause/request, /pause/cancel, /pause/resume.
  [канон: I2 user_pause.activation mini_app — pause-2 §2; ШТАБ-тех]
- Д3 «С завтра»: start_at = day_clock.next_midnight(now, tz); planned_end_at = 00:00 местной даты
  (start + N); проверка pause_rules.pause_days; N 1..7. [канон 02 П.1, I2 7d; api-pause-1a Р3]
- Д4 Проверка заявки — pause_rules.start_refusal с status = "approved" (одобрения ещё нет; причину
  not_approved API не применяет); порядок причин — REFUSAL_REASONS. [api-pause-1a §5; ШТАБ-тех]
- Д5 Бюджет — pause_rules.roll_cycle(cycle_start_at, days_left, now, tz) только для расчёта, без записи;
  строки pause_budgets нет → остаток BUDGET_DAYS, restart_no 0, cycle_ends_at null. [api-pause-1a Р8, Р9, Р12]
- Д6 Идемпотентность заявки — заголовок X-Client-Op-Id (UUID4) и UNIQUE (pid, client_op_id) из 0018;
  повтор проверяется раньше всех проверок. [канон I2 client_op_id — pause-2 §2; образец support.py]
- Д7 Идемпотентность cancel/resume — ключи idempotency_keys pause_cancel:{pid}:{pause_id} и
  pause_resume:{pid}:{pause_id}, TTL "3650 days"; ключ и событие — одна транзакция, один commit;
  ключ уже есть → 202 без нового события. Заголовка op у cancel/resume нет. [ШТАБ-тех, З2 п.1]
- Д8 Гонка с часами — под замком active_pid_locked: cancel при ключе day_keys.key_pause_start(pid, id)
  → 409 PAUSE_NOT_CANCELLABLE; resume при ключе day_keys.key_pause_end(pid, id) → 409 PAUSE_NOT_ACTIVE.
  Часы пишут ключ и событие одним commit под тем же замком — окна гонки нет. life_ops._PENDING_EVENT
  не использовать: у app_api нет прав на participant_events.pid и checkpoints. [ШТАБ-тех, З2 п.2]
- Д9 now — зависимость FastAPI get_now() → day_clock.utcnow(); тесты подставляют своё время. [ШТАБ-тех, З2 п.6]
- Д10 C0/C1 (RECONSENT_REQUIRED) не проверяем: пауза — не новые ПДн; сверка с day.py — долг ШТАБа к T5.
  [ШТАБ-тех, З2 п.5]

## 3. Права app_api (проверено ШТАБом по коду b6cee31; миграции не открывать)
- 0018: participant_pauses — INSERT (pid, kind, status, start_at, planned_end_at, client_op_id),
  SELECT всех колонок, USAGE participant_pauses_id_seq; pause_budgets — SELECT. UPDATE и DELETE нет.
- 0006: participant_events — INSERT, SELECT (id), USAGE participant_events_id_seq (RETURNING id работает).
- 0007: idempotency_keys — SELECT, INSERT.
- participant_state — SELECT колонок из выписки §5.3 (сверяет ШТАБ вместе с выпиской).

## 4. Контракт (выдержка api-pause-1a §5 и решения З2)
Ошибки — формат errors.py {code, message, details?}. Общие: 401 initData; 404 PARTICIPANT_NOT_FOUND
(active_pid_locked → None); 422 VALIDATION_ERROR; 429 RATE_LIMITED; 503 SERVICE_UNAVAILABLE — любая
SQLAlchemyError, в том числе на commit: rollback, в лог только имя класса (как support.py).
GET /pause → 200, ничего не пишет, замок не берёт:
    {"budget_days_left": int, "budget_days_total": 14, "cycle_ends_at": "iso" | null,
     "pause": null | {"id": int, "status": str, "start_at": "iso", "planned_end_at": "iso"},
     "can_request": bool, "refusal": null | str}
- pause — строка kind user в статусе requested / approved / active (индексы 0018: не больше одной), иначе null.
- cycle_ends_at — pause_rules.anniversary(cycle_start после roll_cycle, tz); строки бюджета нет → null.
- refusal: есть открытая или активная строка → "already_open" (только в GET); иначе
  start_refusal(days = 1, start_at = завтра 00:00); None → can_request true.
POST /pause/request — X-Client-Op-Id (UUID4, не-v4 → 422), тело {"days": 1..7} (вне диапазона → 422,
лишние поля отбрасываются) → 201 {"pause": объект как в GET}:
  1) active_pid_locked;
  2) строка (pid, op) есть → commit, 201 с ней (тело повтора не сравнивается);
  3) открытая или активная строка → 409 PAUSE_ALREADY_OPEN;
  4) start_at и planned_end_at по Д3;
  5) состояние §5.3, бюджет §5.1, stage_taken и last_ended_at §5.2 → start_refusal;
     причина → 409 PAUSE_REFUSED, details {"reason": одна из REFUSAL_REASONS};
  6) INSERT ON CONFLICT DO NOTHING RETURNING id; IntegrityError (индекс one_open_user) → rollback,
     409 PAUSE_ALREADY_OPEN; RETURNING пусто → как повтор (шаг 2);
  7) commit → 201.
POST /pause/cancel, без тела → 202 {"status": "accepted"}:
  active_pid_locked; строка kind user в статусе requested / approved — нет → 409 PAUSE_NOT_CANCELLABLE;
  ключ pause_start этой паузы есть → 409 PAUSE_NOT_CANCELLABLE; INSERT ключа pause_cancel ON CONFLICT
  DO NOTHING RETURNING key; пусто → commit, 202 без события; иначе событие pause_cancel
  {"pause_id"} → commit → 202.
POST /pause/resume, без тела → 202 {"status": "accepted"}: то же для статуса active (нет → 409
  PAUSE_NOT_ACTIVE), ключ часов — pause_end, свой ключ — pause_resume, событие pause_ended
  {"pause_id", "reason": "by_participant"}.
Проектор применяет события асинхронно: итоговый статус Mini App перечитывает через GET /pause. Повтор
cancel/resume после того, как проектор применил событие (строки в нужном статусе уже нет) → 409; это норма.

## 5. SQL (сырой text(), как в support.py)
5.1 Бюджет (0018):
    SELECT days_budget_remaining_annual, cycle_start_at, restart_no
    FROM pause_budgets WHERE pid = :pid
5.2 Паузы (колонки и индексы 0018; ШТАБ сверяет stage_taken и last_ended_at с pause_ops.py):
    SELECT id, status, start_at, planned_end_at FROM participant_pauses
    WHERE pid = :pid AND kind = 'user' AND status IN ('requested', 'approved', 'active')
    SELECT id, status, start_at, planned_end_at FROM participant_pauses
    WHERE pid = :pid AND client_op_id = :op
    SELECT 1 FROM participant_pauses WHERE pid = :pid AND kind = 'user'
    AND status IN ('active', 'ended') AND stage_no = :stage AND restart_no = :restart
    SELECT max(ended_at) AS last FROM participant_pauses
    WHERE pid = :pid AND kind = 'user' AND status = 'ended'
    INSERT INTO participant_pauses (pid, kind, status, start_at, planned_end_at, client_op_id)
    VALUES (:pid, 'user', 'requested', :start, :end, :op)
    ON CONFLICT (pid, client_op_id) DO NOTHING RETURNING id
  restart для stage_taken — restart_no из pause_budgets; строки нет → 0.
5.3 ВЫПИСКА ШТАБА (вставить до промпта, без неё промпт не давать): SELECT состояния, который часы
  pause_ops.py передают в start_refusal (flags, phase, day_no, этап позиции, tz), и форма INSERT
  participant_events (колонки, приведение payload, actor, actor_role, at) для событий от участника.
5.4 Ключи:
    SELECT 1 FROM idempotency_keys WHERE key = :key
    INSERT INTO idempotency_keys (key, kind, result_ref) VALUES (:key, :kind, :ref)
    ON CONFLICT (key) DO NOTHING RETURNING key
  result_ref = str(pause_id); payload события — json.dumps({"pause_id": id, ...}).

## 6. Файлы
- новый apps/api/app/routers/pause.py — docstring: порядок шагов §4, права §3, лог;
- apps/api/main.py — импорт pause, pause.router в build_miniapp_v1_router, 4 строки маршрутов в docstring;
- apps/api/app/day_keys.py — KIND_PAUSE_CANCEL = "pause_cancel", KIND_PAUSE_RESUME = "pause_resume",
  TTL_PAUSE_CANCEL и TTL_PAUSE_RESUME = "3650 days", key_pause_cancel и key_pause_resume по образцу
  key_pause_start, обе записи в TTL_BY_KIND, строки в docstring;
- новые тесты §8; правка §7.
pause_rules.py, projector.py, pause_ops.py и миграции не менять. Лог app.pause: INFO только
tg_user_id и итог (created / repeat / accepted / код ошибки); pid, pause_id, op и tz в логе нет.

## 7. Задетые тесты
- apps/api/tests/test_day_current.py::test_kinds_and_ttl (≈ стр. 84) сверяет TTL_BY_KIND целиком:
  добавить в ожидание "pause_cancel": "3650 days" и "pause_resume": "3650 days".
Других сверок целиком нет (ШТАБ З2 по дереву b6cee31: тестов OpenAPI и сверки packages/shared нет;
test_api.py и test_rate_limit.py списков маршрутов не сверяют). Тест вне списка упал → не чинить,
в ИТОГ «тест X вне списка», стоп.

## 8. Тесты (новые)
- tests/test_pause_api.py, без БД: 401 без initData на всех 4 маршрутах; 422 на days 0, 8, "x";
  422 без X-Client-Op-Id и на UUID не v4; формат key_pause_cancel и key_pause_resume.
- tests/test_pause_api_db.py, с БД (CI), фикстуры по образцу test_support_db.py, now через get_now:
  request → 201, границы — 00:00 по поясу, kind user, status requested; повтор того же op → 201, та же
  строка, строк 1; другой op при открытой → 409 PAUSE_ALREADY_OPEN; по причине на тест: block_lives,
  state, gap_24h, stage_taken, no_budget → 409 PAUSE_REFUSED с этим reason; нет участника → 404;
  GET: без строки бюджета → 14, cycle_ends_at null; годовщина в прошлом → 14, строка бюджета не
  изменилась; открытая заявка → refusal already_open, can_request false;
  cancel: requested → 202 и одно событие pause_cancel; повтор → 202, событий 1; ключ pause_start есть
  → 409; открытой нет → 409;
  resume: active → 202 и pause_ended by_participant; повтор → 202 без второго события; ключ pause_end
  → 409; не active → 409;
  ошибка БД → 503; pid и op в логе нет.

## 9. ЧТО ПРОЧИТАТЬ (Агент; вне списка ничего не искать, docs/architecture/** не открывать)
AGENT-BRIEF.md 17,1; docs/decisions/DECISIONS.md 7,7; эта карточка ≈ 13; apps/api/app/pause_rules.py 7,2;
apps/api/migrations/versions/2026_11_16_1200-0018_pauses_pauses.py 14,5; apps/api/app/routers/support.py 11,2;
apps/api/app/participant_lock.py 3,3; apps/api/main.py 6,1; apps/api/app/errors.py 3,3;
apps/api/app/day_keys.py 6,6; apps/api/app/day_clock.py 11,8; apps/api/tests/conftest.py 8,1;
apps/api/tests/test_day_current.py 11,7; apps/api/tests/test_support_db.py 10,0. Итого ≈ 131,6 КБ.
Модели (app/db/models.py) не нужны — сырой SQL. Миграции 0006 и 0007 не нужны — вывод в §3.
Замок — participant_lock.active_pid_locked (в списке). pause_ops.py не нужен — выписка в §5.

## 10. Готово, когда
CI зелёный; 4 маршрута под initData и rate_limit; в participant_pauses API только делает INSERT;
UPDATE участников и pause_budgets нет; ключ и событие — один commit; test_kinds_and_ttl обновлён;
в описании PR — отличия от карточки или «нет».

## 11. Вне задачи
- Статус паузы на /day/current — не делать (ШТАБ З2 п.4, SHTAB 3-Б: day.py 43,8 КБ); T5 берёт его из GET /pause.
- Бот: одобрение, уведомления, кнопки — T4 bot-pause-1. Экран Mini App — T5.
- kind author и shadow, /pause_grant, /unpause_user — Панель. RECONSENT — долг ШТАБа к T5.
- packages/shared (там только README.md и .gitkeep) не трогать.

## 12. Канон и решения
(а) DECISIONS Р-6а (одна на Этап, ≤ 7 дн., 14 дн. за цикл, ≥ 24 ч); канон 02 П.1, П.6, П.8 и I2 user_pause
(activation mini_app, 7d, min_gap 24h, client_op_id) — по pause-2 §2; контракт — api-pause-1a §5.
(б) Противоречий с DECISIONS нет. (в) Правок нет. (г) Правок канона нет.

## 13. Оценка
1 600, стоп 2 400 (принято ШТАБом З2). Основа — факт T2a 1 666 (тот же объём кода и тестов, проектора
нет) и 1 задетый файл (≈ 80); T2b 2 404 — с проектором, здесь его нет.

## 14. РЕВЬЮЕР
Да: новые маршруты под initData и rate-limit (DESIGNER §14: rate-limit → да).

## 15. Прочитано (ПРОЕКТИРОВЩИК, З1; в З2 новых файлов нет)
DESIGNER.md, PACK.md, STATE.md, AGENT-BRIEF.md, DECISIONS.md, CANON-CHECK.md, api-pause-1a.md, pause-2.md,
pause-2-check.md, pause_rules.py, 0018, support.py, rate_limit.py, participant_lock.py, errors.py — целиком.
Сверх списка (п.4 нарушен: 5 вместо 3): main.py, day_keys.py, pause_ops.py, test_rate_limit.py, test_api.py.
docs/architecture/** не открывался.
