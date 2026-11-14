# bot-sup-1 — вопрос поддержки: пост в тему группы по topic_code и ответ ✉️ (Р-19)

## 1. Шапка
- id: bot-sup-1 · заголовок PR: «bot-sup-1: вопросы поддержки — пост в 8 тем группы, ответ ✉️ с предпросмотром» · ветка Агента: feat/bot-sup-1 [ШТАБ-тех] · режим: Агент Р1.
- Зависит от: db-sup-1 (миграция 0017 в main), api-sup-1 (#217, main 1aeae18 — только контракт payload). Миграций в задаче нет. Карточка написана по коду @57eb408 (после #217 бот не менялся).
- Порядок выката: migrate 0017 → бот → api → miniapp (исследование bot-i3-3 §4 Б4): старый бот отправит support_question путём лички → DLQ bad_payload.
- Правило К — docs/process/CANON-CHECK.md. Сначала прочитай docs/decisions/DECISIONS.md целиком.

## 2. Цель
Бот берёт строку outbox support_question, читает вопрос из support_questions и публикует пост в тему Рабочей группы по topic_code (8 тем: s1…s7, other). Под постом — «📇 Карточка» и «✉️ Ответить». Ответ Автора: ✉️ → промпт (ForceReply) → ответ reply → предпросмотр «Отправить»/«Отмена» → участнику в личку от имени бота. Попутно: ленивый импорт fmt_msk в _deliver_group переносится наверх outbox.py.

## 3. Решения Автора (дословно, docs/decisions/DECISIONS.md)
- Р-19 (13.11): «поддержка: кнопка «Помощь» — после 18+ и согласий, всегда внизу Mini App и пунктом «Меню»; экран: тема кнопкой → вопрос (черновик хранится) → пост в тему группы этой темы (подпись Р-15, «Карточка»). Тем 8: «Поддержка 1»…«Поддержка 7» и «Другое», у каждой своя тема группы; названия — заглушки, заменить до показа участникам курса. Ответ Автора — ✉️, предпросмотр, «Отправить»; ветка — цепочка ответов. Отложено (SHTAB-DEBTS §2): human_active, мьют 5/мин, /support_inbox. Устарело: 04 §4.6, YAML support_button: everywhere, I4 §8 E2.»
- Р-15 (01.11): «подпись в группе: «Участник #NNNNNN (ID N) → написать», ссылка tg://user?id=N; имя и username не берём.»

## 4. Выдержки канона (по исследованию bot-i3-3 §1; docs/architecture/** не открывать)
- 08-working-group.md §8.2: «Кнопки: Карточка / Написать.» §8.8: «Кнопка ✉️ … Автор пишет текст в группе → Бот доставляет Участнику от имени Бота»; whitelist; callback привязан к участнику. [канон 08 §8.8]
- normative/I4-wave-d.md §2 P494: предпросмотр перед write_via_bot (совпадает с Р-19); P455: ✉️ стёртому участнику — тихий сброс. [канон I4 §2]
- 09-communications.md R256: HTML, html_escape, 4096 знаков. [канон 09 R256]

## 5. ЧТО ПРОЧИТАТЬ (≈ 128 КБ)
AGENT-BRIEF.md 17,1 · docs/decisions/DECISIONS.md 8,1 · docs/process/CANON-CHECK.md 4,9 · эта карточка ≈ 14 · apps/bot/bot/outbox.py 29,0 · apps/bot/bot/card.py 8,4 · apps/bot/bot/card_handlers.py 6,0 (образец роутера, connect, _reply) · apps/bot/bot/config.py 8,3 · apps/bot/bot/app.py 7,8 · apps/bot/bot/texts.py 7,8 · apps/bot/tests/test_outbox_group.py 16,7 (образец FakeCursor / FakeConn / make_bot — скопировать, не импортировать).

## 6. Файлы (7)
- Создать: apps/bot/bot/support.py (~90), apps/bot/bot/support_handlers.py (~200), apps/bot/tests/test_support.py (~300).
- Изменить: apps/bot/bot/outbox.py (+45), apps/bot/bot/config.py (+50), apps/bot/bot/app.py (+8), apps/bot/bot/texts.py (+25).
- НЕ трогать: card.py, card_handlers.py, access.py, все существующие тесты (в т.ч. test_outbox_group.py), infra/**, .env.example.

## 7. Контракт и поведение
7.1 config.py [ШТАБ-тех]
- Переменные SUPPORT_S1_TOPIC_ID … SUPPORT_S7_TOPIC_ID, SUPPORT_OTHER_TOPIC_ID (message_thread_id тем в WORK_GROUP_ID), чтение _parse_int. Поля support_s1_topic_id … support_s7_topic_id, support_other_topic_id: int | None = None — в КОНЕЦ dataclass.
- SUPPORT_TOPIC_FIELDS = {"s1": "support_s1_topic_id", …, "other": "support_other_topic_id"}; SUPPORT_TOPIC_VARS — 8 имён в том же порядке; SUPPORT_REQUIRED_VARS = ("BOT_DATABASE_URL", "WORK_GROUP_ID", "ACCESS_ADMIN_IDS").
- support_topic_id(code) -> int | None (неизвестный код → None); support_thread_ids() -> frozenset[int] (только заданные); support_missing_vars() -> list[str] (незаданные из REQUIRED, затем из 8 тем); свойство support_enabled = все REQUIRED заданы и задана хотя бы одна тема.
- Требование (а): GROUP_TOPIC_VARS и group_missing_vars() не менять (test_outbox_group №8 ждёт ровно ["REFLECTIONS_TOPIC_ID", "REPORTS_TOPIC_ID"]). Докстринг: блок «Поддержка (bot-sup-1)».

7.2 outbox.py [Р-19 + ШТАБ-тех]
- «from bot.access import fmt_msk» — наверх модуля, ленивый импорт в ветке REFLECTION убрать. Цикла нет (по коду: access.py импортирует только bot.texts).
- SUPPORT_Q (из bot.support): «SELECT pid, topic_code, body, created_at FROM support_questions WHERE id = %s». GROUP_ROUTES["support_question"] = (None, SUPPORT_Q): None = тема берётся из topic_code строки. Докстринг: строка «SUPPORT_Q SELECT (id, pid, topic_code, body, created_at) на support_questions (0017)» и порядок ветки.
- Порядок ветки support_question: шаги 1–3 как сейчас → 4: только work_group_id (нет → group_not_configured; getattr с None не вызывать) → 5: pid в payload как сейчас → question_id: bool, не int или ≤ 0 → bad_payload → SUPPORT_Q: нет строки → support_not_found; str(pid строки) ≠ str(pid) → bad_payload → thread_id = config.support_topic_id(topic_code); None (в т.ч. config None) → group_not_configured → текст → кнопки → _send_group (HTML) → MARK.
- SQL support_question: успех [CLAIM, GROUP_ADDRESSEE, SUPPORT_Q, MARK]; нет темы для topic_code — [CLAIM, GROUP_ADDRESSEE, SUPPORT_Q, TO_DLQ, MARK]; нет WORK_GROUP_ID — [CLAIM, GROUP_ADDRESSEE, TO_DLQ, MARK].
- Требование (в): для reflection_submitted и ladder_day2_alert порядок SQL не меняется: group_not_configured — [CLAIM, GROUP_ADDRESSEE, TO_DLQ, MARK], успех — [CLAIM, GROUP_ADDRESSEE, (REFLECTION,) MARK].
- Текст: texts.GROUP_SUPPORT_QUESTION.format(time=_esc(fmt_msk(_aware(created_at))), who=who, body=_esc(body)). Кнопки: support.question_markup(short_no, question_id).

7.3 support.py — чистые функции и SQL, без БД и Bot API
- SUPPORT_Q; PARTICIPANT = «SELECT tg_user_id, tombstoned_at FROM tg_user_registry WHERE pid = %s» (права 0009). CALLBACK_PREFIX = "sup"; callback_data: sup:r:<N> (✉️), sup:s:<N> (Отправить), sup:x:<N> (Отмена); N — question_id, 1…19 цифр, ≤ 9223372036854775807, иначе None (как card._bigint).
- question_markup(short_no, n) -> InlineKeyboardMarkup: один ряд [кнопка из card_button(short_no).inline_keyboard[0][0], если short_no не None] + [SUPPORT_BUTTON_REPLY, sup:r:N]. preview_markup(n): [SUPPORT_BUTTON_SEND, sup:s:N], [SUPPORT_BUTTON_CANCEL, sup:x:N] одним рядом.
- parse_callback(data) -> (action, n) | None (action ∈ r, s, x; fullmatch). Регулярки заголовков строятся из шаблонов texts (как card._who_re): n_from_prompt(text) — первая строка целиком = SUPPORT_PROMPT; n_from_preview(text) -> (n, body) | None — первая строка = SUPPORT_PREVIEW, body — всё после первой «\n\n».

7.4 support_handlers.py — build_support_router(config, connect=None) (образец card_handlers.py)
- Допуск _allowed(chat_id, thread_id, user_id): chat_id == work_group_id И thread_id ∈ support_thread_ids() И user_id ∈ access_admin_ids [указание ШТАБа]. Чужим колбэкам — callback.answer() без текста + WARNING без ID.
- Колбэк F.data.startswith("sup:"): parse_callback None → answer() + WARNING.
- r (✉️): message.reply(SUPPORT_PROMPT.format(n=N), reply_markup=ForceReply()) — без selective [ШТАБ-тех, решил ШТАБ К-5]; answer(). БД не нужна.
- Ответ админа: router.message с фильтром-функцией (ВСЯ проверка в фильтре, иначе роутер глотает чужие сообщения группы): чат group/supergroup, _allowed, reply_to_message есть, reply.message_id ≠ message_thread_id, reply.from_user.id == message.bot.id, n_from_prompt(reply.text) не None. В обработчике: нет message.text → reply SUPPORT_SEND_TEXT; len > 2000 → SUPPORT_TOO_LONG; иначе reply SUPPORT_PREVIEW.format(n=N) + «\n\n» + text, без parse_mode, preview_markup(N).
- s (Отправить), без памяти: n_from_preview(callback.message.text) → n ≠ N из колбэка или None → answer() + WARNING. БД (connect(config.database_url), close в finally): SUPPORT_Q(N) → pid; PARTICIPANT(pid). Ошибка БД → answer(SUPPORT_TRY_LATER), кнопки остаются. Нет строки или tombstoned_at не None → снять кнопки, текст SUPPORT_NOT_DELIVERED, участнику ничего (P455). Иначе edit_message_reply_markup(reply_markup=None); TelegramBadRequest «message is not modified» → answer() и стоп (второе нажатие). Затем send_message(chat_id=tg_user_id, text=SUPPORT_ANSWER_PREFIX + «\n\n» + body) без parse_mode; затем edit_message_text: SUPPORT_DELIVERED (или SUPPORT_NOT_DELIVERED при ошибке отправки) .format(n=N) + «\n\n» + body; answer().
- x (Отмена): edit_message_reply_markup(None), answer(). Ошибки Telegram везде — WARNING с именем класса, обработчик не падает.

7.5 app.py
- Требование (г): build_dispatcher подключает build_support_router(config, connect) после card и ДО access, только если config.support_enabled (требование (д)). Импорт ленивый, как у card.
- Требование (б): если support_missing_vars() не пуст — один WARNING отдельной записью, текст начинается с «Поддержка выключена»: «Поддержка выключена: не заданы %s» (support_enabled False) или «Поддержка выключена для тем: %s» (включена, часть тем пуста); только имена. Не дописывать в «Темы группы не заданы», не начинать с «Карточка выключена». Докстринг: абзац bot-sup-1.

7.6 texts.py — заглушки [ШТАБ-тех], блок «Поддержка (bot-sup-1)»
GROUP_SUPPORT_QUESTION = "[заглушка] Вопрос в поддержку · {time}\n{who}\n\n{body}"; SUPPORT_PROMPT = "[заглушка] Ответ на вопрос {n}: напишите ответом на это сообщение"; SUPPORT_PREVIEW = "[заглушка] Предпросмотр (вопрос {n}):"; SUPPORT_DELIVERED = "[заглушка] Доставлено (вопрос {n}):"; SUPPORT_NOT_DELIVERED = "[заглушка] Не доставлено (вопрос {n}):"; SUPPORT_SEND_TEXT = "[заглушка] Пришлите ответ текстом."; SUPPORT_TOO_LONG = "[заглушка] Ответ длиннее 2000 знаков."; SUPPORT_TRY_LATER = "[заглушка] Не удалось, попробуйте позже."; SUPPORT_ANSWER_PREFIX = "[заглушка] Ответ поддержки:". Кнопки без префикса (как CARD_BUTTON, ACCESS_BUTTON_*) [К-5]: SUPPORT_BUTTON_REPLY = "✉️ Ответить", SUPPORT_BUTTON_SEND = "Отправить", SUPPORT_BUTTON_CANCEL = "Отмена".

7.7 Логи: только outbox id, event_type, код ошибки, имя класса. Никогда: tg_user_id, pid, short_no, N (question_id), topic_code-значение номера темы, тексты вопроса и ответа.

## 8. БД
Миграций нет. Права app_bot: support_questions SELECT (id, pid, topic_code, body, created_at) — 0017 (по коду миграции); tg_user_registry (pid, tg_user_id, tombstoned_at, short_no) — 0009/0011. Только параметры %s, без SELECT *, без RETURNING.

## 9. Тесты — все в apps/bot/tests/test_support.py (tg_user_id 4401–4499)
Фикстуры FakeCursor / FakeConn / make_bot — копия по образцу test_outbox_group.py. Общая проверка _no_pii(caplog): в логах нет tg_user_id, pid, short_no, N, текстов.
1. support_question успех: тема по topic_code (s3 и other — разные thread_id), HTML, body экранирован (образец test_outbox_group №2), SQL [CLAIM, GROUP_ADDRESSEE, SUPPORT_Q, MARK], кнопки «📇» и «✉️» sup:r:N в одном ряду.
2. short_no None → только «✉️». 3. стёрт → MARK без поста и без DLQ. 4. expired → DLQ.
5. Нет WORK_GROUP_ID → group_not_configured, SQL [CLAIM, GROUP_ADDRESSEE, TO_DLQ, MARK]. 6. Тема topic_code не задана → group_not_configured, SQL [CLAIM, GROUP_ADDRESSEE, SUPPORT_Q, TO_DLQ, MARK].
7. question_id: True, "5", 0, -1, нет → bad_payload. 8. Строки нет → support_not_found. 9. Чужой pid строки → bad_payload.
10. config: 8 переменных, support_topic_id, support_thread_ids, support_missing_vars, support_enabled; кривое число → ConfigError без значения; group_missing_vars прежний.
11. build_dispatcher: support_enabled False → роутера нет, WARNING «Поддержка выключена: не заданы…»; часть тем → WARNING «Поддержка выключена для тем…»; connect передан роутеру.
12. support.py: parse_callback (границы bigint, мусор), n_from_prompt, n_from_preview, разметка кнопок.
13. ✉️ от админа в теме поддержки → ForceReply без selective; не админ / чужой чат / тема не из 8 → answer() без текста, без reply.
14. Ответ reply: предпросмотр без parse_mode и с кнопками; не текст → SEND_TEXT; 2001 знак → TOO_LONG; reply не на промпт бота или не админ → фильтр не пропускает.
15. «Отправить»: участнику без parse_mode с префиксом, предпросмотр → «Доставлено», кнопки сняты; «message is not modified» → второй send_message нет; стёрт → не шлём, «Не доставлено»; ошибка БД → TRY_LATER, кнопки остаются; N колбэка ≠ N заголовка → игнор.
16. «Отмена» → кнопки сняты, участнику ничего.
Цели: bash tools/check.sh bot. SQL бота на настоящей БД CI не проверяет — только живая проверка.

## Задетые тесты (правило «Т»)
Не ожидается — сверил ШТАБ по коду @57eb408 (apps/bot/tests): GROUP_ROUTES целиком тестами не сверяется; monkeypatch fmt_msk нет; все BotConfig(…) в test_bot, test_card, test_outbox, test_outbox_group — только именованные аргументы (новые поля в конце); порядок роутеров не сверяется; теста «все переменные config есть в .env.example» нет. test_access.py ШТАБ сверит до промпта. Зелёными держат требования (а)–(д) в §7. Упал тест вне списка → не чинить, «тест X вне списка» в ИТОГ, стоп.

## 10. Живые проверки (после выката всей пачки «Помощь», одной сессией, PLAN §4)
- Выкат: migrate 0017 → бот → api → miniapp; команды — ШТАБ по PLAN §4.
- Логи старта бота: при пустых SUPPORT_*_TOPIC_ID — один WARNING «Поддержка выключена…» только с именами; Traceback 0.
- Сценарий на А2: «Помощь» → тема → вопрос → «Отправить» → пост в тему группы этой темы (подпись Р-15, «📇», «✉️») → ✉️ → промпт → ответ reply → предпросмотр → «Отправить» → у А2 в личке «[заглушка] Ответ поддержки:» и текст; предпросмотр → «Доставлено», кнопки сняты; повторное нажатие ничего не шлёт.

## 11. Запреты
AGENT-BRIEF §3. Плюс: infra/** и .env.example — ЗАПРЕЩЕНО (Р0 Автора); миграций нет; тексты — только заглушки; состояния в памяти нет (N — из callback_data и текстов своих сообщений); новых зависимостей нет; существующие тесты не править.

## Вне задачи
- 8 переменных SUPPORT_*_TOPIC_ID в environment бота и .env.example — Р0 Автора до выката (ШТАБ).
- human_active, мьют 5/мин, /support_inbox, /support в личке (Р-19); экран Mini App — miniapp-sup-1.

## Канон и решения
(а) 04-onboarding.md §4.6 + YAML support_button; 08 §8.2, §8.5, §8.8; 09 R256, author_channel, address_line_format; build/bot-commands-registry.yaml /support; normative/I4-wave-d.md §2 P455, P494, §5, §8 E2.
(б) Против DECISIONS: механика 04 §4.6 и «кликабельное имя» — Р-19, Р-15; I4 §8 E2 — Р-19; 09 «Имя (@username · ID 12345)» и address_line_format — Р-15; RG /support — Р-19. I4 P494 совпадает с Р-19. Агента правки не держат: Р-19 уже содержит «Устарело» [К-5].
(в) Правки DOCS (вносит ШТАБ DOCS-пакетом; 09 больше 20 КБ — Автор вставляет кусками):
1. architecture/04-onboarding.md · найди «При нажатии: Бот шлёт обращение в тему «Поддержка» Рабочей группы (с кликабельным именем + кнопкой «Карточка») + предлагает Участнику написать вопрос текстом (пересылается в ту же тему).» · замени на «При нажатии (Р-19): экран вопроса в Mini App: тема кнопкой (8 тем: «Поддержка 1»…«Поддержка 7», «Другое») → вопрос (черновик хранится) → «Отправить» → пост в тему Рабочей группы этой темы (подпись Р-15: «Участник #NNNNNN (ID N) → написать», имя и username не берём; кнопки «Карточка» и ✉️). Ответ Автора: ✉️ → предпросмотр → «Отправить» → Участнику от имени Бота. Тем 8 (s1…s7, other), у каждой своя тема группы; ветка — цепочка ответов.»
2. architecture/09-communications.md · найди «канонический формат обращения (8.5): Имя (@username · ID 12345) → [написать]» · замени на «канонический формат обращения (8.5, Р-15): Участник #NNNNNN (ID 12345) → [написать] (имя и username не берём)».
3. architecture/09-communications.md · найди «address_line_format: "<b>{name}</b> (@{username} · ID {tg_user_id}) → [написать]"» · замени на «address_line_format: "Участник #{short_no} (ID {tg_user_id}) → [написать]"  # Р-15».
4. architecture/normative/I4-wave-d.md — врезка в шапку, тело не переписывать: «Врезка AD-xx (Р-19, 13.11.2026): §8 E2 в части поддержки перекрыт docs/decisions/DECISIONS.md Р-19: кнопка «Помощь» в Mini App → тема (8 тем) → вопрос → пост в тему группы этой темы; ответ Автора: ✉️ → предпросмотр → «Отправить»; /support в личке нет.» Плюс OVERRIDES.yaml: id AD-xx (номер — ШТАБ), цель I4 §8 E2, основание Р-19, формат — по соседним AD.
5. architecture/build/bot-commands-registry.yaml — у /support пометка «не делаем (Р-19)»; текст «найди» ШТАБ берёт из RG (окном не прочитан).

## 12. Критерии готовности
7 файлов из §6, других нет; bash tools/check.sh bot зелёный; тесты §9 есть; существующие тесты не менялись и зелёные; ленивого импорта fmt_msk нет; в логах нет ПДн (§7.7); ИТОГ по AGENT-BRIEF §10.

## 13. Оценка
Строк ≈ 720 (код ~420, тесты ~300) → Агент Р1 580–720 кредитов; «Задетых» 0. Часы Автора: ~0,3 (промпт, PR); Р0 env — отдельно.

## 14. РЕВЬЮЕР
Нет: initData, 18+, согласия, rate-limit, GRANT, оплата не затронуты.
