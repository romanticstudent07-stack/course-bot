# pause-2 — дочитка канона к pause-1 (PLAN §5 п.20)
Hash 560f1b8, ИССЛЕДОВАНИЕ, З1–З2, Правило К. Основа — docs/research/pause-1.md; здесь правки и дополнения. Ссылки — путь@560f1b8.
Автор 15.11: В1 = А (возврат жизни, выход из sleeping — в пачке); В3 = В (/pause_grant — Панель); В5 — рестарт по промокоду в пачке; А1–А3 — §8. ШТАБ (К-5): 0016 пропуск; 0018 паузы; 0019 журнал списаний.
Не проверено: хвост normative/I2-wave-b.md (обрыв в deferred_from_i2); 03 §3.6–3.7 в окне не читался.

## 1. Правки pause-1
- Б4: 0018_pauses (down_revision 0017_support_questions), 0019_life_writeoffs (down_revision 0018_pauses); 0016 нет [ШТАБ].
- Б6 неверен: I2 fsm — active → sleeping по any_of [user_pause, author_pause, pause_shadow, no_life, red_flag]. Запрет паузы — пары флагов [pause_user, block_lives], [pause_user, freeze_unpaid] (10-02 legality_matrix). «Спящий» в 02 П.12, 10-01 §1.4, 10-06 Р120 — неоплата (freeze_unpaid; по Р-1 не бывает), не фаза.
- Команда — /life +N | -N (build/bot-commands-registry.yaml lifecycle: owner, hard_confirm, work_group_reply).
- П.8 не устарело — возвращено Автором 15.11 (§8 А3).
- Нарезка pause-1 §4 заменена §6.

## 2. 02 → I2 → итог (I2 выше 02, 10, 17)
| 02 | I2 / 10 / 17 | Итог |
|---|---|---|
| П.1 кнопки бота; с завтра; до 7 дн. | user_pause.activation mini_app_or_bot, 7d, min_gap 24h, client_op_id | Mini App; с завтра; до 7 дн. |
| П.4 дней и напоминаний нет; жизни, таймеры стоят | active → sleeping; 10-02 pause_user freezes [timers, lives] | sleeping + флаг pause_user |
| П.6 «Продолжить», досрочно | by_participant: остаток в бюджет | + день по А1 |
| П.8 квота | 14 дн./год per cohort; (pid, days_budget_remaining_annual, cycle_start_at) | А3: пауза на Этап + 14 дн. за цикл |
| П.9 /pause_grant | grant_events; в реестре нет | Панель (В3) |
| П.11 тайная | pause_shadow (/set_shadow) | не строим; kind shadow в 0018 |
| П.12 | forbidden pairs | запрет при block_lives |
| — | author_pause без квоты (17-04: «обёртка pause_shadow») | kind author; команда — Панель |
| — | /unpause_user: остаток в бюджет, следующая через 24 ч | в правилах; команда — Панель |
П.2, П.3, П.5, П.7, П.10 — I2 молчит, действует 02.

## 3. Закрыто
- В2 = Mini App [канон: I2 user_pause.activation.channel]; бот — уведомления и кнопки Автора (П.2).
- В4 — Автор §8 А1 (канон молчал: 10-02 revive_by_author «с откатом позиции»).

## 4. Причина sleeping
Канон: I2 — sleeping по user_pause, author_pause, pause_shadow, no_life, red_flag; выход — pause_removed_and_lives_ok. 10-01/10-02 — причины = множество флагов. /block, /unblock — open_incompatibility (Р477), решать в п.18 (I2 author_pause против 10-06 ban_mod).
Вывод: sleeping_reason не нужен. Причина — participant_state.status_flags; фаза производная: sleeping, если есть флаг из {pause_user, author_pause, pause_shadow, block_lives, ban_mod, флаг Red Flags}, иначе active. /block и Red Flags добавят флаг без миграции. По коду (pause-1): sleeping по lives = 0, флаги не ставятся → T6a ставит block_lives и делает бэкфилл.

## 5. Механика
Перевыдача дня (А1) — одна функция reissue_day в T6a: позиция = цель; day_started_at = ближайшие 00:00 по поясу участника; до этого времени — ожидание: жизни и таймеры стоят, НП1 и лестница не шлются, списаний нет; кнопки с 04:00, дедлайн — 00:00 следующих суток. Вызывают: выход из sleeping по паузе (T2), revive (T7), restart_paid (T6c), /revert (Панель, позже). /life у участника в строю день не трогает (03 §3.6). Как ожидание выражается в часах (03 §3.6–3.7, day_clock) — не проверено, §9.
/life ±N (T6b): owner, ответом в рабочей группе, двухшаг; замок participant:pid; idempotency life_op:{pid}:{client_op_id}, TTL 1 ч. +N: lives = 0 → отказ, Автору в группе «используй revive», участнику ничего; lives + N > 3 → life_above_max. −N: ниже 0 → life_below_zero; ровно 0 → проектор ставит block_lives. Событие life_op {delta, reason}, actor owner.
revive_by_author (T7, после 0019): оболочка как у /life (owner, hard_confirm, двухшаг; позже Панель). Шаг 1 — Автор выбирает позицию (по умолчанию день 1 текущего модуля). Одна транзакция, замок participant:pid: есть block_lives; возврат = списания в 0019 после точки отката (02 §2.6); событие revive_by_author {target, lives_returned}. Проектор: lives = min(3, 1 + lives_returned); снять block_lives; missed_streak 0; reissue_day(target). Списания до 0019 → только +1. Лимиты пауз, прошлые Этапы, отчёты, рефлексии — не трогает.
Рестарт (T6c) [02 §2.4; 10-02 restart_paid; Р-1/Р-2]: участник — промокод в боте; Автор — [Выдать рестарт] / [Запретить] в админ-теме. Бот, одна транзакция, замок participant:pid: access_grants (purpose restart; requested → granted, UPDATE WHERE status = requested); participant_events restart_paid, actor owner, {grant_id}; outbox — сообщение участнику. Проектор: lives 3; снять block_lives; текущий Этап, модуль 1, день 1; счётчики 0; reissue_day; pause_budgets: остаток 14 (конфиг потока), cycle_start_at = 00:00 дня 1, restart_no + 1. Сохраняет прошлые Этапы, measurements_log, onboarding_form, consent_events, access_grants, прошлые day_marks и отчёты. Гейт Р-2 first-launch — только purpose access.

## 6. 0018, 0019 и нарезка
T1 db-pause-1 — КОДЕР, 0 кредитов, РЕВЬЮЕР да. 0018_pauses:
- participant_pauses: id, pid FK, kind, status, start_at, planned_end_at, ended_at, stage_no, restart_no, client_op_id UNIQUE, created_at. CHECK (У3): kind IS NOT NULL AND kind IN (user, author, shadow); status IS NOT NULL AND status IN (requested, approved, active, ended, cancelled, rejected); start_at IS NOT NULL AND planned_end_at IS NOT NULL AND planned_end_at > start_at; kind <> 'user' OR planned_end_at <= start_at + 7 дн.; kind <> 'user' OR status NOT IN ('active','ended') OR (stage_no IS NOT NULL AND restart_no IS NOT NULL); status <> 'ended' OR ended_at IS NOT NULL.
- Индексы: UNIQUE (pid) WHERE status = 'active'; UNIQUE (pid) WHERE kind = 'user' AND status IN ('requested','approved'); UNIQUE (pid, stage_no, restart_no) WHERE kind = 'user' AND status IN ('active','ended') — «пауза Этапа взята».
- Почему индекс, а не счётчик: в I2 бюджет — проекция событий с client_op_id; счётчик в pause_budgets пишет проектор, он может отстать — индекс по строке паузы защищает в самой БД (две вкладки). stage_no пишется при старте (пауза — Этапа, где началась); отменённая до старта в индекс не входит; досрочный выход = ended, пауза Этапа потрачена; restart_no открывает паузу того же Этапа без удаления истории.
- pause_budgets (I2 user_pause_quota): pid PK FK; days_budget_remaining_annual IS NOT NULL AND >= 0 (верх — конфиг потока); cycle_start_at IS NOT NULL; restart_no IS NOT NULL AND >= 0, DEFAULT 0. Пишет только проектор. Списание при старте на planned дней; досрочный выход возвращает planned_end − ended (округление — карточка T2). Годовщина: та же локальная дата через год, 00:00; 29.02 → 28.02; лениво — pause_rules при now ≥ годовщины считает 14, проектор переносит цикл на следующем событии паузы, крон не нужен.
- access_grants: purpose IS NOT NULL DEFAULT 'access' AND purpose IN ('access','restart'); pid NULL FK; UNIQUE — после §9.
- GRANT: app_bot — INSERT participant_events, SELECT participant_state, SELECT/INSERT idempotency_keys; app_api — SELECT/INSERT/UPDATE participant_pauses, SELECT pause_budgets; app_projector — SELECT/INSERT/UPDATE pause_budgets, SELECT participant_pauses; роль часов (approved → active, stage_no) — по коду. expected_tables.txt +2; downgrade — DROP, колонки, REVOKE.
T1b db-writeoffs-1 — КОДЕР, 0 кредитов, РЕВЬЮЕР да: 0019_life_writeoffs: id, pid FK, event_id UNIQUE, stage_no, module_no, day_no, created_at; CHECK каждый номер IS NOT NULL AND >= 1. Пишет проектор при списании (T6a). Задетые (кандидаты): expected_tables.txt; тесты прав 0009/0010, если сверяют список целиком.

| # | id | Суть | Файлы | Код + тесты | Задетые (кандидаты) | РЕВЬЮЕР | Кредиты |
|---|---|---|---|---|---|---|---|
| 1 | T6a api-sleep-1 | PROJECTOR_VERSION 5; фаза из флагов; block_lives + бэкфилл; reissue_day; life_op ±N; restart_paid; запись 0019 | app/projector.py, app/day_clock.py, app/life_ops.py, tests | 260 + 260 | test_projector*.py, test_projector_static.py, test_life_ops.py, test_day_clock*.py | нет | 840 |
| 2 | T6b bot-life-1 | /life ±N, отказ при 0 | apps/bot, tests | 180 + 180 | список команд бота | да | 440 |
| 3 | T7 bot-revive-1 | revive (после 0019) | apps/bot, app/life_ops.py, tests | 200 + 200 | test_life_ops.py, список команд | да | 560 |
| 4 | T6c bot-restart-1 | рестарт по промокоду | apps/bot, tests | 220 + 220 | тесты заявок Р-2, гейт first-launch | да | 600 |
| 5 | T2 api-pause-1 | события пауз, две проверки, бюджет, возврат дней, выход из sleeping | app/projector.py, app/pause_ops.py, app/pause_rules.py, tests | 420 + 340 | test_projector*.py, test_day_current.py::test_kinds_and_ttl | нет | 1 000 |
| 6 | T3 api-pause-2 | GET /pause, POST request/cancel/resume; статус на /day/current | app/routers/pause.py, main.py, app/routers/day.py, packages/shared, tests | 350 + 300 | тесты /day/current | нет | 810 |
| 7 | T4 bot-pause-1 | карточка заявки, П.4–П.5 | apps/bot, seed текстов | 250 + 200 | типы доставки outbox | нет | 530 |
| 8 | T5 miniapp-pause-1 | экран «Пауза», баннер, экран 0 жизней | PausePage.tsx, api-клиент, App.tsx, DayPage, tests | 300 + 200 | тесты DayPage, маршрутов App | нет | 660 |
Итого 5 440. Порядок: T1, T1b → 1 → 2 → 3 → 4. Стоп от 3 182: 1 (1 260) → 2 342; 2 (660) → 1 902; 3 (840) → 1 342; 4 (900) → 742; 5 (1 500) — стоп. Если 0019 не смержена — 4 раньше 3 (сумма та же). 5–8 — после 25.11 или пакетом КОДЕРА. Тесты grep-ом не искал — сверяет ШТАБ.

## 7. DEFECTS (кандидат, номер — ШТАБ)
02 §2.4 «блок доступа» против кода «фаза sleeping»: 10-01 §1.2–1.3, 10-02 — 4 фазы, 0 жизней = block_lives при active; I2 (выше) — no_life → sleeping. Код верен по I2, но block_lives не ставит. «Спящий» в 10-01 §1.4, 10-06 Р120, 02 П.12 — неоплата. Попутно: I2 life_ops 'life:'||pid против 'participant:'||pid; 02 §2.4 «день 1» против 10-02 Р60 «начало этапа» (Автор 15.11: день 1 модуля 1 текущего Этапа); реестр /pause_author hard_confirm true против I2 false. Правка DOCS: врезка в 10-01 и 10-06 о двух смыслах «спящий».

## 8. Решено Автором 15.11 (К-6: Автор; полный текст — docs-пакет ШТАБа: DECISIONS + файл решений)
- А1. Перевыданный день — с 00:00 по поясу участника (слово «полночь» не используем), кнопки с 04:00, дедлайн — 00:00 следующих суток. До 00:00 — не пропуск: жизни и таймеры стоят, НП1 и лестница не шлются. Для: выхода из sleeping, revive_by_author, /revert, рестарта. /life у участника в строю позицию и день не трогает (03 §3.6).
- Рестарт (Р-1/Р-2): день 1 модуля 1 текущего Этапа; 3 жизни; счётчики и позиция обнуляются; прошлые Этапы, данные доступа, замеры сохраняются; событие restart_paid не переименовывать.
- А2. Из block_lives два выхода (C3): рестарт или revive_by_author. revive — одна транзакция (Р-C3.3): жизнь + откат на позицию, выбранную Автором (обычно день 1 текущего модуля); lives = min(3, 1 + возврат по 02 §2.6), больше 3 не бывает. Команда бота в рабочей группе по образцу /life (owner, hard_confirm, двухшаг), позже Панель; после 0019; по списаниям до 0019 — только +1. revive и /revert не трогают лимиты пауз, прошлые Этапы, журналы отчётов и рефлексий. /life +N при 0 → отказ, подсказка Автору «используй revive», участнику ничего; /life −N до 0 → block_lives. /revert — 02 §2.6 без добавок, день по А1.
- А3. Паузы: одна на Этап, не дольше 7 дн.; поверх — не больше 14 дн. за годовой цикл; между паузами не меньше 24 ч. Цикл — с 00:00 первого дня задания по поясу (после рестарта — заново); бюджет снова 14 в годовщину, 00:00; 29.02 → 28.02. Запрос: остаток ≥ дней и пауза Этапа не взята, иначе отказ (текст — text_registry Б9, формулировка в карточке). Досрочный выход: дни назад в бюджет, пауза Этапа потрачена. Отменённая до старта (П.7) не считается. Пауза относится к Этапу, где началась. author_pause и тайная бюджет не тратят. Рестарт обнуляет оба лимита (C3 reset_pause_quota).
Вопросы Автору: нет.

## 9. Сверить по коду (ШТАБ)
- UNIQUE в access_grants: не помешает ли второй строке (restart).
- Ключи day_marks и отчётов: UNIQUE без даты — повтор дня после revive или рестарта упадёт.
- Тип и CHECK participant_state.status_flags (если CHECK по списку — расширить в 0018).
- Роль часов run_forever; кто переводит approved → active.
- Как бот отличает промокод доступа от рестарта.
- Где хранится дата 00:00 первого дня задания или из чего её вывести (конец онбординга + tz, первый day_started_at).
- Бэкфилл pause_budgets для идущих: cycle_start_at из этого источника, остаток 14, restart_no 0.
- day_started_at при перевыдаче (D-41 п.4): допускает ли day_clock будущее значение и ожидание без списаний; иначе отдельный флаг.
- Число участников с lifecycle_phase = sleeping (бэкфилл block_lives).
- Имя команды revive в реестре 34 команд (если нет — правка реестра в T7).

## 10. Прочитано (З1; в З2 новых файлов нет)
DESIGNER.md 22,0; PACK.md 11,8; STATE.md 18,6; AGENT-BRIEF.md 17,1; DECISIONS.md 7,5; CANON-CHECK.md 4,9; research/pause-1.md 15,5; normative/I2-wave-b.md 40,4 (без хвоста); 10/10-02 15,4; 10/10-06 39,4; 17/17-04 4,1. Сверх списка: build/bot-commands-registry.yaml 7,5 (/life, /block); 10/10-01 20,1 (п.5: фазы и флаги); apps/api/app/routers/me.py 10,9 (/me/card: lives, позиция; фазы и флагов нет).
