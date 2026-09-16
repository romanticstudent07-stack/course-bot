# course-bot

Реализация Telegram-курса: Mini App + бот + backend.

**Источник истины по архитектуре** — отдельный репозиторий
[DOCS-course-bot](https://github.com/romanticstudent07-stack/DOCS-course-bot).
Код без сверки с архитектурой не пишется.

Автоматическое зеркало архитектуры лежит в `docs/architecture/`
и обновляется workflow `.github/workflows/sync-architecture.yml`.
**Папка `docs/architecture/` — read-only.** Все изменения архитектуры
делаются в `DOCS-course-bot`.

## Структура

| Путь | Что здесь |
|---|---|
| `apps/miniapp/` | Клиент Mini App: React 18 + Vite + TypeScript |
| `apps/bot/` | Telegram-бот: Python 3.12 + aiogram 3 |
| `apps/api/` | Backend: FastAPI + PostgreSQL 16 + Redis 7 |
| `apps/api/content/` | YAML-тексты заданий (seed для `text_registry`) |
| `apps/api/migrations/` | Миграции БД (Alembic) |
| `packages/shared/` | OpenAPI-контракт `/miniapp/v1`, общие типы |
| `infra/` | docker-compose для локального запуска |
| `docs/architecture/` | Read-only зеркало DOCS-course-bot |
| `docs/DEFECTS-FOUND.md` | Расхождения архитектуры с реальностью |
| `.github/workflows/` | CI + sync-architecture.yml |
| `.genspark/rules.md` | Жёсткие правила для Genspark Code |

## Принцип разделения

Проект — **Mini App-first**. Основной пользовательский путь в Mini App.
Бот держит только то, что нельзя перенести: уведомления, admin-команды
владельца, доставку ссылки на Mini App, callback-кнопки.

Панель Автора (Блок 17, 35 команд) — **только в боте**, в Mini App не переносится.

## Где что хранится

- **Тексты заданий** — в этом репо (`apps/api/content/`), источник истины
  в рантайме — таблица `text_registry`.
- **Видео и медиа курса** — только во внешнем публичном Telegram-канале.
  Бот не хостит медиа и не отдаёт `file_id`.
- **S3** — фото участника, выгрузки по 152-ФЗ, аудит-логи.
  Не контент курса.

## Оплата

На старте — **вне Telegram Mini App**:
- YooKassa для самозанятого (платёжная ссылка на email/в чат бота);
- либо перевод на карту с ручной сверкой Автора.

После подтверждения оплаты бот выдаёт инвайт-ссылку на запуск Mini App.
Внутри Mini App никаких платёжных экранов быть не должно.

Позже возможна интеграция Telegram Stars для микро-платежей внутри Mini App —
это отдельное решение Автора.

## Секреты

Никогда не коммитить. Все значения — через `.env` по образцу `.env.example`.
Файл `.env` игнорируется через `.gitignore`.

## Разработка на локальном сервере

Пока проект развивается, backend работает на локальном Linux-сервере Автора.
Публичный HTTPS-webhook для Telegram проброшен через Cloudflare Tunnel
(бесплатный, стабильный, `*.trycloudflare.com` или свой домен).

Пошаговая инструкция запуска — в `infra/README.md` (создаётся в Итерации 0).

Переход на VPS/Cloud — после успешных тестов на локальном сервере.

## Ключевые правила

Полный набор правил для агентов — в `AGENTS.md` и `.genspark/rules.md`.

Кратко:
- `docs/architecture/**` — read-only, не править.
- Секреты — только через `.env`, никогда в коде.
- `initData` — валидировать только на сервере (`X-Telegram-Init-Data`),
  никогда не доверять `initDataUnsafe`.
- `client_op_id` — обязателен для всех финансовых и state-меняющих операций.
- CSP Mini App prod — `default-src 'self'` + whitelist, `unsafe-eval` запрещён.
- Панель Автора — только в боте.
- Пуш в `main` — только через PR.

## Открытые вопросы Автора

- Облачный провайдер prod: Yandex Cloud или Timeweb.
- Дефекты из `docs/DEFECTS-FOUND.md`.
