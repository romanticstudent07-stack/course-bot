# STATE — живое состояние course-bot
Обновлено: 18.10.2026 (сжатие STATE; #97 iter2-db-3 — 0009 на сервере ✅ cfb089d; #98 research iter2-api + карточки iter2-api-1, 2a, 2b). До 90 строк. Секретов, реальных ID и IP здесь нет.
Кто обновляет: ШТАБ даёт строки → они идут первым файлом пакета следующей задачи.
Подробности закрытых задач — docs/HISTORY.md. Прежний STATE целиком (до сжатия 18.10, дословно: выкаты сервера до 0008, «Смержено» #49–#96, строки учёта кредитов) — docs/history/STATE-a5ef1d7.md. КОДЕРАМ HISTORY и снимок не давать.
Правила ШТАБа — docs/process/SHTAB.md (часть 1) + docs/process/SHTAB-2.md (часть 2), читать ОБА.
Процессные решения (роли, РЕВЬЮЕР, окна чатов, терминал, rulesets main, форки, LF, expected_tables.txt, миграции по одной) — в SHTAB.md, SHTAB-2.md, DESIGNER.md, README.md.
## Сейчас
- main = a5ef1d7; сервер ✅ cfb089d, alembic 0009_app_bot, 15 таблиц; очередь — iter2-api-1 → 2a → 2b. Сервер IRONCLAD работает только с main.
- Сервер ✅ cfb089d (18.10.2026, 07:28–07:31 MSK): 0008 → 0009_app_bot, 9 с, Traceback 0; 15 таблиц + alembic_version; rolcanlogin app_bot = f; 4.3в t|f|t|f|t|t; 4.3г t|t; outbox 0, outbox_dlq 0; 7/7 Up, 5 healthy, StartedAt не менялись; 200/200/401; бэкап db-20261018_072841-before-0009.dump 41722 Б (116 объектов). #98 — только docs, выката не нужно.
- Норма сервера: 7/7 Up, 5 healthy (db, redis, garage, api, miniapp), healthcheck нет у bot и projector; curl / 200, /healthz 200, /miniapp/v1/onboarding/status 401. Роли: api — coursebot_api, projector — coursebot_projector, alembic и texts load — владелец (только DC --profile tools run --rm --no-deps migrate); env_file нет ни у одного сервиса; repr/str Settings без DSN (api и projector). Перед каждой миграцией — бэкап before-000N и DC --profile tools build migrate.
- bot при выкатах melochi-2 и 0007–0009 не пересобирался (комментарий apps/bot/Dockerfile #87 и docstring #83 подтянутся при следующем выкате bot). Ручной projector once не нужен (SERVER-IRONCLAD).
- В БД (17.10): tg_user_registry 2, consent_events 4, participant_events 2: второй участник — живая проверка Автора на втором аккаунте 15.10 08:51 MSK (miniapp-fix).
- ЗАКРЫТО: И1 (1d, B-1, 1e-1, 1e-2, 1e-2b), projector, returning, ЭТАП B-3 (14.10; D-13 и D-24 — в архиве), miniapp-fix и melochi-2 (15.10; D-23 → архив; gitleaks по истории — секретов 0), DOCS D-2/3/8/12, D-11/16/21, D-22; И2 БД: iter2-db-1 (0007) ✅ b27bdc8, iter2-db-2 (0008) ✅ c5715b6, iter2-db-3 (0009) ✅ cfb089d. Подробно — снимок docs/history/STATE-a5ef1d7.md.
- DEFECTS-FOUND.md < 25 000 байт (prep-projector: правило А — D-15, D-17, D-18, D-19 в архиве целиком); DEFECTS-ARCHIVE.md КОДЕРАМ кода не давать.
- Бэкапы before-0004 ✅ (02.10), before-0005 ✅ (05.10), before-0006 ✅ (09.10), before-b3d ✅ (14.10), before-0007 ✅ (17.10, 36771 Б), before-0008 ✅ (17.10, 39592 Б), before-0009 ✅ (18.10, 41722 Б). Downgrade ниже 0004 запрещён (стирает журнал согласий).
- Процесс v3.8: SHTAB.md 3-Б «бюджет чтения» (КОДЕР: одна карточка = одна область; задачу режем, чтение не урезаем) + DESIGNER.md «Бюджет окна» (ПРОЕКТИРОВЩИК: 1–3 карточки, З1 до 120 КБ, ИССЛЕДОВАНИЕ до 150 КБ — отдельным окном в docs/research/). Файл восстановления ШТАБа — SHTAB-CONTEXT-CHAT.txt.
- Живые проверки 02.10 пройдены: 403 «младше 18» (отказ ничего не создал) и 429 (лимит временно 1/мин, возвращён); числа — DEFECTS-ARCHIVE.md (D-7, D-10).
- Mini App после пересборки: Telegram отдаёт старую версию из кэша — закрыть и открыть заново (проверено 02.10).
- Codespaces проверен 28.09: selftest unpack ПРОЙДЕН, hooksPath=.githooks, Python 3.12.14, Node v20.20.2, check.sh — всё зелёное.
- Репо ПУБЛИЧНЫЙ до 0-Б (обычный AI Chat приватные репо не читает, проверено 28.09); после 0-Б — приватный, файлы в чаты вставлять вручную.
## Смержено (подробно — docs/HISTORY.md и снимок docs/history/STATE-a5ef1d7.md)
- Сервер ✅ после каждого мержа ниже (только docs — только pull).
- #22–#43 — docs/HISTORY.md; #49–#96 — снимок docs/history/STATE-a5ef1d7.md, раздел «Смержено».
- #97 iter2-db-3 (0009_app_bot, роль app_bot, выкат 18.10 07:31 MSK); #98 research iter2-api + карточки iter2-api-1, 2a, 2b.
## Решения Автора (процессные — в правилах, см. шапку)
- Бот — long polling. Cloudflare Tunnel — нет. Прод — российский VPS (фаворит Timeweb Cloud), туннель дом→VPS autossh/WireGuard.
- Память: сумма лимитов ≤ 2 ГБ; сейчас 1920 МБ (с одноразовым migrate 128 МБ, B-3d-1) (api 384, db 384, bot 512, garage 192, miniapp 128, projector 128, redis 64), реально ~362 МБ (06.10, projector 53).
- Бэкап БД на сервере: ~/bin/coursebot-db-backup.sh, cron 03:30 MSK, 14 дней; перед каждой миграцией — ручной pg_dump -Fc.
- initData: TTL 24 ч, допуск «из будущего» 60 с; 401 TG_INIT_MISSING / TG_INIT_INVALID; пустой BOT_TOKEN → 503 SERVICE_MISCONFIGURED. session_jwt — D-9, отложено.
- first-launch: SEAM-1; tg_user_id только из initData; 18+ до БД (Europe/Moscow); дату рождения не храним; повтор → 201 тот же {pid, short_no}; БД недоступна → 503.
- Отказ «младше 18» нигде не сохраняется: перезапуск Mini App позволяет ввести другую дату — принято как свойство самодекларации (Р47, дату не храним).
- participant_state пишет только проектор (отдельная задача). lifecycle_phase — D-11.
- Тексты курса в репо — только заглушки до 0-Б (опубликованное назад не забрать).
- И1 (29.09): строго по одной — 1d → B-1 → 1e-1 → 1e-2 → проектор → B-3; миграции 0003…0006 от 0002.
- И1: onb.payment в 1e нет; после pid: offer (только чтение) → email → city → checkup → rules; оплата вне порядка ADD3 до решения противоречия по оплате.
- И1: согласия до pid — first-launch принимает birth_date + consents[], пишет согласия и pid одной транзакцией (D-10); обязательны C0 (18+) и C1 (ПДн), C5 — с фото; оферта принимается вместе с оплатой.
- И1: rate-limit в API (Redis, ключ tg_user_id, 60/мин, fail-open + лог), nginx-лимит нет. Роли БД: NOLOGIN + GRANT миграцией, LOGIN — вручную.
- И1: lifecycle_phase — FSM И2 (D-11, решено 6А); журнал participant_events (D-16, записан в prep-projector); jsonschema — да.
- И1: seed JSON; ключи по схеме (онбординг B4.*, согласия legal.*), API принимает шаблон схемы (D-14).
- После B-3 каждая миграция с новой таблицей выдаёт GRANT ролям app_api / app_projector в той же миграции.
- 03.10: TTL 24 ч для finished — оставить; D-15 (е) и D-18 → B-3b; sessionStorage в SDK (D-19, 6А) — ничего не менять, пересмотр на 0-Б.
- 04.10: D-20 = А (убрать data: из font-src → miniapp-csp); D-21 = А (DOCS: MINIAPP_URL → WEBAPP_URL, вместе с D-16 после projector); архив по правилу А.
- Решения Автора 16.10 В1–В10 — docs/research/iter2-2.md и карточки iter2-db-*.
- 17.10 (iter2-db-3): В11 — А (адресат через tg_user_registry, tombstoned_at при отправке); В12 — А (текст собирает бот, SELECT text_registry); В13 — А (после DLQ sent_at = now(): «обработано», не «доставлено»); В14 — А (INSERT outbox для app_projector — в 0009). Дословно — docs/tasks/iter2-db-3.md, раздел 3.
- В11–В14 = А (17.10); В15–В19 = А, В20 = да, В21 = А, В22 = А (18.10). В15–В22 — в карточках iter2-api-1, 2a, 2b. П1–П3 закрыты. Файлов > 3 — только пакетом через Codespaces.
## Цель и сроки
- Всё до итерации 6 + 0-Б. Сроков нет: сначала правильная настройка. AI Chat Opus без кредитов до 31.12.2026 → пересмотр плана 01.11.2026 (решение 29.09).
## Очередь
0. [сейчас] И2 API: iter2-api-1 → iter2-api-2a → iter2-api-2b (карточки — docs/tasks, миграций нет; api-1 — Р0+, Codespaces, РЕВЬЮЕР нет). Позже — iter2-send-1 (заметки ниже).
1. Итерации 2–6 по build-order.md, затем 0-Б.
## Для задач И2
- Для api-1: после выката — DC --profile tools run --rm --no-deps migrate python -m app.texts load; ключи заглушек — apps/api/config/texts/<домен>.json по KEY_PATTERN texts.py.
- Для карточки iter2-api-2 (РЕВЬЮЕР #95, Н6): pid только из проверенного initData через tg_user_registry, не из тела; day_started_at из participant_state в той же транзакции; block_id — белый список блоков текущего дня + ограничение длины; участнику с tombstoned_at отметки не писать; тест «pid/day_started_at из тела игнорируются»; проектор считает «пришёл» и «+1 ч» только по текущему day_started_at.
- Для iter2-send-1 (ревью #97): Н1 не-uuid — параметром в транзакции; Н2 тест tombstoned_at → адресат пуст; Н3 запрет app_bot на consent_events; Н4 rolcanlogin при выкате; Н6 current_user = 'app_bot'; LOGIN/пароль/DSN app_bot и драйвер БД в apps/bot (согласие Автора).
## Мелочи (собирать попутно в задачи без БД)
- К проду: закрыть 127.0.0.1:8080, --proxy-headers; копия бэкапов вне ноутбука. healthcheck для bot (у redis есть с #87).
- Settings.model_dump() и __dict__ отдают DSN открытым текстом — настройки целиком не выводить. texts.run_load: ImportError драйвера не ловится (DSN в тексте нет; решение «1 — А», 15.10). rate_limit: INCR и EXPIRE — две отдельные команды; сбой между ними оставит ключ без срока жизни (на лимит не влияет — в ключе номер минуты; лишняя память Redis).
- Долги ШТАБа (Р0, сайт): DEFECTS с D-25 — ключ advisory lock в I2B 'life:' и 'participant:'; outbox_events (канон) ≠ outbox (у нас); В8 — права прямо app_*, не ролям канона; DESIGNER.md «база ≈ 47 КБ» → ≈ 65 КБ; урок — ИССЛЕДОВАНИЕ-2 прочитало 183 из 150 КБ.
- DEFECTS (внести): app_projector INSERT participant_events с любым kind; app_bot UPDATE outbox.sent_at без WHERE; у outbox_relay нет прав на DLQ; компакция outbox (INV-3) без владельца; sent_at = «обработано»; erasure — FK day_marks без DELETE; D-25, D-26 → DOCS PR в CT (тела day/*, «повтор = тот же 200»); I2B: ключ замка 'participant:' || pid (В20).
- DEFECTS (Р0, сайт): app_projector может вставить в participant_events любой kind/actor (INSERT на всю таблицу, В9 = А) — сузить RLS WITH CHECK или триггером отдельной задачей (РЕВЬЮЕР #94, неблок. 2).
- DEFECTS (Р0, сайт, из iter2-db-3 З1): у outbox_relay канона нет прав на outbox_dlq и последовательности; у компакции outbox (INV-3) нет владельца; sent_at после DLQ = «обработано», не «доставлено» (В13).
- Тесты 0007 (РЕВЬЮЕР #94, неблок. 3): негативные CHECK key = '' (ck_idempotency_keys_key_not_empty) и stage_no / module_no = 0 в test_db_roles_0007.py.
- Тесты 0008 (РЕВЬЮЕР #95): Н1 — тест 1 «second.at >= first.at» → «>»; Н2 — закрепить тестом «у day_marks нет последовательностей»; Н3 — шапка 0008 как в 0007; Н4 — убрать свой _alembic_config (брать из tests.conftest); Н5 — строка в docstring 0008: UPDATE (value, at) даёт app_api SELECT FOR UPDATE на day_marks (только блокировка).
- infra/SERVER-IRONCLAD.md, «Миграции и тексты (B-3d)»: команду писать полностью — DC --profile tools run --rm --no-deps migrate (выкат 0007, 17.10).
- AGENT-BRIEF.md §6: «0006, 13 таблиц» → после выката 0009 — «0009, 15 таблиц, роли app_api / app_projector / app_bot». 0009 выкачен 18.10 — пора.
## Уроки ШТАБа (живые)
- #94: карточка миграции с новой таблицей включает tests/test_db_models.py (счётчик и цикл downgrade); перед вопросом Автору — искать ответ в STATE (второй участник 15.10 был записан).
- 17.10: ожидание числа таблиц в бэкапе before-000N = схема ДО этой миграции; DESIGNER.md — карточка до 150 строк (iter2-db-3 — 174); role_engine принимает только APP_ROLES — новая роль в тестах → своя функция.
- 18.10: в проверках таблиц фильтр table_name <> 'alembic_version', в бэкапе ждать N + 1; откат миграции на сервере — только восстановлением дампа по решению Автора; Р0 через сайт — не больше 3 файлов (#98 — 4, отступление).
- 18.10: STATE вырос до 32 КБ / 98 строк и съел бюджет чтения КОДЕРА — сжимать, когда STATE > 90 строк или > 15 КБ.
## К пересмотру 01.11.2026 (не проверено)
- Free Quota Deep Research: что покрывает и сколько (для D-1, D-5, D-9, 152-ФЗ, PSP).
- Триггеры денег: Т1 — апгрейд тарифа на месяц; Т3 — GenTeam + свой Claude Code. Цены, механика.
- Без подтверждения поддержки: докупка 20 $ = 7 500 (источники расходятся); что будет при нуле кредитов; сохраняет ли апгрейд тарифа бесплатный Opus до 31.12.
- 0-Б: после перевода репо в приватный форки и кэши ИИ останутся публичными.
## Дефекты и блокеры
- D-1…D-24: открытые — docs/DEFECTS-FOUND.md, закрытое и перенесённое по правилу А — docs/DEFECTS-ARCHIVE.md. B-1, B-2 и B-3 закрыты (B-3 — роли/GRANT БД, D-13, 14.10). D-13 и D-24 — в архиве целиком (правило А, 14.10); D-23 — в архиве целиком (правило А, 15.10, #82).
- 06.10 (CB-docs-2): D-11, D-16, D-20, D-21 закрыты → архив целиком (правило А); 04.10: D-15, D-17, D-18, D-19 → архив. Зеркало исправлено: D-2/3/8/12 (DOCS #9/#10/#11, sync #51), D-11/16/21 (DOCS #12, sync #59).
- D-15 в (сверка ver_of_text) — проверено 02.10: consent_events.ver_of_text = 0.1.0 совпадает с text_registry.registry_version = 0.1.0. Полная проверка — только после первой смены версии текста (у старых записей версия обязана остаться прежней) — условие к 0-Б.
## Открытые решения Автора
- D-1 медиа (S3 pre-signed или Telegram-канал); провайдер VPS/облака; Telegram в РФ и 152-ФЗ; PSP; модель авторизации к проду (D-9).
- ПРОТИВОРЕЧИЕ ПО ОПЛАТЕ: AGENTS.md — вручную (вариант A); build-order.md, итерация 4 — PSP (YooKassa); экран onb.payment при правиле «оплата вне Mini App». До решения не реализовывать.
## Учёт кредитов
- Plus 10 000/мес, обновление 25-го, не переносятся. Резерв 1 500. Докупка 20 $ за 7 500 — крайний случай. Тратит только чат Агента; бесплатные чаты = 0, ДО/ПОСЛЕ не снимаем.
- Всего ≈ 11 500 (учёт начат не сразу): #25 ≈ 600; #26 = 1300; #27 = 2300; остальное — без разбивки. #28–#31, «процесс v3.3», #33, «процесс v3.4», v3.5, v3.6 = 0. Остаток 10 231.
- Формат новой строки: задача / режим / оценка / факт / часы Автора.
- Строки задач от 1d до «долги #22–#43 → HISTORY + SHTAB-2» — дословно в снимке docs/history/STATE-a5ef1d7.md, раздел «Учёт кредитов» (факт после 1d — 0 у всех).
- #93–#98 (исследования И2, iter2-db-1/2/3, карточки iter2-api): строки не внесены.
- сжатие STATE 18.10 / Р0 / 0 / 0 / часы не замерены (сайт, 2 файла).
