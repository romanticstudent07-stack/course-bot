# AGENT-BRIEF.md — шпаргалка для AI-агента (читать ПЕРВОЙ)

Версия 2.3 · 19.10.2026. Актуальный hash main — в промпте или в `docs/STATE.md`.
Заменяет обязательное чтение 9 файлов. Если промпт задачи противоречит этому
файлу — прав промпт. Если этот файл противоречит AGENTS.md / CONTEXT.md в части
«что читать» и «как тестировать» — прав этот файл.

## 1. Как работать (экономия кредитов)

- Читай ТОЛЬКО этот файл + файлы из раздела «ЧТО ПРОЧИТАТЬ» в промпте.
- `docs/architecture/**` не открывай: нужные выдержки уже в промпте.
  Выдержки не хватает и без неё работу не сделать → стоп, один короткий вопрос.
- Правило К (22.10) — docs/process/CANON-CHECK.md, раздел «Агент…»: догадки о механике в код не вносить; выдержки не хватает или она расходится с кодом → вопрос ШТАБу в «Вопросы» ИТОГА.
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
- CI НЕ ЖДАТЬ (решение Автора 21.10): после push сразу пиши ИТОГ и заканчивай. gh run watch, gh pr checks --watch, опрос статуса проверок и ожидание — запрещены. CI проверяет Автор.

## 6. Что уже есть в коде

Сводка по коду (main 9f3746a). Подробности — docstring модулей: их читать, если файл в «ЧТО ПРОЧИТАТЬ».

- `apps/api/main.py` — сборка приложения. Все `/miniapp/v1/**` идут ТОЛЬКО через общий роутер
  `build_miniapp_v1_router`: сначала `require_init_data`, затем `rate_limit` (401 раньше 429).
  Новые роутеры Mini App добавлять туда же. `/healthz` и `/security/csp-report` — без initData
  и без rate-limit. `app/errors.py` — обработчики ошибок (подключены в main.py).
- `app/telegram_init_data.py` — проверка initData (HMAC-SHA256 + TTL), только stdlib.
- `app/rate_limit.py` — rate-limit (B-1): Redis, окно 1 мин на tg_user_id из проверенной initData,
  превышение → 429 `RATE_LIMITED` + `Retry-After`; Redis недоступен → fail-open (WARNING с именем
  класса ошибки). Самопроверка: `python -m app.rate_limit selftest`.
- `app/config.py` — настройки из переменных окружения; DSN-поля скрыты в repr/str (B-3c).
  `sqlalchemy_dsn()` — api (DATABASE_URL), `projector_dsn()`, `migrations_dsn()` — свои DSN.
- `app/db/` — модели и сессия (`get_engine`, `get_db_session`).
- `app/participants.py` — `tg_user_registry`: get_or_create (строка блокируется до commit),
  `find_active_participant` (tombstoned_at IS NULL), `format_short_no`.
- `app/consent_status.py` — действует ли согласие (только чтение): последнее событие по kind —
  give, text_key и text_snapshot совпадают с текущим текстом. `CONSENT_TEXT_KEYS`, `REASONS`.
- `app/routers/onboarding.py`:
  - `POST /miniapp/v1/onboarding/first-launch` — единственная точка создания участника (SEAM-1).
    Порядок не менять: initData → тело → 18+ без БД (403) → C0 и C1 (422) → ОДНА транзакция:
    тексты → участник → give в `consent_events` (только недействующие согласия) →
    `participant_events` `mini_app_first_consent` (только если pid создан этим вызовом) → commit.
  - `GET /miniapp/v1/onboarding/status` — `returning` (+ short_no) / `reconsent` (+ reasons) /
    `new`; только чтение; pid не отдаётся никогда.
- `app/routers/consents.py` — `GET /miniapp/v1/consents`: свои согласия, только чтение,
  по каждому kind решает последнее событие; нет участника → `[]`.
- `app/routers/texts.py` — `GET /miniapp/v1/texts/{key}` и `POST /miniapp/v1/texts/bulk`
  (до 100 ключей): тексты из `text_registry`, `notes` наружу не отдаются; 404 `TEXT_NOT_FOUND`.
- `app/routers/day.py` — `GET /miniapp/v1/day/current`; `POST /miniapp/v1/day/test-enter`
  (только при `DAY_TEST_ENTRY_ENABLED=true`, по умолчанию false); `PUT /miniapp/v1/day/marks`;
  `POST /miniapp/v1/day/report/submit` (`X-Client-Op-Id`, `idempotency_keys`).
- `app/participant_lock.py` — замок `pg_advisory_xact_lock(hashtext('participant:' || pid))`;
  `active_pid_locked`: найти участника → замок → повторная проверка tombstoned_at IS NULL.
- `app/day_content.py`, `app/day_keys.py`, `app/day_report.py` — контент дня (заглушки
  `apps/api/content/module_1`), ключи и отчёт дня.
- `app/routers/security.py` — `POST /security/csp-report` → 204, тело в лог (до 16 КБ).
- `app/texts.py` — seed `apps/api/config/texts/*.json` (только заглушки) и загрузчик
  `python -m app.texts load`; на сервере — только через одноразовый сервис `migrate`.
- `app/projector.py` — единственный писатель `participant_state` (E1 / INV-1):
  `python -m app.projector run | once`; битый DSN или нет драйвера → WARNING с именем класса, код 1.
  API в `participant_state` не пишет никогда.
- Проектор: `PROJECTOR_VERSION = 2`; знает kinds `mini_app_first_consent`, `day_entered`,
  `day_report_submitted`.
- Роль БД `app_bot` создана миграцией 0009, но кода БД в `apps/bot` пока нет.
- Миграции: от `0001_init` до `0009_app_bot` (последняя — в `docs/STATE.md`).
  Таблиц в public (без alembic_version): 15; полный список — `apps/api/tests/expected_tables.txt`.
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
- В Mini App нет платёжных экранов и упоминаний оплаты (Р-1); нет фото участников, согласия C5,
  photo-экранов (Р-3); нет экрана настроек уведомлений (Р-6); нет S3 pre-signed URL для
  материалов — медиа только во внешнем Telegram-канале (Р-5); паузы (Р-6а) не построены —
  не реализовывать без карточки.

## 8. Окружение (значения — только из `.env`)

- Внутри compose-сети: Postgres `db:5432`, Redis `redis:6379`, Garage (S3) `garage:3900`, API `api:8080`.
- С хоста сервера: Postgres `127.0.0.1:5435`, Redis `127.0.0.1:6382`, API `127.0.0.1:8080`,
  Mini App (nginx) `127.0.0.1:5173`, S3 `127.0.0.1:9000`. Все порты — только 127.0.0.1.
- nginx Mini App проксирует `/miniapp/v1/**` и `/security/csp-report` в `api:8080`.
- TZ контейнеров — Europe/Moscow. S3 в dev — Garage (MinIO не возвращать).

## 9. Открытые решения Автора — агент их НЕ решает

Решённое — docs/STATE.md, «Решения, перекрывающие канон», и docs/decisions/R-2026-10-*.md; они главнее docs/architecture/**.
Открыто: план Б по Telegram в РФ (Р-11: зарубежный бот-слой + уведомление РКН, 152-ФЗ — юристу);
модель авторизации к проду — механизм продления `session_jwt` (D-9, Р-12); PITR у Timeweb
и достаточность 30 дней хранения бэкапов — к 0-Б и юристу (Р-13); три несовместимости Б17;
роли `finance` и `moderator`.
Блокеры B-1 (rate-limit), B-2 (согласия до создания pid) и B-3 (роли/GRANT БД) закрыты
(B-3 — 14.10.2026; подробности — `docs/STATE.md`).

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
- Миграция добавляет или удаляет таблицы → в том же PR `apps/api/tests/expected_tables.txt`
  с полным новым списком таблиц (по нему CI сверяет БД; ci.yml не трогать).
- Новый `*.sh` → `chmod +x <файл>` до коммита: `tools/check.sh` проверяет бит exec и окончания строк LF.
- Код пакета не переписывать и не «улучшать». Каждое отличие от пакета — перечислить в описании PR.
- Состояние проекта — `docs/STATE.md`; карточки задач — `docs/tasks/<id>.md`;
  правила чатов — `docs/process/`. Читать, только если промпт велит.
