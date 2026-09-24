# infra/ — локальный запуск course-bot

Пошаговая инструкция для разработки и тестирования на локальном сервере Автора
(IRONCLAD, Ubuntu 26.04). На VPS/Cloud переходим после успешных тестов.

Правила сервера — в `SERVER-IRONCLAD.md`.

**Dev-вход — Tailscale serve** (только tailnet, только для Автора; шаг 7).
Cloudflare Tunnel для course-bot **не используется**: из РФ нестабилен, а на
IRONCLAD уже работает служба `cloudflared` чужого проекта maxmover — её не трогать.
`CLOUDFLARE-TUNNEL.md` сохранён как архив, на IRONCLAD не применять.
Бот работает на **long polling** — webhook не ставится (D-4 в `docs/DEFECTS-FOUND.md`).

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
- Tailscale на сервере, сервер уже в tailnet Автора (на IRONCLAD — так и есть).
- Tailscale на устройстве, где открыт Telegram (ноутбук), в том же tailnet:
  Mini App по dev-адресу открывается только на устройствах внутри tailnet.
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

**`/newapp` для кнопки Mini App НЕ нужен.** Кнопку меню (Menu Button) бот
ставит сам при старте — по адресу из `WEBAPP_URL` в `.env` (шаг 8).
`/newapp` в `@BotFather` понадобится, только если нужна прямая ссылка
на Mini App вида `t.me/<бот>/<app>` — сейчас не нужна.

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

## Шаг 3. Проверить Tailscale на сервере

cloudflared для course-bot **не ставим** (см. шапку). Dev-вход — Tailscale serve.
На IRONCLAD Tailscale уже установлен и сервер в tailnet. Проверка:

```bash
tailscale status
```

В выводе должны быть сервер и устройство, с которого открываешь Telegram.
Если сервер не в tailnet — это вопрос к Автору (из РФ админка и логин
Tailscale могут быть заблокированы, см. «Прод / внешние тестировщики — позже»).

---

## Шаг 4. Клонировать репозиторий и активировать git-хуки

```bash
cd ~
# Репозиторий ПРИВАТНЫЙ — клон по HTTPS не сработает.
# Клонируем через deploy-ключ с SSH-алиасом (настройка алиаса — в ~/.ssh/config).
git clone git@github-coursebot:romanticstudent07-stack/course-bot.git
cd course-bot

# ОБЯЗАТЕЛЬНО: активировать локальные git-хуки (защита от случайных коммитов
# в docs/architecture/** и .env). Одноразовая команда:
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit
```

Репозиторий приватный, поэтому клон возможен только по SSH с deploy-ключом.
Алиас `github-coursebot` должен быть описан в `~/.ssh/config` и указывать на
приватный ключ, публичная часть которого добавлена в Settings → Deploy keys
репозитория. Если алиас у тебя называется иначе — подставь своё имя.

Сразу после клонирования ОБЯЗАТЕЛЬНО активируй git-хуки (команда выше:
`git config core.hooksPath .githooks`) — без неё защита от случайных
коммитов в `docs/architecture/**` и `.env` не работает.

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
- `WEBHOOK_SECRET` — случайная строка: `openssl rand -hex 32`
  (пока не используется: бот на long polling, D-4).
- `WEBAPP_URL` — временно пустой; вернёмся сюда после Tailscale serve (шаг 7–8).
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
- `S3_ACCESS_KEY` — формат `GK` + 32 hex-символа, итого 34 символа: `GK$(openssl rand -hex 16)`.
- `S3_SECRET_KEY` — ровно 64 hex-символа: `openssl rand -hex 32`.
- `S3_BUCKET_PHOTOS=photos` — этот бакет Garage создаст сам при первом старте.
- `S3_BUCKET_AUDIT=audit` — бакет создаётся ВРУЧНУЮ на Итерации 5 (см. ниже).

**Внутренние секреты Garage** (не путать с S3-ключами выше):
- `GARAGE_RPC_SECRET` — ровно 64 hex-символа: `openssl rand -hex 32`.
- `GARAGE_ADMIN_TOKEN` — случайная строка: `openssl rand -hex 32`.
- `GARAGE_METRICS_TOKEN` — случайная строка: `openssl rand -hex 32`.

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
GARAGE_ADMIN_TOKEN=$(openssl rand -hex 32)
GARAGE_METRICS_TOKEN=$(openssl rand -hex 32)
POSTGRES_PASSWORD=$(openssl rand -hex 24)
WEBHOOK_SECRET=$(openssl rand -hex 32)
EOF
```

**Важно:** ключ доступа и бакет Garage создаёт ОДИН раз — при первом запуске на
пустых volume-ах. Если поменял `S3_ACCESS_KEY` / `S3_SECRET_KEY` уже ПОСЛЕ
первого старта, Garage новый ключ не подхватит. Варианты: создать ключ вручную
(`/garage key create`) либо снести volume-ы командой
`cd ~/course-bot && docker compose --env-file .env -f infra/docker-compose.dev.yml down -v`
(внимание: это удалит все загруженные файлы и базу).

---

## Шаг 6. Поднять стек docker compose

Запускай из корня репозитория и обязательно с флагом `--env-file .env`:
compose-файл лежит в `infra/`, а `.env` — в корне, без флага подстановка
переменных вида `${POSTGRES_PASSWORD}` и `${GARAGE_RPC_SECRET}` не сработает.

```bash
cd ~/course-bot && docker compose --env-file .env -f infra/docker-compose.dev.yml up -d
cd ~/course-bot && docker compose --env-file .env -f infra/docker-compose.dev.yml ps
```

Все контейнеры должны быть `running` или `healthy`. Логи:
```bash
cd ~/course-bot && docker compose --env-file .env -f infra/docker-compose.dev.yml logs -f
```

**Что где слушает** (все — только на `127.0.0.1`):
- Backend API: `http://127.0.0.1:8080` (эндпоинт `/healthz`).
- PostgreSQL: `127.0.0.1:5435`.
- Redis: `127.0.0.1:6382`.
- Garage S3 API: `http://127.0.0.1:9000` — доступ по протоколу S3 (boto3/aws-cli).
- Garage `s3_web`: `http://127.0.0.1:9001` — это НЕ админка и НЕ браузер
  файлов. Порт 3902 раздаёт статические сайты из бакетов по доменному имени;
  при открытии в браузере напрямую будет ошибка. Встроенного веб-интерфейса
  в Garage не существует вовсе — бакеты и ключи смотрим только через CLI:
  `docker exec course-bot_garage /garage -c /etc/garage.toml bucket list`
  и `docker exec course-bot_garage /garage -c /etc/garage.toml key list`.
- Mini App prod-nginx: `http://127.0.0.1:5173` (внутри контейнер порт 80).
  Сюда же смотрит Tailscale serve (шаг 7). nginx miniapp сам проксирует
  `/miniapp/v1/**` и `/security/csp-report` в `api:8080` — отдельный вход
  на 8080 не нужен.

**Vite dev-server** (быстрый hot-reload при разработке Mini App) —
запускается отдельно на dev-машине через `npm run dev` внутри `apps/miniapp/`.
Это НЕ docker-compose сервис. Docker-контейнер `miniapp` = только собранная
production-статика под nginx.

**Первый запуск Garage.** Контейнер сам соберёт кластер из одного узла, создаст
ключ доступа из `.env` и бакет `photos`. Проверка (образ Garage собран
from scratch, оболочки в нём нет — бинарник вызываем по полному пути `/garage`):

```bash
cd ~/course-bot && docker compose --env-file .env -f infra/docker-compose.dev.yml \
  exec garage /garage -c /etc/garage.toml status

cd ~/course-bot && docker compose --env-file .env -f infra/docker-compose.dev.yml \
  exec garage /garage -c /etc/garage.toml bucket list
```

Ожидание: в `status` — один узел со статусом HEALTHY; в `bucket list` — `photos`.

---

## Создание бакета audit — когда понадобится (Итерация 5)

Garage автоматически создаёт только ОДИН бакет (`photos`). Бакет аудита нужен
начиная с Итерации 5 — тогда выполни две команды (вместо `GK...` подставь
значение `S3_ACCESS_KEY` из своего `.env`):

```bash
# 1) создать бакет
cd ~/course-bot && docker compose --env-file .env -f infra/docker-compose.dev.yml \
  exec garage /garage -c /etc/garage.toml bucket create audit

# 2) выдать права нашему ключу доступа
cd ~/course-bot && docker compose --env-file .env -f infra/docker-compose.dev.yml \
  exec garage /garage -c /etc/garage.toml \
  bucket allow --read --write --owner audit --key GK...
```

Проверка:
```bash
cd ~/course-bot && docker compose --env-file .env -f infra/docker-compose.dev.yml \
  exec garage /garage -c /etc/garage.toml bucket info audit
```

Напоминание из архитектуры: бакет фото — Object Lock ОТКЛЮЧЁН (иначе стирание
по запросу клиента невозможно); бакет аудита в prod — режим COMPLIANCE / WORM.

---

## Шаг 7. Включить dev-вход через Tailscale serve

Dev-вход — **Tailscale serve**: HTTPS-адрес доступен **только внутри tailnet**
и только Автору. Наружу (в интернет) ничего не публикуется.

Tailscale serve смотрит на nginx Mini App (`127.0.0.1:5173`). nginx miniapp
сам проксирует `/miniapp/v1/**` и `/security/csp-report` в `api:8080`,
поэтому отдельный вход на API не нужен.

Включить (на сервере):
```bash
sudo tailscale serve --bg http://127.0.0.1:5173
```

Проверить, что включено:
```bash
tailscale serve status
```

Выключить:
```bash
sudo tailscale serve --https=443 off
```

Адрес будет вида `https://<имя-сервера>.<tailnet>.ts.net/` — **это и есть
`WEBAPP_URL`** (шаг 8). Реальный адрес своего tailnet в репозиторий
не вносить — ни в документы, ни в `.env.example`.

> **Если Telegram на ноутбуке работает через VPN в режиме системного прокси**
> (только dev): добавь в исключения прокси `*.ts.net` и IP сервера в tailnet
> (`tailscale ip -4` на сервере). Иначе Mini App не загрузится: запрос уйдёт
> в VPN, а не в tailnet.

---

## Шаг 8. Прописать URL в .env и Telegram

Открой `.env`, впиши адрес из шага 7:
```
WEBAPP_URL=https://<имя-сервера>.<tailnet>.ts.net/
```

Применить `.env`. **`restart` НЕ перечитывает `.env`** — контейнер
перезапустится со старыми переменными. Нужен `up -d` для сервисов, которые
читают `WEBAPP_URL` (compose пересоздаст их с новым окружением):
```bash
cd ~/course-bot && docker compose --env-file .env -f infra/docker-compose.dev.yml up -d bot api
```

После старта бот выставит Menu Button на `WEBAPP_URL` (в логах `bot`:
«Menu Button → WEBAPP_URL установлена»).

**Webhook — НЕ выполнять: бот на long polling (D-4).** Webhook-режим
не реализован, эндпоинта `/webhook/telegram` в api нет. Если webhook
зарегистрирован, long polling не работает: бот пишет ошибку в лог
и ждёт, пока webhook снимут.

Если webhook уже стоит (например, выполнялась старая версия этого шага) —
снять его:
```bash
BOT_TOKEN='<токен>'
curl "https://api.telegram.org/bot${BOT_TOKEN}/deleteWebhook"
```
Ответ: `{"ok":true,...}`. Проверка — в `getWebhookInfo` поле `url` пустое:
```bash
curl "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo"
```

<details>
<summary>Архив: команда setWebhook (НЕ выполнять: бот на long polling, D-4)</summary>

Оставлена только для истории — до отдельной итерации webhook.

```bash
BOT_TOKEN='<токен>'
WEBHOOK_URL='https://<публичный-адрес>/webhook/telegram'
SECRET='<WEBHOOK_SECRET из .env>'
curl -F "url=${WEBHOOK_URL}" \
     -F "secret_token=${SECRET}" \
     "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook"
```

</details>

**В `@BotFather` для Mini App ничего делать не нужно.** Для кнопки Mini App
достаточно `WEBAPP_URL`: бот сам ставит Menu Button (см. лог выше).
`/setdomain` в BotFather — это настройка для Telegram Login Widget
(вход через Telegram на обычном сайте), а не для Mini App. Выполнять его
только если когда-нибудь понадобится Login Widget.

---

## Шаг 9. Проверить, что бот отвечает

Напиши боту `/start` в Telegram. Он должен ответить и показать кнопку Mini App.
Логи запросов увидишь через:
```bash
cd ~/course-bot && docker compose --env-file .env -f infra/docker-compose.dev.yml logs -f bot api
```

---

## Обновление после мержа PR

Когда Автор смерджил PR в `main`, забери изменения на сервер:
```bash
cd ~/course-bot && git pull origin main
cd ~/course-bot && docker compose --env-file .env -f infra/docker-compose.dev.yml up -d
```

**Почему без `--build`:** сервер на HDD 5400 RPM, полная пересборка всех
образов (особенно `miniapp`) занимает 15–40 минут. Обычный `up -d` соберёт
только недостающие образы и перезапустит изменившиеся контейнеры.
Если PR менял только документацию / комментарии — хватит `git pull`,
перезапуск не нужен.
Пересобирай точечно и только когда менялся код конкретного сервиса:

```bash
cd ~/course-bot && docker compose --env-file .env -f infra/docker-compose.dev.yml up -d --build api
cd ~/course-bot && docker compose --env-file .env -f infra/docker-compose.dev.yml up -d --build miniapp
```

Если менялись миграции БД:
```bash
cd ~/course-bot && docker compose --env-file .env -f infra/docker-compose.dev.yml exec api alembic upgrade head
```

---

## Полезные команды

```bash
# Статус всех сервисов
cd ~/course-bot && docker compose --env-file .env -f infra/docker-compose.dev.yml ps

# Применить изменения .env к одному сервису (restart .env НЕ перечитывает!)
cd ~/course-bot && docker compose --env-file .env -f infra/docker-compose.dev.yml up -d bot

# Просто перезапустить процесс (.env не менялся)
cd ~/course-bot && docker compose --env-file .env -f infra/docker-compose.dev.yml restart bot

# Логи одного сервиса
cd ~/course-bot && docker compose --env-file .env -f infra/docker-compose.dev.yml logs -f api

# Зайти внутрь контейнера
cd ~/course-bot && docker compose --env-file .env -f infra/docker-compose.dev.yml exec api bash

# Статус Garage-кластера (должен показать 1 узел HEALTHY).
# Путь /garage обязателен: образ from scratch, оболочки нет.
cd ~/course-bot && docker compose --env-file .env -f infra/docker-compose.dev.yml \
  exec garage /garage -c /etc/garage.toml status

# Список бакетов Garage
cd ~/course-bot && docker compose --env-file .env -f infra/docker-compose.dev.yml \
  exec garage /garage -c /etc/garage.toml bucket list

# Список ключей доступа Garage
cd ~/course-bot && docker compose --env-file .env -f infra/docker-compose.dev.yml \
  exec garage /garage -c /etc/garage.toml key list

# Проверка S3 с хоста через aws-cli (ключи подставь из своего .env)
AWS_ACCESS_KEY_ID="<S3_ACCESS_KEY из .env>" \
AWS_SECRET_ACCESS_KEY="<S3_SECRET_KEY из .env>" \
aws --endpoint-url=http://127.0.0.1:9000 --region garage s3 ls

# Dev-вход Tailscale serve: статус / выключить
tailscale serve status
sudo tailscale serve --https=443 off

# Полный wipe (осторожно — удалит БД и Garage-хранилище)
cd ~/course-bot && docker compose --env-file .env -f infra/docker-compose.dev.yml down -v
```

---

## Частые ловушки

- **Команды compose — только из `~/course-bot` и только с `--env-file .env`.**
  Форма всегда одна:
  `cd ~/course-bot && docker compose --env-file .env -f infra/docker-compose.dev.yml …`.
  Без `--env-file .env` compose ищет `.env` рядом с compose-файлом (в `infra/`),
  не находит — и `${TZ}`, `${POSTGRES_USER}`, `${POSTGRES_PASSWORD}` и прочие
  подставляются пустыми (compose пишет предупреждения `variable is not set`).
- **api отвечает на `/healthz`, а не на `/health`.**
  `curl http://127.0.0.1:8080/healthz` → `{"status":"ok"}`.
- **`127.0.0.1:9001` — это Garage `s3_web`, не админка.** Веб-интерфейса
  у Garage нет. Бакеты смотрим через CLI:
  `docker exec course-bot_garage /garage -c /etc/garage.toml bucket list`.
- **`S3_REGION` = `garage`** — как `s3_region` в `infra/garage/garage.toml`.
  Другое значение — тихий 403 на S3-запросах (подпись не сходится).
- **`up -d --build` долго пересобирает `miniapp`** (HDD). Если код не менялся —
  хватит `up -d`.
- **`restart` не перечитывает `.env`.** После правки `.env` — `up -d <сервис>`.
- **`POST /miniapp/v1/onboarding/first-launch` без initData → `401 TG_INIT_MISSING`** —
  это норма: эндпоинт требует заголовок `X-Telegram-Init-Data`, который
  присылает только Telegram при открытии Mini App.

---

## Если что-то пошло не так

- `cd ~/course-bot && docker compose --env-file .env -f infra/docker-compose.dev.yml logs -f <service>`
  → смотрим ошибку.
- **Garage не поднимается:** проверь монтирование `infra/garage/garage.toml`
  и права на volume-ы. Причину покажет
  `cd ~/course-bot && docker compose --env-file .env -f infra/docker-compose.dev.yml logs garage`.
  `command` в compose не менять: `/garage` в нём — путь к бинарнику внутри
  образа, так Garage v2.3.0 и запускается на IRONCLAD.
- **Бакет `photos` не создался:** проверь, что в `.env` заполнены
  `S3_ACCESS_KEY` (`GK` + 32 hex), `S3_SECRET_KEY` (64 hex) и
  `S3_BUCKET_PHOTOS`, и что стек запускался с флагом `--env-file .env`.
  Бакет создаётся только на пустых volume-ах при самом первом старте.
- **Переменные приехали пустыми / Postgres просит пароль:** ты забыл
  `--env-file .env` или запускал не из `~/course-bot` (см. «Частые ловушки»).
- **api не стартует из-за db:** ждём `pg_isready` в healthcheck; обычно
  устраняется первым перезапуском после первого init БД.
- **Бот молчит, в логах `bot` — «зарегистрирован webhook»:** сними webhook
  командой `deleteWebhook` (шаг 8).
- **Mini App не открывается по адресу `*.ts.net`:** проверь
  `tailscale serve status` на сервере, что устройство с Telegram в tailnet,
  и исключения прокси VPN (шаг 7).
- `cd ~/course-bot && docker compose --env-file .env -f infra/docker-compose.dev.yml down -v`
  → полный сброс томов (потеря данных БД и Garage!).

---

## Прод / внешние тестировщики — позже

Tailscale serve — только для Автора внутри tailnet; внешним тестировщикам
и участникам он не подходит. План (решение Автора, детали — позже):

- **Вход** — российский VPS с публичным HTTPS.
- **Туннель дом → VPS** — через `autossh` или WireGuard.
  **Не Tailscale**: из РФ блокируются его админка и логин.
- **Не Cloudflare Tunnel**: из РФ ~2200 обрывов за месяц.
- **Провайдер VPS** — решение Автора (открыто, см. D-5 в `docs/DEFECTS-FOUND.md`).
- **До любого внешнего доступа** должна быть закрыта проверка подписи initData
  (Итерация 1, D-7 в `docs/DEFECTS-FOUND.md`).

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
