# Исследование iter2-rest — остатки Итерации 2
Окно ИССЛЕДОВАНИЕ, З1 + З2, 30.10.2026. Чтение по hash 49dd033. Правило К — docs/process/CANON-CHECK.md.
Решение Автора 30.10: остатки И2 (а–г) — до Итерации 3. Ответы Автора на В1–В3 и ШТАБа на Ш1–Ш5 — 30.10, §9.

## 1. Канон (К-2)
- DECISIONS@49dd033, НП: активность — только day_marks. Р-1: оплата вне Mini App (касается 13-P).
- 03 §3.12: рефлексия — обязательное поле отчёта дней 6, 13-M, 13-P; без поля «Отправить» нельзя; минимум 2 символа; смысл не оценивается; неизменяемый лог «как замеры»; при ревёрте поле снова обязательно, старый текст — в истории; все рефлексии — Автору в Рабочую группу, тема «Рефлексии».
- 03 §3.13: день 6 не гейтит. 13-M и 13-P — модерация Автора, вердикт на переходе дня 14; 13-P — ещё и оплата.
- 03 §3.14: авто-прохода нет; фазы A/B/C, тайная пауза (Блок 7.7).
- 03 §3.17: «день 2 проблемы → алерт Автору»; момент не задан.
- 02 §2.2: любое списание обнуляет все счётчики. 02 §2.3 и YAML lives.loss_conditions.reflection_day: пропуск дня 6 / 13-M / 13-P → −1 сразу, вне счётчика; частное правило главнее общего attended_not_sent (В2).
- 08 §8.2: темы «Рефлексии» и «Отчёты и активность» («пришёл, но не отправил», день 2). 08 §8.5: ссылка по числовому id.

## 2. Код как сейчас (@49dd033)
| Что | Факт | Файл |
|---|---|---|
| Отчёт | POST /day/report/submit: marks, вердикт, ключи day_done/day_report/day_queue, событие day_report_submitted; поля рефлексии нет | apps/api/app/routers/day.py |
| Вердикт | passed / not_passed / all_not_done; params_hash — только marks | apps/api/app/day_report.py |
| GET /day/current | признака «нужна рефлексия» нет | routers/day.py |
| Переход | passed → day_no + 1, только если день есть в контенте | routers/day.py, next_position |
| Контент | module_1: day_01, day_02 (5 блоков, ключи B9.day_m1_dNN_*) | apps/api/content/module_1/day_02.json |
| «Часы» | close_outcome(came, missed_streak, lives) без номера дня; _STATE без module_no → пропуск дня 6 = обычный пропуск | apps/api/app/life_ops.py |
| Запись «часов» | ключ day_close + life_op (missed_days) + day_closed; outbox не пишут | life_ops.py |
| Лестница | 3 шага, outbox ladder_reminder; алерт «день 2» — вне задачи | apps/api/app/notify_ladder.py |
| notify_ops | tick: tasks_open → noon → ladder; is_13p(module_no, day_no) | apps/api/app/notify_ops.py |
| Бот, outbox | только личка: aggregate_id = pid → tg_user_registry → tg_user_id; адресации группы и темы нет (ШТАБ, Ш2) | apps/bot/bot/outbox.py |
| Бот, доступ | app_bot: SELECT (pid, tg_user_id, tombstoned_at) на tg_user_registry (0009) (ШТАБ, Ш3) | миграция 0009 |
| БД | 16 таблиц, последняя миграция 0010_access_grants | STATE, AGENT-BRIEF §6 |
Не проверено (окнам КАРТОЧКИ): day_clock.close_outcome изнутри; применение life_op проектором; что бот делает с незнакомым event_type; имя env темы «Доступ» (apps/bot/bot/config.py); SELECT роли проектора на day_closed для лестницы; список тестов.

## 3. Решения по пунктам
(а) Рефлексия [Автор В1 А, В3 Б; канон 03 §3.12]:
- submit получает поле reflection. День рефлексии — день 6 любого модуля и день 13 (13-M/13-P). Если поля нет или после strip в нём меньше 2 символов → 422 REFLECTION_REQUIRED. Проверка идёт до вердикта, поэтому all_not_done тоже требует поле.
- Текст пишется в day_reflections: только INSERT, история ревёртов — новыми строками. Строка outbox reflection_submitted, payload {pid, reflection_id}.
- GET /day/current возвращает reflection_required. В Mini App — поле; «Отправить» неактивна, пока поле не заполнено.
- params_hash учитывает reflection только когда поле есть, чтобы старые хеши не менялись [ПРОЕКТИРОВЩИК-тех].
(б) Пропуск дня рефлексии [Автор В2; канон 02 §2.3; ШТАБ]:
- life_ops читает module_no и day_no и передаёт в close_outcome признак is_reflection_day.
- День рефлексии без ключа day_done к дедлайну → life_delta −1 сразу, streak 0, отметки (came) не важны.
- Отчёт сдан (в том числе all_not_done) → жизнь цела.
- Последняя жизнь → как сейчас при 0 (sleeping).
(в) «День 2 проблемы» [ШТАБ; канон 03 §3.17 момент не задаёт, 08 §8.2 — тема]:
- Где: в notify_ladder. Когда: наступил шаг plus1h; прошлый day_closed этого pid — «пришёл без отчёта», и его следующий день = текущий D; сейчас снова есть отметки без day_done.
- Что: одна строка outbox ladder_day2_alert, payload {pid}, ключ на день.
- Алерт пишется, даже если сам plus1h ушёл в late: правило В7 А касается только напоминаний участнику [ПРОЕКТИРОВЩИК-тех, уточнит карточка].
(г) Docstring projector «часы»: дописать НП1 и лестницу — в карточку clocks-1.
Доставка в группу [ШТАБ, Ш2–Ш3]:
- В боте — новая ветка: event_type → чат и тема из env по образцу темы «Доступ».
- tg_user_id для ссылки tg://user?id= бот берёт из tg_user_registry; текст ссылки (метка #NNNNNN) решит карточка.
- Текст рефлексии бот читает из day_reflections по reflection_id. Для этого в 0011 нужен GRANT SELECT для app_bot [ПРОЕКТИРОВЩИК-тех]. ПДн в payload не кладём.

## 4. 13-M / 13-P без Панели Автора [Автор В3 Б]
Делаем сейчас: поле, минимум 2 символа, лог, пост в тему «Рефлексии» без кнопок модерации, −1 сразу за пропуск (03 §3.12, 02 §2.3).
Позже: кнопки Одобрить/Вернуть и вердикт (08 §8.7); переход 13→14 по вердикту, фазы B/C, тайная пауза (03 §3.14); оплата 13-P (Р-1); /revert; сводка 09:00 (03 §3.15, Блок 7; ШТАБ, Ш5).
Условие: контент дня 13 не добавлять до модерации. Иначе passed на дне 13 уведёт участника на день 14, а это авто-проход, который запрещает 03 §3.14.

## 5. Тест дня 6 на IRONCLAD [ШТАБ, Ш1]
Заглушки дней 3–6 (content-1) и CI.
А1 проходит дни 3–6 за 4–5 суток: следующий день открывается в 04:00. Проверка пропуска дня 6 занимает ещё сутки.
Тексты курса до 0-Б — только заглушки (DESIGNER).

## 6. Нарезка (1 карточка — 1 область)
| № | id | Область | Что | Зависит | Кредиты |
|---|---|---|---|---|---|
| 1 | content-1 | API-контент | дни 3–6 и тексты-заглушки | — | 0 (Р0+) |
| 2 | db-1 | БД | 0011_day_reflections; GRANT: app_api INSERT/SELECT, app_bot SELECT; expected_tables 16 → 17; РЕВЬЮЕР да | — | 400–600 или 0 (Р0+) |
| 3 | bot-group-1 | бот | маршрут event_type → тема; посты «Рефлексии» и «Отчёты», ссылка tg://user | 2 | 500–700 |
| 4 | clocks-1 | API, «часы» | (б) + (в) + (г) | 3 | 650–850 |
| 5 | api-refl-1 | API | submit + current + лог + outbox | 2, 3 | 700–900 |
| 6 | miniapp-refl-1 | Mini App | поле, «Отправить» неактивна, 422 | 5 | 400–600 |
Порядок: 1 → 2 → 3 → 4 → 5 → 6.
Почему bot-group-1 раньше clocks-1 и api-refl-1: строки outbox для группы не должны появиться раньше маршрута. Сейчас бот шлёт по pid в личку, и алерт мог бы уйти участнику; что бот делает с незнакомым event_type, не проверено.
Миграция одна (0011). Ориентир по фактам: ladder-1 635, noon-1 550.

## 7. Задетые тесты (предварительно, правило «Т»)
Здесь не открывались. Поиск по репо — окну КАРТОЧКИ или ШТАБу:
- content-1: тесты загрузки контента и счёта текстов.
- db-1: tests/test_db_models.py, apps/api/tests/expected_tables.txt, тесты GRANT.
- bot-group-1: тесты apps/bot по outbox.
- clocks-1: tests/test_life_ops.py, tests/test_notify_ops.py, тесты лестницы, тест projector.
- api-refl-1: тесты submit и params_hash, tests/test_day_current.py (test_kinds_and_ttl при новом виде ключа).
- miniapp-refl-1: тесты экрана дня.

## 8. Чтение окон КАРТОЧКИ (лимит 170 КБ; размеры считает ШТАБ, Ш4)
База: DESIGNER, STATE, AGENT-BRIEF, README, DECISIONS, CANON-CHECK, этот файл.
- Окно К-1 (content-1, db-1): база + day_02.json, загрузчик контента и текстов, миграция 0010, apps/api/tests/expected_tables.txt, модели БД.
- Окно К-2 (bot-group-1, clocks-1): база + apps/bot/bot/outbox.py, apps/bot/bot/config.py, life_ops.py, day_clock.py, notify_ladder.py, notify_ops.py, projector.py.
- Окно К-3 (api-refl-1, miniapp-refl-1): база + routers/day.py, day_report.py, day_keys.py, экран дня Mini App.

## 9. Решения
- В1 = А [Автор 30.10, К-6]: отдельная таблица day_reflections, только INSERT/SELECT, миграция 0011, РЕВЬЮЕР.
- В2 = Б [Автор 30.10, К-6; канон 02 §2.3, YAML reflection_day]: на дне рефлексии отчёт не ушёл к дедлайну → −1 сразу, даже при отметках; missed_streak → 0. Отчёт сдан (в том числе all_not_done) → жизнь цела.
- В3 = Б [Автор 30.10, К-6]: общая механика 6/13-M/13-P сейчас; вердикт, фазы, тайная пауза и оплата — позже; контент дня 13 не добавлять до модерации.
- Ш1 [ШТАБ]: заглушки дней 3–6 + CI.
- Ш2 [ШТАБ, по коду]: бот адресует только личку; маршрут в темы — новая ветка (bot-group-1), env по образцу «Доступ».
- Ш3 [ШТАБ, по коду]: tg_user_id бот берёт из tg_user_registry (0009).
- Ш4 [ШТАБ]: размеры — в стартах окон КАРТОЧКИ.
- Ш5 [ШТАБ]: сводка 09:00 вне пачки; пост в тему «Рефлексии» при сдаче — в пачке.
- (в) [ШТАБ]: алерт «день 2» — в шаге plus1h лестницы, не на ночном закрытии.

## Прочитано (З1)
- docs/process/DESIGNER.md 22,1 — правило «Т», формат.
- docs/STATE.md 18,3 — 16 таблиц, 0010.
- AGENT-BRIEF.md 17,1 — §6, запреты.
- docs/process/README.md 8,9 — роли, миграции по одной.
- docs/decisions/DECISIONS.md 8,5 — НП: активность = day_marks.
- docs/process/CANON-CHECK.md 4,9 — К-4, К-6.
- docs/architecture/03-day-mechanics.md 26,3 — §3.12–3.17.
- docs/architecture/02-access-lives-pause.md 19,4 — §2.3.
- docs/architecture/08-working-group.md 11,8 — темы.
- apps/api/app/notify_ladder.py 11,3; apps/api/app/notify_ops.py 22,4.
- apps/api/app/routers/day.py 10,4; apps/api/app/day_report.py 2,7.
- apps/api/content/module_1/day_02.json 0,9.
- apps/api/app/life_ops.py 17,0 (по необходимости, пункт б).
В З2 новых файлов не читалось; факты о боте — от ШТАБа (Ш2, Ш3).
