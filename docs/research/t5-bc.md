# t5-bc — исследование: очередь POST пауз в IndexedDB (B) и экран /paused (C)

M: 995cb6291aaf0eb10d33b4f460016220a3f61fc4 (995cb62). Область — apps/miniapp. Основание — docs/research/miniapp-pause-canon.md (З3) и docs/decisions/R-2026-11-21.md. Решённое не пересматривается. #267 (fd9119f) — только справка, по hash не открывался.
Правило К — docs/process/CANON-CHECK.md. Метки К-6 — в разделе 6.

## 1. Инвентаризация apps/miniapp@995cb62

| Что | Где | Факт |
|---|---|---|
| indexedDB | components/drafts.ts | Единственный файл, который пишет на устройство (так сказано в шапке). БД course-bot, DB_VERSION 1, хранилище drafts, ключи onboarding и support. createDraftStore и createSupportDraftStore: если indexedDB нет — хранилище в памяти. |
| deleteDatabase | нет | В прочитанных файлах нет ни одного вызова. Полной очистки всех IDB приложения в main нет. |
| Очистка черновиков | drafts.ts | store.clear() удаляет только свой ключ. Где вызывается: readDraft при другом или неизвестном tgUserId, старой записи, finished или битой записи; finishDraft (seal, затем clear); saveDraft со step finished; readSupportDraft — при отказе parseStoredSupportDraft; clearSupportDraft — после 201. Ошибки хранилища глотаются, в лог ничего не пишется. |
| Очередь операций хранилища | drafts.ts createOpQueue | Очередь внутри вкладки с таймаутом 3 с. Между вкладками не работает, Web Locks и BroadcastChannel нет. |
| Привязка к владельцу | api/client.ts tgUserIdFromInitData, readTgUserId | user.id берётся из сырой initData — только для локальной привязки. App.tsx читает tgUserId один раз, через useState. |
| NO_STORAGE_FILES | components/OnboardingFlow.test.ts, раздел «Хранилища и утечки (D-19)» | 12 файлов, в том числе ./App.tsx и ../api/client.ts. По каждому — проверка подстроки в исходнике в нижнем регистре, комментарии тоже считаются. Запрещены: localstorage, sessionstorage, indexeddb, dexie, document.cookie, console., sendbeacon, pushstate, replacestate, location.hash, persist(. Вторая проверка: NO_STORAGE_FILES и ./drafts.ts — нет innerhtml, insertadjacenthtml, document.write. Третья: в drafts.ts нет birth, console., email, city, gender, weight, wellbeing и других. |
| checkDayAccess, DayGuard | не найдены в прочитанных файлах | В client.ts, App.tsx, drafts.ts их нет. Есть ли они в main и в каком файле — не проверено (см. «Надо дочитать»). |
| Импорты API пауз | нет | В client.ts нет функций и типов /pause*. App.tsx пауз не импортирует. Маршрутов фазы app нет в App.tsx — они в navigation/routes.tsx, файл не читал. pause.ts и PausedPage в main нет — по STATE@995cb62 и старту. |
| ApiError | client.ts | Поля: status, code, message, retryAfter. Поле details тела ошибки отбрасывается — reason start_date_passed клиенту сейчас не виден. |
| apiRequest | client.ts | Нет AbortSignal. Сетевая ошибка — исключение от fetch. Ответ не ok — ApiError(code из тела или HTTP_ERROR). Retry-After читается только при 429, только целое больше 0. |
| newClientOpId | client.ts | UUID v4 — сервер требует UUID4 (иначе 422). |

Сервер (по коду apps/api/app/routers/pause.py@995cb62, контракт build/miniapp-api-contract.yaml@995cb62 «Паузы»):
- POST /pause/request: тело {days 1..7, start_date YYYY-MM-DD}, X-Client-Op-Id UUID4 → 201 {pause: {id, status, start_at, planned_end_at}}, время в UTC.
- POST /pause/cancel и /pause/resume: тело {pause_id ≥ 1}, X-Client-Op-Id UUID4 → 202 {status: accepted}.
- Повтор с тем же op и теми же параметрами → прежний 201 или 202. Тот же op с другими параметрами → 409 IDEMPOTENCY_CONFLICT; аудит пишет сервер (security_events).
- Бизнес-отказы 409 без аудита: PAUSE_ALREADY_OPEN; PAUSE_REFUSED с details.reason, в том числе start_date_passed; PAUSE_NOT_CANCELLABLE; PAUSE_NOT_ACTIVE.
- Прочие ответы: 404 PARTICIPANT_NOT_FOUND, 422 VALIDATION_ERROR, 429 RATE_LIMITED с Retry-After, 503.
- Ключи request и cancel/resume разных видов: на каждую операцию клиент даёт новый UUID.
- Формат ошибки — errors.py: {code, message, details?} как есть.
- GET /pause: {budget_days_left, budget_days_total, cycle_ends_at, pause, can_request, refusal}. Даты старта в ответе нет.

Блокер Б1 (для ШТАБа, К-5). Откуда клиенту взять start_date? GET /pause даты старта не отдаёт. Сервер считает её как местную дату next_midnight(now, participant_state.tz).
- Вариант а: дата устройства + 1. Плохо: пояс устройства может отличаться от пояса участника.
- Вариант б: tz из GET /me/card и Intl. Что ошибка безопасна, не доказано: me.py не читал, а при неверной дате придёт start_date_passed и новое подтверждение.
- Вариант в: поле start_date в GET /pause. Это правка API (другая область) и цикл DOCS.
- Рекомендация: в — источник даты один и серверный. Без решения ШТАБа карточку C не писать.

## 2. Раскладка по файлам

B — очередь, без UI и без сети (отправитель передаётся снаружи):

| Файл | Действие | Строк |
|---|---|---|
| apps/miniapp/src/components/pauseQueueStore.ts | создать: IDB в отдельной БД (имя не course-bot, чтобы не трогать DB_VERSION черновиков); слот на владельца; wipeAll — deleteDatabase БД очереди и БД course-bot; при onblocked — отправка закрыта | 150–200 |
| apps/miniapp/src/components/pauseQueue.ts | создать: фазы queued и uncertain, backoff по op-id, Retry-After, гейт владельца, межвкладочный lock, разбор исхода (раздел 5) | 220–300 |
| apps/miniapp/src/components/pauseQueue.test.ts | создать: fake store и fake lock без библиотек | 280–380 |
| apps/miniapp/src/components/OnboardingFlow.test.ts | изменить списки (раздел 3) | 10–20 |
| apps/miniapp/src/components/drafts.ts | только шапка: убрать «ЕДИНСТВЕННЫЙ файл…», дать ссылку на pauseQueueStore.ts | 2–4 |

Чтение КОДЕРА или Агента по B: карточка (около 12) + drafts.ts 21,5 + client.ts 18,3 + OnboardingFlow.test.ts 18,3 ≈ 70 КБ. Код 380–500 строк, тесты 280–380. Это на верхней границе 600 строк: делить ли на B1 (store и wipe) и B2 (worker), решает ШТАБ.

C — клиент /pause/* и экран:

| Файл | Действие | Строк |
|---|---|---|
| apps/miniapp/src/api/client.ts | изменить: типы PauseOut и PauseStatus, getPause и три POST; ApiError.details (необязательный 5-й аргумент); RequestOptions.signal | 60–90 |
| apps/miniapp/src/api/client.test.ts | изменить: details и signal через заглушку fetch | 40–70 |
| apps/miniapp/src/components/pause.ts | создать: координатор чтений (readSeq), серия старта, привязка к pauseQueue | 200–280 |
| apps/miniapp/src/components/pause.test.ts | создать: регрессии 2 и 3 | 300–400 |
| apps/miniapp/src/pages/PausedPage/PausedPage.tsx | создать: экран /paused, тексты-заглушки | 150–220 |
| apps/miniapp/src/navigation/routes.tsx | изменить: маршрут /paused (файл не читал) | 3–10 |
| apps/miniapp/src/components/App.tsx | изменить: запуск и остановка worker в фазе app, гейт владельца | 20–40 |
| файл checkDayAccess и DayGuard | регрессия 4 (файл не найден) | 20–60 |
| apps/miniapp/src/components/OnboardingFlow.test.ts | изменить списки | 5–10 |

Чтение по C: карточка 12 + client.ts 18,3 + App.tsx 11,6 + OnboardingFlow.test.ts 18,3 + pauseQueue.ts из B (около 10) + routes.tsx и файл DayGuard (не измерены) ≈ 75 КБ и больше. Строк 800–1100 — больше 600. Предлагаю два куска:
- C1: client, pause.ts и тесты;
- C2: PausedPage, routes, App, DayGuard.
Решает ШТАБ.

## 3. Задетые тесты (правило «Т»)

B:
- OnboardingFlow.test.ts: в NO_STORAGE_FILES добавить './pauseQueue.ts'. Логика не знает про IDB, хранилище передаётся снаружи; в файле не должно быть подстрок indexeddb, console., persist(.
- OnboardingFlow.test.ts: './pauseQueueStore.ts' добавить в проверку R342 — innerHTML и аналоги (второй it.each, рядом с './drafts.ts').
- OnboardingFlow.test.ts: новый it «pauseQueueStore.ts: нет initData, токенов и console». Запрещённые подстроки: initdata, init_data, token, console., localstorage, sessionstorage, document.cookie, dexie, birth, short_no. Так проверяется R-2026-11-21 «Сохраняемые данные очереди».
- drafts.ts меняется только в комментарии шапки. Запрещённые подстроки третьей проверки (birth, city, gender, weight, wellbeing, email) в новый текст не вносить. drafts.test.ts и drafts.support.test.ts: правок не ожидается; эти файлы не читал — проверить ШТАБу.

C:
- OnboardingFlow.test.ts: в NO_STORAGE_FILES добавить './pause.ts' и '../pages/PausedPage/PausedPage.tsx'.
- client.ts и App.tsx уже в NO_STORAGE_FILES: в новом коде и комментариях нет слова IndexedDB (в любом регистре), нет persist(, pushState, location.hash. В App.tsx — только вызов фабрики из pauseQueueStore.ts.
- OnboardingFlow.test.ts вызывает ApiError с 3 аргументами: details — необязательный 5-й аргумент, правка теста не нужна.
- client.test.ts: существующие тесты (buildUrl, normalizeBaseUrl) не ломаются, только добавления.
- Тесты navigation/* и тесты DayGuard: не найдены — список дополнить после «Надо дочитать».

## 4. Четыре регрессии #267

| № | Суть (miniapp-pause-canon) | Куда |
|---|---|---|
| 1 | сеть → 429 → Retry-After → те же days и UUID, и после пересоздания worker | B: pauseQueue.test.ts (пересоздать worker на том же store). В C — только проброс ApiError.retryAfter (уже есть). |
| 2 | start_at ≤ now: одна серия на (pause.id, start_at); прошлое, равенство, задержка, 1+5 GET через 2 с, очистка | C1: pause.ts, pause.test.ts |
| 3 | readSeq: один координатор чтений; финал очищает только свою серию; отложенные resume, ETA, cancel и start в обоих порядках | C1: pause.ts, pause.test.ts |
| 4 | checkDayAccess хранит Retry-After; DayGuard и кнопка ошибки /paused реально disabled до срока, потом один ручной GET; день не открывается из ошибки, active или таймера | C2: файл checkDayAccess и DayGuard (найти), PausedPage.tsx |

## 5. Порядок включения и старые вызовы

Старых вызовов POST /pause* в main нет: pause.ts и PausedPage откачены #271, в client.ts функций нет. Fallback отключать не нужно — его надо запретить с самого начала:
- три POST экспортируются из client.ts, но вызывает их только отправитель в pauseQueue;
- тест в pause.test.ts по исходнику: в pause.ts и PausedPage.tsx нет postPauseRequest, postPauseCancel, postPauseResume.

Порядок:
1. B — store и worker без подключения: в main ничего не шлёт.
2. C1 — клиент и координатор.
3. C2 — экран и запуск worker в App (фаза app).

Разбор исхода в worker (miniapp-pause-canon «Запись и восстановление», решения R-2026-11-21):
- 201 или 202 — закрыть слот, затем GET.
- 409 IDEMPOTENCY_CONFLICT — доказанная коллизия: флаг wipePending, отправка закрыта, текст R339; полная очистка при следующем открытии.
- 409 с бизнес-кодом — закрыть слот, сообщение и GET; черновики не трогать. Для PAUSE_REFUSED с reason start_date_passed — новое подтверждение и новый UUID.
- Другой 409 — остановка, коллизией не считать.
- 429 — тот же op, срок по Retry-After.
- 401 и 403 — ждать авторизации того же владельца.
- 404 и 422 — остановка без автоповтора.
- Сеть, таймаут, 5xx — uncertain и backoff.

Выкат: сервер на 6695d0c не знает нового контракта. Mini App с C2 выкатывать только после api с #284, #286, #293 (SHTAB-DEBTS §1 п.6). До этого C2 не выкатывать.

## 6. Канон и решения (метки К-6)

| Решение | Метка |
|---|---|
| Очередь в IndexedDB переживает перезагрузку; exponential backoff по client_op_id; повтор тем же op | [канон И4 R339 write_queue; И2 idempotency_keys] |
| Очистка и аудит — только при доказанной коллизии (IDEMPOTENCY_CONFLICT); бизнес-409 без удаления черновиков | [Автор, канон проверен И2, И4 R339 conflict_ux → R-2026-11-21; OVERRIDES AD-01] |
| Аудит client_op_id_conflict пишет только сервер (security_events), клиент не логирует | [Автор, канон молчит → R-2026-11-21 от 22.11] |
| Состав слота: kind, неизменные аргументы, opId, привязка владельца, расписание; без токенов, initData, ответов и снимка | [Автор, канон проверен И4 R339, R380 → R-2026-11-21] |
| Смена tg_user_id — полная очистка сразу | [канон И4 R380 on_tg_user_id_change] |
| on_webapp_close 24 ч не отменено; очистка при следующем открытии — не гарантия 24 ч | [канон И4 R380; Автор → R-2026-11-21] |
| start_date в теле request; дата не сдвигается; start_date_passed — новое подтверждение | [Автор, канон противоречит коду → R-2026-11-21 от 22.11] |
| Текст при коллизии — дословно из R339 show_error | [канон И4 R339 conflict_ux] |
| Backoff 2 с × 2^n, потолок 60 с; Web Locks; отдельная БД очереди; wipe через deleteDatabase | [ШТАБ-тех] (К-5, проект miniapp-pause-canon) |
| Источник start_date (Б1) | [ШТАБ-тех], ждёт решения |

Правки канона для B и C: новых нет — /pause/* и AD-01, AD-03, AD-04 уже внесены (DOCS #25–#27, sync #290, #291, #294). Если по Б1 выбран вариант в — правка контракта GET /pause в цикле DOCS до карточки C.

## Надо дочитать (решает ШТАБ)

- Файл с checkDayAccess и DayGuard, navigation/routes.tsx и их тесты — для регрессии 4 и раздела 3 C. Пути нужны от Автора: Git Bash git grep -n "checkDayAccess\|DayGuard" -- apps/miniapp.
- drafts.test.ts, drafts.support.test.ts — подтвердить «не ожидается» для B.
- apps/api/app/routers/me.py — только если по Б1 выбран вариант б.
- Надо от Автора: Git Bash git grep -n по R339_indexeddb_cache в I4. Причина: в цитатах есть persistence, retry_policy, idempotency и conflict_ux; есть ли у write_queue ограничения размера, порядка или срока — не проверено.

## Вопросы Автору (К-4)

Нет. Б1 — технический выбор, К-5, вопрос ШТАБу.

## Прочитано (995cb62)

| Путь | КБ | Главный факт |
|---|---|---|
| docs/process/PACK.md | 12,4 | метка конца есть |
| docs/process/DESIGNER.md | 21,5 | ИССЛЕДОВАНИЕ: файл до 15 КБ, правило «Т» |
| docs/decisions/DECISIONS.md | 7,6 | паузы 21.11 — R-2026-11-21 |
| docs/process/CANON-CHECK.md | 4,7 | К-4, К-6 |
| docs/decisions/R-2026-11-21.md | 6,9 | 409 только при коллизии; состав слота; start_date |
| docs/research/miniapp-pause-canon.md | 23,0 | проект записи; 4 регрессии; раскладка A, B, C |
| docs/STATE.md | 16,9 | T5-A закрыт; 0022 не выкачена |
| AGENT-BRIEF.md | 16,7 | запреты; новые зависимости — только с согласия |
| apps/miniapp/src/api/client.ts | 18,3 | нет /pause*; ApiError без details |
| apps/miniapp/src/components/drafts.ts | 21,5 | единственный IDB; deleteDatabase нет |
| apps/miniapp/src/components/App.tsx | 11,6 | фазы; маршруты app — в routes.tsx |
| apps/miniapp/src/components/OnboardingFlow.test.ts | 18,3 | NO_STORAGE_FILES, 12 файлов, запрет indexeddb |
| apps/miniapp/src/api/client.test.ts | 0,9 | только buildUrl и normalizeBaseUrl (по необходимости — Задетые тесты) |
| apps/api/app/routers/pause.py | 30,9 | точные тела и коды (по необходимости — К-2 п.5) |
| build/miniapp-api-contract.yaml, раздел «Паузы» | 37,5 | /pause/* как в коде; даты старта в GET нет (по необходимости) |
| apps/api/app/errors.py | 3,2 | формат ошибки {code, message, details} (сверх списка: ApiError.details) |
