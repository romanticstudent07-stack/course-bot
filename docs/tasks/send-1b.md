# send-1b — воркер outbox: доставка в Telegram под ролью app_bot

## 1. Паспорт
- id: send-1b · область: бот (apps/bot) + compose, .env.example, SERVER-IRONCLAD для bot · режим: Р1 (Агент Genspark, 22.10).
- Заголовок PR: feat(bot): воркер outbox — доставка в Telegram под app_bot (send-1b)
- Ветка: send-1b · Зависит от: send-1a (начинать ПОСЛЕ мержа send-1a); 0009_app_bot на сервере. Миграций нет.

## 2. Цель
Цикл asyncio в процессе бота: взять строку outbox → адресат по pid → текст (render из send-1a) → Telegram → sent_at;
окончательная ошибка → outbox_dlq. Бот впервые ходит в БД: пользователь coursebot_bot (роль app_bot), DSN BOT_DATABASE_URL.
Писателей outbox пока нет: строки создают тесты и живая проверка (раздел 10).

## 3. Решения Автора (дословно)
- 17.10: «В11 — А (адресат: pid в aggregate_id → tg_user_registry, проверка tombstoned_at в момент отправки)»;
  «В12 — А (текст по text_id собирает бот; SELECT text_registry для app_bot)»;
  «В13 — А (после DLQ — sent_at = now() в той же транзакции; «обработано», не «доставлено»)».
- 20.10 «ОК все рекомендации»: «В23 — А: psycopg[binary]==3.3.6, async, без SQLAlchemy (согласие Автора на новую зависимость
  бота). DSN бота — postgresql://… без +psycopg». «В24 — А: временные сбои (сеть, 5xx) → строка остаётся, повтор с растущей
  паузой; строке > 24 ч от created_at → DLQ expired»; 429 → ждать retry_after, это не ошибка строки; окончательные (бот
  заблокирован, чат не найден, 400 не из-за HTML) → DLQ сразу. «В25 — А: тесты бота на подделке БД; SQL дословно как в 0009».
- ШТАБ 20.10, ПРИНЯТО: «как минимум один раз, дубль только при аварии (kill -9 между ответом Telegram и commit)».
- Р-6: настроек уведомлений и тихих часов нет. Р-11: исходящий к api.telegram.org в проде пойдёт через прокси — сейчас
  не делать; адрес API Telegram не задавать сверх умолчания aiogram.

## 4. Выдержки (Агент docs/architecture/** не читает)
Таблицы (0001_init; iter2-db-3 §4):
    outbox (id bigserial PK, aggregate_id text NOT NULL, event_type text NOT NULL, payload jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(), sent_at timestamptz, tx_id xid8 NOT NULL)  -- sent_at NULL = не обработано
    outbox_dlq (id bigserial PK, original_id bigint NOT NULL, payload jsonb NOT NULL, error text NOT NULL,
                moved_at timestamptz NOT NULL DEFAULT now(), replayed_at timestamptz, replayed_by text)
    tg_user_registry (pid uuid PK, tg_user_id bigint, tombstoned_at timestamptz, …); text_registry (key text PK, text, tone, …)
Права app_bot (миграция 0009) — других нет: SELECT (id, aggregate_id, event_type, payload, created_at, sent_at) и UPDATE (sent_at)
на outbox; INSERT (original_id, payload, error) на outbox_dlq + USAGE outbox_dlq_id_seq; SELECT (pid, tg_user_id, tombstoned_at)
на tg_user_registry; SELECT на text_registry. Нет: INSERT в outbox, SELECT outbox_dlq, RETURNING, SELECT *, tx_id.
Б9 (09-communications.md): контракт к Б15 emit_envelope {text_id, tier, must_deliver, drop_on_overload, coalesce_key, addressee,
payload_vars, parse_mode: HTML}; fail_closed: tier_missing → T1, template_broken → plain_text_send; erased_gate: blocks_all_emission;
retry и dlq — транспорт (Б15), не Б9. Пользовательских тумблеров уведомлений нет (Р123-FINAL).
Конверт send-1b (payload строки; адресат — колонка aggregate_id = str(pid)):
    {"text_id": "<ключ text_registry>", "tier": "T1|T2|T3" (нет или другое → T1), "payload_vars": {имя: str|int|float} (необязательно)}
render (apps/bot/bot/render.py из send-1a): build_html_parts, build_plain_parts, normalize_tier, MissingVarError, TemplateError.

## 5. ЧТО ПРОЧИТАТЬ (Агент) — ≈ 70 КБ
AGENT-BRIEF.md (15); эта карточка (≈ 11); apps/bot/bot/__main__.py, app.py, config.py (≈ 5); apps/bot/bot/render.py (≈ 8);
apps/bot/tests/test_bot.py (≈ 4, стиль: asyncio.run, без pytest-asyncio); apps/bot/requirements.txt, requirements-dev.txt,
Dockerfile (≈ 2); infra/docker-compose.dev.yml (13: шапка и сервис bot); .env.example (11: блок «Роли БД»);
infra/SERVER-IRONCLAD.md (только раздел «Роли БД (B-3)», ≈ 4).

## 6. Файлы (9)
- Создать: apps/bot/bot/outbox.py (≈ 260 строк), apps/bot/tests/test_outbox.py (≈ 260 строк).
- Изменить: apps/bot/bot/config.py, apps/bot/bot/app.py, apps/bot/requirements.txt (+ psycopg[binary]==3.3.6),
  apps/bot/Dockerfile (комментарий о переменных: + BOT_DATABASE_URL), infra/docker-compose.dev.yml, .env.example,
  infra/SERVER-IRONCLAD.md.

## 7. Контракт
config.py: поле database_url: str = "" из BOT_DATABASE_URL (strip). Пусто → доставка выключена (WARNING при старте, остальное
как раньше). Не начинается с "postgresql://" или "postgres://" → ConfigError("BOT_DATABASE_URL: нужен формат postgresql://…
без +psycopg") — значение не печатать. bot_token и database_url — field(repr=False). Docstring: + BOT_DATABASE_URL.
outbox.py — SQL-константы (права 0009; только параметры %s, литералов адреса нет — Н1):
    CLAIM = "SELECT id, aggregate_id, event_type, payload, created_at FROM outbox WHERE sent_at IS NULL ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED"
    ADDRESSEE = "SELECT tg_user_id, tombstoned_at FROM tg_user_registry WHERE pid = %s"
    TEXT = "SELECT text FROM text_registry WHERE key = %s"
    MARK = "UPDATE outbox SET sent_at = now() WHERE id = %s AND sent_at IS NULL"
    TO_DLQ = "INSERT INTO outbox_dlq (original_id, payload, error) VALUES (%s, %s, %s)"
Отличие от 0009 §7 — только LIMIT 1 вместо :n и created_at в списке (право есть) для expired.
Одна строка = одна короткая транзакция (psycopg.AsyncConnection, autocommit=True + async with conn.transaction()):
1. CLAIM. Строки нет → пауза 2 с (прерывается stop) и снова.
2. now(UTC) − created_at > 24 ч → DLQ "expired" (без отправки).
3. payload не dict, text_id не непустая str или payload_vars не dict → DLQ "bad_payload".
4. uuid.UUID(aggregate_id) в Python; ошибка → DLQ "bad_aggregate_id" (до любого SQL с адресом).
5. ADDRESSEE с параметром uuid.UUID: строки нет → DLQ "addressee_not_found"; tombstoned_at не NULL → MARK без DLQ и без
   отправки, лог «skipped: tombstoned» (Н2, В11).
6. TEXT: нет → DLQ "text_not_found". build_html_parts: MissingVarError → DLQ "missing_var"; TemplateError → build_plain_parts.
7. Части по очереди: bot.send_message(chat_id=tg_user_id, text=часть, parse_mode="HTML" (для plain — None), request_timeout=20).
8. Все части ушли → MARK → commit. rowcount MARK = 0 → WARNING, commit.
DLQ = TO_DLQ (payload как есть через psycopg.types.json.Jsonb, error — код) + MARK в той же транзакции (В13).
Ошибки Telegram (aiogram.exceptions):
- TelegramRetryAfter → ждать retry_after с (прерывается stop), повторить ту же часть; не ошибка строки, без счётчика.
- TelegramNetworkError, TelegramServerError, asyncio.TimeoutError → выйти из транзакции без MARK (строка остаётся); общая пауза
  1, 2, 4 … до 300 с, сброс после успеха. В памяти {outbox_id: число отправленных частей} — повтор идёт со следующей части.
- TelegramBadRequest с "can't parse entities" (без учёта регистра) → один раз build_plain_parts, отправить все plain-части с первой (WARNING).
- TelegramForbiddenError → "tg_forbidden"; TelegramNotFound → "tg_not_found"; прочий TelegramBadRequest → "tg_bad_request";
  прочий TelegramAPIError → "tg_api_error". В error и в логе — только код, без текста ответа Telegram.
- TelegramUnauthorizedError → ERROR, воркер завершается (polling упадёт так же; обработка уже в __main__.py).
БД: psycopg.OperationalError → WARNING только с именем класса (без DSN и текста), закрыть соединение, пауза 5 с, переподключиться.
Остановка: stop проверяется перед CLAIM; текущая строка дописывается (все части + MARK), новая не берётся; паузы прерываются stop.
Логи: только outbox id, event_type, код ошибки, число частей. НИКОГДА: tg_user_id, pid, текст, payload_vars, DSN, BOT_TOKEN.
Docstring outbox.py: SQL и права 0009; «sent_at = обработано, не доставлено (В13)»; «как минимум один раз: дубль только при аварии
(kill -9, падение БД) между ответом Telegram и commit; при SIGTERM дубля нет»; «SQL бота CI на настоящей БД не проверяет —
только живая проверка на сервере»; Р-11.
Самопроверка python -m bot.outbox selfcheck (без секретов и ID): печатает session_user, current_user,
pg_has_role(session_user, 'app_bot', 'MEMBER'); в отдельных транзакциях с откатом SELECT pid FROM consent_events LIMIT 1 и
SELECT * FROM outbox LIMIT 1 → ждёт psycopg.errors.InsufficientPrivilege («denied OK»), иначе «FAIL». Код 0 — только всё OK
и есть членство; пустой BOT_DATABASE_URL → сообщение и код 1.
app.py: функция start_outbox_worker(bot, config, stop) → asyncio.Task | None (None, если DSN пуст). run(): задача стартует ДО
wait_until_no_webhook; в finally: stop.set(), ждать задачу до 25 с (потом cancel), затем bot.session.close(). SIGTERM штатно
останавливает start_polling → finally. Docstring app.py: воркер outbox. Свою сессию и прокси (AiohttpSession) не делать.
docker-compose.dev.yml, сервис bot: в environment — BOT_DATABASE_URL: ${BOT_DATABASE_URL}; в depends_on + db: condition:
service_healthy (api оставить); stop_grace_period: 30s; комментарий над bot и пункт шапки: «bot ходит в БД только по
BOT_DATABASE_URL (coursebot_bot, роль app_bot); пусто → доставка выключена». Без env_file; лимит памяти не менять.
.env.example, блок «Роли БД»: BOT_DATABASE_URL= с комментарием (coursebot_bot, роль app_bot;
postgresql://<пользователь>:<пароль>@db:5432/<POSTGRES_DB> — БЕЗ +psycopg).
SERVER-IRONCLAD.md, «Роли БД (B-3)»: + CREATE ROLE coursebot_bot LOGIN IN ROLE app_bot; и \password coursebot_bot (app_bot — 0009);
строка «— | bot | БД не использует» → «BOT_DATABASE_URL | bot | coursebot_bot (роль app_bot)»; + DC exec bot env | cut -d= -f1 | sort.

## 8. БД: миграций нет, прав сверх 0009 не нужно. Понадобилось новое право → СТОП, вопрос ШТАБу в PR.

## 9. Тесты — apps/bot/tests/test_outbox.py (подделки, asyncio.run)
FakeConn: execute(sql, params) пишет пару в журнал и отдаёт заданные ответы; transaction() — контекст, журнал begin/commit/rollback.
Бот — SimpleNamespace(send_message=AsyncMock(...)). Исключения aiogram — с method=SendMessage(chat_id=1, text="x"). Время и паузы подменяются.
1. Успех: SQL по порядку CLAIM, ADDRESSEE, TEXT, MARK; параметр ADDRESSEE — uuid.UUID; parse_mode="HTML"; commit.
2. Не uuid → TO_DLQ "bad_aggregate_id" + MARK; ADDRESSEE и send не вызваны (Н1).
3. tombstoned_at задан → MARK; TO_DLQ и send не вызваны (Н2).
4. Коды DLQ: адресата нет → "addressee_not_found"; текста нет → "text_not_found"; нет переменной → "missing_var"; нет text_id → "bad_payload".
5. created_at старше 24 ч → "expired", send не вызван.
6. TelegramRetryAfter(retry_after=3), затем успех → пауза 3, один MARK, без DLQ.
7. TelegramNetworkError дважды, затем успех → ни MARK, ни DLQ до успеха; паузы 1, 2; затем MARK.
8. Текст на 3 части: сеть падает на 2-й, затем успех → часть 1 отправлена ровно один раз.
9. "can't parse entities" → повтор с parse_mode None, затем MARK.
10. TelegramForbiddenError → "tg_forbidden"; TelegramBadRequest "chat not found" → "tg_bad_request"; в error нет текста Telegram.
11. stop выставлен во время отправки → строка дописана (MARK), второго CLAIM нет.
12. caplog в тестах 1–10: нет tg_user_id, pid, текста сообщения.
13. config: пустой BOT_DATABASE_URL → start_outbox_worker → None; "postgresql+psycopg://…" → ConfigError без значения; repr(BotConfig)
    без токена и DSN.
14. selfcheck на FakeConn: оба SELECT → InsufficientPrivilege → код 0; один SELECT прошёл → код 1.
Агент: cd apps/bot && pip install -r requirements-dev.txt && python -m pytest -q. CI: bot, docker (bot).
SQL бота CI на настоящей БД НЕ проверяет — только раздел 10.

## 10. Сервер после мержа (задание ШТАБа). DC = docker compose --env-file .env -f infra/docker-compose.dev.yml
Первый выкат bot после melochi-2: пересобрать только bot (--no-deps); api, projector, migrate не трогать; миграций нет.
1. cd ~/course-bot && git pull. Пароль: openssl rand -hex 24 (в чат не писать).
2. DC exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' → CREATE ROLE coursebot_bot LOGIN IN ROLE app_bot; →
   \password coursebot_bot → SELECT rolcanlogin FROM pg_roles WHERE rolname = 'app_bot'; (f, Н4) →
   SELECT pg_has_role('coursebot_bot', 'app_bot', 'MEMBER'); (t).
3. nano .env: BOT_DATABASE_URL=postgresql://coursebot_bot:<пароль>@db:5432/<POSTGRES_DB>.
4. DC up -d --build --no-deps bot; DC logs --tail 30 bot → воркер стартовал, ошибок нет;
   DC exec bot env | cut -d= -f1 | sort → есть BOT_DATABASE_URL, нет POSTGRES_*.
5. DC exec bot python -m bot.outbox selfcheck → session_user = current_user = coursebot_bot, членство в app_bot t,
   consent_events и outbox SELECT * → denied OK, код 0 (Н3, Н6).
6. psql владельца (как в п. 2): BEGIN; затем по одной строке:
    INSERT INTO outbox (aggregate_id, event_type, payload, tx_id) VALUES ((SELECT pid::text FROM tg_user_registry WHERE tg_user_id = <TG_ID_АВТОРА> AND tombstoned_at IS NULL), 'send1_test', jsonb_build_object('text_id', (SELECT key FROM text_registry WHERE text NOT LIKE '%{%' ORDER BY key LIMIT 1), 'tier', 'T2'), pg_current_xact_id());
    INSERT INTO outbox (aggregate_id, event_type, payload, tx_id) VALUES ('not-a-uuid', 'send1_test', '{"text_id": "send1.none"}', pg_current_xact_id());
    INSERT INTO outbox (aggregate_id, event_type, payload, tx_id) VALUES ((SELECT pid::text FROM tg_user_registry WHERE tg_user_id = <TG_ID_АВТОРА> AND tombstoned_at IS NULL), 'send1_test', '{"text_id": "send1.no_such_key"}', pg_current_xact_id());
   Если SELECT count(*) FROM tg_user_registry WHERE tombstoned_at IS NOT NULL; > 0 — четвёртый INSERT, как третий, но с
   (SELECT pid::text FROM tg_user_registry WHERE tombstoned_at IS NOT NULL LIMIT 1) и text_id из первого; иначе «tombstone: не проверено».
   COMMIT;  Нет pid Автора → ошибка NOT NULL, транзакция откатится: сначала first-launch в Mini App.
7. ≤ 10 с: Автору пришло ровно 1 сообщение (заглушка). SELECT id, sent_at IS NOT NULL FROM outbox WHERE event_type = 'send1_test'
   ORDER BY id; → все t. SELECT original_id, error FROM outbox_dlq ORDER BY id DESC LIMIT 3; → bad_aggregate_id, text_not_found
   (строки tombstone в DLQ нет, сообщения нет).
8. DC logs bot | grep -c '<TG_ID_АВТОРА>' → 0 (в чат — только число). DC restart bot; 30 с → нового сообщения нет.
9. DC ps: 7/7 Up, 5 healthy; таблиц 15; alembic current 0009_app_bot. Тестовые строки не удалять.
   Откат: в .env BOT_DATABASE_URL= (пусто) → DC up -d --no-deps --force-recreate bot → доставка выключена.

## 11. Запреты
- Не трогать apps/api/**, render.py (нашёл ошибку — описать в PR), docs/STATE.md, docs/DEFECTS-FOUND.md, docs/architecture/**, .github/**, .env.
- Без миграций и новых прав; из новых зависимостей — только psycopg[binary]==3.3.6 (без SQLAlchemy); без env_file; память не поднимать.
- Не хардкодить адрес API Telegram, DSN, хосты; без своей сессии и прокси (Р-11). Без тихих часов и настроек уведомлений (Р-6).
- Без писателей outbox, plural_ru, SELECT *, RETURNING, литералов адреса в SQL.
- Не логировать tg_user_id, pid, тексты, payload_vars, DSN, BOT_TOKEN. Запреты AGENT-BRIEF.md, раздел 3.
- Стоп: permission denied, нужно право вне 0009, та же ошибка CI дважды → стоп, описание в PR.

## 12. Готовность
Раздел 7 выполнен; тесты 1–14; pytest bot зелёный; CI 7/7; РЕВЬЮЕР — 0 блокирующих; описание PR по AGENT-BRIEF §10,
«Команды для Автора на IRONCLAD» = раздел 10.

## 13. Оценка
Агент ≈ 900 кредитов (диапазон 700–1 200: 9 файлов, ≈ 520 строк, 1–2 круга CI). Автор ≈ 1,5 ч (промпт, PR, ревью, сервер).

## 14. РЕВЬЮЕР: да — первый вход бота в БД под ролью app_bot (B-3), новый секрет BOT_DATABASE_URL, логи без ПДн, tombstone-гейт.
