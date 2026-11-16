# sleep-1 — исследование T6a api-sleep-1 (PLAN §5 п.20)
Hash 6695d0c, ИССЛЕДОВАНИЕ, З1, Правило К. Основа — research/pause-2.md §4–§6 и research/pause-2-check.md §1–§3 (где расходятся — верен check). Ссылки — путь@6695d0c. docs/architecture/** не читался: канон взят из pause-2 (К-2 через сведённый файл). Тексты — заглушки, аккаунты — А1–А4.

## 1. Код сейчас (факты)
- Ф1 apps/api/app/projector.py: PROJECTOR_VERSION = 4; kinds: mini_app_first_consent, day_entered, day_report_submitted, life_op, day_closed, tz_set; прочие → WARNING «unknown kind», пропуск. AGENT-BRIEF §6 («3», миграции до 0010) устарел.
- Ф2 projector._APPLY_LIFE_OP: lives + delta; при 0 → lifecycle_phase sleeping, status_flags не трогает. WHERE: day_started_at совпадает, фаза onboarding/active, 0 ≤ lives + delta ≤ 3. life_op_from_payload: только delta −1 и reason missed_days (Н3).
- Ф3 Фазу active код не ставит нигде: first_consent → onboarding, day_entered фазу не трогает (В21). По отчёту сервера (pause-2-check п.9) у А1 фаза onboarding.
- Ф4 Проектор: глобальный advisory lock participant_state_projector, на каждое событие SAVEPOINT; DataError и IntegrityError → пропуск события; другие SQLAlchemyError (в том числе нет таблицы) → откат всей пачки и повтор.
- Ф5 app/life_ops.py: при флаге из BLOCKING_FLAGS (pause_user, pause_shadow, author_pause, block_lives, ban_mod, freeze_unpaid) участник полностью пропускается; close_outcome при lives = 0 → ValueError; ключ, life_op и day_closed пишутся одной транзакцией под lock_participant (participant:pid).
- Ф6 app/day_clock.py: active_from — первая 04:00 ≥ started; deadline — 00:00 следующих суток; window = not_active до active_from; last_midnight — последняя 00:00 ≤ now. Функции «первая 00:00 после момента» нет.
- Ф7 app/notify_ops.py, НП3: срабатывает по ключу day_queue по dsa(D) после queue_until или по событию day_entered с at = D. choose_text: местное время < 04:00 → «сегодня», иначе «завтра». is_late = window ≠ not_active. НП1 требует window = open.
- Ф8 app/notify_ladder.py: кандидаты и _decide_for — только при window = open, поэтому при будущем D лестницы нет (по коду; тест обязателен, pause-2-check п.8).
- Ф9 0019_life_writeoffs: INSERT (pid, event_id, stage_no, module_no, day_no) VALUES (…) ON CONFLICT (event_id) DO NOTHING; у app_projector: INSERT по этим колонкам, SELECT (event_id), USAGE на последовательность; /life −N в журнал не пишется; бэкфилла нет.
- Ф10 0005: CHECK lifecycle_phase уже включает sleeping; поля participant_events — id, pid, kind, payload, publish_epoch, at, actor, actor_role.

## 2. Решения для T6a (метка К-6)
- Р1 PROJECTOR_VERSION = 5 [ШТАБ-тех, pause-2 §6].
- Р2 SLEEP_FLAGS = pause_user, author_pause, pause_shadow, block_lives, ban_mod (Red Flags добавят позже) [канон I2 через pause-2 §4]; freeze_unpaid — не фаза (pause-2 §1). Фаза пересчитывается в том же UPDATE, что меняет флаги: есть флаг из SLEEP_FLAGS → sleeping; флагов нет и было sleeping → active (I2: выход pause_removed_and_lives_ok); иначе фаза прежняя. Переход onboarding → active — не T6a. muted и erased не трогаются.
- Р3 block_lives [pause-2 §4; Р-20]: life_op, после которого lives = 0, добавляет block_lives (без дубля) и ставит sleeping. Бэкфилл — одним UPDATE при каждом взятии lock проектора (run и once): lifecycle_phase = sleeping AND lives = 0 AND NOT 'block_lives' = ANY(status_flags) → добавить block_lives, projector_version 5. Повтор безопасен, число строк любое (пусть даже 0, check п.9); в лог — только число строк.
- Р4 life_op в две ветки [pause-2 §5; Р-20]. (а) reason missed_days (часы) — как сейчас, плюс Р3 и Р5. (б) reason от /life (имя — Ш1): delta — int, не bool, ≠ 0, |delta| ≤ 3; day_started_at не нужен; позиция и день не трогаются (03 §3.6). Условия в SQL: фаза onboarding или active; для +N — lives > 0 и нет block_lives, иначе пропуск «lives_zero_use_revive»; lives + delta > 3 → пропуск life_above_max; < 0 → life_below_zero; ровно 0 → Р3. Причину для WARNING даёт чистая функция classify_life_op(lives, delta, flags), без pid. Отказы с текстом делает бот (T6b) до записи события, проверка в проекторе — страховка.
- Р5 life_writeoffs [ШТАБ К-5 16.11; 0019]: только ветка missed_days, delta −1, после успешного UPDATE, в том же SAVEPOINT. pid — pid события из пачки, позиция — RETURNING stage_no, module_no, day_no этого же UPDATE. SQL — дословно по 0019, без RETURNING. Если позиция NULL → WARNING, строки нет, жизнь всё равно списана.
- Р6 reissue_day(conn, pid, target, at, tz) — внутренняя функция проектора; не событие и не day_entered (check п.2): позиция = target, missed_streak 0, day_started_at = D = day_clock.next_midnight(at, tz). next_midnight — новая функция: первая 00:00 по поясу строго позже at, через _at_local. D считается из at события, поэтому повтор даёт тот же результат, а боту не нужен day_clock. До 04:00 даты D окно not_active: часы не закрывают день, НП1 и лестницы нет (Ф6–Ф8) [А1 Р-20].
- Р7 restart_paid [pause-2 §5; Р-20; check §1 п.1, п.5]: применяется, если в status_flags есть block_lives и stage_no не NULL, иначе пропуск. Что делает: lives 3; block_lives снимается; фаза по Р2; reissue_day(текущий stage, 1, 1); pause_budgets UPSERT — остаток 14, cycle_start_at = D, restart_no + 1. 0018 не читалась — колонки и права сверяет окно КАРТОЧКИ. payload должен быть dict; grant_id проектор не читает.
- Р8 Третий запуск НП3 [Автор 15.11, check §2]: событие из REISSUE_KINDS (сейчас restart_paid; T7 и T2 дополнят), для которого next_midnight(at, tz) = D. Текст для этого запуска выбирается по дате: местная дата active_from(D) равна местной дате now → «сегодня», иначе «завтра». Почему не choose_text: при перевыдаче между 00:00 и 04:00 он сказал бы «сегодня», а задания откроются через сутки. Для двух старых запусков остаётся choose_text.
- Р9 Дата цикла пауз (check п.6): готовой функции в day_clock нет. По коду дата = active_from(D первого дня, tz).date(), её 00:00 — _at_local(дата, DEADLINE_TIME, zone). Для рестарта cycle_start_at = D: D уже 00:00.

## 3. Нарезка T6a (миграций нет, одна область — API)
| # | id | Суть | Файлы | Код + тесты | Кредиты (стоп 1,5 ×) |
|---|---|---|---|---|---|
| 1 | T6a-1 api-sleep-1a | Р1–Р5 | app/projector.py; tests/test_projector_sleep.py, tests/test_projector_writeoffs.py (новые) + задетые | 170 + 280 | 800 (1 200) |
| 2 | T6a-2 api-sleep-1b | Р6–Р8 | app/projector.py, app/day_clock.py, app/notify_ops.py; tests/test_projector_restart.py, tests/test_reissue_future_day.py (новые) + задетые | 220 + 330 | 1 100 (1 650) |
Сумма 1 900, при стопе 2 850 < 3 744. Порядок 1 → 2: обе меняют projector.py, карточка 2 идёт после мержа 1, задетые ШТАБ сверяет по свежему main. РЕВЬЮЕР — нет (initData, 18+, согласий, ролей и оплаты не трогают). Чтение КОДЕРА для карточки 2: projector + day_clock + notify_ops + notify_ladder + life_ops ≈ 107 КБ без тестов — бюджет впритык.
Обязательные тесты: карточка 1 — pid строки life_writeoffs = pid события participant_events; статическая сверка текста INSERT с 0019 (ON CONFLICT (event_id) DO NOTHING, без RETURNING); повтор события — одна строка; /life −N строку не пишет; бэкфилл при 0 и при N строк. Карточка 2 — при будущем D: life_ops не закрывает день, НП1 не уходит, лестницы нет; НП3 по restart_paid уходит один раз с текстом по Р8.

## 4. Задетые тесты — кандидаты (не читались; сверяет окно КАРТОЧКИ)
- К1: test_projector.py — PROJECTOR_VERSION и life_op при 0 (теперь ещё block_lives).
- К1: test_projector_static.py — SQL записи только в проекторе; новые INSERT в life_writeoffs (и pause_budgets в К2).
- К1: test_projector_v3.py — строгость payload life_op (Н3), а reason /life теперь допустим.
- К1: test_projector_day_entered.py, test_projector_day_report.py, test_projector_tz.py — значение projector_version в строках.
- К1: test_life_ops.py, test_life_ops_race.py — сверка констант с проектором; сквозной сценарий «0 жизней → sleeping» с пустыми флагами.
- К1: test_clocks_1.py — life_op дня рефлексии теперь пишет life_writeoffs.
- К2: test_notify_ops.py — третий запрос в _candidates и _plan (фейковые conn), новая константа REISSUE_KINDS.
- К2: test_day_clock.py — новая next_midnight (если тест сверяет список функций).
- К2: test_notify_noon.py, test_notify_ladder.py — помощники не меняются; вероятно, не задеты.
- test_day_current.py::test_kinds_and_ttl — новых kind ключей T6a не вводит (НП3 пишет tasks_open), поэтому не задет; окно КАРТОЧКИ подтверждает.

## 5. DEFECTS-кандидаты (номер даёт ШТАБ)
- ДК-1. Замок: в I2 life_ops 'life:'||pid (pause-2 §7); в коде один замок participant:pid у всех писателей (lock_participant в life_ops.close_one, notify_ops.notify_one и noon_one, notify_ladder.ladder_one; participant_lock.py — по AGENT-BRIEF §6). 'life:' в прочитанном коде нет. Проектор на pid замок не берёт, у него глобальный lock. Предложение: врезка в I2 «замок участника — единый participant:pid», 'life:' не вводить: два разных замка открыли бы гонку /life против часов.
- ДК-2. Код не ставит active (Ф3), а I2 fsm задаёт onboarding → active (триггер в этом окне не проверен). T6a выводит из sleeping в active (Р2).
- ДК-3. AGENT-BRIEF §6 устарел (Ф1) — долг уже записан в STATE.

## 6. Для ШТАБа (К-5)
- Ш1. Имя reason у life_op от /life (предлагаю author_cmd) — общий контракт T6a-1 и T6b.
- Ш2. D считается из at события, а не берётся из payload (сверить с формулировкой check §2 «новый D в событии»). tz после первого дня не меняется (tz_set только при day_no IS NULL), поэтому D однозначен.
- Ш3. pause_budgets в restart_paid — в T6a-2: без этого рестарт не обнулит квоту (C3). Если не брать — перенести в T2.
- Ш4. Выкат: если проектор v5 запустить до migrate 0019, INSERT упадёт с ProgrammingError, пачка откатится, проектор встанет (Ф4). Порядок: 0018 → 0019 → projector.
- Ш5. /life при sleeping по паузе (lives > 0): T6a его не применяет (нужна фаза onboarding или active); решить в T2.
- Ш6. Если INSERT life_writeoffs упадёт с IntegrityError, откатится весь life_op — жизнь не спишется, а checkpoint сдвинется. Риск низкий (FK на событие той же БД); предлагаю принять.

## 7. Вопросы Автору
Нет: всё закрыто Р-20, pause-2 §8, check §2 и решениями ШТАБа.

## 8. Прочитано
DESIGNER.md 22,0; PACK.md 11,8; STATE.md 18,6; AGENT-BRIEF.md 17,1; DECISIONS.md 7,7; CANON-CHECK.md 4,9; research/pause-2.md 18,1; research/pause-2-check.md 6,0 (jsdelivr не открыл — raw); 0019_life_writeoffs 4,5; app/projector.py 35,8; app/life_ops.py 17,7; app/day_clock.py 11,2; app/notify_ops.py 22,4. Из списка «по необходимости»: app/notify_ladder.py 15,7 (check п.8 — лестница при будущем D); 0005_participant_events 4,5 (CHECK lifecycle_phase).
