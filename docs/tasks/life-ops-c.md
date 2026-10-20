# life-ops-c — «часы» дня: закрытие в 00:00, пропуски, жизни, sleeping (в процессе проектора)

## 1. Паспорт
- id: life-ops-c · область: API/проектор (apps/api) · режим: Р1 (Агент Genspark).
- Заголовок PR: feat(api): life-ops-c — часы дня в проекторе (day_closed, life_op), dry-run
- Ветка: feat/life-ops-c · Зависит от: life-ops-b (начинать после мержа b; нужны day_clock, ключи, проектор v3, окно API).
- Миграций нет, таблиц 15. Outbox НЕ пишется (пуши — отдельная задача). Выкат: projector + api вместе.

## 2. Цель
Раз в 30 с проектор закрывает просроченные дни без отчёта: «пришёл» → счётчик 0; молчание → missed_streak +1,
на втором подряд −1 жизнь и счётчик 0; 0 жизней → sleeping. Новый день — с последней наступившей 00:00.
Один исход на pid + день: повтор после рестарта ничего не спишет второй раз.

## 3. Решения Автора (дословно)
- 20.10: «отчёты сдаются до 00:00!!! …» (полностью — life-ops-a §3). В4 — В («часы» в проекторе).
- Номера ШТАБа: В27 — А (DM 3.6/3.4, см. a §3); В29 — да (onboarding и active при наличии позиции;
  0 жизней → sleeping, в т.ч. из onboarding); В31 — два kind (life_op, day_closed); В32 — да (после простоя
  одна граница, дни простоя жизни не списывают). ЛО-3 да: «часы» — только дни без отчёта.
- ШТАБ: замок — только 'participant:'||pid (В20, D-25); в транзакции — один участник; гонка 23:59:59 / 00:00 — тест обязателен.
- Пауз нет (Р-6а не построен) — «часы» их не обрабатывают; участник с author_pause_reason и в sleeping — пропуск.

## 4. Выдержки
- DM 3.4: «Пришёл» — отметки есть, отчёта нет: жизнь не сгорает. DM 3.6: «каждые 2 дня полного молчания
  подряд = −1, счётчики обнуляются». DM 3.14: в паузе «жизни и таймеры заморожены».
- I2B: lives в [0, 3]; 0 → sleeping (Р477); kind 'life_op'. FSM: active → sleeping по no_life
  (из onboarding в каноне перехода нет — решение Автора В29, кандидат DEFECTS).
- E1/INV-1: participant_state пишет только проектор. «Часы» пишут ТОЛЬКО события и ключи.

## 5. ЧТО ПРОЧИТАТЬ
apps/api/app/projector.py — 19 КБ (v3 из a; цикл run_forever, курсор/checkpoint); app/day_clock.py, day_keys.py — ≈ 6;
app/participant_lock.py — 3; apps/api/tests/test_projector_v3.py (из a) — фикстуры; app/routers/day.py — только
обработчик submit (для теста гонки). Чтение Агента ≈ 60–70 КБ.

## 6. Файлы (4 файла, ≈ 560 строк)
- Создать: apps/api/app/life_ops.py; apps/api/tests/test_life_ops.py; apps/api/tests/test_life_ops_race.py.
- Изменить: apps/api/app/projector.py — только вызов шага «часов» в run_forever (≈ 20 строк).

## 7. Контракт
life_ops.tick(engine, now) → TickResult(closed, skipped). Вызов — из run_forever раз в 30 с (LIFE_OPS_INTERVAL_S = 30),
now = day_clock.utcnow(). Исключение в tick → WARNING (имя класса), цикл проектора живёт дальше. once — без tick.
1. Кандидаты (своя транзакция, только чтение): pid, tz, day_started_at из participant_state, где
   lifecycle_phase IN ('onboarding', 'active') AND author_pause_reason IS NULL AND day_no IS NOT NULL;
   в Python — is_overdue(day_started_at, tz, now). Не больше 200 за тик (остальные — в следующем).
2. Каждый pid — отдельная транзакция: lock_participant(session, pid) → заново прочитать state (фаза, lives,
   missed_streak, tz, day_started_at = D) → снова проверить фильтр п. 1 и is_overdue → иначе rollback, пропуск.
3. «Проектор догнал pid»: нет событий pid новее курсора проектора (как курсор хранится — по projector.py).
   Есть — rollback, пропуск (следующий тик). Так отчёт, принятый до 00:00, но ещё не применённый, не теряется.
4. Есть ключ key_day_done(pid, D) или key_day_close(pid, D) → rollback, пропуск.
5. came = есть строки day_marks по (pid, D). o = day_clock.close_outcome(came, missed_streak, lives).
6. INSERT idempotency_keys key_day_close(pid, D), kind day_close, ttl 3650 days, ON CONFLICT DO NOTHING
   RETURNING key. 0 строк → rollback, пропуск (идемпотентность после рестарта).
7. o.life_delta ≠ 0 → INSERT participant_events kind life_op {day_started_at: dsa(D), delta: −1, reason: "missed_days"}.
   Затем INSERT kind day_closed {day_started_at: dsa(D), outcome, missed_streak: o.missed_streak,
   next_day_started_at: dsa(last_midnight(now, tz))}. actor "life_ops", actor_role "system". COMMIT.
8. Лог INFO на pid: исход и delta, без ПДн. Итог тика — одной строкой.
python -m app.life_ops dry-run <pid>: роль проектора (PROJECTOR_DATABASE_URL), только SELECT, ROLLBACK;
  печатает фазу, lives, missed_streak, tz, day_started_at, active_from, deadline_at, is_overdue и исход
  «если закрыть сейчас». Неверные аргументы → код 2 за < 1 с без БД и настроек (импорт БД — внутри команды).
В тексте life_ops.py не писать INSERT INTO/UPDATE + participant_state подряд (test_projector_static).

## 8. БД
Миграции нет. Права app_projector есть: SELECT participant_state (reader), SELECT day_marks (0008),
SELECT/INSERT idempotency_keys и INSERT participant_events + USAGE seq (0007). pg_advisory_xact_lock — у PUBLIC.

## 9. Тесты (now — аргументом tick; БД — CI)
- test_life_ops.py: молчание 1 → missed_streak 1, lives 3; второе молчание → lives 2, счётчик 0; «пришёл»
  (отметки, без отчёта) → счётчик 0, lives те же; lives 1 + streak 1 + молчание → lives 0, sleeping, дальше
  тик его пропускает; onboarding → обрабатывается; sleeping и author_pause_reason → пропуск; до
  дедлайна + 120 с → ничего; tick дважды с тем же now (рестарт) → один ключ, одна пара событий, одно списание;
  простой 5 суток → одно закрытие, новый day_started_at = последняя полночь; есть необработанное событие pid → пропуск;
  dry-run ничего не пишет; main() dry-run без аргумента → код 2.
- test_life_ops_race.py: отчёт submit через API в 23:59:59 (monkeypatch utcnow) → tick в 00:02:01 до
  projector run_once → пропуск (догнал = нет); после run_once → день сдвинут отчётом, tick → ничего,
  жизнь не списана. Обратный порядок: tick в 00:02:01 закрыл день → submit со старым днём → 409 (не 200).
- test_projector_static.py — зелёный. Быстрые — tools/check.sh; БД — CI 7/7.

## 10. Живые проверки (время в коде не подменять)
1. После выката: logs projector — строки итога тика, нет Traceback. dry-run по тестовому pid Автора — границы верные.
2. Наблюдение: тестовый вход в день X (флаг DAY_TEST_ENTRY_ENABLED включить и выключить в одном задании),
   ничего не отмечать. Утро X+2 (после 00:02) — SELECT: missed_streak 1, lives 3. Утро X+3 — lives 2, missed_streak 0.
   Других участников с позицией дня на сервере нет — сверить SELECT до выката.

## 11. Запреты
AGENT-BRIEF §3. Не писать в participant_state (только события). Ключ 'life:' не использовать. Замок — один pid
на транзакцию. Outbox и тексты бота — не здесь. Миграций нет. Переносы ревью #103 — не делать (api-3).

## 12. Готовность
tick и dry-run по §7; вызов в run_forever; тесты §9 зелёные, включая гонку; CI 7/7; РЕВЬЮЕР — 0 блокирующих.

## 13. Оценка
Автор ≈ 0,8 ч + сервер 1 задание + 2 SELECT наблюдения. Кредиты Агента ≈ 900–1 100.

## 14. РЕВЬЮЕР: да — списание жизней (деньги участника), идемпотентность закрытия, замок и гонка с отчётом.
