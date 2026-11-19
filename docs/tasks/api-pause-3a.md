# api-pause-3a — часы пауз: авто-старт requested вместо not_approved (канон 02 П.2)
Hash main: edd15c9 · Область: API (часы pause_ops) · Пачка pause-3: 3b → 3a.
Начинать после мержа api-pause-3b: проектор v9 применяет pause_started из requested. ШТАБ сверяет номера строк по свежему main.
Источник: docs/research/pause-3.md@e581539 (§1, §6, §8).

## 1. Паспорт
- id: api-pause-3a · Заголовок PR: «api-pause-3a: часы пауз — авто-старт заявки по молчанию Автора»
- Ветка: api-pause-3a · Режим: Р1 · Зависит от: api-pause-3b
- Миграция: нет · РЕВЬЮЕР: нет (DESIGNER §14: нет initData, 18+, согласий, rate-limit, ролей и GRANT, оплаты)

## 2. Цель
Сейчас часы гасят неодобренную заявку в дату начала (pause_start_failed not_approved, Р14). По канону 02 П.2 молчание Автора — авто-разрешение: заявка requested при now ≥ start_at проходит те же проверки, что одобренная, и стартует (pause_started) или получает отказ с настоящей причиной.

## 3. Решения (метка К-6)
- Ч1 requested при now ≥ start_at идёт тем же путём, что approved: _plan_start (вчерашний день закрыт, pause_days, бюджет, Этап, 24 ч, start_refusal) → pause_started или pause_start_failed с причиной. [канон 02 П.2; Автор, канон проверен 02 П.2]
- Ч2 Ветка «requested → pause_start_failed not_approved» (Ч6 api-pause-1b, Р14) удаляется. [Автор, канон проверен 02 П.2]
- Ч3 В _plan_start start_refusal получает status = pause_rules.STATUS_APPROVED (статус проверен в plan) — как API T3 и проектор v9. pause_rules.py не меняется. [ШТАБ-тех, pause-3 §1]
- Ч4 Кандидаты (_CANDIDATES, _PID_CANDIDATES уже берут requested), ключ pause_start:{pid}:{pause_id}, TickResult, итог тика в логе — как есть. [ШТАБ-тех]
- Ч5 Сообщение участнику об авто-старте — бот (T4); API не пишет outbox, kind, text_id. Миграции нет: часы ходят под ролью проектора. [Автор; pause-3 §4, §7]

## 4. Канон и решения
(а) 02 П.2: «… если Автор молчит до наступления даты начала — Бот ставит паузу сам + алерт Автору. Молчание Автора = авто-разрешение (не вредит Участнику).» 02 YAML: «on_author_silence: auto_approve_at_start_date». 02 П.3: «Пауза НЕ спасает уже горящий сегодняшний дедлайн» — поэтому сначала закрытие дня life_ops, потом пауза (проверка в _plan_start уже есть).
(б) Противоречий с DECISIONS.md нет.
(в) —
(г) Правок канона нет.

## 5. ЧТО ПРОЧИТАТЬ (Агент)
AGENT-BRIEF.md 17,1; docs/decisions/DECISIONS.md 7,7; эта карточка ≈ 7; apps/api/app/pause_ops.py 17,3; apps/api/app/pause_rules.py 7,2 (только чтение); apps/api/tests/test_pause_ops.py 13,0.
Чтение Агента ≈ 70 КБ. docs/architecture/** не открывать.

## 6. Файлы
Изменить: apps/api/app/pause_ops.py; apps/api/tests/test_pause_ops.py. Создать: нет. Удалить: нет.

## 7. Что сделать в pause_ops.py (строки по edd15c9, допуск ±3)
1. Константа после OUTCOME_*: «_START_STATUSES = ("requested", pause_rules.STATUS_APPROVED)» с комментарием «канон 02 П.2: молчание Автора — авто-старт (api-pause-3a)».
2. plan (274-294): удалить ветку 281-282 (requested → _failed not_approved). Условие 292 → «if pause.status in _START_STATUSES and _due(pause.start_at, now):» → _plan_start. Ветку active (283-291) не трогать.
3. _plan_start (228-271): «status=pause.status,» → «status=pause_rules.STATUS_APPROVED,»; docstring «A (Ч5, канон 02 П.2): approved или requested; вчерашний день закрыт → start_refusal → started или start_failed».
4. Docstring модуля:
   - строка 1: «… старт одобренных и неодобренных по молчанию Автора (канон 02 П.2), конец по сроку»;
   - п.1: «A — status approved или requested, start_at ≤ now»; строку «B — status requested …» удалить;
   - п.3: строку «B (Ч6) …» удалить; в A дописать «requested — тем же путём (api-pause-3a, канон 02 П.2)»;
   - строка «Источник»: добавить docs/tasks/api-pause-3a.md.
5. pause_rules.REASON_NOT_APPROVED в pause_ops больше не используется; импорт pause_rules остаётся (другие функции).

## 8. Контракт
Часы: pause_started {pause_id} — для requested и approved при now ≥ start_at, вчерашний день закрыт, проектор догнал pid, start_refusal = None; иначе pause_start_failed {pause_id, reason} из block_lives, state, gap_24h, stage_taken, no_budget. not_approved часы больше не пишут. Остальное — docs/tasks/api-pause-3b.md §8.

## 9. Задетые тесты (правило «Т») — apps/api/tests/test_pause_ops.py
- test_b_requested_not_approved → test_b_requested_auto_started: «TickResult(1, 0, 0, 0)»; события «[("pause_started", {"pause_id": pause_id})]»; после run_once статус "active", флаги ["pause_user"], бюджет 11; комментарий «B: requested при now ≥ start_at → авто-старт (канон 02 П.2)».
- test_two_ticks_one_event: «.failed == 1» → «.started == 1», «.failed == 0» → «.started == 0»; PausePlan again: pause_ops.OUTCOME_STARTED, key, "pause_start", "3650 days", "pause_started", {"pause_id": pause_id}.
- test_max_per_tick: «TickResult(0, 2, 0, 0)» → «TickResult(2, 0, 0, 0)»; «TickResult(0, 1, 0, 0)» → «TickResult(1, 0, 0, 0)»; ожидание «[("pause_started", {"pause_id": ids[2]})]».
- test_pending_event_skip, test_full_path, test_c_active_expired, test_author_shadow_not_candidates — не задеты.
Общие списки не меняются: новых видов ключей (TTL_BY_KIND), kind событий, text_id нет; test_pause_rules.py не задет.

## 10. Новые тесты (test_pause_ops.py, фикстуры файла)
- test_a_refused_start_failed: добавить «@pytest.mark.parametrize("status", ["approved", "requested"])» и «_pause(db_engine, pid, status=status)»; ожидания те же (reason, после run_once — cancelled; для requested проверяет Д4 карточки 3b).
- test_b_requested_yesterday_open_skip: _active(started=YESTERDAY), заявка requested → «TickResult(0, 0, 0, 1)», событий нет, ключа pause_start нет.
Цель: bash tools/check.sh api. Тесты с БД — только CI.

## 11. Живые проверки (после мержа 3a; 3b и 3a — одним образом projector, PLAN §4)
- Бэкап не нужен: миграции нет.
- Логи projector после выката: Traceback 0, WARNING 0.
- dry-run pause_ops для тестового pid с заявкой requested и прошедшим start_at: decision_if_now — «pause_started {...}» или pause_start_failed с причиной, но не not_approved. Команды — ШТАБ по infra/SERVER-IRONCLAD.md (projector once рядом с run запрещён).
- Живой авто-старт — только на тестовом участнике и с согласия Автора.

## 12. Запреты
AGENT-BRIEF §3. Плюс: projector.py, pause_rules.py, routers/pause.py, day_keys.py, миграции не трогать; outbox, новых kind и text_id нет; лог без pid, tz, payload.

## 13. Готово, когда
CI зелёный; часы стартуют requested по тем же правилам, что approved; not_approved не пишется; тесты разделов 9–10 есть; в описании PR — отличия от карточки или «нет».

## 14. Оценка
Часы Автора ≈ 0,5. Кредиты ≈ 400, стоп 600.

## 15. РЕВЬЮЕР
Нет.
