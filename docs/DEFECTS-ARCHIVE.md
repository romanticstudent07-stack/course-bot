# DEFECTS-ARCHIVE.md — закрытые расхождения (архив)

Сюда переносятся записи из `docs/DEFECTS-FOUND.md`, у которых «Ждём решения Автора: нет»
и нет открытых пунктов «Остаётся», а также закрытые части действующих записей.
Тексты — дословно. Новые записи сюда не пишут: они идут в `docs/DEFECTS-FOUND.md`.
Правило А (решение Автора 04.10): решения приняты, «Остаётся» — условия будущих карточек → запись переносится целиком; в `docs/DEFECTS-FOUND.md` на её месте — строка-ссылка.

---

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
- **Зеркало исправлено:** DOCS PR #10 (`build/miniapp-frontend-stack.md`, `build/miniapp-api-contract.yaml`: CSP = E2 `csp_final`), sync PR #51.
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
- **Зеркало исправлено:** DOCS PR #9 (`build/build-order.md`: MinIO → Garage), sync PR #51.
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
- **Зеркало исправлено:** DOCS PR #9 (`build/DIVISION.md`, `build/build-order.md`), sync PR #51.
- **Ждём решения Автора:** нет.

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
- **Зеркало исправлено:** DOCS PR #11 (контракт first-launch; И1 — врезка «Уточнено реализацией»; DOCS D-32), sync PR #51.
- **Ждём решения Автора:** нет (решения приняты); правки зеркала — в DOCS-course-bot.

### D-7 (закрытые части) — initData и rate-limit

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
- **Живой 429 проверен 02.10 (закрывает B-1):** лимит временно 1/мин, в логе api
  «rate-limit: 429» = 9, fail-open = 0; через минуту «Повторить» → приложение открылось;
  лимит возвращён (в `.env` `RATE_LIMIT_PER_MINUTE` нет → действует 60 из кода).
### D-10 (закрытые части) — согласия до pid

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
- **Закрыто для Mini App — PR 1e-1b (#40) + живые проверки 02.10 (B-2 закрыт):**
  живой проход в Telegram (welcome → 18+ и дата → C1 → номер участника → «Начать»):
  C0 + C1 у единственного pid, активных pid без C0/C1 = 0, в логе api `consents_recorded=2`;
  ветка 403 «младше 18»: экран отказа без кнопок, `reason=underage` = 1, отказ ничего
  не создал (`tg_user_registry` = 1, `consent_events` = 2).

### D-19: sessionStorage в SDK (исследование 1e-2b, решение Автора 6А)

- **Версии (package-lock):** `@telegram-apps/sdk-react` 3.3.9 → `@telegram-apps/sdk` 3.11.8 →
  `@telegram-apps/bridge` ^2.11.0 (исходник смотрели в 2.11.0), `@telegram-apps/toolkit` 2.1.3.
- **Что и где:** `retrieveLaunchParams()` в bridge ищет launch params в URL, затем в `performance`
  (navigation), затем в sessionStorage; найденную строку сохраняет в sessionStorage под ключом
  с префиксом `tapps/` (`toolkit.setStorageValue` → `sessionStorage.setItem('tapps/' + key, JSON)`).
  В строке — `tgWebAppData`, сырая initData: `user` (id, имя, username), `auth_date`, `hash`,
  `signature`. Компоненты SDK кладут туда своё состояние (в коде видно `tapps/backButton`).
- **Кто вызывает у нас:** `src/index.tsx` (`retrieveLaunchParams`), `src/init.ts` (`initData.restore()`),
  dev-мок `src/mockEnv.ts` (только `import.meta.env.DEV`); `src/api/client.ts` — сверить на 0-Б.
- **Оценка:** те же данные Telegram передаёт в URL; sessionStorage живёт одну сессию webview.
  Тест «нет хранилищ» это не ловит: запись внутри SDK. Удалять ключ рискованно: после смены URL
  и перезагрузки SDK находит параметры только там → экран EnvUnsupported.
- **Решение Автора (03.10, 6А):** записать как свойство SDK, ничего не менять, пересмотреть на 0-Б.
### Закрытые части записей (шаг 8)
**D-7, было:**
- **Суть расхождения (было):** в Итерации 0-А — заглушка: заголовок
  `X-Telegram-Init-Data` обязателен, но HMAC-подпись и `auth_date` НЕ проверялись
  (`verified=False`).
**D-10, было:**
- **Было (ВРЕМЕННО, PR 1b+1c):** `pid` создавался сразу после hard-check даты рождения,
  без согласий.
**D-15 (б):**
  - **(б) участники до 0004 без C0/C1:** решение Автора 1А — долечиваются на живом
    проходе 1e-1b (повторный first-launch пишет согласия). Затем проверка
    «активные pid без give C0 или C1 = 0» обязательна перед B-3 и перед VPS.
    Выполнено 02.10: активных pid без C0/C1 = 0;
**D-14, сделано здесь:**
- **Сделано здесь (решение Автора, PR 1d):** seed — JSON, один файл на домен
  (`apps/api/config/texts/<домен>.json`, как `per_domain_files` в И4), проверка схемой
  (Draft 2020-12). API и загрузчик принимают шаблон СХЕМЫ (одна константа `KEY_PATTERN`);
  тоны — по схеме. Те же правила — в CHECK таблицы `text_registry`.
  PR 1e-1a: добавлен `legal.json` (3 заглушки).
  PR 1e-2: `B4.json` + 4 заглушки (`B4.onb_email`, `B4.onb_city`, `B4.onb_checkup`,
  `B4.onb_rules`), `legal.json` + `legal.offer`; версия обоих файлов — 0.2.0.

## D-17. Mini App: first-launch уходил без `X-Client-Op-Id`

- **Источник правила:** `AGENTS.md` (запрет №4), `AGENT-BRIEF.md` §7.
- **Файлы реализации:** `apps/miniapp/src/api/client.ts`, `apps/miniapp/src/components/OnboardingFlow.tsx`.
- **Сделано (PR 1e-2):** один uuid v4 на весь онбординг (`ref` в `OnboardingFlow`), повтор после
  ошибки — с тем же id. Сервер заголовок не читает; повторы гасит уникальность активного `tg_user_id`.
- **Остаётся:** серверная идемпотентность по `client_op_id` — с первой финансовой / state-меняющей
  операцией без естественного ключа. Правило (ревью #43): хранить только ответ 2xx и хэш тела;
  4xx (422) не хранить — повтор с тем же op-id после исправления тела выполняется заново;
  тот же op-id после 2xx с другим телом → 409 `IDEMPOTENCY_KEY_REUSED`.
- **Ждём решения Автора:** нет.

## D-19. Хранилища на устройстве: тест «нет хранилищ», TTL черновика, SDK

- **Файлы реализации:** `apps/miniapp/src/components/OnboardingFlow.test.ts`, `drafts.ts`, `LaterSteps.tsx`.
- **Сделано (PR 1e-2):** тест запрещённых подстрок проверяет `OnboardingFlow.tsx`, `LaterSteps.tsx`,
  `App.tsx`, `api/client.ts`; черновик — только `drafts.ts` (IndexedDB: `step`, `email`, `city`).
- **Сделано (PR #46, 1e-2b-2):** «Перейти к курсу» → в черновике только `{step: 'finished'}`,
  email и город стёрты; ошибка записи переход не блокирует (решение Автора 5Б).
- **Остаётся:**
  - TTL 24 ч проверяется только при открытии: не нажал «Перейти к курсу» и не открывает
    приложение → email и город лежат дольше 24 ч (I4 R380 «wipe within 24h» — остаточный риск);
  - метка `finished` живёт по тому же TTL: не открывал больше 24 ч → шаги онбординга снова
    (пока «онбординг пройден» не хранится на сервере);
  - SDK пишет launch params с сырой initData в sessionStorage (ключ `tapps/launchParams`).
    Решение Автора 03.10 (6А): свойство SDK, ничего не менять, пересмотреть на 0-Б (с CSP / XSS).
    Подробности — `docs/DEFECTS-ARCHIVE.md`, «D-19: sessionStorage в SDK».
- **Ждём решения Автора:** нет.

### Блокеры B-1, B-2 (закрытые части, 04.10)

| # | Блокер | Где описан | Статус |
|---|---|---|---|
| B-1 | Rate-limit на `/miniapp/v1/**` (Б14 R328) | D-7 | **закрыт**: код PR #36 + живой 429 02.10 (лимит временно 1/мин: «rate-limit: 429» = 9, fail-open = 0; лимит возвращён) |
| B-2 | Согласия (`legal_consents`, C0 (18+) и C1 (ПДн); C2–C6 — позже) **до** создания `pid` (ADD3 ordering) | D-10 | **закрыт**: API PR #38 + экраны PR #40 + живой проход 02.10 (C0 + C1 у единственного pid, активных pid без C0/C1 = 0); отмечено в PR 1e-2 |

### D-5 (закрытые части, 04.10)

- **Сделано здесь:** `infra/README.md` переписан под Tailscale serve;
  `infra/CLOUDFLARE-TUNNEL.md` сохранён как архив с предупреждением «НЕ применять
  на IRONCLAD».

### D-9 (закрытые части, 04.10)

     **PR 1b+1c (решение Автора):** применён SEAM-1 — неизвестный `tg_user_id` на
     first-launch создаётся, 403 для него не отдаётся (403 — только возрастной гейт).
     Мок 501 и `details.tg_user_id` удалены. Правка зеркала (пометить R327 отменённым) —
     по-прежнему в DOCS-course-bot.
- **Сделано здесь (решение Автора, PR 1a):** TTL по умолчанию 86400 (как в контракте);
  `auth_date > now + 60 с` — отказ; 503 `SERVICE_MISCONFIGURED` при пустом `BOT_TOKEN`.
  Для R327 ничего не делалось — применяется SEAM-1 как старший слой.

## D-15. Ревью #38 (1e-1a): отложенное

- **Файл архитектуры (зеркало):** `normative/errata-unified.md` (ADD3 ordering),
  И1 R_378 (`consent_events`, append-only) — см. D-10.
- **Файлы реализации:** `apps/api/app/routers/onboarding.py`, `apps/api/app/participants.py`,
  `apps/api/app/db/models.py`, `apps/api/migrations/versions/…0004_consent_events…`.
- **Суть расхождения:** РЕВЬЮЕР PR #38 блокирующих замечаний не нашёл; неблокирующие
  и решения Автора по ним собраны здесь:
  - **(а) revoke:** сейчас «согласие дано» = есть событие give. Когда появится revoke,
    given считать по ПОСЛЕДНЕМУ событию на kind. Это условие для первой задачи,
    которая пишет revoke. PR 1e-2: чтение `GET /miniapp/v1/consents` уже считает
    по последнему событию на kind; запись give в first-launch пока проверяет только give;
  - **(б)** выполнено 02.10 (активных pid без C0/C1 = 0), повторить перед B-3a и VPS — текст в архиве;
  - **(в) `ver_of_text`:** снимок текста берётся в момент first-launch, а клиент видел
    текст раньше (версия могла смениться между показом и отправкой). Решение Автора 2А:
    для И1 допустимо; до 0-Б клиент шлёт версию показанного текста, сервер сверяет
    (блокер к 0-Б). Первая смена версии — `legal.json` 0.2.0 в PR 1e-2: после загрузки
    текстов у старых записей `consent_events` `ver_of_text` обязан остаться 0.1.0;
  - **(г) в B-3 добавить тесты:** откат после get_or_create (OperationalError на INSERT
    `consent_events` → 0 строк участника); гонка для участника до 0004 (8 потоков →
    ровно 2 give); явный rollback для любых исключений в first-launch;
  - **(д) downgrade 0004 = DROP журнала согласий:** на сервере запрещён; откат только
    через бэкап (before-0004) по решению Автора;
  - **(е) compare_metadata не сравнивает CHECK:** ограничения `consent_events` сейчас
    сверены глазами; тест через `pg_constraint` — позже.
- **Предлагаемое решение:** (а) — в карточку первой задачи с revoke; (б) — в 1e-1b
  и в критерии B-3; (в) — в план 0-Б; (г) и (е) — в карточку B-3; (д) — в задания серверу.
- **Ждём решения Автора:** нет (решения 1А/2А приняты 02.10).

## D-18. Ошибки 422 и 500 приходят не в формате `Error`

- **Файл архитектуры (зеркало):** `build/miniapp-api-contract.yaml` (`components.schemas.Error`).
- **Файл реализации:** `apps/api/app/errors.py` (ловит только `HTTPException`).
- **Суть расхождения:** (1) `RequestValidationError` → стандартный `{"detail": [...]}` с полем
  `input` (для first-launch дата рождения возвращается клиенту); клиент видит `HTTP_ERROR`.
  (2) Ревью #43: прочие исключения в first-launch и `/consents` → 500 текстом без `code`;
  traceback со значениями параметров SQL уходит в лог api.
- **Предлагаемое решение:** 422 `{code: "VALIDATION_ERROR", details: {errors: [{loc, type}]}}`
  без значений полей; общий перехват → 500 с кодом `INTERNAL_ERROR`, в лог только имя класса;
  `hide_parameters=True` у движка. Тесты с `"detail"` в 422 — поменять.
- **Решение Автора (03.10):** «D-18 в B-3» → карточка `docs/tasks/B-3b.md`.
- **Контракт:** формат 422 зафиксирован в контракте DOCS PR #11 — B-3b делает ровно его.
- **Ждём решения Автора:** нет.
