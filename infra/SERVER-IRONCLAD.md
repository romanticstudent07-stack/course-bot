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
  (решение Автора, 25.09.2026; было ≤ 1.5 GB). Сейчас сумма лимитов — 1664 МБ
  (api 384 + db 384 + bot 512 + garage 192 + miniapp 128 + redis 64).
  Реальное потребление стека ~290 МБ (замер 25.09.2026; бот ~155 МБ — базовый объём,
  утечки нет, наблюдение 24–25.09.2026).
- Перед добавлением контейнера или повышением лимита — проверить, что сумма остаётся ≤ 2 GB.
- Лимиты заданы в `.env` через `MEM_LIMIT_*` и применяются в `docker-compose.dev.yml`.
- HDD 5400 rpm — сборки медленные. Использовать `python:3.12-slim`, `redis:7-alpine`,
  `postgres:16` (не полные образы), `dxflrs/garage`.
- Docker build-cache чистить перед крупными сборками: `docker builder prune`.

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
