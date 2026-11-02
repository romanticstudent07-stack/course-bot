# clocks-1 — «часы»: пропуск дня рефлексии, алерт «день 2», docstring проектора
Правило К — docs/process/CANON-CHECK.md. Карточка по docs/research/iter2-rest.md (§3 б, в, г; §9) и коду @709ab90.

## 1. Паспорт
- id: clocks-1. Заголовок PR: «feat(api): часы — день рефлексии и алерт день 2 (clocks-1)». Ветка: feat/clocks-1.
- Режим: Агент (PLAN §1: сложные задачи — в начале месяца). Оценка 650–850 кредитов.
- Зависит от: bot-group-1 (смержен и выкачен, #161). Начинать от свежего main. Миграции нет (последняя — 0011_reflections_log).
- РЕВЬЮЕР: нет (§14).

## 2. Цель
(б) Если день 6 или 13 закрыт без отчёта, «часы» сразу списывают 1 жизнь и обнуляют счётчик, отметки при этом не важны.
(в) Лестница пишет Автору одну строку outbox ladder_day2_alert, если участник второй день подряд пришёл, но не отправил отчёт.
(г) В docstring проектора, в абзац «часы», дописать НП1 и лестницу.

## 3. Решения (дословно и метки К-6)
- В2 = Б [Автор, 30.10, iter2-rest §9]: частное правило дня рефлексии главнее общего attended_not_sent.
- Решение (в) [ШТАБ, 30.10, iter2-rest §9; канон 03 §3.17 момент не задаёт]: алерт пишет notify_ladder на шаге plus1h.
- Т1 [ШТАБ, К-5]: reason у life_op остаётся "missed_days". Т2 [ШТАБ]: день рефлексии определяется только по day_no ∈ {6, 13}.
- Т3 [ШТАБ]: новые тесты — только в test_clocks_1.py. Т4 [ШТАБ]: алерт пишется только при вставке ключа plus1h в этой транзакции.
- Т5 [ШТАБ]: условие «день 2» проверяется в Python, битый payload → False, CAST в SQL не используем.
- НП (DECISIONS): активность — только day_marks. Отсюда came = есть строки day_marks.

## 4. Выдержки архитектуры
- 02 §2.3: «Пропуск дня рефлексии (6, 13-M или 13-P) → −1 жизнь сразу… всегда ровно 1 жизнь, без суммирования с предыдущими пропусками».
- 02 §2.2 (выдержка iter2-rest §1): любое списание обнуляет все счётчики.
- 03 §3.12 (выдержка iter2-rest §1): рефлексия — обязательное поле отчёта дней 6, 13-M, 13-P. День 6 не гейтит (§3.13).
- 03 §3.17 (выдержка iter2-rest §1): «день 2 проблемы → алерт Автору». Момент не задан.
- 08 §8.2: «Отчёты и активность — … «пришёл, но не отправил» (день 2)». Доставку в тему делает бот (bot-group-1 #161).

## 5. ЧТО ПРОЧИТАТЬ (КОДЕР / Агент)
apps/api/app/day_clock.py 9,8; apps/api/app/life_ops.py 16,6; apps/api/app/notify_ladder.py 11,0;
apps/api/app/day_keys.py 4,6; apps/api/app/projector.py 31,3 (только docstring);
apps/api/tests/test_day_current.py 11,3; apps/api/tests/test_notify_ladder.py 13,1 (образец фикстур и сценариев с БД);
AGENT-BRIEF.md 16,7; docs/decisions/DECISIONS.md 7,7; эта карточка ≈ 11. Чтение ≈ 133 КБ.

## 6. Файлы
- Изменить: apps/api/app/day_clock.py, apps/api/app/life_ops.py, apps/api/app/notify_ladder.py, apps/api/app/day_keys.py,
  apps/api/app/projector.py (только docstring), apps/api/tests/test_day_current.py (одна строка, раздел «Задетые тесты»).
- Создать: apps/api/tests/test_clocks_1.py. Удалить: ничего.

## 7. Контракт
(б) day_clock:
- Новая константа REFLECTION_DAYS = (6, 13) и функция is_reflection_day(day_no) → bool. bool и не-int → False.
- close_outcome(came, missed_streak, lives, *, is_reflection_day=False). Проверки входа — как сейчас (lives = 0 → ValueError).
- При флаге True возвращается CloseOutcome(outcome = came/silent по came, missed_streak = 0, life_delta = −1, sleeping = lives − 1 == 0).
  Ровно 1 жизнь, даже если missed_streak = 1. При флаге False поведение прежнее, позиционные вызовы не меняются.
- Поле outcome остаётся из прежнего набора, поэтому DAY_CLOSED_OUTCOMES в проекторе не трогаем.
(б) life_ops:
- В _plan и dry_run: close_outcome(came, row.missed_streak, row.lives, is_reflection_day=day_clock.is_reflection_day(row.day_no)).
- SQL _STATE не трогаем, day_no в нём уже есть. В dry_run новых ключей нет: −1 видно в outcome_if_closed_now.
- reason = LIFE_OP_REASON ("missed_days"). life_op пишется по прежнему правилу «delta ≠ 0».
- «Отчёт сдан → жизнь цела» обеспечивает шаг 4: есть ключ day_done → пропуск. Так же для all_not_done: ключ тот же.
- Docstring life_ops: в шаг 5 дописать про день рефлексии.
(в) day_keys:
- Добавить KIND_LADDER_DAY2 = "ladder_day2", TTL_LADDER_DAY2 = "3650 days", запись в TTL_BY_KIND
  и key_ladder_day2(pid, started_at) → "ladder_day2:{pid}:{dsa}". Строку формата дописать в docstring модуля.
(в) notify_ladder:
- EVENT_TYPE_DAY2 = "ladder_day2_alert".
- Добавить _LAST_DAY_CLOSED = SELECT payload FROM participant_events WHERE pid = :pid AND kind = 'day_closed' ORDER BY id DESC LIMIT 1.
- Чистая функция is_day2(payload, started) → bool. True, только если payload — dict, payload["outcome"] == "came",
  next_day_started_at — строка ISO с поясом и в UTC равна started. Любое другое значение или исключение разбора → False.
- В _write фиксируется, вставлен ли ключ plus1h в этой транзакции: шаг в plan.late (_insert_key вернул True) или plan.send.
  Если вставлен: читается _LAST_DAY_CLOSED; is_day2 → ключ key_ladder_day2 через notify_ops._INSERT_KEY (RETURNING);
  ключ вставлен → одна строка через notify_ops._INSERT_OUTBOX: aggregate_id = str(pid), event_type ladder_day2_alert,
  payload = {"pid": str(pid)}. Ровно такой payload проверяет бот (bot-group-1 §7, шаг 5).
  Ключ уже есть → без строки и без отката.
- Всё в той же транзакции, один commit. Если ключа send нет → откат всего, как сейчас.
- Подсчёт: необязательный параметр day2_counter: list[int] | None = None у ladder_one и _write (по образцу late_counter).
  NotifyResult не меняется. Существующую строку лога не трогать.
  Новая отдельная строка INFO: «notify_ops: ladder day2=%s», без pid.
- LadderPlan, decide_ladder, step_times и _candidates не менять.
- Docstring: строку «Алерт Автору „день 2 проблемы“ — вне задачи» заменить описанием алерта.
- Если на момент выката ключ plus1h за текущий день уже есть — алерта за этот день не будет (один раз, при выкате).
(г) projector.py, только docstring: в абзац про шаги «часов» в run_forever дописать: life_ops — день рефлексии (−1 сразу);
  notify_ops — НП1 noon_nudge (T3) и лестница ladder_reminder (T2) + ladder_day2_alert. PROJECTOR_VERSION = 3, без изменений.

## 8. БД
Миграции нет. Новых прав не нужно: app_projector уже читает participant_events (_PENDING_EVENT) и пишет idempotency_keys и outbox.
expected_tables.txt не трогаем. Если окажется, что миграция нужна — стоп и вопрос ШТАБу.

## 9. Тесты (apps/api/tests/test_clocks_1.py)
Без БД:
1. is_reflection_day: 6 и 13 → True; 1, 5, 7, 12, 14, None, True → False.
2. close_outcome с флагом: came при streak 0 → (came, 0, −1). silent при streak 1 → (silent, 0, −1), не −2. lives 1 → sleeping. lives 0 → ValueError.
3. close_outcome без флага — прежние значения (контроль). key_ladder_day2 — формат; TTL_BY_KIND["ladder_day2"] == "3650 days".
4. is_day2: came + next == started (в другом поясе тоже) → True. silent / next ≠ started / нет поля / не строка / naive / не dict → False.
С БД (только CI; состояние готовит владелец БД UPDATE-ом, как в test_notify_ladder):
5. День 6 с отметками, без отчёта, tick после дедлайна → life_op (delta −1, reason missed_days) и day_closed came.
   После run_once: lives на 1 меньше, missed_streak 0.
6. День 13, тишина, missed_streak 1 → lives на 1 меньше (не на 2), missed_streak 0.
7. День 6 с ключом day_done → ни ключа day_close, ни событий. День 6 при lives 1 → после run_once sleeping.
8. Дни 5 и 7 → прежнее поведение (came → без life_op). dry_run на дне 6 → outcome_if_closed_now.life_delta == −1.
9. «День 2»: день 1 с отметками закрыт tick-ом life_ops (came) → run_once → день 2. Отметка в день 2, tick_ladder в first + 1 ч →
   1 строка ladder_reminder, 1 строка ladder_day2_alert (payload {"pid"}), ключ ladder_day2. Повторный tick → второго алерта нет.
10. plus1h ушёл в late (первая отметка дня 2 в 21:30) → алерт есть. Простой до 23:30 → алерт есть.
11. Прошлый день silent; day_closed нет вовсе; ключ plus1h записан раньше → алерта нет.
12. Логи (caplog) без pid; есть строка «ladder day2=».
Цели: bash tools/check.sh api. Тесты с БД — только CI.

## Задетые тесты
Поиск по правилу «Т» и общим спискам проведён по импортам. Остальное покажет CI.
- apps/api/tests/test_day_current.py::test_kinds_and_ttl: в словарь добавить строку "ladder_day2": "3650 days",  # clocks-1
- test_day_clock.py: правок нет, вызовы close_outcome позиционные.
- test_life_ops.py, test_life_ops_race.py: правок нет, везде день 1, reason прежний.
- test_notify_ladder.py: правок нет, _outbox фильтрует ladder_reminder, предыдущего day_closed нет.
- test_notify_ops.py (статический тест читает только notify_ops.py), test_notify_noon.py, test_projector_v3.py: правок нет.
Итог: задетых 1.

## 10. Живые проверки на сервере (после мержа)
- СЕРВЕРНЫЙ: build projector, пересоздать только projector. api — по решению ШТАБа (поведение api не меняется).
- Логи projector: Traceback 0, WARNING 0, есть строки «ladder sent=» и «ladder day2=».
- python -m app.life_ops dry-run <pid А1> — только чтение. Вывод печатается, ошибок нет.
- Сценарии «день 6» и «день 2» — только по указанию ШТАБа. Тестовый день А1 не трогать. Только метки А1–А4, имён нет.

## 11. Запреты
- AGENT-BRIEF §3. Без миграций, GRANT и новых прав. notify_ops.py не менять. projector.py — только docstring.
- PROJECTOR_VERSION, LIFE_OP_REASON, DAY_CLOSED_OUTCOMES, LadderPlan, NotifyResult не менять.
- В app/ вне projector.py нет SQL записи в participant_state. Регулярка test_projector_static проверяет и docstring.
- Docstring life_ops, notify_ladder, day_clock, day_keys пишутся без фраз «INSERT INTO participant_state» и «UPDATE participant_state».
- В логах нет pid, tz, payload и ПДн. Тексты курса не писать: у алерта текст делает бот, заглушка там уже есть.
- datetime.now() и SQL now() в логике не использовать, now приходит аргументом.

## 12. Критерии готовности
CI зелёный, тесты §9 есть. Из существующих тестов изменена только строка в test_kinds_and_ttl. Живая проверка §10 прошла.

## 13. Оценка
Агент 650–850 кредитов. Часы Автора ≈ 1 (промпт, PR, выкат).

## 14. РЕВЬЮЕР: нет
Задача не трогает initData, 18+, согласия (B-2), rate-limit (B-1), роли и GRANT (B-3), оплату.

## Вне задачи
- reason reflection_day — к журналу жизней (Блок 17).
- Поле рефлексии в отчёте и reflection_required — api-refl-1. Вердикт 13-M / 13-P на переходе дня 14 — не здесь.

## Канон и решения
(а) Используются: 02 §2.2, §2.3 (и YAML lives.loss_conditions.reflection_day); 03 §3.12, §3.13, §3.17; 08 §8.2.
(б) Противоречий с DECISIONS.md нет. НП «активность — только day_marks» совпадает с came.
    В7 А (pushi.md) относится к напоминаниям участнику, алерт Автору под него не попадает.
(в) Пусто.
(г) Правок канона нет. Канон: проверено DECISIONS@709ab90, выдержки iter2-rest §1, цитата 02 §2.3 от ШТАБа.
