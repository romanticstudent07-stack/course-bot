# T7a api-revive-1 — проектор применяет revive_by_author (projector v7)
Hash main a96d4b6. Основа: docs/research/pause-2.md §5, §6 строка 3, §8 А2; pause-2-check.md §2; sleep-1.md Р6–Р8; образец docs/tasks/api-sleep-1b.md. Правило К — docs/process/CANON-CHECK.md. Сначала прочитай docs/decisions/DECISIONS.md целиком.

## 1. Паспорт
- id: T7a api-revive-1 · PR: «api-revive-1: revive_by_author в проекторе (projector v7)» · ветка: feat/api-revive-1
- Режим: Р1 (Агент). Зависит от: T6a-2 api-sleep-1b (#238, в main). Миграций нет. Одна область — API.
- Пара: команда бота — следующая карточка bot-revive-1 (T7b), она пишет событие по контракту §7.1.

## 2. Цель
Проектор применяет новый kind revive_by_author. Снимает block_lives, ставит lives = min(3, 1 + lives_returned) и выдаёт день target (позицию выбирает Автор) с D = следующая 00:00 по поясу после at события. После перевыдачи уходит НП3 (это третий запуск). PROJECTOR_VERSION 6 → 7. Число lives_returned считает бот (bot-revive-1). Проектор берёт его из payload и сам не пересчитывает.

## 3. Решения (дословно; метка К-6)
- Р-20 (DECISIONS.md): «день после выхода из sleeping, revive, /revert, рестарта — с 00:00 по поясу (кнопки 04:00, дедлайн 00:00)»; «из block_lives — … revive (min(3, 1 + возврат §2.6), команда бота, после 0019)» [Автор, канон проверен — pause-2 §8].
- pause-2 §8 А2: «revive — одна транзакция (Р-C3.3): жизнь + откат на позицию, выбранную Автором (обычно день 1 текущего модуля); lives = min(3, 1 + возврат по 02 §2.6), больше 3 не бывает. … по списаниям до 0019 — только +1. revive и /revert не трогают лимиты пауз, прошлые Этапы, журналы отчётов и рефлексий» [Автор 15.11].
- Автор 15.11 (sleep-1 Р8): третий запуск НП3 после перевыдачи, текст по дате [Автор, check §2].
- ШТАБ (К-5), Ш1 = А: lives_returned считает бот, проектор применяет payload. Основание: в docstring 0019 сказано «читает бот для revive_by_author (T7)», SELECT (pid, event_id, stage_no, module_no, day_no) выдан app_bot, а у app_projector есть только SELECT (event_id). Пересборка проекции детерминирована, потому что число лежит в payload события [ШТАБ-тех].
- Обоснование, почему нет гонки: при block_lives «часы» life_ops пропускают участника (block_lives входит в BLOCKING_FLAGS, по коду: app/life_ops.py, docstring п.1). Поэтому между подсчётом в боте и применением событием новых списаний не бывает. Кроме того, life_op при фазе sleeping проектор не применяет (WHERE фаза onboarding/active, sleep-1 Ф2) [ШТАБ, по коду].
- ШТАБ: новый kind меняет проекцию → PROJECTOR_VERSION 7 [ШТАБ-тех].

## 4. Выдержки (КОДЕР канон не читает)
- pause-2 §5: «revive_by_author (T7, после 0019): оболочка как у /life (owner, hard_confirm, двухшаг …). Шаг 1 — Автор выбирает позицию (по умолчанию день 1 текущего модуля). Одна транзакция, замок participant:pid: есть block_lives; возврат = списания в 0019 после точки отката (02 §2.6); событие revive_by_author {target, lives_returned}. Проектор: lives = min(3, 1 + lives_returned); снять block_lives; missed_streak 0; reissue_day(target). … Лимиты пауз, прошлые Этапы, отчёты, рефлексии — не трогает».
- sleep-1 Р6 (через api-sleep-1b §4): «reissue_day(conn, pid, target, at, tz) — внутренняя функция проектора; не событие и не day_entered: позиция = target, missed_streak 0, day_started_at = D = day_clock.next_midnight(at, tz). … До 04:00 даты D окно not_active: часы не закрывают день, НП1 и лестницы нет».
- Р2 в коде (projector.phase_for_flags): muted/erased не меняются; при флаге из SLEEP_FLAGS → sleeping; sleeping без флагов сна → active; в остальных случаях фаза прежняя.
- Образец restart_paid v6 (api-sleep-1b §7.2): проверяется (1) _payload_dict(payload) is None или at is None → «bad payload»; (2) нет строки → «no state»; нет block_lives или stage_no IS NULL → пропуск; (3) UPDATE с WHERE 'block_lives' = ANY(…) AND stage_no IS NOT NULL RETURNING pid; всё в SAVEPOINT события; пропуск → _skip.
- Роль: в выдержках api-sleep-1b §4 и §7.2 проверки actor и actor_role для restart_paid нет. Для revive_by_author проверка роли такая же, как у restart_paid в v6, и не строже; это ШТАБ сверяет по коду. Если в v6 роль не проверяется, здесь её тоже не проверять.
- CHECK participant_state (0007): позиция (stage_no, module_no, day_no, day_started_at) либо задана целиком, либо вся NULL; lives 0..3.
- 0019 docstring: «Бэкфилла нет: списания до 0019 в журнал не попадают (по ним revive даёт только +1)». Для проектора это означает: бот передаст lives_returned = 0, и выйдет lives 1. Отдельной ветки нет.

## 5. ЧТО ПРОЧИТАТЬ (Агент)
Целиком: AGENT-BRIEF.md 17,1; docs/decisions/DECISIONS.md 7,7; эта карточка ≈10; apps/api/app/projector.py 50,2; apps/api/app/notify_ops.py ≈23; apps/api/tests/test_projector_restart.py 10,8 (образец фикстур и прогона). Итого ≈119 КБ.
Только выдержки по grep: тесты из «Задетых» — «PROJECTOR_VERSION|projector_version|REISSUE_KINDS|unknown kind»; apps/api/tests/test_reissue_future_day.py — фикстура F4 (НП3) как образец для V12. Чтение Агента ≈125 КБ (меньше 140).

## 6. Файлы
- Изменить: apps/api/app/projector.py, apps/api/app/notify_ops.py; тесты из «Задетых тестов».
- Создать: apps/api/tests/test_projector_revive.py.
- Удалить: нет.

## 7. Контракт
7.1 Событие (пишет бот в bot-revive-1, здесь только применяется):
- kind "revive_by_author"; actor 'bot', actor_role 'owner' (как у restart_paid в bot-restart-1).
- payload {"target": {"stage_no": int, "module_no": int, "day_no": int}, "lives_returned": int}.
- Поля target: int, не bool, IS NOT NULL и ≥ 1. lives_returned: int, не bool, ≥ 0. Лишние ключи игнорируются.
- Невалидный payload → пропуск события через _skip («bad payload»), как у restart_paid.
7.2 projector.py:
- PROJECTOR_VERSION = 7; EVENT_KIND_REVIVE_BY_AUTHOR = "revive_by_author".
- revive_from_payload(payload) -> tuple[tuple[int, int, int], int] | None — чистая функция. Делает _payload_dict; target — dict с тремя полями по 7.1; lives_returned по 7.1. Любое нарушение → None. bool отсекать явно (isinstance(x, bool) → None).
- _apply_revive_by_author(conn, event_id, pid, kind, at, payload). Порядок:
  (1) parsed = revive_from_payload(payload); parsed is None или at is None → «bad payload»;
  (2) SELECT lifecycle_phase, status_flags, stage_no, module_no, day_no, tz FROM participant_state WHERE pid. Нет строки → «no state». Нет block_lives или stage_no IS NULL → «revive: not blocked or no position»;
  (3) target.stage_no ≠ stage_no → «revive: other stage». (target.module_no, target.day_no) > (module_no, day_no) при сравнении кортежей → «revive: target ahead». target = текущей позиции допустим;
  (4) lives = min(MAX_LIVES, 1 + lives_returned); flags = status_flags без block_lives; phase = phase_for_flags(phase, flags); UPDATE participant_state SET lives, status_flags = CAST(:flags AS text[]), lifecycle_phase, updated_at = now(), projector_version WHERE pid AND 'block_lives' = ANY(coalesce(status_flags, CAST('{}' AS text[]))) AND stage_no = :s RETURNING pid. Если строк нет → _skip;
  (5) reissue_day(conn, pid, target, at, tz). pause_budgets, day_marks, отчёты, рефлексии и life_writeoffs не читаются и не пишутся.
  Всё выполняется в одном SAVEPOINT события. Пропуск означает, что состояние не меняется и событие не применено.
- _apply_event: ветка kind revive_by_author → _apply_revive_by_author.
- Docstring модуля: kind revive_by_author, версия 7, lives_returned берётся из payload (считает бот, Ш1 = А).
7.3 notify_ops.py: EVENT_KIND_REVIVE_BY_AUTHOR = "revive_by_author" (импорта проектора нет); REISSUE_KINDS = (EVENT_KIND_RESTART_PAID, EVENT_KIND_REVIVE_BY_AUTHOR). Остальное не трогать: is_reissue и _REISSUE_* уже фильтруют по REISSUE_KINDS.
7.4 Лог: только id и kind события. pid, tz, payload, target и D в лог не пишутся.

## 8. БД
Миграций нет. Новых GRANT нет: проектор пишет только participant_state, права на это уже есть. expected_tables.txt не меняется.

## 9. Тесты
Урок 16.11: в любой фикстуре participant_state позиция либо задана целиком, либо вся NULL; lives 0..3.
test_projector_revive.py (с БД, CI; фикстуры по образцу test_projector_restart.py; событие с actor 'bot', actor_role 'owner'):
- V1: sleeping, lives 0, {block_lives}, позиция (2, 3, 5, старый dsa), tz Europe/Moscow; target (2, 3, 1), lives_returned 1 → lives 2, flags {}, active, позиция (2, 3, 1), day_started_at = next_midnight(at, tz), missed_streak 0, projector_version 7. Число строк day_marks и life_writeoffs у pid не меняется.
- V2: lives_returned 0 → lives 1 (случай «списания до 0019»).
- V3: lives_returned 5 → lives 3.
- V4: {pause_user, block_lives} → flags {pause_user}, фаза sleeping (Р2), день перевыдан.
- V5: строка pause_budgets (5, старая дата, 0) после revive не меняется; если строки не было, она не появляется.
- V6: target (2, 3, 6), (2, 4, 1), (3, 1, 1), (1, 1, 1) → каждый раз пропуск, строка состояния не меняется.
- V7: target = текущая позиция (2, 3, 5) → применено, day_started_at = D.
- V8: active, lives 2, без флагов → пропуск. {block_lives} при всей позиции NULL → пропуск. Нет строки состояния → пропуск.
- V9 (чисто): revive_from_payload — валидный → кортеж. Каждый из случаев → None: нет target; target — список; поле True; поле 0; −1; "1"; 1.0; нет lives_returned; lives_returned False или −1; payload — список или не-JSON.
- V10: второй revive после применённого первого → пропуск, lives не меняются.
- V11 (чисто): EVENT_KIND_REVIVE_BY_AUTHOR в notify_ops совпадает с projector; REISSUE_KINDS == (restart_paid, revive_by_author).
- V12: НП3 — revive в 10:00 по поясу, tick_tasks_open через 5 мин → sent 1, text_id TEXT_TOMORROW; повторный tick → sent 0.
Задетые тесты (правило «Т»; кандидаты, ШТАБ сверяет по коду до промпта):
- test_projector_v3.py, test_projector_day_entered.py, test_projector_tz.py, test_projector_sleep.py, test_projector_writeoffs.py, test_projector_restart.py: PROJECTOR_VERSION == 6 и projector_version = 6 → 7 (в restart это R1, R2).
- test_projector_restart.py R10: если сверяет REISSUE_KINDS целиком → (restart_paid, revive_by_author).
- test_notify_ops.py: если сверяет REISSUE_KINDS или набор констант целиком.
- test_projector.py: пример «unknown kind» не должен быть revive_by_author.
- test_reissue_future_day.py, test_day_current.py::test_kinds_and_ttl — не задеты (новых видов ключей нет).
Цели: bash tools/check.sh api. Только CI: все тесты с БД (V1–V8, V10, V12).

## 10. Выкат (после мержа)
- Г0: DC ps → 7/7 Up. DC logs projector должен показывать «running (version 6)», то есть api-sleep-1b выкачен. Если нет — выкатить v6 и v7 одним разом, решает ШТАБ. alembic current → 0019_life_writeoffs.
- Бэкап не нужен: миграций нет.
- projector: DC build projector, затем DC up -d projector; DC logs --since 10m projector → «lock acquired, running (version 7)», Traceback 0.
- api не пересобирать: код api не меняется.
- revive живьём не проверить: писатель (bot-revive-1) ещё не готов.

## 11. Запреты
AGENT-BRIEF §3. Кроме того: не писать событие revive_by_author из api или бота; не читать life_writeoffs в проекторе и не пересчитывать lives_returned; не менять life_ops.py, day_clock.py, notify_ladder.py, миграции и права; не трогать pause_budgets, author_pause_reason, muted/erased, прошлые Этапы, day_marks, отчёты и рефлексии; не брать D из payload; роль не проверять строже, чем у restart_paid; не логировать pid, tz, payload.

## 12. Критерии готовности
Разделы 7 и 9 выполнены; check.sh api зелёный; V1–V12 есть; правки только в файлах раздела 6; описание PR — по AGENT-BRIEF §10.

## 13. Оценка
Часы Автора ≈0,5 (мерж и выкат). Кредиты: код ≈90 строк + тесты ≈220 → база ≈600; задетые до 8 файлов × 60–100 ≈650 → ≈1 250, стоп 1 875 (1,5 ×).

## 14. РЕВЬЮЕР: нет
initData, 18+, согласия, rate-limit, роли/GRANT и оплату задача не трогает (GRANT нет, миграции нет).

## Канон и решения
(а) Используется: Р-20 (DECISIONS.md); pause-2 §5 и §8 А2 (10-02 revive_by_author «с откатом позиции» — через pause-2 §3); docstring 0019; docs/architecture в этом окне не читался.
(б) Противоречий с DECISIONS.md нет: «повторная оплата» (02 §2.4) уже снята Р-20. 02 §2.6 в этой карточке не используется.
(в) Для bot-revive-1 (в этой задаче не делается): build/bot-commands-registry.yaml, группа lifecycle — команда revive (owner, hard_confirm true, work_group_reply), итог 35, имя команды и правка DOCS — bot-revive-1 (pause-2-check п.10). Расчёт lives_returned, правило :after и сверка 02 §2.6 — bot-revive-1. Права app_bot на SELECT participant_events для :after не проверены; если их нет — миграция 0020 в bot-revive-1, решает ШТАБ.
(г) В этой задаче правок канона нет.
