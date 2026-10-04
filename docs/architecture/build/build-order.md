---
file: build/build-order.md
block: "—"
title: "Порядок сборки: зависимости, миграции, синтетический запуск"
status: скелет
doc_version: "build-order v1.3"
contains: [4 уровня сборки, 6 итераций Mini App-first, boot-gate, синтетический запуск, локальный старт IRONCLAD]
---

# Порядок сборки

Скелет для агента бота: с чего начинать реализацию, чтобы система собралась без круговых зависимостей.

## Уровень 0 — инфраструктура

1. PostgreSQL (основная БД) + PITR-настройка.
2. S3-совместимое хранилище (`{s3-domain-ru}` — до решения Автора: Yandex Cloud / Timeweb Cloud).
3. Redis (только буфер аналитики, критичные события — синхронно в PG, см. `critical_writes: synchronous_postgres`).
4. Object Lock отключён на бакетах фото; `COMPLIANCE`/WORM на бакетах аудита.

### Локальный старт на сервере Автора (IRONCLAD) — до первого прода

Уровень 0 разделён на две подступени, чтобы разработка велась на сервере Автора
до принятия решения об облачном провайдере:

- **Итерация 0-А (локальная инфра)** — Postgres 16 / Redis 7 / Garage (S3-совместимый, образ `dxflrs/garage`)
  в контейнерах на сервере Автора, публичный HTTPS через Cloudflare Tunnel.
- **Итерация 0-Б (переезд на облако)** — Yandex Cloud / Timeweb / VK Cloud, Managed
  PostgreSQL + Object Storage, реальный `{s3-domain-ru}`.

Локальный стек описан в репозитории реализации в файлах:
`infra/SERVER-IRONCLAD.md`, `infra/docker-compose.dev.yml`, `infra/CLOUDFLARE-TUNNEL.md`.
Правило нулевых потерь: переход 0-А → 0-Б **не меняет контракты** (API, БД, тексты).
Меняется только инфраструктура (провайдер, deployment, backup).

## Уровень 1 — ядро данных

1. DDL из [db-schema.sql](db-schema.sql) — эталонные ядра (8 критичных таблиц + 6 ролей).
   Полный DDL для остальных ~25 таблиц (список — [db-tables-index.md](db-tables-index.md))
   наполняется как **alembic-миграции** в репозитории `course-bot` во время Итерации 1.
   Причина: оригинал Архитектуры не содержит полного DDL одним куском; здесь только те таблицы,
   для которых оригинал даёт колонки и типы.
2. `outbox` + `dlq` + `consumer_offsets` (Б15/И2) — уже в `db-schema.sql`.
3. `text_registry` — пустой + seed из блоков 2, 3, 5, 9, 10, 15, 16 после юридической вычитки (И4).
   Валидация seed'а — по JSON-Schema [config-schemas/text_registry.schema.json](config-schemas/text_registry.schema.json).

## Уровень 2 — проекторы и саги

1. `participant_state_projector` (владелец Б10) — читает `state_transition_log`, пишет `participant_state`.
2. Refund Saga (Б16 + И3).
3. Photo Ingest Saga (Б15 + И3).
4. **Red Flags Protocol** (Б5 + И3, авто-эскалация за 60 сек в `sleeping` + `author_pause(reason_class=red_flag)`
   + шаблон экстренных контактов). **Не нарушает NR-17.14** («бот никогда не банит»),
   потому что переводит участника в `sleeping`, а не в `banned_*` — состояния `banned_*` вообще
   удалены из FSM (Р477, И2). См. оригинал Архитектуры, стр. 293–294, 350.
5. Export Worker (Б14 + И3, `data_export_event`).

## Уровень 3 — API и клиенты

1. Telegram Bot API — реализация 35 UI-команд из [bot-commands-registry.yaml](bot-commands-registry.yaml).
   Маппинг «UI-команда → backend capability» — [commands-mapping.md](commands-mapping.md).
   Backend-контракт `block_17.commands` (25 внутренних операций) — [../17/17-99-yaml-full.md](../17/17-99-yaml-full.md).
2. Mini App API — [miniapp-api-contract.yaml](miniapp-api-contract.yaml), 8+ эндпоинтов, CSP `default-src 'self'` (E2).
3. Панель Автора (Б17) — 6 поверхностей администрирования.

## Уровень 4 — гейт прод-запуска (boot-gate)

Не запускать в прод, пока не закрыт каждый из семи пунктов [C-registries.md#8-boot-gate](../appendix/C-registries.md):

1. Все 15+ текстов `legal_status: pre-legal-review` подписаны юристом.
2. Д-40 закрыт (РКН реальным событием).
3. Д-30 закрыт (DPA с провайдером).
4. Д-31 закрыт (модель угроз, УЗ-3).
5. `{s3-domain-ru}` заменён на реальный домен.
6. `full_backup_rotation_cycle` заменён на число (более строгая граница A4 с учётом WAL).
7. Все `pre-legal-review` сняты.

## Открытые несовместимости, которые НЕ реализовывать до решения Автора

Три несовместимости Б7↔И3 (из шапки [../17-author-panel.md](../17-author-panel.md)):

1. `/erasure_finalize_before_cooling_off` **не реализовывать** до решения Автора (противоречит
   14-дневной отсрочке стирания И3; до решения — использовать более строгое требование И3).
2. Роли `finance` и `moderator` **не разграничивать** до решения Автора — использовать роль
   `owner` для всех финансовых и модераторских операций.
3. `/block`/`/unblock` — реализовывать как перевод в `sleeping + author_pause(reason_class=block)`
   (Р477, И2 стр. 323), а НЕ в `banned_*` (эти состояния удалены из FSM).

Автоэскалация в 60 сек **не относится** к этим трём несовместимостям — она разрешена в
Уровне 2, шаг 4 (см. выше).

## Порядок первых итераций (Mini App-first)

Приоритет тестового запуска — Mini App-первый экран участника. Бот и backend поднимаются в объёме, необходимом для этого пути.

### Итерация 0-А — локальная инфра на сервере Автора (1-2 дня)

Работает на сервере IRONCLAD, без облачных зависимостей. См. `infra/SERVER-IRONCLAD.md`.

1. Docker + Docker Compose v2 + `cloudflared` — установлены на сервере (уже готово).
2. Telegram Bot регистрация в BotFather: `/newbot`. `/newapp` — только если нужна прямая ссылка вида `t.me/<бот>/<app>`; `/setdomain` — настройка Telegram Login Widget, для Mini App не нужна.
3. Cloudflare Tunnel — именованный туннель на свой домен
   (см. `infra/CLOUDFLARE-TUNNEL.md` в репо реализации).
4. Vite + React + TypeScript скелет через `npx @telegram-apps/create-mini-app` —
   в multi-stage Docker (`node:20-alpine`), т.к. Node на сервере не установлен.
5. FastAPI скелет в `apps/api/`: `main.py`, `/healthz`, alembic init.
6. aiogram 3 скелет в `apps/bot/`: `/start` + Menu Button на `WEBAPP_URL`.
7. `infra/docker-compose.dev.yml` — сервисы `db`, `redis`, `garage` (первый бакет создаётся при старте, init-контейнер не нужен),
   позже `api`, `bot`. Всё на 127.0.0.1 (правило IRONCLAD), с лимитами памяти.
8. Проверка: `docker compose up -d`, бот отвечает на `/start`, Mini App открывается
   по Menu Button через HTTPS туннеля.

### Итерация 0-Б — переезд на облако (после Итерации 0-А, 1 неделя)

Запускается только после успешных локальных тестов Итераций 0-А … 3.
Параллельно с Итерацией 4 (оплата).

1. Yandex Cloud аккаунт + Managed PostgreSQL + Object Storage.
2. Telegram Bot регистрация в BotFather: `/newbot`. Menu Button бот ставит сам через Bot API из URL Mini App (`WEBAPP_URL` в course-bot) — `/setmenubutton` не нужен; `/newapp` — только для прямой ссылки `t.me/<бот>/<app>`; `/setdomain` — только для Login Widget.
3. Vite + React + TypeScript скелет через `npx @telegram-apps/create-mini-app`.
4. FastAPI скелет + alembic + docker-compose.

### Итерация 1 — онбординг (SEAM-1) (2 недели)

**Mini App:**
- Экраны `onb.welcome` → `onb.age-gate` → `onb.consent-152fz` → `onb.offer` → `onb.payment` → `onb.form` → `onb.checkup` → `onb.rules`.
- Валидация `initData` на сервере (эндпоинт `/miniapp/v1/onboarding/first-launch`).
- IndexedDB для черновиков анкеты.

**Bot:**
- `/start` в приватном чате → приветствие + Menu Button.
- Fallback: «Установите последнюю версию Telegram и откройте кнопку меню».

**Backend:**
- alembic-миграции для остальных таблиц из [db-tables-index.md](db-tables-index.md).
- Таблицы `tg_user_registry`, `participant_state`, `role_capability_matrix`.
- Проектор `participant_state_projector`.
- Стек `text_registry` минимальный (только тексты онбординга), валидация — по JSON-Schema.

### Итерация 2 — дневной модуль (2 недели)

**Mini App:** `day.current` + отправка отчёта + счётчик жизней.
**Bot:** утренний старт-пуш, напоминания-лестница.
**Backend:** П-31, life-ops атомарность, `state_transition_log`.

### Итерация 3 — Чек-Ап и Карточка (2 недели)

**Mini App:** `me.card`, `me.consents`, `me.change-map`, `me.settings-notifications`.
**Bot:** `/card <@user>` для владельца в Рабочей группе.
**Backend:** генерация Карточки на лету, аудит `privacy_audit_log`.

### Итерация 4 — оплата и refund (2 недели)

**Mini App:** `payment.pay`, `payment.refund`, `payment.act`.
**Bot:** reply-команда `/refund` с hard-confirm.
**Backend:** Refund Saga (И3), интеграция с PSP (YooKassa/CloudPayments), retention `refund_details`.

### Итерация 5 — фото и хранение (2 недели)

**Mini App:** `content.photo-submit` + деконструкция pre-signed URL.
**Bot:** deep-link «Открыть материал».
**Backend:** Photo Ingest Saga, S3 bucket без Object Lock (для стирания), WORM на аудите.

### Итерация 6 — Панель Автора (2 недели)

**Bot целиком:** реестр 35 UI-команд из [bot-commands-registry.yaml](bot-commands-registry.yaml),
маппинг на backend capabilities из [commands-mapping.md](commands-mapping.md),
hard-confirm (E3), whitelist admin-ID, дашборд владельца, palette.
**Backend:** `admin_action_log`, `role_capability_matrix`, `hard_confirm_phrases`.

## Минимальный синтетический запуск (для приёмки)

```
1) pg + s3-mock + redis
2) DDL (db-schema.sql — 8 таблиц + alembic для остальных) + seed text_registry
3) participant_state_projector
4) один stub-эндпоинт Mini App + ручной онбординг из бот-диалога (для тестов)
5) refund saga в dry-run режиме
6) панель Автора (только whitelist из feature flags)
```

`ready_for_synthetic_launch: yes` — при выполнении всех шести пунктов выше.

## Переменные окружения (минимум)

- `BOT_TOKEN` — Telegram Bot API.
- `PG_DSN` — DSN основной БД.
- `PG_DSN_READER` — DSN read-replica для аналитики.
- `S3_ENDPOINT` — `{s3-domain-ru}` (после решения Автора).
- `S3_ACCESS_KEY`, `S3_SECRET_KEY` — секреты S3.
- `REDIS_URL` — Redis (только буфер).
- `MINIAPP_URL` — URL Mini App (в РФ).
- `WHITELIST_ADMIN_IDS` — список tg_user_id Автора и партнёров.
- `FEATURE_FLAGS` — `miniapp_enabled`, `broadcast_enabled` и т.д.
- `LEGAL_GATE_MODE` — `blocking` (прод) или `advisory` (синтетика).

## Состав `docker-compose.yaml` (минимум)

- `postgres:16` с WAL-репликацией.
- `redis:7`.
- `garage` (S3-совместимое хранилище для синтетики, образ `dxflrs/garage`; версия — в compose репо реализации).
- `bot` — Python 3.12 + Telegram Bot API + FastAPI (Mini App back-end).
- `miniapp` — статика (nginx + CSP-заголовок из E2).
- `worker` — export-worker + saga executors.

## Долг

- Config-schemas для всех YAML — [config-schemas/](config-schemas/) (первая схема,
  `text_registry.schema.json`, уже присутствует; остальные создаются при первом реальном конфиге).
- CI-pipeline — [ci-checks.yaml](ci-checks.yaml).
- Плейлист миграций (Alembic) — при первой правке DDL после первого прода.
