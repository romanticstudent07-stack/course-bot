# bot-i3-3: «Помощь» по Р-19 (PLAN §5 п.13), версия 2
ИССЛЕДОВАНИЕ 13.11.2026, заменяет файл #209. Новые факты — @9252d66, факты из #209 — @010bdc7. Правило К. Тексты — заглушки. Метки К-6: [канон §], [Р-19], [ШТАБ-тех].
Сокращения: P4 = docs/architecture/04-onboarding.md, P8 = 08-working-group.md, P9 = 09-communications.md, I4 = normative/I4-wave-d.md, RG = build/bot-commands-registry.yaml; OB = apps/bot/bot/outbox.py; MD = apps/api/app/db/models.py; RL = apps/api/app/rate_limit.py; NL = apps/api/app/notify_ladder.py; AM = apps/api/main.py; APX = apps/miniapp/src/components/App.tsx; OF, LS = там же OnboardingFlow.tsx, LaterSteps.tsx.

## 0. Что изменено против #209
- §1 и §9 оставлены, добавлены строки про Р-19. §8: правка 1 переписана под Р-19; правка normative «при В2 = А» снята (В2 = Б совпадает с I4 P494); добавлены правки 4–5.
- §2: вывод «путь (а) [ШТАБ-тех]» снят Р-19, путь — (б); добавлены факты @9252d66.
- §3, §5, §6, §7 переписаны; §4 обновлён; §10: В1 и В2 закрыты, добавлен В3.

## 1. Канон (К-2), из #209
- P4 §4.6: «На любом шаге онбординга — кнопка «Поддержка/Вопросы». При нажатии: Бот шлёт обращение в тему «Поддержка» Рабочей группы (с кликабельным именем + кнопкой «Карточка») + предлагает Участнику написать вопрос текстом (пересылается в ту же тему).» YAML: support_button: everywhere. Механику перекрывает Р-19; «на любом шаге» — В3.
- P8 §8.2: «Кнопки: Карточка / Написать.» §8.8: «Кнопка ✉️ … Автор пишет текст в группе → Бот доставляет Участнику от имени Бота»; whitelist; callback привязан к участнику.
- P9: R256 — нужна кнопка; HTML, html_escape, 4096 знаков; author_channel с {name} и @{username} противоречит Р-15.
- RG: /support (role any, private_chat). Р-19: /support в личке не делаем.
- I4 §2 P494: предпросмотр перед write_via_bot — совпадает с Р-19 (В2 = Б); P455: ✉️ стёртому участнику — тихий сброс. I4 §5: write_via_bot_flow «participant taps "написать"… participant confirms» противоречит P8 §8.8 (§9).
- Не прочитано: I4 §8 E2 (файл ≈ 57 КБ) — §10.

## 2. Код сейчас
Из #209 (@010bdc7): /start есть только в личке; /support и темы «Поддержка» нет. Роутер доступа ловит всю личку; текст от участника с доступом → NOTHING. texts.py: GROUP_WHO «Участник #{num} (ID {tg_id}) → {link}», GROUP_WRITE, CARD_BUTTON «📇 Карточка». В OF и LS кнопки поддержки нет.
Новое (@9252d66):
- OB: GROUP_ROUTES = {event_type: (поле BotConfig темы, доп. SQL)}: reflection_submitted → reflections_topic_id, ladder_day2_alert → reports_topic_id. Если event_type нет в GROUP_ROUTES → путь лички; без payload.text_id строка уходит в DLQ bad_payload. _deliver_group: pid → GROUP_ADDRESSEE (участник стёрт → MARK без поста) → expired 24 ч → WORK_GROUP_ID и тема (нет → group_not_configured) → payload {pid,…} → текст → card_button(short_no) → _send_group (HTML) → MARK. Ветвление «if extra_sql is REFLECTION … else DAY2»; в ветке REFLECTION — ленивый импорт «from bot.access import fmt_msk».
- Права app_bot (0009, 0011, по докстрингу OB): SELECT outbox, UPDATE sent_at, INSERT outbox_dlq, SELECT tg_user_registry (pid, tg_user_id, tombstoned_at, short_no), text_registry, reflections_log. TO_DLQ копирует payload целиком.
- NL: строку в outbox вставляет notify_ops._INSERT_OUTBOX {aggregate_id: str(pid), event_type, payload: json.dumps(…)} в одной транзакции с ключом. ladder_day2_alert: payload {"pid"}. Текст SQL лежит в notify_ops.py, его не открывал.
- MD: reflections_log — образец «текст в своей таблице, в outbox только id»: FK pid, CHECK длины 2…2000, у app_api INSERT/SELECT/USAGE seq, у app_bot SELECT, UPDATE и DELETE нет ни у кого. measurements_log — образец идемпотентности: UNIQUE (pid, client_op_id), ON CONFLICT DO NOTHING, client_op_id 1…64. Модели outbox в MD нет.
- AM: все /miniapp/v1/** идут через build_miniapp_v1_router (require_init_data → rate_limit); новый роутер добавляется в create_app.
- RL: окно 1 мин на tg_user_id, ключ rl:miniapp:{tg}:{минута}, RATE_LIMIT_PER_MINUTE (60 по STATE), 429 RATE_LIMITED + Retry-After, fail-open. Отдельного лимита на маршрут нет.
- APX: фазы checking / start-error / no-access / number / onboarding (OF, до pid) / later (LS) / app (HashRouter; маршруты — navigation/routes.tsx, не открыт; «*» → /day).
- LS: offer → form → checkup → rules → finished; черновик шага — drafts.ts (DraftStore, привязка к tg_user_id, TTL 24 ч; файл не открыт). OF: welcome, age-gate (18+), consent, done; pid создаётся только в POST first-launch.

## 3. Поток [Р-19; механика — ШТАБ-тех]
1. Кнопка «Помощь» — в фазах later (все шаги LS) и app; до pid — по В3. Подпись — константа в компоненте, без ключа text_registry.
2. SupportScreen: поле, «Отправить», «Назад». В фазе later экран открывается состоянием в APX поверх LS («Назад» возвращает на тот же шаг); в фазе app — маршрут /help в routes.tsx.
3. Черновик хранится на клиенте: DraftStore, свой ключ, привязка к tg_user_id, TTL 24 ч, очистка после 201. На сервере черновика нет, поэтому нет ни таблицы, ни прав, ни стирания. Сверить: если drafts.ts работает на sessionStorage, после закрытия черновик пропадёт.
4. api: POST /miniapp/v1/support/question {text}, X-Client-Op-Id. Порядок: initData → rate_limit → btrim ≥ 2 и ≤ 2000, иначе 422 SUPPORT_TEXT_INVALID → активный участник (нет → 404; reconsent → 409 RECONSENT_REQUIRED — сверить с onboarding_form.py) → одна транзакция под active_pid_locked: частота (п.6) → INSERT support_questions ON CONFLICT (pid, client_op_id) DO NOTHING RETURNING id → если вставлено, INSERT outbox → commit → 201 {status: "sent"}. Повтор с тем же id → 201 без новой строки.
5. outbox: event_type support_question; aggregate_id str(pid); payload {"pid": str(pid), "question_id": id}. Текста в payload нет, потому что DLQ копирует payload. Ключ идемпотентности — UNIQUE (pid, client_op_id); idempotency_keys и day_keys.TTL_BY_KIND не трогаем.
6. Частота: общих 60/мин мало, чтобы защитить тему от потока. В api — не чаще 1 вопроса в 30 с на pid (max(created_at) под замком), иначе 429 SUPPORT_TOO_FREQUENT + Retry-After. RL не меняем.
7. Пост: GROUP_ROUTES += support_question → (support_topic_id, SUPPORT_Q); SUPPORT_Q = «SELECT pid, body, created_at FROM support_questions WHERE id = %s». question_id — int > 0; чужой pid → bad_payload; строки нет → support_not_found. Текст: «[заглушка] Вопрос в поддержку», затем _group_who (GROUP_WHO), пустая строка, _esc(body). Кнопки в один ряд: card_button из bot/card.py (если есть short_no) и «✉️ Ответить» (sup:r:<id>). Как склеить с card_button — смотреть card.py.
8. ✉️ нажимают только ACCESS_ADMIN_IDS в WORK_GROUP_ID и SUPPORT_TOPIC_ID; остальным — answer() без текста и запись в лог. Бот отвечает reply на пост: «[заглушка] Ответ на вопрос N: напишите ответом» + ForceReply(selective).
9. На reply админа (текст ≤ 2000) бот отвечает reply с предпросмотром без parse_mode: «[заглушка] Предпросмотр (вопрос N):», пустая строка, текст; кнопки «Отправить» (sup:s:<N>) и «Отмена» (sup:x:<N>). Не текст → «[заглушка] Пришлите текстом».
10. «Отправить» (тот же фильтр): текст берётся из СВОЕГО предпросмотра после первой пустой строки; N → pid → tg_user_id; стёрт → не слать (P455). Участнику уходит без parse_mode, с префиксом «[заглушка] Ответ поддержки:». Предпросмотр меняется на «доставлено» или «не доставлено», кнопки снимаются, повторное нажатие ничего не шлёт. «Отмена» снимает кнопки.
11. Тема одна. Ветка — цепочка reply: пост → промпт ✉️ → ответ Автора → предпросмотр. Новый вопрос того же участника — новый пост; привязка к прежнему потребовала бы хранить message_id и дать UPDATE боту.
12. Состояния в памяти нет: N берётся из callback_data и текста своих сообщений бота. Логи — без tg_user_id, pid, short_no и текстов.
Вне пачки (Р-19, SHTAB-DEBTS §2): human_active, мьют 5/мин, /support_inbox.

## 4. Блокеры и сверки
- Б2 (из #209): «📇» обрабатывает card_handlers.py. Если фильтр пускает не из любой темы WORK_GROUP_ID — правка входит в bot-sup-1. Проверить в КАРТОЧКАХ.
- Б3 (из #209): config.py, app.py, texts.py могут меняться другими задачами — сверять по свежему main.
- Б4: старый бот отправит support_question путём лички → DLQ bad_payload. Порядок выката: migrate → бот → api → miniapp.
- Б1 из #209 (кнопка «Написать» в других темах) — вне пачки.

## 5. Нарезка
Кредиты ≈ строки × 0,8–1,0 + 60–100 за файл «Задетых».
| id | область | файлы (≈ строк) | режим, кредиты | РЕВЬЮЕР |
|---|---|---|---|---|
| db-sup-1 | api, БД | создать миграцию «00NN_support_questions, номер — ШТАБ» ~110, tests/test_db_roles_00NN.py ~220; изменить models.py +45, tests/expected_tables.txt +1 | Агент Р1, 360–480 | да: GRANT (B-3) |
| api-sup-1 | api, §3 п.4–6 | создать app/routers/support.py ~170, tests/test_support_db.py ~260; изменить main.py +3 | Агент Р1, 350–450 | нет: initData и RL не меняются |
| bot-sup-1 | bot, §3 п.7–12 и убрать ленивый импорт fmt_msk в _deliver_group | создать bot/support_handlers.py ~200, tests/test_support.py ~260; изменить outbox.py +45, config.py +15, app.py +5, texts.py +15, tests/test_outbox_group.py +60 | Агент Р1, 480–650 | нет |
| miniapp-sup-1 | Mini App, §3 п.1–3 | создать SupportScreen.tsx ~120, SupportScreen.test.ts ~80; изменить App.tsx +25, routes.tsx +5, api/client.ts +25, drafts.ts +30 | КОДЕР + Р1-П, 100–150 | нет; при В3 = А — да (OF, экран 18+) |
Порядок: db-sup-1 → api-sup-1 и bot-sup-1 параллельно (миграций нет, области разные) → miniapp-sup-1 после api (контракт). Карточек 4 при лимите 3 на окно — два окна КАРТОЧКИ: (db, api) и (bot, miniapp).
db-sup-1: support_questions — id bigint (seq), pid uuid NOT NULL → tg_user_registry (support_questions_pid_fkey), body text NOT NULL, client_op_id text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(). CHECK «body IS NOT NULL AND char_length(btrim(body)) >= 2 AND char_length(body) <= 2000» и «client_op_id IS NOT NULL AND char_length(client_op_id) BETWEEN 1 AND 64» (У3). UNIQUE (pid, client_op_id), индекс (pid, created_at). app_api: INSERT (pid, body, client_op_id), SELECT (id, pid, client_op_id, created_at), USAGE seq. app_bot: SELECT (id, pid, body, created_at). app_projector прав не получает; UPDATE, DELETE, TRUNCATE нет ни у кого. down_revision — последняя в main (0016 занят журналом списаний). Стирание при отзыве согласия делать по п.22 PLAN §5 — PLAN не прочитан, нужна выдержка ШТАБа. По коду: у reflections_log и measurements_log DELETE нет (MD); в STATE это записано в «Мелочах» как «erasure — FK без DELETE».

## 6. Чтение окна КАРТОЧКИ (КБ, лимит 170)
Общее: база 67,7 + этот файл ≈ 14 + DECISIONS 8,1 + CANON-CHECK 4,9 = 94,7.
- db-sup-1: + models 25,6, миграция 0015 4,5, 0011 5,8, test_db_roles_0015 14,8, expected_tables 1,0 = 146,4.
- api-sup-1: + main 6,0, onboarding_form.py 16,5, notify_ops.py 22,4, participant_lock 3,3, participants 4,8, errors 3,3, test_onboarding_form_db 9,9 = 160,9.
- bot-sup-1: + outbox 29,0, card 8,4, card_handlers 6,0, config 8,3, app 7,8, texts 7,8 = 162,0.
- miniapp-sup-1: + App.tsx ≈ 7,5, LS 12,6, OnboardingFlow.test.ts ≈ 21,0 = 135,8 + drafts.ts, routes.tsx, api/client.ts (размеры — ШТАБ).

## 7. Задетые тесты (черновик «Т»)
- db-sup-1: expected_tables.txt — полный список + support_questions (общий список). test_db_models.py: новая модель нужна, сам тест не правится. Не проверено (grep): сверяют ли test_db_roles_0009/0011/0013/0015.py полный набор прав app_bot или app_api без фильтра по таблице → если да, в список.
- api-sup-1: новый маршрут, ожидается «не задето». Не проверено: grep «/miniapp/v1/» в tests/test_api.py и test_rate_limit.py (перечень маршрутов целиком); проверяет ли тест packages/shared (контракт).
- bot-sup-1: grep в apps/bot/tests: «GROUP_ROUTES» (сверка ключей целиком); «fmt_msk» (после переноса импорта наверх monkeypatch bot.access.fmt_msk надо заменить на bot.outbox.fmt_msk); «missing_vars|caplog|BotConfig(» в test_bot.py, test_card.py, test_access.py. До переноса убедиться, что bot/access.py не импортирует bot.outbox (иначе цикл).
- miniapp-sup-1: grep «routes» в src/**/*.test.ts (сверка списка маршрутов). Ключи текстов не меняются.

## 8. Канон и решения
(а) P4 §4.6 + YAML support_button; P8 §8.2, 8.5, 8.8; P9 R256, author_channel, address_line_format; RG /support; I4 §2 P455, P494, §5; I4 §8 E2 (не прочитан).
(б) Против DECISIONS: механика P4 §4.6 — Р-19, «с кликабельным именем» — Р-15; I4 §8 E2 — Р-19; P9 «Имя (@username · ID 12345)» и address_line_format — Р-15; RG /support — Р-19. Р-16: полей анкеты в посте нет. I4 P494 совпадает с Р-19.
(в) Правки DOCS (P9 больше 20 КБ — Автор вставляет кусками):
1. architecture/04-onboarding.md · найди «При нажатии: Бот шлёт обращение в тему «Поддержка» Рабочей группы (с кликабельным именем + кнопкой «Карточка») + предлагает Участнику написать вопрос текстом (пересылается в ту же тему).» · замени на «При нажатии (Р-19): экран вопроса в Mini App (черновик хранится) → «Отправить» → пост в тему «Поддержка» Рабочей группы (подпись Р-15: «Участник #NNNNNN (ID N) → написать», имя и username не берём; кнопки «Карточка» и ✉️). Ответ Автора: ✉️ → предпросмотр → «Отправить» → Участнику от имени Бота. Тема одна, ветка — цепочка ответов.»
2. architecture/09-communications.md · найди «канонический формат обращения (8.5): Имя (@username · ID 12345) → [написать]» · замени на «канонический формат обращения (8.5, Р-15): Участник #NNNNNN (ID 12345) → [написать] (имя и username не берём)».
3. architecture/09-communications.md · найди «address_line_format: "<b>{name}</b> (@{username} · ID {tg_user_id}) → [написать]"» · замени на «address_line_format: "Участник #{short_no} (ID {tg_user_id}) → [написать]"  # Р-15».
4. architecture/normative/I4-wave-d.md — врезка в шапку, тело не переписывать: «Врезка AD-xx (Р-19, 13.11.2026): §8 E2 в части поддержки перекрыт docs/decisions/DECISIONS.md Р-19: кнопка «Помощь» в Mini App → экран вопроса → пост в тему «Поддержка»; ответ Автора: ✉️ → предпросмотр → «Отправить»; /support в личке нет.» Плюс OVERRIDES.yaml: id AD-xx (номер — ШТАБ), цель I4 §8 E2, основание Р-19. Формат записи — по соседним AD (не прочитан).
5. architecture/build/bot-commands-registry.yaml — у /support пометка «не делаем (Р-19)»; точный текст записи — дочитать RG.
Для ШТАБА: в Р-15 «В каноне устарело» дописать «09 author_channel»; в Р-19 «Устарело» дописать «RG /support»; при В3 = Б ещё «04 YAML support_button: everywhere».

## 9. Кандидаты DEFECTS (в DF не пишу)
- I4 §5 write_via_bot_flow (пишет участник) противоречит P8 §8.8 (пишет Автор).
- I4 topic_bindings (таблица, /bind_topic) противоречит коду: темы заданы env с bot-group-1.
- support_questions: при erasure DELETE нет, как у reflections_log (продолжение пункта STATE).

## 10. Вопросы Автору (К-4)
В1 и В2 закрыты: В1 снят Р-19, В2 = Б (SHTAB-DEBTS §2).
- В3 [г]. Где кнопка «Помощь». Канон: проверено P4 §4.6 «На любом шаге онбординга», YAML support_button: everywhere; Р-19 о шагах молчит; I4 §8 E2 не прочитан — задавать после дочитки, если E2 молчит. А — на всех шагах, включая шаги до pid (по канону): нужен вход по tg_user_id без pid в api, таблице и боте; вопрос может прийти до проверки 18+; +150–250 кредитов, РЕВЬЮЕР да. Б — только после pid (шаги LS и курс): всё работает по pid, но на шагах welcome, 18+ и согласий помощи нет. Мнение: Б (отход от канона → DECISIONS).
Надо дочитать: I4 §8 (57 КБ) — цитата E2 для врезки и для В3; PLAN §5 п.22 — стирание; drafts.ts — где хранится черновик; routes.tsx — маршрут /help; card.py — card_button; notify_ops.py — текст _INSERT_OUTBOX; day.py (43,8 КБ, кусок) — вставка reflection_submitted.

## 11. Прочитано (@9252d66)
- База: DESIGNER (v4.0, «Т», «Канон и решения»), PACK (метка есть), STATE (права app_*, RL 60/мин), AGENT-BRIEF (§6 устарел).
- research/bot-i3-3.md #209 13 — прежний §1–§11; DECISIONS 8,1 — Р-19; CANON-CHECK 4,9 — К-4, К-6.
- outbox.py 28,7 — GROUP_ROUTES, _deliver_group, ленивый fmt_msk; models.py 25,6 — образцы reflections_log и measurements_log; main.py 6,0 — общий роутер; App.tsx ≈ 6,8 — фазы (путь components/, src/App.tsx — 404).
- По необходимости: notify_ladder.py 15,7 — _INSERT_OUTBOX; rate_limit.py 6,7 — 60/мин, fail-open; OnboardingFlow.tsx 16,9 — шаги до pid.
- Сверх списка: LaterSteps.tsx 12,6 — шаги после pid и черновик (место кнопки).
