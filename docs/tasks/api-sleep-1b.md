# T6a-2 api-sleep-1b — restart_paid, перевыдача дня с 00:00, третий запуск НП3 (projector v6)
Hash main 19ce64d. Основа — docs/research/sleep-1.md@19ce64d §2 Р6–Р9, §3 карточка 2. Правило К — docs/process/CANON-CHECK.md. Сначала прочитай docs/decisions/DECISIONS.md целиком.

## 1. Паспорт
- id: T6a-2 api-sleep-1b · PR: «api-sleep-1b: restart_paid, reissue_day, НП3 после перевыдачи (projector v6)» · ветка: feat/api-sleep-1b
- Режим: Р1 (Агент). Зависит от: T6a-1 api-sleep-1a (#236, смержен). Миграций нет. Одна область — API.

## 2. Цель
Проектор применяет новый kind restart_paid: снимает block_lives, ставит 3 жизни, выдаёт день 1 модуля 1 текущего Этапа с D = следующая 00:00 по поясу после at события, заново заводит бюджет пауз (14, цикл с D, restart_no + 1). НП3 «Задания откроются …» уходит и после перевыдачи, текст выбирается по дате. PROJECTOR_VERSION 5 → 6.

## 3. Решения (дословно; метка К-6)
- Р-20 (DECISIONS.md): «день после выхода из sleeping, revive, /revert, рестарта — с 00:00 по поясу (кнопки 04:00, дедлайн 00:00)»; «из block_lives — рестарт по промокоду (Р-1/Р-2; день 1 модуля 1 текущего Этапа, 3 жизни, лимиты пауз сброшены; имя restart_paid прежнее)» [Автор, канон проверен — pause-2 §5 через sleep-1 §2].
- Р-6а: «не больше 14 дн. за годовой цикл (с 00:00 первого дня задания, бюджет снова 14 в годовщину)» [Автор].
- Автор 15.11 (sleep-1 Р8): третий запуск НП3 после перевыдачи, текст по дате [Автор, check §2].
- ШТАБ 16.11 (К-5): Ш2 — «D из at события (next_midnight(at, tz)), не из payload»; Ш3 — «pause_budgets UPSERT в restart_paid»; Ш5 — «/life при sleeping по паузе в T2, не здесь» [ШТАБ-тех].
- ШТАБ 17.11: новый kind меняет проекцию → PROJECTOR_VERSION 6 [ШТАБ-тех].

## 4. Выдержки (КОДЕР канон не читает)
- sleep-1 Р6: «reissue_day(conn, pid, target, at, tz) — внутренняя функция проектора; не событие и не day_entered: позиция = target, missed_streak 0, day_started_at = D = day_clock.next_midnight(at, tz). next_midnight — новая функция: первая 00:00 по поясу строго позже at, через _at_local. … До 04:00 даты D окно not_active: часы не закрывают день, НП1 и лестницы нет».
- sleep-1 Р7: «применяется, если в status_flags есть block_lives и stage_no не NULL, иначе пропуск. … lives 3; block_lives снимается; фаза по Р2; reissue_day(текущий stage, 1, 1); pause_budgets UPSERT — остаток 14, cycle_start_at = D, restart_no + 1. … payload должен быть dict; grant_id проектор не читает».
- sleep-1 Р8: «событие из REISSUE_KINDS (сейчас restart_paid; T7 и T2 дополнят), для которого next_midnight(at, tz) = D. … местная дата active_from(D) равна местной дате now → «сегодня», иначе «завтра». … Для двух старых запусков остаётся choose_text».
- sleep-1 Р9: «Для рестарта cycle_start_at = D: D уже 00:00».
- Р2 в коде (projector.phase_for_flags, v5): muted/erased не меняются; есть флаг из SLEEP_FLAGS → sleeping; sleeping без флагов сна → active; иначе фаза прежняя.
- 0018_pauses@19ce64d — pause_budgets: pid uuid PK, FK → tg_user_registry.pid; days_budget_remaining_annual smallint NOT NULL, CHECK «IS NOT NULL AND >= 0»; cycle_start_at timestamptz NOT NULL; restart_no smallint NOT NULL DEFAULT 0, CHECK «IS NOT NULL AND >= 0». Права app_projector (PRIVILEGES, сверено дословно): SELECT (pid, days_budget_remaining_annual, cycle_start_at, restart_no), INSERT (те же), UPDATE (days_budget_remaining_annual, cycle_start_at, restart_no). SQL из docstring 0018 — брать дословно:
    INSERT INTO pause_budgets (pid, days_budget_remaining_annual, cycle_start_at, restart_no)
    VALUES (:pid, :d, :c, :r) ON CONFLICT (pid) DO UPDATE SET
    days_budget_remaining_annual = EXCLUDED.days_budget_remaining_annual,
    cycle_start_at = EXCLUDED.cycle_start_at, restart_no = EXCLUDED.restart_no
- CHECK participant_state (0007, по старту ШТАБа и комментарию MAX_LIVES в projector.py): ck_participant_state_day_position — stage_no, module_no, day_no, day_started_at все NULL или все заданы; ck_participant_state_lives_range — lives 0..3.

## 5. ЧТО ПРОЧИТАТЬ (Агент)
Целиком: AGENT-BRIEF.md 17,1; docs/decisions/DECISIONS.md 7,7; эта карточка ≈12; apps/api/app/projector.py 44,6; apps/api/app/day_clock.py 11,2; apps/api/app/notify_ops.py 22,4. Итого целиком ≈115 КБ.
Только выдержки по grep (целиком не читать): apps/api/app/life_ops.py 17,7 — «_CANDIDATES|_STATE|_eligible|_PENDING_EVENT|BLOCKING_FLAGS|def tick»; apps/api/app/notify_ladder.py 15,7 — «def tick_ladder|WINDOW_OPEN|day_marks»; apps/api/tests/test_projector_sleep.py — фикстуры состояния и прогона проектора (образец для новых тестов); apps/api/tests/test_notify_ladder.py — как фикстура вставляет day_marks; четыре файла из «Задетых тестов» — «PROJECTOR_VERSION|projector_version». Итог чтения Агента ≈125 КБ (меньше 140).

## 6. Файлы
- Изменить: apps/api/app/projector.py, apps/api/app/day_clock.py, apps/api/app/notify_ops.py; тесты из раздела «Задетые тесты».
- Создать: apps/api/tests/test_projector_restart.py, apps/api/tests/test_reissue_future_day.py.
- Удалить: нет.

## 7. Контракт
7.1 day_clock.next_midnight(at: datetime, tz: str | None) -> datetime — первая 00:00 по поясу строго позже at. Код: _require_aware(at); z = zone(tz); at_u = _utc(at); day = at_u.astimezone(z).date(); cand = _at_local(day, DEADLINE_TIME, z); если cand <= at_u → _at_local(day + 1, DEADLINE_TIME, z). Возврат — cand.astimezone(z), как у last_midnight. naive → ValueError. Если 00:00 нет из-за перевода часов, правило то же, что у _at_local (момент перехода).
7.2 projector.py:
- PROJECTOR_VERSION = 6; EVENT_KIND_RESTART_PAID = "restart_paid"; PAUSE_BUDGET_DAYS = 14 (Р-6а); RESTART_LIVES = MAX_LIVES.
- reissue_day(conn, pid, target: tuple[int, int, int], at: datetime, tz: str | None) -> datetime: D = day_clock.next_midnight(at, tz); UPDATE participant_state SET stage_no, module_no, day_no = target, day_started_at = D, missed_streak = 0, updated_at = now(), projector_version WHERE pid = :pid RETURNING pid; возвращает D. Фаза, флаги, жизни и author_pause_reason не упоминаются. Это не событие и не day_entered.
- _apply_restart_paid(conn, event_id, pid, kind, at, payload). Порядок: (1) _payload_dict(payload) is None или at is None → «bad payload»; (2) SELECT lifecycle_phase, status_flags, stage_no, tz FROM participant_state WHERE pid: нет строки → «no state»; нет block_lives или stage_no IS NULL → «restart: not blocked or no position»; (3) flags = status_flags без block_lives; phase = phase_for_flags(phase, flags); UPDATE SET lives = 3, status_flags = CAST(:flags AS text[]), lifecycle_phase = :phase, updated_at, projector_version WHERE pid AND 'block_lives' = ANY(coalesce(status_flags, CAST('{}' AS text[]))) AND stage_no IS NOT NULL RETURNING pid; (4) D = reissue_day(conn, pid, (stage_no, 1, 1), at, tz); (5) SELECT restart_no FROM pause_budgets WHERE pid; r = (restart_no или 0) + 1; UPSERT из раздела 4 дословно с d = 14, c = D, r. Всё в одном SAVEPOINT события; пропуск → _skip, событие не применено.
- _apply_event: ветка kind restart_paid → _apply_restart_paid (нужны at и payload).
- Docstring модуля: kind restart_paid, версия 6, reissue_day, pause_budgets (права 0018).
7.3 notify_ops.py:
- EVENT_KIND_RESTART_PAID = "restart_paid" (совпадает с projector; импорта проектора нет); REISSUE_KINDS = (EVENT_KIND_RESTART_PAID,).
- choose_text_reissue(started, tz, now) -> str: day_clock.active_from(started, tz).date() == _local(now, tz).date() → TEXT_TODAY, иначе TEXT_TOMORROW.
- is_reissue(started, tz, ats) -> bool: есть at из событий REISSUE_KINDS pid, для которого _utc(day_clock.next_midnight(at, tz)) == _utc(started).
- decide(…, reissued: bool = False): если нет ключа очереди и нет entered, но reissued → send/late по is_late; иначе как сейчас.
- Новые запросы: _REISSUE_ALL — SELECT pid, at FROM participant_events WHERE kind = ANY(CAST(:kinds AS text[])) AND pid = ANY(CAST(:pids AS uuid[])); _REISSUE_ONE — то же для одного pid. Используются в _candidates и _plan; _ENTERED_* не меняются.
- _write: текст choose_text_reissue — только если сработал третий запуск (нет ключа очереди и нет entered); для двух старых запусков — choose_text. Ключ tasks_open:{pid}:{dsa(D)} и outbox — как сейчас.
7.4 Лог: только id и kind события; pid, tz, payload и D в лог не идут.

## 8. БД
Миграций нет. Нужны 0018 (pause_budgets и права app_projector) и 0019 (life_writeoffs у v5). expected_tables.txt не меняется.

## 9. Тесты
Урок 16.11: в любой фикстуре participant_state либо задана вся позиция (stage_no, module_no, day_no, day_started_at), либо вся позиция NULL; lives 0..3. Сценарии вроде «stage задан, day_started_at NULL» или «lives 4» — запрещены (их нет и ниже).
test_projector_restart.py (с БД, CI):
- R1: sleeping, lives 0, {block_lives}, позиция (2, 3, 5, старый dsa), tz Europe/Moscow, строки pause_budgets нет → после события: lives 3, flags {}, active, позиция (2, 1, 1), day_started_at = next_midnight(at, tz), missed_streak 0, projector_version 6; в pause_budgets строка (14, D, 1).
- R2: как R1, но строка pause_budgets (5, старая дата, 0) → (14, D, 1).
- R3: {pause_user, block_lives} → flags {pause_user}, фаза sleeping (Р2), день всё равно перевыдан.
- R4: active, lives 2, флагов нет, позиция задана → пропуск, строка и pause_budgets без изменений.
- R5: sleeping, lives 0, {block_lives}, вся позиция NULL (законно по CHECK) → пропуск «no position».
- R6: нет строки состояния → пропуск; payload — список или не-JSON → «bad payload».
- R7: второй restart_paid после применённого первого → пропуск, restart_no остаётся 1.
- R8 (статически): текст UPSERT pause_budgets совпадает с docstring 0018 (нормализация пробелов).
- R9 (чисто): next_midnight — Asia/Vladivostok, at 2026-11-20T13:30Z → 2026-11-20T14:00Z; at ровно 00:00 по поясу → следующие сутки; America/Santiago, at 2026-09-05T12:00Z → 2026-09-06T04:00Z; naive → ValueError.
- R10: EVENT_KIND_RESTART_PAID в notify_ops == в projector; restart_paid входит в REISSUE_KINDS.
test_reissue_future_day.py (с БД; сначала событие restart_paid проводится проектором):
- F1: life_ops.tick(engine, now) при at < now < D и при D ≤ now < active_from(D) → нет day_closed, нет life_op, нет ключа day_close.
- F2: notify_ops.tick_noon при 12:30 по поясу в день рестарта (рестарт 09:00, D — следующая 00:00) → 0 outbox noon_nudge.
- F3: notify_ladder.tick_ladder в тот же now с отметкой day_marks на D (фикстура как в test_notify_ladder.py) → 0 outbox ladder_reminder.
- F4: НП3 — рестарт в 10:00 по поясу, tick_tasks_open через 5 мин → sent 1, text_id TEXT_TOMORROW; повторный tick → sent 0 (ключ).
- F5: рестарт в 01:00 по поясу → TEXT_TOMORROW (choose_text дал бы «сегодня»).
- F6: рестарт в 23:58, tick в 00:01 → TEXT_TODAY; tick после 04:00 даты D без прошлого НП3 → late: ключ есть, outbox нет.
- F7 (чисто): choose_text_reissue и is_reissue на случаях F4–F6; at, для которого next_midnight ≠ D → False.
Задетые тесты (правило «Т»):
- test_projector_v3.py, test_projector_day_entered.py, test_projector_tz.py, test_projector_sleep.py: везде PROJECTOR_VERSION == 5 и projector_version = 5 → 6 (по старту ШТАБа; строки сверяет ШТАБ до промпта).
- test_notify_ops.py — кандидат, сверяет ШТАБ до промпта (фейковые conn в _candidates и _plan получают новый запрос _REISSUE_*; новая константа).
- test_day_clock.py — кандидат, сверяет ШТАБ до промпта (если тест сверяет список функций модуля).
- test_projector_static.py — кандидат, сверяет ШТАБ до промпта (новый INSERT pause_budgets в проекторе).
- test_projector.py — кандидат, сверяет ШТАБ до промпта (пример «unknown kind» не должен быть restart_paid).
- test_day_current.py::test_kinds_and_ttl — не задет: новых kind ключей нет (НП3 пишет tasks_open).
Цели: bash tools/check.sh api. Только CI: все тесты с БД (R1–R8, F1–F6).

## 10. Выкат (после мержа; ШТАБ 17.11: projector v5 + T6a-2 одним разом)
- Г0: DC ps → 7/7 Up; alembic current через сервис migrate (как в прошлых выкатах) → 0019_life_writeoffs. Если ниже — стоп, к ШТАБу: v5 без 0019 и v6 без 0018 упадут с ProgrammingError, и проектор встанет.
- Бэкап до выката не нужен: миграций нет (ежесуточный cron работает).
- projector: DC build projector, затем DC up -d projector; DC logs --since 10m projector → «lock acquired, running (version 6)», «backfill block_lives, строк N» (N любое), Traceback 0.
- api: код api не меняется, day_clock только дополняется → api не пересобирать. Если api импортирует day_clock, пересборка безвредна; решает ШТАБ.
- restart_paid живьём проверить нельзя: писателя (бот, T6b) ещё нет.

## 11. Запреты
AGENT-BRIEF §3. Плюс: не писать событие restart_paid из api или бота; не менять life_ops.py, notify_ladder.py и миграции; не брать D из payload; не трогать author_pause_reason, muted и erased; /life при sleeping по паузе не делать (Ш5 → T2); grant_id не читать; не логировать pid, tz, payload.

## 12. Критерии готовности
Разделы 7 и 9 выполнены; check.sh api зелёный; R1–R10 и F1–F7 есть; правки только в файлах раздела 6; описание PR — по AGENT-BRIEF §10.

## 13. Оценка
Часы Автора ≈0,5 (мерж и выкат). Кредиты: sleep-1 §3 1 100 + задетые 4–6 × 60–100 ≈1 500, стоп 2 250.

## 14. РЕВЬЮЕР: нет
initData, 18+, согласия, rate-limit, роли/GRANT и оплату не трогает (GRANT уже выдан в 0018).

## Канон и решения
(а) Используется: Р-20 и Р-6а (DECISIONS.md); канон I2 и 02/03 — через research pause-2 §4–§5 и sleep-1 §2 (docs/architecture в этом окне не читался).
(б) Противоречий с DECISIONS.md нет: «повторная оплата» (02 §2.4) уже снята Р-20.
(в)–(г) Правок канона нет.
