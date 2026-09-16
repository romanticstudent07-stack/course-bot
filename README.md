# course-bot

Реализация Telegram-курса: Mini App + бот + backend.

**Источник истины по архитектуре** — отдельный репозиторий
[DOCS-course-bot](https://github.com/romanticstudent07-stack/DOCS-course-bot).
Код без сверки с архитектурой не пишется.

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
| `docs/` | Зеркало архитектуры (read-only) + дефекты |
| `.github/workflows/` | CI-проверки |

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
- **S3** — фото участника, выгрузки по 152-ФЗ, аудит-логи. Не контент курса.

## Секреты

Никогда не коммитить. Все значения — через `.env` по образцу `.env.example`.

## Открытые вопросы Автора (блокируют работу)

- Облачный провайдер: Yandex Cloud или Timeweb.
- PSP и вопрос Telegram Stars для цифровых товаров.
- Дефект D-1 (см. `docs/DEFECTS-FOUND.md`).
