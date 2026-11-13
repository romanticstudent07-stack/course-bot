# bot-i3-1 — /card по #NNNNNN и по reply + обработчик нажатия «card:»

## 1. Паспорт
- id: bot-i3-1 · Заголовок PR: «bot-i3-1: /card по номеру и reply, обработчик card:» · Ветка: feat/bot-i3-1-card
- Режим: Р1 (Агент) · РЕВЬЮЕР: да · Зависит от: db-i3-1 (0013), db-i3-2 (0014) — смержены; исследование docs/research/bot-i3.md (PR #203).
- Следующая: bot-i3-2 (кнопка «📇 Карточка» под постами, outbox.py) — берёт из bot/card.py только card_button и CALLBACK_PREFIX.

## 2. Цель
Owner из whitelist вызывает в Рабочей группе /card #NNNNNN или /card ответом (reply) на пост бота и получает карточку участника, собранную свежей из БД, только в теме «Карточки». До отправки бот пишет строку аудита в privacy_audit_log. Обработчик нажатия «card:<номер>» тоже делается здесь (кнопку под постами ставит i3-2). Миграции нет. Тексты — заглушки.

## 3. Решения Автора (дословно, К-6)
- Р-15 (01.11): «Делаем: «Участник #NNNNNN (ID N) → написать», ссылка tg://user?id=N; имя и username не берём.»
- Р-16 (04.11): «город → только tz (IANA), город не храним; … ФИО, телефон, email не собираем».
- В1 (12.11, bot-i3.md §9): «Статус — словарь в коде бота из двух слов: active → «Заглушка: активен», sleeping → «Заглушка: спящий». Любой другой код lifecycle_phase — как есть: «статус: <код>» через html.escape. «Нет данных» для статуса не писать: код есть, нет перевода. status_flags в карточку не выводить.»
- В2 (12.11): «Вариант А с поправкой: «Жизни: осталось N» и строка «Заглушка: журнал списаний — позже» (не «нет данных»).»
- Р-1 (оплаты вне Mini App), Р-6а (паузы не построены), Р-3 (фото нет): в карточке оплаты и паузы — «нет данных», фото нет.

## 4. Выдержки архитектуры
- 06 §6.1: «Единый источник правды — БД. Карточка формируется свежей из БД в момент запроса (не хранится готовой).»
- 06 §6.2: «По reply + /card (параметр не нужен, user_id из reply). По кнопке 📇 Карточка … По параметру /card #000123» (часть «/card @username» не делаем — Р-15, см. «Канон и решения»).
- 06 §6.4 (порядок): «Кто: часовой пояс, кликабельная ссылка tg://user?id=, короткий №» → «Было → стало: вес (старт → текущий), Чек-Ап-зона (старт → последняя, с пометкой улучшение/ухудшение)» → «Текущая позиция: Этап, модуль.день, статус» → «Жизни: осталось + журнал списаний» → «Оплаты» → «Паузы» → «Счётчик возвратов на закрепление» → «Дата регистрации». Кнопка «📊 Полная Карта изменений» — вне пачки.
- 06 Fail-safe: «/card — только whitelist. Без reply/параметра → просьба уточнить идентификатор. Несуществующий идентификатор → «не найден». Карточка = ПДн + данные о здоровье → только в теме «Карточки», только whitelist. Аудит-лог доступа обязателен (кто, когда, чью карточку смотрел) — 152-ФЗ. … Карточка мигрированного не падает при отсутствии данных (показывает «нет данных»).»
- 08 §8.6 (по bot-i3.md §1): «Callback строго привязан к participant_id» — привязка через short_no (UNIQUE).
- 05 §5.3 (по bot-i3.md §3) + apps/api/config/checkup/checkup.v1.json: green 0–9, yellow 10–22, red 23–45.

## 5. ЧТО ПРОЧИТАТЬ (Агент)
AGENT-BRIEF.md 17,1; apps/bot/bot/config.py 7,0; apps/bot/bot/app.py 7,0; apps/bot/bot/access_handlers.py 10,1 (образец фильтров, command_precheck, _with_conn); apps/bot/bot/access.py 15,2 (connect, fmt_msk, aware); apps/bot/bot/texts.py 5,0; apps/bot/tests/test_bot.py 4,6 (образец _feed через build_dispatcher). Эта карточка ≈ 13. Чтение КОДЕРА ≈ 79 КБ.
Не читать: tests/test_access.py, outbox.py, docs/architecture/**.

## 6. Файлы
- Создать: apps/bot/bot/card.py, apps/bot/bot/card_handlers.py, apps/bot/tests/test_card.py.
- Изменить: apps/bot/bot/config.py, apps/bot/bot/app.py, apps/bot/bot/texts.py.
- Больше ничего (infra и .env.example — см. «Запреты»).

## 7. Контракт
Проверено ПРОЕКТИРОВЩИКОМ (выводом, по коду):
- UNIQUE short_no — миграция 0002: short_no bigint GENERATED ALWAYS AS IDENTITY, CONSTRAINT tg_user_registry_short_no_key UNIQUE (short_no). В 0011 — только GRANT SELECT (short_no) роли app_bot. Поиск по short_no даёт 0 или 1 строку.
- Коды зон — CHECK в 0014: checkup_zone IS NULL OR checkup_zone IN ('green', 'yellow', 'red'). Порядок: green < yellow < red (checkup.v1.json, 05 §5.3).
- Права app_bot: tg_user_registry (pid, tg_user_id, tombstoned_at, short_no, created_at); participant_state (pid, lifecycle_phase, status_flags, stage_no, module_no, day_no, lives, tz); measurements_log (pid, kind, occasion, checkup_zone, weight_kg, created_at) — БЕЗ id, БЕЗ checkup_score; privacy_audit_log — только INSERT (actor_id, actor_role, action, participant_id), без SELECT и без RETURNING.

config.py [решил ШТАБ, bot-i3 §5]:
- Поле cards_topic_id: int | None = None (тема «Карточки», message_thread_id); from_env: _parse_int(env, "CARDS_TOPIC_ID").
- CARD_REQUIRED_VARS = ("BOT_DATABASE_URL", "WORK_GROUP_ID", "CARDS_TOPIC_ID", "ACCESS_ADMIN_IDS"); card_missing_vars() по образцу access_missing_vars; card_enabled = not card_missing_vars(). Докстринг модуля дополнить.

app.py: в build_dispatcher после build_router и ДО роутера доступа: при config.card_enabled — dp.include_router(build_card_router(config, connect)) (импорт внутри if, как у доступа); иначе один logger.warning("Карточка выключена: не заданы %s", имена). Докстринг дополнить.

bot/card.py — SQL (только %s) и чистые функции:
    FIND = "SELECT pid, tg_user_id, created_at FROM tg_user_registry WHERE short_no = %s AND tombstoned_at IS NULL"
    STATE = "SELECT lifecycle_phase, stage_no, module_no, day_no, lives, tz FROM participant_state WHERE pid = %s"
    MEASUREMENTS = "SELECT kind, checkup_zone, weight_kg, created_at FROM measurements_log WHERE pid = %s ORDER BY created_at"
    AUDIT = "INSERT INTO privacy_audit_log (actor_id, actor_role, action, participant_id) VALUES (%s, 'owner', 'view', %s)"
- ORDER BY только created_at: SELECT (id) у app_bot нет. status_flags не выбирать. actor_id = str(tg id owner).
- CALLBACK_PREFIX = "card"; card_button(short_no: int) → InlineKeyboardMarkup с одной кнопкой texts.CARD_BUTTON, callback_data f"card:{short_no}". Здесь только сборка; «{num} = — → кнопки нет» решает i3-2.
- parse_arg(args) → int | None: строка после strip совпадает целиком с «#(\d{1,18})». Другое («123», «@user», пусто) → None.
- parse_callback(data) → int | None: целиком «card:(\d{1,18})».
- number_from_reply(reply) → int | None, по порядку: (1) callback_data «card:N» в любой кнопке reply.reply_markup; (2) первый «#(\d{1,18})» в (reply.text или reply.caption) ДО первой пустой строки ("\n\n"); (3) None. Текст после пустой строки (body участника) не смотреть.
- who_line(short_no, tg_user_id): texts.GROUP_WHO.format(num=f"{short_no:06d}", tg_id=tg_user_id, link='<a href="tg://user?id=N">' + html.escape(texts.GROUP_WRITE) + '</a>').
- render_card(short_no, tg_user_id, registered_at, state, rows) → str (HTML; каждая подстановка из БД — html.escape). Строки по 06 §6.4:
  1. CARD_TITLE; who_line; CARD_TZ (tz или CARD_NO_DATA).
  2. CARD_WEIGHT: первая и последняя строки kind body (один замер — оба одинаковы); нет строк → CARD_NO_DATA. Вес — str(weight_kg).
  3. CARD_ZONE: первая и последняя строки kind checkup, коды как есть. Пометка при ≥ 2 замерах и обоих кодах из ZONE_RANK = {green: 0, yellow: 1, red: 2}: ранг меньше → CARD_ZONE_BETTER, больше → CARD_ZONE_WORSE, равен → CARD_ZONE_SAME; иначе без пометки. Балл не показывать.
  4. CARD_POSITION (этап, модуль.день; любой номер NULL → CARD_NO_DATA); статус по В1 (CARD_STATUS_ACTIVE / CARD_STATUS_SLEEPING / CARD_STATUS_RAW.format(code=escape)); lifecycle_phase NULL → CARD_NO_DATA.
  5. CARD_LIVES.format(n=lives) (NULL → CARD_NO_DATA) + CARD_LIVES_LOG (В2).
  6. CARD_PAYMENTS, CARD_PAUSES, CARD_RETURNS — каждая со значением CARD_NO_DATA.
  7. CARD_REGISTERED.format(date=access.fmt_msk(created_at)).
  Нет строки participant_state → tz, позиция, статус и жизни — CARD_NO_DATA (CARD_LIVES_LOG остаётся).
- async load_and_audit(conn, short_no, actor_id) → (tg_user_id, html) | None: FIND (нет строки → None, аудита нет) → STATE → MEASUREMENTS → AUDIT → render. Исключение пробрасывается.

bot/card_handlers.py — build_card_router(config, connect=None), connect по умолчанию access.connect, _with_conn как в AH:
- Command("card") + F.chat.type.in_({"group", "supergroup"}). Фильтр: chat.id == work_group_id и from_user.id in access_admin_ids (тема — любая); иначе игнор + logger.warning без id, без вызовов Bot API и БД.
- Номер: parse_arg(command.args) → если args есть, но не разобраны → reply CARD_ASK_ID. Аргумента нет → reply (reply None или reply.message_id == message.message_thread_id → «reply нет» → CARD_ASK_ID). Reply не от бота (from_user.id != bot.id) → CARD_NOT_FOUND без БД. number_from_reply None → CARD_NOT_FOUND.
- load_and_audit: None → reply CARD_NOT_FOUND; исключение → лог имени класса + reply CARD_TRY_LATER, карточку не слать.
- Отправка: bot.send_message(chat_id=work_group_id, message_thread_id=cards_topic_id, text=html, parse_mode="HTML"); ошибка → лог имени класса + reply CARD_TRY_LATER. Успех: на /card — ничего [решил ШТАБ, К-5].
- Callback: F.data.startswith("card:"). Фильтр: callback.message.chat.id == work_group_id и from_user.id in access_admin_ids, parse_callback не None; иначе callback.answer() без текста + лог. Дальше как для /card; ошибки и «не найден» — текстом callback.answer; успех — callback.answer(texts.CARD_SENT) [К-5].
- Логи: без tg_user_id, pid, short_no и текста карточки.

texts.py — блок «Карточка (bot-i3-1). Заглушки», с ключами-комментариями bot.card_*: CARD_BUTTON = "📇 Карточка", CARD_ASK_ID, CARD_NOT_FOUND, CARD_TRY_LATER, CARD_SENT, CARD_TITLE, CARD_NO_DATA = "нет данных", CARD_TZ, CARD_WEIGHT ({start}, {current}), CARD_ZONE ({start}, {last}, {mark}), CARD_ZONE_BETTER, CARD_ZONE_WORSE, CARD_ZONE_SAME = "[заглушка] зона прежняя", CARD_POSITION ({s}, {m}, {d}), CARD_STATUS_ACTIVE = "Заглушка: активен", CARD_STATUS_SLEEPING = "Заглушка: спящий", CARD_STATUS_RAW = "статус: {code}", CARD_LIVES = "Жизни: осталось {n}", CARD_LIVES_LOG = "Заглушка: журнал списаний — позже", CARD_PAYMENTS, CARD_PAUSES, CARD_RETURNS, CARD_REGISTERED ({date}). Формулировки — «[заглушка] …».

## 8. БД
Миграции нет. Права — 0009, 0011, 0013, 0014 (выкачены). expected_tables.txt не трогать.

## 9. Тесты (apps/bot/tests/test_card.py, ≈ 12; сверх списка не добавлять)
Сборка — как test_bot.py: _feed через build_dispatcher(config, connect=fake); fake connect пишет порядок вызовов (SQL) и отдаёт заданные строки; Bot API перехвачен make_request.
1. config: CARDS_TOPIC_ID читается; «x» → ConfigError; card_enabled только при всех 4 переменных; card_missing_vars — имена.
2. parse_arg и parse_callback: «#000123» → 123; «123», «@user», «», «card:x» → None.
3. number_from_reply: кнопка card:7 важнее текста; «#000042» в подписи; «#999» после пустой строки — нет; «#—» → None.
4. render_card полный: ссылка tg://user?id, вес старт → текущий, зоны yellow→green улучшение / green→red ухудшение / равные / один замер без пометки; статус active, sleeping и «<x>» экранирован; жизни + строка журнала; оплаты, паузы, возвраты — нет данных.
5. render_card без строки state и без замеров: «нет данных», падения нет.
6. /card #000123 от админа: AUDIT раньше SendMessage; SendMessage — chat work_group_id, thread cards_topic_id, parse_mode HTML; actor_id — строка.
7. /card reply на пост бота с подписью GROUP_WHO → карточка в «Карточки».
8. /card от не-админа и из чужого чата → calls == [], connect не вызван.
9. /card без аргумента и без reply → CARD_ASK_ID; /card #000999 нет строки → CARD_NOT_FOUND, AUDIT не выполнен.
10. AUDIT бросает исключение → в тему «Карточки» ничего, ответ CARD_TRY_LATER.
11. callback «card:123» от админа → карточка + AnswerCallbackQuery с CARD_SENT; от чужого → answer без текста, connect не вызван.
12. CARDS_TOPIC_ID пуст → /card: нет SendMessage; WARNING с «CARDS_TOPIC_ID» и без «BOT_DATABASE_URL» при заданном DSN.
Цели: bash tools/check.sh bot. Только CI: всё то же (тестов с БД нет).

## Задетые тесты
Задетых 0 (правило «Т»: ШТАБ прочитал test_access.py, test_outbox.py, test_outbox_group.py, test_render.py — fields(, asdict, __dataclass_fields__ нет; test_bot.py — make_config без новых переменных, /start в группе → calls == []). Упал тест вне test_card.py → не чинить, «тест X вне списка» в ИТОГ, стоп.

## Не ломать (инварианты готовых тестов)
- cards_topic_id: int | None = None — со значением по умолчанию (BotConfig(...) без него в test_access.cfg, test_outbox_group.make_cfg, test_outbox).
- WARNING «карточка выключена» — только имена недостающих переменных; при заданном BOT_DATABASE_URL строки «BOT_DATABASE_URL» в нём нет; фраза «Темы группы не заданы» в нём не встречается.
- Роутер карточки ловит только Command("card") (своё @username — сам Command, как в AH) и callback с data.startswith("card:"). /access_* и «acc:…» доходят до роутера доступа без вызовов Bot API и БД (test_command_from_stranger_ignored: calls == []; test_command_with_other_botname_ignored: только GetMe; test_button_from_stranger_answer_without_text).
- Личные сообщения роутер карточки не ловит.

## 10. Живые проверки (после мержа и выката)
Предусловие: тема «Карточки» создана в Рабочей группе; CARDS_TOPIC_ID задан в .env сервера и в compose (Р0 Автора); бот перезапущен. Аккаунты: А1 — в ACCESS_ADMIN_IDS; А2 прошёл онбординг; А3 — не в whitelist.
1. А1 в любой теме: /card #NNNNNN (номер А2) → карточка только в «Карточки», «Кто» по Р-15.
2. А1 reply /card на пост бота о рефлексии А2 в «Рефлексиях» → карточка в «Карточки».
3. А1: /card без аргумента → просьба уточнить; /card #999999 → «не найден».
4. А3: /card #NNNNNN → бот молчит.
5. Аудит: 2 новые строки (owner, view) — команду psql под audit_reader даёт ШТАБ.
6. Логи бота: нет id, номеров и текста карточки.

## 11. Запреты
- AGENT-BRIEF §3 целиком. Не трогать outbox.py, handlers.py, access*.py, миграции.
- infra/docker-compose.dev.yml и .env.example НЕ трогать: CARDS_TOPIC_ID туда вносит Автор (Р0) перед выкатом.
- Не выбирать checkup_score, checkup_answers, id из measurements_log; не делать RETURNING и SELECT в privacy_audit_log.
- Не делать /card @username, автоудаление и замену карточек, командные кнопки, «📊 Полная Карта изменений».
- Новых зависимостей нет. Тексты — только заглушки.

## 12. Критерии готовности
6 файлов раздела 6; tools/check.sh bot зелёный; 12 тестов раздела 9; готовые тесты не правились; PR по AGENT-BRIEF §10, CI не ждать.

## 13. Оценка
Код ≈ 360 строк (card.py ≈ 170, card_handlers.py ≈ 120, config/app/texts ≈ 70), тесты ≈ 300 строк. Кредиты 500–600. Часы Автора 0,5 (Р0 compose/.env + живые проверки).

## 14. РЕВЬЮЕР: да
Права БД app_bot (B-3), ПДн, аудит 152-ФЗ.
Вопросы РЕВЬЮЕРУ: (1) Есть ли DEFAULT у participant_state.tz в миграции, создавшей таблицу? Если есть — карточка может показать пояс, который участник не выбирал (решил ШТАБ, К-5: показывать как есть) — кандидат в DEFECTS, не блокер. (2) SQL card.py использует только колонки из раздела 7.

## Канон и решения
(а) Использует: 06 §6.1, §6.2, §6.3, §6.4, Fail-safe, YAML invocation; 08 §8.6; 05 §5.3.
(б) Противоречит DECISIONS: 06 §6.2 и YAML invocation «/card @username» — против Р-15 (username не берём). Карточка идёт по Р-15 (К-2). 06 §6.4 «Кто» уже по Р-16 — совпадает.
(в) Правка DOCS — в долг DOCS-пакета ШТАБа (решение ШТАБа 13.11): убрать «/card @username» из 06 §6.2 и из YAML invocation. 06 §6.5 (одна карточка, автоудаление 24 ч) — не противоречие, вне пачки, тоже в долг.
