# day-screen-b — Mini App: «Выполнил / Не выполнил» и «Отправить отчёт» на /day; живая проверка «C»

## 1. Паспорт
- id: day-screen-b · область: Mini App (apps/miniapp) · режим: Р1 (Агент Genspark).
- Заголовок PR: feat(miniapp): day-screen-b — отметки блоков (PUT marks) и отчёт дня (POST report/submit)
- Ветка: feat/day-screen-b · Зависит от: day-screen-a (начинать после мержа a).
- Миграций нет. API не меняется. Выкат — miniapp (a + b вместе), затем живая проверка §10.

## 2. Цель
Под каждым блоком — «Выполнил» / «Не выполнил» (переключаемо до отправки), «Отправить отчёт» — когда отмечены все блоки.
Отчёт идёт с одним X-Client-Op-Id на попытку; при ошибке — сообщение и повтор, ложного успеха нет. Результат дня экран
не показывает: его даёт очередь (DM 3.19).

## 3. Решения Автора
- 20.10: «отчёты сдаются до 00:00!!! … кнопки нажать что выполнил может только в 04:00 следующего дня!!!!».
- ШТАБ 20.10: 409 DAY_CLOSED (после 00:00), DAY_NOT_ACTIVE (до 04:00); повтор того же X-Client-Op-Id — раньше этих
  проверок, тот же 200. В15: повтор отчёта = тот же 200 без записи.
- З2 21.10: сверить кнопки с DM 3.3, 3.10, 3.11, 3.16; закрытие дня «часами» ≈ 00:02–00:03.
- Решение Автора «C»: живая проверка после выката (§10). Флаг — одно задание серверу (ШТАБ), как в life-ops-c §10.
- D-32: в живой проверке — только закрытие дня; tombstone не проверяем.

## 4. Выдержки (docs/architecture/03-day-mechanics.md)
- DM 3.3: «2 кнопки: «✅ Выполнил» / «⬜ Не выполнил» (состояние переключаемо до отправки отчёта). Кнопка «Отправить
  отчёт» активируется только после того, как все задания отмечены. Визуализация состояния — сменой текста/эмодзи на той
  же кнопке … Не более 2 кнопок в ряд, короткие подписи».
- DM 3.9: момент нажатия — по серверному времени; ≤ дедлайна — принят.
- DM 3.10: «после первого нажатия гаснет, повторный клик игнорируется».
- DM 3.11: «Если запись в БД не удалась — … показывается ошибка с просьбой повторить (ложный успех не показывается никогда)».
- DM 3.16: «всё не выполнено» → «мягкое сообщение», жизнь не горит. DM 3.19: результат — только после очереди 10–60 мин.
  Поэтому экран вердикт не показывает; мягкое сообщение — пуш бота (не эта пачка).
- DM 3.4: «Пришёл» — отметил галочки, отчёт не ушёл: жизнь не горит. Поэтому каждая отметка сразу идёт на сервер.

## 5. ЧТО ПРОЧИТАТЬ (чтение Агента ≈ 60 КБ)
AGENT-BRIEF.md — 16,8; apps/miniapp/src/api/client.ts — ≈ 8 (после a); apps/miniapp/src/pages/DayPage/DayPage.tsx — ≈ 9;
apps/miniapp/src/components/dayScreen.ts — ≈ 5; apps/miniapp/src/components/dayScreen.test.ts — ≈ 6 (образец);
apps/miniapp/src/components/OnboardingFlow.tsx — 16,7 (submittingRef, clientOpIdRef: один op_id на повтор, D-17).

## 6. Файлы (4 файла, ≈ 450 строк)
- Изменить: apps/miniapp/src/api/client.ts — putDayMark, postDayReport и их типы.
- Создать: apps/miniapp/src/components/dayMarks.ts — чистые функции §7.4.
- Создать: apps/miniapp/src/components/dayMarks.test.ts — тесты §9.
- Изменить: apps/miniapp/src/pages/DayPage/DayPage.tsx — кнопки и отправка §7.5.

## 7. Контракт (выдержка из apps/api/app/routers/day.py @3734b54)
7.1 PUT /miniapp/v1/day/marks, тело {block_id: ^[a-z0-9_]{1,32}$, value: 'done' | 'not_done'}; X-Client-Op-Id не нужен
  (UPSERT: повтор безопасен). 200 {block_id, value}. 404 PARTICIPANT_NOT_FOUND; 409 DAY_NOT_STARTED / DAY_NOT_ACTIVE /
  DAY_CLOSED / DAY_ALREADY_SUBMITTED; 422 BLOCK_NOT_IN_DAY; 503.
7.2 POST /miniapp/v1/day/report/submit, заголовок X-Client-Op-Id (uuid v4, обязателен — newClientOpId), тело
  {marks: [{block_id, value}]} — каждый блок дня ровно один раз. 200 {verdict: 'passed' | 'not_passed' | 'all_not_done',
  queued: true} — только после commit. Порядок проверок: 404 → повтор op_id (то же тело → тот же 200, даже после 00:00
  и сдвига дня; другое тело → 409 IDEMPOTENCY_CONFLICT) → 409 DAY_NOT_STARTED → 503 DAY_CONTENT_MISSING →
  409 DAY_NOT_ACTIVE / DAY_CLOSED → 422 MARKS_INCOMPLETE → 409 DAY_ALREADY_SUBMITTED. 401, 429, 503 — как везде.
7.3 client.ts: putDayMark = (body) => apiRequest<DayMarkOut>('/miniapp/v1/day/marks', { method: 'PUT', body });
  postDayReport = (body, clientOpId) => apiRequest<DayReportOut>('/miniapp/v1/day/report/submit', { method: 'POST', body, clientOpId }).
7.4 dayMarks.ts:
- type LocalMarks = Record<string, 'done' | 'not_done'>; marksFromDay(day) — из blocks[].mark (null пропускать).
- markLabels(mark) → { done: mark === 'done' ? '✅ Выполнил' : 'Выполнил', notDone: mark === 'not_done' ? '⬜ Не выполнил' : 'Не выполнил' }.
- allMarked(blocks, marks); canPressMark(view, day, busy) = view === 'open' && day.buttons_active === true
  && !busy.sending && !busy.sent; canSendReport = canPressMark && allMarked.
- reportBody(blocks, marks) → { marks } в порядке блоков.
- reuseOpId(prev: {opId, key} | null, body, makeId) → тот же prev, если key === JSON.stringify(body); иначе новый {opId: makeId(), key}.
- markErrorAction(err): 409 DAY_NOT_STARTED / DAY_NOT_ACTIVE / DAY_CLOSED / DAY_ALREADY_SUBMITTED, 422 BLOCK_NOT_IN_DAY → 'refetch';
  прочее → 'retry'.
- submitErrorAction(err): те же 409 и 422 MARKS_INCOMPLETE → 'refetch'; 409 IDEMPOTENCY_CONFLICT → 'new_op_refetch';
  прочее (401, 429, 503, сеть) → 'retry' с тем же opId.
- actionMessage(err, kind 'mark' | 'report'): DAY_CLOSED → «День закрыт: отчёт принимался до 00:00.»;
  DAY_NOT_ACTIVE → «Кнопки станут активны в 04:00.»; DAY_ALREADY_SUBMITTED → «Отчёт уже отправлен.»;
  DAY_NOT_STARTED, BLOCK_NOT_IN_DAY, MARKS_INCOMPLETE, IDEMPOTENCY_CONFLICT → «День обновился. Проверьте отметки.»;
  прочее → «Отметка не сохранилась. » или «Отчёт не отправлен. » + errorMessage(err).
7.5 DayPage.tsx:
- локальные отметки = marksFromDay после каждого GET (сервер — источник правды); PUT 200 → отметка из ответа.
- ряд 1: [Выполнил] [Не выполнил] (aria-pressed, подписи markLabels); ряд 2: [❓ Как выполнить?]; не больше 2 кнопок в ряд.
  В not_active кнопки видны, но disabled (DM 3.1); в closed, queued и submitted кнопок нет.
- клик: тот же выбор → ничего; один PUT на блок за раз (Set в ref); пока PUT идёт — кнопки блока disabled;
  ошибка → actionMessage, отметка прежняя; 'refetch' → GET.
- «Отправить отчёт» — отдельным рядом под блоками; disabled, пока не canSendReport; клик: sendingRef → body →
  opRef = reuseOpId(opRef, body, newClientOpId) → POST. Во время отправки «Отправляем…», отметки заблокированы.
  200 → sent = true (кнопка остаётся погашенной), opRef = null, сразу GET; вердикт не показывать.
  Ошибка → actionMessage; 'retry' — кнопка снова активна, повтор с тем же opId; 'new_op_refetch' → opRef = null, GET.
- sent сбрасывается, когда GET вернул другой view или другой day_started_at.

## 8. БД — нет.

## 9. Тесты (vitest, node). Цель: bash tools/check.sh miniapp
dayMarks.test.ts:
- markLabels для done / not_done / null; marksFromDay пропускает null; allMarked: пусто, часть, все.
- canPressMark / canSendReport: open + buttons_active true → да; not_active, closed, queued, sending, sent → нет;
  не все отмечены → canSendReport нет.
- reportBody — порядок блоков; reuseOpId: то же тело → тот же opId (makeId не вызван); другое тело → новый.
- markErrorAction и submitErrorAction — каждая ветка (ApiError 409 / 422 по коду, 503, не-ApiError → 'retry').
- actionMessage: DAY_CLOSED, DAY_NOT_ACTIVE, прочее с префиксом. Тесты dayScreen из a — зелёные.

## 10. Живая проверка «C» (после выката a + b; D — день проверки)
SQL — под владельцем, тем же способом, что в прошлых живых проверках (SERVER.md); строку psql не угадывать.
Выбран полный путь (ШТАБ 21.10).
Шаг 1. СЕРВЕРНЫЙ (D): выкат miniapp a + b; 7/7 Up, 5 healthy.
Шаг 2. Одно задание серверу (ШТАБ, D, днём; как life-ops-c §10):
  2.1 бэкап pg_dump -Fc → before-day-live (размер > 0, около before-0009);
  2.2 DAY_TEST_ENTRY_ENABLED=true → DC up -d --no-build --no-deps api → printenv в api: true (config целиком не печатать);
  2.3 Автор, Mini App: «Тестовый вход» → «Готовим день…» → день 1: блоки, кнопки disabled, «… ДД.ММ (D+1) в 04:00»;
  2.4 сервер: в participant_events одна строка kind day_entered; participant_state day_no 1;
  2.5 флаг false → DC up -d --no-build --no-deps api → printenv false. Экран дня 1 после «Обновить» — тот же.
  Дальше шаги 3–7 — с флагом false: флаг читают только POST test-enter и поле test_entry в GET (при позиции оно false).
Шаг 3. Автор (D+1, после 04:00, до 23:59): переключить одну отметку туда и обратно; отметить все блоки (⭐ — «Выполнил»);
  «Отправить отчёт» дважды быстро → кнопка гаснет → экран очереди. Сервер: ровно одна строка day_report_submitted
  (verdict passed, next_day_no 2); лог api «status=ok verdict=passed».
Шаг 4. Через 10–60 мин экран сам показывает день 2: кнопки disabled, «… ДД.ММ (D+2) в 04:00». participant_state day_no 2.
Шаг 5. D+2: Автор в дне 2 ничего не нажимает (полное молчание, DM 3.4).
Шаг 6. Ночь D+2→D+3: в 00:00–00:02 экран — t(closedHint); «часы» закрывают день 2 ≈ 00:02–00:03.
Шаг 7. СЕРВЕРНЫЙ, утро D+3: SELECT kind, payload FROM participant_events WHERE kind = 'day_closed' → одна строка;
  payload (life-ops-c §7 п.7): day_started_at — старт дня 2; outcome "silent" (day_clock.OUTCOME_SILENT);
  missed_streak 1; next_day_started_at — момент нового старта. Payload — в отчёт дословно (без pid).
  SELECT lives, stage_no, module_no, day_no, day_started_at, tz FROM participant_state → lives 3 (без списания),
  day_no 2, day_started_at = next_day_started_at из payload; логи projector: Traceback 0, WARNING 0.
  Автор: день 2 снова, отметок нет, «… ДД.ММ (D+3) в 04:00».
Шаг 8. ШТАБ: D-32 — «живое закрытие дня проверено (дата)»; tombstone — до прода.
Почему ночь D+2→D+3: закрывается только несданный день; день 1 сдан на шаге 3. «Пришёл» покрыт тестами CI.

## 11. Запреты
AGENT-BRIEF §3. Ложного успеха нет: «отправлено» — только после 200. Вердикт на экране не показывать. Окно на клиенте не считать —
только buttons_active и коды 409. Новый op_id при повторе того же тела — нельзя. Отметки не хранить на устройстве.
apps/api, dayScreen.ts (кроме экспорта, если нужен), OnboardingFlow.tsx не менять. Новых npm-пакетов нет. CI не ждать (А-CI).

## 12. Готовность
Файлы §6; DM 3.3 / 3.10 / 3.11 выполнены; тесты §9; CI 7/7; живая проверка §10 — шаги 1–8 (ШТАБ отмечает D-32).

## 13. Оценка
Автор ≈ 0,5 ч + 4 коротких захода по 5 мин (D–D+3); сервер 3 задания (выкат, флаг, утро D+3). Кредиты Агента ≈ 600–900 (+ правки).

## 14. РЕВЬЮЕР: нет — по решению ШТАБа (initData, 18+, согласия, rate-limit, роли БД, оплата не затронуты;
идемпотентность отчёта обеспечивает сервер, клиент лишь повторяет тот же op_id).
