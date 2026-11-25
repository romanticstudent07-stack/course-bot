# miniapp-pause-c2 — очередь пауз: гейт владельца и запись перед отправкой (правка B1 и B2)

## 1. Паспорт
- id: miniapp-pause-c2 · пачка T5-C · порядок Агента: c1 → c2 → c3.
- Заголовок PR: fix(miniapp): гейт владельца и запись до отправки в очереди пауз (miniapp-pause-c2)
- Ветка: feat/miniapp-pause-c2 · Режим: Р1 · Зависит от: miniapp-pause-c1 (начинать после его мержа).
- Отличие от раскладки t5-bc §5: экран /paused, DayGuard, маршрут и запуск воркера в App перенесены в miniapp-pause-c3 (решение ШТАБа З2).

## 2. Цель
- Сейчас смену владельца в очереди не видно. pauseQueueStore.read(ownerId) читает ключ 'slot:' + ownerId, поэтому владелец B слот A не видит.
  Проверка slot.ownerId в pauseQueue никогда не срабатывает с настоящим хранилищем: тест #299 зелёный только на фейке.
- Дать хранилищу память о владельце и общий гейт pauseStartupGate.
- Отправлять только после записи, которая прошла успешно.

## 3. Решения Автора и ШТАБа
- R-2026-11-21, «Область конфликтного 409»: «Очистка и аудит безопасности — только при доказанной коллизии op-id.»
- R-2026-11-21 (по шапке pauseQueueStore.ts): в слоте только kind, неизменные аргументы, opId, владелец и расписание.
- Ответы ШТАБа З2:
  - claimOwner возвращает 'same', 'changed' или 'unavailable'; ключ 'owner';
  - порядок: wipePending → claimOwner → wipeAll → claimOwner; 'blocked' закрывает отправку;
  - тест — на настоящем хранилище в памяти. [канон И4 R380] + [ШТАБ-тех] за форму.
- write возвращает boolean, B2 отправляет только после true [канон: miniapp-pause-canon «Запись и восстановление» п.2] + [ШТАБ-тех].
- Таймаут гейта 3 с, как createOpQueue в drafts.ts [ШТАБ-тех, К-5].

## 4. Выдержки канона (по docs/research/miniapp-pause-canon.md и t5-bc)
- И4 docs/architecture/normative/I4-wave-d.md, R380: «on_tg_user_id_change: full wipe immediately»; слот битый, старше 24 ч или из будущего дальше 60 с — удалить при чтении.
- И4 R339: «persistence: IndexedDB (survives page reload)»; conflict_ux.on_server_409: «full IndexedDB wipe on next open».
- miniapp-pause-canon, «Запись и восстановление», п.2: ошибка IDB до commit — ноль POST. Поле tgOwnerTag: проверять и при пустом слоте.

## Канон и решения
(а) Используется: И4 R380, И4 R339. (б) Противоречий с DECISIONS.md нет.
(в) Правок канона нет.

## 5. ЧТО ПРОЧИТАТЬ
- AGENT-BRIEF.md — 16,7 КБ
- apps/miniapp/src/components/pauseQueueStore.ts — 9,0 (правка)
- apps/miniapp/src/components/pauseQueueStore.test.ts — размер даст ШТАБ (правка)
- apps/miniapp/src/components/pauseQueue.ts — ≈9 после c1 (правка)
- apps/miniapp/src/components/pauseQueue.test.ts — ≈10 после c1 (правка)
- apps/miniapp/src/components/OnboardingFlow.test.ts — 18,3 (только сверка, раздел 9)
- Чтение КОДЕРА ≈ 63 КБ + pauseQueueStore.test.ts.

## 6. Файлы
- Изменить: apps/miniapp/src/components/pauseQueueStore.ts, pauseQueueStore.test.ts, pauseQueue.ts, pauseQueue.test.ts.
- Создать и удалить: нет.

## 7. Поведение
7.1 pauseQueueStore.ts (B1)
- Ключ 'owner' в той же БД и том же хранилище slots, рядом с 'wipe-pending'.
- claimOwner(ownerId): Promise<'same' | 'changed' | 'unavailable'>:
  - ключа нет → записать ownerId, вернуть 'same';
  - ключ равен ownerId → 'same';
  - ключ другой → 'changed', ключ не перезаписывать;
  - ошибка хранилища → 'unavailable'.
- wipeAll удаляет БД очереди целиком, вместе с ключом 'owner'. Следующий claimOwner запишет нового владельца.
- write(slot): Promise<boolean> — true только после завершения транзакции, false при любой ошибке. Ошибку по-прежнему не логировать.
- Хранилище в памяти (indexedDB нет) ведёт себя так же: claimOwner работает, write возвращает true.
- Интерфейс PauseQueueStore дополнить claimOwner, тип write поменять.
7.2 pauseQueue.ts (B2)
- Экспорт pauseStartupGate(store, ownerId: string | null, timeoutMs = 3000): Promise<'open' | 'closed'>:
  - ownerId null → closed;
  - sendClosed() → closed;
  - isWipePending() → wipeAll(); 'blocked' → closed;
  - claimOwner: 'unavailable' → closed; 'changed' → wipeAll(); 'blocked' → closed; затем claimOwner снова, не 'same' → closed;
  - иначе open;
  - не уложились в timeoutMs → closed.
- runTick: гейт вызывается до store.read, после проверок halted и conflict, которые уже есть в B2. closed → send не вызывается, таймер не ставится, onOutcome не вызывается.
- enqueue: гейт первым шагом; closed → бросить Error, как сейчас при отсутствии владельца. write вернул false → бросить Error, слота нет, POST нет.
- Каждая запись слота перед send должна вернуть true, иначе send не вызывается и таймер не ставится. Результат записей после ответа (clear, stopped) не проверять.
- Если воркер уже в конфликте после 409 IDEMPOTENCY_CONFLICT: enqueue и runTick гейт не вызывают и ведут себя как сейчас (R339 «wipe on next open»: стирает новый воркер).
- Проверку slot.ownerId оставить как вторую защиту. Поведение тестов #299 сохранить.
- В pauseQueue.ts, в том числе в комментариях, нет слова indexedDB: файл в NO_STORAGE_FILES.

## 8. БД
Миграции нет. Новых зависимостей нет.

## 9. Тесты
- pauseQueue.test.ts — новые тесты на настоящем хранилище: фабрика B1 с аргументом null, хранилище в памяти, имя — как в pauseQueueStore.ts:
  - (1) A ставит операцию, владелец меняется на B, tick → send 0, read(A) = null. Без правки этот тест падает: это доказательство ошибки;
  - (2) A ставит операцию, новый воркер с владельцем B делает enqueue → слота A нет, слот B есть.
- pauseQueue.test.ts — новые тесты на фейке:
  - (3) owner null → enqueue бросает, send 0;
  - (4) claimOwner 'unavailable' → send 0;
  - (5) 'changed' и wipeAll 'blocked' → send 0, enqueue бросает;
  - (6) claimOwner не отвечает, timeoutMs = 10 → closed, send 0;
  - (7) write false в enqueue → бросает, send 0;
  - (8) wipePending у нового воркера → wipeAll до первого send.
Задетые тесты (правило «Т»), полный список:
- apps/miniapp/src/components/pauseQueue.test.ts — в fakeStore добавить поле owner и claimOwner; write возвращает true. Тест «смена владельца → wipeAll до send» переделать на claimOwner. Остальные тесты не трогать.
- apps/miniapp/src/components/pauseQueueStore.test.ts — изменить. Точные правки (claimOwner: same, changed, unavailable, ключ после wipeAll; write: true и false) Агент вносит сам, только в этом файле.
- apps/miniapp/src/components/OnboardingFlow.test.ts — не меняется. Новых файлов нет, поэтому NO_STORAGE_FILES остаётся как есть.
  Новые строки pauseQueueStore.ts не должны содержать слов из его проверки: initdata, init_data, token, console., localstorage, sessionstorage, document.cookie, dexie, birth, short_no.
- Цели tools/check.sh — область miniapp, как в AGENT-BRIEF.md. vitest — в CI.

## 10. Живые проверки на сервере
Нет: воркер запускается только в c3.

## 11. Запреты
- AGENT-BRIEF.md, раздел 3.
- Не трогать client.ts, pause.ts, pauseSend.ts, App.tsx, routes.tsx и drafts.ts. Версию БД черновиков не менять.
- Не логировать ownerId и слот. Новых зависимостей нет.

## 12. Критерии готовности
- Тест (1) зелёный на настоящем хранилище, тесты #299 зелёные.
- Отправки нет без успешной записи и без гейта 'open'. Отличия от карточки перечислены в PR.

## 13. Оценка
Автор ≈ 0,3 ч. Агент Opus 450–700 кредитов, в том числе 2 задетых файла по правилу «Т». Код ≈ 80–130 строк, тесты ≈ 200–300.

## 14. РЕВЬЮЕР
Нет: initData, 18+, согласия, rate-limit, GRANT и оплату карточка не меняет.
