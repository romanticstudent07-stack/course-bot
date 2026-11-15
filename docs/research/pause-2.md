# pause-2 — дочитка канона к pause-1 (PLAN §5 п.20)
Hash 560f1b8, ИССЛЕДОВАНИЕ, З1, Правило К. Ссылки — путь@560f1b8. Основа — docs/research/pause-1.md; здесь только правки и дополнения.
Автор 15.11: В1 = А (возврат жизни и выход из sleeping — в пачке); В3 = В (/pause_grant — Панель); В5 — рестарт по промокоду при 0 жизней — в пачке. ШТАБ (К-5): 0016 пропуск; 0018 паузы (down_revision 0017_support_questions); 0019 журнал списаний.
Не проверено: хвост normative/I2-wave-b.md (обрыв в deferred_from_i2; ci_checks_i2, audit_additions_i2, risk_registry_additions_i2).

## 1. Правки pause-1
- Б4: 0018_pauses, down_revision 0017_support_questions; журнал списаний — 0019; 0016 не используется [ШТАБ-тех].
- Б6 неверен. I2 fsm: active → sleeping по any_of[user_pause, author_pause, pause_shadow, no_life, red_flag] — пауза сама ведёт в sleeping. Запрет паузы — по флагам: пары [pause_user, block_lives] и [pause_user, freeze_unpaid] (10-02 legality_matrix). «Спящий» в 02 П.12, 10-01 §1.4, 10-06 Р120 — неоплата (freeze_unpaid), а не фаза sleeping; по Р-1 freeze_unpaid не бывает.
- Команда возврата жизни: /life +N | -N (build/bot-commands-registry.yaml lifecycle: owner, hard_confirm, work_group_reply).
- Нарезка pause-1 §4 заменена §6.

## 2. 02 → I2 → итог (I2 выше 02, 10, 17)
| 02 | I2 / 10 / 17 | Итог |
|---|---|---|
| П.1 кнопки бота; старт с завтра; до 7 дн. | user_pause.activation: mini_app_or_bot, 7d, min_gap 24h, client_op_id | Mini App (§3); старт с завтра; до 7 дн. |
| П.4 нет дней, напоминаний; жизни, таймеры заморожены | active → sleeping; 10-02 pause_user freezes [timers, lives] | sleeping + флаг pause_user |
| П.6 «Продолжить», с ближайшего 00:00, досрочно | by_participant: refunds remainder to budget | как 02 + остаток в бюджет |
| П.8 квота | 14 дн./год per cohort; user_pause_quota (pid, days_budget_remaining_annual, cycle_start_at) | Р-6а = I2 |
| П.9 /pause_grant | grant_events [onboarding_bonus, refund_partial_makeup]; в реестре 34 команд нет | Панель (В3) |
| П.11 тайная пауза | pause_shadow: /set_shadow, reason_code из списка, невидима | не строим; kind shadow в 0018 |
| П.12 не в неоплаченном | 10-02 forbidden pairs | запрет при block_lives |
| нет | author_pause: /pause_author, без квоты; 17-04 «обёртка pause_shadow» | отдельный kind author (I2 выше 17-04); команда — Панель |
| нет | /unpause_user: остаток в бюджет, следующая пауза не раньше T + 24 ч | в pause_rules; команда — Панель |
П.2 (одобрение тапом, молчание = авто + алерт), П.3, П.5, П.7, П.10 — I2 молчит, действует 02; стадии заявки — в Б2 (10-01 §1.3).

## 3. Закрыто каноном
- В2 = Mini App [канон I2 user_pause.activation.channel]. Один канал из «mini_app_or_bot» канону не противоречит, запись в DECISIONS не нужна. Бот — уведомления и кнопки Автора (П.2).
- В4 частично: 10-02 block_lives.exit revive_by_author «с откатом позиции» (предохранитель от потери жизни на застрявшем дне), b10_reaction [remove_modifier, set_active, refresh_screen_and_start]. Время старта и цель отката — молчит → А1, А2.

## 4. Причина sleeping
Канон: I2 — sleeping по user_pause, author_pause, pause_shadow, no_life, red_flag; выход — pause_removed_and_lives_ok. 10-01/10-02 — причины = множество флагов, не одно поле. Hard-block: I2 — sleeping + author_pause; 10-06 — ban_mod (снапшот, окно 7 дн.); реестр /block, /unblock — open_incompatibility (Р477), решать в п.18.
Вывод: колонки sleeping_reason нет. Причина — флаги participant_state.status_flags; фазу считает проектор: sleeping, если есть флаг из {pause_user, author_pause, pause_shadow, block_lives, ban_mod, флаг Red Flags} или lives = 0, иначе active. Возврат жизни снимает только block_lives и не будит участника на паузе или в блоке; /block и Red Flags добавят флаг без миграции.
По коду (pause-1): sleeping ставится по lives = 0, status_flags проектор не меняет → T6a ставит block_lives при 0 и делает бэкфилл. Тип и CHECK status_flags не проверены; если CHECK по списку есть — расширить в 0018.

## 5. Возврат жизни и рестарт
/life +N (T6b) [реестр + I2 life_ops]: Автор, ответом в рабочей группе, только owner, двухшаг кнопкой. Замок participant:pid (в I2 life_ops — 'life:'||pid, расхождение внутри I2). Проверки: участник активен; lives + N не больше 3, иначе life_above_max. idempotency_keys: life_op:{pid}:{client_op_id}, TTL 1 ч. Событие life_op {delta: +N, reason: author_return}, actor owner. Команда −N — в Панель [ШТАБ].
Проектор: из 0 — снять block_lives, missed_streak = 0 (иначе следующее молчание снова спишет жизнь), фаза по §4, day_started_at по А1, позиция по А2.
Рестарт по промокоду (T6c). Канон: 02 §2.4 — день 1, 3 жизни; 10-02 restart_paid — одна транзакция: снять block_lives, прогресс на начало текущего этапа (Р60), lives 3, журнал замеров сохранить, квоту паузы сбросить, событие отдельное (Р59). Р-1 — денег нет; Р-2 — промокод → админ-тема → кнопки.
Кто жмёт: участник вводит промокод в боте; Автор — [Выдать рестарт] или [Запретить] в админ-теме.
Пишет бот, одна транзакция, замок participant:pid: access_grants (purpose restart, pid; requested → granted через UPDATE WHERE status = requested); participant_events restart_granted, actor owner, payload {grant_id}; outbox — сообщение участнику (заглушка).
Проектор по restart_granted: lives 3; снять block_lives; позиция — текущий этап, модуль 1, день 1; missed_streak 0; day_started_at по А1; бюджет пауз — полный. Не трогает measurements_log, onboarding_form, consent_events, прошлые day_marks и отчёты. Гейт Р-2 (first-launch) — только purpose access.
Сверить ШТАБу по коду: UNIQUE в access_grants (не даст вторую строку); ключи day_marks и отчётов (UNIQUE без даты — повтор дня 1 упадёт); как бот распознаёт промокод.

## 6. 0018 и нарезка
T1 db-pause-1 — КОДЕР, 0 кредитов, РЕВЬЮЕР да (B-3). 0018_pauses, down_revision 0017_support_questions:
- participant_pauses: id, pid FK, kind, status, start_at, planned_end_at, ended_at NULL, client_op_id UNIQUE, created_at. CHECK (У3): kind IS NOT NULL AND kind IN (user, author, shadow); status IS NOT NULL AND status IN (requested, approved, active, ended, cancelled, rejected); start_at IS NOT NULL AND planned_end_at IS NOT NULL AND planned_end_at > start_at; kind <> user OR planned_end_at <= start_at + 7 дн. Частичный UNIQUE (pid) WHERE status = active.
- pause_budgets: pid PK FK; cycle_start_at NOT NULL; days_budget_remaining_annual IS NOT NULL AND >= 0 (верх — конфиг потока). Пишет только проектор.
- access_grants: purpose NOT NULL DEFAULT access, CHECK IN (access, restart); pid NULL FK; UNIQUE — после сверки.
- GRANT: app_bot — INSERT participant_events, SELECT participant_state, SELECT и INSERT idempotency_keys, UPDATE (status) participant_pauses; app_api — SELECT, INSERT, UPDATE participant_pauses, SELECT pause_budgets; app_projector — SELECT, INSERT, UPDATE pause_budgets, SELECT participant_pauses. Роль «часов» — по коду run_forever (не проверено). Узкая альтернатива для app_bot — функция SECURITY DEFINER только для life_op и restart_granted (ШТАБ с РЕВЬЮЕРОМ).
- expected_tables.txt +2; downgrade: DROP, снять колонки, REVOKE.
Задетые (кандидаты): expected_tables.txt; тесты прав app_bot (0009) и access_grants (0010), если сверяют список целиком.

| # | id | Суть | Файлы | Код + тесты | Задетые (кандидаты) | РЕВЬЮЕР | Кредиты |
|---|---|---|---|---|---|---|---|
| 1 | T6a api-sleep-1 | PROJECTOR_VERSION 5; фаза из флагов; block_lives + бэкфилл; life_op +N; restart_granted | app/projector.py, app/life_ops.py, tests | 200 + 220 | test_projector*.py, test_projector_static.py, test_life_ops.py | нет | 660 |
| 2 | T6b bot-life-1 | /life +N | apps/bot, tests | 180 + 180 | список команд бота, если сверяется целиком | да (owner, права БД) | 440 |
| 3 | T6c bot-restart-1 | рестарт по промокоду | apps/bot (access), tests | 220 + 220 | тесты заявок Р-2; гейт first-launch | да | 600 |
| 4 | T2 api-pause-1 | события пауз, pause_ops, бюджет | app/projector.py, app/pause_ops.py, tests | 380 + 300 | test_projector*.py, test_projector_static.py, test_day_current.py::test_kinds_and_ttl | нет | 920 |
| 5 | T3 api-pause-2 | GET /pause, POST request, cancel, resume; статус на /day/current | app/routers/pause.py, main.py, app/pause_rules.py, app/routers/day.py, packages/shared, tests | 350 + 300 | тесты /day/current, kinds idempotency | нет | 810 |
| 6 | T4 bot-pause-1 | карточка заявки, П.4–П.5 | apps/bot, seed текстов | 250 + 200 | типы доставки outbox | нет | 530 |
| 7 | T5 miniapp-pause-1 | экран «Пауза», баннер, экран 0 жизней | PausePage.tsx, api-клиент, App.tsx, DayPage, tests | 300 + 200 | тесты DayPage, маршрутов App | нет | 660 |
Итого 4 620. Стоп (остаток не меньше 1,5 × оценки) от 3 182: 1 (нужно 990) → 2 522; 2 (660) → 2 082; 3 (900) → 1 482; 4 (1 380) → 562; 5 (1 215) — стоп. 5–7 — после 25.11 или пакетом КОДЕРА. Порядок: T1 → 1 → 2 → 3 → 4. Тесты grep-ом не искал — сверяет ШТАБ.

## 7. DEFECTS (кандидат, номер — ШТАБ)
02 §2.4 «блок доступа» против кода «фаза sleeping». 10-01 §1.2–1.3, 10-02: фаз 4, 0 жизней — модификатор block_lives при active. I2 (выше): 6 фаз, no_life → sleeping. Код верен по I2, но block_lives не ставит. «Спящий» в 10-01 §1.4, 10-06 Р120, 02 П.12 — неоплата; в I2 и коде — фаза. Попутно: I2 'life:'||pid против 'participant:'||pid; 02 §2.4 «день 1» против 10-02 Р60 «начало этапа» (на Этапе 1 совпадает); реестр /pause_author hard_confirm true против I2 false. Правка DOCS: врезка в 10-01 и 10-06 о двух смыслах «спящий».

## 8. Вопросы Автору
- А1. С какого момента идёт день после возврата жизни и после рестарта? Канон: проверено 02 §2.4–2.5, 10-02 revive_by_author и restart_paid, 10-06 Р120 — молчит; аналог 02 П.6 — с ближайшего 00:00. А — с ближайшего 00:00 по ТЗ, задания в 04:00, как после онбординга; Б — сразу, день уже идёт, жизнь легко потерять снова. Мнение: А.
- А2. Куда «откат позиции» при возврате жизни? Канон: проверено 10-02 revive_by_author — «с откатом позиции», куда — молчит. А — тот же застрявший день заново; Б — начало модуля. Мнение: А.
- А3. Что такое «год» в бюджете 14 дней? Канон: проверено I2 user_pause.quota (cycle_start_at без правила), Р-6а — молчит. А — 365 дней от конца онбординга, затем снова 14; Б — календарный год. Мнение: А.

## 9. Прочитано
- docs/process/DESIGNER.md 22,0 — формат исследования, правило «Т».
- docs/process/PACK.md 11,8 — метка конца есть.
- docs/STATE.md 18,6 — паузы не построены.
- AGENT-BRIEF.md 17,1 — паузы без карточки не делать.
- docs/decisions/DECISIONS.md 7,5 — Р-1, Р-2, Р-6а.
- docs/process/CANON-CHECK.md 4,9 — К-4, К-6.
- docs/research/pause-1.md 15,5 — основа.
- docs/architecture/normative/I2-wave-b.md 40,4 — fsm, user_pause, life_ops; конец не получен.
- docs/architecture/10/10-02-transition-matrix.md 15,4 — block_lives, restart_paid, пары.
- docs/architecture/10/10-06-reactivation-return.md 39,4 — «спящий» = неоплата; бан — снапшот.
- docs/architecture/17/17-04-pause-verdict-refund.md 4,1 — /pause_author «обёртка shadow».
- docs/architecture/build/bot-commands-registry.yaml 7,5 — сверх списка: /life, /block.
- docs/architecture/10/10-01-state-catalogue.md 20,1 — сверх списка, п.5: 4 фазы + флаги.
- apps/api/app/routers/me.py 10,9 — сверх списка: /me/card отдаёт lives, фазу и флаги — нет.
