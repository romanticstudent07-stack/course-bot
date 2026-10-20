# AGENTS.md — course-bot

Этот файл читается AI-агентами (Genspark Code, Claude Code, Cursor, OpenAI Codex).
Формат — [agents.md](https://agents.md/), рекомендации 2026 г.

## Природа репозитория

**course-bot** — репозиторий-реализация для Telegram-курс-бота с Mini App.
Здесь живёт код: Mini App (React/Vite), бот (aiogram), backend (FastAPI + PostgreSQL + Redis).

**Источник истины** — репозиторий `romanticstudent07-stack/DOCS-course-bot`.
В настоящем репозитории его копия зеркалируется в папку `docs/architecture/` как
**read-only-зеркало** (обновляется автоматически GitHub Actions из DOCS-course-bot).
Решения Автора, принятые до правки канона, — `docs/decisions/R-2026-10-*.md`
и `docs/STATE.md` («Решения, перекрывающие канон»); при расхождении они главнее зеркала.

## КРИТИЧНО: папка `docs/architecture/` — только для чтения

1. Агент читает `docs/architecture/**` ТОЛЬКО если промпт прямо велит (режим Р2).
   Обычно нужные выдержки уже в промпте или в карточке `docs/tasks/<id>.md`.
2. Агент **НИКОГДА не правит** файлы в `docs/architecture/**`.
3. При обнаружении расхождения архитектуры с реальностью — писать в
   `docs/DEFECTS-FOUND.md` (не править зеркало).
4. Любой PR, изменяющий `docs/architecture/**`, должен быть отклонён ревьюером.
5. Любое изменение архитектуры делается в репозитории DOCS-course-bot,
   потом приходит сюда PR-ом через `.github/workflows/sync-architecture.yml`.

## Обязательная активация локальных git-хуков

Сразу после клона (одноразово):

    git config core.hooksPath .githooks
    chmod +x .githooks/pre-commit

Без этой команды `.githooks/pre-commit` не работает, и защита от случайного
коммита в `docs/architecture/**` и `.env` не активна. Агент, работающий локально
(например, через Genspark Code с sandbox), должен выполнить эту команду
в начале сессии.

## Ключевые точки входа (в порядке чтения)

1. `AGENT-BRIEF.md` — ВСЕГДА первым. В части «что читать» и «как тестировать» он главнее этого файла.
2. Файлы из раздела «ЧТО ПРОЧИТАТЬ» в промпте или карточка задачи `docs/tasks/<id>.md`.
3. `docs/STATE.md` — текущее состояние проекта (если промпт велит).

Полный список — ТОЛЬКО если промпт прямо велит (режим Р2, новая архитектурная область):
`CONTEXT.md` → `AGENTS.md` → `.genspark/rules.md` → `docs/architecture/AGENTS.source.md` →
`docs/architecture/CANONICAL-SOURCES.md` → `docs/architecture/normative/README.md` →
`docs/architecture/normative/OVERRIDES.yaml` → `docs/architecture/build/DIVISION.md` →
`docs/architecture/build/build-order.md` → `infra/SERVER-IRONCLAD.md`.

## Правила старшинства (наследуются из архитектуры)

При расхождении между слоями побеждает верхний:

    корпус v3 → И1 → И2 → И3 → И4 → Б17 → SEAM-PATCH-1 → OVERRIDES.yaml → ERRATA-UNIFIED (высшее)

При конфликте YAML — читать `docs/architecture/normative/OVERRIDES.yaml`.

## Что запрещено

1. **Не править `docs/architecture/**`** — это read-only зеркало.
2. **Не создавать реализацию для состояний `banned_soft` / `banned_hard`** —
   удалены Р477 (И2). Читать через `sleeping + author_pause + owner-review`.
3. **Не помещать секретные значения в код** (`BOT_TOKEN`, PSP-ключи, `initData secret`,
   реквизиты карты). Только через переменные окружения. В репо — только `.env.example`.
4. **Не игнорировать `client_op_id`** при финансовых и state-меняющих операциях
   (идемпотентность).
5. **Не разрешать `unsafe-eval` в CSP** Mini App production-сборки (E2 ERRATA).
   Разрешено только в dev-режиме Vite.
6. **Не переносить Панель Автора (Блок 17) в Mini App** — по решению `DIVISION.md`.
7. **Не доверять `Telegram.WebApp.initDataUnsafe`** нигде, кроме отрисовки имени.
   Все критичные операции — только через серверную валидацию `initData`.
8. **Не выдумывать значения открытых решений Автора** (см. ниже).
9. **Не пушить в `main` напрямую** — только через PR.
10. **Не встраивать платёжные экраны и упоминания оплаты в Mini App (Р-1)**: оплата —
    в личной переписке с Автором, вне продукта.
11. **Не возвращаться к MinIO** — с октября 2025 бесплатных Docker-образов и бинарников
    community-версии нет (только исходники; issue minio/minio #21647), 25.04.2026 репозиторий
    minio/minio архивирован. Используем Garage (`dxflrs/garage`) как S3 в dev.

## Структура репозитория (по DIVISION.md)

    course-bot/
    ├── apps/
    │   ├── miniapp/           React 18 + Vite + TypeScript + Zustand + tanstack-query
    │   ├── bot/               Python 3.12 + aiogram 3
    │   └── api/               FastAPI + PostgreSQL 16 + Redis 7 + Alembic
    ├── packages/
    │   └── shared/            общие типы, схемы, константы, OpenAPI-контракт
    ├── infra/                 docker-compose, IaC, миграции, garage/, инструкции dev-входа (Tailscale serve)
    ├── docs/
    │   ├── architecture/      ← read-only зеркало DOCS-course-bot (не править!)
    │   └── DEFECTS-FOUND.md   ← сюда писать расхождения архитектуры с реальностью
    ├── .github/
    │   ├── workflows/         CI + sync-architecture.yml
    │   └── PULL_REQUEST_TEMPLATE.md
    ├── .githooks/
    │   └── pre-commit         защита от коммитов в docs/architecture/ и .env
    ├── .genspark/
    │   └── rules.md           жёсткие правила для Genspark Code
    ├── .env.example
    ├── .gitignore
    ├── AGENTS.md              этот файл
    ├── CONTEXT.md
    └── README.md

## Как валидировать `initData` (единственная критичная процедура безопасности)

Каждый запрос к `/miniapp/v1/**` содержит заголовок `X-Telegram-Init-Data`. Сервер:

1. `secret_key = HMAC-SHA256(key="WebAppData", msg=BOT_TOKEN)`
2. Собрать `data_check_string`: пары `key=value` из initData (кроме `hash`),
   отсортированные по ключу, соединённые `\n`.
3. `expected_hash = HMAC-SHA256(key=secret_key, msg=data_check_string)`
4. Сравнить с `hash` из initData.
5. Проверить `auth_date` (TTL 24 ч; для `/refund`, `/erasure_*` — 1 ч).

Никогда не доверять `Telegram.WebApp.initDataUnsafe` — только серверная валидация.

## Оплата и доступ участника (Р-1, Р-2, Р-4)

Оплата полностью вне продукта (Р-1, 17.10.2026): в Mini App нет платёжных экранов
и упоминаний оплаты (`onb.payment`, `payment.*` не делать). Оплата — в личной переписке
с Автором, доступ к курсу Автор выдаёт лично. Виджет PSP внутри Mini App не делать никогда.

Схема доступа (Р-2, 17.10.2026), кратко:

1. Оплата — в личной переписке с Автором (вне продукта).
2. Автор шлёт участнику ссылку на бота и персональное кодовое слово.
3. Участник нажимает Start.
4. Бот просит ввести промокод.
5. Участник пишет своё слово.
6. Бот шлёт в админ-тему Рабочей группы «слово + ID» с кнопками [Выдать доступ] / [Запретить].
7. После «Выдать доступ» бот пишет участнику, что можно продолжать.
8. Онбординг в Mini App: возраст → согласия → участник создан (pid, SEAM-1). Без выданного
   доступа — нейтральный экран «доступ не открыт», участник не создаётся.

Флажок «доступ выдан» хранится в новой таблице по `tg_user_id` (миграция — в задаче Р-2,
после send-1, с РЕВЬЮЕРОМ). Пока не построено — не реализовывать без карточки.
Имя команды Панели и тексты сообщений — в карточке задачи.

Будущее — YooKassa (основной) / CloudPayments (запасной) только на внешнем сайте, вне Telegram (Р-4).
Возвраты — вручную; `/refund` Панели Автора — учётная операция без PSP. Переменные `PSP_*`
в `.env.example` остаются. Сейчас ничего платёжного не строить.

## Порядок работы агента

1. Прочитать `AGENT-BRIEF.md`, затем файлы из «ЧТО ПРОЧИТАТЬ» в промпте
   (или карточку `docs/tasks/<id>.md`). Остальное — только по прямому указанию промпта.
2. Если в промпте дан готовый пакет (режим Р1-П) — разложить его `python3 tools/unpack.py`,
   прогнать `bash tools/check.sh <цели>`, чинить только упавшее (`AGENT-BRIEF.md`, раздел 11).
3. Реализовать в соответствующем `apps/<layer>/`.
4. При обнаружении расхождения с архитектурой — фиксировать в `docs/DEFECTS-FOUND.md`,
   **не править зеркало**.
5. Одна задача — один PR. Заголовок и описание PR — по промпту и `AGENT-BRIEF.md`, раздел 10.

## Стек по умолчанию

- **Mini App:** React 18 + Vite + TypeScript + `@telegram-apps/sdk-react` + Zustand + tanstack-query + dexie (IndexedDB).
- **Bot:** Python 3.12 + aiogram 3.
- **Backend:** FastAPI + PostgreSQL 16 + Redis 7 + Alembic.
- **S3 dev:** Garage (`dxflrs/garage`) — S3-совместимое хранилище, локально в compose.
- **S3 prod:** Timeweb Object Storage, только бэкапы и WORM-аудит (Р-10).
  Переезд dev → prod — смена `S3_ENDPOINT` в `.env`, код на `boto3` не переписывается.
- **Хостинг разработки:** локальный сервер Автора (Ubuntu Server IRONCLAD).
  Бот — на long polling, webhook не ставится (D-4). Dev-вход в Mini App —
  Tailscale serve (только tailnet, только Автор); Cloudflare Tunnel не используется.
- **Вход prod / внешние тестировщики:** позже — туннель дом→VPS Timeweb
  через autossh или WireGuard (D-5, Р-9).
- **Хостинг prod:** Timeweb Cloud: VPS + managed PostgreSQL; Yandex Cloud — запасной (Р-9).

## Открытые вопросы Автора (агент их не решает)

- Три несовместимости Б17 (см. `docs/architecture/normative/README.md`).
- Определение ролей `finance` и `moderator`.
- Решённое — `docs/decisions/R-2026-10-*.md`.

Полный трекер открытых вопросов — **GitHub Issues** репозитория с меткой
`author-decision`. При задачах, задевающих эти пункты — вежливо вернуть вопрос
Автору вместо угадывания. Не заполнять пробелы правдоподобной выдумкой —
это самый опасный режим отказа.

## Тесты и CI

- Тесты Mini App — Vitest + React Testing Library.
- Тесты Bot — pytest + aiogram test framework.
- Тесты Backend — pytest + httpx.
- Быстрые тесты без БД: `bash tools/check.sh` (Codespaces или sandbox).
- CI (`.github/workflows/ci.yml`) — 7 проверок на каждый PR: api (pytest с живым postgres:16
  + миграции), bot, miniapp, docker ×3, guard. Тесты с БД — только в CI.
- Красный CI не мержится.
