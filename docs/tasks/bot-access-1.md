# bot-access-1 — бот: промокод, заявка в админ-тему, кнопки, /access_grant и /access_deny

Пачка Р-2, карточка (б) из 4. Начинать ПОСЛЕ мержа db-access-1. Параллельно с api-access-1.

## 1. Цель
Пользователь без доступа пишет боту кодовое слово → заявка уходит в админ-тему Рабочей группы →
Автор решает кнопкой или командой. Попытки работают как ввод пароля. После «Выдать» бот пишет
пользователю, что можно продолжать, и даёт кнопку Mini App.

## 2. Решения (К-6)
- Поток Р-2 [STATE Р-2; R-2026-10-1 Р-2 п.1–8].
- Команды /access_grant и /access_deny — reply на заявку в админ-теме [Автор 23.10, ответ 1;
  B17-admin-panel-patch «command = /{domain}_{action}»; 08 §8.4].
- Без reply не выполнять, просить reply; не из whitelist — игнор + лог [08 Fail-safe].
- Кликабельное имя «Имя (@username · ID 12345) → [написать]», ссылка tg://user?id [08 §8.5].
- Слово в БД не хранить, только в сообщении темы [Автор, ответ 3].
- Попытки, пауза, ответы — по ответу 4 Автора, пункты а–ж [Автор 23.10, канон молчит].
- Время паузы — МСК с пометкой «МСК» [решил ШТАБ, К-5: у не-участника нет tz].
- Whitelist — env со списком ID; пусто → функция выключена + WARNING [Автор, ответ 7; 08 Fail-safe; 17/17-05].
- Тексты — заглушки на «Вы» в bot/texts.py [Автор, ответ 2].
- psycopg, соединение на запрос, без новых зависимостей; FOR UPDATE против гонок [ШТАБ 23.10].
- Ключ advisory-блокировки со своей приставкой 'access_grants:' [решил ШТАБ, К-5: другие advisory-блокировки
  проекта не проверены].
- Тесты бота — на подделке соединения; гонка с настоящей БД — в db-access-1 §10 [решил ШТАБ, К-5;
  по коду: test_outbox.py — «без сети и Postgres», FakeConn].
- Имена ACCESS_*, длина слова до 64 [решил ПРОЕКТИРОВЩИК, К-5; принято ШТАБом].

## 3. Ветка, коммит, PR
Ветка: feat/bot-access-1. Коммит: «feat(bot): доступ по промокоду и команды Панели (bot-access-1)».
PR: «bot-access-1: промокод → админ-тема → /access_grant, /access_deny (Р-2)».

## 4. Что прочитать (≈ 125 КБ)
AGENT-BRIEF.md 17,1 · docs/STATE.md 20,6 · эта карточка ≈ 10 · apps/bot/bot/app.py 5,4 · handlers.py 2,6 ·
config.py 2,6 · texts.py 1,5 · outbox.py ≈ 20 (образец psycopg async и SQL с %s) ·
apps/bot/tests/test_bot.py и test_outbox.py (образец тестов и подделки FakeConn) · apps/bot/tests/conftest.py ·
infra/docker-compose.dev.yml ≈ 12 (environment бота) · .env.example ≈ 9.
Настоящего Postgres в тестах бота нет и не нужно: всё проверяется на подделке (раздел 11).

## 5. Файлы
- apps/bot/bot/config.py — новые настройки;
- новый apps/bot/bot/access.py — SQL, переходы состояний, чистые функции;
- новый apps/bot/bot/access_handlers.py — роутер: личка, кнопки, команды;
- handlers.py — /start с проверкой доступа; app.py — подключить роутер; texts.py — заглушки;
- infra/docker-compose.dev.yml — environment бота; .env.example — описание переменных;
- новый apps/bot/tests/test_access.py; docs/STATE.md (раздел 12).

## 6. Настройки (config.py + строки environment бота в compose + .env.example — В ЭТОЙ ЖЕ задаче)
    WORK_GROUP_ID          id Рабочей группы (в .env.example уже есть; в environment бота добавить — сейчас её там нет)
    ACCESS_ADMIN_TOPIC_ID  message_thread_id админ-темы
    ACCESS_ADMIN_IDS       whitelist: tg id через запятую (временно до Б17)
    ACCESS_MAX_DENIES      ${ACCESS_MAX_DENIES:-5}, целое ≥ 1
    ACCESS_LOCK_HOURS      ${ACCESS_LOCK_HOURS:-24}, целое ≥ 1
- access_enabled = BOT_DATABASE_URL и три первые настройки заданы.
- Не хватает чего-то → один WARNING при старте с ИМЕНАМИ переменных, без значений. В этом режиме /start
  работает как сейчас (приветствие + кнопка), заявок нет; новых людей тогда не пустит гейт API.
- Неверный формат числа → ConfigError без значения.

## 7. Состояния (access.py, чистая функция; «сейчас» передаётся параметром, UTC)
Текст в личке (не команда) от пользователя:
- функция выключена или granted → ничего не делать (как сейчас);
- pending → PENDING («заявка на проверке, дождитесь ответа»); в тему ничего; попытка не тратится;
- locked_until > сейчас → LOCKED с датой; в тему ничего;
- locked_until ≤ сейчас → deny_count = 0, locked_until = NULL, дальше как новая заявка;
- нет строки или denied → новая заявка (раздел 8), пользователю REQUEST_SENT;
- слово после strip пустое или длиннее 64 → SEND_TEXT («отправьте кодовое слово текстом»), заявки нет.
Прочее:
- Не текст (стикер, фото, файл и т.п.) и команды, кроме /start, у пользователя без доступа → SEND_TEXT.
- /start: выключено или granted → как сейчас (меню-кнопка + приветствие). Иначе по строке:
  pending → PENDING, пауза → LOCKED, иначе → PROMPT («введите промокод»). /start — не заявка и не попытка.
- Меню-кнопку Mini App ставить только при granted или выключенной функции.

## 8. Новая заявка (одна транзакция psycopg)
    SELECT pg_advisory_xact_lock(hashtextextended('access_grants:' || %s::text, 0))   -- tg_user_id
    SELECT … FROM access_grants WHERE tg_user_id = %s FOR UPDATE
    перепроверить раздел 7 (пока ждали блокировку, доступ могли выдать)
    отправить в тему (chat_id = WORK_GROUP_ID, message_thread_id = ACCESS_ADMIN_TOPIC_ID,
      parse_mode="HTML") текст ADMIN_REQUEST + кнопки [Выдать доступ] / [Запретить]
    INSERT … (status 'pending', admin_message_id, requested_at, created_via 'bot_promo')
      ON CONFLICT (tg_user_id) DO UPDATE SET status, admin_message_id, requested_at,
      deny_count, locked_until, updated_at = now()
    COMMIT; затем пользователю REQUEST_SENT
- Advisory-блокировка нужна, потому что строки ещё может не быть и FOR UPDATE нечего держать.
  Приставка 'access_grants:' — чтобы ключ не совпал с чужими блокировками.
- Отправка в тему не удалась → ROLLBACK, пользователю TRY_LATER, лог без слова.
- Слово, имя и username экранировать html.escape.
- Формат темы (08 §8.5): слово в <code>, затем «Имя (@username · ID N) → написать» со ссылкой tg://user?id=N.
- callback_data: «acc:g:<tg_user_id>» / «acc:d:<tg_user_id>».

## 9. Решение Автора (кнопка или команда; одна функция decide; одна транзакция)
Кнопки:
- принимать, только если callback.message.chat.id == WORK_GROUP_ID, message_thread_id == ACCESS_ADMIN_TOPIC_ID
  и from_user.id в ACCESS_ADMIN_IDS;
- иначе answerCallbackQuery без текста + лог (без слова).
Команды /access_grant и /access_deny (Command, учитывает @BotName):
- только из темы и от whitelist, иначе игнор + лог;
- без reply → REPLY_REQUIRED («ответьте командой на сообщение-заявку»);
- reply не на заявку бота → REQUEST_NOT_FOUND.
Поиск пользователя:
- команда — по admin_message_id = reply_to_message.message_id;
- кнопка — по tg_user_id из callback_data + сверка admin_message_id == message_id.
В транзакции:
    SELECT … FROM access_grants WHERE tg_user_id = %s FOR UPDATE
    grant: status = granted (из pending, denied или паузы), deny_count = 0, locked_until = NULL,
           decided_at, decided_by, updated_at; уже granted → «доступ уже выдан», без изменений
    deny:  условный UPDATE … WHERE tg_user_id = %s AND status = 'pending' AND admin_message_id = %s;
           0 строк → «уже решено», без изменений;
           deny_count + 1, status = denied, decided_*; deny_count ≥ ACCESS_MAX_DENIES →
           locked_until = сейчас + ACCESS_LOCK_HOURS
    COMMIT
После COMMIT:
- сообщение заявки в теме: дописать итог (заглушка «Выдан доступ» / «Запрещено k из MAX» + время МСК)
  и снять кнопки (reply_markup=None); answerCallbackQuery;
- пользователю: grant → GRANTED + кнопка Mini App (webapp_keyboard, если webapp_enabled);
  deny → DENIED_RETRY(N осталось), при N = 1 — DENIED_LAST, при паузе — LOCKED(дата «дд.мм.гггг чч:мм МСК»,
  ZoneInfo("Europe/Moscow") явно).
Ошибки Telegram после COMMIT только логировать: решение уже записано.

## 10. Тексты-заглушки (texts.py; комментарий-ключ bot.access_*; «Вы»)
PROMPT «Введите, пожалуйста, промокод.» · REQUEST_SENT «Спасибо! Заявка отправлена, дождитесь ответа.» ·
PENDING «Ваша заявка на проверке, дождитесь ответа.» · SEND_TEXT «Отправьте кодовое слово текстом.» ·
GRANTED «Доступ открыт, можно продолжать.» · DENIED_RETRY «Код не подошёл. Попробуйте ещё раз. Осталось попыток: {n}.» ·
DENIED_LAST «Код не подошёл. Осталась 1 попытка.» · LOCKED «Попытки закончились. Попробуйте после {until}.» ·
TRY_LATER «Не удалось отправить заявку, попробуйте позже.» · ADMIN_REQUEST, REPLY_REQUIRED, REQUEST_NOT_FOUND,
кнопки «Выдать доступ» / «Запретить» — короткие заглушки.

## 11. Тесты (test_access.py; без сети и Postgres, по образцу FakeConn из test_outbox.py)
Чистые функции:
- переходы раздела 7: pending, пауза, конец паузы со сбросом, слово пустое или 65 символов, не текст;
- 4-й отказ → осталось 1; 5-й → пауза ровно на ACCESS_LOCK_HOURS; grant в паузе сбрасывает счётчик;
- формат даты МСК; html.escape имени и слова;
- фильтры: чужой чат, чужая тема, не whitelist → ничего; команда без reply → REPLY_REQUIRED;
- config: пусто → выключено + WARNING без значений; кривое число → ConfigError.
На подделке соединения (записывает SQL и параметры, отдаёт заданные строки):
- decide идёт в одной транзакции: SELECT … FOR UPDATE и UPDATE между началом и COMMIT;
  при исключении — откат, COMMIT нет;
- записанный SQL decide содержит «FOR UPDATE»;
- новая заявка: первый SQL — pg_advisory_xact_lock с 'access_grants:', затем SELECT … FOR UPDATE;
- deny: SQL UPDATE содержит условия status = 'pending' и admin_message_id; подделка возвращает 0 строк →
  результат «уже решено», пользователю ничего не уходит, сообщение темы не правится;
- deny при status = pending и совпавшем admin_message_id → deny_count + 1, ответ DENIED_RETRY;
- повторный grant по строке granted → «доступ уже выдан», UPDATE не выполняется;
- слово не попадает ни в параметры SQL, ни в лог (caplog).
Гонка двух соединений с настоящей БД — в db-access-1 §10 (CI с Postgres); здесь её не делать.
Быстрые тесты: bash tools/check.sh bot.

## 12. Строки STATE (внести в PR)
- bot-access-1 (Р-2, б): промокод → заявка в админ-теме → кнопки и /access_grant, /access_deny;
  5 отказов → пауза 24 ч (настройки). Новые env бота: WORK_GROUP_ID, ACCESS_ADMIN_TOPIC_ID, ACCESS_ADMIN_IDS,
  ACCESS_MAX_DENIES, ACCESS_LOCK_HOURS. Без них функция выключена.

## 13. Сервер, кредиты, CI
- Сервер (после 25.10, ШТАБ):
  - заполнить 3 переменные в .env; пересоздать bot вместе с api (api-access-1);
  - в логе бота нет WARNING о выключенной функции;
  - живая проверка: новый аккаунт → /start → промокод → заявка в теме → «Запретить» → «осталось 4» →
    «Выдать» → Mini App → онбординг до pid.
- Вопрос Автору (задаст ШТАБ перед выкатом): есть ли Telegram-аккаунт, который ещё не участник?
- Оценка кредитов: 700–1 100.
- CI НЕ ЖДАТЬ: после push сразу ИТОГ и конец; gh run watch и опрос проверок запрещены.

## 14. РЕВЬЮЕР
Да (доступ к онбордингу и права БД). Проверить:
- решать может только whitelist и только из темы;
- гонки закрыты FOR UPDATE и условным UPDATE;
- слово не пишется в БД и в лог;
- HTML экранирован;
- при выключенной функции заявок нет.
РЕВЬЮЕР — после 25.10 (новые кредиты), до выката.
