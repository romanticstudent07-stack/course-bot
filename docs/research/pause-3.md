# pause-3 — авто-старт паузы по канону 02 П.2 (api-pause-3)
Hash edd15c9, ИССЛЕДОВАНИЕ З1, Правило К. Ссылки — путь@edd15c9:строки. Строки посчитаны вручную по выдаче, допуск ±3. Где строк нет — указано имя функции или константы.
Решение Автора (ШТАБ, дословно в старте): «Б» — действует канон 02 П.2; Р14 карточки api-pause-1a отменён; запись в DECISIONS не нужна. [Автор, канон 02 П.2]
Канон: текст 02 П.2 в этом окне не читался; pause-2.md §2 и §3 — «П.2 … I2 молчит, действует 02», «бот — уведомления и кнопки Автора (П.2)». Цитаты П.2 нет — см. §9.

## 1. Часы: где сжигают requested и что проверяет обычный старт
- Сжигание — apps/api/app/pause_ops.py@edd15c9:274-294, функция plan целиком: 276-278 строка паузы; 279-280 проектор не догнал pid (life_ops._PENDING_EVENT) → пропуск; 281-282 status requested и start_at ≤ now → _failed(pid, pause_id, REASON_NOT_APPROVED) (Ч6); 283-291 active → pause_ended expired; 292-293 approved → _plan_start; 294 None.
- Кандидаты уже берут requested: _CANDIDATES 84-94 и _PID_CANDIDATES 96-105 (status IN ('approved', 'requested')). Описание в docstring — 13-31 (ветка B — 30).
- Проверки обычного старта — _plan_start 228-271:
  - вчерашний день не закрыт (life_ops._eligible и day_clock.is_overdue) → пропуск, 232-238;
  - pause_rules.pause_days → ValueError → WARNING и пропуск, 240-244;
  - бюджет через _budget_left 215-225 (pause_rules.roll_cycle, строки нет → BUDGET_DAYS, 0);
  - _STAGE_TAKEN 134-142 и _LAST_END 145-150;
  - pause_rules.start_refusal 251-261, причина → _failed 262-263, иначе pause_started 264-271.
- pause_rules.py@edd15c9:132-165, start_refusal: 150-151 status ≠ approved → not_approved; затем block_lives 152-153, state, gap_24h, stage_taken, no_budget. Константы: STATUS_APPROVED 32, REFUSAL_REASONS 46-53.
- Для авто-старта нужны те же функции: _plan_start, _budget_left, pause_rules.pause_days / roll_cycle / start_refusal.
- Предлагаемая правка (ШТАБ-тех, К-5): ветку 281-282 убрать. Условие 292 — status IN (requested, approved), дальше _plan_start. В start_refusal для requested передавать status = STATUS_APPROVED — так уже делает API T3 (api-pause-2 Д4). Тогда pause_rules не меняется, а not_approved остаётся в REFUSAL_REASONS: проектор принимает старые события с этой причиной.
- Docstring pause_ops: 1, 13-31 (убрать «сгорание неодобренных» и ветку B).

## 2. Проектор
- Сейчас старт идёт только из approved. apps/api/app/projector.py@edd15c9: SQL _START_PAUSE — «WHERE id = :id AND pid = :pid AND kind = 'user' AND status = 'approved'». В docstring — «pause_started {pause_id}: approved → active … Повтор — статус уже active → пропуск». PROJECTOR_VERSION = 8. Тело _apply_pause_started не прочитано, строки не проверены (§9).
- Что изменить: в _START_PAUSE — status IN ('requested', 'approved'); в проверке статуса _apply_pause_started — то же; в start_refusal передавать status = STATUS_APPROVED. Повтор (active) по-прежнему пропуск.
- Права и БД менять не нужно: app_projector UPDATE (status, stage_no, restart_no, ended_at) — 0018:162-166; CHECK ck_participant_pauses_user_stage требует stage_no и restart_no у active — 0018:104-109, их ставит _START_PAUSE; participant_pauses_one_active_uq — 0018:132.
- Новая версия: по образцу v7 и v8 — да, 8 → 9 (поведение вида события изменилось). Цена: файлы тестов, которые сверяют версию (§6). Решает ШТАБ.

## 3. Позднее «Одобрить»
- Где сейчас отменяется: projector.py@edd15c9, docstring видов пауз — «pause_approved {pause_id}: requested → approved; at ≥ start_at → cancelled (Р14)». Тело функции не прочитано.
- Нужно по 02 П.2: ветку Р14 удалить, pause_approved всегда переводит requested → approved. Пример: одобрение пришло после start_at, но до тика часов. Строка станет approved, часы стартуют её по пути A.
- После авто-старта (active) или конца (ended) pause_approved и pause_rejected — пропуск без смены статуса. Повтор безопасен: UPDATE с ожидаемым статусом вернёт 0 строк. Предлагаю без WARNING (уровень INFO): норма сервера — WARNING 0 (STATE «Норма сервера»). [ШТАБ-тех]
- Ответ кнопке — дело бота T4. Контракт api-pause-1a §5 (строка «Бот (T4)») сейчас требует проверки «now < start_at, иначе „заявка устарела“». По П.2 ответ будет «пауза уже началась» (text_id — заглушка в T4). Это правка контракта для карточки T4. bot-pause-1 здесь не меняется.

## 4. Сообщение участнику при авто-старте
- В API нет ни события, ни outbox. pause_ops.py@edd15c9:11 — «participant_state, participant_pauses, pause_budgets и outbox здесь не пишутся»; projector docstring — «Уведомлений (outbox) нет»; api-pause-1a §5 — «Уведомления (outbox) T2 не пишет; T4 сам выбирает…».
- По решению Автора признак авто-старта такой: пауза active, а ключа решения бота нет. Значит, API ничего не добавляет: ни нового kind, ни text_id, ни outbox. Сообщение и text_id-заглушка — в T4. [Автор]
- Ключ часов pause_start:{pid}:{pause_id} пишется при обоих стартах (pause_ops 264-271), поэтому признаком авто-старта он служить не может. Нужен ключ решения бота. Его формат — в bot-pause-1 (не читалась).

## 5. T4: SELECT app_bot на idempotency_keys.key — ЕСТЬ
- 0018@edd15c9:181 — FOREIGN_PRIVILEGES («SELECT (key, result_ref)», «TABLE idempotency_keys», «app_bot»); 180 — INSERT (key, kind, result_ref); docstring 44-52.
- 0007@edd15c9:86-91 — SELECT, INSERT только app_api и app_projector, app_bot нет.
- 0019@edd15c9, PRIVILEGES — у app_bot только SELECT life_writeoffs.
- 0020@edd15c9:36-38 — у app_bot только SELECT (id, pid, kind) participant_events.
- 0006 — не читался (по AGENT-BRIEF §6 app_bot создан в 0009); на ответ это не влияет.
- Попутно: у app_bot нет прав на participant_pauses (0018 docstring 53-54). Как бот узнаёт, что пауза стала active, решают 0021 и bot-pause-1 (их не меняем, не читались).

## 6. Задетые тесты (правило «Т»)
- apps/api/tests/test_pause_ops.py@edd15c9:
  - test_b_requested_not_approved → ожидать TickResult(1, 0, 0, 0), событие pause_started {pause_id}, после run_once статус active; имя поменять на test_b_requested_auto_started;
  - test_two_ticks_one_event → «.failed == 1» и «.failed == 0» заменить на «.started == 1» и «.started == 0»; PausePlan again — OUTCOME_STARTED, pause_started, {pause_id};
  - test_max_per_tick → TickResult(2, 0, 0, 0), затем (1, 0, 0, 0); ожидание pause_started {pause_id: ids[2]}.
  - test_pending_event_skip не задет.
- Новые тесты: requested при block_lives → pause_start_failed block_lives; requested и вчерашний день не закрыт → пропуск.
- apps/api/tests/test_projector_pause.py — не читался. По api-pause-1a §8 там есть тест «поздний pause_approved → cancelled»: заменить на «→ approved». Добавить: pause_started из requested → active; pause_approved при active → пропуск без WARNING.
- Версия 8 → 9: какие файлы сверяют PROJECTOR_VERSION — не проверено. api-pause-1a §7 называет кандидатов: test_projector_v3, _day_entered, _tz, _sleep, _restart, _revive; ШТАБ упоминал 13 файлов со строкой projector_version.
- Общие списки: новых видов ключей нет (TTL_BY_KIND, test_day_current.py::test_kinds_and_ttl не задет). Новых kind событий нет. text_id в API нет. pause_rules.py не меняется, test_pause_rules.py не задет. Сверено по чтению кода выше, поиском по дереву не проверялось.

## 7. Миграция
Не нужна: права проектора — 0018:162-166; часы ходят под ролью проектора (pause_ops.py:5); app_bot SELECT key — 0018:181; CHECK статусов 0018:90-94 не меняется.

## 8. Нарезка и оценка
| # | id | Суть | Файлы | Чтение Агента | Кредиты |
|---|---|---|---|---|---|
| 1 | api-pause-3b | projector v9: старт из requested, без Р14, тихий пропуск approved / rejected при active | projector.py, test_projector_pause.py, файлы с версией | BRIEF 17,1 + DEC 7,7 + карточка ≈ 9 + projector 73,8 + test_projector_pause ≈ 15 = ≈ 123 | ≈ 600 (+60–100 на файл с версией) |
| 2 | api-pause-3a | часы: requested → _plan_start | pause_ops.py, test_pause_ops.py | 17,1 + 7,7 + ≈ 8 + 17,3 + pause_rules 7,2 + 11 = ≈ 68 | ≈ 400 |
Итого ≈ 1 000 без файлов версии. Порядок строго 3b → 3a, выкат одним образом projector. Одна карточка — ≈ 144 КБ без test_projector_pause, выше лимита 140 КБ.

## 9. Не проверено / надо дочитать (решает ШТАБ)
- projector.py — тела _apply_pause_approved, _apply_pause_started и строки (≈ 32 КБ из 73,8 прочитано; raw offset ≥ 10 000 — ошибка gzip/br).
- test_projector_pause.py — точные правки §6.
- grep PROJECTOR_VERSION / projector_version в apps/api/tests — список файлов версии.
- Канон 02 П.2 — цитата для раздела «Канон и решения» карточек.

## 10. Прочитано (КБ — по факту выдачи)
- DESIGNER.md ≈ 13 — правило «Т», общие списки.
- PACK.md ≈ 9 — §5 шаги.
- STATE.md 18,6 — норма сервера WARNING 0.
- AGENT-BRIEF.md 17,1 — app_bot с 0009.
- DECISIONS.md 7,7 — Р-6а.
- research/pause-2.md ≈ 15 — П.2: I2 молчит.
- tasks/api-pause-1a.md ≈ 13 — Р14, контракт §5.
- tasks/api-pause-2.md ≈ 13 — Д4 status approved.
- pause_ops.py 17,3 — plan 274-294.
- pause_rules.py 7,2 — start_refusal 132-165.
- 0018 14,5 — app_bot SELECT key, стр. 181.
- projector.py ≈ 32 из 73,8 — _START_PAUSE только approved.
- 0007 ≈ 6,5 — app_bot нет.
- 0019 ≈ 6 — app_bot только life_writeoffs.
- 0020 ≈ 2,3 — app_bot SELECT (id, pid, kind).
- test_pause_ops.py ≈ 11 — 3 теста на not_approved.
- Сверх списка: CANON-CHECK.md ≈ 4,9 (Правило К из старта); список файлов jsdelivr ≈ 10 и список миграций GitHub (размеры и имена файлов).
- Итого ≈ 208 КБ из 200: превышение ≈ 8 КБ из-за обычного режима чтения projector.py.
