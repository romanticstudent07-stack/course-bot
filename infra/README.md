# infra/ — локальный запуск course-bot

Пошаговая инструкция для разработки и тестирования на локальном сервере Автора
(IRONCLAD, Ubuntu 26.04). На VPS/Cloud переходим после успешных тестов.

Правила сервера — в `SERVER-IRONCLAD.md`. Cloudflare Tunnel — в `CLOUDFLARE-TUNNEL.md`.

S3-совместимое хранилище в dev — **Garage** (`dxflrs/garage:v2.3.0`), заменил MinIO
(MinIO удалил официальные Docker-образы в сентябре 2026). Переезд на
Yandex Object Storage — просто смена `S3_ENDPOINT` в `.env`, код не трогаем.

Начиная с v2.3.0 Garage настраивает себя сам (флаги `--single-node --default-bucket`):
создаёт кластер из одного узла, ключ доступа и первый бакет. Отдельного
init-контейнера и скриптов инициализации в проекте больше НЕТ.

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
- `S3_ACCESS_KEY` — формат `GK` + 32 hex-символа: `GK$(openssl rand -hex 16)`.
- `S3_SECRET_KEY` — ровно 64 hex-символа: `openssl rand -hex 32`.
- `S3_BUCKET_PHOTOS=photos` — этот бакет Garage создаст сам при первом старте.
- `S3_BUCKET_AUDIT=audit` — бакет создаётся ВРУЧНУЮ на Итерации 5 (см. ниже).

**Внутренние секреты Garage** (не путать с S3-ключами выше):
- `GARAGE_RPC_SECRET` — ровно 64 hex-символа: `openssl rand -hex 32`.
- `GARAGE_ADMIN_TOKEN` — случайная строка: `openssl rand -base64 32`.
- `GARAGE_METRICS_TOKEN` — случайная строка: `openssl rand -base64 32`.

Эти три значения перекрывают плейсхолдеры из `garage.toml` (переменные
окружения имеют высший приоритет над конфиг-файлом).

**Часовой пояс:**
- `TZ=Europe/Moscow`
- `SERVER_TIMEZONE=Europe/Moscow`

Остальные поля (PAYMENT_*, PSP_*) — оставь как в `.env.example` на старте.

---

## Шаг 5-бис. Как сгенерировать все секреты одной командой

Выполни в терминале — команда напечатает готовые строки. Скопируй их в `.env`
вместо пустых значений:

```bash
cat <<EOF
S3_ACCESS_KEY=GK$(openssl rand -hex 16)
S3_SECRET_KEY=$(openssl rand -hex 32)
GARAGE_RPC_SECRET=$(openssl rand -hex 32)
GARAGE_ADMIN_TOKEN=$(openssl rand -base64 32)
GARAGE_METRICS_TOKEN=$(openssl rand -base64 32)
POSTGRES_PASSWORD=$(openssl rand -hex 24)
WEBHOOK_SECRET=$(openssl rand -hex 32)
EOF
```

**Важно:** ключ доступа и бакет Garage создаёт ОДИН раз — при первом запуске на
пустых volume-ах. Если поменял `S3_ACCESS_KEY` / `S3_SECRET_KEY` уже ПОСЛЕ
первого старта, Garage новый ключ не подхватит. Варианты: создать ключ вручную
(`/garage key create`) либо снести volume-ы командой
`docker compose --env-file .env -f infra/docker-compose.dev.yml down -v`
(внимание: это удалит все загруженные файлы и базу).

---

## Шаг 6. Поднять стек docker compose

Запускай из корня репозитория и обязательно с флагом `--env-file .env`:
compose-файл лежит в `infra/`, а `.env` — в корне, без флага подстановка
переменных вида `${POSTGRES_PASSWORD}` и `${GARAGE_RPC_SECRET}` не сработает.

```bash
cd ~/course-bot
docker compose --env-file .env -f infra/docker-compose.dev.yml up -d
docker compose --env-file .env -f infra/docker-compose.dev.yml ps
```

Все контейнеры должны быть `running` или `healthy`. Логи:
```bash
docker compose --env-file .env -f infra/docker-compose.dev.yml logs -f
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

**Первый запуск Garage.** Контейнер сам соберёт кластер из одного узла, создаст
ключ доступа из `.env` и бакет `photos`. Проверка (образ Garage собран
from scratch, оболочки в нём нет — бинарник вызываем по полному пути `/garage`):

```bash
docker compose --env-file .env -f infra/docker-compose.dev.yml \
  exec garage /garage -c /etc/garage.toml status

docker compose --env-file .env -f infra/docker-compose.dev.yml \
  exec garage /garage -c /etc/garage.toml bucket list
```

Ожидание: в `status` — один узел со статусом HEALTHY; в `bucket list` — `photos`.

---

## Создание бакета audit — когда понадобится (Итерация 5)

Garage автоматически создаёт только ОДИН бакет (`photos`). Бакет аудита нужен
начиная с Итерации 5 — тогда выполни две команды (вместо `GK...` подставь
значение `S3_ACCESS_KEY` из своего `.env`):

```bash
cd ~/course-bot

# 1) создать бакет
docker compose --env-file .env -f infra/docker-compose.dev.yml \
  exec garage /garage -c /etc/garage.toml bucket create audit

# 2) выдать права нашему ключу доступа
docker compose --env-file .env -f infra/docker-compose.dev.yml \
  exec garage /garage -c /etc/garage.toml \
  bucket allow --read --write --owner audit --key GK...
```

Проверка:
```bash
docker compose --env-file .env -f infra/docker-compose.dev.yml \
  exec garage /garage -c /etc/garage.toml bucket info audit
```

Напоминание из архитектуры: бакет фото — Object Lock ОТКЛЮЧЁН (иначе стирание
по запросу клиента невозможно); бакет аудита в prod — режим COMPLIANCE / WORM.

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
docker compose --env-file .env -f infra/docker-compose.dev.yml restart
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
docker compose --env-file .env -f infra/docker-compose.dev.yml logs -f bot api
```

---

## Обновление после мержа PR

Когда Автор смерджил PR в `main`, забери изменения на сервер:
```bash
cd ~/course-bot
git pull origin main
docker compose --env-file .env -f infra/docker-compose.dev.yml up -d --build
```

Если менялись миграции БД:
```bash
docker compose --env-file .env -f infra/docker-compose.dev.yml exec api alembic upgrade head
```

---

## Полезные команды

```bash
# Статус всех сервисов
docker compose --env-file .env -f infra/docker-compose.dev.yml ps

# Перезапуск одного сервиса
docker compose --env-file .env -f infra/docker-compose.dev.yml restart bot

# Логи одного сервиса
docker compose --env-file .env -f infra/docker-compose.dev.yml logs -f api

# Зайти внутрь контейнера
docker compose --env-file .env -f infra/docker-compose.dev.yml exec api bash

# Статус Garage-кластера (должен показать 1 узел HEALTHY).
# Путь /garage обязателен: образ from scratch, оболочки нет.
docker compose --env-file .env -f infra/docker-compose.dev.yml \
  exec garage /garage -c /etc/garage.toml status

# Список бакетов Garage
docker compose --env-file .env -f infra/docker-compose.dev.yml \
  exec garage /garage -c /etc/garage.toml bucket list

# Список ключей доступа Garage
docker compose --env-file .env -f infra/docker-compose.dev.yml \
  exec garage /garage -c /etc/garage.toml key list

# Проверка S3 с хоста через aws-cli (ключи подставь из своего .env)
AWS_ACCESS_KEY_ID="<S3_ACCESS_KEY из .env>" \
AWS_SECRET_ACCESS_KEY="<S3_SECRET_KEY из .env>" \
aws --endpoint-url=http://127.0.0.1:9000 --region garage s3 ls

# Полный wipe (осторожно — удалит БД и Garage-хранилище)
docker compose --env-file .env -f infra/docker-compose.dev.yml down -v
```

---

## Если что-то пошло не так

- `docker compose logs -f <service>` → смотрим ошибку.
- **Garage не поднимается:** проверь монтирование `infra/garage/garage.toml`
  и права на volume-ы. `docker compose logs garage` покажет причину.
- **Garage падает сразу при старте с ошибкой про аргумент `/garage`:** убери
  первый элемент из `command` в compose, оставив
  `command: ["server", "--single-node", "--default-bucket"]`.
- **Бакет `photos` не создался:** проверь, что в `.env` заполнены
  `S3_ACCESS_KEY` (`GK` + 32 hex), `S3_SECRET_KEY` (64 hex) и
  `S3_BUCKET_PHOTOS`, и что стек запускался с флагом `--env-file .env`.
  Бакет создаётся только на пустых volume-ах при самом первом старте.
- **Переменные приехали пустыми / Postgres просит пароль:** ты забыл
  `--env-file .env`. Compose ищет `.env` рядом с compose-файлом (в `infra/`),
  а он лежит в корне репозитория.
- **api не стартует из-за db:** ждём `pg_isready` в healthcheck; обычно
  устраняется первым перезапуском после первого init БД.
- `docker compose down -v` → полный сброс томов (потеря данных БД и Garage!).

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
