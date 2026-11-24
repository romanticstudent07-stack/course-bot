# pause-api-a5 — GET /pause отдаёт start_date (блокер Б1)

Hash main: 7316c1f5fbc04329b5667cf8d111b1b814dca352. Ветка исполнителя: feat/pause-api-a5. PR без мержа.
Правило К — docs/process/CANON-CHECK.md. Сначала прочитай docs/decisions/DECISIONS.md целиком.
Основание: docs/research/t5-bc.md §1 «Блокер Б1»; решение ШТАБа — вариант «в».

## 1. Цель
Клиенту Mini App (T5-B/T5-C) нужна дата начала паузы, чтобы участник подтвердил её
и отправил в POST /pause/request (поле start_date, R-2026-11-21 «Поздняя доставка: форма»).
Сейчас GET /pause этой даты не отдаёт. Задача: добавить в ответ GET /pause поле start_date.

## 2. Канон и решения
- Поле start_date (date, YYYY-MM-DD) в ответе GET /pause — [ШТАБ-тех, К-5]. Имя — [ШТАБ-тех].
- Значение: местная дата day_clock.next_midnight(now, tz) по поясу участника — тот же расчёт,
  что в request_pause шаг 4 (_bounds) и в read_status (start_at для refusal) [ШТАБ-тех; по коду: pause.py].
- Поле есть всегда, в том числе при can_request = false и refusal = "already_open" [ШТАБ-тех].
- Поздняя доставка: дата не сдвигается, отказ 409 PAUSE_REFUSED {"reason": "start_date_passed"}
  и новое подтверждение — уже в коде [Автор, R-2026-11-21 «Поздняя доставка: форма»]. Логику request не менять.
- R-2026-11-21 «Границы подтверждения»: форма API не утверждалась (expected_start_at, server_now,
  valid_until не вводятся). start_date в GET с этим не спорит. Канон: проверено DECISIONS.md, R-2026-11-21.md.
- (в) Контракт GET /pause поля не знает. Канон: docs/architecture/build/miniapp-api-contract.yaml
  «Паузы», /miniapp/v1/pause get (строки 304–318 по main 7316c1f5). build/ — не normative, правка прямо в тело.
  Правка идёт PR в DOCS-course-bot и sync в course-bot ДО промпта исполнителю. Точная правка — раздел 3.

## 3. Правка DOCS (до исполнителя)
Файл: build/miniapp-api-contract.yaml (в course-bot после sync — docs/architecture/build/miniapp-api-contract.yaml).
Правка 1. Найди (в /miniapp/v1/pause get, responses "200"):
    required: [budget_days_left, budget_days_total, cycle_ends_at, pause, can_request, refusal]
Замени на:
    required: [budget_days_left, budget_days_total, cycle_ends_at, pause, can_request, refusal, start_date]
Правка 2. Найди (там же, конец строки "200"):
    refusal: { type: [string, "null"] } } } } } }
Замени на:
    refusal: { type: [string, "null"] }, start_date: { type: string, format: date, description: "местная дата ближайшей 00:00 по поясу участника (YYYY-MM-DD); есть всегда" } } } } } }
Правка 3. Найди (description GET /pause, первое вхождение в файле):
            Уточнено реализацией course-bot (pause.py).
Замени на две строки:
            start_date — дата, которую участник подтверждает в POST /pause/request (R-2026-11-21).
            Уточнено реализацией course-bot (pause.py).
Отступ строк description — 8 пробелов, как в файле.

## 4. Область
Только apps/api. Правится apps/api/app/routers/pause.py и apps/api/tests/test_pause_api_db.py.
Миграции нет. POST /pause/request, /pause/cancel, /pause/resume не трогать.
Формат логов app.pause не менять: start_date и tz в лог не писать.

## 5. Что сделать в pause.py (по коду: pause.py@7316c1f5)
1) Новая функция рядом с _bounds:
    def _local_start_date(now: datetime, tz: str | None) -> date:
        """Местная дата ближайшей 00:00 по поясу (Д3) — та же, что start_at в _bounds."""
        start = day_clock.next_midnight(now, tz)
        return _utc(start).astimezone(day_clock.zone(tz)).date()
2) PauseStatusOut: последним полем добавить
    start_date: date
3) read_status: start_at = day_clock.next_midnight(now, tz) считать ДО проверки open_row
   (сейчас он только в ветке else); в ветке else использовать его же. В PauseStatusOut передать
   start_date=_utc(start_at).astimezone(day_clock.zone(tz)).date() или _local_start_date(now, tz).
   Расчёт refusal не меняется.
4) request_pause шаг 4: сравнение заменить на
    if _local_start_date(now, tz) != start_date:
   Поведение то же (одна формула). Порядок шагов и коды ошибок не менять.
5) Docstring модуля, раздел GET /pause, добавить пункт:
    4) start_date — местная дата next_midnight(now, tz) по поясу участника, всегда
       (и при can_request = false); клиент шлёт её в POST /pause/request (R-2026-11-21).
   Строку «pid, pause_id, op, tz и start_date в логе нет» оставить как есть.

## 6. Задетые тесты (правило «Т»)
Поиск: git grep по apps/api/tests (вывод Автора 24.11). Ответ GET /pause целиком сверяет один тест.
- apps/api/tests/test_pause_api_db.py::test_get_without_budget_row — в словаре
  assert r.json() == {...} после строки "refusal": None, добавить строку
    "start_date": "2026-11-21",
  (NOW = 2026-11-20 09:00 UTC = 12:00 МСК; ближайшая 00:00 Europe/Moscow — 2026-11-21 = TOMORROW.date()).
Регрессия без правок: test_get_anniversary_in_past, тесты request / cancel / resume в
test_pause_api_db.py; apps/api/tests/test_pause_api.py (строка 27 — список маршрутов без initData).
Упал тест вне списка → не чинить, «тест X вне списка» в ИТОГ и стоп.

## 7. Новые проверки
- test_get_open_request (can_request = false, already_open): в конец добавить
    assert body["start_date"] == TOMORROW.date().isoformat()
- Новый тест test_get_start_date_after_midnight: pause.get_now подменить на
  datetime(2026, 11, 20, 21, 30, tzinfo=timezone.utc) (00:30 МСК 21.11), участник со своим
  tg_user_id из диапазона 8811–8899, не занятым в файле; ожидать "start_date": "2026-11-22".

## 8. Исполнитель
КОДЕР (Р0+, 0 кредитов). Причина: одна функция и одно поле в одном файле, 3 точечные правки
тестов, без миграции и новой механики; прецедент — pause-api-a1 #284 (КОДЕР / 0).
Тесты с БД проверяет только CI (REQUIRE_DB_TESTS=1).

## 9. Проверка исполнителем
bash tools/check.sh api. CI — 7 проверок, проверяет Автор.

## 10. Готово, когда
GET /pause возвращает start_date во всех ветках; request ведёт себя как раньше;
тесты разделов 6–7 зелёные в CI; лог app.pause без новых полей.

## 11. Не делать
Не трогать POST /pause/*, миграции, pause_rules, day_clock, логи, docs/architecture/**.

## 12. Сервер
Выкат позже (PLAN §4): образ api в очереди SHTAB-DEBTS §1 вместе с п.6.

## 13. Вопросы
Нет (все решения — ШТАБ, указания 1–7).

## 14. РЕВЬЮЕР
Нет: правка меньше порога, поведение request не меняется.
