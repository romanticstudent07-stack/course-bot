# miniapp-pause-c3b — экран /paused, DayGuard, маршрут

## 1. Шапка
- id: miniapp-pause-c3b · пачка T5-C · область apps/miniapp
- Заголовок PR: feat(miniapp): paused screen, DayGuard, /paused route (c3b)
- Ветка: feat/miniapp-pause-c3b
- Режим: Р1 (Агент Opus) или Р0+ — выбирает ШТАБ
- Зависит от: miniapp-pause-c3a. Начинать после её мержа. Миграции нет. Новых зависимостей нет.
- Выкат Mini App — только после api #284, #286, #293.

## 2. Цель
DayGuard оборачивает /day: при активной паузе участник попадает на /paused, и день не открывается.
Экран /paused показывает статус и ETA, даёт взять, отменить и досрочно завершить паузу через координатор pause.ts.
Пункта «Меню» нет (это задача панели): экран открывается только маршрутом /paused.

## 3. Решения Автора
- 26.11 (К-4 г, по сообщению ШТАБа): вход — пункт «Пауза» в «Меню». В normal это запрос, в pause_user — управление и экран статуса. Ссылки под днём нет.
- 26.11, дословно: «если участник заполняет … и решает что ему что-то нужно уточнить по кнопке Помощь то при возврате на экран заполнения заполненные данные должны сохраняться».
- R-2026-11-21: бизнес-409 — сообщение и reread, без очистки. Поздняя доставка — PAUSE_REFUSED и новое подтверждение, дата сама не сдвигается.

## 4. Выдержки канона
- miniapp-screens.md:51: «lifecycle.paused | /paused | Экран паузы (три полосы паузы, ETA)».
- B17-admin-panel-patch.md:44: «вывод трёх полос паузы (user_pause, author_pause, pause_shadow) с указанием инициатора и кода причины, где теневая пауза видна только владельцу».
- 10-02 resolver: screen_rule: reread_state_then_resolve. Регрессия 4 (t5-bc §4) — см. c3a §4.
- Контракт GET /pause: budget_days_left, budget_days_total, cycle_ends_at, pause {id, status, start_at, planned_end_at}, can_request, refusal, start_date (обязательное).
- Канон и решения:
  (а) используются miniapp-screens:51, B17:44, 10-02, контракт /pause.
  (б) три полосы — см. §15. 10-05 §3 — задача панели.
  (г) правок канона в c3b нет; предложение для DEFECTS — в ИТОГЕ окна.

## 5. ЧТО ПРОЧИТАТЬ (полные размеры @f864913 плюс то, что добавила c3a)
- AGENT-BRIEF.md — 17,1
- apps/miniapp/src/components/pause.ts — 10,0
- apps/miniapp/src/components/pauseRuntime.ts — около 4 (c3a)
- apps/miniapp/src/components/dayAccess.ts — около 2 (c3a)
- apps/miniapp/src/components/pauseQueue.ts — около 11
- apps/miniapp/src/navigation/routes.tsx — 0,8
- apps/miniapp/src/components/dayScreen.ts — 6,3
- apps/miniapp/src/pages/MePage/MeCardPage.tsx — 3,4 (образец стиля)
- apps/miniapp/src/api/client.ts — 22,6
- apps/miniapp/src/components/OnboardingFlow.test.ts — 18,3
Чтение КОДЕРА ≈ 96 КБ плюс карточка.

## 6. Файлы
Создать:
- apps/miniapp/src/components/DayGuard.tsx
- apps/miniapp/src/components/pausedScreen.ts
- apps/miniapp/src/components/pausedScreen.test.ts
- apps/miniapp/src/pages/PausedPage/PausedPage.tsx
Изменить:
- apps/miniapp/src/navigation/routes.tsx
- apps/miniapp/src/components/OnboardingFlow.test.ts
DayPage.tsx и App.tsx не трогать.

## 7. Поведение
7.1 routes.tsx
- Маршрут /day рендерит DayGuard с DayPage внутри (обёртка в этом файле).
- Новый маршрут { path: '/paused', Component: PausedPage }.

7.2 DayGuard.tsx
- При монтировании — один checkDayAccess(getPause, Date.now()).
- Пока ждём — «Загрузка…». open → children. paused → Navigate на /paused с replace.
- error → dayErrorMessage(error) и кнопка «Повторить»:
  - кнопка реально disabled, пока !canRetry;
  - таймер setTimeout(retryAt − now) только включает кнопку и GET не делает; при размонтировании — clearTimeout;
  - по нажатию — снова проверить canRetry(Date.now()) и сделать ровно один checkDayAccess.
- Повтор с отсрочкой (dayRetryDelayMs) здесь не применять: это только для /day/current.
- Экспорт DayGuardErrorView({ text, retryEnabled, onRetry }) — без хуков, нужен для теста.

7.3 PausedPage.tsx
- runtime берётся из PauseRuntimeContext. Если null — PAUSE_REOPEN_TEXT, без кнопок.
- При монтировании:
  - создать координатор по сигнатуре pause.ts: queue — runtime.queue(), чтение — getPause;
  - detach = runtime.attach(coord.onOutcome);
  - сделать coord.reread();
  - после успешного GET вызвать runtime.queue().resumeAuth(), если координатор этого ещё не делает (по коду pause.ts — не дублировать).
- При размонтировании: detach и coord.dispose().
- Снимок из onView кладётся в state. Вид строит pausedView(snapshot, nowMs) из pausedScreen.ts.
- Ошибка GET: текст и кнопка по тем же правилам, что в DayGuard (retryAtFrom, canRetry, один ручной GET).
- Кнопки по статусу. Это экран управления паузой, а не кнопки дня, поэтому статус смотрит клиент.
  - pause null и can_request → форма запроса:
    - срок 1..7 и «Начало: <start_date из GET>»;
    - кнопка «Взять паузу» → coord.request({ days, start_date });
    - срок хранится в runtime.setFormDays: уход в /help и возврат его не теряет; после принятой постановки — setFormDays(null).
  - pause null и !can_request → текст по refusal (§7.4), без формы.
  - status из PAUSE_STATUS_CANCELLABLE → даты начала и конца и «Отменить паузу» → coord.cancel(pause.id).
  - status = PAUSE_STATUS_ACTIVE → полосы, ETA и «Выйти досрочно» → coord.resume(pause.id).
  - другой status → строка статуса, без кнопок.
- Пока busy — кнопки disabled.
- Исход stopped, в том числе STORAGE_WRITE_FAILED (status 0) → сообщение и reread. Новый UUID — только при новом нажатии (enqueue поверх stopped).
- Исход conflict или runtime.sendClosed() = true → PAUSE_CONFLICT_TEXT, кнопок нет.
- enqueue отклонён из-за «нет очереди» → PAUSE_REOPEN_TEXT.
- Ссылка «К экрану дня» ведёт на /day; что показать, решает DayGuard свежим GET.
- Таймеров в PausedPage нет: ETA пересчитывается при каждом новом снимке. Серию старта ведёт координатор.

7.4 pausedScreen.ts. Чистые функции, nowMs — аргументом.
- formatEta(planned_end_at, nowMs): «До конца паузы: N дн. M ч»; если срок прошёл — «Пауза завершается». Без пояса (решение ШТАБа З2, К-5).
- pauseBars(status, nowMs) — §15, вариант А до ответа Автора:
  - «Дни паузы в цикле»: доля budget_days_left / budget_days_total в процентах; при total 0 полосы нет;
  - «Ход паузы» (только при active): доля пройденного от start_at до planned_end_at, обрезка 0..100.
- refusalText(code): известные коды → короткие заглушки интерфейса; неизвестный → общий текст. Тексты интерфейса, не курса.
- pausedView(snapshot, nowMs) → { kind, buttons, bars, eta, message }.

## 8. БД
Нет.

## 9. Тесты (vitest, node, без DOM; рендер через createElement и renderToStaticMarkup)
pausedScreen.test.ts:
- active → кнопка resume, полосы и ETA; requested и approved → cancel; null и can_request → форма; null и !can_request → refusal;
- formatEta: часы и дни; прошедший срок;
- pauseBars: total 0, обрезка 0..100;
- DayGuardErrorView при retryEnabled false → button disabled; при true — без disabled;
- в исходниках DayGuard.tsx и PausedPage.tsx нет setInterval; в DayGuard.tsx единственный setTimeout включает кнопку и getPause не вызывает (поиск по исходнику).
Задетые тесты:
- OnboardingFlow.test.ts: в NO_STORAGE_FILES добавить './DayGuard.tsx', './pausedScreen.ts' и '../pages/PausedPage/PausedPage.tsx'.
- Тестов на routes.tsx и App.tsx нет (git grep @f864913, метка 6).
Цели: bash tools/check.sh miniapp.

## 10. Живые проверки
После выката api и Mini App:
- адрес с #/paused без паузы → форма;
- с активной паузой: #/day → /paused;
- «Выйти досрочно» → после reread день открывается через DayGuard.

## 11. Запреты
- AGENT-BRIEF §3. Новых зависимостей нет.
- Не менять: DayPage.tsx, App.tsx, pauseQueue.ts, pauseQueueStore.ts, pauseSend.ts, client.ts, pauseRuntime.ts.
- Три POST напрямую не вызывать — только через координатор.
- День не открывать из ошибки, active или таймера.
- console нет; ответы GET /pause — только в state React.
- «Меню», нижнюю панель, «Перенести» и «Дополнительную паузу» не делать.

## 12. Критерии готовности
- Тесты зелёные.
- Регрессия 4 соблюдена в DayGuard и на /paused.
- Форма сохраняет срок при уходе в /help.

## 13. Оценка
Автор 0,5 ч. Агент Opus 1 000–1 400 (около 620 строк с тестами).

## 14. РЕВЬЮЕР
Нет.

## 15. Открыто (К-4): три полосы
Канон: проверено miniapp-screens.md:51, B17-admin-panel-patch.md:44, :68, 06-participant-card.md:12, контракт GET /pause.
Противоречит: три полосы (user_pause, author_pause, pause_shadow) заданы для Карточки участника в админ-панели (Б17), а теневая видна только владельцу. В 10-04 (со слов ШТАБа) в pause_shadow пункт скрыт. В GET /pause нет полей author_pause и pause_shadow.
- А. Две полосы из GET /pause (бюджет и ход своей паузы) и ETA. Плюс: делается сейчас, API не нужен.
- Б. Своя пауза и пауза Автора без причины, теневую не показывать. Нужны задача api (поле в GET /pause) и правка канона.
- В. Одна полоса хода паузы и ETA, бюджет — строкой.
Мнение ПРОЕКТИРОВЩИКА: А. Код c3b пишется под А, смена варианта затронет только pauseBars.
