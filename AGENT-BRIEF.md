# AGENT-BRIEF.md — шпаргалка для AI-агента (читать ПЕРВОЙ)

Версия 2 · 27.09.2026. Актуальный hash main — в промпте или в `docs/STATE.md`.
Заменяет обязательное чтение 9 файлов. Если промпт задачи противоречит этому
файлу — прав промпт. Если этот файл противоречит AGENTS.md / CONTEXT.md в части
«что читать» и «как тестировать» — прав этот файл.

## 1. Как работать (экономия кредитов)

- Читай ТОЛЬКО этот файл + файлы из раздела «ЧТО ПРОЧИТАТЬ» в промпте.
- `docs/architecture/**` не открывай: нужные выдержки уже в промпте.
  Выдержки не хватает и без неё работу не сделать → стоп, один короткий вопрос.
- Не исследуй репозиторий вслепую (ls -R, grep по всему репо, чтение «для контекста»).
  Исключение: если ошибка теста или импорт прямо указывает на файл вне списка — открой
  только его и перечисли такие файлы в описании PR.
- Решения в промпте уже приняты Автором. «ОК» не жди (кроме режима Р2), сразу выполняй.
- Не перепроверяй то, что в промпте отмечено как проверенное сервером или CI.
- Коммить и пушь после каждого готового шага.
- Одна и та же ошибка дважды — остановись и опиши, не перебирай варианты.
- Ответ в чат — не больше 15 строк: ссылка на PR, итог тестов, что нужно от Автора.

## 2. Проект за 30 секунд

Telegram-курс личной трансформации: Mini App + бот + backend. Mini App-first.
Панель Автора (Блок 17) — только в боте. Оплата — только ВНЕ Mini App.

| Путь | Что | Стек |
|---|---|---|
| `apps/api/` | backend `/miniapp/v1/**` | Python 3.12, FastAPI, PostgreSQL 16, Redis 7, Alembic |
| `apps/bot/` | Telegram-бот, long polling (webhook не ставится) | Python 3.12, aiogram 3 |
| `apps/miniapp/` | клиент, отдаётся nginx | React 18, Vite, TypeScript |
| `packages/shared/` | OpenAPI-контракт `/miniapp/v1`, общие типы | — |
| `infra/` | docker-compose для сервера Автора (IRONCLAD) | Docker Compose |
| `docs/architecture/` | READ-ONLY зеркало DOCS-course-bot | — |
| `docs/DEFECTS-FOUND.md` | расхождения архитектуры с реальностью (D-N, B-N) | — |

## 3. Жёсткие запреты

- Не править: `docs/architecture/**`, `.github/**`, `.githooks/**`, `.env`.
  Нужен новый `.github/**` → дай полный текст в описании PR одним блоком и перечисли
  отличия от main (GitHub App не имеет права workflows, файл внесёт Автор).
- Не пушить в `main` — только ветка + PR.
- Секреты — только из `.env` (в репо только `.env.example`). URL, порты, хосты не хардкодить.
- Не логировать initData, `hash`, `auth_date`, BOT_TOKEN, ПДн (имя, username, дата рождения).
- Никаких dev-обходов проверки initData. Не доверять `initDataUnsafe` на клиенте.
- Новые зависимости — только с согласия Автора (вопрос в PR).
- Не создавать состояния `banned_soft` / `banned_hard` — их не существует.
- Не встраивать оплату в Mini App. Не переносить Панель Автора в Mini App.
- Не угадывать открытые решения Автора (раздел 9) — вопрос в конце описания PR.

## 4. Sandbox: что можно и чего нельзя

- Docker в sandbox НЕТ: `docker compose` не запускать.
- Не поднимать Postgres / uvicorn / серверы, не делать curl, если промпт прямо не велит.
  Живые проверки делает сервер Автора, тесты с БД — CI.
- Тесты (по 1 прогону; гонки/нагрузка — не больше 2), только для затронутых приложений:
  - api: `cd apps/api && pip install -r requirements-dev.txt && python -m pytest -q`
  - bot: `cd apps/bot && pip install -r requirements-dev.txt && python -m pytest -q`
  - miniapp: `cd apps/miniapp && npm ci && npx tsc --noEmit && npx vitest run`
- Тесты с БД без живого Postgres в sandbox пропускаются — это нормально.
  В CI они обязательны (`REQUIRE_DB_TESTS=1`, живой postgres:16).
- Временные файлы — только в `/home/user/webapp/.tmp/` (в .gitignore). `/tmp` — нельзя.
- Один раз после клона: `git config core.hooksPath .githooks && chmod +x .githooks/pre-commit`.

## 5. CI — 7 проверок на каждый PR (`.github/workflows/ci.yml`)

`api` (pytest + alembic upgrade/downgrade на postgres:16) · `bot` (pytest) ·
`miniapp` (npm ci, tsc, vitest, vite build) · `docker` ×3 (сборка api / bot / miniapp,
`nginx -t`) · `guard` (PR не трогает `docs/architecture/**` и не приносит `.env`).
Красный CI → Автор пришлёт лог в этот же чат.

## 6. Что уже есть в коде

- `apps/api/app/telegram_init_data.py` — проверка initData (HMAC-SHA256 + TTL), только stdlib;
  подключена ко всем `/miniapp/v1/**` через общий роутер.
- `apps/api/app/config.py` — настройки из переменных окружения.
- `apps/api/app/db/` — подключение к БД; `apps/api/app/participants.py` — работа с `tg_user_registry`.
- `apps/api/app/routers/onboarding.py` — `POST /miniapp/v1/onboarding/first-launch`.
- Миграции: `0001_init`, `0002_tg_user_registry`. Таблиц в public (без alembic_version): 9.
  `tg_user_registry`: pid uuid PK, tg_user_id bigint (>0), short_no bigint identity UNIQUE,
  created_via text (= 'mini_app_first_launch'), created_at timestamptz, tombstoned_at timestamptz;
  UNIQUE (tg_user_id) WHERE tombstoned_at IS NULL.

## 7. Принятые решения Автора (не менять)

- initData: TTL 24 ч (`INIT_DATA_MAX_AGE_SECONDS=86400`), допуск «из будущего» 60 с.
  401 `TG_INIT_MISSING` / `TG_INIT_INVALID`; пустой BOT_TOKEN → 503 `SERVICE_MISCONFIGURED`.
- first-launch: участник создаётся здесь (SEAM-1); tg_user_id — только из initData;
  18+ проверяется ДО записи в БД, «сегодня» — по Europe/Moscow; дата рождения НЕ хранится;
  повтор → 201 с тем же {pid, short_no}; пропуски short_no допустимы;
  403 `AGE_GATE_UNDERAGE`, в лог — только `reason=underage`; БД недоступна → 503 `SERVICE_UNAVAILABLE`.
- `participant_state` пишет только проектор (отдельная задача). API туда не пишет.
- Идемпотентность: `client_op_id` обязателен для финансовых и state-меняющих операций.
- CSP Mini App: `unsafe-eval` запрещён.

## 8. Окружение (значения — только из `.env`)

- Внутри compose-сети: Postgres `db:5432`, Redis `redis:6379`, Garage (S3) `garage:3900`, API `api:8080`.
- С хоста сервера: Postgres `127.0.0.1:5435`, Redis `127.0.0.1:6382`, API `127.0.0.1:8080`,
  Mini App (nginx) `127.0.0.1:5173`, S3 `127.0.0.1:9000`. Все порты — только 127.0.0.1.
- nginx Mini App проксирует `/miniapp/v1/**` и `/security/csp-report` в `api:8080`.
- TZ контейнеров — Europe/Moscow. S3 в dev — Garage (MinIO не возвращать).

## 9. Открытые решения Автора — агент их НЕ решает

Провайдер облака / российского VPS (D-5); Telegram в РФ и 152-ФЗ (D-6); медиа: S3 pre-signed
или Telegram-канал (D-1); модель авторизации к проду, session_jwt (D-9); PSP и способ оплаты
(противоречие: AGENTS.md — оплата вручную, build-order — YooKassa, экран `onb.payment`
при правиле «оплата вне Mini App»); `full_backup_rotation_cycle`; три несовместимости Б17;
роли `finance` и `moderator`.
Блокеры до любого внешнего доступа: B-1 rate-limit, B-2 согласия до создания pid, B-3 роли/GRANT БД.

## 10. Описание PR (стандарт)

1. Прочитанные файлы (включая открытые по исключению из раздела 1).
2. Что сделано — кратко, без пересказа кода.
3. Таблица проверок (тест → результат).
4. Полный текст `.github/**`, если нужен (одним блоком + отличия от main).
5. «Команды для Автора на IRONCLAD»: «До мержа» — ничего; «После мержа (main)» — без git checkout.
6. «Вопросы Автору». Не выдумывай — спрашивай.

## 11. Режим Р1-П «Раскладчик пакета» и память проекта

- Пакет — текст с блоками `===== FILE: путь =====` … `===== END =====`
  и `===== DELETE: путь =====`. Его пишет бесплатный чат КОДЕР; агент только раскладывает.
- Порядок: сохранить пакет в `/home/user/webapp/.tmp/bundle.txt` →
  `python3 tools/unpack.py .tmp/bundle.txt` → `bash tools/check.sh <api|bot|miniapp>` →
  чинить ТОЛЬКО упавшее, минимальной правкой → коммит → push → PR.
- Скрипт отклонил пакет → не обходить, описать ошибку Автору.
- Код пакета не переписывать и не «улучшать». Каждое отличие от пакета — перечислить в описании PR.
- Состояние проекта — `docs/STATE.md`; карточки задач — `docs/tasks/<id>.md`;
  правила чатов — `docs/process/`. Читать, только если промпт велит.
