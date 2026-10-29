# miniapp-fix-2 — /day: «Обновляем…», автоповтор GET при 503, «Участник не найден» на marks/submit, удалить HomePage

## 1. Паспорт
- id: miniapp-fix-2 · ветка КОДЕРА: `fix/miniapp-fix-2` · режим: Р0+ (бесплатный КОДЕР) · зависит от: нет.
- Заголовок PR: `fix(miniapp): /day — «Обновляем…», повтор GET при 503, 404 участника на marks/submit, удалить HomePage`
- Область (SHTAB.md 3-Б): только `apps/miniapp/src/**`. API, бот, БД, nginx.conf — не трогать.
- Первый файл пакета — `docs/STATE.md`, если ШТАБ дал строки в старте КОДЕРА. Нет строк — STATE не трогать.
- Цель check.sh: `miniapp`.

## 2. Цель
Мелочи Mini App из docs/STATE.md («Кандидаты miniapp-fix-2»): при «Обновить» экран дня не мигает
«Загрузка…», кнопка пишет «Обновляем…»; GET /day/current при 503 SERVICE_UNAVAILABLE повторяется сам
2 раза; 404 PARTICIPANT_NOT_FOUND на PUT /day/marks и POST /day/report/submit — понятный текст;
неиспользуемый HomePage.tsx удалён.

## 3. Решения (метки К-6)
- «Обновить» [ШТАБ-тех, 29.10]: экран дня остаётся, кнопка «Обновить» гаснет и пишет «Обновляем…»;
  ошибка обновления — прежний экран ошибки с «Повторить»; «Повторить» на экране ошибки — «Загрузка…», как сейчас.
- Автоповтор [ШТАБ-тех, 29.10]: только 503 SERVICE_UNAVAILABLE; 2 повтора через 2 с и 4 с (3 попытки);
  DAY_CONTENT_MISSING, 404, 401, сеть — без повтора. Один timerRef; load() сначала clearTimer(); старые
  ответы отсекаются по requestIdRef; при размонтировании таймер чистится. Счётчик сбрасывают успех и
  «Повторить». Чистая функция dayRetryDelayMs(err, attempt) в dayScreen.ts, с тестами.
- 404 участника [ШТАБ-тех]: 404 PARTICIPANT_NOT_FOUND → PARTICIPANT_NOT_FOUND_MESSAGE (уже есть в
  dayScreen.ts) без префикса; действия после ошибки (markErrorAction / submitErrorAction) не менять.
- HomePage [ШТАБ, состав STATE]: удалить файл; в routes.tsx убрать строку-комментарий о нём.
- Не менять: маппинг IDEMPOTENCY_CONFLICT → DAY_CHANGED_MESSAGE (так задумано), API, бот, БД.

## 4. Выдержки и факты кода (КОДЕР архитектуру не читает)
Канон: проверено build/miniapp-screens.md §«Дневной модуль», build/miniapp-api-contract.yaml
(components.responses.ServiceUnavailable, /day/current), 03-day-mechanics.md §3.10, §3.11, DECISIONS.md —
о «Обновить» и повторах GET молчит; поэтому решения выше — [ШТАБ-тех].
По коду (проверил ПРОЕКТИРОВЩИК, hash 7922a65; эти файлы не читать):
- apps/api/app/routers/day.py: любая ошибка БД → 503 `SERVICE_UNAVAILABLE`; нет контента дня →
  503 `DAY_CONTENT_MISSING` (повтор не поможет). Retry-After на 503 сервер не ставит.
- api/client.ts: `ApiError(status, code, message)`; заголовки ответа в ApiError не хранятся.
- git grep HomePage: только routes.tsx (стр. 11, комментарий) и сам HomePage.tsx. Упоминания в
  docs/DEFECTS-ARCHIVE.md и docs/STATE.md — история, не трогать. Тестов на HomePage нет.

## Канон и решения
(а) Используются: 03-day-mechanics.md §3.10, §3.11 (только как граница: гашение и «ложного успеха нет» —
про отчёт, задача их не меняет); build/miniapp-screens.md §«Дневной модуль» (day.current);
build/miniapp-api-contract.yaml ServiceUnavailable, /day/current.
(б) Противоречий с DECISIONS.md нет.
(в) —
(г) Правок канона нет. Отставание контракта от кода дня (коды ошибок /day/*) — уже D-33
«Контракт Mini App отстаёт от кода дня» (docs/DEFECTS-FOUND.md); новой записи не нужно.

## 5. ЧТО ПРОЧИТАТЬ (по hash main из docs/STATE.md)
| Файл | КБ |
|---|---|
| docs/process/CODER.md | ≈ 11 |
| AGENT-BRIEF.md | 17 |
| docs/decisions/DECISIONS.md | 8,5 |
| docs/STATE.md | ≈ 18 |
| docs/tasks/miniapp-fix-2.md (эта карточка) | ≈ 11 |
| apps/miniapp/src/pages/DayPage/DayPage.tsx | 15,1 |
| apps/miniapp/src/components/dayScreen.ts | 5,5 |
| apps/miniapp/src/components/dayMarks.ts | 5,3 |
| apps/miniapp/src/navigation/routes.tsx | 0,5 |
| apps/miniapp/src/components/dayScreen.test.ts | 8,0 |
| apps/miniapp/src/components/dayMarks.test.ts | 8,9 |
Чтение КОДЕРА ≈ 109 КБ (лимит 130–140). HomePage.tsx не читать — только DELETE.
client.ts, App.tsx, OnboardingFlow.tsx — НЕ читать.

## 6. Файлы
- Изменить: `apps/miniapp/src/pages/DayPage/DayPage.tsx`, `apps/miniapp/src/components/dayScreen.ts`,
  `apps/miniapp/src/components/dayMarks.ts`, `apps/miniapp/src/navigation/routes.tsx`,
  `apps/miniapp/src/components/dayScreen.test.ts`, `apps/miniapp/src/components/dayMarks.test.ts`.
- Удалить: `apps/miniapp/src/pages/HomePage/HomePage.tsx` (блок `===== DELETE: … =====`). Создать: нет.

## 7. Контракт (API не меняется; только клиент)
dayScreen.ts — добавить после testEnterAction:
    export const DAY_RETRY_DELAYS_MS = [2000, 4000] as const;
    /** Повтор GET /day/current после ошибки: мс или null. Только 503 SERVICE_UNAVAILABLE;
     *  attempt — сколько повторов уже сделано (0 → 2000, 1 → 4000, 2 и больше → null). */
    export function dayRetryDelayMs(err: unknown, attempt: number): number | null
  Не ApiError, другой status или code, attempt < 0 или не целое → null.
dayMarks.ts:
- импорт: `import { PARTICIPANT_NOT_FOUND_MESSAGE, type DayView } from './dayScreen.ts';`
  (цикла нет: dayScreen.ts не импортирует dayMarks.ts).
- actionMessage: первой строкой внутри `if (err instanceof ApiError)` —
  `if (err.status === 404 && err.code === 'PARTICIPANT_NOT_FOUND') return PARTICIPANT_NOT_FOUND_MESSAGE;`
  Прочие строки actionMessage не трогать (DAY_CHANGED_CODES с IDEMPOTENCY_CONFLICT — как есть).
routes.tsx: удалить строку `// HomePage.tsx оставлен в репозитории, но в маршрутах не используется.`
DayPage.tsx:
- `type LoadMode = 'full' | 'refresh' | 'silent';` — full: «Загрузка…» (монтирование, «Повторить»,
  тестовый вход); refresh: «Обновить» (экран на месте, кнопка «Обновляем…»); silent: таймер и после
  отметки / отчёта. Замены: `load(true)` → `load('full')`, `load(false)` → `load('silent')`.
- Новое: `const [refreshing, setRefreshing] = useState(false);` и `const retryRef = useRef(0);`
- load(mode, isRetry = false):
    clearTimer();
    if (!isRetry) retryRef.current = 0;
    const id = ++requestIdRef.current;
    if (mode === 'full') setStatus('loading');
    setRefreshing(mode === 'refresh');
    then: (проверка mounted/id как сейчас) → retryRef.current = 0; setRefreshing(false); дальше всё как сейчас
          (refetchDelayMs ставит timerRef — как есть).
    catch: (проверка mounted/id как сейчас) →
          const delay = dayRetryDelayMs(err, retryRef.current);
          if (delay !== null) { retryRef.current += 1; timerRef.current = setTimeout(() => load(mode, true), delay); return; }
          retryRef.current = 0; setRefreshing(false); setLoadError(err); setStatus('error');
  Между попытками: full — «Загрузка…»; refresh — экран дня и «Обновляем…»; silent — экран дня как был.
  После 3-й неудачи — экран ошибки dayErrorMessage + «Повторить» (как сейчас).
  Два таймера невозможны: и повтор, и refetchDelayMs пишут в один timerRef, а load() начинается с
  clearTimer(). Новый load не-повтор (Обновить, отметка, таймер) отменяет ждущий повтор и сбрасывает счётчик.
- Кнопки: `const retryLoad = () => { setNotice(''); load('full'); };` — для «Повторить» на экране ошибки
  и в view 'unknown'. `refresh = () => { if (refreshing) return; setNotice(''); load('refresh'); }` — «Обновить»:
      <button type="button" disabled={refreshing} onClick={refresh}>{refreshing ? 'Обновляем…' : 'Обновить'}</button>
- Размонтирование — как сейчас (mountedRef = false; clearTimer()).
- Шапку DayPage.tsx дополнить 2 строками: «Обновить» — без «Загрузка…», кнопка «Обновляем…»;
  503 SERVICE_UNAVAILABLE — 2 повтора (2 с, 4 с) тем же timerRef (miniapp-fix-2).
Принято, не чиним: быстрый двойной клик до перерисовки может отправить 2 GET — первый отсекается requestIdRef.

## 8. БД
Нет.

## 9. Тесты (vitest, environment node)
dayScreen.test.ts — добавить в импорт `DAY_RETRY_DELAYS_MS, dayRetryDelayMs` и describe('dayRetryDelayMs'):
- 503 SERVICE_UNAVAILABLE: attempt 0 → 2000, 1 → 4000, 2 → null; DAY_RETRY_DELAYS_MS = [2000, 4000].
- без повтора: 503 DAY_CONTENT_MISSING, 404 PARTICIPANT_NOT_FOUND, 401 TG_INIT_INVALID,
  TypeError('Failed to fetch'), attempt −1 → null.
dayMarks.test.ts — добавить в импорт `import { PARTICIPANT_NOT_FOUND_MESSAGE } from './dayScreen.ts';` и в describe('actionMessage'):
- 404 PARTICIPANT_NOT_FOUND → PARTICIPANT_NOT_FOUND_MESSAGE и для 'mark', и для 'report' (без префикса).
- 404 NOT_FOUND → с префиксом: `Отметка не сохранилась. ${errorMessage(e)}`.
DayPage.tsx юнит-тестами не покрыт (React-тестов в окружении нет): проверка — сборка CI и живые.
Быстрые: `bash tools/check.sh miniapp`. Только CI: vite build, docker miniapp.

## Задетые тесты (правило «Т»)
- `apps/miniapp/src/components/dayMarks.test.ts` → только добавления из раздела 9; существующие it не
  меняются («прочее — с префиксом» использует 503 и сеть — проходит).
- `apps/miniapp/src/components/dayScreen.test.ts` → только новый describe из раздела 9; существующие не меняются.
- Другие тесты Mini App (client, startup, drafts, ErrorBoundary, OnboardingFlow) actionMessage, dayScreen и
  HomePage не импортируют. Упал тест вне списка — не чинить, «тест X вне списка» в ИТОГ.

## 10. Живые проверки (после мержа)
СЕРВЕРНЫЙ (`DC` = `docker compose --env-file .env -f infra/docker-compose.dev.yml`, из `~/course-bot`):
1. `git pull origin main` → `DC up -d --build --no-deps miniapp` → `DC ps`: miniapp Up (healthy),
   остальные не пересозданы. Бэкап не нужен (БД не трогаем).
Автор (Telegram, аккаунт А2 — день не начат). А1 НЕ трогать (идёт тестовый день).
2. Закрыть Mini App полностью и открыть заново (кэш Telegram).
3. Открывается /day: «Загрузка…» один раз, затем «День ещё не начат.» и «Обновить».
4. Нажать «Обновить» → кнопка гаснет и пишет «Обновляем…» (на быстрой сети — мельком), экран
   НЕ сменяется на «Загрузка…»; затем снова «Обновить». В логе api — GET /miniapp/v1/day/current 200.
404 PARTICIPANT_NOT_FOUND и 503 SERVICE_UNAVAILABLE живьём не воспроизвести — только тесты CI.

## 11. Запреты
- AGENT-BRIEF.md, раздел 3 (ПДн и initData не логировать; initDataUnsafe не доверять; новых зависимостей нет).
- Не менять api/client.ts, App.tsx, OnboardingFlow.tsx, startup.ts, index.css, nginx.conf и файлы вне
  `apps/miniapp/src/**` (кроме docs/STATE.md со строками ШТАБа).
- Не менять refetchDelayMs, его числа и тесты; маппинг IDEMPOTENCY_CONFLICT → DAY_CHANGED_MESSAGE;
  markErrorAction / submitErrorAction; логику X-Client-Op-Id.
- Не хранить ничего на устройстве; в лог и на экран — без error.message.
- Тексты — только из раздела 3 и уже существующие константы.

## 12. Критерии готовности
- check.sh miniapp зелёный; CI 7/7. Всё из раздела 7; старые тесты dayScreen/dayMarks зелёные.
- HomePage.tsx удалён; в apps/miniapp нет строки «HomePage».
- В DayPage.tsx один timerRef; setTimeout повтора и refetchDelayMs — только через него.
- Живые 1–4 ✅.

## 13. Оценка
Автор ~0,5 ч + сервер 1 задание; кредиты 0 (Р0+).

## 14. РЕВЬЮЕР
Нет: initData, 18+, согласия, rate-limit, роли БД и оплату карточка не трогает.
