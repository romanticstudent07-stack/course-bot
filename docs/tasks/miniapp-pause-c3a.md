# miniapp-pause-c3a — гейт старта и запуск очереди пауз (без нового UI)

## 1. Шапка
- id: miniapp-pause-c3a · пачка T5-C · область apps/miniapp
- Заголовок PR: feat(miniapp): pause startup gate, queue runtime, day access (c3a)
- Ветка: feat/miniapp-pause-c3a
- Режим: Р0+ (КОДЕР, 0 кредитов) или Р1 (Агент Opus) — исполнителя выбирает ШТАБ
- Зависит от: #305, #306 (в main f864913). Миграции нет. Новых зависимостей нет.
- Следом: miniapp-pause-c3b (после мержа этой задачи).

## 2. Цель
App запускает pauseStartupGate один раз при монтировании и не пускает к черновикам, пока гейт не кончился.
В фазе app работает воркер очереди пауз. Появляются чистые функции доступа к дню (регрессия 4).
Участник изменений не видит: экрана /paused и DayGuard ещё нет (они в c3b).

## 3. Решения Автора
- R-2026-11-21, «Область конфликтного 409»: «Очистка и аудит безопасности — только при доказанной коллизии op-id. Обычный бизнес-отказ — сообщение и перечитывание состояния, без удаления черновиков.»
- Р-6а: лимиты и досрочный выход считает сервер; клиент их не считает.
- Решение Автора 26.11 (К-4 г, по сообщению ШТАБа): «Пауза будет в мини-ап!» Вход — пункт «Пауза» в «Меню» нижней панели. Это отдельная задача панели, не c3.

## 4. Выдержки канона
- Б10, 10-02 resolver: screen_rule: reread_state_then_resolve. По miniapp-pause-canon, «Основания»: день допускает только свежий GET — не таймер, не кэш, не 201/202.
- И4 R339 (реализовано в pauseQueue.ts): persistence IndexedDB; retry exponential backoff per client_op_id; on_server_409 — текст «локальные данные повреждены; переоткройте Mini App».
- И4 R380 on_tg_user_id_change → wipeAll (сделано в c2, pauseStartupGate).
- t5-bc §4, регрессия 4: checkDayAccess хранит Retry-After. DayGuard и кнопка ошибки /paused реально disabled до срока, потом один ручной GET. День не открывается ни из ошибки, ни из active, ни по таймеру.
- Канон и решения:
  (а) используются 10-02 resolver, И4 R339 и R380, miniapp-screens.md:51.
  (б) противоречий с DECISIONS.md нет. 10-05 §3 (Р96, «Пауза» в наборе бота) расходится с решением Автора 26.11; правка — в задаче панели ШТАБа.
  (г) правок канона в c3a нет.

## 5. ЧТО ПРОЧИТАТЬ (полные размеры @f864913)
- AGENT-BRIEF.md — 17,1
- apps/miniapp/src/components/App.tsx — 11,9
- apps/miniapp/src/components/pause.ts — 10,0
- apps/miniapp/src/components/pauseQueue.ts — около 11
- apps/miniapp/src/components/pauseQueueStore.ts — около 10 (размер не сверен)
- apps/miniapp/src/components/pauseSend.ts — 2,3
- apps/miniapp/src/api/client.ts — 22,6 (нужны ApiError и типы пауз)
- apps/miniapp/src/components/OnboardingFlow.test.ts — 18,3 (NO_STORAGE_FILES и запреты)
Чтение КОДЕРА ≈ 103 КБ плюс эта карточка.

## 6. Файлы
Создать:
- apps/miniapp/src/components/pauseRuntime.ts
- apps/miniapp/src/components/pauseRuntime.test.ts
- apps/miniapp/src/components/dayAccess.ts
- apps/miniapp/src/components/dayAccess.test.ts
Изменить:
- apps/miniapp/src/components/App.tsx
- apps/miniapp/src/components/pause.ts — только экспорт констант
- apps/miniapp/src/components/OnboardingFlow.test.ts — NO_STORAGE_FILES

## 7. Поведение
7.1 pause.ts. Экспорт:
- PAUSE_STATUS_ACTIVE = 'active';
- PAUSE_STATUS_CANCELLABLE = ['requested', 'approved'] as const.
Источник — pause.py:112–113, сверил ШТАБ. Внутреннюю ACTIVE заменить этим экспортом. Логику координатора не менять.

7.2 pauseRuntime.ts. Без React-хуков и без хранилищ.
- runPauseGate(gate, store, ownerId): Promise<boolean>. true только при результате 'open'; любой другой результат и отказ промиса → false.
  - gate — pauseStartupGate из pauseQueue.ts. Таймаут 3 с уже внутри c2, свой не добавлять.
- createPauseRuntime({ makeQueue(onOutcome), sendClosed }) возвращает { start, stop, queue, attach, sendClosed, getFormDays, setFormDays }:
  - start(): если очередь уже есть — ничего. Иначе q = makeQueue(dispatch), затем void q.tick(), чтобы поднять слот после перезагрузки. Метода start у очереди нет.
  - stop(): q.stop() и q = null. stop необратим, поэтому новый start() создаёт новую очередь.
  - queue(): объект типа PauseQueue. Если q есть — вызовы передаются в неё. Если q нет — enqueue отклоняется с Error('pause: no queue'), а tick и resumeAuth ничего не делают. В c3b при таком отказе экран покажет PAUSE_REOPEN_TEXT.
  - attach(listener) возвращает detach. dispatch(event) отдаёт исход только текущему listener; если listener нет, исход отбрасывается (экран при монтировании сам делает reread).
  - sendClosed(): тот же вызов store.sendClosed(), тип ответа — как в pauseQueueStore.ts, без переделки.
  - getFormDays() / setFormDays(n | null): срок формы запроса, целое 1..7 или null. Хранится только в замыкании: не на устройстве и не в логе. Нужно в c3b, чтобы введённое не терялось при уходе в «Помощь».
- PauseRuntimeContext = createContext<PauseRuntime | null>(null), без JSX.

7.3 App.tsx
- Новые состояния:
  - [pauseStore] = useState(() => createPauseQueueStore());
  - [runtime] = useState(() => createPauseRuntime({ makeQueue: (onOutcome) => createPauseQueue(buildPauseQueueDeps({ store: pauseStore, onOutcome })), sendClosed: () => pauseStore.sendClosed() }));
  - gateRef: Promise<boolean>;
  - [gateOpen, setGateOpen] = useState(false).
- useEffect с пустым списком зависимостей: один раз gateRef.current = runPauseGate(pauseStartupGate, pauseStore, pauseOwnerId()), по результату setGateOpen. Гейт идёт в фазе checking, параллельно с GET status. «Повторить» (attempt) гейт заново не запускает.
- routeByDraft перед openDraft ждёт gateRef.current: wipeAll удаляет и БД course-bot.
- onboarding.onComplete без reconsent: setPhase('later') — только после gateRef.current.
- Отказ гейта не ведёт в start-error: просто нет отправки.
- useEffect([phase, gateOpen]): при phase === 'app' и gateOpen → runtime.start(); в cleanup → runtime.stop(). Гейт не 'open' → очередь не создаётся.
- В фазе app обернуть HashRouter в PauseRuntimeContext.Provider value={runtime}. Маршруты, /help, HelpBar и «Помощь» (Р-19) не трогать.
- В шапку добавить одну строку про гейт и очередь (c3a).
- В App.tsx нельзя слов из запретов NO_STORAGE_FILES. Имя createPauseQueueStore с ними не совпадает — сверить по списку в тесте. Если совпадает — стоп и вопрос в ИТОГ.

7.4 dayAccess.ts. Чистые функции: без таймеров и без React; время приходит аргументом nowMs.
- type DayAccess = { kind: 'open' } | { kind: 'paused' } | { kind: 'error'; error: unknown; retryAt: number }.
- retryAtFrom(err, nowMs): ApiError 429 с retryAfter → nowMs + retryAfter × 1000; иначе nowMs.
- canRetry(access, nowMs): только для kind 'error'; true при nowMs >= retryAt.
- checkDayAccess(get, nowMs): ровно один вызов get(), в c3b это getPause.
  - pause?.status === PAUSE_STATUS_ACTIVE → paused;
  - иначе → open;
  - исключение → error с retryAtFrom.
- requested и approved дают open, потому что статус дня решает GET /day/current, а клиент даты и окно не считает (dayScreen.ts).

## 8. БД
Нет.

## 9. Тесты (vitest, node, без DOM)
dayAccess.test.ts:
- active → paused; requested, approved и pause null → open; get вызван ровно 1 раз;
- сеть или 503 → error, retryAt = now; 429 с retryAfter 30 → retryAt = now + 30 000;
- canRetry(now + 29 999) = false, canRetry(now + 30 000) = true;
- из error никакой now не даёт open без нового checkDayAccess;
- в исходнике dayAccess.ts нет setTimeout, setInterval и Date.now.
pauseRuntime.test.ts (фейковая очередь):
- start → makeQueue 1 раз и tick 1 раз; повторный start не создаёт новую очередь;
- stop → q.stop; start после stop создаёт новую очередь;
- queue().enqueue без start отклоняется; tick и resumeAuth без очереди не бросают;
- attach/detach: исход приходит текущему listener, после detach — не приходит;
- runPauseGate: 'open' → true, другое → false, отказ → false;
- formDays: set и get, сброс null; sendClosed передаёт вызов store.
Задетые тесты:
- OnboardingFlow.test.ts: в NO_STORAGE_FILES добавить './pauseRuntime.ts' и './dayAccess.ts'.
- Тестов, которые импортируют App.tsx или navigation/routes.tsx, нет (git grep @f864913, вывод Автора 26.11, метка 6).
Цели: bash tools/check.sh miniapp (как в c1/c2; ШТАБ сверяет).

## 10. Живые проверки
Выкат позже: после api #284, #286, #293 (SHTAB-DEBTS §1 п.6). После выката открыть Mini App — экран дня как раньше.

## 11. Запреты
- AGENT-BRIEF §3. Новых зависимостей нет.
- Не менять: DayPage.tsx, routes.tsx, drafts.ts, pauseQueue.ts, pauseQueueStore.ts, pauseSend.ts, client.ts.
- В App не добавлять таймеров и не вызывать GET /pause.
- Исходы и ошибки не логировать (console нет). На устройство ничего, кроме очереди c2.
- Нижнюю панель, «Меню» и «Помощь» не трогать — это задача панели.

## 12. Критерии готовности
- Тесты зелёные.
- Гейт не 'open' → очередь не создана.
- routeByDraft и переход в later ждут гейт.
- Экраны участника те же.

## 13. Оценка
Автор 0,5 ч. КОДЕР 0. Агент Opus 900–1 300 (около 480 строк с тестами; запас на регрессию 4: в c1 факт 1 395 при оценке 650–950).

## 14. РЕВЬЮЕР
Нет: initData, 18+, согласия, rate-limit, роли и оплата не затронуты; tg_user_id берётся готовым из pauseOwnerId.
