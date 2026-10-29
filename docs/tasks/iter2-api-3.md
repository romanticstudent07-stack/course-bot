# iter2-api-3 — submit: срок op_id, UUID v4, 503 на битый result_ref; тесты гонки через pg_blocking_pids

## 1. Паспорт
- id: iter2-api-3. PR: «iter2-api-3: submit — срок op_id, UUID v4, 503 на битый result_ref, тесты гонки».
- Ветка: feat/iter2-api-3. Режим: Р1 (Агент). Зависит от: iter2-api-2b, life-ops-b (в main). Миграций нет.
- Состав — ревью PR #103, комментарий ШТАБа 19.10, пункты (1), (2), (3), (5), (6). Issues #13 #14 #15 #17 #18
  закрыты 26.10 — не берём.

## 2. Цель
Повтор отчёта с тем же X-Client-Op-Id даёт 200 только в пределах срока ключа (1 ч), позже — 409.
Битый result_ref → 503 (не 500). Заголовок — только UUID v4. Тесты гонки ждут замок через pg_locks
с фильтром pg_blocking_pids — без sleep и без счёта чужих ожиданий в кластере.

## 3. Решения (метки К-6)
- В15 — А [Автор, дословно из iter2-api-2b §3]: «повтор с тем же X-Client-Op-Id → 200 тем же телом».
- Срок op_id — вариант В [ШТАБ-тех, К-5; по коду: миграция 0007_day_state — у idempotency_keys есть
  created_at timestamptz NOT NULL и ttl interval NOT NULL]. Ключ day_report истёк, если
  created_at + ttl < :now; сравнение — в SQL, :now = day_clock.utcnow() один раз за запрос (после замка).
  Истёк → 409 IDEMPOTENCY_CONFLICT. params_hash НЕ меняется (вариант А отклонён — ломает В15; Б — сложнее
  при том же результате).
- Почему этого достаточно: TTL day_report = 1 ч (day_keys.TTL_DAY_REPORT); отчёт принимается до 00:00,
  кнопки следующего дня — с 04:00 (day_clock, окно дня) → любой повтор в пределах 1 ч относится к сданному
  дню. В15 соблюдён: сдвиг day_started_at проектором на ответ повтора не влияет.
- created_at ключа day_report = :now запроса, а не DEFAULT now() [ШТАБ-тех, К-5; подтверждено ШТАБом в З3].
  Причина: время в логике — только day_clock (docstring day.py, У1). В тестах day_clock подменён на прошлое
  (20.10.2026), а SQL now() — настоящее время; с DEFAULT now() срок ключа в тестах не наступал бы никогда,
  а в логике смешались бы два источника времени. day_done и day_queue — без изменений (DEFAULT).
- result_ref вне VERDICTS → rollback, WARNING, 503 SERVICE_UNAVAILABLE [ШТАБ-тех, ревью #103 п.5].
- X-Client-Op-Id — только UUID v4 [канон: contract ClientOpId; по коду: apps/miniapp/src/api/client.ts,
  newClientOpId() ставит биты версии 4 и варианта — Mini App не ломается].
- PUT /day/marks: op_id не нужен [ШТАБ-тех; канон: contract — пути marks нет, молчит; buttons_idempotent —
  не проверено; по коду: UPSERT идемпотентен, at не меняется; client.ts putDayMark: X-Client-Op-Id не нужен].
  В задачу не входит, поведение не меняется.
- CORS не нужен [по коду: в apps/api/main.py нет CORSMiddleware; Mini App и API — один origin через nginx].

## 4. Канон и решения
(а) Канон задачи:
    - docs/architecture/build/miniapp-api-contract.yaml, components.headers.ClientOpId:
      «UUID v4 клиента для идемпотентности (buttons_idempotent, money_ops_idempotent)»;
    - 03-day-mechanics.md, шапка: «Инвариант зачёта дня П-31 (day_counting: on_confirmed_db_write)…»;
      §3.10 «повтор игнорируется» — по выдержке в карточке iter2-api-2b §4 (блок не читался).
(б) Противоречий с docs/decisions/DECISIONS.md нет: Р-1…Р-14 и НП submit не касаются.
(в) Правок нет.
(г) Правок канона нет. Тела day/* в contract — отдельный DOCS PR (Ш6 из iter2-api-2b), не эта задача.

## 5. ЧТО ПРОЧИТАТЬ (Агент; ≈ 127 КБ)
AGENT-BRIEF.md 17; docs/decisions/DECISIONS.md 8; эта карточка 10; apps/api/app/routers/day.py 37;
apps/api/app/day_keys.py 5; apps/api/app/day_report.py 3; apps/api/tests/conftest.py 7;
apps/api/tests/test_day_report_submit.py 17; apps/api/tests/test_day_writers.py 9;
apps/api/tests/test_day_window.py 12.

## 6. Файлы (только изменить; создать и удалить — нет)
apps/api/app/routers/day.py; apps/api/app/day_keys.py (только docstring); apps/api/tests/conftest.py;
apps/api/tests/test_day_report_submit.py; apps/api/tests/test_day_writers.py; apps/api/tests/test_day_window.py.

## 7. Контракт и код
POST /miniapp/v1/day/report/submit:
- Заголовок: client_op_id: UUID4 (from pydantic import UUID4) = Header(alias=CLIENT_OP_ID_HEADER).
  Не UUID или версия ≠ 4 (v1, v3, v5, nil) → 422 VALIDATION_ERROR (обработчик уже есть).
  Тип op_id в submit_day_report остаётся uuid.UUID.
- Шаг 2 (ключ day_report:{pid}:{op_id} есть). Чтение — text-SQL вместо select(IdempotencyKey…):
      _REPORT_KEY_SQL = text(
          "SELECT result_ref, params_hash, (created_at + ttl < :now) AS expired "
          "FROM idempotency_keys WHERE key = :key"
      )
  Порядок:
  2.1 expired → rollback, 409 IDEMPOTENCY_CONFLICT; message тот же, что при несовпадении hash: клиенту
      различать не нужно;
  2.2 params_hash другой → 409 IDEMPOTENCY_CONFLICT (как сейчас);
  2.3 result_ref not in VERDICTS (from app.day_report import VERDICTS; NULL тоже) → rollback,
      logger.warning("day/report/submit: ключ day_report с result_ref вне VERDICTS — 503")
      (pid, op_id и сам result_ref в лог не идут) → 503 SERVICE_UNAVAILABLE (_service_unavailable);
  2.4 иначе → rollback, 200 {verdict: result_ref, queued: true} (как сейчас).
- Шаг 8: ключ day_report пишется с created_at = :now (новый text-SQL с колонкой created_at или
  параметр created_at в _insert_result_key — только для KIND_DAY_REPORT). day_done, day_queue — как сейчас.
- SQL now() и datetime.now() в новой логике не использовать. Остальные шаги 1–10 не меняются.
- docstring day.py: шапка POST «(uuid, обязателен; нет или не uuid → 422…)» → «(UUID v4, обязателен;
  нет, не UUID или не v4 → 422…)»; шаг 2 — по 2.1–2.4; шаг 8 — «day_report с created_at = now
  запроса (api-3)».
- docstring day_keys.py: «Срок ttl в логике не проверяется: UPDATE и DELETE ключей нет ни у кого,
  строка есть → ключ есть.» → «Срок ttl в логике не проверяется, кроме day_report: submit отвечает 409
  на повтор после created_at + ttl (api-3). UPDATE и DELETE ключей нет ни у кого.»

## 8. БД
Миграций нет. Колонки created_at и ttl уже есть (0007_day_state). expected_tables.txt не трогать.

## 9. Тесты
conftest.py — новый общий помощник:
    def wait_for_lock_waiter(engine, holder_pid: int, timeout: float = 10.0) -> bool:
        # True, когда кто-то ждёт advisory-замок, который держит holder_pid
        sql = text("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
                   "AND NOT granted AND :h = ANY(pg_blocking_pids(pid))")
        # опрос каждые 0.05 с до timeout
test_day_report_submit.py:
- test_op_id_v1_422 (без БД): заголовок str(uuid.uuid1()) → 422 VALIDATION_ERROR, _header_error.
- test_parallel_submits_one_200_one_409 — переписать: в held_commit до ready.set() запомнить
  holder = session.execute(text("SELECT pg_backend_pid()")).scalar_one(); вместо time.sleep(0.3) —
  assert wait_for_lock_waiter(db_engine, holder). Остальные проверки — как были.
- test_double_tap_same_op_id_both_200 (новый): та же гонка, один op_id и одно тело _all("done") в обоих
  потоках → оба verdict passed; _events == 1; _keys == 3 (day_done, day_report, day_queue — по одному).
- test_repeat_within_ttl_after_projector_200 (новый, В15): сдать отчёт → run_once → day_started_at
  в state ≠ started → UPDATE idempotency_keys SET created_at = :t (t = _CLOCK["now"] − 30 мин)
  WHERE key = key_day_report(pid, str(op_id)) → повтор тем же op_id и телом == первый ответ; _events == 1.
  UPDATE created_at — только в тесте, через db_engine (владелец БД, как INSERT ключей в
  test_day_window.py); в коде приложения UPDATE ключей нет.
- test_repeat_after_ttl_409 (новый): то же, но t = _CLOCK["now"] − 2 ч → 409 IDEMPOTENCY_CONFLICT;
  _events == 1, _keys == 3. UPDATE created_at — только в тесте, через db_engine (владелец БД, как INSERT
  ключей в test_day_window.py); в коде приложения UPDATE ключей нет.
- test_result_ref_outside_verdicts_503 (новый): до сдачи вставить ключ напрямую: key_day_report(pid,
  str(op_id)), kind 'day_report', ttl '1 hour', result_ref 'bogus', params_hash =
  params_hash(list(_all("done").items())), created_at = _CLOCK["now"] (явно!) → submit тем же op_id и
  телом → HTTPException 503 SERVICE_UNAVAILABLE; caplog (logger "app.routers.day") — есть WARNING,
  в тексте нет str(pid) и str(op_id); _events == 0, _marks == {}.
- test_report_key_created_at_is_request_now (новый): после сдачи created_at ключа day_report ==
  _CLOCK["now"] (сравнивать в UTC).
Цели check.sh: apps/api/tests/test_day_report_submit.py apps/api/tests/test_day_writers.py
apps/api/tests/test_day_window.py apps/api/tests/test_day_report_unit.py. С БД (гонки, срок, 503) — только CI.

## Задетые тесты (правило «Т»; основа — grep ШТАБа по 0a26161)
- apps/api/tests/conftest.py → добавить wait_for_lock_waiter (выше); импорт text из sqlalchemy.
- apps/api/tests/test_day_writers.py → удалить _WAITERS_SQL и _wait_for_lock_waiter; в _race::held_commit
  до ready.set() запомнить pid держателя (SELECT pg_backend_pid() через ту же session);
  waited = wait_for_lock_waiter(engine, holder_pid); импорт из tests.conftest. Тесты test_race_* не менять.
- apps/api/tests/test_day_window.py → в test_race_on_midnight_now_taken_after_lock: в held_commit до
  ready.set() запомнить holder (SELECT pg_backend_pid() через ту же session); time.sleep(0.3) →
  assert wait_for_lock_waiter(db_engine, holder); assert len(calls) == 1 оставить; импорт из tests.conftest;
  если time больше не используется — убрать import time. Остальные тесты файла не трогать.
- apps/api/tests/test_day_report_submit.py → раздел 9.
- Не трогать (проверено grep ШТАБом): test_day_report_unit.py (params_hash не меняется); test_day_queue.py,
  test_life_ops_race.py (сигнатура submit_day_report та же, каждый submit — новый uuid4, повторов op_id нет);
  test_day_window.py::test_repeat_same_op_id_after_midnight_same_200 (повтор через 5 мин < 1 ч → 200);
  test_day_current.py::test_kinds_and_ttl (TTL_BY_KIND не меняется). uuid1 в тестах нет.

## 10. Живые проверки (только после мержа; сейчас сервер занят — ничего не запускать)
СЕРВЕРНЫЙ по заданию ШТАБа: build api из main → пересоздать только api (проектор не трогать) →
GET /healthz = 200; POST /miniapp/v1/day/report/submit без initData = 401; в логах api Traceback = 0.
Бэкап не нужен: миграций нет.

## 11. Запреты
AGENT-BRIEF §3. Плюс: без миграций; не трогать projector.py, main.py, apps/miniapp, PUT /day/marks,
params_hash, day_clock; без SQL now() и datetime.now() в логике; pid и op_id в лог не писать; CI не ждать
(А-CI); упал тест вне списка «Задетые тесты» → не чинить, «тест X вне списка» в ИТОГ и стоп.

## 12. Готовность
CI 7/7; все тесты раздела 9 зелёные; в test_day_report_submit.py и test_day_window.py нет time.sleep;
в test_day_writers.py нет _WAITERS_SQL и _wait_for_lock_waiter; живые проверки раздела 10 ✅.

## 13. Оценка
Агент Р1 ≈ 640 кредитов (база ≈ 350 + 4 файла «Задетых тестов» ≈ 290). Автор ≈ 0,5 ч.

## 14. РЕВЬЮЕР
Нет: initData, 18+, согласия, B-1, B-3 и оплата не затронуты. Идемпотентность сверяет ШТАБ.
