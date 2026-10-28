# ladder-1 — лестница «пришёл, но не отправил» (DM 3.17): +1 ч, 22:00, 23:30

## 0. Паспорт
- Область: apps/api — новый app/notify_ladder.py, notify_ops.tick, day_keys, тексты. Миграций нет. Проектор не меняется (зовёт только notify_ops.tick — ШТАБ, 00bff0b).
- Старт — только после мержа noon-1 (читать по hash main после него).
- Ветка задачи: feat/ladder-1. check.sh: api. Режим: очередь Агента — решает ШТАБ.
- Оценка: 500–750 кредитов (общий цикл и NotifyTick уже есть после noon-1; новый модуль; 1 задетый файл).
- Правило К — docs/process/CANON-CHECK.md. Сначала прочитай docs/decisions/DECISIONS.md целиком.
- Агенту docs/architecture/** не открывать: выдержки — §4.

## 1. Цель
Участник отметил хотя бы одно задание текущего дня, а отчёт не отправил — бот напоминает три раза: через 1 час после первой отметки, за 2 часа до дедлайна (22:00), за 30 минут (23:30). Тексты — заглушки. Алерт Автору «день 2 проблемы» — вне задачи.

## 2. Решения (К-6)
- Р-6 тумблеров нет [STATE Р-6] = 09 R123-FINAL, NR-215. Р-8 ключ = раздел + имя маленькими, seed JSON [STATE Р-8]. (pushi.md §0 дословно)
- Первая отметка = min(day_marks.at) по (pid, day_started_at): PUT /day/marks пишет ON CONFLICT DO UPDATE SET value, at не меняется («пришёл» = min(at), В19) [по коду: apps/api/app/routers/day.py@00bff0b].
- В6 А — активность = только day_marks [Автор против канона → DECISIONS НП].
- В7 А — отправляется только самый поздний наступивший шаг; более ранние ненаступившие-до-этого шаги — ключ без отправки (как В4 А у НП3); шаг +1 ч не шлём, если его время не раньше «−2 ч» [Автор, канон молчит → DECISIONS НП].
- Т1 [ШТАБ, К-5]: лестница — отдельный модуль app/notify_ladder.py; вход один — notify_ops.tick.
- Т2 [ШТАБ-тех]: шаги «−2 ч» и «−30 мин» считаются от дедлайна day_clock (00:00 следующих суток после активации) вычитанием в UTC; tier T2.

## 3. Канон и решения
(а) Использует: 03 §3.17, yaml attended_not_sent_ladder, §3.4 «пришёл», §3.9 (серверное время), §3.21; 09 tiers (T2).
(б) Противоречий с DECISIONS нет. Уточнение: «через 1 час после отметки» — по коду это первая отметка дня (min(at)).
(в) Правка DOCS (маленький PR и sync ДО промпта Агенту):
1. architecture/03-day-mechanics.md · найди «через 1 час после отметки» · замени на «через 1 час после первой отметки дня»
(yaml «+1ч после отметки» — смысл тот же; та же правка — по желанию ШТАБа.)
(г) В7 А — канон молчит, правок нет (запись НП в DECISIONS).

## 4. Выдержки канона
- 03 §3.17: «День 1 проблемы: Участник отметил галочки, отчёт не ушёл → жизнь спасена. Бот напоминает по умной лестнице: через 1 час после отметки („отметил, но отчёт не ушёл — всё ок? нажми Отправить“), за ~2 часа до дедлайна (настойчивее), за ~30 минут до дедлайна (финально). (Не „каждые 15 минут“.) Отчёт так и не ушёл к дедлайну → Бот выдаёт те же задания на следующий день (день не засчитан, жизнь цела). День 2 проблемы: ситуация повторяется → Бот шлёт алерт Автору».
- 03 §3.4: «Пришёл» — есть галочки, отчёт не ушёл: жизнь не горит, день не засчитан.

## 5. Файлы (6)
1. apps/api/app/day_keys.py — KIND_LADDER = "ladder", TTL_LADDER = "3650 days", в TTL_BY_KIND; LADDER_STEPS = ("plus1h", "minus2h", "minus30m"); key_ladder(pid, started_at, step) → "ladder:{pid}:{dsa(started_at)}:{step}", неизвестный step → ValueError; строка в docstring.
2. apps/api/app/notify_ladder.py — новый, §6.
3. apps/api/app/notify_ops.py — NotifyTick получает поле ladder; tick вызывает третье правило.
4. apps/api/config/texts/day.json — §7; version 0.4.0 → 0.5.0.
5. apps/api/tests/test_notify_ladder.py — новый, §9.
6. apps/api/tests/test_day_current.py — задет, §8.

## 6. notify_ladder: что сделать
- Импорт без цикла: notify_ladder делает «from app import notify_ops» и берёт его помощники (_run_rule, _INSERT_KEY, _INSERT_OUTBOX, проверку «проектор догнал») только при вызове; notify_ops импортирует notify_ladder ВНУТРИ tick (комментарий: «notify_ladder импортирует notify_ops»). Своего SQL INSERT в outbox в notify_ladder нет.
- Константы: EVENT_TYPE = "ladder_reminder", TIER = "T2", PLUS1H = 1 ч, MINUS2H = 2 ч, MINUS30M = 30 мин, TEXT_BY_STEP: plus1h → B9.day_ladder_plus1h, minus2h → B9.day_ladder_minus2h, minus30m → B9.day_ladder_minus30m.
- step_times(first_mark_at, deadline) → [(plus1h, min(first+1 ч, deadline−2 ч)), (minus2h, deadline−2 ч), (minus30m, deadline−30 мин)] — в UTC. Дедлайн — функция day_clock (та, что даёт deadline_at в GET /day/current; имя по коду).
- decide_ladder(now, window_open, first_mark_at, deadline, done, keyed) → LadderPlan(send: step, late: tuple) | None:
  - None, если не window_open, нет first_mark_at, done;
  - due = шаги в порядке LADDER_STEPS с временем ≤ now и без ключа; due пуст → None;
  - send = последний из due по порядку шагов; late = остальные due;
  - время plus1h в step_times уже ограничено «−2 ч» (min): если first+1 ч ≥ deadline−2 ч, plus1h наступает вместе с minus2h и по правилу «send = последний» всегда уходит в late (В7 А).
- tick_ladder(engine, now) → NotifyResult(sent = pid с отправкой, late = записанных ключей без отправки, skipped):
  1. Кандидаты — одна транзакция, только чтение: тот же фильтр, что у tick_noon; окно дня open; батчем: «SELECT pid, day_started_at, min(at) FROM day_marks WHERE pid = ANY(…) GROUP BY pid, day_started_at» (сравнение day_started_at в UTC), ключи day_done и ladder трёх шагов; decide_ladder; не больше MAX_PER_TICK.
  2. Каждый pid — своя транзакция как в notify_one (lock_timeout, lock_participant, _STATE, _eligible, проектор догнал, данные и решение заново).
  3. Запись: ключи late (ON CONFLICT DO NOTHING, результат не важен); ключ send с RETURNING — 0 строк → rollback; outbox: aggregate_id = str(pid), event_type ladder_reminder, payload {"text_id": TEXT_BY_STEP[send], "payload_vars": {}, "tier": "T2"}. Один commit.
  4. INFO одной строкой «notify_ops: ladder sent=%s late=%s skipped=%s»; без pid, tz, payload.
- notify_ops.tick: порядок tasks_open → noon → ladder; правило в своём try/except, как в noon-1.

## 7. Тексты (day.json, version 0.5.0; notes у первого: «ladder-1: лестница DM 3.17, пишет notify_ladder (T2). Заглушки до 0-Б.»)
- B9.day_ladder_plus1h · soft · pre-legal-review · «[ЗАГЛУШКА] Вы отметили задания, но отчёт ещё не отправлен. Всё в порядке? Нажмите «Отправить отчёт».»
- B9.day_ladder_minus2h · neutral · pre-legal-review · «[ЗАГЛУШКА] До конца приёма отчёта около 2 часов. Не забудьте отправить отчёт.»
- B9.day_ladder_minus30m · neutral · pre-legal-review · «[ЗАГЛУШКА] До конца приёма отчёта 30 минут. Отправьте отчёт, чтобы день засчитался.»
- В text_registry после texts load — 39 ключей.

## 8. Задетые тесты
- apps/api/tests/test_day_current.py::test_kinds_and_ttl — добавить «"ladder": "3650 days",  # ladder-1».
- test_notify_noon.py по карточке noon-1 сравнивает NotifyTick по полям, версию day.json не сверяет — ШТАБ подтверждает после мержа noon-1. Иначе — внести сюда до промпта.
- Упал тест вне списка → не чинить, «тест X вне списка» в ИТОГ, стоп.

## 9. Новые тесты — apps/api/tests/test_notify_ladder.py
Без БД (MSK и VVO; день: активация 04:00, дедлайн 00:00):
1. step_times: отметка 15:00 → 16:00, 22:00, 23:30; отметка 21:30 → plus1h = 22:00 (ограничено «−2 ч»).
2. decide: 15:59 → None; 16:00 → send plus1h; 22:00 и plus1h с ключом → send minus2h; 22:00 без ключей (простой) → send minus2h, late (plus1h); 23:30 без ключей → send minus30m, late (plus1h, minus2h).
3. Отметка 21:30 → first+1 ч = 22:30, plus1h = 22:00 (min): в 21:45 → None; в 22:00 → send minus2h, late (plus1h).
4. done → None; окно закрыто (после дедлайна) → None; отметок нет → None.
5. key_ladder: формат, тот же момент в UTC — тот же ключ, неизвестный шаг → ValueError; TTL_BY_KIND["ladder"].
6. Импорт в обоих порядках: subprocess sys.executable -c «import app.notify_ladder, app.notify_ops» и обратный, cwd apps/api — код возврата 0.
7. Все три текста есть в day.json.
С БД (фикстуры — как test_notify_ops.py; отметки владельцем, at задаётся явно):
8. Через 1 ч после отметки → ladder.sent == 1, ключ plus1h, 1 outbox ladder_reminder (T2); второй tick → 0.
9. 23:30 после простоя → 1 outbox (minus30m) и 3 ключа.
10. Ключ day_done → 0. Пропуск: пауза, флаг, sleeping, не догнанное событие → 0, ни ключа, ни outbox.
11. tick: результат по полям (r.ladder.sent); падение одного правила не останавливает другие.

## 10. Не делать
- Не менять projector.py, life_ops.py, day_clock.py, routers/day.py, миграции, бота.
- Не писать participant_state и participant_events. Не делать алерт Автору «день 2».
- Не дублировать INSERT в outbox в notify_ladder.

## 11. Живая проверка
- А1 не трогать без указания ШТАБа.
- Ожидаемое состояние А2/А3 — по отчёту сервера до выката.
- А3: открытый день, одна отметка, отчёт не отправлять. Через 1 ч — доставка plus1h; 22:00 по ТЗ — minus2h; 23:30 — minus30m; dlq без новых. После дедлайна день закрывается как «пришёл»: lives не меняются, missed_streak 0, день выдан снова.
- Полуденного у А3 в этот день нет (есть отметка) — перекрёстная проверка noon-1.

## 12. Команды для Автора на IRONCLAD (через СЕРВЕРНЫЙ, после мержа, только main)
- Миграций нет. Сборка api/projector/migrate; build migrate до texts load; texts load (39 ключей); пересоздать projector.
- Лог projector: «notify_ops: ladder sent=… late=… skipped=…»; Traceback 0, WARNING 0.

## 13. Для ШТАБА
- Подтвердить после мержа noon-1 строку §8 про test_notify_noon.py.
- Алерт Автору «день 2 проблемы» (03 §3.17, yaml day_2_problem) — отдельная задача; нужен признак «пришёл, но не отправил» вчера.
- Строка STATE после выката: text_registry 39; notify_ops — НП3, НП1, лестница.
- Настоящие тексты лестницы (к 0-Б, юрист): 09 R257 — якорь «по Вашему времени» в ladder_texts; NR-224 — без нарастания угроз. Заглушки сейчас — не блокер.

## 14. РЕВЬЮЕР
Не нужен: нет initData, 18+, оплаты, прав БД.
