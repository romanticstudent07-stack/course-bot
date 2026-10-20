# life-ops-b — API дня: окно 04:00–00:00 (409), позиция после отчёта, очередь 10–60 мин в GET

## 1. Паспорт
- id: life-ops-b · область: API (apps/api) · режим: Р1 (Агент Genspark).
- Заголовок PR: feat(api): life-ops-b — окно дня (409 DAY_CLOSED/DAY_NOT_ACTIVE), позиция в отчёте, очередь в GET
- Ветка: feat/life-ops-b · Зависит от: life-ops-a (начинать после мержа a). Дальше: life-ops-c.
- Миграций нет, таблиц 15. Выкат: api + projector вместе (лучше вместе с c — см. §10).

## 2. Цель
Отметки и отчёт принимаются только в окне дня (с 04:00 до 00:00 по поясу участника). Отчёт сам выдаёт
следующий день: passed → следующий, иначе тот же (ЛО-3). GET /day/current показывает границы окна и
статус «в очереди» 10–60 мин после отчёта (ЛО-1 Б). Сообщения бота — не здесь (пуши).

## 3. Решения Автора (дословно)
- 20.10: «отчёты сдаются до 00:00!!! … кнопки нажать что выполнил может только в 04:00 следующего дня!!!!»
  (полностью — life-ops-a §3).
- 20.10: «ЛО-1-Б, ЛО-2-А (но тут нужно придумать или вместе с заданиями уведомление или отдельно бот напишет,
  что "заданию доступны к выполнению с завтрашнего дня" или "внимание начинаем завтра с 4:00 кнопки
  активируются"), ЛО-3 да, ЛО-4 да».
- В30 (номер ШТАБа): passed → следующий день сразу (показ после очереди, кнопки с 04:00); not_passed и
  all_not_done → тот же день, жизнь цела. Модули, этапы и день 13 — позже.
- ШТАБ, 20.10: 409 DAY_CLOSED (после 00:00), DAY_NOT_ACTIVE (до 04:00); повтор того же X-Client-Op-Id —
  раньше этих проверок, тот же 200. Уведомление по ЛО-2: экран /day (поле active_from) и бот (пуши).

## 4. Выдержки
- DM 3.1: кнопки активны в 04:00 по поясу; «сегодня выдано — завтра выполняется».
- DM 3.9: время сдачи — по серверу; «≤ дедлайна — принят»; повтор игнорируется (3.10).
- DM 3.19, yaml: «queue: random(10min, 60min)»; «day_counting: instant_regardless # очередь влияет ТОЛЬКО на показ».
- П-31: зачёт — только после подтверждённой записи в БД. DM 3.21: смена пояса — со следующего дня.

## 5. ЧТО ПРОЧИТАТЬ
apps/api/app/routers/day.py — 31 КБ; apps/api/app/day_clock.py и day_keys.py (из a) — ≈ 6; app/day_content.py — 7;
app/day_report.py — 3; app/participant_lock.py — 3; тесты submit из iter2-api-2b (один раз ls apps/api/tests,
открыть только файл тестов day/report/submit). Чтение Агента ≈ 70–80 КБ.

## 6. Файлы (≤ 4 файла, ≈ 520 строк)
- Изменить: apps/api/app/routers/day.py.
- Создать: apps/api/tests/test_day_window.py (окно, 409, гонка на 00:00); apps/api/tests/test_day_queue.py
  (позиция в payload, ключ очереди, GET).
- Изменить при необходимости: файл тестов submit из iter2-api-2b — только если его ожидания ломает новое окно
  (фиксировать «сейчас» внутри окна); перечислить в PR.

## 7. Контракт
Общее: «сейчас» = day_clock.utcnow(), взять ПОСЛЕ замка participant:pid (lock_participant). Окно считать
по day_started_at и tz из participant_state (SELECT tz — к текущему чтению state). day.py не пишет participant_state.
POST /day/marks: после замка и чтения state → day_clock.window: "not_active" → 409 DAY_NOT_ACTIVE;
  "closed" → 409 DAY_CLOSED; иначе как сейчас.
POST /day/report/submit, порядок: замок → state → повтор по X-Client-Op-Id (как сейчас, тот же 200) →
  окно (409 как в marks) → прежние проверки → запись. В той же транзакции:
- payload day_report_submitted дополнить: next_stage_no, next_module_no, next_day_no, next_day_started_at = dsa(now).
  passed → следующий день того же модуля (day_no + 1), если он есть в DayContent; нет → та же позиция
  (день 13 и переходы модулей — позже). not_passed / all_not_done → та же позиция.
- INSERT idempotency_keys: key_day_queue(pid, now), kind day_queue, ttl 3650 days.
Тело 409 — тот же формат ошибки, что у других кодов day.py; в лог — tg_user_id и код, без тела.
GET /day/current, новые поля (ISO 8601 со сдвигом пояса участника):
- active_from, deadline_at — при наличии позиции, иначе null; buttons_active = (window == "open");
- can_submit = прежнее условие И window == "open";
- статус "queued": есть ключ day_queue по текущему day_started_at и now < queue_until → queued_until;
  задания дня (позиция, блоки, отметки) не отдаются (null / пустые); остальные поля — как обычно;
- статус "closed": window == "closed" и нет ключа day_done (день ждёт «часов» из c);
- "submitted" (ключ day_done есть, проектор ещё не сдвинул день, обычно ≤ 2 с) — без изменений.
- Повтор GET не меняет queued_until (формула детерминирована).
test-enter не меняется: первый день получает кнопки с ближайшей 04:00 (ЛО-2 А) — через active_from.

## 8. БД
Миграции нет. Права app_api есть: INSERT/SELECT idempotency_keys (0007), SELECT participant_state (tz — 0007).

## 9. Тесты (utcnow — monkeypatch; БД — CI)
- test_day_window.py: marks и submit до 04:00 → 409 DAY_NOT_ACTIVE; в 04:00:00 → 200; submit 23:59:59 → 200;
  ровно 00:00:00 → 200; 00:00:01 → 409 DAY_CLOSED; повтор того же op_id после 00:00 → тот же 200 (не 409);
  состояние, events и ключи после 409 не меняются; можно отправить не позже 00:00 → ответ 200 = запись есть (П-31).
- test_day_queue.py: payload next_* (passed → day_no + 1; passed на последнем дне контента → та же позиция;
  not_passed и all_not_done → та же); ключ day_queue записан; после projector run_once GET → queued и
  queued_until в [10, 60] мин; на queued_until + 1 с → open, buttons_active false, active_from = ближайшая 04:00;
  поля active_from/deadline_at у дня из test-enter.
- Прежние тесты day/* зелёные. Быстрые — tools/check.sh; БД — CI 7/7.

## 10. Живые проверки (после мержа; DAY_TEST_ENTRY_ENABLED включить и выключить в одном задании)
Тестовый pid Автора: test-enter днём → GET: active_from = завтра 04:00, buttons_active false; marks → 409
DAY_NOT_ACTIVE. Флаг выключить, проверить false. Отчёт — на следующий день после 04:00 → GET queued.
Без c просроченный день остаётся «closed» (только у тестового pid) — поэтому лучше выкатить b вместе с c.

## 11. Запреты
AGENT-BRIEF §3. Не писать слова INSERT INTO/UPDATE + participant_state подряд (тест static). Время в рабочем
коде не подменять (только monkeypatch в тестах). Outbox не трогать. Переносы ревью #103 (pg_locks,
_wait_for_lock_waiter, op_id в другой день, result_ref вне VERDICTS, только UUID v4) — НЕ делать (api-3).

## 12. Готовность
Окно на marks и submit; повтор раньше 409; payload next_*; ключ day_queue; GET с полями §7; тесты §9; CI 7/7;
РЕВЬЮЕР — 0 блокирующих.

## 13. Оценка
Автор ≈ 0,8 ч + сервер 1 задание. Кредиты Агента ≈ 700–900.

## 14. РЕВЬЮЕР: да — П-31 и идемпотентность отчёта, граница дня (зачёт = жизни), initData → pid.
