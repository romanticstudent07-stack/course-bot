# STATE — живое состояние course-bot

Обновлено: 28.09.2026 (PR «LF + процесс v3»). До 90 строк. Секретов, реальных ID и IP здесь нет.
Кто обновляет: ШТАБ даёт строки → они идут первым файлом пакета следующей задачи.
Подробности закрытых задач — docs/HISTORY.md. Правила ШТАБа — docs/process/SHTAB.md.

## Сейчас
- main = 84cace9 (мерж #30); после мержа PR «LF + процесс v3» — новый hash (из отчёта сервера).
- Сервер IRONCLAD работает только с main.
- Процесс v2 + правила ШТАБа v3.2. Этап: НАСТРОЙКА завершается, дальше — карточки И1 и пилот 1d.
- Codespaces проверен 28.09: selftest unpack ПРОЙДЕН, hooksPath=.githooks, Python 3.12.14,
  Node v20.20.2, check.sh — всё зелёное.
- Репо ПУБЛИЧНЫЙ до переезда на VPS (0-Б): обычный AI Chat приватные репо не читает
  (проверено 28.09). После 0-Б — приватный; файлы в чаты вставлять вручную.

## Смержено (подробно — docs/HISTORY.md)
- #22 скелет: api FastAPI /healthz, bot aiogram long polling, miniapp Vite+React, миграция 0001_init.
- #23 nginx — единый origin: /miniapp/v1/** и /security/csp-report → api:8080.
- #24 docs: Tailscale serve, --env-file, MinIO → Garage; D-5, D-6, D-7. История git не переписываем.
- #25 CI: 7 проверок (api, bot, miniapp, docker×3, guard); requirements-dev.txt; D-8.
- #26 1a: проверка initData (HMAC + TTL), общий роутер /miniapp/v1. Сервер ✅.
- #27 1b+1c: миграция 0002 tg_user_registry + first-launch; CI: 9 таблиц, REQUIRE_DB_TESTS=1. Сервер ✅.
  Проверка «настоящая Mini App → first-launch» — ждёт экран (1e).
- #28 Р0: лимит бота 512M, сумма лимитов ≤ 2 ГБ. Сервер ✅.
- #29 Р0: AGENT-BRIEF.md v1 + .genspark/rules.md. Сервер ✅.
- #30 процесс v2: tools/unpack.py, tools/check.sh, .devcontainer, STATE.md, docs/process/*,
  AGENTS.md, AGENT-BRIEF.md v2. Сервер ✅ 84cace9. 7 файлов с CRLF → PR «LF + процесс v3».

## Решения Автора
- Роли: ШТАБ — главный, закрывает задачи; серверный чат ОДИН, постоянный, со своим промптом
  у Автора; ПРОЕКТИРОВЩИК и КОДЕР — временные окна. Все чаты — Opus 5.5.
- Бот — long polling. Cloudflare Tunnel — нет. Прод — российский VPS (фаворит Timeweb Cloud),
  туннель дом→VPS autossh/WireGuard.
- Память: сумма лимитов ≤ 2 ГБ; сейчас 1664 МБ (api 384, db 384, bot 512, garage 192,
  miniapp 128, redis 64), реально ~290 МБ.
- Бэкап БД на сервере: ~/bin/coursebot-db-backup.sh, cron 03:30 MSK, 14 дней.
  Перед каждой миграцией — ручной pg_dump -Fc.
- initData: TTL 24 ч, допуск «из будущего» 60 с; 401 TG_INIT_MISSING / TG_INIT_INVALID;
  пустой BOT_TOKEN → 503 SERVICE_MISCONFIGURED. session_jwt — D-9, отложено.
- first-launch: SEAM-1; tg_user_id только из initData; 18+ до БД (Europe/Moscow);
  дату рождения не храним; повтор → 201 тот же {pid, short_no}; БД недоступна → 503.
- participant_state пишет только проектор (отдельная задача). lifecycle_phase — D-11.
- Required status checks не включаем; красный PR не мержим.
- Концы строк — только LF: .gitattributes + .vscode/settings.json + eol в check.sh и в CI guard.

## Цель и сроки
- Всё до итерации 6 + 0-Б. Сроков нет: сначала правильная настройка.
- AI Chat Opus без кредитов до 31.12.2026 → пересмотр плана в начале декабря 2026.

## Очередь
0. [сейчас] PR «LF + процесс v3» → мерж → сервер (eol = 0) → Автор обновляет файлы на компьютере.
1. Разбор 3-го исследования Автора (отдельное окно РАЗБОР) → находки в ШТАБ → при нужде Р0-PR.
2. ПРОЕКТИРОВЩИК: карточки итерации 1 — 1d text_registry, 1e экраны онбординга + согласия (B-2),
   проектор participant_state, B-1 rate-limit, B-3 роли БД → PR с карточками.
3. Пилот 1d в Р0+ (замер: часы Автора, запросы до лимита окна, круги CI).
4. Итерации 2–6 по build-order.md, затем 0-Б.

## Мелочи (собирать попутно в задачи без БД)
- /miniapp без слэша → 404. К проду: закрыть 127.0.0.1:8080, --proxy-headers.
- healthcheck для bot и redis. README (HTTPS) и infra/README.md (SSH) — клонировать одинаково.
- «MinIO — сентябрь 2026» в AGENTS.md и infra/README.md проверить (по данным Claude — осень 2025).
- infra/SERVER-IRONCLAD.md: описать автобэкап (без секретов). Копия бэкапов вне ноутбука — к проду.
- ci.yml: в шапке-комментарии guard дописать «и CRLF» (при следующей правке ci.yml).
- gitleaks: разовый скан истории (план PROCESS-V2) — выполнение не записано; сделать в Codespaces.

## Дефекты и блокеры
- D-5…D-13 в docs/DEFECTS-FOUND.md.
- Блокеры до VPS: B-1 rate-limit (R328); B-2 согласия legal_consents до создания pid (D-10);
  B-3 роли/GRANT БД (D-13).

## Открытые решения Автора
- D-1 медиа (S3 pre-signed или Telegram-канал); провайдер VPS/облака; Telegram в РФ и 152-ФЗ;
  PSP; модель авторизации к проду (D-9).
- ПРОТИВОРЕЧИЕ ПО ОПЛАТЕ: AGENTS.md — вручную (вариант A); build-order.md, итерация 4 — PSP
  (YooKassa); экран onb.payment при правиле «оплата вне Mini App». До решения не реализовывать.

## Учёт кредитов
- Plus 10 000/мес, обновление 25-го, не переносятся. Резерв 1 500. Докупка 20 $ за 7 500 — крайний случай.
- Всего ≈ 11 500 (учёт начат не сразу): #25 ≈ 600; #26 = 1300; #27 = 2300; остальное — без разбивки.
- #28 = 0; #29 = 0; #30 = 0; «LF + процесс v3» = 0.
- Формат новой строки: задача / режим / оценка / факт / часы Автора.
