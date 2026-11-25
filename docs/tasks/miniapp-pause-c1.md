# miniapp-pause-c1 — клиент API пауз, координатор pause.ts, отправитель pauseSend.ts

## 1. Паспорт
- id: miniapp-pause-c1 · пачка T5-C · порядок Агента: c1 → c2 → c3.
- Заголовок PR: feat(miniapp): клиент /pause, координатор pause.ts и отправитель pauseSend.ts (miniapp-pause-c1)
- Ветка: feat/miniapp-pause-c1 · Режим: Р1 · Зависит от: miniapp-pause-b1 (#298), miniapp-pause-b2 (#299), start_date в GET /pause (#302).
- Основание: docs/research/t5-bc.md §5 (раскладка, регрессии 2 и 3), docs/decisions/R-2026-11-21.md.

## 2. Цель
Типизированный доступ Mini App к GET /pause и трём POST; координатор чтений pause.ts без гонки старых ответов;
единственное место вызова трёх POST — pauseSend.ts (отправитель для воркера B2). В main новые модули никто
не вызывает: экран /paused, DayGuard и запуск воркера — miniapp-pause-c3.

## 3. Решения Автора (дословно)
- R-2026-11-21, «Поздняя первая доставка»: «Не сдвигать дату автоматически. Если операция ещё не применена и исходная дата уже недопустима — показать отказ и запросить новое подтверждение. Если применена — вернуть прежний результат. Не вводить часовой срок намерения.»
- R-2026-11-21, «Область конфликтного 409»: «Очистка и аудит безопасности — только при доказанной коллизии op-id. Обычный бизнес-отказ — сообщение и перечитывание состояния, без удаления черновиков.»
- R-2026-11-21, итог: «PAUSE_REFUSED (reason start_date_passed) и новое подтверждение; применена — прежний результат. start_date входит в сверку параметров повтора.»
- Указание ШТАБа: клиент шлёт start_date из GET в POST /pause/request (R-2026-11-21, #302).

## 4. Выдержки канона (цитаты по docs/research/miniapp-pause-canon.md, который сверял И2/И4@878ee9e)
- И4 docs/architecture/normative/I4-wave-d.md, mini_app_client.R339_indexeddb_cache: «persistence: IndexedDB (survives page reload)»; «retry_policy: exponential backoff, per client_op_id»; «idempotency: client_op_id from И2 idempotency_keys».
- И4 R339 conflict_ux.on_server_409: «action: full IndexedDB wipe on next open», «log: security_audit event client_op_id_conflict» — сужено R-2026-11-21 до доказанной коллизии.
- И2 docs/architecture/normative/I2-wave-b.md, idempotency_keys.behavior_on_collision: «conflicting_params: return 409 + log conflict event».
- Б10, 10-02-transition-matrix.md: «screen_rule: reread_state_then_resolve»; день допускает свежий GET, а не таймер, кэш или ответ 201/202.

## Канон и решения
(а) Используется: И4 R339, И2 idempotency_keys, Б10 screen_rule.
(б) И4 R339 on_server_409 сужен решением R-2026-11-21 [Автор, канон противоречит себе/коду — см. R-2026-11-21].
(в) Правок канона в этой карточке нет. По STATE от 23.11 «Канон /pause/* внесён: DOCS #25, #26, #27 … OVERRIDES AD-03/AD-04».
    Входит ли туда сужение R339 — не проверено в окне КАРТОЧКИ. ШТАБ сверяет до промпта.

## 5. ЧТО ПРОЧИТАТЬ
- AGENT-BRIEF.md — 16,7 КБ
- apps/miniapp/src/api/client.ts — 18,3 (правка)
- apps/miniapp/src/components/pauseQueue.ts — 8,9 (правка: одна точка, раздел 7.2)
- apps/miniapp/src/components/pauseQueue.test.ts — ≈9 (+1 тест)
- apps/miniapp/src/components/pauseQueueStore.ts — 9,0 (только типы PauseSlot, PauseOpArgs; правка запрещена)
- apps/miniapp/src/components/OnboardingFlow.test.ts — 18,3 (только NO_STORAGE_FILES)
- docs/research/t5-bc.md — ≈15 (§5: дословные регрессии 2 и 3)
- apps/api/app/routers/pause.py — ≈31 (только чтение: модели ответов и коды ошибок; правка запрещена)
- Чтение КОДЕРА ≈ 126 КБ.

## 6. Файлы
- Создать: apps/miniapp/src/components/pause.ts, pauseSend.ts, pause.test.ts, pauseSend.test.ts (все в apps/miniapp/src/components/).
- Изменить: apps/miniapp/src/api/client.ts; apps/miniapp/src/components/pauseQueue.ts (только раздел 7.2);
  apps/miniapp/src/components/pauseQueue.test.ts (+1 тест); apps/miniapp/src/components/OnboardingFlow.test.ts (+2 строки).

## 7. Контракт и поведение
7.1 client.ts
- ApiError: необязательный 5-й аргумент details: Record<string, unknown> | undefined, по умолчанию undefined.
  apiRequest кладёт payload.details, только если это объект: не массив и не null. Формат ошибки {code, message, details} — apps/api/app/errors.py.
- RequestOptions.signal?: AbortSignal передаётся в fetch.
- Типы ответа GET /pause — буква в букву по модели ответа GET в pause.py, ничего не угадывать.
  Точно есть: start_date — местная дата YYYY-MM-DD, приходит всегда, и при can_request = false; can_request; refusal — "already_open" при открытой строке.
- getPause(signal?): GET /miniapp/v1/pause, без X-Client-Op-Id. Ошибки: 401, 404 PARTICIPANT_NOT_FOUND, 429, 503.
- postPauseRequest({days, start_date}, clientOpId) → 201, тело — по pause.py. days 1..7.
- postPauseCancel({pause_id}, clientOpId) и postPauseResume({pause_id}, clientOpId) → 202 {"status":"accepted"}.
- Ошибки POST:
  - 409: PAUSE_ALREADY_OPEN, PAUSE_REFUSED (details.reason, в том числе start_date_passed), PAUSE_NOT_CANCELLABLE, PAUSE_NOT_ACTIVE, IDEMPOTENCY_CONFLICT;
  - 404: PARTICIPANT_NOT_FOUND, PAUSE_NOT_FOUND;
  - 422 VALIDATION_ERROR; 401; 429 с Retry-After; 503.
  - Какие коды у какого маршрута — по pause.py.
7.2 pauseQueue.ts — единственная правка: исход 'business' получает details?: Record<string, unknown> из err.details.
  Если details нет, ключ не добавлять: тогда it.each с бизнес-409 в pauseQueue.test.ts проходит как есть.
7.3 pauseSend.ts
- sendPauseOp(slot): request → postPauseRequest(slot.args, slot.opId); cancel → postPauseCancel; resume → postPauseResume.
  args и opId из слота передаются как есть. Ошибку не ловить: её разбирает воркер B2.
- buildPauseQueueDeps({ store, onOutcome }) возвращает зависимости для createPauseQueue:
  - send = sendPauseOp;
  - getOwnerId: readTgUserId() → строка или null;
  - now = Date.now; newOpId = newClientOpId;
  - schedule на setTimeout, возвращает функцию отмены;
  - locks = navigator.locks, если он есть, иначе null.
7.4 pause.ts — координатор без React и без хранилищ
- createPauseCoordinator({ getPause, queue, onView }) возвращает { reread, request(days), cancel(pauseId), resume(pauseId), onOutcome }.
- reread (регрессия 2):
  - readSeq += 1; прошлый AbortController — abort();
  - ответ применяется, только если его seq последний;
  - после применения — queue.resumeAuth();
  - ошибка GET → onView с ошибкой по статусу; без таймеров и без pauseBackoffMs; AbortError не показывать.
- request(days):
  - start_date — только из последнего применённого GET. Такого GET нет или can_request = false → enqueue не вызывать;
  - пока операция в работе, повторный вызов ничего не ставит (регрессия 3);
  - enqueue бросил ошибку (нет владельца, B2) → onView с PAUSE_REOPEN_TEXT, POST не уходит;
  - после enqueue — queue.tick().
- cancel и resume — так же, pause_id берётся из аргумента.
- onOutcome:
  - done → reread;
  - business → текст по коду и reread;
  - PAUSE_REFUSED с details.reason = 'start_date_passed' → отказ, reread и новое подтверждение; автоповтора нет;
  - stopped → сообщение и reread; новый opId — только после нового явного вызова (enqueue поверх stopped, B2);
  - conflict → onView с outcome.text; после этого request, cancel и resume ничего не ставят.
- Тексты — технические заглушки, константы в pause.ts [ШТАБ-тех]. PAUSE_CONFLICT_TEXT импортировать из pauseQueue.ts.
- Дословно регрессии 2 и 3 — в t5-bc.md §5. Если §5 расходится с этим разделом — стоп и вопрос ШТАБу в ИТОГЕ.

## 8. БД
Миграции нет. Новых зависимостей нет.

## 9. Тесты
- pause.test.ts:
  - (1) два reread, первый ответ пришёл позже — применён только второй, первый получил abort;
  - (2) двойной request до исхода → один enqueue;
  - (3) start_date из последнего применённого GET попадает в args;
  - (4) GET не было или can_request = false → enqueue 0;
  - (5) start_date_passed → reread, enqueue не повторяется;
  - (6) stopped → reread; новый request → новый enqueue;
  - (7) enqueue бросает → заглушка, tick 0;
  - (8) успешный GET → resumeAuth 1 раз; ошибка GET → 0;
  - (9) conflict → текст R339, request ничего не ставит.
- pauseSend.test.ts:
  - (1) три вида операций → нужный postPause* с opId и args слота (vi.mock client.ts);
  - (2) по исходнику: postPauseRequest, postPauseCancel, postPauseResume есть только в client.ts и pauseSend.ts, в pause.ts их нет;
  - (3) getOwnerId: null → null, число → строка.
- pauseQueue.test.ts: +1 тест — PAUSE_REFUSED с details {reason:'start_date_passed'} → исход business с этими details.
- Цели tools/check.sh — область miniapp, как в AGENT-BRIEF.md. Сборка и vitest — в CI.
Задетые тесты (правило «Т»), полный список:
- apps/miniapp/src/components/OnboardingFlow.test.ts — в NO_STORAGE_FILES добавить './pause.ts' и './pauseSend.ts'.
- apps/miniapp/src/components/pauseQueue.test.ts — +1 тест, остальные тесты не трогать.
- Другие файлы, которые вызывают ApiError, правка не задевает: 5-й аргумент необязательный.
  Полный поиск по репо в этом окне не делался — ШТАБ сверяет по свежему main (правило «Т», п.5).

## 10. Живые проверки на сервере
Нет: до c3 модули никто не вызывает. Выкат — после c3 и api #284, #286, #293, #302.

## 11. Запреты
- AGENT-BRIEF.md, раздел 3.
- Не трогать pauseQueueStore.ts, App.tsx, routes.tsx, DayPage и apps/api.
- В pause.ts и pauseSend.ts — даже в комментариях — нет слов indexedDB, localStorage, sessionStorage, console.
- Тела запросов и ответов не логировать. Новых зависимостей нет.

## 12. Критерии готовности
- Тесты раздела 9 зелёные. Задетые тесты — только по списку.
- postPause* вызываются только в pauseSend.ts. Отличия от карточки перечислены в PR.

## 13. Оценка
Автор ≈ 0,5 ч. Агент Opus 650–950 кредитов, в том числе 2 задетых файла по правилу «Т». Код ≈ 300–430 строк, тесты ≈ 350–470.

## 14. РЕВЬЮЕР
Нет: initData, 18+, согласия, rate-limit, GRANT и оплату карточка не меняет. readTgUserId уже есть в main.
