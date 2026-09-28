# STATE — живое состояние course-bot

Обновлено: 27.09.2026 (PR «процесс v2»). До 90 строк. Секретов, реальных ID и IP здесь нет.
Кто обновляет: КОДЕР — первым файлом пакета следующей задачи (по отчёту сервера) или ШТАБ.

## Сейчас
- main = 77d312b (мерж #29), после мержа этого PR — новый hash (впишет следующий КОДЕР).
- Сервер IRONCLAD работает только с main.
- Процесс: v2 (docs/process/README.md). Этап: НАСТРОЙКА. Пилот 1d — после настройки.
- Репо ПУБЛИЧНЫЙ временно (бесплатные чаты читают его). Закрыть после 0-Б
  или раньше, если Genspark подтвердит чтение приватного репо.

## Смержено
- #22 скелет: api FastAPI /healthz, bot aiogram long polling, miniapp Vite+React, миграция 0001_init.
- #23 nginx — единый origin: /miniapp/v1/** и /security/csp-report → api:8080.
- #24 docs: Tailscale serve, --env-file, MinIO → Garage; D-5, D-6, D-7. История git не переписываем.
- #25 CI: 7 проверок (api, bot, miniapp, docker×3, guard); requirements-dev.txt; D-8.
- #26 1a: проверка initData (HMAC + TTL), общий роутер /miniapp/v1. Сервер ✅.
- #27 1b+1c: миграция 0002 tg_user_registry + first-launch; CI: 9 таблиц, REQUIRE_DB_TESTS=1.
  Сервер ✅ 25.09: alembic current = 0002_tg_user_registry; 401 / 201 / 201 через nginx / 403;
  утечек в логах 0; тестовый участник #000001 (ADMIN_USER_ID) оставлен в dev-БД.
  Проверка «настоящая Mini App → first-launch» — ждёт экран (1e).
- #28 Р0: лимит бота 512M, сумма лимитов ≤ 2 ГБ. Сервер ✅ Memory=536870912, RestartCount=0.
- #29 Р0: AGENT-BRIEF.md v1 + .genspark/rules.md (чтение: BRIEF + файлы из промпта). Сервер ✅.

## Решения Автора (подробно — AGENT-BRIEF.md, раздел 7)
- Бот — long polling. Cloudflare Tunnel — нет. Прод — российский VPS (фаворит Timeweb Cloud),
  туннель дом→VPS autossh/WireGuard.
- Память: сумма лимитов ≤ 2 ГБ; сейчас 1664 МБ (api 384, db 384, bot 512, garage 192,
  miniapp 128, redis 64), реально ~290 МБ. Бот 155 МБ — норма, утечки нет.
- Бэкап БД на сервере: ~/bin/coursebot-db-backup.sh, cron 03:30 MSK, хранение 14 дней.
  Перед каждой миграцией — ручной pg_dump -Fc.
- initData: TTL 24 ч, допуск «из будущего» 60 с; 401 TG_INIT_MISSING / TG_INIT_INVALID;
  пустой BOT_TOKEN → 503 SERVICE_MISCONFIGURED. Модель к проду (session_jwt) — D-9, отложено.
- first-launch: SEAM-1; tg_user_id только из initData; 18+ до БД (Europe/Moscow);
  дату рождения не храним; повтор → 201 тот же {pid, short_no}; БД недоступна → 503.
- participant_state пишет только проектор (отдельная задача). lifecycle_phase — D-11.
- Required status checks не включаем; красный PR не мержим.

## Цель
- Всё до итерации 6 + переезд на VPS (0-Б). Ориентир 1–2 месяца.
- Код бесплатными чатами Opus — до 15.12.2026 (с 01.01.2027 Opus в чате платный).

## Очередь
0. [сейчас] PR «процесс v2» → мерж → Codespaces → самопроверка unpack/check.
1. Письмо в поддержку Genspark (приватный GitHub, 5-часовое окно, ноль кредитов в Code).
2. ШТАБ выдаёт промпт ШТАБ v3 целиком.
3. ПРОЕКТИРОВЩИК: карточки итерации 1 — 1d text_registry, 1e экраны онбординга + согласия (B-2),
   проектор participant_state, B-1 rate-limit, B-3 роли БД.
4. Пилот 1d в режиме Р0+ (замер: часы Автора, запросы до лимита окна, круги CI).
5. Итерации 2–6 по build-order.md, затем 0-Б.

## Мелочи (собирать попутно в задачи без БД)
- /miniapp без слэша → 404. К проду: закрыть 127.0.0.1:8080, --proxy-headers.
- healthcheck для bot и redis. README (HTTPS) и infra/README.md (SSH) — клонировать одинаково.
- «MinIO — сентябрь 2026» в AGENTS.md и infra/README.md проверить (по данным Claude — осень 2025).
- infra/SERVER-IRONCLAD.md: описать автобэкап (без секретов). Копия бэкапов вне ноутбука — к проду.

## Дефекты и блокеры
- D-5…D-13 в docs/DEFECTS-FOUND.md.
- Блокеры до VPS: B-1 rate-limit (R328); B-2 согласия legal_consents до создания pid (D-10);
  B-3 роли/GRANT БД (D-13).

## Открытые решения Автора
- D-1 медиа (S3 pre-signed или Telegram-канал); провайдер VPS/облака; Telegram в РФ и 152-ФЗ;
  PSP; модель авторизации к проду (D-9); видимость репо (сейчас публичный).
- ПРОТИВОРЕЧИЕ ПО ОПЛАТЕ: AGENTS.md — вручную (вариант A); build-order.md, итерация 4 — PSP
  (YooKassa); экран onb.payment при правиле «оплата вне Mini App». До решения не реализовывать.

## Учёт кредитов (тариф Plus, 10 000/мес, не переносятся; резерв 1 500)
- Всего ≈ 11 500: #25 CI ≈ 600; #26 = 1300; #27 = 2300; #28 = 0; #29 = 0; процесс v2 = 0.
- Формат новой строки: задача / режим / оценка / факт / часы Автора.
