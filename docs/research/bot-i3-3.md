# bot-i3-3: «Поддержка» (PLAN §5 п.13), З1
ИССЛЕДОВАНИЕ, 13.11.2026, @010bdc7 — все пути по этому hash. Правило К. Тексты — заглушки. Аккаунты — А1–А4.
Сокращения: P4 = docs/architecture/04-onboarding.md, P8 = 08-working-group.md, P9 = 09-communications.md, I4 = normative/I4-wave-d.md, RG = build/bot-commands-registry.yaml; CF, APP, TX, H, AH, AC = apps/bot/bot/config.py, app.py, texts.py, handlers.py, access_handlers.py, access.py; OF, LS = apps/miniapp/src/components/OnboardingFlow.tsx, LaterSteps.tsx. Метки К-6: [канон §], [ШТАБ-тех], [Автор].

## 1. Канон (К-2)
- P4 §4.6: «На любом шаге онбординга — кнопка «Поддержка/Вопросы». При нажатии: Бот шлёт обращение в тему «Поддержка» Рабочей группы (с кликабельным именем + кнопкой «Карточка») + предлагает Участнику написать вопрос текстом (пересылается в ту же тему).» YAML: support_button: everywhere.
- P8 §8.2: «Поддержка — обращения участников + кнопка поддержки из онбординга. Кнопки: Карточка / Написать.» §8.8: «Кнопка ✉️ под релевантными сообщениями: Автор пишет текст в группе → Бот доставляет Участнику от имени Бота». Fail-safe: whitelist; callback привязан к участнику.
- P9: R256 — команда не единственный путь участника, нужна кнопка; HTML, html_escape подстановок, 4096 знаков; author_channel с {name} и @{username} — против Р-15 (§8).
- RG: /support — role any, private_chat, audit base.
- I4 §2 P494: санитайзер и предпросмотр перед отправкой write_via_bot; P455: ✉️ участнику erased — тихий сброс. I4 §5: topic_bindings (alias support необязателен); write_via_bot_flow: «participant taps "написать"… participant confirms» — против P8 §8.8 (§9).
- НЕ прочитано: I4 §8 «Онбординг — финализация E2 и E3» (шапка P4: контур поддержки — И4 E2/E3). Файл 57 КБ, обрезан после §7. Дочитать до карточек; §3 верен, если §8 ему не противоречит.

## 2. Код сейчас
- H: только /start в личке; CommandStart() ловит и /start с аргументом. /support и темы «Поддержка» нет.
- APP build_dispatcher: start → card → access. Докстринг: роутер доступа ловит ВСЕ личные сообщения — новые обработчики лички ставить ДО него.
- AH on_private: текст от granted → исход NOTHING → бот молчит; текст участника с доступом сейчас никуда не идёт. command_precheck: в теме форума reply на первое сообщение темы = «reply нет».
- TX: GROUP_WHO = «Участник #{num} (ID {tg_id}) → {link}», {num} — 6 цифр или «—»; GROUP_WRITE; CARD_BUTTON = «📇 Карточка». Подпись Р-15 готова.
- app_bot читает tg_user_registry (pid, tg_user_id, tombstoned_at, short_no) — bot-i3.md §2@23bc377. Миграция не нужна.
- OF: welcome, age-gate, consent, done, underage, error (до pid). LS: offer, form, checkup, rules, finished. Кнопки поддержки нет нигде. Mini App говорит только с api.
- Mini App → бот: (а) Telegram.WebApp.openTelegramLink на t.me/<бот>?start=support — нужен username бота в сборке; api и outbox не нужны; (б) api → outbox → бот — нужен outbox.py (блок); (в) WebApp.sendData — только Mini App с клавиатурной кнопки, у нас Menu Button. Выбор (а) [ШТАБ-тех].
- Минусы (а): Mini App сворачивается; до pid ввод OF (дата, галочки) теряется, шаг LS хранит черновик. Шлёт ли клиент «/start support» в открытом чате без «Начать» — не проверено (живая проверка). Как miniapp получает VITE_* (apps/miniapp/Dockerfile, compose) — не проверено.

## 3. Поток [канон P4 §4.6, P8 §8.2, §8.8; механика — ШТАБ-тех, кроме В1–В2]
1. Вход: «/start support» и /support в личке. При access_enabled — только granted (AC.read_state → NOTHING). Повтор чаще раза в 60 с — без нового поста (память процесса).
2. Пост в «Поддержку»: «[заглушка] Обращение в поддержку» + GROUP_WHO (номер по tg_user_id, tombstoned_at IS NULL; нет строки — «—»). Кнопки: «📇 Карточка» (card:<short_no>, только при номере) и «✉️ Написать» (sup:w:<tg_id>).
3. Участнику: «[заглушка] Напишите вопрос ответом на это сообщение» + ForceReply (В1).
4. Reply участника на этот промпт, текст: пост — подпись, пустая строка, текст (html.escape, до 3500 знаков), те же кнопки; участнику «[заглушка] Вопрос передан». Не текст — «[заглушка] Пришлите текстом».
5. ✉️ — только WORK_GROUP_ID + SUPPORT_TOPIC_ID + ACCESS_ADMIN_IDS, иначе answer() без текста + лог. Бот в теме: «[заглушка] Ответ участнику #NNNNNN (ID N): напишите ответом» + ForceReply(selective).
6. Reply админа на него: send_message участнику без parse_mode, префикс «[заглушка] Ответ поддержки:». Есть только tombstoned-строки — не слать (P455). В теме «[заглушка] доставлено» или «не доставлено» (В2).
- tg_id — из текста СВОЕГО сообщения бота до первой пустой строки («ID <цифры>»); на tg:// и текст участника не опираться (как bot-i3.md §1). Логи — без tg_user_id, short_no, текстов.

## 4. Блокеры (указание ШТАБа п.4)
- Б1. «Написать» под постами «Рефлексии» и «Отчёты» (P8 §8.2) — только через outbox.py (под КОДЕРОМ). Вне пачки; карточка после мержа его задачи.
- Б2. Нажатие «📇» под постом поддержки обрабатывает card_handlers.py. Если фильтр пускает не из любой темы WORK_GROUP_ID — нужна правка, блок. Проверить чтением — окно КАРТОЧКИ. Префикс кнопки — импорт из card.py без правки (имя — не проверено).
- Б3. config.py, app.py, texts.py может менять КОДЕР (bot-i3-2: texts.py). 3a — после его мержа, сверка по свежему main.

## 5. Нарезка (одна карточка — одна область)
| id | область | что | файлы | режим, кредиты | РЕВЬЮЕР |
|---|---|---|---|---|---|
| bot-i3-3a | bot | §3 п.1–4 | создать bot/support.py ~180 стр., bot/support_handlers.py ~170, tests/test_support.py ~280; изменить config.py +30, app.py +10, texts.py +20 | Агент Р1, 450–550 | нет |
| bot-i3-3b | bot | §3 п.5–6 | support.py +80, support_handlers.py +90, texts.py +8, test_support.py +150 | Агент Р1, 300–400 | нет |
| miniapp-i3-3 | Mini App | кнопка на всех шагах OF и LS, кроме «Загрузка…» | создать SupportButton.tsx ~50; OF +15, LS +10, тест +40 | КОДЕР + Р1-П, 100–150 | да: OF содержит экран 18+ |
Порядок: 3a → 3b (общий support_handlers.py); miniapp-i3-3 параллельно 3a; выкат вместе, бот раньше.
- Роутер: build_support_router(config, connect) — ДО build_router (иначе «/start support» съест H), фильтр CommandStart(deep_link=True, magic=F.args == "support"); /start без аргумента не задет.
- CF: support_topic_id (SUPPORT_TOPIC_ID, _parse_int); SUPPORT_REQUIRED_VARS = BOT_DATABASE_URL, WORK_GROUP_ID, SUPPORT_TOPIC_ID, ACCESS_ADMIN_IDS; support_enabled; иначе WARNING с именами.
- Env: SUPPORT_TOPIC_ID и VITE_BOT_USERNAME (имя условное) — как CARDS_TOPIC_ID: compose и .env.example — Р0 Автора перед выкатом, в карточки Агента не входят, в «Запреты» прямо. ARG в apps/miniapp/Dockerfile — файл Mini App, в карточку входит (не проверено).
- Подпись кнопки — константа «Поддержка» в компоненте, без ключа text_registry: ключ задел бы B4.json (api) и ONBOARDING_TEXT_KEYS / LATER_TEXT_KEY_LIST [ШТАБ-тех].

## 6. Чтение окна КАРТОЧКИ (КБ, лимит 170)
Общее: база 67,7 + этот файл ≈ 13 + DECISIONS 7,5 + CANON-CHECK 4,7 = 92,9.
- 3a и 3b: + config 8,3, app 7,8, texts 7,8, handlers 4,4, access_handlers 10,4, access.py 15,2, card.py 7,3, card_handlers.py 5,4 (Б2), test_bot.py 4,6 = 164,1. I4 §8 сюда не влезает.
- miniapp-i3-3: + OF 16,9, LS 12,6, OnboardingFlow.test.ts ≈ 21,0, App.tsx ≈ 6,8 (размеры — iter3-2) = ≈ 150,2 + apps/miniapp/Dockerfile (размер — ШТАБ).

## 7. Задетые тесты (черновик «Т»)
- 3a меняет общие build_dispatcher и BotConfig. test_bot.py — не ожидается: make_config без переменных → выключено, caplog нет, plain /start не ловится (проверено по файлу). test_card.py, test_access.py — не проверено: grep «missing_vars|caplog|build_dispatcher|BotConfig(»; сверка текста WARNING или полного списка полей → в список. Общие списки: grep в apps/bot/tests и tools/check.sh на сверку переменных CF с .env.example и на перечень констант TX (vars(texts), dir(texts)).
- 3b: tests/test_support.py (из 3a); прочее не ожидается.
- miniapp-i3-3: кнопку ставит контейнер, новые пропсы презентационных компонентов — необязательные → не ожидается; grep «renderToStaticMarkup|toMatchSnapshot|LaterStepView» в src/**/*.test.ts. Списки ключей текстов не меняем.

## 8. Канон и решения
(а) P4 §4.6 + YAML; P8 §8.2, 8.5, 8.6, 8.8 + YAML support, write_via_bot; P9 R256, text_form_technical_contract, author_channel; RG /support; I4 §2 P455, P494, §5; I4 §8 — не проверено.
(б) Против DECISIONS: P4 §4.6 «с кликабельным именем» — Р-15; P9 выжимка «Имя (@username · ID 12345)» и YAML address_line_format — Р-15. Р-16: в пост полей анкеты нет, текст вопроса пишет сам участник — правок нет. P8 §8.5 и YAML clickable_name уже по Р-15.
(в) Правки DOCS (P9 > 20 КБ — Автор вставляет кусками):
1. architecture/04-onboarding.md · найди «Бот шлёт обращение в тему «Поддержка» Рабочей группы (с кликабельным именем + кнопкой «Карточка»)» · замени на «Бот шлёт обращение в тему «Поддержка» Рабочей группы (подпись Р-15: «Участник #NNNNNN (ID N) → написать», имя и username не берём; кнопка «Карточка»)».
2. architecture/09-communications.md · найди «канонический формат обращения (8.5): Имя (@username · ID 12345) → [написать]» · замени на «канонический формат обращения (8.5, Р-15): Участник #NNNNNN (ID 12345) → [написать] (имя и username не берём)».
3. architecture/09-communications.md · найди «address_line_format: "<b>{name}</b> (@{username} · ID {tg_user_id}) → [написать]"» · замени на «address_line_format: "Участник #{short_no} (ID {tg_user_id}) → [написать]"  # Р-15».
Normative: при В2 = А — врезка в шапку I4 + OVERRIDES AD-xx (номер — ШТАБ): «P494 предпросмотр write_via_bot — позже; до того доставка сразу, без parse_mode». При В2 = Б — правок нет.
Для ШТАБА: в Р-15 «В каноне устарело» дописать «04 §4.6, 09 author_channel».

## 9. Кандидаты DEFECTS (в DF не пишу)
- I4 §5 write_via_bot_flow (пишет участник) против P8 §8.8 (пишет Автор).
- I4 topic_bindings (таблица, /bind_topic) против кода: темы — переменные окружения (CF) с bot-group-1.

## 10. Вопросы Автору (К-4)
- В1 [г]. Как участник шлёт вопрос. Канон: проверено P4 §4.6, P8 §8.2, RG, I4 §2, §5 — молчит о механике; I4 §8 не прочитан. А — сообщение бота с полем ответа; в группу идёт только ответ на него, прочее — тишина, как сейчас. Плюс: случайное не уходит в группу. Минус: написал не ответом — не дойдёт. Б — любой текст участника с доступом идёт в «Поддержку». Плюс: проще (P4 §4.5). Минус: в группу уходит всё; правка access_handlers.py и test_access.py, +80–100 кредитов. Мнение: А.
- В2 [б]. Предпросмотр ответа Автора. Канон: I4 §2 P494 «called_from: write_via_bot before preview render»; P8 §8.8 — без предпросмотра. А — доставка сразу, без HTML, в теме «доставлено»; отход от I4 → DECISIONS + OVERRIDES. Б — по I4: предпросмотр + «Отправить», +100–150 кредитов к 3b. Мнение: А.

## 11. Прочитано
- Обязательные: DESIGNER, PACK, STATE, AGENT-BRIEF, DECISIONS, CANON-CHECK, P4 (§4.6), P8 (§8.2, 8.8), iter3-2 («Поддержка» — кандидат), bot-i3 (подпись, фильтры), app (порядок роутеров), config (шаблон тем), texts (GROUP_WHO), handlers (CommandStart), OF и LS (шаги без кнопки).
- По необходимости: P9 — до R258, конец обрезан; AH — фильтры, ловушка темы; RG — /support. outbox.py не нужен.
- Сверх списка: access.py 15,2 — read_state для гейта; test_bot.py 4,6 — правило «Т»; I4 ≈ 57 — §1–7, §8 обрезан.
