# day-screen-a — Mini App: экран /day (показ дня, очередь, тестовый вход)

## 1. Паспорт
- id: day-screen-a · область: Mini App (apps/miniapp) · режим: Р1 (Агент Genspark).
- Заголовок PR: feat(miniapp): day-screen-a — экран /day по GET /day/current, очередь, тестовый вход
- Ветка: feat/day-screen-a · Зависит от: day-texts (смержен, texts load сделан). Дальше: day-screen-b.
- Миграций нет. API не меняется. Выкат — только miniapp (лучше один раз после b).

## 2. Цель
После онбординга Mini App открывает /day: текущий день по GET /miniapp/v1/day/current — блоки (в a только чтение),
«❓ Как выполнить?», строка «кнопки станут активны ДД.ММ в 04:00», ожидание очереди 10–60 мин, закрытый день,
кнопка «Тестовый вход» при включённом флаге. Отметки и отчёт — day-screen-b.

## 3. Решения Автора
- 20.10 (life-ops-b §3): «отчёты сдаются до 00:00!!! … кнопки нажать что выполнил может только в 04:00 следующего дня!!!!»;
  «ЛО-2-А (… "внимание начинаем завтра с 4:00 кнопки активируются")» → экран /day (поле active_from) и бот.
- В30: passed → следующий день сразу (показ после очереди, кнопки с 04:00); not_passed / all_not_done → тот же день.
- З2 21.10: вход — вариант А: в фазе app путь «/» и любой другой → /day; отдельной кнопки «Открыть день» нет.
- З2: ключи B9.day_active_from_hint, B9.day_queue_wait, B9.day_closed_hint; меток {date} нет — дату ДД.ММ и время
  экран выводит рядом сам, из строки active_from (не через new Date() в поясе телефона).
- ШТАБ: таймер просрочки DM 3.8 — не в этой пачке. РЕВЬЮЕР — нет.

## 4. Выдержки архитектуры (docs/architecture/03-day-mechanics.md, build/miniapp-screens.md)
- DM 3.1: «Задания дня и кнопки под ними становятся активными в 04:00 по локальному времени Участника (его ТЗ)».
- DM 3.2: «Пока текущий день не сдан, Участнику виден только экран текущего дня».
- DM 3.3: «Под каждым блоком — кнопка «❓ Как выполнить?» (интерактивная справка по конкретному заданию…)».
- DM 3.8: отсчёт «стартует в 00:00 суток выполнения»; DM 3.14: «21:00 по ТЗ Участника (за 3 часа до 00:00)» — дедлайн 00:00.
- DM 3.19: «выжидает рандомную задержку 10–60 минут … и только потом выдаёт результат и задания следующего дня»;
  «очередь влияет только на показ результата».
- miniapp-screens.md: onb.rules → day.current = /day; путь / занят onb.welcome.
- Границы (apps/api/app/day_clock.py): окно open — от active_from до deadline_at включительно; «часы» закрывают
  день после deadline + 120 с, тик 30 с → ≈ 00:02–00:03. Клиент окно НЕ считает: только поля сервера.

## 5. ЧТО ПРОЧИТАТЬ (чтение Агента ≈ 51 КБ)
AGENT-BRIEF.md — 16,8; apps/miniapp/src/api/client.ts — 6,8; apps/miniapp/src/components/App.tsx — 5,8;
apps/miniapp/src/navigation/routes.tsx — 0,4; apps/miniapp/src/pages/HomePage/HomePage.tsx — 0,6 (образец страницы);
apps/miniapp/src/components/OnboardingFlow.tsx — 16,7 (errorMessage, textsToMap, pickText, pageStyle, ref от двойного клика);
apps/miniapp/src/components/startup.test.ts — 4,0 (образец vitest). apps/api/** не читать — выдержка в §7.

## 6. Файлы (6 файлов, ≈ 550 строк)
- Изменить: apps/miniapp/src/api/client.ts — типы дня, getDayCurrent, postDayTestEnter.
- Создать: apps/miniapp/src/components/dayScreen.ts — чистые функции §7.4 (без React).
- Создать: apps/miniapp/src/components/dayScreen.test.ts — тесты §9.
- Создать: apps/miniapp/src/pages/DayPage/DayPage.tsx — экран §7.5.
- Изменить: apps/miniapp/src/navigation/routes.tsx — { path: '/day', Component: DayPage } вместо '/' → HomePage.
- Изменить: apps/miniapp/src/components/App.tsx — только fallback <Navigate to="/day"/> и строка комментария фазы app.
  HomePage.tsx не удалять (Мелочи).

## 7. Контракт (выдержка из apps/api/app/routers/day.py @3734b54; префикс /miniapp/v1; initData — как сейчас)
7.1 GET /day/current — только чтение. 200, тело с response_model_exclude_unset:
- всегда: status 'not_started' | 'entering' | 'open' | 'submitted' | 'queued' | 'closed'; lives: number; test_entry: boolean.
- not_started и entering (позиции нет) — ТОЛЬКО эти три поля. test_entry = флаг DAY_TEST_ENTRY_ENABLED и позиции нет.
- open, submitted, closed: position {stage_no, module_no, day_no}; day_started_at; blocks; min_optional; can_submit;
  active_from; deadline_at; queued_until = null; buttons_active.
- queued: position, blocks, min_optional = null; can_submit = false; buttons_active = false; active_from и deadline_at —
  следующего дня; queued_until — строка.
- блок: {block_id, title_key, help_key, critical: boolean, mark: 'done' | 'not_done' | null}.
- время — ISO 8601 со сдвигом пояса участника, например "2026-10-22T04:00:00+03:00" (бывает дробь секунд).
- приоритет на сервере: submitted → queued → closed → open. open + buttons_active false = ещё до 04:00.
  submitted — отчёт записан, проектор ещё не сдвинул день (обычно ≤ 2 с).
- ошибки {code, message}: 401 TG_INIT_MISSING / TG_INIT_INVALID; 404 PARTICIPANT_NOT_FOUND; 429;
  503 SERVICE_UNAVAILABLE / DAY_CONTENT_MISSING.
7.2 POST /day/test-enter — тела нет, X-Client-Op-Id не нужен. 202 {status:'entering'}; 200 {status:'already'};
  404 NOT_FOUND (флаг выключен) / PARTICIPANT_NOT_FOUND; 409 RECONSENT_REQUIRED; 409 DAY_STATE_SYNCING (Retry-After: 1); 503.
  Позицию ставит проектор: GET даст entering, затем open (кнопки — с ближайшей 04:00).
7.3 client.ts: DayBlock, DayCurrent (кроме status, lives, test_entry все поля «?: T | null»);
  getDayCurrent = () => apiRequest<DayCurrent>('/miniapp/v1/day/current');
  postDayTestEnter = () => apiRequest<{ status: 'already' | 'entering' }>('/miniapp/v1/day/test-enter', { method: 'POST' }).
7.4 dayScreen.ts (время — только аргументом nowMs):
- DAY_TEXT_KEYS = { activeFromHint: 'B9.day_active_from_hint', queueWait: 'B9.day_queue_wait', closedHint: 'B9.day_closed_hint' }.
- dayView(resp: unknown) → 'not_started' | 'test_entry' | 'entering' | 'not_active' | 'open' | 'submitted' | 'queued' | 'closed' | 'unknown':
  not_started + test_entry true → test_entry; open + buttons_active не true → not_active; битое тело, незнакомый status,
  open / closed / submitted без массива blocks → unknown.
- wallClock(iso) → { date: 'ДД.ММ', time: 'ЧЧ:ММ' } | null — регулярка ^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}) по строке; без Date.
- dayTextKeys(day) → 3 ключа DAY_TEXT_KEYS + title_key и help_key блоков, без повторов, порядок стабилен.
- refetchDelayMs(day, nowMs, sameViewTries) → мс или null. Цель: queued → queued_until; not_active → active_from;
  open → deadline_at; задержка = Date.parse(цель) − nowMs + 1000 в пределах [1000, 86 400 000]; не парсится → null.
  closed → 60 000; submitted и entering → 2000, пока sameViewTries < 5, потом null; остальные → null.
  (Date.parse строки со сдвигом — абсолютный момент: пояс телефона не влияет.)
- dayErrorMessage(err): 404 PARTICIPANT_NOT_FOUND → «Участник не найден. Закройте и откройте приложение заново.»;
  иначе errorMessage(err) из OnboardingFlow.tsx.
- testEnterAction(err): 404 NOT_FOUND → 'refetch'; 409 DAY_STATE_SYNCING → 'retry_1s' (один раз);
  409 RECONSENT_REQUIRED → 'reopen' («Закройте и откройте приложение заново.»); прочее → 'error'.
7.5 DayPage.tsx (как OnboardingFlow: useEffect и состояние, без react-query):
- монтирование и «Обновить» → один GET; после ответа — /texts/bulk только для новых ключей dayTextKeys
  (ошибка текстов экран не ломает: pickText даёт заглушку).
- таймер setTimeout(refetchDelayMs) → GET; чистить при размонтировании и новом ответе; sameViewTries — одинаковый view подряд.
- view → экран:
  test_entry — «День ещё не начат.» + «Тестовый вход» (ref от двойного клика) → после 200 / 202 → GET;
  not_started — «День ещё не начат.»; entering — «Готовим день…»;
  not_active — блоки + абзац: t(activeFromHint) + « ДД.ММ в ЧЧ:ММ» из wallClock(active_from) (null → только текст);
  open — блоки; submitted — t(queueWait); queued — t(queueWait) + строка про active_from, как в not_active;
  closed — t(closedHint), блоки не показывать; unknown — «Что-то пошло не так.» + «Повторить».
- блок: t(title_key), «⭐» при critical; отметка словами: done — «✅ Выполнил», not_done — «⬜ Не выполнил»,
  null — «не отмечено»; кнопка «❓ Как выполнить?» раскрывает t(help_key) под блоком (DM 3.3).
- ошибка GET → dayErrorMessage + «Повторить». «Обновить» — везде, кроме загрузки и ошибки.
- служебные строки (в кавычках выше) — в коде; тексты курса — только по ключам.

## 8. БД — нет.

## 9. Тесты (vitest, environment node). Цель: bash tools/check.sh miniapp (tsc + vitest; плюс eol и exec)
dayScreen.test.ts:
- dayView: 6 статусов; not_started + test_entry → test_entry; open без buttons_active или false → not_active;
  null, {}, status 'x', open без blocks → unknown.
- wallClock: "2026-10-22T04:00:00+03:00" → 22.10 / 04:00; с дробью секунд и с "Z" — по строке; "плохо", undefined → null.
- dayTextKeys: 3 + ключи блоков без повторов; queued (blocks null) → только 3.
- refetchDelayMs: queued → до queued_until + 1 с; цель в прошлом → 1000; > 24 ч → 86 400 000; not_active → active_from;
  open → deadline_at; closed → 60 000; submitted tries 0–4 → 2000, 5 → null; not_started → null; битая дата → null.
- dayErrorMessage, testEnterAction — по тесту на ветку. Тестов React-компонентов нет (окружение node).
Только CI: тесты с БД (не затронуты) и сборка образа miniapp.

## 10. Живые проверки (после выката miniapp; DAY_TEST_ENTRY_ENABLED = false)
Выкат miniapp — по infra/SERVER-IRONCLAD.md (пересборка miniapp), лучше один раз вместе с b.
- Автор, Mini App: закрыть и открыть (кэш Telegram) → номер участника → «Продолжить» → экран дня: «День ещё не начат.»,
  кнопки «Тестовый вход» нет.
- СЕРВЕРНЫЙ: в логе api «day/current: tg_user_id=… status=not_started»; 7/7 Up, 5 healthy; /onboarding/status 401.
Полная проверка дня (решение «C») — day-screen-b §10.

## 11. Запреты
AGENT-BRIEF §3. initDataUnsafe и часы телефона для решений не использовать: «можно ли нажать» — только buttons_active,
«какой экран» — только status. Окно 04:00–00:00 на клиенте не считать; new Date() для показа даты — нельзя (только wallClock).
Ответы не хранить (localStorage, sessionStorage). apps/api, OnboardingFlow.tsx, LaterSteps.tsx, startup.ts не менять.
Новых npm-пакетов нет. Тексты курса в коде не писать. Кнопок отметок и «Отправить отчёт» в a нет. CI не ждать (А-CI).

## 12. Готовность
Файлы §6; после онбординга → /day; все view §7.5; таймеры §7.4; тесты §9; CI 7/7; отличия от карточки — в описании PR.

## 13. Оценка
Автор ≈ 0,5 ч + сервер 1 задание (выкат miniapp, можно вместе с b). Кредиты Агента ≈ 700–1 000 (+ правки).

## 14. РЕВЬЮЕР: нет — initData, 18+, согласия, rate-limit, роли БД и оплату не трогает (чтение дня и флаговый вход).
