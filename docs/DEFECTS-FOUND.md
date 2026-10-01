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

## ⛔ Блокеры до выхода на VPS (любой внешний доступ, кроме Автора в tailnet)

Пока пункты ниже не закрыты, Mini App **не открывать** никому, кроме Автора
(dev-вход — Tailscale serve, только tailnet). Список ведёт агент; закрывает — PR + решение Автора.

| # | Блокер | Где описан | Статус |
|---|---|---|---|
| B-1 | Rate-limit на `/miniapp/v1/**` (Б14 R328) | D-7 | реализован, PR #36 |
| B-2 | Согласия (`legal_consents`, C1–C6) **до** создания `pid` (ADD3 ordering) | D-10 | реализован (API), PR #38; экраны — 1e-1b |
| B-3 | Роли и GRANT в БД: приложение ходит под владельцем БД; ролей/GRANT на `tg_user_registry` нет | D-13 | не реализовано |

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
- **Закрыто PR B-1 (#36, «B-1: rate-limit /miniapp/v1 — Redis, 60/мин на tg_user_id, fail-open»):**
  - rate-limit на `/miniapp/v1/**` (Б14 R328, §14.13) — `apps/api/app/rate_limit.py`:
    фиксированное окно 1 мин в Redis (`rl:miniapp:{tg_user_id}:{unix_minute}`, INCR + EXPIRE 120),
    лимит `RATE_LIMIT_PER_MINUTE` (по умолчанию 60); превышение → 429 `RATE_LIMITED` + `Retry-After`;
  - ключ — `tg_user_id` из проверенной initData, а не `pid`, как в R328 (`pid` есть не у всех:
    его создаёт first-launch); unauth без лимита: отдельного `/auth` нет, поэтому «10/мин на unauth
    `/auth`» из §14.13 не применяется — запросы без валидной initData отсекаются 401 раньше
    счётчика и не считаются (решение Автора 5Б);
  - Redis недоступен или `REDIS_URL` пуст → fail-open: запрос проходит, WARNING в лог
    (только имя исключения); nginx-лимит не делается: за туннелем один IP (решение Автора 5Б).
- **Остаётся открытым:**
  - противоречие источников по TTL и `session_jwt` — см. D-9;
  - rate-limit, РЕВЬЮЕР PR #36 (неблокирующее): INCR и EXPIRE — две команды; при сбое между
    ними ключ остаётся без TTL (ключ поминутный — лимит не «залипает», только лишние байты
    в Redis). Фикс позже: MULTI/pipeline (INCR + EXPIRE) или Lua;
  - rate-limit, РЕВЬЮЕР PR #36 (неблокирующее): при недоступном Redis каждый запрос ждёт
    до ~0,4 с (connect + read по 0,2 с) в пуле потоков. Фикс позже: «предохранитель» —
    после ошибки N секунд не обращаться к Redis;
  - живой 429 на сервере не проверялся (нужна настоящая initData) — в 1e-1b;
  - TTL 1 ч для `/refund`, `/erasure_*` (`init_data_sensitive_max_age_seconds` есть
    в config, но не применяется — таких маршрутов ещё нет);
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
     **PR 1b+1c (решение Автора):** применён SEAM-1 — неизвестный `tg_user_id` на
     first-launch создаётся, 403 для него не отдаётся (403 — только возрастной гейт).
     Мок 501 и `details.tg_user_id` удалены. Правка зеркала (пометить R327 отменённым) —
     по-прежнему в DOCS-course-bot.
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

## D-10. Порядок first-launch: согласия и оплата до `pid` — источники расходятся, в контракте их нет

- **Файлы архитектуры (зеркало):**
  - `normative/errata-unified.md` → ADD3: `ordering: [age_soft_checkbox, age_hard_check_dob,
    legal_consents, pid_creation]`;
  - `build/miniapp-security-checklist.md` §3: `age_gate → legal_consents → payment → pid_creation`;
  - `AGENTS.md` (репо реализации), «Связь с Mini App»: сначала SEAM-1 создаёт participant,
    потом проверяется `payment_confirmed`, потом Age Gate → PID;
  - `build/miniapp-api-contract.yaml` → first-launch: в теле только `birth_date`
    (нет ни soft-checkbox, ни согласий, ни ссылки на оплату);
  - И1 R_378 (`consent_events: [pid, kind, action, at, ip, ua, ver_of_text]`, append-only), И1 D_14.
- **Файлы реализации:** `apps/api/app/routers/onboarding.py`, `apps/api/app/participants.py`,
  `apps/api/app/db/models.py`, `apps/api/migrations/versions/…0004_consent_events…`,
  `apps/api/config/texts/legal.json`.
- **Суть расхождения:** три разных порядка (оплата до `pid` / после / не упомянута), а контракт
  first-launch не несёт данных ни для согласий, ни для soft-checkbox 18+.
- **Было (ВРЕМЕННО, PR 1b+1c):** `pid` создавался сразу после hard-check даты рождения,
  без согласий.
- **Закрыто для API — PR 1e-1a (#38), решения Автора «1А», «2А», «В1 А»:**
  - порядок: initData → тело → hard-check 18+ без БД (403) → обязательные согласия (422) →
    ОДНА транзакция: тексты согласий из `text_registry` → `pid` (get_or_create) →
    `consent_events` → commit. Нет текста согласия в `text_registry` → откат,
    503 `SERVICE_MISCONFIGURED`, `pid` не создаётся;
  - **расширение контракта:** тело first-launch `{birth_date, consents: ["C0", "C1"]}`,
    `consents` обязателен; 422 `CONSENTS_REQUIRED` `{details: {missing: [...]}}`;
    дубли и id вне C0–C6 — 422 валидации тела; C2–C6 на first-launch — 422
    `CONSENT_NOT_SUPPORTED` `{details: {unsupported: [...]}}` (текстов для них нет;
    C5 — свой экран перед фото);
  - текст согласия выбирает сервер (`CONSENT_TEXT_KEYS`), клиент шлёт только id;
  - **сверх колонок R_378:** `id`, `text_key` (FK `text_registry`), `text_snapshot`
    (принятый текст), `created_via`; `ver_of_text` = `registry_version`;
  - **`ip` и `ua` не заполняются (NULL):** за туннелем IP недостоверен,
    `--proxy-headers` — к проду;
  - повтор → 201 тот же `pid`, без дублей give; участник, созданный до 0004, получает
    согласия при повторном first-launch; гонка — строка участника блокируется до commit;
  - append-only: UPDATE/DELETE запретит GRANT в B-3 (D-13).
- **Остаётся:** экраны Mini App и живой проход в Telegram — 1e-1b; оплата до `pid` —
  до решения противоречия по оплате; правка контракта — в DOCS-course-bot.
- **Ждём решения Автора:** нет для API; по оплате — да.

## D-11. `participant_state.lifecycle_phase`: значения 0001 ≠ FSM И2

- **Файлы архитектуры (зеркало):** `build/db-schema.sql` (комментарий к `lifecycle_phase`:
  `pre_road, active, pending_erasure, erased`) vs `normative/I2-wave-b.md` →
  `participant_state_contract.fsm_participant.states: [pre_registered, onboarding, active,
  sleeping, muted, erased]`.
- **Файл реализации:** `apps/api/migrations/versions/…0001_init…` (дословно из db-schema.sql).
- **Суть расхождения:** два разных набора состояний; неясно, какая фаза у участника сразу
  после first-launch.
- **Сделано здесь:** ничего — в PR 1b+1c `participant_state` не пишется (решение Автора:
  писатель — только проектор, E1/INV-1; отдельный PR вместе с проектором).
- **Ждём решения Автора:** да — до PR с проектором.

## D-12. first-launch: `short_no` и ответы вне контракта

- **Файлы архитектуры (зеркало):** `normative/I1-wave-a.md` (`tg_user_id_pid_registry.columns`
  без `short_no`), `06-participant-card.md` §6.3 (`short_number: "#000123"`,
  `assigned_at: registration`), `build/miniapp-api-contract.yaml` (first-launch: 201/401/403).
- **Файлы реализации:** `apps/api/migrations/versions/…0002_tg_user_registry…`,
  `apps/api/app/routers/onboarding.py`, `apps/api/app/participants.py`.
- **Суть расхождения / сделано здесь:**
  1. **`short_no`** есть в контракте (`PidCreated`) и в Б6, но не в колонках И1. Добавлен в
     `tg_user_registry` как `bigint GENERATED ALWAYS AS IDENTITY UNIQUE`, формат ответа
     `#%06d` (после 999999 — больше цифр). **Пропуски номеров возможны** (конфликт/гонка/откат
     расходуют значение последовательности) — допустимо, номер только для показа (решение Автора).
  2. **Повторный вызов** → 201 с тем же телом (как в контракте, решение Автора). После
     tombstone тот же `tg_user_id` получает новый `pid` и новый `short_no` (И1, Р243).
  3. **503 `SERVICE_UNAVAILABLE`** (БД недоступна) — в формате `schemas.Error`, в контракте
     такого ответа нет (решение Автора). Также 503 `SERVICE_MISCONFIGURED`, если
     `SERVER_TIMEZONE` неизвестен (fail closed; для пустого `BOT_TOKEN` — см. D-9 п.3).
  4. **422** (`BIRTH_DATE_IN_FUTURE` и ошибки валидации тела) — в контракте нет.
  5. **«Сегодня» для возраста** — дата в `SERVER_TIMEZONE` (Europe/Moscow), а не
     `tz_at(pid_candidate)` из ADD3: часовой пояс участника на first-launch ещё неизвестен
     (решение Автора).
  6. **Дата рождения не хранится** (решение Автора): проверка только в момент запроса.
- **Предлагаемое решение:** в DOCS-course-bot добавить `short_no` в колонки И1, описать
  в контракте 422/503 и семантику повторного 201.
- **Ждём решения Автора:** нет (решения приняты); правки зеркала — в DOCS-course-bot.

## D-13. Роли и GRANT для `tg_user_registry` не определены; приложение ходит под владельцем БД

- **Файлы архитектуры (зеркало):** `build/db-schema.sql` (6 ролей, GRANT только на таблицы 0001),
  `build/db-tables-index.md` (роли только для `participant_state`), `normative/I2-wave-b.md`
  (`read_only_enforcement`), `normative/OVERRIDES.yaml` N-02.
- **Файлы реализации:** `apps/api/migrations/versions/…0002_tg_user_registry…`,
  `apps/api/app/db/session.py` (DSN из `.env` — сейчас пользователь-владелец БД).
- **Суть расхождения:** для `tg_user_registry` ролей/GRANT в архитектуре нет. API подключается
  под `POSTGRES_USER` (владелец БД) — это обходит INV-1/E1 на уровне прав (приложение
  технически может писать и в `participant_state`).
- **Сделано здесь:** ничего (решение Автора — отложить). В коде API запись в
  `participant_state` отсутствует. Добавилась `consent_events` (0004): для неё в B-3 —
  только SELECT, INSERT (append-only).
- **⛔ БЛОКЕР к проду / до VPS (B-3):** отдельная роль приложения с минимальными GRANT
  (`tg_user_registry`: SELECT, INSERT; `participant_state`: только через reader/projector).
- **Ждём решения Автора:** да — набор ролей и кто их создаёт (миграция vs ручная операция).

## D-14. text_registry: шаблон ключа, формат seed и тоны — источники расходятся

- **Файлы архитектуры (зеркало):** `build/config-schemas/text_registry.schema.json`,
  `build/miniapp-api-contract.yaml` (`GET /miniapp/v1/texts/{key}`, `POST /miniapp/v1/texts/bulk`),
  `normative/I4-wave-d.md` §1.
- **Файлы реализации:** `apps/api/app/texts.py` (`KEY_PATTERN`, загрузчик), `apps/api/app/routers/texts.py`,
  `apps/api/config/texts/B4.json`, `apps/api/migrations/versions/…0003_text_registry…`.
- **Суть расхождения:**
  1. **Ключ:** схема — `^(B2|B4|B5|B7|B9|B10|B14|B15|B16|legal)\.[a-z][a-z0-9_]*$` (домены
     B2…B16 с заглавной B и `legal`); контракт — только строчные `^[a-z0-9_]+\.[a-z0-9_]+$`.
     Ключ `B4.onb_welcome` проходит схему, но не контракт; `b4.onb_welcome` — наоборот.
  2. **Формат seed:** И4 — `versioned_yaml_in_git`, `config/texts/*.yaml`; схема проверяет JSON.
  3. **Тоны:** И4 — soft / neutral / dry; схема — soft / neutral / strict.
- **Сделано здесь (решение Автора, PR 1d):** seed — JSON, один файл на домен
  (`apps/api/config/texts/<домен>.json`, как `per_domain_files` в И4), проверка схемой
  (Draft 2020-12). API и загрузчик принимают шаблон СХЕМЫ (одна константа `KEY_PATTERN`);
  тоны — по схеме. Те же правила — в CHECK таблицы `text_registry`.
  PR 1e-1a: добавлен `legal.json` (3 заглушки).
- **Предлагаемое решение:** в DOCS-course-bot привести к схеме шаблон ключа в контракте,
  а в И4 — формат (JSON), путь и набор тонов.
- **Ждём решения Автора:** да — правка зеркала в DOCS-course-bot.

<!-- следующие записи (D-15, ...) добавляет агент по мере обнаружения -->
