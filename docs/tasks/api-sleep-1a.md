# T6a-1 api-sleep-1a — проектор v5: block_lives, sleeping, /life, life_writeoffs

## 1. Паспорт
- id: api-sleep-1a (T6a-1, PLAN §5 п.20). Ветка Агента: feat/api-sleep-1a.
- Заголовок PR: «api-sleep-1a: проектор v5 — block_lives, sleeping, life_op от /life, life_writeoffs».
- Режим: Р1 (Агент). Зависит от: db-pause-1 (0018) и db-pause-2 (0019) — смержены, на сервере с 16.11 (alembic 0019_life_writeoffs). Миграций в задаче нет.
- Основа: docs/research/sleep-1.md §2 Р1–Р5, §3 (карточка 1). Р6–Р9 (reissue, restart_paid, НП3, next_midnight) — НЕ здесь, это T6a-2 после мержа.
- Правило К — docs/process/CANON-CHECK.md. Сначала прочитай docs/decisions/DECISIONS.md целиком.

## 2. Цель
Проектор v5: при 0 жизней ставит флаг block_lives и фазу sleeping (с бэкфиллом старых строк); принимает life_op от команды /life (reason author_cmd, ±N без дня); при списании по часам пишет строку в журнал life_writeoffs (0019) для будущего revive (T7).

## 3. Решения Автора (дословно, docs/decisions/DECISIONS.md)
- Р-20 (15.11) — «жизни и рестарт (полностью — R-2026-11-15.md): … /life в строю день не трогает, при 0 — отказ; из block_lives — рестарт по промокоду … или revive (min(3, 1 + возврат §2.6), команда бота, после 0019)».
- Решения ШТАБа 16.11 (метка «ШТАБ 16.11», К-5): Ш1 — reason life_op от /life = 'author_cmd'; Ш3 — права app_projector на pause_budgets уже в 0018, pause_budgets — в T6a-2; Ш4 — выкат 0018 → 0019 → projector v5, 0018 и 0019 уже на сервере; Ш5 — /life при sleeping по паузе — в T2; Ш6 — IntegrityError на INSERT life_writeoffs откатывает весь life_op, риск принят, WARNING с id события.

## 4. Выдержки (канон — через docs/research/sleep-1.md@42d9d69, К-2 через pause-2 §4–§5)
- I2 (pause-2 §4): флаги сна SLEEP_FLAGS = pause_user, author_pause, pause_shadow, block_lives, ban_mod; freeze_unpaid — не фаза. Выход из sleeping — «pause_removed_and_lives_ok» → active.
- pause-2 §4, Р-20: life_op, после которого lives = 0, ставит block_lives.
- 03 §3.6 (через pause-2 §5): /life позицию и день не трогает.
- 02 §2.6, 0019 (docstring): журнал списаний life_ops (delta −1) с позицией дня; /life −N в журнал не пишется; бэкфилла журнала нет.

## Канон и решения
(а) Используется: I2 fsm_participant и флаги сна (pause-2 §4); 03 §3.6; 02 §2.6; Р-20.
(б) Противоречий с DECISIONS.md нет.
(в) Правок канона нет. Кандидат DOCS (сверяет ШТАБ): имя reason 'author_cmd' (Ш1) сверить с I2 — есть ли там своё имя reason у life_op от /life.
(г) Правок канона нет. ДК-1, ДК-2 из sleep-1 §5 — DEFECTS-кандидаты ШТАБа, в задачу не входят.

## Решения задачи (метка К-6)
- Р1 PROJECTOR_VERSION = 5 [ШТАБ-тех, pause-2 §6].
- Р2 SLEEP_FLAGS = ("pause_user", "author_pause", "pause_shadow", "block_lives", "ban_mod") [канон I2 через pause-2 §4]. Чистая функция phase_for_flags(phase, flags) -> str: phase в (muted, erased) → phase; есть флаг из SLEEP_FLAGS → "sleeping"; флагов сна нет и phase == "sleeping" → "active"; иначе phase. Фаза пересчитывается ТОЛЬКО в UPDATE, который меняет флаги; в этой задаче это только life_op до 0 (флаг block_lives → sleeping). Переход onboarding → active не делать. Функцию использует T6a-2.
- Р3 block_lives [pause-2 §4; Р-20]: обе ветки life_op — если lives + delta = 0: status_flags = array_append(…, 'block_lives') только если флага ещё нет, lifecycle_phase = 'sleeping'. Бэкфилл — функция _backfill_block_lives(engine) -> int, своя транзакция engine.begin(), один UPDATE: SET status_flags = array_append(coalesce(status_flags, CAST('{}' AS text[])), 'block_lives'), updated_at = now(), projector_version = :version WHERE lifecycle_phase = 'sleeping' AND lives = 0 AND NOT ('block_lives' = ANY(coalesce(status_flags, CAST('{}' AS text[])))). Вызов: run_once — после взятия lock, до _drain; run_forever — сразу после «lock acquired», до внутреннего цикла. Ошибки не глушить. Лог INFO «projector: backfill block_lives, строк N» — только число. По серверу 16.11 строк в sleeping 0.
- Р4 life_op в две ветки [pause-2 §5; Р-20; ШТАБ 16.11 Ш1]. Ветвление по payload.reason.
  (а) reason "missed_days": life_op_from_payload, LIFE_OP_DELTAS, LIFE_OP_REASON — имена, сигнатура и поведение прежние. _APPLY_LIFE_OP: добавить Р3 и RETURNING pid, stage_no, module_no, day_no; WHERE прежний. Текст WARNING при 0 строк прежний.
  (б) reason "author_cmd" (новая константа LIFE_OP_REASON_AUTHOR): новая функция author_life_op_from_payload(payload) -> int | None — delta int, не bool, ≠ 0, |delta| ≤ MAX_LIVES; иначе None → «bad payload». day_started_at не нужен и не читается. Новый SQL _APPLY_AUTHOR_LIFE_OP: lives = lives + :delta, Р3, updated_at, projector_version; WHERE pid, фаза IN ('onboarding','active'), lives + :delta BETWEEN 0 AND :max_lives, и (:delta < 0 ИЛИ (lives > 0 И NOT 'block_lives' = ANY(coalesce(status_flags, '{}')))). Позиция, day_started_at, missed_streak не упоминаются. 0 строк → SELECT lives, status_flags, lifecycle_phase по pid: нет строки → «no state»; фаза не onboarding/active → «phase not allowed»; иначе причина = classify_life_op(lives, delta, flags).
  classify_life_op(lives, delta, flags) -> str | None, чистая, без pid: delta > 0 и (lives == 0 или "block_lives" в flags) → "lives_zero_use_revive"; lives + delta > MAX_LIVES → "life_above_max"; lives + delta < 0 → "life_below_zero"; иначе None. WARNING через _skip (id и kind, без pid и payload).
  Прочие reason → «bad payload», как сейчас.
- Р5 life_writeoffs [ШТАБ К-5 16.11; 0019]: только ветка (а), после успешного UPDATE, в том же SAVEPOINT. pid строки = pid события из пачки (аргумент pid _apply_event), event_id = id события; позиция — из RETURNING этого UPDATE. SQL — константа _INSERT_LIFE_WRITEOFF, дословно по 0019, без RETURNING:
    INSERT INTO life_writeoffs (pid, event_id, stage_no, module_no, day_no)
    VALUES (:pid, :event_id, :s, :m, :d) ON CONFLICT (event_id) DO NOTHING
  Любое из stage_no, module_no, day_no NULL → WARNING «projector: life_writeoffs skipped, no position, event id=X» (без pid), строки нет, жизнь всё равно списана, событие считается применённым. Ветка (б) в журнал не пишет.

## 5. ЧТО ПРОЧИТАТЬ (Агент)
AGENT-BRIEF.md 17,1 КБ; docs/decisions/DECISIONS.md 7,7; docs/process/CANON-CHECK.md 4,9; эта карточка ≈ 14; apps/api/app/projector.py 35,8; apps/api/migrations/versions/2026_11_17_1200-0019_life_writeoffs_life_writeoffs.py 4,5; apps/api/tests/test_projector_v3.py 16,9 (хелперы для новых тестов); apps/api/tests/test_projector_day_entered.py 8,4; apps/api/tests/test_projector_tz.py 7,1; apps/api/tests/test_life_ops.py 21,2 (только места с _drain); apps/api/tests/test_notify_ops.py 13,3 (только места с _drain). Чтение КОДЕРА ≈ 150,9 КБ.

## 6. Файлы
- Изменить: apps/api/app/projector.py (Р1–Р5, docstring: v5, life_op две ветки, бэкфилл, журнал).
- Создать: apps/api/tests/test_projector_sleep.py; apps/api/tests/test_projector_writeoffs.py.
- Изменить (задетые): apps/api/tests/test_projector_v3.py; apps/api/tests/test_projector_day_entered.py; apps/api/tests/test_projector_tz.py; apps/api/tests/test_life_ops.py; apps/api/tests/test_notify_ops.py.
- Удалить: нет. expected_tables.txt не трогать (таблиц не добавляем).

## 7. Контракт
- life_op author_cmd: payload {"delta": int, "reason": "author_cmd"}; пишет бот (T6b, после этой задачи), отказы с текстом — у бота до записи события; проверка в проекторе — страховка.
- life_op missed_days: payload прежний {day_started_at, delta −1, reason "missed_days"}.
- Новых kind нет; HTTP-контракт не меняется.

## 8. БД
Миграций нет. Права app_projector на life_writeoffs (INSERT по 5 колонкам, SELECT (event_id), USAGE life_writeoffs_id_seq) — в 0019. UPDATE status_flags у проектора уже есть (по коду: _UPSERT_STATE пишет status_flags).

## 9. Тесты (CI с БД; без БД — check.sh api)
test_projector_sleep.py:
- без БД: SLEEP_FLAGS — ровно 5 имён из Р2, "freeze_unpaid" нет; phase_for_flags — onboarding+block_lives → sleeping; sleeping без флагов сна → active; sleeping+["freeze_unpaid"] → active; muted+block_lives → muted; onboarding без флагов → onboarding; classify_life_op — каждая из трёх причин и None; author_life_op_from_payload — годные ±1…±3, отказ на True, 0, 4, −4, "1", без delta; PROJECTOR_VERSION == 5.
- с БД: missed_days 1 → 0 при пустых флагах → lives 0, sleeping, флаги ["block_lives"], версия 5; то же при уже стоящем block_lives — без дубля.
- author_cmd −2 из 3 → lives 1, фаза, позиция, day_started_at, missed_streak прежние; payload без day_started_at применяется; +2 из 1 → 3; −1 из 1 → 0, sleeping, block_lives.
- author_cmd пропуски с причиной в WARNING (без pid): +1 при 3 → life_above_max; −2 при 1 → life_below_zero; +1 при lives 0 → lives_zero_use_revive; +1 при lives 2 и флаге block_lives → lives_zero_use_revive; фаза sleeping → пропуск, lives прежние; битый delta → «bad payload».
- бэкфилл 0 строк: только строки вне условия (sleeping с block_lives; onboarding с lives 0) → run_once, в логе «строк 0», строки прежние.
- бэкфилл N строк: 2 строки sleeping, lives 0, флаги {} (+ строки вне условия) → run_once → обе ["block_lives"], версия 5, в логе «строк 2», прочие прежние; повторный run_once → «строк 0». db_engine — чистая БД на тест (как test_projector.py::test_batch_of_501).
- run_forever вызывает бэкфилл: monkeypatch _backfill_block_lives (счётчик), _drain → ProjectorResult(0, 0), _life_ops_step/_notify_ops_step → возврат аргумента, sleep бросает своё исключение → вызовов 1.
- run_once вызывает бэкфилл до _drain: engine = object(); monkeypatch _advisory_lock фейковым lock (contextmanager без БД), _backfill_block_lives и _drain пишут свои имена в общий список, _drain → ProjectorResult(0, 0) → бэкфилл вызван 1 раз и стоит в списке раньше _drain.
test_projector_writeoffs.py:
- без БД: нормализованный (split/join) текст _INSERT_LIFE_WRITEOFF == строке из Р5; эта строка входит в нормализованный текст файла 0019; "RETURNING" нет в _INSERT_LIFE_WRITEOFF.
- с БД: missed_days −1 → 1 строка; pid строки = pid события: JOIN participant_events e ON e.id = w.event_id AND e.pid = w.pid даёт 1; позиция = позиция дня (1, 1, 1).
- два участника А и Б в одной пачке → у каждой строки pid = pid своего события.
- повтор события: DELETE checkpoint pid (владелец, только тест) → run_once снова → строк по этому event_id 1.
- author_cmd −2 → строк 0; пропущенный life_op (другой день) → строк 0.
- позиция NULL (владелец ставит day_started_at, day_no NULL) → life_op применён, lives −1, строк 0, WARNING с id события, без pid.
Цели: bash tools/check.sh api. Только CI: все тесты с БД.

## Задетые тесты (правило «Т»; проверено по коду @42d9d69)
- test_projector_v3.py: test_version_is_4 → test_version_is_5, assert PROJECTOR_VERSION == 5. Остальное проходит: _prepare ставит block_lives, но UPDATE, не меняющий флаги, фазу не пересчитывает (Р2); параметры test_life_op_bad_payload_skipped без author_cmd остаются «bad payload». object()-движков нет (проверено): все тесты на db_engine, _advisory_lock не подменяется.
- test_projector_day_entered.py: в test_position_from_payload — assert PROJECTOR_VERSION == 5 (комментарий «api-sleep-1a»).
- test_projector_tz.py: test_version_and_kind — PROJECTOR_VERSION == 5; test_tz_set_before_first_day — state.projector_version == PROJECTOR_VERSION; docstring «PROJECTOR_VERSION 4» → 5.
- test_life_ops.py (сверил ШТАБ, К-5 16.11: engine = object(), бэкфилл упадёт на engine.begin()): в хелпере _run_forever_with (через него идут test_run_forever_ticks_every_30s и test_run_forever_tick_error_warning_loop_alive) и в test_run_once_without_tick рядом с monkeypatch.setattr(projector, "_drain", …) добавить monkeypatch.setattr(projector, "_backfill_block_lives", lambda engine: 0). Больше в файле ничего не трогать.
- test_notify_ops.py (так же сверил ШТАБ): в test_notify_ops_step_error_warning_loop_alive рядом с monkeypatch.setattr(projector, "_drain", …) добавить monkeypatch.setattr(projector, "_backfill_block_lives", lambda engine: 0). Больше в файле ничего не трогать.
- test_projector.py, test_projector_static.py — правка не нужна (версия из импорта; WRITE_RE только по participant_state).
- Сверено ШТАБом 16.11 @42d9d69, правка не нужна: test_projector_day_report.py; test_life_ops_race.py (lives 3 → 2, до 0 не доходит); test_clocks_1.py (тест 7: lives 1 → 0, проверяет только lives и фазу; журнал пишется — позиция есть); test_notify_ops.py, test_notify_noon.py, test_notify_ladder.py — фильтры block_lives и sleeping ставит владелец, проектор не участвует; test_life_ops.py — test_last_life_sleeping_then_skipped и test_k1_* проверяют только lives, фазу и streak.
- Упал тест вне списка → не чинить, «тест X вне списка» в ИТОГ, стоп.

## 10. Живые проверки (после мержа)
Миграции нет, бэкап не нужен; 0018 и 0019 уже на сервере. Только пересборка projector: pull main → DC build projector → DC up -d projector. Ожидание в логах projector: «lock acquired, running (version 5)», «backfill block_lives, строк 0», Traceback 0, WARNING 0. projector once рядом с run не запускать (infra/SERVER-IRONCLAD.md:146).

## 11. Запреты
AGENT-BRIEF §3. Плюс: не трогать life_ops.py, notify_*.py, day_clock.py, бота и миграции; не переименовывать LIFE_OP_DELTAS, LIFE_OP_REASON, life_op_from_payload; не делать Р6–Р9 и pause_budgets; не ставить active из onboarding; pid и payload в лог не писать; SQL INSERT в life_writeoffs не менять против 0019.

## 12. Критерии готовности
check.sh api зелёный; все тесты раздела 9 есть; задетые — точно по списку; docstring проектора описывает v5; в PR — прочитанные файлы и таблица проверок.

## 13. Оценка
Часы Автора ≈ 0,5 (PR, CI, пересборка). Кредиты ≈ 800 (sleep-1 §3) + 5 задетых × 60–100 ≈ 1 200; стоп 1 500.

## 14. РЕВЬЮЕР
Нет (initData, 18+, согласия, rate-limit, роли/GRANT, оплату не трогает).
