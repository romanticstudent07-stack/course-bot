# pause-1 — исследование: паузы Р-6а и выход из sleeping (PLAN §5 п.20)
Hash main: 2ca16c9. Окно ИССЛЕДОВАНИЕ, З1. Правило К. Ссылки — путь@2ca16c9.
П.21 (Red Flags) не в пачке — только пересечения (§5).

## 1. Канон и решения (К-2)
- DECISIONS Р-6а: паузы 14 дн./год, одна не дольше 7 дн., между паузами не меньше 24 ч; не построены (D-28); устарело 02 П.8.
- R-2026-10-1 Р-6а: канон — патч И2 user_pause: annual_budget_default 14 (настраивается на поток), досрочный выход возвращает неиспользованные дни; три семантики user / author / shadow не трогать; таблица бюджета (pid, days_budget_remaining_annual, cycle_start_at); client_op_id обязателен; правила пауз в оферте — юристу.
- 02 (шапка): паузы и life-ops переопределены И2 (normative/I2-wave-b.md); тело блока — черновик.
- 02 П.1–П.12 (тело; где И2 перекрыл — не проверено): П.1 запрос кнопками бота, участник задаёт дату начала (с завтра или позже) и срок до 7 дн.; П.2 Автор одобряет одним тапом, молчание до даты начала = авто + алерт; П.3 старт в 00:00 по ТЗ, сегодняшний дедлайн всё равно горит; П.4 новых дней и напоминаний нет, жизни и таймеры заморожены, сообщения pause_active / pause_ending; П.5 предупреждение при 3–7 дн.; П.6 выход по «Продолжить», задания с ближайшего 00:00, можно раньше срока; П.7 отмена или перенос до 2 дн. с алертом; П.9 доп. пауза — /pause_grant; П.10 замораживает на несданном дне; П.11 тайная пауза квоту не тратит; П.12 паузу нельзя взять в неоплаченном состоянии (спящий, архив).
- 02 §2.4: 0 жизней — блок доступа, разблок — платный рестарт (день 1, 3 жизни). §2.5: Автор возвращает жизнь командой (Б17), атомарно, в границах 0…3.
- 10 (индекс): FSM из 6 состояний (И2); реактивация — шаг 6, 10/10-06 (не прочитан).

## 2. Как сейчас по коду
| Что | Факт | Где |
|---|---|---|
| Кто ставит sleeping | проектор по life_op: lives + delta = 0 → lifecycle_phase = sleeping | apps/api/app/projector.py@2ca16c9 _APPLY_LIFE_OP |
| Когда | life_ops.tick закрывает просроченный день (00:00 + 120 с): 2 молчания подряд или день 6 / 13 без отчёта → −1 жизнь | apps/api/app/life_ops.py@2ca16c9, day_clock.close_outcome |
| После sleeping | «часы» и лестница его не берут (фазы только onboarding / active); close_outcome при lives = 0 → ValueError | life_ops._CANDIDATES, notify_ladder._candidates |
| Как вернуть | никак: delta только −1 (LIFE_OP_DELTAS), reason только missed_days; выхода из sleeping нет ни у одного kind | projector.py@2ca16c9 |
| Флаги пауз | BLOCKING_FLAGS: pause_user, pause_shadow, author_pause, block_lives, ban_mod, freeze_unpaid; плюс author_pause_reason IS NULL — «часы» и лестница пропускают | life_ops.py@2ca16c9 |
| Кто ставит флаги | никто: проектор status_flags не меняет | projector.py@2ca16c9 |
| Что видит участник в sleeping | не проверено (day.py, me.py не в списке) | — |
| PROJECTOR_VERSION | 4 (AGENT-BRIEF §6 пишет 3 — устарело) | projector.py@2ca16c9 |
Вывод: при 0 жизней участник выпадает до ручного SQL. Решение Автора 13.11 (SHTAB-DEBTS §0, ручная сдача за А1) держится, пока нет T6.

## 3. Блокеры и ловушки
- Б1. Снять флаг паузы без сдвига дня — значит списать жизнь: day_started_at старый, первый tick видит is_overdue и закрывает день как silent. Событие конца паузы обязано ставить day_started_at = 00:00 выхода (П.6); позицию и missed_streak не трогать.
- Б2. Порядок в 00:00 начала паузы: сначала life_ops закрывает вчерашний день (П.3), потом пауза. Старт — только когда day_started_at не раньше начала паузы.
- Б3. Проектор времени не знает: старт и конец паузы по часам — новый шаг «часов» pause_ops в run_forever (как life_ops, notify_ops); он пишет события, проектор их применяет (E1).
- Б4. В main уже 0017_support_questions, значит номер 0016 занят. Следующий свободный — 0018 (down_revision 0017_support_questions). Журнал списаний (SHTAB-DEBTS §2, «0016») тоже нужно перенумеровать — решит ШТАБ. Каталог миграций не проверен.
- Б5. notify_ops (НП1 noon, НП3 tasks_open) — фильтр флагов не проверен. Лестница флаги учитывает (life_ops._CANDIDATES).
- Б6. П.12: паузу в sleeping не давать; пауза не выводит из sleeping.
- Б7. Возврат жизни при старом day_started_at — тот же эффект, что в Б1; нужен сдвиг дня (В4).

## 4. Нарезка (порядок: T1 → T2 → T3 → T4 → T5; T6a после T2, T6b после T6a)
| id | Область | Суть | Файлы | Строки код + тесты | Задетые тесты (правило «Т», сверить ШТАБу) | РЕВЬЮЕР | Кредиты |
|---|---|---|---|---|---|---|---|
| T1 db-pause-1 | db | 0018_pauses: participant_pauses (id, pid FK, kind user/author/shadow, status requested/approved/active/ended/cancelled/rejected, start_at, planned_end_at, ended_at, days_used, client_op_id UNIQUE, created_at; CHECK с IS NOT NULL по У3; user — не дольше 7 дн.); pause_budgets (pid PK, cycle_start_at, days_budget_remaining_annual IS NOT NULL AND 0…14); GRANT app_api, app_projector, app_bot (UPDATE status; INSERT participant_events — если В1 = А) | apps/api/migrations/versions/0018_pauses.py, apps/api/tests/expected_tables.txt, тест миграции | 140 + 160 | expected_tables.txt (+2 таблицы); тесты прав app_bot (0009), если сверяют полный список | да (GRANT, B-3) | ≈ 460 |
| T2 api-pause-1 | api + проектор | PROJECTOR_VERSION 5; kinds pause_started (+ флаг pause_user или author_pause по kind) и pause_ended (снять флаг, day_started_at = 00:00 выхода, Б1); app/pause_ops.py — tick: старт по Б2, конец по сроку или «Продолжить», пересчёт бюджета, авто-одобрение при молчании (П.2) | app/projector.py, app/pause_ops.py (новый), app/day_keys.py, tests | 380 + 300 | test_day_current.py::test_kinds_and_ttl (новый вид ключа); тесты проектора на PROJECTOR_VERSION и список kinds; test_projector_static.py | нет | ≈ 920 |
| T3 api-pause-2 | api | GET /miniapp/v1/pause; POST /pause/request (X-Client-Op-Id; правила Р-6а; П.3 — не раньше завтра; П.12); POST /pause/cancel; POST /pause/resume; outbox pause_requested; /day/current — статус «на паузе» | app/routers/pause.py, main.py (build_miniapp_v1_router), app/pause_rules.py, app/routers/day.py, packages/shared (OpenAPI), tests | 350 + 300 | тесты /day/current (новый статус); список kinds idempotency | нет | ≈ 810 |
| T4 bot-pause-1 | bot | карточка запроса в админ-тему с ✅ / ✖ (П.2); callback меняет status; участнику pause_active, pause_ending, предупреждение П.5 (тексты — заглушки) | apps/bot (обработчики, доставка outbox), seed текстов | 250 + 200 | тест списка event_type доставки, если сверяет целиком | нет | ≈ 530 |
| T5 miniapp-pause-1 | miniapp | экран «Пауза»: остаток бюджета, дата начала и срок 1–7, предупреждение, отмена, «Продолжить»; баннер на /day | PausePage.tsx (новый), api-клиент, apps/miniapp/src/components/App.tsx, DayPage, tests | 300 + 200 | тесты DayPage и маршрутов App | нет | ≈ 660 |
| T6a sleep-1 | api + проектор | life_op delta +1, reason author_return: из sleeping 0 → 1 жизнь, фаза active, сдвиг дня (Б7, В4) | app/projector.py, tests | 120 + 150 | тесты проектора «delta ≠ −1 → bad payload»; test_life_ops (сверка LIFE_OP_REASON) | нет | ≈ 430 |
| T6b sleep-2 | bot | команда Автора «вернуть жизнь» (имя — из реестра Б17, не проверено) → событие под замком participant:pid | apps/bot, tests | 150 + 150 | не ожидается | да (права БД) | ≈ 380 |
Итого ≈ 4 190 кредитов (≈ 1 кредит на строку + 60–100 за каждый задетый тест-файл). Тесты репо grep-ом не искал — список кандидатов сверяет ШТАБ (правило «Т», п.5).

## 5. Пересечения — что решить сейчас
- Панель (п.16–18): кто пишет события от имени Автора — бот напрямую (app_bot INSERT participant_events) или API-вход для бота. Нужен один путь для всех команд Панели; решить до T1 (GRANT в 0018).
- /block, /unblock через sleeping (п.18): нужна причина sleeping (lives / block / red_flag), иначе возврат жизни «разбудит» заблокированного. Варианты: reason в payload и колонка sleeping_reason в той же 0018 или флаг ban_mod (уже в BLOCKING_FLAGS).
- Red Flags (п.21): author_pause — kind author в participant_pauses, флаг author_pause уже в BLOCKING_FLAGS; CHECK kind заложить в T1 сразу. «60 с в sleeping» — тот же переход, что у /block: одно общее событие.
- Тайная пауза (П.11) — kind shadow, бюджет не тратит; сейчас не строить.
- Журнал списаний (VIEW): включать ли возврат жизни; номер миграции — после 0018.

## 6. Вопросы Автору
- В1. Возврат жизни Автором — в pause-1 (T6a + T6b) или в Панель (п.16–18)? Канон: проверено 02 §2.4–2.5 — возврат есть (Б17), очередь не задана; по коду выхода из sleeping нет. А — pause-1: плюс — снимает ручную сдачу за А1 (§0); минус — GRANT app_bot решать сейчас. Б — Панель: плюс — единый дизайн команд; минус — ручная сдача за А1 дольше. Мнение: А.
- В2 (задать, если I2 и miniapp-screens не ответят). Где участник просит паузу? Канон: проверено 02 П.1 — «кнопки Бота»; I2 user_pause не проверено. А — Mini App (initData и client_op_id уже есть), бот только уведомляет; против канона — запись в DECISIONS (К-7). Б — бот (как П.1): плюс — по канону; минус — новый диалог бота. В — оба: дороже. Мнение: А.
- В3. /pause_grant (02 П.9) при годовом бюджете? Канон: проверено 02 П.8–П.9 и Р-6а — противоречит: «выдать 2-ю/3-ю паузу» против «14 дн./год». А — команда добавляет дни в бюджет; Б — убрать; В — отложить в Панель. Мнение: В.
- В4. С какого момента идёт день после возврата из sleeping? Канон: проверено 02 §2.5 — молчит; 10/10-06 не проверено. А — с ближайшего 00:00, тот же застрявший день (как П.6); Б — сразу, с последнего 00:00. Мнение: А.
- В5. Платный рестарт при 0 жизней (02 §2.4; оплата вне продукта, Р-1) — в pause-1? Канон: проверено 02 §2.4 — рестарт с дня 1; деньги (К-4 в). А — нет, позже в Панель; Б — да. Мнение: А.

## 7. Надо дочитать до КАРТОЧЕК (решает ШТАБ)
normative/I2-wave-b.md (user_pause, fsm); 10/10-02 и 10/10-06; 17/17-04 и 17/17-07; build/bot-commands-registry.yaml (/pause_grant, возврат жизни, /block); apps/api/app/routers/day.py и me.py (экран sleeping); apps/api/app/notify_ops.py (Б5); каталог apps/api/migrations/versions (Б4).

## 8. Прочитано
- docs/process/DESIGNER.md 22,0 — формат файла исследования и правило «Т».
- docs/process/PACK.md 11,8 — метка конца есть.
- docs/STATE.md 18,6 — паузы не построены; STATE отстаёт с 04.11.
- AGENT-BRIEF.md 17,1 — паузы без карточки не делать; §6 устарел.
- docs/decisions/DECISIONS.md 7,5 — Р-6а.
- docs/process/CANON-CHECK.md 4,9 — К-2, К-4.
- docs/decisions/R-2026-10-1.md 23,6 — Р-6а: канон — И2 user_pause, таблица бюджета.
- docs/architecture/02-access-lives-pause.md 19,4 — П.1–П.12, §2.4–2.5; шапка — И2.
- docs/architecture/10-lifecycle-return.md 8,2 — только индекс; реактивация в 10/10-06.
- apps/api/app/life_ops.py 17,7 — BLOCKING_FLAGS, фазы onboarding / active.
- apps/api/app/projector.py 35,8 — sleeping по life_op, выхода нет, версия 4.
- apps/api/app/day_clock.py 11,2 — lives = 0 → ValueError; дни рефлексии 6, 13.
- docs/process/SHTAB-DEBTS.md 9,1 — сверх списка: §0 и §2 (А1, журнал 0016).
- docs/architecture/17-author-panel.md 6,2 — сверх списка: индекс, пауз-семантика в 17/17-04.
- apps/api/app/notify_ladder.py 15,7 — сверх списка: лестница учитывает флаги пауз.
