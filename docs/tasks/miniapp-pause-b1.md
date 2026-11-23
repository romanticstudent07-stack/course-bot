# miniapp-pause-b1 — хранилище очереди пауз (pauseQueueStore)

## 1. Паспорт
- id: miniapp-pause-b1 · PR: feat(miniapp): pause queue store (T5-B1) · ветка: feat/miniapp-pause-b1 [ШТАБ-тех]
- Режим: Р0+ (КОДЕР) · зависит от: нет · следующая: miniapp-pause-b2
- Основание: docs/research/t5-bc.md §2, §3 B; деление B на B1/B2 — решение ШТАБа (К-5, SHTAB.md 3-Б).

## 2. Цель
Отдельная IndexedDB для очереди POST пауз: один слот на владельца, флаг wipePending и полная очистка
wipeAll (deleteDatabase БД очереди и БД course-bot). Ни UI, ни сети: в main ничего не вызывает.

## 3. Решения Автора (docs/decisions/R-2026-11-21.md, сверено ШТАБом по d7163a0)
- Очистка — только при доказанной коллизии (409 IDEMPOTENCY_CONFLICT); бизнес-409 черновики не трогают.
- Состав слота: kind, неизменные аргументы, opId, привязка владельца, расписание; без токенов, initData, ответов и снимка.
- Аудит client_op_id_conflict пишет только сервер, таблица security_events [Автор → R-2026-11-21 «Носитель события client_op_id_conflict»]; клиент коллизию не логирует [ШТАБ-тех; AGENT-BRIEF §3].
- Очистка при следующем открытии — не гарантия 24 ч; on_webapp_close 24 ч не отменено.
- «Метаданные не называть анонимными.»
- «Удаление при завершении операции и полную очистку при смене пользователя включить в обязательные проверки.» (завершение — тест clear в B1; смена владельца — тест в B2)

## 4. Канон и решения (К-6)
Выдержки (И4 I4-wave-d.md, по d7163a0, проверено ШТАБом):
- 593–596 write_queue: persistence: IndexedDB (survives page reload); retry_policy: exponential backoff, per client_op_id; idempotency: client_op_id from И2 idempotency_keys. Размер, порядок и срок очереди канон не задаёт.
- 599–603 conflict_ux.on_server_409: show_error "локальные данные повреждены; переоткройте Mini App"; action: full IndexedDB wipe on next open; log: security_audit event client_op_id_conflict.
- 607–613 R380_cleanup: on_tg_user_id_change: full wipe immediately; on_webapp_close: wipe sensitive fields within 24h TTL guarantee.
- AD-01, AD-02 — в шапке И4 (строки 34, 36), уже канон.

| Решение | Метка |
|---|---|
| Очередь в IndexedDB, переживает перезагрузку | [канон И4 R339 write_queue] |
| Полная очистка IDB при следующем открытии после коллизии | [канон И4 R339 conflict_ux; AD-01] |
| Полная очистка сразу при смене владельца (вызов — в B2) | [канон И4 R380 on_tg_user_id_change] |
| Только коллизия, не любой 409; клиент не логирует | [Автор, канон проверен И4 R339 → R-2026-11-21] |
| Состав слота без токенов и initData | [Автор, канон проверен И4 R339, R380 → R-2026-11-21] |
| Одна запись на владельца, без размера и порядка | [ШТАБ-тех] |
| Слот живёт не дольше 24 ч — read удаляет старый | [ШТАБ-тех; И4 R380; R-2026-11-21] |
| Отдельная БД course-bot-pause-queue v1, хранилище slots | [ШТАБ-тех] (не трогать DB_VERSION черновиков) |
| wipeAll = deleteDatabase обеих БД; onblocked → sendClosed | [ШТАБ-тех] |
| Нет indexedDB → хранилище в памяти, как в drafts.ts | [ШТАБ-тех] |
Правок канона нет.

## 5. ЧТО ПРОЧИТАТЬ (бюджет исполнителя)
- эта карточка ≈ 8 КБ
- apps/miniapp/src/components/drafts.ts — 21,5 КБ (образец IDB: DB 'course-bot' v1, store 'drafts', db.close после каждой транзакции; шапка)
- apps/miniapp/src/components/OnboardingFlow.test.ts — 18,3 КБ (NO_STORAGE_FILES, BANNED_STORAGE, BANNED_HTML, функция source)
- Чтение исполнителя ≈ 48 КБ. Оба файла КОДЕР читает целиком.

## 6. Файлы и способ правки
Урок 22.11-б: файл длиннее 350 строк КОДЕРУ целиком не выдавать (drafts.ts ≈ 480 строк, OnboardingFlow.test.ts ≈ 470).
- создать (пакетом КОДЕРА): apps/miniapp/src/components/pauseQueueStore.ts
- создать (пакетом КОДЕРА): apps/miniapp/src/components/pauseQueueStore.test.ts
- изменить (текстом «найти → заменить», вносит Автор в редакторе Codespaces, шаги даёт ШТАБ):
  а) apps/miniapp/src/components/drafts.ts — найти строку:
       // Это ЕДИНСТВЕННЫЙ файл Mini App, который пишет на устройство.
     заменить на:
       // На устройство пишут два файла Mini App: этот и pauseQueueStore.ts (очередь пауз, своя БД).
  б) apps/miniapp/src/components/OnboardingFlow.test.ts — найти строку:
       it.each([...NO_STORAGE_FILES, './drafts.ts'])('%s: нет innerHTML и аналогов (R342)', (path) => {
     заменить на:
       it.each([...NO_STORAGE_FILES, './drafts.ts', './pauseQueueStore.ts'])('%s: нет innerHTML и аналогов (R342)', (path) => {
  в) apps/miniapp/src/components/OnboardingFlow.test.ts — блоком «дописать в конец»: новый describe
     с it «pauseQueueStore.ts: нет initData, токенов и console» по подстрокам §7 (через функцию source из этого же файла).

## 7. Контракт модуля [ШТАБ-тех]
Типы (экспорт):
- PauseOpKind = 'request' | 'cancel' | 'resume'
- PauseOpArgs = { days: number; start_date: string } | { pause_id: number }
- PauseSlot = { ownerId: string; kind; args; opId: string; phase: 'queued' | 'uncertain' | 'stopped'; attempt: number; notBefore: number; savedAt: number }
  savedAt — мс, время первой записи; ставит enqueue в B2, повторы не меняют.
- PauseQueueStore = { read(ownerId, now): Promise<PauseSlot | null>; write(slot): Promise<void>; clear(ownerId): Promise<void>;
  setWipePending(): Promise<void>; isWipePending(): Promise<boolean>; wipeAll(): Promise<'done' | 'blocked'>; sendClosed(): boolean }
Фабрика: createPauseQueueStore(idb?: IDBFactory | null). По умолчанию globalThis.indexedDB; null или нет → в памяти.
Правила:
- Ключ записи — 'slot:' + ownerId; флаг — ключ 'wipe-pending' в той же БД.
- read с битой записью (нет полей, неверный kind) → clear и null.
- read: now − savedAt > 24 ч или savedAt > now + 60 с → clear и null.
- wipeAll: deleteDatabase('course-bot-pause-queue') и deleteDatabase('course-bot'). Обе success → 'done'.
  onblocked или error у любой → 'blocked', sendClosed() = true до перезагрузки; флаг не снимать.
- Ошибки IDB глотаются, без логов (в файле нет console.).
- В файле нет подстрок: initdata, init_data, token, console., localstorage, sessionstorage, document.cookie, dexie, birth, short_no.

## 8. БД
Серверной БД нет. Клиентская IDB — раздел 7.

## 9. Тесты
pauseQueueStore.test.ts — свой минимальный фейк IDBFactory, без библиотек:
- write → read тем же ownerId возвращает слот; чужой ownerId → null.
- битая запись → null и запись удалена.
- слот старше 24 ч → null и запись удалена.
- clear удаляет только свой слот (удаление при завершении операции — R-2026-11-21).
- setWipePending → isWipePending true, переживает новый экземпляр на том же фейке.
- wipeAll вызывает deleteDatabase для обеих БД → 'done'.
- onblocked у course-bot → 'blocked', sendClosed() true, флаг остался.
- idb = null → память, те же операции работают.
Задетые тесты (правило «Т»):
- OnboardingFlow.test.ts: правки §6 б) и в).
- В NO_STORAGE_FILES pauseQueueStore.ts НЕ добавлять (он пишет в IDB). './pauseQueue.ts' добавляет B2.
- drafts.test.ts, drafts.support.test.ts — правок не ожидается (проверено ШТАБом по d7163a0).
bash tools/check.sh miniapp; CI — то же.

## 10. Живые проверки
Нет: модуль ни к чему не подключён; выкат позже (PLAN §4).

## 11. Запреты
- AGENT-BRIEF.md §3; новые зависимости (fake-indexeddb и др.) — нельзя.
- Не менять DB_VERSION, имя БД и логику drafts.ts; в шапке нет слов birth, city, gender, weight, wellbeing, email.
- Не подключать к App.tsx и client.ts; не писать checkDayAccess и DayGuard.
- В коде и комментариях нет слова «анонимн» (R-2026-11-21).
- Тексты — заглушки; реальных ID нет; аккаунты — А1–А4.

## 12. Критерии готовности
Тесты раздела 9 зелёные; шапка drafts.ts без «ЕДИНСТВЕННЫЙ файл…» и со ссылкой на pauseQueueStore.ts; diff только 4 файла.

## 13. Оценка
Код 150–210 строк, тесты 160–230, правки 12–24. Часы Автора ≈ 0,5 (плюс ручные правки §6 а–в); кредиты 0 (КОДЕР).
Исполнитель: КОДЕР, Claude Opus 5.5 — причина: один новый модуль по образцу drafts.ts, чтение < 50 КБ, без CI-итераций.
КОДЕР выдаёт пакетом только 2 новых файла; правки drafts.ts и OnboardingFlow.test.ts — текстом «найти → заменить» и «дописать в конец».

## 14. РЕВЬЮЕР
Нет: initData, 18+, согласий, rate-limit, ролей и оплаты не трогает.
