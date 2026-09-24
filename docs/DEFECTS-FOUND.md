# DEFECTS-FOUND.md — расхождения архитектуры с реальностью

Сюда агент пишет расхождения, найденные при реализации.

**НЕ править `docs/architecture/**`** — это read-only зеркало.
Все правки архитектуры делаются в репо DOCS-course-bot.

## Формат записи

## D-N. Краткое название

- **Файл архитектуры (зеркало):** `docs/architecture/…`
- **Файл реализации:** `apps/…`
- **Суть расхождения:** описание что не сходится.
- **Предлагаемое решение:** что предлагает агент.
- **Ждём решения Автора:** да/нет.

---

## D-1. Блок 15: доставка медиа

- **Файл архитектуры (зеркало):** `docs/architecture/build/DIVISION.md`,
  `docs/architecture/15-content-antipiracy.md` (и подпапка `15/`).
- **Файл реализации:** пока не создан.
- **Суть расхождения:** DIVISION.md говорит, что Mini App отдаёт медиа
  через pre-signed URL. Блок 15 (антипираттство) утверждает,
  что видео и материалы курса живут только во внешнем публичном
  Telegram-канале, бот не хостит медиа и не отдаёт `file_id`.
  Схемы «pre-signed URL» и «внешний Telegram-канал» противоречат друг другу.
- **Предлагаемое решение:** Автору определить, какой источник медиа —
  S3 pre-signed URL для собственного хостинга или внешний Telegram-канал.
- **Ждём решения Автора:** да.

## D-2. CSP: три разные редакции в зеркале

- **Файл архитектуры (зеркало):** `normative/errata-unified.md` (E2 `csp_final`),
  `build/miniapp-frontend-stack.md`, `build/miniapp-api-contract.yaml` (комментарий в конце).
- **Файл реализации:** `apps/miniapp/nginx.conf`.
- **Суть расхождения:** E2 разрешает `script-src 'self' https://telegram.org`
  и `frame-ancestors https://web.telegram.org https://telegram.org`. В build-файлах
  указаны `script-src 'self'`, `connect-src 'self' https://api.telegram.org`
  и `frame-ancestors https://web.telegram.org https://t.me`.
- **Решение агента:** взята редакция E2 (у ERRATA высшее старшинство). Домен
  `{s3-domain-ru}` не подставлен: это плейсхолдер-шлюз, решение Автора.
- **Решение Автора:** выравнивать CSP в DOCS-course-bot, не здесь.
  В `apps/miniapp/nginx.conf` остаётся редакция E2.
- **Ждём решения Автора:** нет.

## D-3. Остатки MinIO и версия Garage в документах

- **Файл архитектуры (зеркало):** `build/build-order.md` (Итерация 0-А: «MinIO», `minio-init`).
- **Файлы вне зеркала:** `.genspark/rules.md` (хосты `minio:9000`),
  `infra/SERVER-IRONCLAD.md` (`dxflrs/garage:v2.1.0`, а в compose и README — `v2.3.0`).
- **Суть расхождения:** MinIO устарел, код использует Garage (`http://garage:3900`).
- **Решение агента:** в коде только Garage.
- **Статус:** вне зеркала исправлено — `.genspark/rules.md` (хосты MinIO → Garage
  `garage:3900` / `127.0.0.1:9000`) и `infra/SERVER-IRONCLAD.md` (`v2.1.0` → `v2.3.0`)
  в PR «docs: dev-вход через Tailscale, --env-file, остатки MinIO».
  MinIO в зеркале (`build/build-order.md`: Итерация 0-А, `minio`, `minio-init`,
  состав `docker-compose.yaml`) — править в DOCS-course-bot.
- **Ждём решения Автора:** нет (правка зеркала — в DOCS-course-bot).

## D-4. Кто принимает Telegram webhook

- **Файл архитектуры (зеркало):** `build/DIVISION.md` (backend: «Обработчик Telegram Webhook»).
- **Файлы реализации:** `apps/bot/bot/app.py`, `infra/README.md` (шаг 8: `setWebhook` → `/webhook/telegram`).
- **Суть расхождения:** по DIVISION апдейты принимает backend, но диспетчер
  aiogram живёт в `apps/bot`. Контракт передачи апдейтов api → bot не описан.
- **Решение агента:** в Итерации 0-А бот работает на long polling (входящий порт
  не нужен). Если webhook зарегистрирован, бот его не удаляет, а пишет ошибку в лог.
- **Решено (Автор):** long polling до отдельной итерации webhook. `setWebhook`
  в `infra/README.md` помечен «НЕ выполнять», добавлена команда `deleteWebhook`.
- **Ждём решения Автора:** нет.

## D-5. Публичный вход: Cloudflare Tunnel неприменим

- **Файл архитектуры (зеркало):** `build/build-order.md` (Итерация 0-А: «публичный
  HTTPS через Cloudflare Tunnel», шаг 1 «`cloudflared` установлен», шаг 3
  «именованный туннель», ссылка на `infra/CLOUDFLARE-TUNNEL.md`).
- **Файлы реализации:** `infra/README.md`, `infra/CLOUDFLARE-TUNNEL.md`,
  `infra/SERVER-IRONCLAD.md`.
- **Суть расхождения:** зеркало предполагает Cloudflare Tunnel как вход. Факты
  (проверены Автором на IRONCLAD 24.09.2026):
  - Cloudflare Tunnel из РФ нестабилен: ~2200 обрывов за месяц;
  - на сервере работает служба `cloudflared` чужого проекта maxmover —
    `cloudflared service install` для course-bot с ней конфликтует; её не трогать;
  - dev-вход — Tailscale serve (только tailnet, только Автор);
  - прод / внешние тестировщики — позже: российский VPS как вход, туннель
    дом→VPS через autossh или WireGuard (не Tailscale: из РФ блокируются его
    админка и логин).
- **Сделано здесь:** `infra/README.md` переписан под Tailscale serve;
  `infra/CLOUDFLARE-TUNNEL.md` сохранён как архив с предупреждением «НЕ применять
  на IRONCLAD».
- **Предлагаемое решение:** в DOCS-course-bot поправить `build/build-order.md`
  (вход Итерации 0-А и ссылку на `infra/CLOUDFLARE-TUNNEL.md`).
- **Ждём решения Автора:** да — провайдер VPS.

## D-6. Ограничения Telegram в РФ

- **Файл архитектуры (зеркало):** `build/build-order.md` (Итерация 0-Б, хостинг),
  `99-legal.md` / `99/` (152-ФЗ).
- **Файлы реализации:** пока нет (инфраструктурный риск).
- **Суть расхождения:** с февраля 2026 ограничения Telegram в РФ нарастают.
  Архитектура не учитывает риски:
  - участникам может понадобиться VPN, чтобы открыть бота и Mini App;
  - боту на РФ-VPS могут ограничить доступ к `api.telegram.org`
    (long polling и отправка сообщений перестанут работать).
- **Предлагаемое решение:** нужна позиция Автора: где хостить бота (доступ
  к `api.telegram.org`) и где хранить данные участников (152-ФЗ — в РФ).
  Агент вариантов не выбирает.
- **Ждём решения Автора:** да.

## D-7. initData без проверки подписи

- **Файл архитектуры (зеркало):** `build/miniapp-api-contract.yaml`
  (`securitySchemes.TelegramInitData`), `build/miniapp-security-checklist.md`,
  `build/build-order.md` (Итерация 1: «Валидация `initData` на сервере»).
- **Файл реализации:** `apps/api/app/telegram_init_data.py`, `apps/api/main.py`.
- **Суть расхождения (было):** в Итерации 0-А — заглушка: заголовок
  `X-Telegram-Init-Data` обязателен, но HMAC-подпись и `auth_date` НЕ проверялись
  (`verified=False`).
- **Закрыто PR 1a («Итерация 1a: проверка initData (HMAC + TTL)»):**
  - HMAC-SHA256 по алгоритму Telegram (`secret_key = HMAC("WebAppData", BOT_TOKEN)`,
    `data_check_string` без `hash`, поле `signature` и неизвестные поля остаются),
    сравнение `hmac.compare_digest`; только стандартная библиотека;
  - TTL `auth_date` — `INIT_DATA_MAX_AGE_SECONDS`, по умолчанию 86400; `auth_date`
    дальше `now + 60 с` (`init_data_future_skew_seconds`) — отказ;
  - зависимость `require_init_data` на уровне роутера — на ВСЕХ `/miniapp/v1/**`;
    `/healthz` и `/security/csp-report` — без проверки;
  - ответы: 401 `TG_INIT_MISSING` (нет/пустой заголовок), 401 `TG_INIT_INVALID`
    (всё остальное), 503 `SERVICE_MISCONFIGURED` (пустой `BOT_TOKEN`, fail closed);
    в лог — только причина (`reason`), без initData, hash и токена;
  - dev-обхода проверки нет.
- **Остаётся открытым:**
  - противоречие источников по TTL и `session_jwt` — см. D-9;
  - TTL 1 ч для `/refund`, `/erasure_*` (`init_data_sensitive_max_age_seconds` есть
    в config, но не применяется — таких маршрутов ещё нет);
  - rate-limit на `/miniapp/v1/**` (Б14 R328) — не реализован;
  - анти-replay сверх TTL (одна initData может использоваться многократно в пределах
    24 ч) — зависит от решения по D-9;
  - R344 (сверка `user.id` vs `query_id`, security-audit) — не реализовано.
- **Ждём решения Автора:** нет по самой проверке; по TTL — см. D-9.

## D-8. BotFather: `/setmenubutton`, `/setdomain`, `/newapp` не нужны для Mini App

- **Файл архитектуры (зеркало):** `build/DIVISION.md` (Bot: «Меню-кнопка → открытие
  Mini App (`WebAppInfo`, `/setmenubutton`)»; приоритеты бота, п.1: «Menu Button →
  Mini App URL (`/setmenubutton` в BotFather)»), `build/build-order.md`
  (Итерация 0-А, шаг 2: `/newbot`, `/newapp` «домен привяжется после туннеля»;
  Итерация 0-Б, шаг 2: `/newbot`, `/newapp`, `/setmenubutton https://<s3-domain-ru>/`, `/setdomain`).
- **Файлы реализации:** `apps/bot/bot/app.py` (Menu Button ставится ботом через
  `set_chat_menu_button` из `WEBAPP_URL`), `infra/README.md` (шаги 1 и 8).
- **Суть расхождения:** зеркало описывает настройку Mini App руками в BotFather.
  Факты (проверены Автором на IRONCLAD):
  - Menu Button бот ставит сам при старте из `WEBAPP_URL` — `/setmenubutton` не нужен;
  - `/setdomain` — настройка Telegram Login Widget, к Mini App отношения не имеет;
  - `/newapp` нужен только для прямой ссылки вида `t.me/<бот>/<app>`.
- **Сделано здесь:** `infra/README.md`, шаги 1 и 8, переписаны под эти факты.
- **Предлагаемое решение:** править в DOCS-course-bot (`build/DIVISION.md`,
  `build/build-order.md`): Menu Button — через Bot API из `WEBAPP_URL`;
  `/setdomain` — только для Login Widget; `/newapp` — только для прямой ссылки.
- **Ждём решения Автора:** нет.

## D-9. initData: противоречия в зеркале (TTL, session_jwt, 403 vs SEAM-1, 503)

- **Файлы архитектуры (зеркало):**
  - `build/miniapp-api-contract.yaml` → `securitySchemes.TelegramInitData`:
    TTL `auth_date` 24 ч (1 ч для `/erasure`, `/refund`); ответы 401/403/409, **503 нет**;
  - `AGENTS.source.md` и `build/miniapp-frontend-stack.md` (§Аутентификация): 24 ч / 1 ч;
  - `build/miniapp-security-checklist.md` §2: `max_age_seconds`, «ориентир — 3600»;
  - `14-data-durability.md` §14.13, `INV-B14-INITDATA-TTL`, `R325`–`R327`,
    `auth_date_ttl: {write: 300, read: 3600}`: TTL 5 мин (write) / 60 мин (read),
    затем `POST /miniapp/auth` → `session_jwt` HS256 TTL 60 мин;
    `R327`: «несуществующий `tg_user_id` → 403 (участник создаётся только через
    bot-онбординг); авто-создание участника через Mini App запрещено».
- **Файлы реализации:** `apps/api/app/telegram_init_data.py`, `apps/api/app/config.py`,
  `.env.example`.
- **Суть расхождения:**
  1. **TTL:** три разных значения (24 ч / 3600 / 300+3600). Модель Б14 опирается на
     `session_jwt`, которого в контракте `miniapp-api-contract.yaml` нет (там initData
     на каждом запросе). Без `session_jwt` TTL 300 с сломает Mini App через 5 минут.
  2. **403 для неизвестного `tg_user_id` (Б14 R327) vs SEAM-PATCH-1:** SEAM-1 (выше Б14
     по старшинству) делает first-launch Mini App ЕДИНСТВЕННОЙ точкой создания участника;
     R327 это прямо запрещает. Для PR 1a не критично (проверка initData от этого не
     зависит), но важно для PR 1b+ (first-launch с БД).
  3. **503:** контракт не описывает ответ при неправильной конфигурации сервера
     (пустой `BOT_TOKEN`). Реализация отвечает 503 `SERVICE_MISCONFIGURED` в формате
     `schemas.Error` — в контракте такого ответа нет.
- **Сделано здесь (решение Автора, PR 1a):** TTL по умолчанию 86400 (как в контракте);
  `auth_date > now + 60 с` — отказ; 503 `SERVICE_MISCONFIGURED` при пустом `BOT_TOKEN`.
  Для R327 ничего не делалось — применяется SEAM-1 как старший слой.
- **Предлагаемое решение:** в DOCS-course-bot
  (а) выбрать одну модель авторизации: «initData на каждом запросе, TTL N» или
  «initData → session_jwt» (Б14) и привести к ней контракт, checklist и Б14;
  (б) пометить R327 как отменённый SEAM-PATCH-1 (или внести в OVERRIDES);
  (в) добавить в контракт `503` (`SERVICE_MISCONFIGURED`) в `components.responses`.
- **Ждём решения Автора:** да — модель авторизации и TTL к проду (когда появится
  `session_jwt` или будет решено без него); правки зеркала — в DOCS-course-bot.

<!-- следующие записи (D-10, ...) добавляет агент по мере обнаружения -->
