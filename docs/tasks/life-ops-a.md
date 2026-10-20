# life-ops-a — day_clock (границы дня, очередь), ключи day_close/day_queue, проектор v3

## 1. Паспорт
- id: life-ops-a · область: API/проектор (apps/api) · режим: Р1 (Агент Genspark, код по карточке).
- Заголовок PR: feat(api): life-ops-a — day_clock, ключи day_close/day_queue, проектор v3 (life_op, day_closed)
- Ветка: feat/life-ops-a · Зависит от: нет (main 1f6f256). Дальше: life-ops-b (после мержа a) → life-ops-c (после мержа b).
- Миграций нет: таблиц 15, expected_tables.txt не меняется. Новая зависимость: tzdata==2026.5 (ЛО-4).
- Выкат: api и projector вместе (образ один — apps/api; новые kinds в проекторе).

## 2. Цель
Всё время дня — в одном месте: app/day_clock.py (кнопки с 04:00, дедлайн 00:00, пауза 120 с, очередь
10–60 мин, исход закрытия дня). Ключи day_close и day_queue. Проектор v3 применяет life_op, day_closed
и новые поля day_report_submitted. Пишут эти события задачи b и c: после a их никто не пишет,
поведение сервера не меняется.

## 3. Решения Автора (дословно)
- 20.10: «отчёты сдаются до 00:00!!! в 04:00 не задания открылись а кнопки под заданиями стали Активны!
  Задания следующего дня высылаются после сдачи отчёта, но с хитрой паузой от 10 до 60 (кажется).
  участник посмотреть задания завтрашнего дня может и сегодня после сдачи отчёта, а кнопки нажать что
  выполнил может только в 04:00 следующего дня!!!!»
- 20.10, «ОК все рекомендации» (номера ШТАБа): В27 — А (по DM 3.6/3.4: полное молчание → missed_streak +1;
  на 2 → −1 жизнь и счётчик 0; «пришёл» → счётчик 0, жизнь цела; любой отчёт → 0, В18); В29 — да
  (onboarding и active при наличии позиции; 0 жизней → sleeping, в т.ч. из onboarding); В30 — passed →
  следующий день сразу, not_passed/all_not_done → тот же день; В31 — два kind: life_op и day_closed;
  В32 — после простоя одна граница; В33 — разрезка; РЕВЬЮЕР — да.
- 20.10: «ЛО-1-Б, ЛО-2-А (…), ЛО-3 да, ЛО-4 да» (ЛО-4 = зависимость tzdata, точная версия ==).
- В4 = В: «часы» — в процессе проектора (iter2-db-1 §3). Замок — только 'participant:'||pid (В20).

## 4. Выдержки (Агент docs/architecture/** не читает)
- DM 3.1: «Задания дня и кнопки под ними становятся активными в 04:00 по локальному времени Участника».
  «сегодня выдано — завтра выполняется».
- DM 3.4: «Пришёл» (отметки есть, отчёт не отправлен) — жизнь не сгорает. DM 3.6: «каждые 2 дня полного
  молчания подряд = −1, счётчики обнуляются». DM 3.9: время сдачи — по серверу, «≤ дедлайна — принят».
- DM 3.19, yaml: «queue: random(10min, 60min) # не раньше 10, не позже 60»; «day_counting: instant_regardless
  # очередь влияет ТОЛЬКО на показ»; «life_impact: none».
- DM 3.21, yaml: «timezone_change: applies: next_day_only; affects_running_deadline: false».
- I2B: участник — participant_state.lives, границы [0, 3]; 0 жизней → sleeping (Р477); событие жизни —
  kind 'life_op'. FSM: active → sleeping по no_life. E1/INV-1: participant_state пишет только проектор.
- DM 3.14: во время паузы «жизни и таймеры заморожены». Пауз в коде нет (Р-6а не построен).

## 5. ЧТО ПРОЧИТАТЬ (по hash из промпта)
apps/api/app/projector.py — 19 КБ; apps/api/app/day_keys.py — 2; apps/api/requirements.txt — 1;
apps/api/tests/test_projector_static.py — ≈ 3; apps/api/tests/conftest.py — фикстуры БД (если > 15 КБ — только они).
Чтение Агента ≈ 30–40 КБ.

## 6. Файлы (6 файлов, ≈ 580 строк)
- Создать: apps/api/app/day_clock.py; apps/api/tests/test_day_clock.py; apps/api/tests/test_projector_v3.py.
- Изменить: apps/api/app/projector.py; apps/api/app/day_keys.py; apps/api/requirements.txt (+ tzdata==2026.5
  с комментарием «IANA-пояса для zoneinfo в python:3.12-slim, life-ops-a, ЛО-4»).

## 7. Контракт
app/day_clock.py — чистые функции, без БД и логов, кроме WARNING о плохом поясе. Константы:
    ACTIVATION_TIME = time(4, 0)        # кнопки дня активны с 04:00 по поясу
    DEADLINE_TIME = time(0, 0)          # дедлайн — 00:00 следующих суток после активации
    CLOSE_GRACE = timedelta(seconds=120)
    QUEUE_MIN_MINUTES = 10; QUEUE_MAX_MINUTES = 60
    DEFAULT_TZ = "Europe/Moscow"
Функции (все datetime — aware; naive → ValueError, как day_keys.dsa):
- utcnow() → datetime.now(timezone.utc). Единственный источник «сейчас» для b и c (тесты подменяют monkeypatch).
- zone(tz_name) → ZoneInfo; пустой или неизвестный пояс → ZoneInfo(DEFAULT_TZ) + WARNING (имя пояса, без pid).
- active_from(started_at, tz) → первая 04:00 по поясу, которая ≥ started_at (03:59:59 → в тот же день 04:00;
  04:00:00 → она же; 04:00:01 → завтра).
- deadline_at(started_at, tz) → 00:00 по поясу на дату (active_from.date + 1 день).
- window(started_at, tz, now) → "not_active" (now < active_from) | "open" (active_from ≤ now ≤ deadline,
  обе границы включительно) | "closed" (now > deadline).
- is_overdue(started_at, tz, now) → now > deadline_at + CLOSE_GRACE.
- last_midnight(now, tz) → последняя 00:00 по поясу, которая ≤ now (простой → одна граница, В32).
- queue_delay(pid, started_at) → timedelta(minutes = 10 + int(sha256(f"{pid}:{dsa}").hexdigest(), 16) % 51),
  где dsa = day_keys.dsa(started_at). Детерминирована, хранить не надо (ЛО-1).
- queue_until(pid, started_at) → started_at + queue_delay.
- close_outcome(came, missed_streak, lives) → CloseOutcome(outcome, missed_streak, life_delta, sleeping):
  came=True → ("came", 0, 0, False); иначе streak+1; streak+1 ≥ 2 → life_delta −1, streak 0;
  sleeping = (lives + life_delta == 0). lives вне [0, 3] → ValueError.
Результаты переводить в пояс участника (astimezone(zone)); сравнения — в aware-времени.
В тексте day_clock.py не писать подряд слова INSERT INTO/UPDATE и participant_state (test_projector_static).
day_keys.py: KIND_DAY_CLOSE = "day_close", KIND_DAY_QUEUE = "day_queue"; ttl "3650 days" обоим;
  key_day_close(pid, ts) = "day_close:{pid}:{dsa}"; key_day_queue(pid, ts) = "day_queue:{pid}:{dsa}"; TTL_BY_KIND дополнить.
События (payload — JSON; время — UTC ISO как day_keys.dsa). Проектор v3, PROJECTOR_VERSION = 3:
- day_report_submitted (пишет b), новые поля: next_stage_no, next_module_no, next_day_no, next_day_started_at.
  Все четыре есть → позиция = next_*, day_started_at = next_day_started_at, missed_streak = 0; условие —
  текущий day_started_at = payload.day_started_at (поле v2; если в v2 имя другое — то, что есть).
  Нет полей → поведение v2 (только обнуление счётчика). Поле есть частично → WARNING, пропуск.
- life_op (пишет c): day_started_at, delta (−1), reason "missed_days". Применение: lives = lives + delta;
  lives + delta = 0 → lifecycle_phase = 'sleeping'; условие — day_started_at совпадает и 0 ≤ lives + delta ≤ 3.
  0 строк → WARNING, пропуск (как в v2).
- day_closed (пишет c): day_started_at, outcome ("came" | "silent"), missed_streak, next_day_started_at.
  Применение: day_started_at = next_day_started_at, missed_streak = payload; позиция не меняется;
  условие — day_started_at совпадает. 0 строк → WARNING, пропуск.
Порядок в c: life_op раньше day_closed (меньший e.id), поэтому оба видят старый day_started_at.
Повтор события после рестарта не применится второй раз: day_started_at уже другой.

## 8. БД
Миграции нет. Права уже есть: app_projector — запись в participant_state (0006), INSERT participant_events и
USAGE seq, SELECT/INSERT idempotency_keys (0007), SELECT day_marks (0008). Колонки lives, missed_streak, tz,
day_started_at — 0007; 'sleeping' — в CHECK lifecycle_phase (0005).

## 9. Тесты
- test_day_clock.py (быстрые): 04:00 ± 1 с; дедлайн; window на 03:59:59 / 04:00:00 / 00:00:00 (open) / 00:00:01;
  is_overdue на +120 и +121 с; last_midnight; queue_delay в [10, 60] мин, одинакова при повторе и разная у двух
  pid; плохой пояс → Moscow + WARNING; naive → ValueError; close_outcome (came; silent 0→1; 1→0 и −1; lives 1 → sleeping).
- test_projector_v3.py (БД, только CI): все 3 kind по правилам §7; старый payload #103 → только счётчик;
  чужой day_started_at → пропуск; lives 0 → sleeping; выход за [0, 3] → пропуск; once дважды — без изменений.
- test_projector_static.py — зелёный без правок; main() с неверным аргументом → код 2 за < 1 с.
- Быстрые: tools/check.sh (цель — как у прошлых API-задач); БД-тесты — CI 7/7.

## 10. Живые проверки (после мержа; выкат api + projector)
docker compose logs projector: нет Traceback, видна версия 3; SELECT участников — фаза и счётчики как до выката.
Новые kinds никто не пишет — других проверок нет.

## 11. Запреты
AGENT-BRIEF §3. Не писать в participant_state вне projector.py. Outbox не трогать. Ключ 'life:' не использовать.
Миграций, новых таблиц, правок ci.yml нет. Код вне §6 не менять. Тексты бота — не здесь.

## 12. Готовность
6 файлов; PROJECTOR_VERSION = 3; константы только в day_clock.py; тесты §9 зелёные; CI 7/7; РЕВЬЮЕР — 0 блокирующих.

## 13. Оценка
Автор ≈ 0,7 ч + сервер 1 задание. Кредиты Агента ≈ 600–800.

## 14. РЕВЬЮЕР: да — жизни участника (деньги), применение life_op в проекторе, единственный писатель (INV-1).
