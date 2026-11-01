# bot-group-1 — доставка outbox в темы Рабочей группы
Правило К — docs/process/CANON-CHECK.md. Карточка по docs/research/iter2-rest.md (§3, §6 стр. 3, §9 Ш2–Ш3) и коду @70288cb.

## 1. Паспорт
- id: bot-group-1. Заголовок PR: «feat(bot): доставка outbox в темы Рабочей группы (bot-group-1)». Ветка: feat/bot-group-1.
- Режим: Р0+ (бесплатный КОДЕР). Зависит от: db-1 (0011 на сервере). Миграций нет.
- Порядок: раньше clocks-1 и api-refl-1. Строки для группы не должны появиться в outbox раньше маршрута (iter2-rest §6).

## 2. Цель
Воркер outbox доставляет строки двух видов в темы Рабочей группы, а не участнику в личку.
reflection_submitted → тема «Рефлексии» (текст читается из reflections_log по reflection_id).
ladder_day2_alert → тема «Отчёты и активность». Все остальные event_type идут прежним путём лички.

## 3. Решения Автора (дословно)
- Р-15 (01.11) — подпись в группе. Делаем: «Участник #NNNNNN (ID N) → написать», ссылка tg://user?id=N; имя и username не берём. В каноне устарело: 08 §8.5, YAML clickable_name. Источник: карточка bot-group-1.
- Р-14 (19.10) — репо публичный до 0-Б. Поэтому тексты постов — только заглушки.

## 4. Выдержки архитектуры
- 08 §8.2: «Рефлексии — очередь на проверку (дни 6 / 13-M / 13-P)». «Отчёты и активность — … «пришёл, но не отправил» (день 2)».
- 08 §8.3: «Сюда Бот постит отчёты, рефлексии (6 / 13-M / 13-P), алерты».
- 08 §8.5: «кликабельная ссылка на Участника через числовой user_id: tg://user?id=… (username ненадёжен)». Формат перекрыт Р-15.
- 08 §8.6: «Отправка сообщений в конкретную тему — через message_thread_id».
- 03 §3.12: все рефлексии идут Автору в Рабочую группу, тема «Рефлексии». 03 §3.17: «день 2 проблемы → алерт Автору».
- Кнопки тем (08 §8.2) в задачу не входят (Автор, iter2-rest §9 В3).

## 5. ЧТО ПРОЧИТАТЬ (КОДЕР)
apps/bot/bot/outbox.py 20,6; apps/bot/bot/config.py 5,9; apps/bot/bot/texts.py 4,3; apps/bot/bot/app.py 6,7;
apps/bot/tests/test_outbox.py 26,0 (фейки FakeConn/make_bot); infra/docker-compose.dev.yml ≈12 (environment бота);
.env.example 11,9. Чтение КОДЕРА ≈ 87 КБ.

## 6. Файлы
- Изменить: apps/bot/bot/outbox.py, apps/bot/bot/config.py, apps/bot/bot/texts.py, apps/bot/bot/app.py, infra/docker-compose.dev.yml, .env.example.
- Создать: apps/bot/tests/test_outbox_group.py. Удалить: ничего.

## 7. Контракт
Вывод по коду (outbox.py @70288cb) — что бот делает сейчас:
- _deliver не смотрит на event_type, тип есть только в логах. Любая строка идёт путём лички:
  aggregate_id → ADDRESSEE (стёрт → MARK) → expired → нужны text_id и payload_vars.
- Строка нового типа без text_id сегодня уходит в DLQ bad_payload, MARK стоит в той же транзакции.
  Пропуска и ошибки нет, участнику ничего не уходит.
- Почему личка не сломается: в начале _deliver стоит развилка GROUP_ROUTES.get(event_type). При None выполняется прежний код.
  Ветка группы всегда заканчивается MARK или DLQ+MARK. Строка не может висеть и держать очередь: CLAIM берёт самую старую (ORDER BY created_at).
Env и конфиг (config.py) [ПРОЕКТИРОВЩИК-тех, по образцу ACCESS_ADMIN_TOPIC_ID]:
- REFLECTIONS_TOPIC_ID, REPORTS_TOPIC_ID парсятся через _parse_int. Пусто → None, не целое → ConfigError без значения.
- В конец BotConfig добавить поля reflections_topic_id, reports_topic_id со значением None. Добавить GROUP_TOPIC_VARS
  и метод group_missing_vars(): возвращает только имена из двух переменных выше, без значений. Чат — существующий work_group_id.
- WARNING (app.start_outbox_worker, после проверки database_url): отдельная строка «Темы группы не заданы: <имена>».
  В ней только REFLECTIONS_TOPIC_ID / REPORTS_TOPIC_ID, без слов BOT_DATABASE_URL и ACCESS_*. WARNING доступа не менять.
- В run_worker и OutboxWorker добавить в конец параметр config=None. app передаёт его именованным аргументом.
Маршрут (outbox.py): GROUP_ROUTES = {"reflection_submitted": ("reflections_topic_id", REFLECTION), "ladder_day2_alert": ("reports_topic_id", DAY2)}.
SQL (права app_bot: 0009 — pid, tg_user_id, tombstoned_at; 0011 — short_no и 8 колонок reflections_log). Только %s:
- GROUP_ADDRESSEE = "SELECT tg_user_id, short_no, tombstoned_at FROM tg_user_registry WHERE pid = %s"
- REFLECTION = "SELECT pid, stage_no, module_no, day_no, body, created_at FROM reflections_log WHERE id = %s"
Порядок ветки группы (как Ф7 лички):
1. aggregate_id → UUID, иначе bad_aggregate_id.
2. GROUP_ADDRESSEE: строки нет → addressee_not_found; стёрт → MARK без поста и без DLQ (В11).
3. Строка старше 24 ч → expired.
4. Чат или тема маршрута не заданы → group_not_configured [ПРОЕКТИРОВЩИК-тех: строка не висит, личка не блокируется].
5. payload — dict; payload.pid (строка UUID) == pid из aggregate_id, иначе bad_payload.
   Для reflection_submitted: reflection_id — int > 0, но не bool, иначе bad_payload.
6. REFLECTION: строки нет → reflection_not_found; pid строки ≠ pid → bad_payload.
7. Одно send_message(chat_id=work_group_id, message_thread_id=тема, text, parse_mode="HTML", request_timeout=20) → MARK.
Ошибки Telegram — как в личке, но частей нет и прогресс не ведётся:
- retry_after ≤ 25 с суммарно ждём внутри транзакции, больше → LATER; сеть, 5xx и таймаут → NET_RETRY.
- Unauthorized → raise; Forbidden → tg_forbidden; BadRequest → tg_bad_request; NotFound → tg_not_found; прочее → tg_api_error.
Текст (texts.py, заглушки) [ПРОЕКТИРОВЩИК-тех, по образцу ACCESS_ADMIN_*; text_registry не трогаем]:
- GROUP_WHO = "Участник #{num} (ID {tg_id}) → {link}" [Автор против канона → DECISIONS Р-15; 08 §8.5, YAML clickable_name].
  GROUP_WRITE = "написать"; link = <a href="tg://user?id=N">написать</a>.
  num = str(short_no).zfill(6), при None — «—». getChat не вызывать.
- GROUP_DAY2_ALERT = "[заглушка] День 2: пришёл, но не отправил.\n{who}"
- GROUP_REFLECTION = "[заглушка] Рефлексия · этап {s} · модуль {m} · день {d} · {time}\n{who}\n\n{body}"
  time — access.fmt_msk(created_at). body, num и прочие подстановки — через html.escape.
  Body ≤ 2000 символов (CHECK 0011), сообщение одно.
ПДн [указание 5]: текст рефлексии в payload и логи не попадает. В логах только oid, event_type, код.
Никогда не логировать body, pid, tg_user_id, short_no. В DLQ уходит payload как есть, то есть {pid, reflection_id}.

## 8. БД
Миграции нет. Права выданы в 0011 (app_bot SELECT reflections_log, SELECT (short_no) на tg_user_registry). expected_tables.txt не трогаем.

## 9. Тесты (apps/bot/tests/test_outbox_group.py; фейки — по образцу test_outbox.py)
1. ladder_day2_alert: SQL = [CLAIM, GROUP_ADDRESSEE, MARK]. chat_id = WORK_GROUP_ID, thread = REPORTS, parse_mode HTML, есть tg://user?id=, TEXT не вызывается.
2. reflection_submitted: SQL = [CLAIM, GROUP_ADDRESSEE, REFLECTION, MARK], thread = REFLECTIONS. Body «<b>x</b>» экранирован.
3. Темы нет или config=None → DLQ group_not_configured, отправки нет. Стёрт → только MARK. Старше 24 ч → expired.
4. bad_payload: payload не dict; pid ≠ aggregate_id; reflection_id отсутствует / 0 / True / "5"; pid строки reflections_log ≠ pid.
5. reflection_not_found. Forbidden → tg_forbidden. NetworkError → NET_RETRY без MARK. retry_after 3 с → DONE.
6. Логи (caplog DEBUG) без body, PID, TG_ID, short_no. Payload в DLQ == {pid, reflection_id}.
7. Личка цела: send1_test и незнакомый тип при заданных темах → [CLAIM, ADDRESSEE, TEXT, MARK], chat_id = TG_ID.
8. Конфиг: обе темы парсятся. "abc" → ConfigError без значения. group_missing_vars().
   WARNING в start_outbox_worker содержит только имена двух тем, без BOT_DATABASE_URL и ACCESS_.
Проверка: bash tools/check.sh bot. SQL на настоящей БД CI не проверяет — только живая проверка (§10).

## Задетые тесты
Поиск сделан (правило «Т», общие списки): в apps/bot/tests нет тестов, которые сверяли бы список event_type или поля BotConfig целиком.
- test_outbox.py: имена CLAIM/ADDRESSEE/MARK/TEXT/TO_DLQ сохраняются. test_config_database_url вызывает start_outbox_worker с пустым DSN → None до WARNING. Правок нет.
- test_bot.py: BotConfig создаётся с именованными полями, новые поля с умолчанием его не ломают. Правок нет.
- test_access.py: правок нет, проверено ШТАБом. test_render.py: render.py не меняется.
Итог: Задетых 0.

## 10. Живые проверки на сервере (после мержа)
- До выката Автор заносит REFLECTIONS_TOPIC_ID и REPORTS_TOPIC_ID в .env сервера. Значения в репо не пишутся.
- СЕРВЕРНЫЙ: пересобрать и поднять бота. В логе нет WARNING «Темы группы не заданы»; python -m bot.outbox selfcheck → OK.
- Только ladder_day2_alert: одна строка outbox на А1 (event_type ladder_day2_alert, aggregate_id = pid А1, payload {"pid": pid А1}).
  Столбцы INSERT СЕРВЕРНЫЙ берёт из миграции 0001 сам, роль — владелец (у app_bot нет INSERT).
- Ожидание: пост «[заглушка] День 2…» в теме «Отчёты и активность», «написать» открывает А1, sent_at заполнен, outbox_dlq без новых строк.
- Рефлексию живьём не проверяем до api-refl-1: reflections_log неизменяемый.

## 11. Запреты
AGENT-BRIEF §3. Без миграций, GRANT и новых прав. getChat не вызывать. text_registry и render.py не трогать.
Реальные ID и тексты курса в репо не писать. Не логировать body, pid, tg_user_id, short_no. Путь лички не менять.

## 12. Критерии готовности
CI зелёный, тесты §9 есть. Существующие тесты бота не правились. Живая проверка §10 прошла. DLQ лички не изменился.

## 13. Оценка
Р0+: кредиты 0. Часы Автора ≈ 1 (пакет, .env сервера, PR).

## 14. РЕВЬЮЕР: нет
Задача не трогает initData, 18+, согласия (B-2), rate-limit (B-1) и оплату.
Роли и GRANT (B-3) не меняются: используются права 0011, а их РЕВЬЮЕР уже смотрел в #157.
ПДн (текст рефлексии) закрыты тестом 6 и проверкой ШТАБа.

## Канон и решения
(а) Используются: 08 §8.2, §8.3, §8.5, §8.6 и YAML clickable_name; 03 §3.12, §3.17.
(б) Противоречит DECISIONS: 08 §8.5 и YAML clickable_name — перекрыты Р-15.
(в) Правки DOCS (маленький PR в DOCS-course-bot и sync до промпта КОДЕРУ):
- architecture/08-working-group.md, §8.5 · найди: «Формат: Имя (@username · ID 12345) → [написать]; если username нет — просто кликабельное имя.» · замени: «Формат (Р-15, 01.11): Участник #NNNNNN (ID 12345) → [написать]; имя и username не берём.»
- Там же, YAML · найди: «format: "Имя (@username · ID 12345) → [написать]"» · замени: «format: "Участник #NNNNNN (ID 12345) → [написать]"   # Р-15».
Метки К-6: решения с пометкой [ПРОЕКТИРОВЩИК-тех] приняты ШТАБом 01.11 (З2, п.5).
