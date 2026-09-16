# AGENTS.md — course-bot

Этот файл читается AI-агентами (Genspark Code, Claude Code, Cursor, OpenAI Codex).
Формат — [agents.md](https://agents.md/), рекомендации 2026 г.

## Природа репозитория

**course-bot** — репозиторий-реализация для Telegram-курс-бота с Mini App.
Здесь живёт код: Mini App (React/Vite), бот (aiogram), backend (FastAPI + PostgreSQL + Redis).

**Источник истины** — репозиторий `romanticstudent07-stack/DOCS-course-bot`.
В настоящем репозитории его копия зеркалируется в папку `docs/architecture/` как
**read-only-зеркало** (обновляется автоматически GitHub Actions из DOCS-course-bot).

## КРИТИЧНО: папка `docs/architecture/` — только для чтения

1. Агент **читает** `docs/architecture/**` для понимания требований.
2. Агент **НИКОГДА не правит** файлы в `docs/architecture/**`.
3. При обнаружении расхождения архитектуры с реальностью — писать в
   `docs/DEFECTS-FOUND.md` (не править зеркало).
4. Любой PR, изменяющий `docs/architecture/**`, должен быть отклонён ревьюером.
5. Любое изменение архитектуры делается в репозитории DOCS-course-bot,
   потом приходит сюда PR-ом через `.github/workflows/sync-architecture.yml`.

## Ключевые точки входа (в порядке чтения)

1. `CONTEXT.md` — быстрое введение в проект (3 минуты).
2. `AGENTS.md` (этот файл) — правила работы агента.
3. `.genspark/rules.md` — жёсткие правила для Genspark Code.
4. `docs/architecture/AGENTS.md` — правила работы с архитектурой (наследуются).
5. `docs/architecture/CANONICAL-SOURCES.md` — правило «верхний файл vs подпапка (10/, 15/, 17/, 99/)».
6. `docs/architecture/normative/README.md` — старшинство нормативного стека.
7. `docs/architecture/normative/OVERRIDES.yaml` — арбитр YAML-конфликтов.
8. `docs/architecture/build/DIVISION.md` — что реализуется в Mini App, что в боте, что в API.
9. `docs/architecture/build/build-order.md` — порядок первых итераций.

## Правила старшинства (наследуются из архитектуры)

При расхождении между слоями побеждает верхний:

```
корпус v3 → И1 → И2 → И3 → И4 → Б17 → SEAM-PATCH-1 → OVERRIDES.yaml → ERRATA-UNIFIED (высшее)
```

При конфликте YAML — читать `docs/architecture/normative/OVERRIDES.yaml`.

## Что запрещено

1. **Не править `docs/architecture/**`** — это read-only зеркало.
2. **Не создавать реализацию для состояний `banned_soft` / `banned_hard`** —
   удалены Р477 (И2). Читать через `sleeping + author_pause + owner-review`.
3. **Не помещать секретные значения в код** (`BOT_TOKEN`, PSP-ключи, `initData secret`).
   Только через переменные окружения. В репо — только `.env.example` без значений.
4. **Не игнорировать `client_op_id`** при финансовых и state-меняющих операциях
   (идемпотентность).
5. **Не разрешать `unsafe-eval` в CSP** Mini App production-сборки (E2 ERRATA).
   Разрешено только в dev-режиме Vite.
6. **Не переносить Панель Автора (Блок 17) в Mini App** — по решению `DIVISION.md`.
7. **Не доверять `Telegram.WebApp.initDataUnsafe`** нигде, кроме отрисовки имени.
   Все критичные операции — только через серверную валидацию `initData`.
8. **Не выдумывать значения открытых решений Автора** (см. ниже).
9. **Не пушить в `main` напрямую** — только через PR.

## Структура репозитория (по DIVISION.md)

```
course-bot/
├── apps/
│   ├── miniapp/           React 18 + Vite + TypeScript + Zustand + tanstack-query
│   ├── bot/               Python 3.12 + aiogram 3
│   └── api/               FastAPI + PostgreSQL 16 + Redis 7 + Alembic
├── packages/
│   └── shared/            общие типы, схемы, константы
├── infra/                 docker-compose, IaC, миграции
├── docs/
│   ├── architecture/      ← read-only зеркало DOCS-course-bot (не править!)
│   └── DEFECTS-FOUND.md   ← сюда писать расхождения архитектуры с реальностью
├── .github/
│   ├── workflows/         CI + sync-architecture.yml
│   └── PULL_REQUEST_TEMPLATE.md
├── .genspark/
│   └── rules.md           жёсткие правила для Genspark Code
├── .env.example
├── .gitignore
├── AGENTS.md              этот файл
├── CONTEXT.md
└── README.md
```

## Как валидировать `initData` (единственная критичная процедура безопасности)

Каждый запрос к `/miniapp/v1/**` содержит заголовок `X-Telegram-Init-Data`. Сервер:

1. `secret_key = HMAC-SHA256(key="WebAppData", msg=BOT_TOKEN)`
2. Собрать `data_check_string`: пары `key=value` из initData (кроме `hash`),
   отсортированные по ключу, соединённые `\n`.
3. `expected_hash = HMAC-SHA256(key=secret_key, msg=data_check_string)`
4. Сравнить с `hash` из initData.
5. Проверить `auth_date` (TTL 24 ч; для `/refund`, `/erasure_*` — 1 ч).

Никогда не доверять `Telegram.WebApp.initDataUnsafe` — только серверная валидация.

## Оплата (текущее решение Автора)

Приём оплаты происходит **вне Telegram Mini App** — на отдельной оплатной ссылке
YooKassa (для самозанятого) или на карту с ручной проверкой. Внутри Telegram
Mini App никаких платёжных экранов быть не должно. После подтверждения оплаты
пользователь получает от бота инвайт-ссылку, по которой запускается Mini App.

Позже возможен перенос части оплат внутрь Mini App через Telegram Stars —
это отдельное решение Автора, до тех пор Telegram Stars НЕ используются.

## Порядок работы агента

1. Прочитать `CONTEXT.md`, потом `docs/architecture/build/DIVISION.md`.
2. Найти блок, к которому относится задача.
3. Проверить нормативные наложения через `docs/architecture/normative/OVERRIDES.yaml`
   и врезки «Переопределено/Уточнено ERRATA-UNIFIED» в шапке файла блока.
4. Реализовать в соответствующем `apps/<layer>/`.
5. При обнаружении расхождения с архитектурой — фиксировать в `docs/DEFECTS-FOUND.md`,
   **не править зеркало**.
6. Атомарные PR: одна задача — один PR. Заголовок PR = «Блок N: короткое описание».
   В описании PR перечислить, какие файлы `docs/architecture/**` прочитаны
   и какие правила ERRATA/OVERRIDES применены.

## Стек по умолчанию

- **Mini App:** React 18 + Vite + TypeScript + `@telegram-apps/sdk-react` + Zustand + tanstack-query + dexie (IndexedDB).
- **Bot:** Python 3.12 + aiogram 3.
- **Backend:** FastAPI + PostgreSQL 16 + Redis 7 + Alembic.
- **Хостинг разработки:** локальный сервер Автора (Ubuntu Server).
  Публичный webhook — через Cloudflare Tunnel / ngrok до переезда на VPS.
- **Хостинг prod:** будет выбран позже (Yandex Cloud vs Timeweb — открытый вопрос).

## Открытые вопросы Автора (агент их не решает)

- Выбор облачного провайдера prod (Yandex Cloud vs Timeweb).
- Значение `full_backup_rotation_cycle`.
- Три несовместимости Б17 (см. `docs/architecture/normative/README.md`).
- Определение ролей `finance` и `moderator`.

При задачах, задевающих эти пункты — вежливо вернуть вопрос Автору вместо угадывания.
Не заполнять пробелы правдоподобной выдумкой — это самый опасный режим отказа.

## Тесты и CI

- Тесты Mini App — Vitest + React Testing Library.
- Тесты Bot — pytest + aiogram test framework.
- Тесты Backend — pytest + httpx.
- CI-чеки — по мере поднятия pipeline.
