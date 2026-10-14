# miniapp-fix-1 — D-23: таймаут и очередь черновика, нейтральный ErrorBoundary, текст HomePage

## 1. Паспорт
- id: miniapp-fix-1 · ветка КОДЕРА: `fix/miniapp-fix-1` · режим: Р0+ · зависит от: нет
  (Р0 nginx из раздела 15 мержится ДО выката этой карточки).
- Заголовок PR: `fix(miniapp): D-23 — таймаут и очередь черновика, нейтральный ErrorBoundary, HomePage`
- Область (SHTAB.md 3-Б): только `apps/miniapp/src/**`. БД, API, бот, nginx.conf — не трогать.
- Первый файл пакета — `docs/STATE.md`, если ШТАБ дал строки в старте КОДЕРА. Нет строк — STATE не трогать.
- Цель check.sh: `miniapp`.

## 2. Цель
D-23 (ревью #63, неблокирующее; обхода согласий нет). «Продолжить» не виснет, если IndexedDB
не отвечает: через 3 с — курс. Записи черновика идут одной очередью; после «Перейти к курсу»
email и город не возвращаются на устройство. При сбое UI — нейтральный текст без `error.message`.
HomePage — актуальный текст-заглушка.

## 3. Решения Автора (14.10, пачка miniapp-fix)
- Таймаут — Б: 3 с, `DRAFT_IO_TIMEOUT_MS = 3000`, один для openDraft и finishDraft.
- ErrorBoundary — А: «Что-то пошло не так. Закройте приложение и откройте заново.» Без кнопки.
- HomePage — А: «Здесь будет курс (экран-заглушка).»
- `/miniapp` без слэша → 404, как у `/miniapp/`. НЕ в пакете КОДЕРА: Р0 на сайте, раздел 15.

## 4. Выдержки (КОДЕР архитектуру не читает)
D-23, docs/DEFECTS-FOUND.md (дословно):
    1) openDraft без таймаута: IndexedDB.open завис → «Продолжить» неактивна навсегда;
    2) saveDraft без очереди: put прошлого шага может завершиться после clear (finishDraft) →
       email и город снова на устройстве (до 24 ч), номер ведёт в анкету;
    3) Root.tsx (шаблон): ErrorBoundary показывает пользователю error.message.
    Предлагаемое решение: таймаут openDraft (→ курс); одна очередь записей черновика;
    ErrorBoundary — нейтральный текст без message.
Правила черновика из шапки drafts.ts НЕ меняются: только step / email / city; привязка к
tg_user_id; TTL 24 ч; метки finished нет; ошибка хранилища переход не блокирует и в лог не пишется.
Как вызывается сейчас (проверил ПРОЕКТИРОВЩИК по hash 2782ac3; эти файлы не читать):
- App.tsx: хранилище одно — `const [draftStore] = useState(() => createDraftStore())`;
  `openDraft(draftStore, tgUserId, Date.now())` с `.catch(() => null)` → `afterNumber(null)` = курс.
- LaterSteps.tsx: получает этот store пропом; `openDraft(store, tgUserId, Date.now()).catch`;
  `saveDraft(store, tgUserId, draft, Date.now()).catch` на каждое изменение;
  `finishDraft(store, tgUserId, Date.now(), onFinish)`.
Подписи вызовов сохраняются (новые параметры — только необязательные в конце),
поэтому App.tsx и LaterSteps.tsx не меняются.

## 5. ЧТО ПРОЧИТАТЬ (по hash main из docs/STATE.md)
| Файл | КБ |
|---|---|
| docs/process/CODER.md | 11,1 |
| AGENT-BRIEF.md | 11,2 |
| docs/STATE.md | 23 |
| docs/tasks/miniapp-fix-1.md (эта карточка) | 9 |
| apps/miniapp/src/components/drafts.ts | 9,7 |
| apps/miniapp/src/components/drafts.test.ts | 10,5 |
| apps/miniapp/src/components/ErrorBoundary.tsx | 1,0 |
| apps/miniapp/src/components/Root.tsx | 1,2 |
| apps/miniapp/src/pages/HomePage/HomePage.tsx | 0,8 |
Чтение КОДЕРА ≈ 78 КБ. App.tsx, LaterSteps.tsx, startup.ts, OnboardingFlow.tsx, client.ts — НЕ читать.

## 6. Файлы
- Изменить: `apps/miniapp/src/components/drafts.ts`, `apps/miniapp/src/components/drafts.test.ts`,
  `apps/miniapp/src/components/ErrorBoundary.tsx`, `apps/miniapp/src/components/Root.tsx`,
  `apps/miniapp/src/pages/HomePage/HomePage.tsx`.
- Создать: `apps/miniapp/src/components/ErrorBoundary.test.ts`. Удалить: нет.

## 7. Контракт (API не меняется; только код клиента)
drafts.ts:
- `export const DRAFT_IO_TIMEOUT_MS = 3000;`
- `export function withTimeout<T>(p: Promise<T>, ms: number, fallback: T): Promise<T>` — что раньше:
  результат или ошибка p либо fallback через ms. Таймер снимается (clearTimeout), когда p завершилось.
  Ошибка p, пришедшая после таймаута, глотается (без unhandledrejection).
- `DraftStore` + необязательный `seal?(): void`.
- `export function createSerialDraftStore(inner: DraftStore, timeoutMs = DRAFT_IO_TIMEOUT_MS): DraftStore`
  (с seal):
  а) get, put, clear — одна очередь: следующая операция стартует, только когда предыдущая отпустила очередь;
  б) операция держит очередь до своего завершения (успех или ошибка) ИЛИ до timeoutMs от своего
     старта — что раньше; затем очередь идёт дальше (зависший IndexedDB не блокирует записи навсегда);
  в) вызывающий получает результат inner как есть (resolve или reject); reject и синхронный throw
     inner очередь не ломают;
  г) флаг sealed проверяется В МОМЕНТ ВЫПОЛНЕНИЯ put, не постановки: put, поставленный до seal и
     ещё не начатый, тоже пропускается (resolve без записи); get и clear после seal работают;
  д) seal() синхронный, повторный вызов безвреден.
- `createDraftStore()` → `createSerialDraftStore(<IndexedDB или память, как сейчас>)`.
  `createMemoryDraftStore` и `createIndexedDbDraftStore` не меняются.
- `openDraft(store, tgUserId, now, timeoutMs = DRAFT_IO_TIMEOUT_MS)`: прежняя логика целиком
  (get и возможный clear) под `withTimeout(<логика>, timeoutMs, null)`. Таймаут → null
  (App — курс; LaterSteps — анкета с первого шага). Ошибка до таймаута — reject, как сейчас.
- `saveDraft` — без изменений: порядок даёт очередь хранилища.
- `finishDraft(store, _tgUserId, _now, onFinish, timeoutMs = DRAFT_IO_TIMEOUT_MS)`:
  1) `store.seal?.()`; 2) clear под withTimeout (reject и синхронный throw глотаются, без лога);
  3) onFinish ровно 1 раз — после clear или по таймауту. Ошибка внутри onFinish не перехватывается.
- Шапку drafts.ts дополнить 2–3 строками: очередь, seal, таймаут 3 с (D-23).
ErrorBoundary.tsx:
- `export function NeutralErrorFallback()` → `<div className="page"><p>` + текст из раздела 3 + `</p></div>`;
  проп error не читает.
- `componentDidCatch(error: unknown)`: только `console.error('ErrorBoundary:', name)`, где
  name = `error instanceof Error ? error.name : typeof error`. Не `constructor.name` (сборка Vite
  сжимает имена классов). message, stack, componentStack не логировать. Лишний `setState` убрать
  (state ставит getDerivedStateFromError). getDerivedStateFromError и render — не менять.
Root.tsx: `<ErrorBoundary fallback={NeutralErrorFallback}>`; функцию ErrorBoundaryError удалить.
HomePage.tsx: подсказка → «Здесь будет курс (экран-заглушка).»; шапка: строка 1 —
«экран курса (заглушка)»; строку про SEAM-1 и Итерацию 1 убрать; строка про initData остаётся.
Принято, не чиним: (1) React сам пишет пойманную ошибку в консоль устройства — пользователь её
не видит; (2) если IndexedDB.open у put висел дольше 3 с и затем сработал уже после clear, запись
может вернуться — вероятность низкая; (3) таймаут openDraft в анкете → анкета с первого шага,
следующий put перезапишет старый черновик.

## 8. БД
Нет.

## 9. Тесты (vitest, environment node; таймауты — параметром 20–50 мс, без fake timers)
drafts.test.ts — добавить; старые тесты не менять:
- withTimeout: быстрое p → значение; медленное → fallback; reject до таймаута → reject.
- очередь: put (держим вручную) → clear → после обоих хранилище пусто; порядок вызовов inner: put, clear.
- seal: put после seal → inner.put не вызван; put, поставленный до seal и не начатый, — тоже не пишет.
- К2: зависший get (никогда не резолвится) → следующий put выполняется после timeoutMs.
- reject и синхронный throw inner → следующая операция выполняется.
- openDraft: зависший get → null за timeoutMs.
- finishDraft: зависший clear → резолвится, onFinish 1 раз; после finishDraft saveDraft не пишет
  (serial поверх памяти: peek → undefined).
- createDraftStore() в node (indexedDB нет) → у хранилища есть seal.
ErrorBoundary.test.ts (создать; `react-dom/server` — часть react-dom ^18.3.1, он уже в dependencies):
- `renderToStaticMarkup(createElement(NeutralErrorFallback))` — текст заглушки есть.
- state = `ErrorBoundary.getDerivedStateFromError(new Error('MARKER-d23'))`; экземпляр
  `new ErrorBoundary({ fallback: NeutralErrorFallback, children: createElement('p', null, 'child') })`,
  ему state → `renderToStaticMarkup(instance.render())`: нет `MARKER-d23`, текст заглушки есть.
  (renderToStaticMarkup границу ошибок не вызывает — поэтому state задаём руками.)
- `vi.spyOn(console, 'error')` + `componentDidCatch(new Error('MARKER-d23'))` → в аргументах
  нет `MARKER-d23`, есть `Error`.
Быстрые: `bash tools/check.sh miniapp`. Только CI: vite build, docker miniapp.

## 10. Живые проверки (после мержа; Р0 nginx уже в main — одна пересборка на оба PR)
СЕРВЕРНЫЙ (`DC` = `docker compose --env-file .env -f infra/docker-compose.dev.yml`, из `~/course-bot`):
1. `git pull origin main` → `DC up -d --build --no-deps miniapp` → `DC ps`: miniapp Up (healthy),
   остальные 6 не пересозданы. Бэкап не нужен (БД не трогаем).
2. Проверки curl из раздела 15 (если Р0 nginx в этом выкате).
Автор (Telegram):
3. Закрыть Mini App полностью и открыть заново (кэш Telegram).
4. Виден номер участника; в логе api `GET /miniapp/v1/onboarding/status` — 200 (returning).
   «Продолжить» → экран «Здесь будет курс (экран-заглушка).»
5–7 — нужен участник, не прошедший анкету (второй тестовый аккаунт Telegram). Нет такого —
пометить «не проверялось вживую», покрыто тестами CI:
5. Дойти до шага email или city, закрыть Mini App, открыть заново → анкета с сохранённого шага.
6. Дойти до finished → «Перейти к курсу» срабатывает один раз.
7. «Назад» сразу после «Перейти к курсу» → закрыть, открыть → номер → «Продолжить» ведёт в курс.
ErrorBoundary живьём не проверяем — только тест CI.

## 11. Запреты
- AGENT-BRIEF.md, раздел 3 (ПДн и initData не логировать; initDataUnsafe не доверять; новых зависимостей нет).
- Не менять App.tsx, LaterSteps.tsx, startup.ts, OnboardingFlow.tsx, api/client.ts, nginx.conf и файлы
  вне `apps/miniapp/src/**` (кроме docs/STATE.md со строками ШТАБа).
- Не добавлять хранилищ на устройстве (localStorage, sessionStorage, новые ключи IndexedDB);
  формат записи черновика (v = 1) не менять.
- В лог и на экран — без error.message, stack, email, города, tg_user_id.
- Тексты — только заглушки из раздела 3.

## 12. Критерии готовности
- check.sh miniapp зелёный; CI 7/7. Все пункты раздела 7; старые тесты drafts.test.ts зелёные.
- В Root.tsx и ErrorBoundary.tsx нет `error.message`.
- Живые 1–4 ✅; 5–7 — ✅ или «не проверялось вживую».

## 13. Оценка
Автор ~0,5 ч + сервер 1 задание; кредиты 0 (Р0+).

## 14. РЕВЬЮЕР
Нет: initData, 18+, согласия, rate-limit, роли БД и оплату карточка не трогает; черновик — только
step / email / city на устройстве, его правила не меняются.

## 15. Р0 nginx (отдельный PR на сайте, не КОДЕР)
- Ветка `fix/nginx-miniapp-noslash` · заголовок PR `fix(nginx): /miniapp без слэша → 404 (правило IRONCLAD)` ·
  файл только `apps/miniapp/nginx.conf`.
- Предусловие ДО мержа: СЕРВЕРНЫЙ печатает только путь WEBAPP_URL, без адреса:
      grep '^WEBAPP_URL=' ~/course-bot/.env | sed -E 's#^WEBAPP_URL=https?://[^/]*##'
  Ожидание: `/` (или пусто). Ровно `/miniapp` → НЕ мержить, вопрос Автору.
- Правка 1 (шапка файла). Было:
      #   /miniapp/ (и прочее под /miniapp/*, кроме v1) → 404 (правило IRONCLAD)
  Стало:
      #   /miniapp, /miniapp/ (и прочее под /miniapp/*, кроме v1) → 404 (правило IRONCLAD)
- Правка 2: ПЕРЕД строкой `# Правило IRONCLAD (SERVER-IRONCLAD.md, «Крон-окна»): путь /miniapp/ занят`
  вставить блок и пустую строку после него. В файле перед `#` и `location` — 4 пробела, перед `return` — 8:
      # /miniapp без слэша — тоже 404 (правило IRONCLAD, как /miniapp/ ниже).
      # Без этого блока путь уходит в location / и отдаёт index.html с кодом 200.
      location = /miniapp {
          return 404;
      }
- CI: job docker miniapp (`nginx -t`) зелёный.
- Живая (с сервера, после пересборки из раздела 10):
      curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5173/miniapp
      curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5173/miniapp/
      curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5173/
      curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5173/healthz
      curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5173/miniapp/v1/onboarding/status
  Ожидание по порядку: 404, 404, 200, 200, 401.
- Если карточка уже выкачена без Р0 nginx — отдельно `DC up -d --build --no-deps miniapp`.
