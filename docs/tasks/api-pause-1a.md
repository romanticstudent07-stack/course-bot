# api-pause-1a — T2a: правила пауз и проектор v8 (паузы участника Р-6а)
Hash main: edbd726 · Область: API (проектор) · Пара: T2a → T2b (docs/tasks/api-pause-1b.md), один промпт, строго по очереди (обе правят projector.py).
Оценка пары: 1 300 кредитов, стоп 1 950. РЕВЬЮЕР: нет (DESIGNER §14: нет миграций и GRANT, initData, оплаты).
Миграция: не нужна (по коду: ШТАБ З2 п.4 — CHECK на participant_state.status_flags нет; права — 0018).
Источник: docs/research/pause-2.md §2, §5, §6 (строка T2), §8 А1 и А3; решения З1/З2 этого окна.
Раздел 5 «Контракт T3/T4» — нормативный для карточек T3 api-pause-2 и T4 bot-pause-1.

## 1. Зачем
Участник берёт паузу курса (Mini App, с завтра, 1–7 дней). Во время паузы дней, напоминаний, таймеров и списаний жизней нет; после неё день, не сделанный до паузы, выдаётся заново с 00:00. Бюджет — 14 дней за годовой цикл, одна пауза на Этап, между паузами ≥ 24 ч. T2a — правила и применение событий в проекторе; часы (кто пишет pause_started / pause_ended expired) — T2b.

## 2. Решения (метка К-6 у каждого)
- Р1 Сигнал — события participant_events; строку participant_pauses проектор меняет только UPDATE `... WHERE id = :pause_id AND pid = :pid AND kind = 'user' AND status = <ожидаемый>` (права 0018: UPDATE (status, stage_no, restart_no, ended_at), INSERT нет). Смена статуса, флаг и фаза — в одном SAVEPOINT события. [канон: 0018 docstring «статус пишет только проектор (бот и API пишут события)»; E1/INV-1; I2 user_pause_quota — pause-2 §6]
- Р2 approved → active — по событию pause_started, его пишут часы T2b. [ШТАБ-тех; pause-2 §9 «роль часов run_forever»]
- Р3 «С завтра»: start_at = day_clock.next_midnight(время запроса, tz), planned_end_at = 00:00 местной даты (start + N), 1 ≤ N ≤ 7. Считает API (T3) при записи строки; проектор и часы проверяют через pause_rules.pause_days. [канон 02 П.1, I2 user_pause 7d — pause-2 §2]
- Р4 Вход: флаг pause_user, фаза — phase_for_flags (pause_user уже в SLEEP_FLAGS); жизни и таймеры стоят без правок: life_ops, НП1, НП3, лестница отсекают BLOCKING_FLAGS (в нём pause_user). [канон 10-02 pause_user freezes [timers, lives] — pause-2 §2; по коду: ШТАБ З2 п.4]
- Р5 Выход по сроку (reason expired): D = day_clock.last_midnight(at, tz) при at ≥ planned_end_at (обычно = planned_end_at; после простоя сервера — сегодняшняя 00:00, без штрафа за простой). Возврат 0. [Автор А1; ШТАБ-тех]
- Р6 Выход досрочный (reason by_participant): D = day_clock.next_midnight(at, tz); возврат = (местная дата planned_end_at − местная дата D), не меньше 0; день нажатия потрачен. [ШТАБ, pause-2 §6; Автор А1]
- Р7 На выходе — reissue_day(conn, pid, target = текущая позиция participant_state, at, tz, day_start = D): позиция та же, missed_streak 0, day_started_at = D. [Автор А1; pause-2 §5]
- Р8 Бюджет: остаток ≤ 14 (BUDGET_DAYS), списание N при старте, возврат по Р6 — только если пауза начата в текущем цикле (start_at ≥ cycle_start_at после ленивой смены цикла), остаток не выше 14. [Автор А3; ШТАБ-тех]
- Р9 Годовщина — лениво, по at события: дата cycle_start (местная) + 1 год, 00:00 по поясу; 29.02 → 28.02; at ≥ годовщины → остаток 14, cycle_start = годовщина (повторять, пока at ≥ следующей). Крона нет. [Автор А3; pause-2 §6]
- Р10 Пауза Этапа одна: у pid нет паузы в статусе active или ended с тем же (stage_no, restart_no); индекс participant_pauses_stage_taken_uq — страховка. stage_no — Этап текущей позиции, restart_no — из pause_budgets; оба пишет проектор при pause_started. [Автор А3; 0018]
- Р11 restart_paid уже сбрасывает бюджет (UPSERT pause_budgets: 14, новый цикл, restart_no + 1) — оба лимита сброшены; не править, только тест. [по коду: SQL projector v6, прочитан в З1; DECISIONS Р-20]
- Р12 Строку pause_budgets новым участникам создаёт проектор в _apply_day_entered: INSERT … ON CONFLICT (pid) DO NOTHING; остаток 14, cycle_start_at — та же формула, что BACKFILL 0018 (00:00 по поясу в дату первой 04:00 первого дня), restart_no — как в бэкфилле 0018. tz — RETURNING в SQL позиции или SELECT, по коду. Запасной путь: строки нет при pause_started — создать там же тем же SQL. Закрывает вопрос сервера 16.11 №5. [ШТАБ-тех; Автор А3]
- Р13 block_lives запрещает старт паузы. [канон 10-02 forbidden pairs [pause_user, block_lives] — pause-2 §1]
- Р14 Одобрение после start_at — заявка сгорает (cancelled), участник подаёт заново. Проектор: pause_approved при at ≥ start_at → cancelled; часы T2b: requested при now ≥ start_at → pause_start_failed not_approved. [Автор 18.11, канон молчит: pause-2 §2–§3]
- Р15 Повторная проверка в проекторе: pause_started с нарушенным правилом → статус cancelled, флаг не ставится, WARNING без ПДн («pause_started отклонён: <reason>»). Часы проверяют то же до записи события. [ШТАБ-тех]

## 3. Что уже в main (использовать, не дублировать)
По коду edbd726: 0018 (participant_pauses, pause_budgets, права, бэкфилл), 0019_life_writeoffs; проектор v7 — phase_for_flags, SLEEP_FLAGS, block_lives, reissue_day, life_op, restart_paid (v6), revive_by_author (v7). Образец ветки события — _apply_restart_paid и _apply_revive_by_author (разбор payload → SAVEPOINT → UPDATE). Плохой payload и «не тот статус» — как у существующих видов (пропуск и счётчик «пропущено», по коду).
reissue_day сейчас всегда ставит D = next_midnight(at, tz) (по коду: ШТАБ З2 п.4).

## 4. Что сделать
### 4.1 apps/api/app/pause_rules.py — новый, чистые функции (без БД, aware datetime, naive → ValueError, сравнения в UTC как day_clock)
- BUDGET_DAYS = 14, MAX_DAYS = 7, MIN_GAP = timedelta(hours=24).
- anniversary(cycle_start_at, tz) → datetime: Р9.
- roll_cycle(cycle_start_at, days_left, at, tz) → (cycle_start_at, days_left): Р9.
- pause_days(start_at, planned_end_at, tz) → int: оба — 00:00 по поясу, разность местных дат 1..7, иначе ValueError (точные 7 местных суток; CHECK 0018 — 169 ч).
- refund_days(planned_end_at, day_start, tz) → int ≥ 0: Р6.
- start_refusal(*, status, flags, phase, day_no, days, days_left, stage_taken, last_ended_at, start_at) → str | None. Порядок причин фиксирован: not_approved (status ≠ approved) → block_lives (Р13) → state (фаза ≠ active, или day_no IS NULL, или у pid уже есть активная пауза) → gap_24h (last_ended_at есть и start_at − last_ended_at < MIN_GAP) → stage_taken → no_budget (days_left < days).

### 4.2 apps/api/app/projector.py — PROJECTOR_VERSION 7 → 8, новые виды
Payload: pause_id — int (не bool) ≥ 1; reason — строка из списка. Строка паузы ищется по (id, pid, kind 'user').
| kind | из статуса | в статус | ещё |
|---|---|---|---|
| pause_approved {pause_id} | requested | approved; при at ≥ start_at — cancelled (Р14) | — |
| pause_rejected {pause_id} | requested | rejected | — |
| pause_cancel {pause_id} | requested, approved | cancelled | — |
| pause_start_failed {pause_id, reason} | requested, approved | cancelled | reason из раздела 5 |
| pause_started {pause_id} | approved | active | roll_cycle по at; start_refusal (Р15); stage_no, restart_no; days_left −= N (UPDATE … WHERE days_left >= N); флаг pause_user; фаза phase_for_flags |
| pause_ended {pause_id, reason} | active | ended | ended_at = at; снять pause_user; фаза; D по Р5/Р6; reissue_day(…, day_start = D); возврат по Р6/Р8 |
pause_ended expired при at < planned_end_at — пропуск с WARNING. pause_ended by_participant при D ≥ planned_end_at — возврат 0.
Статусы rejected и cancelled — по CHECK 0018. Если какого-то значения в CHECK нет — стоп, вопрос ШТАБу (миграцию не писать).

### 4.3 reissue_day — новый необязательный параметр day_start: datetime | None = None
None → как сейчас (next_midnight(at, tz)); вызовы restart_paid и revive_by_author не меняются.

### 4.4 _apply_day_entered — строка pause_budgets по Р12.

### 4.5 Docstring проектора — версия 8, виды пауз, ссылка на эту карточку.

## 5. Контракт T3/T4
Статусы participant_pauses (kind user): requested → approved | rejected | cancelled; approved → active | cancelled; active → ended. Статус пишет только проектор (кроме INSERT строки API).
| Кто | Что пишет | Когда |
|---|---|---|
| API (T3) | INSERT participant_pauses: kind 'user', status 'requested', start_at, planned_end_at (Р3), client_op_id | заявка; перед INSERT — pause_rules: pause_days, roll_cycle (остаток для показа, без записи), start_refusal с status = 'approved' (заявка с причиной → 409 с этой причиной). Повтор с тем же op — по client_op_id; второй открытый запрос → UniqueViolation → 409 |
| API (T3) | событие pause_cancel {pause_id} | «Отменить» до старта |
| API (T3) | событие pause_ended {pause_id, reason: "by_participant"} | «Продолжить» во время active |
| Бот (T4) | события pause_approved {pause_id}, pause_rejected {pause_id} (actor owner) | кнопки Автора; перед записью бот проверяет status = requested и now < start_at, иначе отвечает «заявка устарела» и событие не пишет |
| Часы (T2b) | pause_started {pause_id} | approved, now ≥ start_at, вчерашний день закрыт, проектор догнал pid, start_refusal = None |
| Часы (T2b) | pause_start_failed {pause_id, reason} | requested при now ≥ start_at → not_approved; approved с отказом start_refusal → его reason |
| Часы (T2b) | pause_ended {pause_id, reason: "expired"} | active, now ≥ planned_end_at |
reason у pause_start_failed: not_approved, block_lives, state, gap_24h, stage_taken, no_budget.
Остаток для показа: pause_budgets.days_left после pause_rules.roll_cycle(…, now) — только чтение.
Уведомления (outbox) T2 не пишет; T4 сам выбирает, на какие события и смены статуса слать (одобрено, отклонено, сгорела, началась, закончилась).
Ключи часов: виды pause_start / pause_end — docs/tasks/api-pause-1b.md.

## 6. Файлы (≤ 12)
Новые: apps/api/app/pause_rules.py; apps/api/tests/test_pause_rules.py; apps/api/tests/test_projector_pause.py.
Правка: apps/api/app/projector.py; тесты с версией — раздел 7.

## 7. Задетые тесты (правило «Т»)
PROJECTOR_VERSION 7 → 8. Кандидаты (ШТАБ сверит по коду до промпта; строку projector_version содержат 13 файлов, список — у ШТАБа): tests/test_projector_v3.py, test_projector_day_entered.py, test_projector_tz.py, test_projector_sleep.py, test_projector_restart.py, test_projector_revive.py. Правка — только ожидаемая версия.
Не задеты (по коду: ШТАБ З2 п.4): test_projector_sleep.py:51 (SLEEP_FLAGS не меняем), test_life_ops.py:408 (BLOCKING_FLAGS не меняем). REISSUE_KINDS и TTL_BY_KIND — T2b.

## 8. Новые тесты (фикстуры — по образцу tests/test_projector_restart.py)
test_pause_rules.py: anniversary (обычная дата; 29.02 → 28.02; пояс с переводом часов); roll_cycle (до годовщины, ровно в 00:00, через 2 года); pause_days (1 и 7 — ок; 0, 8, не 00:00 — ValueError; 7 суток через переход на летнее время); refund_days (нажал в первый день, в последний — 0); start_refusal — каждая причина и порядок.
test_projector_pause.py: путь requested → approved → active → ended expired (флаг, фаза sleeping, остаток 14 − N, D = planned_end_at, missed_streak 0, позиция та же); by_participant (возврат по Р6; день нажатия не возвращается); поздний pause_approved → cancelled; pause_started при block_lives / no_budget / stage_taken / gap_24h → cancelled, флага нет; повтор события — без двойного списания; годовщина во время паузы → возврата нет; day_entered создаёт pause_budgets один раз (второй day_entered не меняет); restart_paid → пауза того же Этапа снова разрешена; reissue_day без day_start — как в v7.

## 9. Чтение Агента (T2a)
AGENT-BRIEF.md 17,1; docs/decisions/DECISIONS.md 7,7; эта карточка ≈ 12; apps/api/app/projector.py 54,9 (целиком); apps/api/app/day_clock.py 11,8; apps/api/migrations/versions/2026_11_16_1200-0018_pauses_pauses.py 14,5; apps/api/tests/test_projector_restart.py 10,8. Итого ≈ 129 КБ. docs/architecture/** не открывать.

## 10. Готово, когда
CI зелёный; PROJECTOR_VERSION = 8; все виды раздела 4.2 применяются по таблице; SQL записи в participant_state — только в projector.py (test_projector_static); вызовы reissue_day из v6/v7 не изменены; в описании PR — список отличий от карточки или «нет».

## 11. Вне задачи
kind author и shadow, /pause_grant, /unpause_user — Панель (Автор В3, pause-2 §2). Эндпоинты — T3. Уведомления и кнопки — T4. Часы — T2b.

## 12. Прочитано (ПРОЕКТИРОВЩИК, З1–З2)
DESIGNER.md, PACK.md, STATE.md, AGENT-BRIEF.md, DECISIONS.md, CANON-CHECK.md, research/pause-2.md — целиком; 0018 — целиком; projector.py — ≈ 20 КБ из 54,9 (docstring, SQL, разборщики payload), тела функций — по выписке ШТАБа З2 п.4; day_clock.py — целиком (next_midnight, last_midnight, is_overdue); life_ops.py — шапка (BLOCKING_FLAGS — по ШТАБу З2). docs/architecture/** не открывался (канон — pause-2).
