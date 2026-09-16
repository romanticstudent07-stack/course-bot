# infra/ — локальный запуск course-bot

Пошаговая инструкция для разработки и тестирования на локальном сервере Автора.
На VPS/Cloud переходим после успешных тестов.

---

## Что понадобится

- Ubuntu Server (или любой Linux) с 4 GB RAM и 20 GB свободного места.
- Docker + Docker Compose (`sudo apt install docker.io docker-compose-plugin`).
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

## Шаг 4. Клонировать репозиторий

```bash
cd ~
git clone https://github.com/romanticstudent07-stack/course-bot.git
cd course-bot
```

Если репо приватный — сначала настрой SSH-ключ или используй HTTPS с токеном.

---

## Шаг 5. Настроить .env

```bash
cp .env.example .env
nano .env    # или любой редактор
```

Заполни минимум:
- `BOT_TOKEN` — токен от BotFather (шаг 1).
- `BOT_USERNAME` — username бота без @ (например `mycourse_test_bot`).
- `WEBHOOK_SECRET` — случайная строка (сгенерируй `openssl rand -hex 32`).
- `WEBAPP_URL` — временно оставь пустым, вернёмся сюда после запуска Cloudflare Tunnel.
- `ADMIN_USER_ID` — твой telegram-ID (узнать через `@userinfobot`).
- `POSTGRES_HOST=postgres`, `POSTGRES_DB=coursebot`, `POSTGRES_USER=coursebot`,
  `POSTGRES_PASSWORD` — случайная строка.
- `REDIS_URL=redis://redis:6379/0`
- `TZ=Europe/Moscow`, `SERVER_TIMEZONE=Europe/Moscow`, `LOG_LEVEL=INFO`.

Остальные поля (S3, PSP) — оставь пустыми на старте.

---

## Шаг 6. Поднять стек docker compose

```bash
docker compose -f infra/docker-compose.dev.yml up -d
docker compose -f infra/docker-compose.dev.yml ps
```

Все контейнеры должны быть `running`. Логи:
```bash
docker compose -f infra/docker-compose.dev.yml logs -f
```

Backend будет на `http://localhost:8000`.
Mini App (Vite dev) — на `http://localhost:5173`.

---

## Шаг 7. Запустить Cloudflare Tunnel

**Вариант A — быстрый (временный домен, для проб):**

```bash
cloudflared tunnel --url http://localhost:8000
```

В консоли появится URL вида
`https://random-slug.trycloudflare.com`.
Скопируй его.

**Вариант B — стабильный (свой домен, для долгой разработки):**

Если у тебя есть свой домен, добавленный в Cloudflare —
регистрируй именованный туннель:
```bash
cloudflared tunnel login       # откроется браузер, выбери домен
cloudflared tunnel create coursebot
cloudflared tunnel route dns coursebot coursebot.example.com
cloudflared tunnel run coursebot --url http://localhost:8000
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

# Полный wipe (осторожно — удалит БД)
docker compose -f infra/docker-compose.dev.yml down -v
```

---

## Куда переезжать после локальных тестов

- **Yandex Cloud** — managed PostgreSQL/Redis, 152-ФЗ штатно, дороже.
- **Timeweb «Облако 152-ФЗ»** — дешевле, часть работы админить самому.
- **VPS (Selectel/Timeweb VPS)** — самый гибкий, но админить весь стек самому.

Выбор — открытый вопрос Автора.
После выбора: миграция сводится к `docker compose up` на новом хосте
и переключению DNS/webhook на новый URL.
