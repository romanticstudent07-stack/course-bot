# miniapp-pause-b1 — хранилище очереди пауз (pauseQueueStore)

## 1. Паспорт
- id: miniapp-pause-b1 · PR: feat(miniapp): pause queue store (T5-B1) · ветка: feat/miniapp-pause-b1 [ШТАБ-тех]
- Режим: Р0+ (КОДЕР) · зависит от: нет · следующая: miniapp-pause-b2
- Основание: docs/research/t5-bc.md §2, §3 B; деление B на B1/B2 — решение ШТАБа (К-5, SHTAB.md 3-Б).

## 2. Цель
Отдельная IndexedDB для очереди POST пауз: один слот на владельца, флаг wipePending и полная очистка
wipeAll (deleteDatabase БД очереди и БД course-bot). Ни UI, ни сети: в main ничего не вызывает.

## 3. Решения Автора (по R-2026-11-21 через t5-bc §6; ШТАБ сверяет с R-2026-11-21.md до промпта)
- Очистка — только при доказанной коллизии (409 IDEMPOTENCY_CONFLICT); бизнес-409 черновики не трогают.
- Состав слота: kind, неизменные аргументы, opId, привязка владельца, расписание; без токенов, initData, ответов и снимка.
- Аудит client_op_id_conflict пишет только сервер (security_events); клиент ничего не логирует (R-2026-11-21, 22.11).
- Очистка при следующем открытии — не гарантия 24 ч; on_webapp_close 24 ч не отменено.

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
| Одна запись на владельца, без размера, порядка и срока | [ШТАБ-тех] (канон молчит, К-5) |
| Отдельная БД course-bot-pause-queue v1, хранилище slots | [ШТАБ-тех] (не трогать DB_VERSION черновиков) |
| wipeAll = deleteDatabase обеих БД; onblocked → sendClosed | [ШТАБ-тех] |
| Нет indexedDB → хранилище в памяти, как в drafts.ts | [ШТАБ-тех] |
Правок канона нет.

## 5. ЧТО ПРОЧИТАТЬ (бюджет исполнителя)
- эта карточка ≈ 7 КБ
- apps/miniapp/src/components/drafts.ts — 21,5 КБ (образец IDB, шапка)
- apps/miniapp/src/components/OnboardingFlow.test.ts — 18,3 КБ (списки)
- Чтение исполнителя ≈ 47 КБ.

## 6. Файлы
- создать: apps/miniapp/src/components/pauseQueueStore.ts
- создать: apps/miniapp/src/components/pauseQueueStore.test.ts
- изменить: apps/miniapp/src/components/drafts.ts — только шапка
- изменить: apps/miniapp/src/components/OnboardingFlow.test.ts — списки (раздел 9)

## 7. Контракт модуля [ШТАБ-тех]
Типы (экспорт):
- PauseOpKind = 'request' | 'cancel' | 'resume'
- PauseOpArgs = { days: number; start_date: string } | { pause_id: number }
- PauseSlot = { ownerId: string; kind; args; opId: string; phase: 'queued' | 'uncertain' | 'stopped'; attempt: number; notBefore: number }
- PauseQueueStore = { read(ownerId): Promise<PauseSlot | null>; write(slot): Promise<void>; clear(ownerId): Promise<void>;
  setWipePending(): Promise<void>; isWipePending(): Promise<boolean>; wipeAll(): Promise<'done' | 'blocked'>; sendClosed(): boolean }
Фабрика: createPauseQueueStore(idb?: IDBFactory | null). По умолчанию globalThis.indexedDB; null или нет → в памяти.
Правила:
- Ключ записи — 'slot:' + ownerId; флаг — ключ 'wipe-pending' в той же БД.
- read с битой записью (нет полей, неверный kind) → clear и null.
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
- clear удаляет только свой слот.
- setWipePending → isWipePending true, переживает новый экземпляр на том же фейке.
- wipeAll вызывает deleteDatabase для обеих БД → 'done'.
- onblocked у course-bot → 'blocked', sendClosed() true, флаг остался.
- idb = null → память, те же операции работают.
Задетые тесты (правило «Т»):
- OnboardingFlow.test.ts: './pauseQueueStore.ts' — во второй it.each (R342: innerhtml, insertadjacenthtml, document.write) рядом с './drafts.ts'.
- OnboardingFlow.test.ts: новый it «pauseQueueStore.ts: нет initData, токенов и console» с подстроками раздела 7.
- В NO_STORAGE_FILES pauseQueueStore.ts НЕ добавлять (он пишет в IDB). './pauseQueue.ts' добавляет B2.
- drafts.test.ts, drafts.support.test.ts — правок не ожидается (проверено ШТАБом по d7163a0).
Цели tools/check.sh — miniapp-цели по AGENT-BRIEF.md; CI — то же.

## 10. Живые проверки
Нет: модуль ни к чему не подключён; выкат позже (PLAN §4).

## 11. Запреты
- AGENT-BRIEF.md §3; новые зависимости (fake-indexeddb и др.) — нельзя.
- Не менять DB_VERSION, имя БД и логику drafts.ts; в шапке нет слов birth, city, gender, weight, wellbeing, email.
- Не подключать к App.tsx и client.ts; не писать checkDayAccess и DayGuard.
- Тексты — заглушки; реальных ID нет; аккаунты — А1–А4.

## 12. Критерии готовности
Тесты раздела 9 зелёные; шапка drafts.ts без «ЕДИНСТВЕННЫЙ файл…» и со ссылкой на pauseQueueStore.ts; diff только 4 файла.

## 13. Оценка
Код 150–200 строк, тесты 150–220, правки 12–24. Часы Автора ≈ 0,5; кредиты 0 (КОДЕР).
Исполнитель: КОДЕР, Claude Opus 5.5 — причина: один новый модуль по образцу drafts.ts, чтение < 50 КБ, без прогона CI-итераций.

## 14. РЕВЬЮЕР
Нет: initData, 18+, согласий, rate-limit, ролей и оплаты не трогает.
