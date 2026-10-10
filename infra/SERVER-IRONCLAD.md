# infra/SERVER-IRONCLAD.md — факт-памятка о сервере разработки

Кратко: сервер, на котором разработка запускается локально до переезда на VPS/Cloud.
Полный аудит — у Автора в файле `IRONCLAD-factsheet.md` (не в репо, персональный документ).
Здесь только те факты, которые нужны Агенту при написании кода и docker-конфигов.

## Правила публикации портов

- **Только `127.0.0.1`.** Никогда `0.0.0.0` и никогда без явного bind-хоста
  (`docker-compose` по умолчанию биндит на 0.0.0.0 → выход в LAN!).
- Вход снаружи 127.0.0.1: **dev — Tailscale serve (tailnet only)**, только для Автора
  (`sudo tailscale serve --bg http://127.0.0.1:5173`, см. `infra/README.md`, шаг 7).
  В документы — только шаблон адреса `<имя-сервера>.<tailnet>.ts.net`.
- Cloudflare Tunnel для course-bot **не используется** (из РФ нестабилен; служба
  `cloudflared` на сервере — чужая, maxmover). `CLOUDFLARE-TUNNEL.md` — архив,
  на IRONCLAD не применять.
- Прод / внешние тестировщики — позже: российский VPS как вход, туннель дом→VPS
  через autossh или WireGuard (решение Автора, провайдер не выбран).

## Занятые порты (не использовать)

| Порт | Кем занят |
|---|---|
| 22 | SSH |
| 53 | systemd-resolved |
| 323 | chronyd (NTP) |
| 5434 | maxmover PostgreSQL |
| 6381 | maxmover Redis |
| 8443 | maxmover webhook |
| 20241, 38725 | cloudflared (служба maxmover — не трогать) / containerd |

## Порты для course-bot (свободны на 2026-09-19)

| Сервис | Порт | Bind |
|---|---|---|
| API (FastAPI) | 8080 | 127.0.0.1 |
| PostgreSQL 16 | 5435 | 127.0.0.1 |
| Redis 7 | 6382 | 127.0.0.1 |
| Garage S3 API | 9000 | 127.0.0.1 |
| Garage `s3_web` (раздача статики, НЕ админка; веб-UI у Garage нет) | 9001 | 127.0.0.1 |
| Mini App (nginx prod) | 5173 | 127.0.0.1 |

## S3-совместимое хранилище

**dev:** Garage (`dxflrs/garage:v2.3.0`) — S3-совместимое, Rust, ~30 MB RAM.
Заменил MinIO (MinIO удалил официальные Docker-образы в сентябре 2026,
проект в maintenance mode с декабря 2025).

**prod:** Yandex Object Storage (или Timeweb / VK Cloud — решение Автора).
Object Lock (WORM) для бакета аудита — только в prod (Garage single-node
не поддерживает WORM). В dev auditing идёт в обычный бакет `audit` без WORM.

**Переезд dev → prod:** меняем `S3_ENDPOINT` в `.env` — код на `boto3` не трогаем.

## Ресурсы (жёсткие лимиты)

- RAM свободно ≈ 4.6 GiB. Сумма лимитов всех контейнеров course-bot **≤ 2 GB**
  (решение Автора, 25.09.2026; было ≤ 1.5 GB). Сейчас сумма лимитов — 1792 МБ
  (api 384 + db 384 + bot 512 + garage 192 + miniapp 128 + projector 128 + redis 64).
  Реальное потребление стека ~362 МБ (замер 06.10.2026; проектор 53 МБ).
  Бот ~155 МБ — базовый объём, утечки нет (наблюдение 24–25.09.2026).
- Перед добавлением контейнера или повышением лимита — проверить, что сумма остаётся ≤ 2 GB.
- Лимиты заданы в `.env` через `MEM_LIMIT_*` и применяются в `docker-compose.dev.yml`.
- HDD 5400 rpm — сборки медленные. Использовать `python:3.12-slim`, `redis:7-alpine`,
  `postgres:16` (не полные образы), `dxflrs/garage`.
- Docker build-cache чистить перед крупными сборками: `docker builder prune`.

## Роли БД (B-3)

Ниже `DC` = `docker compose --env-file .env -f infra/docker-compose.dev.yml` (из `~/course-bot`).

**Групповые роли.** `app_api` и `app_projector` создаёт миграция `0006_app_roles`: роли NOLOGIN,
права (GRANT) выдаются в той же миграции. Войти под ними нельзя.

**Пользователи для входа** создаются вручную, один раз (так сделано на сервере 09.10.2026,
фаза Б B-3a-2), в psql под владельцем БД (`POSTGRES_USER`):

    CREATE ROLE coursebot_api LOGIN IN ROLE app_api;
    CREATE ROLE coursebot_projector LOGIN IN ROLE app_projector;
    \password coursebot_api
    \password coursebot_projector

- Пароли генерируются командой `openssl rand -hex 24` (только 0-9a-f — экранировать в DSN не нужно).
- Пароль задаётся только через `\password`: он не попадает в историю psql и не печатается при вводе.
  В SQL-команду (`PASSWORD '...'`) пароль не писать.
- Пароли хранятся только в `.env` на сервере. В репо, чаты и логи — никогда.

**Какая переменная у какого процесса** (формат DSN — в `.env.example`, блок «Роли БД»):

| Переменная | Процесс | Пользователь БД |
|---|---|---|
| `DATABASE_URL` | api (FastAPI) | `coursebot_api` (роль `app_api`) |
| `PROJECTOR_DATABASE_URL` | projector | `coursebot_projector` (роль `app_projector`) |
| `MIGRATIONS_DATABASE_URL` | `alembic` и `python -m app.texts load` | владелец (`POSTGRES_USER`) |
| — | bot | БД не использует |

- У projector `PROJECTOR_DATABASE_URL` — единственный путь к БД: запасного пути к владельцу нет,
  пусто в `.env` → проектор остаётся без БД.
- alembic и загрузчик текстов запускаются в контейнере api (у него env_file) и берут
  `MIGRATIONS_DATABASE_URL`. У api в окружении пока есть пароль владельца — известный долг D-24
  (решение — при закрытии B-3).

**Порядок выката миграции:**
1. Ручной бэкап `pg_dump -Fc` (см. раздел «Автобэкап»).
2. alembic — ДО пересоздания api: `DC run --rm api alembic upgrade head`.
3. Затем пересоздать сервисы: `DC up -d --force-recreate <сервисы>`.

**Правило GRANT.** Каждая миграция, которая добавляет таблицу, выдаёт права ролям
`app_api` / `app_projector` в той же миграции. Без этого API и проектор не увидят новую таблицу.

**env_file.** У projector и bot его нет: в их контейнерах только переменные из `environment`
в `docker-compose.dev.yml`. Новая переменная им добавляется туда явной строкой
(в `.env` одной её мало).

**Не выводить в чат целиком** (там пароли): `docker compose config` и `env` контейнера.
Список имён без значений можно: `DC exec projector env | cut -d= -f1 | sort`.

## Автобэкап

- Скрипт `~/bin/coursebot-db-backup.sh`, cron в 03:30 MSK, хранятся 14 дней.
- Перед каждой миграцией — ручной `pg_dump -Fc`. Сделаны: before-0004 (02.10.2026),
  before-0005 (05.10.2026), before-0006 (09.10.2026).
- Downgrade ниже 0004 запрещён: стирает журнал согласий.
- Копия бэкапов вне сервера — к проду.

## Часовой пояс

- Хост в **Europe/Moscow (MSK)**. journald пишет метки в MSK.
- Договорённость: **в БД храним timestamptz (Postgres хранит в UTC под капотом),
  отображаем MSK**.
- `.env`: `TZ=Europe/Moscow` (для процессов), `SERVER_TIMEZONE=Europe/Moscow`.

## Изоляция от других проектов

- Compose-project name: `course-bot` (задано в `docker-compose.dev.yml`).
- Собственная сеть: `course-bot_net` (не пересекается с `maxmover_default 172.19.0.0/16`
  и `tg_vk_bot_bot_net 172.18.0.0/16`).
- Именованные тома: `course-bot_pgdata`, `course-bot_redis-data`,
  `course-bot_garage-meta`, `course-bot_garage-data`.
- **Не использовать чужие БД/Redis** — держать полностью отдельные контейнеры.

## Крон-окна (не пересекаться)

- 03:00 — backup maxmover (HDD-нагрузка).
- 03:30 — автобэкап БД course-bot (раздел «Автобэкап»).
- 04:00 — git_backup tg_vk_bot.
- Ежеминутный `curl -I https://<domain>/miniapp/` — **путь `/miniapp/` занят
  мониторингом**. Наши эндпоинты для Mini App держим под `/app/` или `/miniapp/v1/`
  (по контракту), но не отдаём HTTP 200 на голом `/miniapp/`.

## Рантаймы на хосте

- `python3` = 3.14.4, но `pip3` НЕ установлен. Не полагаться на host-Python.
- Node.js на хосте **нет**. Сборка Mini App — только multi-stage Docker
  (`node:20-alpine` внутри Dockerfile для `apps/miniapp`).
- Архитектура требует Python **3.12** + aiogram 3 + FastAPI → в Docker-образах
  использовать `python:3.12-slim`, не хост-Python.

## Firewall (UFW)

- UFW active, deny incoming, открыт **только 22/tcp**.
- Docker публикует порты через iptables в обход UFW → любой bind на `0.0.0.0`
  выйдет в LAN. Правило «только 127.0.0.1» — не рекомендация, а требование.

## Автодеплой из GitHub Actions

- GitHub Actions **не достучится до сервера напрямую** (UFW блокирует).
- Способы:
  1. **Self-hosted runner** на сервере (простой, но требует поддержки).
  2. **Деплой через Tailscale** — сервер в оверлее по адресу `<IP-сервера-в-tailnet>`,
     runner в облаке коннектится по Tailscale.
- До первого прода автодеплой не нужен — обновление делается вручную:
  `cd ~/course-bot && git pull && docker compose --env-file .env -f infra/docker-compose.dev.yml up -d`.
  `--build` — только если менялся код (и точечно: `up -d --build <сервис>`),
  на HDD пересборка `miniapp` идёт долго. Если менялись только документы — хватит `git pull`.

## Стоп-факторы (не трогать без согласия Автора)

- `docker system prune -a --volumes` — уничтожит 6 анонимных томов чужих проектов.
- Служба `cloudflared` — принадлежит maxmover (course-bot её не использует):
  не обновлять, не переустанавливать, не выполнять `cloudflared service install`.
- Порт `/miniapp/` — уже занят мониторингом keep-alive от maxmover.
- **MinIO deprecated** — не пробовать вернуть, репо архивирован Apr 2026,
  Docker-образы удалены Sep 2026. Мы на Garage.
