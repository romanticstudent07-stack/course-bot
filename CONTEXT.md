# CONTEXT.md — контекст проекта course-bot

Быстрое введение для нового читателя (или AI-агента) — читается за 3 минуты.

## Что это

**course-bot** — репозиторий-реализация проекта **Telegram-курс-бота с Mini App**.
Здесь живёт код (Mini App + бот + backend). Архитектура зеркалируется из
`DOCS-course-bot` в папку `docs/architecture/` как read-only копия.

## Что за продукт

Курс личной трансформации на 4–6 модулей (28-дневные блоки). Участник проходит
день за днём в Mini App, Автор проверяет рефлексии в Рабочей группе через бота.
Оплата — вне Mini App, через YooKassa (самозанятый) или на карту с ручной сверкой,
после чего бот выдаёт инвайт-ссылку. Система жёстко удерживает дисциплину:
3 жизни на этап, отчёт по каждому дню, дедлайны по серверному времени.

## Где что лежит

```
course-bot/
├── apps/miniapp/           клиент (React + Vite + TypeScript)
├── apps/bot/               Telegram-бот (Python + aiogram 3)
├── apps/api/               backend (FastAPI + PostgreSQL 16 + Redis 7)
├── packages/shared/        общие типы и схемы
├── infra/                  docker-compose + миграции + IaC
├── docs/architecture/      ← read-only зеркало DOCS-course-bot (не править!)
└── docs/DEFECTS-FOUND.md   ← сюда пишем расхождения архитектуры с реальностью
```

## Как читать архитектуру

**Единственный источник истины** — папка `docs/architecture/`.
Она автоматически синхронизируется из `DOCS-course-bot` через
GitHub Actions (`.github/workflows/sync-architecture.yml`).

Правило «верхний файл vs подпапка» для блоков 10/, 15/, 17/, 99/ —
см. `docs/architecture/CANONICAL-SOURCES.md`.

При конфликте YAML-описаний — читать `docs/architecture/normative/OVERRIDES.yaml`.

Старшинство:
```
корпус v3 → И1 → И2 → И3 → И4 → Б17 → SEAM-PATCH-1 → OVERRIDES.yaml → ERRATA-UNIFIED (высшее)
```

## Ключевые архитектурные факты (напоминание)

- **Mini App-first.** Основной пользовательский опыт — в Mini App. Бот держит
  уведомления, admin-команды и Menu Button.
- **Точка создания участника** — first-launch Mini App (SEAM-PATCH-1).
- **35 admin-команд** в реестре Б17. Всегда через whitelist + hard-confirm (E3 ERRATA).
- **`participant_state`** — обычная таблица с проектором (E1 ERRATA),
  не materialized_view.
- **CSP Mini App** — `default-src 'self'` с белым списком, `unsafe-eval` запрещён (E2 ERRATA).
- **`text_registry`** — единый источник текстов, три тона, `{домен}.{имя}` (И4).
- **22 риска** в реестре (RISK-L-01…22), каноническое число (E4 NOTE1).
- **Оплата — вне Mini App**, через YooKassa/карту, с ручной или webhook-сверкой.

## Разработка на локальном сервере Автора

Пока идёт разработка, backend работает на локальном Linux-сервере Автора,
а публичный HTTPS-webhook для Telegram проброшен через Cloudflare Tunnel
(бесплатно, HTTPS, стабильный домен `*.trycloudflare.com` или свой).

Инструкция по подключению Cloudflare Tunnel — в `infra/README.md`
(будет создана в Итерации 0).

Переход на VPS — после успешных тестов на локальном сервере.

## Что делать агенту-новичку

1. Прочитать этот файл (уже сделали).
2. Открыть `AGENTS.md` — правила работы.
3. Открыть `.genspark/rules.md` — жёсткие правила Genspark.
4. Открыть `docs/architecture/CANONICAL-SOURCES.md` —
   правило «верхний файл vs подпапка» для блоков 10/, 15/, 17/, 99/.
5. Открыть `docs/architecture/build/DIVISION.md` —
   карта «блок → уровень реализации».
6. Открыть `docs/architecture/build/build-order.md` —
   порядок первых итераций.
7. Дождаться промпта от Автора и начать с первой итерации.

## Что НЕ делать агенту

- **Не править `docs/architecture/**`** — это read-only зеркало.
- **Не выдумывать значения открытых решений** (см. AGENTS.md,
  «Открытые вопросы Автору»).
- **Не создавать реализацию `banned_soft`/`banned_hard`** — их нет,
  читать через `sleeping + author_pause + owner-review`.
- **Не помещать секреты в код** — только `.env` переменные,
  а в репо только `.env.example`.
- **Не пушить в `main` напрямую** — только через PR.
- **Не встраивать оплату внутрь Mini App** — оплата пока только снаружи.
