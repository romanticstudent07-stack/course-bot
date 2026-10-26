# pushi-notify-1 — НП3 «Задания откроются … в 04:00» из «часов» проектора

## 1. Шапка
- id: pushi-notify-1. Заголовок PR: feat(api): pushi-notify-1 — НП3 «Задания откроются в 04:00» из часов проектора
- Ветка: feat/pushi-notify-1. Режим: Р1 (Агент). Зависит от: #133 (docs/research/pushi.md) в main.
- Выкат на сервер — только после закрытия живой проверки «C» (STATE: projector 88dc8d4 не пересобирать до неё).
- Правило К — docs/process/CANON-CHECK.md. Читать по hash main cf920ef.

## 2. Цель
«Часы» в проекторе пишут в outbox сообщение участнику «Задания откроются сегодня/завтра в 04:00 по Вашему времени»:
(а) когда кончилась очередь после сдачи дня; (б) когда назначен первый день (после онбординга).
Новый модуль app/notify_ops.py по образцу app/life_ops.py, вызов из run_forever рядом с life_ops.tick. Миграций нет. Бот не меняется.

## 3. Решения (К-6)
- НП3 А — после очереди и после онбординга «Задания откроются … в 04:00 по Вашему времени», заглушка [Автор; 03 §3.19, 09 R257].
- В1 А — после онбординга тоже пишут «часы» (роль app_projector, права 0009: INSERT (aggregate_id, event_type, payload, tx_id) + USAGE outbox_id_seq; SELECT нет → без RETURNING); задержка до тика допустима [Автор, канон молчит].
- В2 Б — два текста: местное время записи до 04:00 → B9.day_tasks_open_today, с 04:00 → B9.day_tasks_open_tomorrow; момент — запись в outbox [Автор, канон молчит].
- В4 А (26.10) — НП3, опоздавший из-за простоя на время после 04:00 дня, на который он указывает (задания уже открыты), НЕ отправляется; ключ всё равно пишется [Автор, канон молчит; 03 §3.19, 09 R257]. В pushi.md В4 записан открытым — решён здесь.
- Ключи текстов — B9.day_* (домена B3 в схеме нет); тексты «[ЗАГЛУШКА] …», legal_status pre-legal-review [ШТАБ].
- Новый kind tasks_open в idempotency_keys без миграции (CHECK на kind нет, 0007) [ШТАБ].
- Ключ «после очереди» — к тому же next_started, что ключ day_queue:{pid}:{dsa(next_started)} life-ops-b [ШТАБ, по коду day.py@8833b18].
- Аргумент очереди X = текущий participant_state.day_started_at [по коду: routers/day.py@cf920ef — submit пишет key_day_queue(pid, next_started), проектор ставит day_started_at = next_day_started_at, read_day_current проверяет key_day_queue(pid, started) и day_clock.queue_until(pid, started)].
- Ключ «после онбординга» — тот же kind и формат tasks_open:{pid}:{dsa(day_started_at)}: первый день ставит событие day_entered (day_started_at = at события, только при day_no IS NULL) [по коду: app/projector.py@cf920ef, _SET_POSITION].
- Триггер «после онбординга» — событие day_entered любого источника; сейчас его пишет только POST /day/test-enter (payload source test_flag) [по коду: day.py@cf920ef] — кто бы ни писал day_entered.
- Фильтр участников — как у life_ops: фазы onboarding/active, author_pause_reason IS NULL, нет BLOCKING_FLAGS [ШТАБ-тех, образец life_ops; гейт T2 в каноне — не проверено].
- Тон текстов neutral; версия day.json 0.2.0 → 0.3.0 (схема: «bump при любой правке текста»; test_texts проверяет версии только у B4 и legal) [ШТАБ].

## 4. Выдержки (Агент docs/architecture/** не открывает)
- 03 §3.19, 09 R257 (по docs/research/pushi.md §0, §4): после очереди и после онбординга — «Задания откроются … в 04:00 по Вашему времени».
- 03 §3.1 (pushi.md §0, НП2): кнопки дня активны с 04:00 по поясу участника; отдельного пуша в 04:00 нет.
- Бот (pushi.md §5, apps/bot/bot/outbox.py@8833b18): aggregate_id = pid строкой; payload {text_id, payload_vars (по умолчанию {}), tier}; event_type — только в логах; нет текста → DLQ text_not_found. Outbox не умеет «не раньше» — бот берёт строку сразу.
- 0001_init@cf920ef: outbox.tx_id xid8 NOT NULL, DEFAULT нет. 0009: у app_projector есть INSERT на колонку tx_id.
- В text_registry.schema.json домены ключей: B2, B4, B5, B7, B9, B10, B14, B15, B16, legal; формат «{домен}.{имя}», имя snake_case.

## 5. ЧТО ПРОЧИТАТЬ (Агент)
- AGENT-BRIEF.md — 17,1; эта карточка — ≈ 12.
- apps/api/app/projector.py — 30,8 (run_forever, _life_ops_step, EVENT_KIND_DAY_ENTERED).
- apps/api/app/life_ops.py — 17,0 (образец: кандидаты, lock_participant, ключ ON CONFLICT, LOCK_TIMEOUT, логи).
- apps/api/app/day_clock.py — 10,0; apps/api/app/day_keys.py — 2,9; apps/api/config/texts/day.json — 5,2.
- apps/api/tests/test_life_ops.py — только импорты и фикстуры БД (образец для DB-тестов; размер не проверен).
- Чтение Агента ≈ 95 КБ.

## 6. Файлы
- Создать: apps/api/app/notify_ops.py; apps/api/tests/test_notify_ops.py.
- Изменить: apps/api/app/projector.py; apps/api/app/day_keys.py; apps/api/config/texts/day.json.
- Удалить: нет. expected_tables.txt не трогать (таблиц не прибавляется).

## 7. Контракт модуля notify_ops.py
Константы: NOTIFY_OPS_INTERVAL_S = life_ops.LIFE_OPS_INTERVAL_S; MAX_PER_TICK = 200; LOCK_TIMEOUT = "5s";
EVENT_TYPE = "tasks_open_notice"; TIER = "T2"; TEXT_TODAY = "B9.day_tasks_open_today"; TEXT_TOMORROW = "B9.day_tasks_open_tomorrow";
EVENT_KIND_DAY_ENTERED = "day_entered" (равно projector.EVENT_KIND_DAY_ENTERED; сверяет тест; projector не импортировать — он импортирует notify_ops).
day_keys.py: KIND_TASKS_OPEN = "tasks_open", TTL_TASKS_OPEN = "3650 days", запись в TTL_BY_KIND, key_tasks_open(pid, ts) = f"tasks_open:{pid}:{dsa(ts)}"; в docstring строка формата.
Чистые функции (без БД):
- choose_text(now, tz) → TEXT_TODAY, если местное время now (day_clock.zone(tz)) < day_clock.ACTIVATION_TIME, иначе TEXT_TOMORROW.
- is_late(started, tz, now) → day_clock.window(started, tz, now) != day_clock.WINDOW_NOT_ACTIVE (задания уже открыты — В4).
- decide(pid, started, tz, now, has_queue_key, entered) → None | "send" | "late"; started = текущий participant_state.day_started_at:
  есть ключ day_queue:{pid}:{dsa(started)} → если now < day_clock.queue_until(pid, started) (сравнение в UTC) → None (ждём); иначе триггер;
  нет его, но entered (есть событие day_entered с at = started) → триггер; иначе None.
  Триггер → "late", если is_late, иначе "send".
tick(engine, now) → NotifyResult(sent, late, skipped); now aware, иначе ValueError (как life_ops._require_aware):
1. Чтение, своя транзакция, rollback: строки participant_state с фильтром life_ops (_CANDIDATES тот же, флаги life_ops.BLOCKING_FLAGS); в Python ключи tasks_open и day_queue по dsa(day_started_at);
   одним запросом SELECT key FROM idempotency_keys WHERE key = ANY(:keys); одним запросом SELECT pid, at FROM participant_events WHERE kind = 'day_entered' AND pid = ANY(:pids).
   Есть ключ tasks_open → не кандидат. decide = None → не кандидат. Не больше MAX_PER_TICK.
2. Каждый pid — своя транзакция: SET LOCAL lock_timeout, lock_participant(conn, pid), состояние заново, фильтр life_ops._eligible,
   «проектор догнал pid» (как life_ops._PENDING_EVENT) — нет → пропуск; ключи и day_entered заново; decide заново.
3. Запись: INSERT INTO idempotency_keys (key, kind, ttl) VALUES (..., 'tasks_open', CAST(:ttl AS interval)) ON CONFLICT DO NOTHING RETURNING key; 0 строк → rollback.
   "send" → INSERT INTO outbox (aggregate_id, event_type, payload, tx_id) VALUES (:aggregate_id, 'tasks_open_notice', CAST(:payload AS jsonb), pg_current_xact_id()) — БЕЗ RETURNING;
   aggregate_id = str(pid); payload = {"text_id": choose_text(now, tz), "payload_vars": {}, "tier": "T2"}.
   tx_id обязателен (xid8 NOT NULL, DEFAULT нет). pg_current_xact_id() — номер транзакции, не время: запрет «SQL now()» его не касается.
   "late" → только ключ. Один commit на pid.
4. Ошибка на pid → rollback, WARNING с именем класса, другие pid идут дальше. Ошибка чтения кандидатов — наружу (ловит projector).
Время — только аргумент now; datetime.now(), time.time(), SQL now() в логике нельзя. Сравнения моментов — в UTC или функциями day_clock.
Лог: без pid, tz, payload, ПДн. Итог тика INFO: «notify_ops: tick sent=%s late=%s skipped=%s».
projector.py: _notify_ops_step(engine, last) — копия _life_ops_step (свой last, интервал NOTIFY_OPS_INTERVAL_S, now = day_clock.utcnow(),
любая ошибка → WARNING «projector: notify_ops tick failed (<класс>)»); в run_forever вызов сразу после _life_ops_step; once — без него.
PROJECTOR_VERSION не менять (новых видов событий нет). Docstring projector.py: одна строка про notify_ops.
day.json: 2 записи (tone neutral, legal_status pre-legal-review), version "0.3.0":
B9.day_tasks_open_today — «[ЗАГЛУШКА] Задания откроются сегодня в 04:00 по Вашему времени.»
B9.day_tasks_open_tomorrow — «[ЗАГЛУШКА] Задания откроются завтра в 04:00 по Вашему времени.»
notes у первой: «pushi-notify-1: НП3, пишет notify_ops. Заглушки до 0-Б.»

## 8. БД
Миграции нет. Новый kind tasks_open — без миграции (CHECK на kind нет, 0007). participant_events и participant_state notify_ops не пишет.

## 9. Тесты (apps/api/tests/test_notify_ops.py)
Без БД:
1. choose_text: 03:59 местного → today; 04:00 и 23:59 → tomorrow (пояса Europe/Moscow и Asia/Vladivostok).
2. is_late и decide: старт 15:00, now 20:00 → send; now следующего дня 04:00 → late; есть day_queue, now < queue_until → None; now ≥ queue_until → send.
3. decide: нет day_queue и нет day_entered (день после day_closed) → None.
4. key_tasks_open: формат, naive → ValueError; TTL_BY_KIND содержит tasks_open.
5. Статика: в notify_ops.py нет «RETURNING» в INSERT INTO outbox, есть pg_current_xact_id(), нет INSERT INTO participant_events; EVENT_KIND_DAY_ENTERED == projector.EVENT_KIND_DAY_ENTERED.
6. tick с naive now → ValueError; _notify_ops_step: исключение tick → WARNING с именем класса, проектор живёт.
С БД (фикстуры — как в test_life_ops.py; в CI обязательно):
7. После очереди: ключ day_queue по текущему day_started_at + now ≥ queue_until → 1 строка outbox (text_id, tier T2, payload_vars {}), ключ tasks_open; второй tick → ничего нового.
8. После онбординга: событие day_entered + состояние с тем же day_started_at → 1 строка outbox.
9. Опоздание (В4): now после active_from → ключ есть, outbox 0.
10. Фильтры: пауза, флаг block_lives, sleeping, есть событие после checkpoint → ни ключа, ни outbox.
11. Роль app_projector (как в тестах life_ops): INSERT в outbox без RETURNING проходит; у строки outbox tx_id не NULL.
Цели: bash tools/check.sh api. CI: тесты с БД.

## 10. Задетые тесты (правило «Т»)
Меняется общее: run_forever в projector.py (новый шаг), TTL_BY_KIND в day_keys.py, day.json.
- apps/api/tests/test_projector_static.py — правка не нужна (notify_ops не пишет participant_state); должен остаться зелёным.
- apps/api/tests/test_texts.py — правка не нужна (новые записи — заглушки, дублей нет, версии проверяются только у B4 и legal).
- apps/api/tests/test_texts_load_errors.py — не задет.
- Вне прочитанного (test_projector_v3.py, test_life_ops.py — run_forever; тесты day_keys и day.json): не угадывать.
  Упал тест вне списка → Агент НЕ чинит, пишет «тест X вне списка» в ИТОГ и останавливается.

## 11. Живая проверка (после мержа и после закрытия «C»; команды пишет СЕРВЕРНЫЙ)
Аккаунты: А1 (#000001, админ; его тестовый день идёт — не трогать), А2 (#000026), А3 (#000027), А4 (новый, с ботом не взаимодействовал).
1. Сервер: DC --profile tools build migrate; build projector; texts load → «загружено 2, обновлено 33, лишних в БД 0»; up -d projector.
2. Логи projector 2 мин: «notify_ops: tick sent=0 late=K skipped=S» раз в 30 с (K ≥ 0 — старые дни получают только ключ); Traceback 0, WARNING 0.
3. После очереди: перед проверкой сервер запросом говорит, у кого из А2 и А3 открыт день. Этот аккаунт сдаёт отчёт дня в Mini App между 04:00 и 23:00 местного.
   Через 10–60 мин бот пишет «[ЗАГЛУШКА] Задания откроются завтра в 04:00 по Вашему времени.»
   SQL: idempotency_keys kind tasks_open +1; outbox event_type tasks_open_notice +1 с sent_at и непустым tx_id; outbox_dlq без новых строк.
4. После онбординга — А4 (нужен аккаунт без позиции: day_entered применяется только при day_no IS NULL). Перед шагом ШТАБ спрашивает Автора и пишет причину «нет аккаунта без позиции».
   А4: промокод → доступ → онбординг; сервер по заданию ШТАБа включает DAY_TEST_ENTRY_ENABLED=true; тестовый вход → в течение ≈ 30 с сообщение «… завтра …» (до 04:00 местного — «… сегодня …»); сервер возвращает флаг в false.
5. Повтор: restart projector → новых сообщений нет (ключи). А1 сообщений не получил.

## 12. Запреты
AGENT-BRIEF §3. Плюс: бот, миграции, схему text_registry, docs/architecture/** не трогать; не менять PROJECTOR_VERSION и life_ops.py;
не писать participant_state и participant_events из notify_ops; RETURNING в INSERT outbox нельзя; datetime.now() и SQL now() в логике нельзя; CI не ждать.

## 13. Критерии готовности
Тесты раздела 9 есть и зелёные в sandbox (без БД); tools/check.sh api зелёный; файлы PR = раздел 6; в ИТОГ — прочитанные файлы и вопросы ШТАБу.

## 14. Оценка
Часы Автора ≈ 1 (PR + выкат + живая проверка). Агент 600–900 кредитов (5 файлов, ≈ 550 строк, из них тесты ≈ 250; tx_id — одна колонка, оценка не меняется; правка задетых тестов из списка не нужна — 0 × 60–100).

## 15. РЕВЬЮЕР
Нет (не трогает initData, 18+, согласия, rate-limit, GRANT, оплату).
