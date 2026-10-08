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
| B-1 | Rate-limit на `/miniapp/v1/**` (Б14 R328) | D-7 | **закрыт** (PR #36, живой 429 02.10) — подробности: `docs/DEFECTS-ARCHIVE.md` |
| B-2 | Согласия (`legal_consents`, C0 (18+) и C1 (ПДн); C2–C6 — позже) **до** создания `pid` (ADD3 ordering) | D-10 | **закрыт** (PR #38, #40, живой проход 02.10) — подробности: `docs/DEFECTS-ARCHIVE.md` |
| B-3 | Роли и GRANT в БД: приложение ходит под владельцем БД; ролей/GRANT на `tg_user_registry` нет | D-13 | не реализовано |

Закрытые записи и закрытые части записей — `docs/DEFECTS-ARCHIVE.md`.

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
- **Сделано здесь:** — `docs/DEFECTS-ARCHIVE.md`, «D-5 (закрытые части, 04.10)».
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
- **Закрытые части записи** (было, PR 1a, PR B-1 #36, живой 429 02.10) — `docs/DEFECTS-ARCHIVE.md`, «D-7 (закрытые части)».
- **Остаётся открытым:**
  - противоречие источников по TTL и `session_jwt` — см. D-9;
  - rate-limit, РЕВЬЮЕР PR #36 (неблокирующее): INCR и EXPIRE — две команды; при сбое между
    ними ключ остаётся без TTL (ключ поминутный — лимит не «залипает», только лишние байты
    в Redis). Фикс позже: MULTI/pipeline (INCR + EXPIRE) или Lua;
  - rate-limit, РЕВЬЮЕР PR #36 (неблокирующее): при недоступном Redis каждый запрос ждёт
    до ~0,4 с (connect + read по 0,2 с) в пуле потоков. Фикс позже: «предохранитель» —
    после ошибки N секунд не обращаться к Redis;
  - TTL 1 ч для `/refund`, `/erasure_*` (`init_data_sensitive_max_age_seconds` есть
    в config, но не применяется — таких маршрутов ещё нет);
  - анти-replay сверх TTL (одна initData может использоваться многократно в пределах
    24 ч) — зависит от решения по D-9;
  - R344 (сверка `user.id` vs `query_id`, security-audit) — не реализовано.
- **Ждём решения Автора:** нет по самой проверке; по TTL — см. D-9.

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
     **PR 1b+1c:** применён SEAM-1 — `docs/DEFECTS-ARCHIVE.md`, «D-9 (закрытые части, 04.10)».
  3. **503:** контракт не описывает ответ при неправильной конфигурации сервера
     (пустой `BOT_TOKEN`). Реализация отвечает 503 `SERVICE_MISCONFIGURED` в формате
     `schemas.Error` — в контракте такого ответа нет.
- **Сделано здесь (PR 1a):** — `docs/DEFECTS-ARCHIVE.md`, «D-9 (закрытые части, 04.10)».
- **Предлагаемое решение:** в DOCS-course-bot
  (а) выбрать одну модель авторизации: «initData на каждом запросе, TTL N» или
  «initData → session_jwt» (Б14) и привести к ней контракт, checklist и Б14;
  (б) пометить R327 как отменённый SEAM-PATCH-1 (или внести в OVERRIDES);
  (в) добавить в контракт `503` (`SERVICE_MISCONFIGURED`) в `components.responses` — **сделано:** DOCS PR #11 (`ServiceUnavailable`), sync PR #51.
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
- **Закрытые части записи** (API PR #38, Mini App PR #40, живые проверки 02.10) — `docs/DEFECTS-ARCHIVE.md`, «D-10 (закрытые части)».
- **Остаётся:** оплата до `pid` — до решения противоречия по оплате; отложенное по ревью #38 — D-15.
  Правка контракта сделана: DOCS PR #11 (first-launch: `consents`, 422, 503), sync PR #51.
- **Ждём решения Автора:** нет для API и экранов; по оплате — да.

- **D-11** (`lifecycle_phase` ≠ FSM И2) — целиком в `docs/DEFECTS-ARCHIVE.md` (правило А, 06.10).

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
- **Сделано здесь:** seed JSON по доменам, шаблон ключа схемы — текст в `docs/DEFECTS-ARCHIVE.md`.
- **Предлагаемое решение:** в DOCS-course-bot привести к схеме шаблон ключа в контракте,
  а в И4 — формат (JSON), путь и набор тонов.
- **Ждём решения Автора:** да — правка зеркала в DOCS-course-bot.

- **D-15** (ревью #38: отложенное) — целиком в `docs/DEFECTS-ARCHIVE.md` (правило А, 04.10).

- **D-16** (`participant_events` ≠ `state_transition_log`) — целиком в `docs/DEFECTS-ARCHIVE.md` (правило А, 06.10).

- **D-17** (`X-Client-Op-Id`) — целиком в `docs/DEFECTS-ARCHIVE.md` (правило А, 04.10).

- **D-18** (формат 422/500 → B-3b) — целиком в `docs/DEFECTS-ARCHIVE.md` (правило А, 04.10).

- **D-19** (хранилища на устройстве) — целиком в `docs/DEFECTS-ARCHIVE.md` (правило А, 04.10).

- **D-20** (CSP `font-src` без `data:`) — целиком в `docs/DEFECTS-ARCHIVE.md` (правило А, 06.10).

- **D-21** (`MINIAPP_URL` → `WEBAPP_URL`) — целиком в `docs/DEFECTS-ARCHIVE.md` (правило А, 06.10).

## D-22. Вернувшийся участник: GET /onboarding/status и повторное согласие

- **Файл архитектуры (зеркало):** `build/miniapp-api-contract.yaml` (first-launch; пути status нет).
- **Файлы реализации:** `apps/api/app/routers/onboarding.py`, `apps/api/app/consent_status.py` (PR #62);
  `apps/miniapp/src/components/App.tsx`, `startup.ts`, `drafts.ts` (PR #63).
- **Суть расхождения:** 1) в контракте нет способа узнать «кто я» без экранов 18+ и C1;
  2) «уже данные согласия повторно не записываются» — после отзыва или смены текста
  повторное согласие не записалось бы (круг); 3) что видит фаза sleeping — не определено.
- **Решение Автора (06.10, вариант А; returning: 1 Б, 2 Б, 3 да):**
  а) GET /miniapp/v1/onboarding/status → 200: {status: returning, short_no} / {status: reconsent,
     reasons} / {status: new}; «нет участника» и erased — одно тело; pid не отдаётся;
     401/429/503 как у /miniapp/v1/**; 403 нет;
  б) reasons — закрытый перечень: C0_missing, C0_revoked, C0_text_changed, C1_missing,
     C1_revoked, C1_text_changed;
  в) согласие действует = последнее событие по kind — give, и text_snapshot = текущий текст
     ключа (snapshot_of при записи и проверке); ver_of_text не критерий; participant_state не используется;
  г) first-launch пишет give по присланному kind, только если согласие не действует;
     revoke не трогает; participant_events — только при создании pid;
  д) sleeping — позже (задача, которая введёт /block);
  е) метка finished на устройстве убрана, «пускать ли» решает сервер — исполнено PR #63 (D-19).
- **Сделано:** PR #62 (живая 06.10: status без initData 401, у Автора returning);
  PR #63 (живая 08.10: номер сразу, без экранов; first-launch не вызывался).
- **Остаётся (ревью #62):** условие для первой задачи, которая пишет revoke: revoke берёт ту же
  блокировку строки участника (FOR UPDATE), порядок событий — по id (bigint), не по at
  (at = время начала транзакции: give может встать «после» более позднего revoke).
- **Правка DOCS сделана:** DOCS PR #13 (miniapp-api-contract.yaml: путь status, схема OnboardingStatus, reasons, повторный give в first-launch), sync PR #65.
- **Ждём решения Автора:** нет.

## D-23. Черновик на устройстве: зависание IndexedDB, гонка записи, текст ErrorBoundary

- **Файлы реализации:** `apps/miniapp/src/components/App.tsx`, `LaterSteps.tsx`, `drafts.ts`, `Root.tsx`.
- **Суть (ревью #63, неблокирующее; обхода согласий нет):**
  1) openDraft без таймаута: IndexedDB.open завис → «Продолжить» неактивна навсегда;
  2) saveDraft без очереди: put прошлого шага может завершиться после clear (finishDraft) →
     email и город снова на устройстве (до 24 ч), номер ведёт в анкету;
  3) Root.tsx (шаблон): ErrorBoundary показывает пользователю error.message.
- **Предлагаемое решение:** таймаут openDraft (→ курс); одна очередь записей черновика;
  ErrorBoundary — нейтральный текст без message. Задача без БД, вместе с мелочами Mini App.
- **Ждём решения Автора:** нет.

<!-- следующие записи: новые — с D-24 -->
