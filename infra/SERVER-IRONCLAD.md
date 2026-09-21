# infra/SERVER-IRONCLAD.md — факт-памятка о сервере разработки

Кратко: сервер, на котором разработка запускается локально до переезда на VPS/Cloud.
Полный аудит — у Автора в файле `IRONCLAD-factsheet.md` (не в репо, персональный документ).
Здесь только те факты, которые нужны Агенту при написании кода и docker-конфигов.

## Правила публикации портов

- **Только `127.0.0.1`.** Никогда `0.0.0.0` и никогда без явного bind-хоста
  (`docker-compose` по умолчанию биндит на 0.0.0.0 → выход в LAN!).
- Наружу — **только** через Cloudflare Tunnel (см. `CLOUDFLARE-TUNNEL.md`).

## Занятые порты (не использовать)

| Порт | Кем занят |
|---|---|
| 22 | SSH |
| 53 | systemd-resolved |
| 323 | chronyd (NTP) |
| 5434 | maxmover PostgreSQL |
| 6381 | maxmover Redis |
| 8443 | maxmover webhook |
| 20241, 38725 | cloudflared / containerd |

## Порты для course-bot (свободны на 2026-09-19)

| Сервис | Порт | Bind |
|---|---|---|
| API (FastAPI) | 8080 | 127.0.0.1 |
| PostgreSQL 16 | 5435 | 127.0.0.1 |
| Redis 7 | 6382 | 127.0.0.1 |
| MinIO S3 | 9000 | 127.0.0.1 |
| MinIO Console | 9001 | 127.0.0.1 |

## Ресурсы (жёсткие лимиты)

- RAM свободно ≈ 4.6 GiB. Сумма лимитов всех контейнеров course-bot **≤ 900 MB**.
- Лимиты заданы в `.env` через `MEM_LIMIT_*` и применяются в `docker-compose.dev.yml`.
- HDD 5400 rpm — сборки медленные. Использовать `python:3.12-slim`, `redis:7-alpine`,
  `postgres:16` (не полные образы).
- Docker build-cache чистить перед крупными сборками: `docker builder prune`.

## Часовой пояс

- Хост в **Europe/Moscow (MSK)**. journald пишет метки в MSK.
- Договорённость: **в БД храним UTC, отображаем MSK**.
- `.env`: `TZ=UTC` (для процессов), `SERVER_TIMEZONE=Europe/Moscow` (для отображения).

## Изоляция от других проектов

- Compose-project name: `course-bot` (задано в `docker-compose.dev.yml`).
- Собственная сеть: `course-bot_net` (не пересекается с `maxmover_default 172.19.0.0/16`
  и `tg_vk_bot_bot_net 172.18.0.0/16`).
- Именованные тома: `course-bot_pgdata`, `course-bot_redis-data`, `course-bot_minio-data`.
- **Не использовать чужие БД/Redis** — держать полностью отдельные контейнеры.

## Крон-окна (не пересекаться)

- 03:00 — backup maxmover (HDD-нагрузка).
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
  2. **Деплой через Tailscale** — сервер в оверлее по адресу `100.106.29.5`,
     runner в облаке коннектится по Tailscale.
- До первого прода автодеплой не нужен — обновление делается вручную:
  `git pull && docker compose up -d --build`.

## Стоп-факторы (не трогать без согласия Автора)

- `docker system prune -a --volumes` — уничтожит 6 анонимных томов чужих проектов.
- Обновление `cloudflared` — обслуживает и maxmover, обновлять аккуратно.
- Порт `/miniapp/` — уже занят мониторингом keep-alive от maxmover.
