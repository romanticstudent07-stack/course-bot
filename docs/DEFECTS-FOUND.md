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
| B-3 | Роли и GRANT в БД: приложение ходит под владельцем БД; ролей/GRANT на `tg_user_registry` нет | D-13 | **закрыт** (PR #69–#71, #73, #74, #76, #77; сервер ✅ 14.10) — подробности: `docs/DEFECTS-ARCHIVE.md` |

Закрытые записи и закрытые части записей — `docs/DEFECTS-ARCHIVE.md`.

---

## D-1. Блок 15: доставка медиа (pre-signed URL vs внешний Telegram-канал)
- **Статус:** решено (Р-5, 17.10): медиа — только внешний Telegram-канал; pre-signed URL не делать.
- Правка канона (DIVISION.md) — в DOCS-course-bot.

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
- **Ждём решения Автора:** нет — провайдер Timeweb Cloud (Р-9, 18.10); правка build-order — в DOCS.

## D-6. Ограничения Telegram в РФ
- **Статус:** решено (Р-11, 19.10): данные в РФ + прокси к api.telegram.org; план Б — зарубежный бот-слой + уведомление РКН (позже).
- Правки канона (build-order 0-Б, 99-legal) — в DOCS-course-bot.

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

- **Статус:** частично решено (Р-12): TTL 24 ч до прода, session_jwt 60 мин — к проду.
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
- **Ждём решения Автора:** да — механизм продления `session_jwt` к проду (Р-12); правки зеркала — в DOCS-course-bot.

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

- **D-13** (роли и GRANT БД, блокер B-3) — целиком в `docs/DEFECTS-ARCHIVE.md` (правило А, 14.10).

## D-14. text_registry: шаблон ключа, формат seed и тоны — источники расходились
- **Файлы:** зеркало — `build/config-schemas/text_registry.schema.json`, `build/miniapp-api-contract.yaml`, `normative/I4-wave-d.md` §1; код — `apps/api/app/texts.py`, `apps/api/config/texts/*.json`.
- **Статус:** решено (Р-8 + «ОК А», 17–19.10): ключ B2…B16/legal, seed JSON, тоны soft/neutral/dry + strict; код не менять; правки — в каноне.

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

- **D-23** (черновик на устройстве: IndexedDB, гонка записи, ErrorBoundary) — целиком в `docs/DEFECTS-ARCHIVE.md` (правило А, 15.10).

- **D-24** (пароль владельца БД в контейнере api, env_file) — целиком в `docs/DEFECTS-ARCHIVE.md` (правило А, 14.10).

## D-25. Ключ замка дня: I2B 'life:' vs код 'participant:'
- **Файл архитектуры (зеркало):** I2B — ключ замка 'life:' || pid.
- **Файл реализации:** `apps/api/app/participant_lock.py` — 'participant:' || pid (В20, `docs/tasks/iter2-api-2a.md`).
- **Суть расхождения:** канон и код используют разные ключи advisory-замка.
- **Предлагаемое решение:** в коде один ключ 'participant:'; канон привести в DOCS-course-bot.
- **Ждём решения Автора:** нет.

## D-26. Контракт day/*: тела и «повтор = тот же 200» есть в коде, нет в каноне
- **Файл архитектуры (зеркало):** `build/miniapp-api-contract.yaml`.
- **Файл реализации:** `apps/api/app/routers/day.py` (#101, #103).
- **Суть расхождения:** тела запросов/ответов day/* и правило «повтор = тот же 200» есть в коде, в контракте их нет.
- **Предлагаемое решение:** PR в DOCS-course-bot (miniapp-api-contract).
- **Ждём решения Автора:** нет.

## D-27. Будущий tombstone/erasure обязан брать замок participant:pid

- **Файл архитектуры (зеркало):** правила tombstone/erasure (И1 tombstone_semantics; точный раздел — ШТАБ);
  ключ замка — В20 (docs/tasks/iter2-api-2a.md).
- **Файлы реализации:** `apps/api/app/participant_lock.py` (`active_pid_locked`: find → замок →
  повторная проверка tombstoned_at IS NULL); писатели под замком — `apps/api/app/routers/day.py`
  (test-enter, marks, report/submit); tombstone/erasure — пока не создан.
- **Суть расхождения:** Будущий tombstone/erasure обязан брать тот же замок
  pg_advisory_xact_lock(hashtext('participant:' || pid)); иначе tombstone между повторной проверкой
  и commit даст запись для удалённого pid. Источник: ревью PR #101.
- **Предлагаемое решение:** задача tombstone/erasure ставит tombstoned_at (и удаляет данные) в
  транзакции, которая сначала берёт этот замок (`lock_participant`), и приносит тест гонки
  «писатель дня + tombstone» (второй ждёт замок, записи для удалённого pid нет).
- **Ждём решения Автора:** нет.

## D-28. Квота пауз: П.8 «1 пауза на Этап» vs патч И2 «14 дн./год»
- **Файл архитектуры (зеркало):** `02-access-lives-pause.md` (П.8 — «1 пауза на Этап»; шапка, патч И2 — «14 дн./год»).
- **Файл реализации:** нет — паузы в коде не построены.
- **Статус:** решено (Р-6а, 17.10): канон — патч И2 (14 дн./год, одна ≤ 7 дн., между ≥ 24 ч).
- **Предлагаемое решение:** П.8 привести к патчу И2 в DOCS-course-bot.
- **Ждём решения Автора:** нет.

## D-29. life-ops-c Н1: WARNING day_clock о плохом поясе каждые 30 с
- **Файл архитектуры (зеркало):** решение #111 Н9.
- **Файл реализации:** day_clock / «часы» life_ops в projector.
- **Статус:** открыт. Источник: PR #113, 21.10.
- **Суть расхождения:** WARNING day_clock о плохом поясе повторяется каждые 30 с на каждого участника (решение #111 Н9).
- **Предлагаемое решение:** сделать «один раз» (на участника).
- **Ждём решения Автора:** нет.

## D-30. life-ops-c Н3: вечно пропускаемый участник занимает MAX_PER_TICK
- **Файл архитектуры (зеркало):** —
- **Файл реализации:** «часы» life_ops в projector.
- **Статус:** открыт. Источник: PR #113, 21.10.
- **Суть расхождения:** участник, которого вечно пропускают («state out of range»), занимает место в MAX_PER_TICK и пишет WARNING каждые 30 с.
- **Предлагаемое решение:** исключать такого участника из выборки тика и писать WARNING один раз.
- **Ждём решения Автора:** нет.

## D-31. Дни рефлексии (6, 13-M, 13-P): пропуск = −1 жизнь сразу
- **Файл архитектуры (зеркало):** `02-access-lives-pause.md` §2.3.
- **Файл реализации:** «часы» life_ops — не реализовано.
- **Статус:** открыт. Источник: PR #113, 21.10.
- **Суть расхождения:** по канону (02 §2.3) пропуск дня рефлексии = −1 жизнь сразу — не реализовано, контента этих дней нет.
- **Предлагаемое решение:** реализовать вместе с контентом дней рефлексии.
- **Ждём решения Автора:** нет.

## D-32. tombstone не видят «часы»; живое закрытие дня не проверено
- **Файл архитектуры (зеркало):** правила tombstone (см. D-27).
- **Файл реализации:** «часы» life_ops в projector.
- **Статус:** открыт. Источник: PR #113, 21.10.
- **Суть расхождения:** tombstone «часы» не видят — до прода; живое закрытие дня на сервере не проверено (нет позиций).
- **Предлагаемое решение:** tombstone — до прода; живое закрытие дня проверить после первого входа в день.
- **Ждём решения Автора:** нет.

<!-- следующие записи: новые — с D-33 -->
