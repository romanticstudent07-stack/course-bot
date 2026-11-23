# miniapp-pause-b2 — воркер очереди пауз (pauseQueue)

## 1. Паспорт
- id: miniapp-pause-b2 · PR: feat(miniapp): pause queue worker (T5-B2) · ветка: feat/miniapp-pause-b2 [ШТАБ-тех]
- Режим: Р1 (Агент) · зависит от: miniapp-pause-b1 — начинать после её мержа
- Основание: docs/research/t5-bc.md §2, §4 (регрессия 1), §5.

## 2. Цель
Воркер одной операции: фазы queued и uncertain, backoff по op-id, Retry-After, гейт владельца,
межвкладочный lock, разбор исхода. Отправитель передаётся снаружи; в main воркер никто не запускает (запуск — C2).

## 3. Решения Автора (по R-2026-11-21 через t5-bc §6; ШТАБ сверяет с R-2026-11-21.md до промпта)
- Только 409 IDEMPOTENCY_CONFLICT — коллизия: очистка и текст R339; бизнес-409 — без удаления черновиков.
- Аудит client_op_id_conflict — только сервер; клиент не логирует (R-2026-11-21, 22.11).
- start_date не сдвигается; PAUSE_REFUSED start_date_passed — новое подтверждение и новый UUID (делает C1, не воркер).

## 4. Канон и решения (К-6)
Выдержки И4 I4-wave-d.md (d7163a0): 593–596 write_queue — retry_policy: exponential backoff, per client_op_id;
idempotency: client_op_id from И2 idempotency_keys. 599–603 conflict_ux.on_server_409: show_error
"локальные данные повреждены; переоткройте Mini App"; action: full IndexedDB wipe on next open.
607–613 R380_cleanup: on_tg_user_id_change: full wipe immediately; trigger: Telegram.WebApp.initDataUnsafe.user.id mismatch on load.

| Решение | Метка |
|---|---|
| Повтор тем же opId и теми же args, backoff по op-id | [канон И4 R339 write_queue; И2 idempotency_keys] |
| Коллизия → setWipePending, отправка закрыта, текст R339 дословно | [канон И4 R339 conflict_ux; Автор → R-2026-11-21] |
| Владелец слота ≠ текущий → wipeAll сразу | [канон И4 R380 on_tg_user_id_change] |
| Разбор исхода по t5-bc §5 | [Автор, канон проверен И4 R339 → R-2026-11-21] |
| Backoff min(60 с, 2 с × 2^attempt) | [ШТАБ-тех] (К-5) |
| Retry-After: notBefore = now + retryAfter × 1000, сохраняется в слоте | [ШТАБ-тех] |
| Lock navigator.locks 'course-bot-pause-queue', ifAvailable; без navigator.locks — без межвкладочного lock (повтор безопасен: тот же opId, сервер вернёт прежний 201/202) | [ШТАБ-тех] |
| 404, 422, прочие 409 → phase 'stopped', без автоповтора | [ШТАБ-тех] |
Правок канона нет.

## 5. ЧТО ПРОЧИТАТЬ (бюджет исполнителя)
- эта карточка ≈ 7 КБ
- apps/miniapp/src/components/pauseQueueStore.ts из B1 ≈ 7 КБ
- apps/miniapp/src/api/client.ts — 18,3 КБ, только тип ApiError (status, code, message, retryAfter)
- Чтение исполнителя ≈ 32 КБ.

## 6. Файлы
- создать: apps/miniapp/src/components/pauseQueue.ts
- создать: apps/miniapp/src/components/pauseQueue.test.ts
- изменить: apps/miniapp/src/components/OnboardingFlow.test.ts — './pauseQueue.ts' в NO_STORAGE_FILES

## 7. Контракт модуля [ШТАБ-тех]
createPauseQueue(deps): { enqueue(kind, args): Promise<string>; tick(): Promise<void>; resumeAuth(): void; stop(): void }
deps: store (PauseQueueStore из B1); send(slot) → Promise<unknown>; getOwnerId() → string | null;
now() → number; schedule(fn, ms) → отмена; locks? (по умолчанию navigator.locks, если есть); onOutcome(event).
- enqueue: новый opId — от вызывающего через args или deps.newOpId (UUID v4, newClientOpId из client.ts передаёт C1).
  Слот уже есть → не перезаписывать, вернуть его opId.
- tick: isWipePending → wipeAll, onOutcome {type:'wiped'}; sendClosed → выход; нет владельца → выход;
  slot.ownerId ≠ getOwnerId() → wipeAll сразу; now < notBefore → schedule; иначе под lock: phase 'uncertain', write, send.
Разбор исхода (ошибка — объект с числовым status; иное — сеть):
- успех (201/202) → clear, onOutcome {type:'done', kind, result}; GET делает C1.
- 409 IDEMPOTENCY_CONFLICT → setWipePending, отправка закрыта, onOutcome {type:'conflict', text: R339 show_error дословно}.
- 409 PAUSE_ALREADY_OPEN, PAUSE_REFUSED, PAUSE_NOT_CANCELLABLE, PAUSE_NOT_ACTIVE → clear, onOutcome {type:'business', code, details?}.
- другой 409, 404, 422 → phase 'stopped', onOutcome {type:'stopped', status, code}.
- 429 → тот же opId, notBefore по retryAfter (нет — backoff), attempt + 1.
- 401, 403 → ждать resumeAuth() того же владельца; отправки нет.
- сеть, таймаут, 5xx → 'uncertain', attempt + 1, notBefore = now + backoff.
- В файле нет подстрок indexeddb, console., persist(, localstorage, sendbeacon, location.hash.

## 8. БД
Нет.

## 9. Тесты
pauseQueue.test.ts — фейковые store, lock, часы и send, без библиотек:
- Регрессия 1 (t5-bc §4): сеть → 429 Retry-After 5 → повтор не раньше 5 с с теми же days, start_date и opId;
  новый воркер на том же store повторяет тот же opId и соблюдает notBefore.
- backoff 2, 4, 8 … 60 с, потолок держится.
- 201 → слот очищен, onOutcome done.
- 409 IDEMPOTENCY_CONFLICT → wipePending, send больше не вызывается, текст R339 дословно.
- каждый бизнес-409 → слот очищен, store.wipeAll не вызван.
- 404, 422, неизвестный 409 → stopped, повтора нет.
- 401 → нет повтора до resumeAuth.
- смена владельца → wipeAll до send.
- lock занят (ifAvailable → null) → send не вызван; без locks — send вызван.
- enqueue при занятом слоте не меняет opId.
Задетые тесты (правило «Т»): OnboardingFlow.test.ts — './pauseQueue.ts' в NO_STORAGE_FILES. Другие правок не ожидается.
Цели tools/check.sh — miniapp-цели по AGENT-BRIEF.md.

## 10. Живые проверки
Нет: воркер не подключён; выкат Mini App с C2 — только после api с #284, #286, #293 (SHTAB-DEBTS §1 п.6).

## 11. Запреты
- AGENT-BRIEF.md §3; новых зависимостей нет.
- Не трогать App.tsx, client.ts, routes; не делать GET и UI; checkDayAccess и DayGuard не писать.
- Клиент не логирует коллизию; тексты, кроме R339, — заглушки; аккаунты — А1–А4.

## 12. Критерии готовности
Тесты раздела 9 зелёные; в main воркер ни откуда не вызывается; diff — 3 файла.

## 13. Оценка
Код 220–300 строк, тесты 280–380. Часы Автора ≈ 1; кредиты ≈ 300–450 + 60–100 за OnboardingFlow.test.ts.
Исполнитель: Агент Р1, Claude Opus 5.5 — причина: таймеры, lock и 10+ сценариев, нужны прогоны тестов.

## 14. РЕВЬЮЕР
Нет: initData, 18+, согласий, серверного rate-limit (B-1), ролей и оплаты не трогает; 429 — только чтение Retry-After.
