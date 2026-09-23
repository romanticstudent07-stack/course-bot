# infra/ — локальный запуск course-bot

Пошаговая инструкция для разработки и тестирования на локальном сервере Автора
(IRONCLAD, Ubuntu 26.04). На VPS/Cloud переходим после успешных тестов.

Правила сервера — в `SERVER-IRONCLAD.md`. Cloudflare Tunnel — в `CLOUDFLARE-TUNNEL.md`.

S3-совместимое хранилище в dev — **Garage** (`dxflrs/garage`), заменил MinIO
(MinIO удалил официальные Docker-образы в сентябре 2026). Переезд на
Yandex Object Storage — просто смена `S3_ENDPOINT` в `.env`, код не трогаем.

---

## Что понадобится

- Ubuntu Server (или любой Linux) с 4 GB RAM и 20 GB свободного места.
- Docker + Docker Compose v2 (`sudo apt install docker.io docker-compose-plugin`).
- Git (`sudo apt install git`).
- Cloudflare-аккаунт (бесплатный) — для проброса HTTPS наружу.
- Telegram-бот от `@BotFather` (см. ниже).

---

## Шаг 1. Создать Telegram-бота

Открой Telegram → напиши `@BotFather` → команды:

```
/newbot
```

BotFather спросит:
1. Имя бота (то, что видит пользователь): например `My Course Bot`.
2. Username (латиница, кончается на `bot`): например `mycourse_test_bot`.

BotFather выдаст **токен вида** `1234567890:AAF...`.

**Сохрани токен в менеджере паролей.** Никуда не вставляй в код.

Дополнительно сразу создай Mini App через того же `@BotFather`:
```
/newapp
```
Выбери бота → название Mini App → короткое описание → пропусти
фото/аватарки → пропусти домен (`/empty`) — вернёшься сюда позже,
когда будет URL Cloudflare Tunnel.

---

## Шаг 2. Установить Docker на Ubuntu (если ещё нет)

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin git
sudo usermod -aG docker $USER
newgrp docker            # перечитать группу без релогина
docker --version         # проверка
docker compose version   # проверка (должно быть v2)
```

---

## Шаг 3. Установить cloudflared (Cloudflare Tunnel)

```bash
# Скачиваем deb-пакет (архитектура amd64 или arm64 — определи через uname -m)
ARCH=$(dpkg --print-architecture)
wget -O cloudflared.deb "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${ARCH}.deb"
sudo dpkg -i cloudflared.deb
cloudflared --version
```

---

## Шаг 4. Клонировать репозиторий и активировать git-хуки

```bash
cd ~
git clone https://github.com/romanticstudent07-stack/course-bot.git
cd course-bot

# ОБЯЗАТЕЛЬНО: активировать локальные git-хуки (защита от случайных коммитов
# в docs/architecture/** и .env). Одноразовая команда:
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit
```

Если репо приватный — сначала настрой SSH-ключ или используй HTTPS с токеном.

---

## Шаг 5. Настроить .env

```bash
cp .env.example .env
nano .env    # или любой редактор
```

Заполни минимум (значения СОГЛАСОВАНЫ с `.env.example` — не выдумывай свои!):

**Telegram:**
- `BOT_TOKEN` — токен от BotFather (шаг 1).
- `BOT_USERNAME` — username бота без @ (например `mycourse_test_bot`).
- `WEBHOOK_SECRET` — случайная строка: `openssl rand -hex 32`.
- `WEBAPP_URL` — временно пустой; вернёмся сюда после Cloudflare Tunnel.
- `ADMIN_USER_ID` — твой telegram-ID (узнать через `@userinfobot`).

**PostgreSQL:**
- `POSTGRES_DB=course_bot`
- `POSTGRES_USER=course_bot`
- `POSTGRES_PASSWORD` — случайная строка: `openssl rand -hex 24`.
- `POSTGRES_PORT=5435` (для публикации на хосте — 5432 занят системой,
  5434 занят maxmover).
- `POSTGRES_HOST_INTERNAL=db` (имя сервиса в compose-сети).
- `POSTGRES_HOST=127.0.0.1` (для доступа с хоста, например psql).

**Redis:**
- `REDIS_URL=redis://redis:6379/0` — для доступа ИЗ контейнеров compose.
- `REDIS_URL_EXTERNAL=redis://127.0.0.1:6382/0` — для доступа с хоста.

**S3 / Garage:**
- `S3_ENDPOINT=http://garage:3900` — из контейнеров.
- `S3_ENDPOINT_EXTERNAL=http://127.0.0.1:9000` — с хоста.
- `S3_ACCESS_KEY=GKcoursebotdev01` (dev-дефолт; в prod генерируй свой).
- `S3_SECRET_KEY=0000000000000000000000000000000000000001` — 40 hex-символов
  (для prod: `openssl rand -hex 20`, тоже даст 40 hex-символов).

**Часовой пояс:**
- `TZ=Europe/Moscow`
- `SERVER_TIMEZONE=Europe/Moscow`

Остальные поля (PAYMENT_*, PSP_*) — оставь как в `.env.example` на старте.

---

## Шаг 6. Поднять стек docker compose

```bash
docker compose -f infra/docker-compose.dev.yml up -d
docker compose -f infra/docker-compose.dev.yml ps
```

Все контейнеры должны быть `running` или `healthy`. Логи:
```bash
docker compose -f infra/docker-compose.dev.yml logs -f
```

**Что где слушает** (все — только на `127.0.0.1`):
- Backend API: `http://127.0.0.1:8080` (эндпоинт `/healthz`).
- PostgreSQL: `127.0.0.1:5435`.
- Redis: `127.0.0.1:6382`.
- Garage S3 API: `http://127.0.0.1:9000` — доступ по протоколу S3 (boto3/aws-cli).
- Garage Web/Object browser: `http://127.0.0.1:9001`.
- Mini App prod-nginx: `http://127.0.0.1:5173` (внутри контейнер порт 80).

**Vite dev-server** (быстрый hot-reload при разработке Mini App) —
запускается отдельно на dev-машине через `npm run dev` внутри `apps/miniapp/`.
Это НЕ docker-compose сервис. Docker-контейнер `miniapp` = только собранная
production-статика под nginx.

**Первый запуск Garage** — сервис `garage-init` создаст бакеты `photos`, `audit`
и импортирует ключ. Смотри логи: `docker compose logs garage-init`.
Ожидание: строка `[garage-init] DONE. Buckets: photos, audit. Ready.`

---

## Шаг 7. Запустить Cloudflare Tunnel

**Вариант A — быстрый (временный домен, для проб):**

```bash
cloudflared tunnel --url http://127.0.0.1:8080
```

В консоли появится URL вида
`https://random-slug.trycloudflare.com`.
Скопируй его.

**Вариант B — стабильный (свой домен, для долгой разработки):**

Полная инструкция — в `CLOUDFLARE-TUNNEL.md`. Кратко:
```bash
cloudflared tunnel login
cloudflared tunnel create coursebot
cloudflared tunnel route dns coursebot coursebot.example.com
cloudflared tunnel run coursebot --url http://127.0.0.1:8080
```

Теперь `https://coursebot.example.com` смотрит на твой сервер.

---

## Шаг 8. Прописать URL в .env и Telegram

Открой `.env`, впиши:
```
WEBAPP_URL=https://<твой-tunnel-url>
```

Перезапусти стек:
```bash
docker compose -f infra/docker-compose.dev.yml restart
```

Скажи Telegram, куда слать обновления боту:
```bash
BOT_TOKEN='<токен>'
WEBHOOK_URL='https://<твой-tunnel-url>/webhook/telegram'
SECRET='<WEBHOOK_SECRET из .env>'
curl -F "url=${WEBHOOK_URL}" \
     -F "secret_token=${SECRET}" \
     "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook"
```

Ответ должен быть `{"ok":true, ...}`.

Проверка:
```bash
curl "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo"
```

Скажи BotFather, где живёт Mini App:
```
/setdomain
```
→ выбери бота → введи `https://<твой-tunnel-url>`.

---

## Шаг 9. Проверить, что бот отвечает

Напиши боту `/start` в Telegram. Он должен ответить.
Логи запросов увидишь через:
```bash
docker compose -f infra/docker-compose.dev.yml logs -f bot api
```

---

## Обновление после мержа PR

Когда Автор смерджил PR в `main`, забери изменения на сервер:
```bash
cd ~/course-bot
git pull origin main
docker compose -f infra/docker-compose.dev.yml up -d --build
```

Если менялись миграции БД:
```bash
docker compose -f infra/docker-compose.dev.yml exec api alembic upgrade head
```

---

## Полезные команды

```bash
# Статус всех сервисов
docker compose -f infra/docker-compose.dev.yml ps

# Перезапуск одного сервиса
docker compose -f infra/docker-compose.dev.yml restart bot

# Логи одного сервиса
docker compose -f infra/docker-compose.dev.yml logs -f api

# Зайти внутрь контейнера
docker compose -f infra/docker-compose.dev.yml exec api bash

# Статус Garage-кластера (должен показать 1 узел UP)
docker compose -f infra/docker-compose.dev.yml exec garage garage status

# Список бакетов Garage
docker compose -f infra/docker-compose.dev.yml exec garage garage bucket list

# Проверка S3 с хоста через aws-cli (если установлен)
AWS_ACCESS_KEY_ID=GKcoursebotdev01 \
AWS_SECRET_ACCESS_KEY=0000000000000000000000000000000000000001 \
aws --endpoint-url=http://127.0.0.1:9000 s3 ls

# Полный wipe (осторожно — удалит БД и Garage-хранилище)
docker compose -f infra/docker-compose.dev.yml down -v
```

---

## Если что-то пошло не так

- `docker compose logs -f <service>` → смотрим ошибку.
- **Garage не поднимается:** проверь монтирование `infra/garage/garage.toml`
  и права на volume-ы. `docker compose logs garage` покажет причину.
- **garage-init висит:** проверь, что переменные `S3_ACCESS_KEY` (16 символов)
  и `S3_SECRET_KEY` (ровно 40 hex-символов) корректны в `.env`.
- **api не стартует из-за db:** dwait `pg_isready` в healthcheck; обычно
  устраняется первым перезапуском после первого init БД.
- `docker compose down -v` → полный сброс тoмов (потеря данных БД и Garage!).

---

## Куда переезжать после локальных тестов

- **Yandex Cloud (Managed PostgreSQL + Object Storage)** — 152-ФЗ штатно, дороже.
  Переезд с Garage → Yandex Object Storage: меняем `S3_ENDPOINT` на
  `https://storage.yandexcloud.net`, `S3_REGION=ru-central1`, ключи от Yandex.
  Код на `boto3` не переписывается.
- **Timeweb «Облако 152-ФЗ»** — дешевле, часть работы админить самому.
- **VPS (Selectel/Timeweb VPS)** — самый гибкий; можно оставить Garage
  как S3 или мигрировать на облачный S3.

Выбор — открытый вопрос Автора.
