# bot-access-2 — бот: мелочи ревью Р-2 (#125) + долги #87, #83

Пачка Р-2, после выката 170808e. Область — только apps/bot. Код читать по hash main из docs/STATE.md.
Миграций нет. Режим — Агент (Р1). Источник — docs/reviews/R2-2510.md, раздел «## bot (#125)».

## 1. Цель
Закрыть мелочи ревью бота: тесты на @BotName и чужие решения; кнопки старой заявки снимаются и при
«уже решено»; команда работает только как reply на сообщение бота; ожидание блокировки БД ограничено.
Плюс устаревшие строки в Dockerfile и docstring. Поведение для пользователя не меняется.

## 2. Решения (К-6)
- Т1 тесты @BotName, чужой admin_message_id, чужая кнопка [ШТАБ-тех; R2-2510 bot].
- Т2 при ALREADY_GRANTED / ALREADY_DECIDED снимать кнопки только у сообщения, на которое нажали или
  ответили; NOT_FOUND ничего не правит [ШТАБ 25.10, К-5; канон молчит].
- Т3 команда — только reply на сообщение самого бота; проверка ДО connect [канон 08 §8.4: «через
  reply на конкретное сообщение Бота»; ШТАБ 25.10].
- Т4 lock_timeout = 10s в соединении бота; LockNotAvailable → общий except → TRY_LATER, новых веток
  нет [ШТАБ 25.10, К-5; 10 с — как тест гонки db-access-1 §10].
- Т5 заявка-«сирота»: кода нет, только docstring [ШТАБ 25.10, В1 = «в»: удаление скрыло бы записанную
  заявку, если COMMIT прошёл в БД].
- Т6 decided_at / decided_by при новой заявке не сбрасываются, SQL не меняется, только docstring
  [ШТАБ 25.10, В2 = «а»; app_api читает лишь (tg_user_id, status)].
- Т7 docstring app.py о порядке роутеров [R2-2510 bot]; долги #87 и #83 закрыты выкатом 170808e,
  взамен — две строки (раздел 6, Т7) [ШТАБ 25.10, В3].
- GetMe в подделке: User(id=BOT_ID, …) — id как у Bot из токена теста [решил ПРОЕКТИРОВЩИК, К-5].

## 3. Ветка, коммит, PR
Ветка: feat/bot-access-2. Коммит: «fix(bot): мелочи ревью Р-2 — reply на бота, кнопки при ALREADY_*,
lock_timeout (bot-access-2)». PR: «bot-access-2: мелочи ревью Р-2 (бот) + долги #87, #83».

## 4. Что прочитать (≈ 101 КБ)
AGENT-BRIEF.md 17,1 · docs/STATE.md 20,4 · эта карточка ≈ 9 · apps/bot/bot/access.py 14,4 ·
access_handlers.py 9,5 · app.py 6,5 · config.py 5,9 · apps/bot/Dockerfile 1,0 · apps/bot/tests/test_access.py 17,2.
handlers.py, texts.py, test_bot.py, test_outbox.py, conftest.py — не нужны (не меняются, не задеты).

## 5. Файлы (6)
apps/bot/bot/access.py · apps/bot/bot/access_handlers.py · apps/bot/bot/app.py (docstring) ·
apps/bot/bot/config.py (docstring) · apps/bot/Dockerfile (комментарий) · apps/bot/tests/test_access.py.

## 6. Что сделать
Т2 — access_handlers.after_commit: при note is None, вместо простого return:
    if decision.kind in (access.ALREADY_GRANTED, access.ALREADY_DECIDED):
        try:
            await bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)
        except Exception as exc:  # noqa: BLE001
            logger.warning("access: кнопки старой заявки не сняты (%s)", type(exc).__name__)
    return
message_id — тот, что уже передаётся: кнопка → msg.message_id, команда → reply.message_id.
По коду ALREADY_* никогда не бывает на живой pending-заявке (grant сверяет admin_message_id, deny —
условный UPDATE), поэтому живые кнопки не снимаются.

Т3 — access_handlers._on_command, сразу после блока REPLY_REQUIRED, ДО _now() и _with_conn:
    reply = message.reply_to_message
    if reply.from_user is None or reply.from_user.id != message.bot.id:
        await message.reply(texts.ACCESS_REQUEST_NOT_FOUND)
        return
command_precheck НЕ менять (test_command_precheck не трогать).

Т4 — access.py: константа LOCK_TIMEOUT = "10s" рядом с CONNECT_TIMEOUT; в connect:
    psycopg.AsyncConnection.connect(dsn, autocommit=True, connect_timeout=CONNECT_TIMEOUT,
                                    options=f"-c lock_timeout={LOCK_TIMEOUT}")
Новых SQL нет: порядок SQL в тестах не меняется.

Т5 — docstring access.submit_request, дописать дословно:
«Если UPSERT/COMMIT упал после отправки в тему — в теме остаётся заявка-сирота; удалять её нельзя
(COMMIT мог пройти). Нажатие на сироту даёт NOT_FOUND или ALREADY_DECIDED; при ALREADY_* кнопки снимаются».

Т6 — docstring модуля access.py, дописать: «Строка = последняя заявка + последнее решение: новая заявка
(UPSERT_REQUEST) decided_at / decided_by не сбрасывает. Соединение — lock_timeout 10s: ожидание
блокировки дольше → исключение → TRY_LATER».

Т7 — строки:
- app.py, docstring, абзац «Доступ по промокоду»: «Личный роутер доступа ловит ВСЕ личные сообщения —
  новые обработчики лички подключать ДО него».
- access_handlers.py, docstring: та же строка; в пункт про команды дописать «reply не на сообщение бота →
  REQUEST_NOT_FOUND без обращения к БД»; в пункт «После COMMIT» — «при ALREADY_* снимаются кнопки».
- config.py: «Пусто → доставка outbox выключена, остальное как раньше.» →
  «Пусто → доставка outbox и доступ по промокоду выключены, остальное как раньше.»
- Dockerfile: строку «# BOT_TOKEN, WEBAPP_URL, LOG_LEVEL, BOT_DATABASE_URL — из environment …» заменить на
  «# Переменные — из environment в infra/docker-compose.dev.yml (env_file нет, B-3); полный список — docstring bot/config.py.»

## 7. Задетые тесты (правило «Т») — только apps/bot/tests/test_access.py
- Импорты: из aiogram.methods добавить AnswerCallbackQuery, EditMessageReplyMarkup, GetMe;
  из aiogram.types — CallbackQuery. Константа BOT_ID = 123456 (часть FAKE_TOKEN до «:» = Bot.id).
- _feed(config, update, conn, fail=()): в fake_request после calls.append(method):
  isinstance(method, GetMe) → вернуть User(id=BOT_ID, is_bot=True, first_name="B", username="course_bot");
  type(method) in fail → raise RuntimeError("tg fail"); иначе True.
- _cmd(…, reply_from=BOT_ID): у reply-сообщения from_user=User(id=reply_from, is_bot=True, first_name="B")
  (reply_from=None → без from_user). _group_cmd пробрасывает reply_from. Без этого из-за Т3 упадут
  test_command_deny_already_decided_nothing_to_user и test_command_deny_edits_topic_and_tells_user,
  а test_command_reply_not_request пройдёт, но уже ничего не проверит.
- test_command_deny_already_decided_nothing_to_user: добавить — ровно один EditMessageReplyMarkup
  с message_id == MID и reply_markup is None; проверка «нет EditMessageText» остаётся.
Не задеты: test_bot.py (handlers.py не меняется, у app.py меняется только docstring), conftest.py (там только sys.path),
test_outbox.py (build_dispatcher там подменён, access не импортируется — сверил ШТАБ).
Упал тест вне списка → не чинить, «тест X вне списка» в ИТОГ и стоп.

## 8. Новые тесты (test_access.py)
Хелпер _button(data=f"acc:g:{USER}", user=ADMIN): Update(callback_query=CallbackQuery(id="cb1",
from_user=User(id=user, …), chat_instance="ci", data=data, message=Message(message_id=MID,
chat=Chat(id=GROUP, type="supergroup"), message_thread_id=TOPIC, text="заявка", date=…))).
1. «/access_deny@course_bot» + pending → один EditMessageText, SendMessage пользователю USER.
2. «/access_deny@OtherBot» → в calls только GetMe; conn.log == [].
3. decide GRANT при pending_row(mid=MID + 1) и admin_message_id=MID → ALREADY_DECIDED;
   GRANT_UPDATE не в sqls(); log кончается «commit».
4. Кнопка от user=1 → calls == один AnswerCallbackQuery с text None; conn.log == [].
5. Кнопка, строка ("granted", 0, None, MID) → ровно один EditMessageReplyMarkup (chat_id GROUP, message_id MID,
   reply_markup None), EditMessageText нет, SendMessage нет, AnswerCallbackQuery.text == ACCESS_ALREADY_GRANTED.
6. Кнопка, строки нет (db(None)) → нет EditMessageReplyMarkup и EditMessageText;
   AnswerCallbackQuery.text == ACCESS_REQUEST_NOT_FOUND.
7. Как п.5, но fail={EditMessageReplyMarkup} → AnswerCallbackQuery всё равно ACCESS_ALREADY_GRANTED;
   в caplog WARNING «кнопки старой заявки не сняты»; ошибка не всплывает.
8. Команда, reply_from=ADMIN (не бот) → SendMessage ACCESS_REQUEST_NOT_FOUND; conn.log == [] и conn.closed is False
   (connect не вызывался).
9. connect: monkeypatch psycopg.AsyncConnection.connect = AsyncMock(); asyncio.run(access.connect("postgresql://x/y"));
   await_args == call("postgresql://x/y", autocommit=True, connect_timeout=10, options="-c lock_timeout=10s")
   (по образцу test_outbox.test_connect_timeout_argument).
Быстрые тесты: bash tools/check.sh bot.

## 9. Заметки (кода нет)
- granted + БД недоступна на /start → сейчас «Не удалось отправить заявку» (TRY_LATER); отдельный текст —
  на этапе текстов [R2-2510; канон молчит].
- Анонимный админ: команды приходят от GroupAnonymousBot (не whitelist) → молча игнор; кнопки работают
  (в callback виден настоящий пользователь). Знание Автору: для команд выключить «Оставаться анонимным».
- Смена WORK_GROUP_ID: Т3 исключает ложное совпадение номера сообщения чужого автора; остаток риска
  (UNIQUE admin_message_id) — запись D-? (раздел 13), правка — миграцией позже.

## 10. Запреты
SQL-константы (LOCK, STATE*, FIND_BY_MESSAGE, UPSERT_REQUEST, GRANT_UPDATE, DENY_UPDATE), whitelist,
тему, texts.py, handlers.py не менять. docs/STATE.md и docs/DEFECTS-FOUND.md не трогать.
Новых зависимостей нет. Каждое отличие от карточки — в описании PR.

## 11. Сервер, кредиты, CI
- Сервер (ШТАБ): пересобрать bot; в логе нет WARNING о выключенном доступе; живая проверка: reply
  /access_deny на обычное сообщение в теме → «Заявка не найдена»; нажатие на кнопку старой заявки →
  «Уже решено» и кнопки исчезают; новая заявка проходит (lock_timeout принят сервером БД).
- Оценка кредитов: 260–450 (база 200–350 + 60–100 за test_access.py).
- CI НЕ ЖДАТЬ: после push сразу ИТОГ и конец; gh run watch и опрос проверок запрещены.

## 12. Строки STATE
В PR не вносить. Строку после мержа даёт ШТАБ (раздел 13).

## 13. Для ШТАБА
Чек-лист diff (вместо РЕВЬЮЕРА):
1) команда — только reply на сообщение бота; проверка ДО connect;
2) ALREADY_* снимает кнопки только с сообщения, на которое нажали или ответили;
3) NOT_FOUND ничего не правит;
4) whitelist, тема, SQL-константы не менялись.
Запись D-? для DEFECTS-FOUND.md (следующим docs-пакетом): «D-? access_grants не хранит chat_id заявки:
admin_message_id уникален глобально, а номера сообщений свои в каждом чате. При смене WORK_GROUP_ID
UPSERT новой заявки может упасть на UNIQUE admin_message_id (→ TRY_LATER). Ложное решение закрыто Т3
bot-access-2 (reply только на сообщение бота). Правка — колонка chat_id миграцией, позже».
Строка STATE после мержа: «bot-access-2: мелочи ревью Р-2 (бот) — reply только на бота, кнопки снимаются
при ALREADY_*, lock_timeout 10s; долги #87/#83 закрыты выкатом 170808e».

## 14. РЕВЬЮЕР
Нет. Доступ только сужается (Т3), новых путей выдачи нет; diff проверяет ШТАБ по чек-листу раздела 13.
