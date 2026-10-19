# STATE — живое состояние course-bot
Обновлено: 19.10.2026 (#103 iter2-api-2b выкачен 0817dc3; решения Р-1…Р-14 — docs/decisions/R-2026-10-1.md и -2.md). До 90 строк. Секретов, реальных ID и IP здесь нет.
Кто обновляет: ШТАБ даёт строки → они идут первым файлом пакета следующей задачи.
Подробности закрытых задач — docs/HISTORY.md. Прежний STATE целиком (до сжатия 18.10, дословно: выкаты сервера до 0008, «Смержено» #49–#96, строки учёта кредитов) — docs/history/STATE-a5ef1d7.md. КОДЕРАМ HISTORY и снимок не давать.
Правила ШТАБа — docs/process/SHTAB.md (часть 1) + docs/process/SHTAB-2.md (часть 2), читать ОБА.
Процессные решения (роли, РЕВЬЮЕР, окна чатов, терминал, rulesets main, форки, LF, expected_tables.txt, миграции по одной) — в SHTAB.md, SHTAB-2.md, DESIGNER.md, README.md.
## Сейчас
- main = 0817dc3; сервер ✅ 0817dc3 (19.10), alembic 0009_app_bot, 15 таблиц, 7/7 Up, 5 healthy; DAY_TEST_ENTRY_ENABLED в api = false (выкл.); PROJECTOR_VERSION = 2; очередь — docs-r-1 → docs-r-2 → ПРОЕКТИРОВЩИК send-1 и life-ops → Агент 22–24.10. Сервер IRONCLAD работает только с main.
- Выкаты: 19.10 — #101 (пересобраны api и projector), #102 (без сборки), #103 (api+projector вместе, новый kind day_report_submitted); выкаты 54ca133 и раньше — docs/HISTORY.md и снимок docs/history/STATE-a5ef1d7.md. Образ migrate — 54ca133 (перед следующей миграцией или texts load — build migrate); bot не пересобирался с melochi-2 (комментарий apps/bot/Dockerfile #87 и docstring #83 — при следующем выкате bot).
- Норма сервера: 7/7 Up, 5 healthy (db, redis, garage, api, miniapp), healthcheck нет у bot и projector; curl / 200, /healthz 200, /miniapp/v1/onboarding/status 401. Роли: api — coursebot_api, projector — coursebot_projector, alembic и texts load — владелец (только DC --profile tools run --rm --no-deps migrate); env_file нет ни у одного сервиса; repr/str Settings без DSN. Перед каждой миграцией — бэкап before-000N и DC --profile tools build migrate.
- Проектор на сервере проверяется по логам (Traceback 0, WARNING 0); projector once рядом с run запрещён (infra/SERVER-IRONCLAD.md:146).
- В БД (18.10): tg_user_registry 2, consent_events 4, participant_events 2, participant_state 2, day_marks 0; второй участник — живая проверка Автора 15.10 (miniapp-fix).
- ЗАКРЫТО: И1 (1d, B-1, 1e-1, 1e-2, 1e-2b), projector, returning, ЭТАП B-3, miniapp-fix, melochi-2, DOCS D-2/3/8/12, D-11/16/21, D-22; И2 БД: iter2-db-1/2/3 (0007–0009); И2 API: iter2-api-1 ✅ 54ca133, iter2-api-2a ✅ e5de293. Подробно — снимок docs/history/STATE-a5ef1d7.md.
- DEFECTS-FOUND.md < 25 000 байт (правило А); DEFECTS-ARCHIVE.md КОДЕРАМ кода не давать.
- Бэкапы before-0004 ✅ (02.10), before-0005 ✅ (05.10), before-0006 ✅ (09.10), before-b3d ✅ (14.10), before-0007 ✅ (17.10, 36771 Б), before-0008 ✅ (17.10, 39592 Б), before-0009 ✅ (18.10, 41722 Б). Downgrade ниже 0004 запрещён (стирает журнал согласий).
- Процесс: лимиты чтения — КОДЕР ≈ 130–140 КБ; ПРОЕКТИРОВЩИК ПОЛНОЕ/КАРТОЧКИ 170 КБ, ИССЛЕДОВАНИЕ 200 КБ (решение Автора 19.10). SHTAB.md 3-Б: одна карточка = одна область, задачу режем, чтение не урезаем; DESIGNER.md «Бюджет окна». Файл восстановления ШТАБа — SHTAB-CONTEXT-CHAT.txt.
- Живые проверки 02.10: 403 «младше 18» (ничего не создал) и 429 (числа — DEFECTS-ARCHIVE.md, D-7, D-10). Mini App после пересборки — закрыть и открыть заново (кэш Telegram).
- Codespaces проверен 28.09: selftest unpack, hooksPath=.githooks, Python 3.12.14, Node v20.20.2, check.sh зелёный.
- Репо ПУБЛИЧНЫЙ до 0-Б (обычный AI Chat приватные репо не читает); после 0-Б — приватный, файлы в чаты вставлять вручную.
## Смержено (подробно — docs/HISTORY.md и снимок docs/history/STATE-a5ef1d7.md)
- Сервер ✅ после каждого мержа ниже (только docs — только pull).
- #22–#43 — docs/HISTORY.md; #49–#96 — снимок; #97 iter2-db-3 (0009), #98 research + карточки iter2-api, #99 сжатие STATE, #100 iter2-api-1 — выкат ✅ 54ca133 (18.10).
- #101 iter2-api-2a — POST day/test-enter (флаг), PUT day/marks, замок participant:pid, проектор v2 (day_entered, SAVEPOINT, граница 32767); выкачено 19.10 (api + projector).
- #102 limits-flag-env — DAY_TEST_ENTRY_ENABLED в environment api (дефолт false) и .env.example; лимиты чтения DESIGNER.md; выкачено 19.10 без сборки.
- #101 iter2-api-2a, #102 limits-flag-env, #103 iter2-api-2b (POST /miniapp/v1/day/report/submit + projector day_report_submitted) — выкачены 19.10.
## Решения Автора (процессные — в правилах, см. шапку)
- Бот — long polling. Cloudflare Tunnel — нет. Прод — российский VPS (фаворит Timeweb Cloud), туннель дом→VPS autossh/WireGuard.
- Память: сумма лимитов ≤ 2 ГБ; сейчас 1920 МБ (api 384, db 384, bot 512, garage 192, miniapp 128, projector 128, redis 64; migrate 128 одноразово), реально ~362 МБ (06.10).
- Бэкап БД на сервере: ~/bin/coursebot-db-backup.sh, cron 03:30 MSK, 14 дней; перед каждой миграцией — ручной pg_dump -Fc.
- initData: TTL 24 ч, допуск «из будущего» 60 с; 401 TG_INIT_MISSING / TG_INIT_INVALID; пустой BOT_TOKEN → 503 SERVICE_MISCONFIGURED. session_jwt — D-9, отложено.
- first-launch: SEAM-1; tg_user_id только из initData; 18+ до БД (Europe/Moscow); дату рождения не храним; повтор → 201 тот же {pid, short_no}; БД недоступна → 503. Отказ «младше 18» не сохраняется (Р47).
- participant_state пишет только проектор. lifecycle_phase — D-11 (FSM И2, 6А). Тексты курса в репо — только заглушки до 0-Б.
- И1: согласия до pid (D-10), обязательны C0 и C1; оферта — вместе с оплатой; оплата вне порядка ADD3 до решения противоречия по оплате.
- И1: rate-limit в API (Redis, tg_user_id, 60/мин, fail-open + лог); роли БД: NOLOGIN + GRANT миграцией, LOGIN — вручную; seed JSON, ключи по схеме (D-14); jsonschema — да.
- После B-3 каждая миграция с новой таблицей выдаёт GRANT ролям app_api / app_projector в той же миграции.
- 03.10–04.10: TTL 24 ч для finished — оставить; D-19 (sessionStorage) — пересмотр на 0-Б; D-20 = А; D-21 = А.
- 16.10 В1–В10 — docs/research/iter2-2.md и карточки iter2-db-*; 17.10 В11–В14 = А (docs/tasks/iter2-db-3.md, раздел 3).
- 18.10: В15–В19 = А, В20 = да, В21 = А, В22 = А — в карточках iter2-api-1, 2a, 2b. П1–П3 закрыты. Файлов > 3 — только пакетом через Codespaces.
## Решения, перекрывающие канон (до правки DOCS-course-bot)
Источник — docs/decisions/R-2026-10-1.md (Р-1…Р-8) и -2.md (Р-9…Р-14). Расходится с docs/architecture/** — прав этот раздел.
- Р-1: оплаты в Mini App нет совсем (onb.payment, payment.* не делать); оплата — в личке с Автором.
- Р-2: доступ — промокод в боте → админ-тема [Выдать доступ]/[Запретить] → флажок по tg_user_id → онбординг; до прода обязательно (миграция + РЕВЬЮЕР), после send-1.
- Р-3: фото участников нет: C5, слой «фото» Карты, /view_photos, /grant_photos_access, photo_view_log, S3_BUCKET_PHOTOS — не делать.
- Р-4: PSP на потом (YooKassa — основной, CloudPayments — запасной, только внешний сайт); Refund Saga на потом; /refund — учётная операция.
- Р-5: медиа — только внешний Telegram-канал; S3 pre-signed не делать; D-1 закрыт.
- Р-6: настроек уведомлений нет (me.settings-notifications не делать).
- Р-6а: паузы — 14 дн./год, одна ≤ 7 дн., между ≥ 24 ч; пока не построены (D-28).
- Р-7: конфиг Чек-Апа — обычные правки вперёд через эпохи; критичные для безопасности — задним числом с «ПРИМЕНИТЬ ЗАДНИМ ЧИСЛОМ».
- Р-8: ключ текста — раздел B2…B16/legal с большой буквы + имя маленькими; seed — JSON; тоны soft/neutral/dry + strict (юр-тексты).
- Р-9: прод — Timeweb Cloud (VPS + managed PostgreSQL); Yandex Cloud — запасной.
- Р-10: S3 прода — Timeweb Object Storage, только бэкапы и WORM-аудит.
- Р-11: данные в РФ; исходящий трафик к api.telegram.org — прокси на зарубежном VPS; план Б — позже.
- Р-12: initData TTL 24 ч до прода; к проду — session_jwt 60 мин (пересмотр Б14).
- Р-13: full_backup_rotation_cycle = 30 дней; PITR у Timeweb не описан (к 0-Б и юристу).
- Р-14: репо публичный до 0-Б; при 0-Б — приватный (чек-лист — R-2026-10-2.md).
## Цель и сроки
- Всё до итерации 6 + 0-Б. Сроков нет: сначала правильная настройка. AI Chat Opus без кредитов до 31.12.2026 → пересмотр плана 01.11.2026 (решение 29.09).
## План до 24.10 (решение Автора 19.10)
- Тратим все кредиты до 24.10. Агент: 22.10 send-1 + life-ops (параллельно); 23.10 пуши + Р-2 (после мержа send-1; Р-2 с РЕВЬЮЕРОМ); 24.10 ≈ 1 000 на доделки. Бесплатно: docs-r-1, docs-r-2, ПРОЕКТИРОВЩИК (карточки к 22–23.10), экран /day — КОДЕР параллельно; api-3 — после мержа life-ops. Пересмотр плана 01.11.
## Очередь
0. [сейчас] И2 API: iter2-api-2b (Р0+, РЕВЬЮЕР да) → подготовка Агента; затем iter2-api-3. Позже — iter2-send-1 (заметки ниже). Включение флага DAY_TEST_ENTRY_ENABLED — отдельным заданием ШТАБа.
1. Итерации 2–6 по build-order.md, затем 0-Б.
## Для задач И2
- Норма texts load с #100: «загружено 0, обновлено 30, лишних в БД 0».
- Правила день/*: pid только из initData через tg_user_registry; day_started_at из participant_state в той же транзакции; block_id — белый список дня; tombstoned — ничего не писать; каждый писатель событий существующего pid берёт замок participant:pid до INSERT; проектор считает «пришёл» и «+1 ч» только по текущему day_started_at.
- Для iter2-send-1 (ревью #97): Н1 не-uuid — параметром; Н2 тест tombstoned_at → адресат пуст; Н3 запрет app_bot на consent_events; Н4 rolcanlogin при выкате; Н6 current_user = 'app_bot'; LOGIN/пароль/DSN app_bot и драйвер БД в apps/bot (согласие Автора).
## Мелочи (собирать попутно в задачи без БД)
- К проду: закрыть 127.0.0.1:8080, --proxy-headers; копия бэкапов вне ноутбука; healthcheck для bot.
- Settings.model_dump() и __dict__ отдают DSN — настройки целиком не выводить. texts.run_load: ImportError драйвера не ловится («1 — А», 15.10). rate_limit: INCR и EXPIRE — две команды (лишняя память Redis).
- Долги ШТАБа (Р0, сайт): DEFECTS D-25 и D-26 зарезервированы — ключ замка I2B 'life:' vs 'participant:' (В20) и DOCS PR в CT (тела day/*, «повтор = тот же 200»); D-27 (tombstone и замок) внесён в iter2-api-2b; outbox_events (канон) ≠ outbox; В8 — права прямо app_*.
- DEFECTS (внести, Р0): app_projector INSERT participant_events с любым kind/actor (РЕВЬЮЕР #94); app_bot UPDATE outbox.sent_at без WHERE; у outbox_relay нет прав на outbox_dlq и последовательности; компакция outbox (INV-3) без владельца; sent_at после DLQ = «обработано» (В13); erasure — FK day_marks без DELETE.
- Тесты 0007 (#94): негативные CHECK key = '' и stage_no / module_no = 0. Тесты 0008 (#95): Н1 «>» вместо «>=»; Н2 нет последовательностей у day_marks; Н3 шапка 0008; Н4 _alembic_config из tests.conftest; Н5 docstring про SELECT FOR UPDATE.
- infra/SERVER-IRONCLAD.md, «Миграции и тексты (B-3d)»: команду писать полностью — DC --profile tools run --rm --no-deps migrate. AGENT-BRIEF.md §6: «0006, 13 таблиц» → «0009, 15 таблиц, роли app_api / app_projector / app_bot» — пора.
## Уроки ШТАБа (живые)
- #94 и 17.10: карточка миграции с новой таблицей включает tests/test_db_models.py; перед вопросом Автору — искать в STATE; карточка до 150 строк; новая роль в тестах → своя функция.
- 18.10: проверки таблиц — фильтр table_name <> 'alembic_version', в бэкапе N + 1; откат миграции — только дампом по решению Автора; Р0 через сайт — не больше 3 файлов; сжимать STATE при > 90 строк или > 20 КБ.
- Новая настройка api без строки в environment compose до контейнера не доходит — PR с настройкой меняет compose и .env.example; при ревью сверять файлы PR с разделом 6 карточки.
- Смена только compose → up -d --no-build --no-deps <сервис>; проверка флага — printenv + Settings, config целиком не печатать; projector once рядом с run запрещён — проверка по логам.
- Новые тексты требуют пересборки образа migrate до texts load; образ migrate сейчас на 54ca133.
- 19.10: файлы PR = раздел 6 карточки; настройка api → compose environment + .env.example; правка только compose → up -d --no-build --no-deps; projector once на сервере запрещён; новый kind → api+projector вместе; путь маршрута — grep -A2 '@router.', префикс — в main.py без угадывания имени; КОДЕР ≈ 130–140 КБ чтения, ПРОЕКТИРОВЩИК 170/200.
## К пересмотру 01.11.2026 (не проверено)
- Free Quota Deep Research: что покрывает и сколько (D-1, D-5, D-9, 152-ФЗ, PSP).
- Триггеры денег: Т1 — апгрейд тарифа на месяц; Т3 — GenTeam + свой Claude Code. Докупка 20 $ = 7 500 (источники расходятся); ноль кредитов; бесплатный Opus до 31.12 при апгрейде.
- 0-Б: после перевода репо в приватный форки и кэши ИИ останутся публичными (Р-14: риск принят Автором; закрыть в день 0-Б).
## Дефекты и блокеры
- D-1…D-27: открытые — docs/DEFECTS-FOUND.md, закрытые и перенесённые по правилу А — docs/DEFECTS-ARCHIVE.md (D-11, D-13, D-15…D-21, D-23, D-24). B-1, B-2, B-3 закрыты.
- D-15 в (сверка ver_of_text) — проверено 02.10 (0.1.0 = 0.1.0); полная проверка — после первой смены версии текста (условие к 0-Б).
## Открытые решения Автора
- Закрыто решениями 17–19.10: оплата и ПРОТИВОРЕЧИЕ ПО ОПЛАТЕ (Р-1), PSP (Р-4), хостинг (Р-9), S3 (Р-10), медиа D-1 (Р-5), ротация бэкапов (Р-13), настройки уведомлений (Р-6), тоны текстов (Р-8, «ОК А»), C5 (Р-3), Telegram в РФ — основной план (Р-11), авторизация до прода (Р-12).
- Открыто: план Б Р-11 (зарубежный бот-слой + уведомление РКН, 152-ФЗ — юристу); D-9 к проду — продление session_jwt (Р-12); PITR Timeweb и достаточность 30 дней — к 0-Б и юристу (Р-13).
## Учёт кредитов
- Plus 10 000/мес, обновление 25-го, не переносятся. Резерв 1 500. Тратит только чат Агента; бесплатные чаты = 0.
- Всего ≈ 11 500; остаток 12 900 (Автор, 19.10). Строки задач до 18.10 — снимок docs/history/STATE-a5ef1d7.md, «Учёт кредитов»; #93–#98 не внесены.
- Формат строки: задача / режим / оценка / факт / часы Автора.
- сжатие STATE 18.10 / Р0 / 0 / 0 / не замерены; iter2-api-1 / Р0+ / 0 / 0 / не замерены (КОДЕР 1 окно, З2 — 1 круг CI); docs-r-1 / Р0+ / 0 / 0 / не замерены.
