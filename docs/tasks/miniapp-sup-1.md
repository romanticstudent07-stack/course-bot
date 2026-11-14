# miniapp-sup-1 — экран «Помощь» в Mini App (Р-19)
Карточка по hash main 1aeae18 (apps/miniapp не менялся с 57eb408). Правило К — docs/process/CANON-CHECK.md. Сначала прочитай docs/decisions/DECISIONS.md целиком.
Основа: docs/research/bot-i3-3.md §3 п.1–3, §5, §7; Р-19 перекрывает исследование («тема одна» → 8 тем). Метки К-6 у решений.

## 1. Паспорт
- id: miniapp-sup-1 · заголовок PR: «feat(miniapp): экран Помощь — тема, вопрос, черновик (Р-19)»
- Ветка кода: feat/miniapp-sup-1 · режим: Р0+ КОДЕР (0 кредитов); Р1-П — только после 2 кругов красного CI [ШТАБ-тех, SHTAB-2 §4]
- Зависит от: api-sup-1 (#217, смержен). Миграций нет. Мерж — сразу; выкат — последним: migrate 0017 → бот → api → miniapp.

## 2. Цель
Кнопка «Помощь» внизу Mini App в фазах later и app. Экран: тема кнопкой (8 тем) → поле вопроса → «Отправить» (POST /miniapp/v1/support/question) или «Назад». Черновик (тема и текст) хранится на устройстве до 24 ч и стирается после 201.

## 3. Решения Автора (дословно, DECISIONS @1aeae18)
- Р-19 (13.11) — поддержка: кнопка «Помощь» — после 18+ и согласий, всегда внизу Mini App и пунктом «Меню»; экран: тема кнопкой → вопрос (черновик хранится) → пост в тему группы этой темы (подпись Р-15, «Карточка»). Тем 8: «Поддержка 1»…«Поддержка 7» и «Другое», у каждой своя тема группы; названия — заглушки, заменить до показа участникам курса. Ответ Автора — ✉️, предпросмотр, «Отправить»; ветка — цепочка ответов. Отложено (SHTAB-DEBTS §2): human_active, мьют 5/мин, /support_inbox. Устарело: 04 §4.6, YAML support_button: everywhere, I4 §8 E2.
- Р-16: ответы анкеты на устройстве не хранятся. Р-18: ответы Чек-Апа — только в памяти экрана.

## 4. Выдержки канона
- 04-onboarding §4.6 (через research §1): «На любом шаге онбординга — кнопка «Поддержка/Вопросы». …» — перекрыто Р-19 (где кнопка и сколько тем).
- Пункт «Меню» (Р-19): по коду (App.tsx, Root.tsx, routes.tsx, DayPage.tsx) меню в Mini App нет → пункт появится вместе с меню (долг в SHTAB-DEBTS). В этой задаче меню НЕ делать.

## 5. ЧТО ПРОЧИТАТЬ (КОДЕР)
docs/process/PACK.md 11,8; AGENT-BRIEF.md 17,1; docs/decisions/DECISIONS.md 7,5; docs/process/CANON-CHECK.md 4,9; эта карточка ≈ 13;
apps/miniapp/src/components/App.tsx 8,9; drafts.ts 13,3; LaterSteps.tsx 12,6 (образец open/save черновика в эффектах); apps/miniapp/src/api/client.ts 16,8; apps/miniapp/src/navigation/routes.tsx 0,8.
Чтение КОДЕРА ≈ 106,7 КБ + CODER.md (досчитает ШТАБ). OnboardingFlow.test.ts и drafts.test.ts не давать — их запреты в разделе 11.

## 6. Файлы (≈ 625 строк)
- Создать: apps/miniapp/src/components/SupportScreen.tsx (~200); apps/miniapp/src/components/SupportScreen.test.ts (~120); apps/miniapp/src/components/drafts.support.test.ts (~110).
- Изменить: apps/miniapp/src/components/App.tsx (+45); apps/miniapp/src/components/drafts.ts (+110); apps/miniapp/src/api/client.ts (+40).
- Не трогать: routes.tsx, LaterSteps.tsx, OnboardingFlow.tsx, все существующие *.test.ts.

## 7. Контракт и поведение
### 7.1 API [по коду apps/api/app/routers/support.py @1aeae18]
- POST /miniapp/v1/support/question; заголовок X-Client-Op-Id — UUID v4 (newClientOpId), один на попытку; повтор той же попытки — тот же id → 201 без нового поста.
- Тело: {topic_code: "s1"…"s7" | "other", text: string}. Сервер: len(text.strip()) >= 2 И len(text) <= 2000 по СЫРОМУ тексту; NUL → 422.
- 201 {"status":"sent"}; 401; 404 PARTICIPANT_NOT_FOUND; 409 RECONSENT_REQUIRED; 422 VALIDATION_ERROR / SUPPORT_TOPIC_INVALID / SUPPORT_TEXT_INVALID; 429 RATE_LIMITED / SUPPORT_TOO_FREQUENT + Retry-After (у SUPPORT_TOO_FREQUENT целое 1…30); 503 SERVICE_UNAVAILABLE / SERVICE_MISCONFIGURED. Тело ошибки {code, message}.
### 7.2 client.ts [ШТАБ-тех]
- export type SupportTopicCode = 's1' | 's2' | 's3' | 's4' | 's5' | 's6' | 's7' | 'other'.
- export const postSupportQuestion = (body: {topic_code: SupportTopicCode; text: string}, clientOpId: string) → apiRequest<{status: 'sent'}>(путь, {method: 'POST', body, clientOpId}).
- export function parseRetryAfter(v: string | null): number | null — только строка из цифр, целое > 0 и safe integer, иначе null.
- ApiError: 4-й параметр public readonly retryAfter: number | null = null (необязательный; вызовы с 3 аргументами не меняются). apiRequest при status 429 передаёт parseRetryAfter(response.headers.get('Retry-After')).
### 7.3 drafts.ts — черновик поддержки [Р-19 «черновик хранится»; механика ШТАБ-тех]
- Тот же IndexedDB и то же хранилище объектов, что у шага онбординга; отдельный ключ 'support'. Версию БД и состав хранилищ НЕ менять.
- import type { SupportTopicCode } from '../api/client.ts'; export const SUPPORT_TOPIC_CODES: readonly SupportTopicCode[] = s1…s7, other (по порядку).
- export interface SupportDraft { topic: SupportTopicCode | null; text: string }; EMPTY_SUPPORT_DRAFT = {topic: null, text: ''}.
- Запись: {v: 1, tgUserId, savedAt, topic, text}; SUPPORT_DRAFT_VERSION = 1; SUPPORT_DRAFT_MAX_CHARS = 4000 (кодовых точек, защита хранилища).
- export function parseStoredSupportDraft(raw, tgUserId, now): SupportDraft | null — null, если: не объект; v ≠ 1; tgUserId не равен; savedAt не число или > now + DRAFT_FUTURE_SKEW_MS; now − savedAt > DRAFT_TTL_MS; topic не из SUPPORT_TOPIC_CODES и не null; text не строка или длиннее SUPPORT_DRAFT_MAX_CHARS. Лишние поля отбрасываются.
- export interface SupportDraftStore { get(): Promise<unknown>; put(v: StoredSupportDraft): Promise<void>; clear(): Promise<void> }.
- export createMemorySupportDraftStore(); export createSupportDraftStore() — IndexedDB по ключу 'support' (нет IndexedDB → память), сверху своя очередь с таймаутом DRAFT_IO_TIMEOUT_MS, без seal. Общую очередь и доступ по ключу можно вынести во внутренние обобщённые функции; createSerialDraftStore и createIndexedDbDraftStore снаружи не меняются.
- export openSupportDraft(store, tgUserId, now): Promise<SupportDraft> — tgUserId null, битая, чужая или старая запись → clear и EMPTY; ошибка или таймаут 3 с → EMPTY. Никогда не бросает.
- export saveSupportDraft(store, tgUserId, draft, now): Promise<void> — tgUserId null или пустой черновик (topic null и text.trim() пусто) → clear; иначе put с обрезкой text до SUPPORT_DRAFT_MAX_CHARS. Ошибки глотает, в лог не пишет.
- export clearSupportDraft(store): Promise<void> — ошибки глотает.
- finishDraft и seal онбординга ключ 'support' не трогают (разные хранилища-обёртки).
- Шапку файла дополнить: «текст вопроса поддержки хранится по Р-19 (ключ support, 24 ч, привязка к tg_user_id); ответы анкеты и Чек-Апа сюда не класть никогда». Слова-запреты — раздел 11.
### 7.4 SupportScreen.tsx [Р-19; тексты — ШТАБ-тех]
- Пропсы: tgUserId: number | null; store: SupportDraftStore; onBack(); onRestart(); send? (по умолчанию postSupportQuestion — для тестов).
- export const SUPPORT_TOPICS = [{code: 's1', label: 'Поддержка 1'}, …, {code: 's7', label: 'Поддержка 7'}, {code: 'other', label: 'Другое'}] — подписи по Р-19 (заглушки самого Р-19), без text_registry.
- Монтирование: «Загрузка…» → openSupportDraft; есть тема → сразу шаг «вопрос», нет → шаг «тема». После загрузки каждое изменение темы или текста → saveSupportDraft.
- Шаг «тема» (export SupportTopicView): 8 кнопок, выбранная — aria-pressed="true"; «Назад» → onBack(). Нажатие темы → шаг «вопрос».
- Шаг «вопрос» (export SupportQuestionView): подпись выбранной темы, textarea, «Отправить» (disabled, пока validateSupportText ≠ 'ok' или идёт отправка), «Назад» → шаг «тема» (тема и текст остаются).
- export validateSupportText(s): 'nul' | 'short' | 'long' | 'ok' — '\u0000' в строке → 'nul'; [...s.trim()].length < 2 → 'short'; [...s].length > 2000 (СЫРОЙ текст) → 'long'. Подсказка под полем для short, long, nul. Отправляется текст как введён.
- X-Client-Op-Id: state opId. export opIdForSend(current, gen) = current ?? gen(). Любая смена темы или текста → opId = null; ошибки opId не сбрасывают (повтор = тот же id); 201 → null.
- 201 → черновик EMPTY и clearSupportDraft → экран «Вопрос отправлен.» + «Назад» → onBack().
- export supportErrorView(err): {kind: 'restart'} | {kind: 'message', text}. Тексты — константы в файле, обычным текстом в стиле startErrorMessage (startup.ts), без «[заглушка]»:
  401 → «Не удалось подтвердить вход. Закройте приложение и откройте снова.»;
  404 PARTICIPANT_NOT_FOUND, 409 RECONSENT_REQUIRED → restart: текст «Нужно заново проверить данные.» + «Повторить» → onRestart() (как formErrorAction 'restart' в onbForm.ts), черновик не трогать;
  422 любой → «Проверьте вопрос: от 2 до 2000 знаков.»;
  429 → «Слишком часто. Попробуйте через N с.» при retryAfter числе, иначе «Слишком часто. Попробуйте чуть позже.» (таймера нет);
  503 и ошибка сети (не ApiError) → «Сервис временно недоступен. Попробуйте позже.»; прочее → «Не удалось отправить. Попробуйте ещё раз.»
### 7.5 App.tsx [Р-19 «после 18+ и согласий»; механика ШТАБ-тех]
- Кнопка «Помощь» — только в фазах later и app. Нет в checking, start-error, no-access, onboarding [Р-19] и number [ШТАБ-тех: переходный экран].
- const [supportStore] = useState(() => createSupportDraftStore()) рядом с draftStore.
- later: state helpOpen. LaterSteps всегда смонтирован, при helpOpen обёрнут в div hidden (ответы анкеты и Чек-Апа в памяти не теряются, Р-16, Р-18). helpOpen → SupportScreen (onBack → helpOpen false; onRestart → retry). Не helpOpen → внизу кнопка «Помощь». retry() ставит helpOpen false.
- app: внутри HashRouter маршрут path="/help" перед «*» (в App.tsx, routes.tsx не трогать: там Component без пропсов) с компонентом-обёрткой SupportScreen; onBack: location.key === 'default' → navigate('/day', {replace: true}), иначе navigate(-1); onRestart → retry. Под Routes — компонент HelpBar (useLocation, useNavigate): на /help не показывается, иначе кнопка «Помощь» → navigate('/help').
- Нижняя панель: div со style position sticky, bottom 0, padding 16. На DayPage своей нижней панели нет (внизу «Обновить» и Link на /me) — проверил ШТАБ.
- Шапку App.tsx дополнить строкой про «Помощь» (Р-19) — без слов-запретов раздела 11.

## 8. БД
Миграций нет.

## 9. Тесты (vitest: include src/**/*.test.ts, environment node → только .ts, без JSX; рендер — createElement + renderToStaticMarkup, как в me.test.ts)
SupportScreen.test.ts:
1. SUPPORT_TOPICS: 8 штук, коды по порядку = SUPPORT_TOPIC_CODES, подписи «Поддержка 1»…«Поддержка 7», «Другое».
2. validateSupportText: '' и ' a ' → short; 'ab' и ' ab ' → ok; 2000 эмодзи → ok (кодовые точки); 'a' × 2001 → long; 'a' × 1999 + 2 пробела → long (максимум по сырому тексту); 'a\u0000b' → nul.
3. supportErrorView: 401, 404, 409 (restart), каждый код 422, 429 с retryAfter 7 (текст содержит «7») и с null, 503, TypeError, ApiError 500.
4. opIdForSend: null → вызван gen; строка → та же, gen не вызван.
5. parseRetryAfter: '7' → 7; null, '', '0', '-1', '1.5', 'abc', дата HTTP → null.
6. Рендер SupportTopicView: 8 кнопок тем + «Назад»; выбранная — aria-pressed="true". SupportQuestionView: подпись темы, textarea, «Отправить» с disabled при тексте 'a'.
7. Исходник SupportScreen.tsx (node:fs, в нижнем регистре) не содержит подстрок обоих списков раздела 11 (п.1 и п.2) — свои массивы в этом тесте.
drafts.support.test.ts (память, vi.useFakeTimers для таймаута):
8. save → open тем же tgUserId: тема и текст на месте; запись содержит v 1, tgUserId, savedAt.
9. open: чужой tgUserId, null, старше DRAFT_TTL_MS, savedAt в будущем > DRAFT_FUTURE_SKEW_MS, v 2, topic 's8', text не строка → EMPTY и запись стёрта.
10. save пустого черновика → clear; save при tgUserId null → clear; текст 5000 знаков обрезан до 4000.
11. get, который не завершается → open отдаёт EMPTY через DRAFT_IO_TIMEOUT_MS; get с ошибкой → EMPTY без исключения.
12. createSupportDraftStore() в node → работает (память), put/get/clear проходят.
Цели: bash tools/check.sh miniapp. Только CI: полный прогон vitest и tsc.

## 10. Живые проверки (после выката бота и api)
Автор в Mini App: фаза app → «Помощь» → тема «Поддержка 1» → вопрос → «Отправить» → «Вопрос отправлен.»; в группе пост в теме этой темы (проверка bot-sup-1). Закрыть Mini App с недописанным вопросом, открыть → тема и текст на месте (IndexedDB в Telegram iOS/Android — по коду не проверить). Два вопроса подряд → «Слишком часто…». Миграций и бэкапа нет.

## 11. Запреты
- AGENT-BRIEF §3 целиком: без новых зависимостей, без логов initData и ПДн, без window.history, без dev-обходов.
- OnboardingFlow.test.ts, NO_STORAGE_FILES содержит ./App.tsx и ../api/client.ts: в их исходнике (нижний регистр, включая комментарии) нельзя: localstorage, sessionstorage, indexeddb, dexie, document.cookie, console., sendbeacon, pushstate, replacestate, location.hash, persist( ; в них и в drafts.ts нельзя: innerhtml, insertadjacenthtml, document.write. Значит в App.tsx нет слова indexeddb даже в комментарии; навигация — только useNavigate / navigate(-1), без window.history.
- drafts.ts (тот же тест): нельзя подстрок birth, console., localstorage, sessionstorage, document.cookie, dexie, email, city, gender, weight, wellbeing — в том числе в новой шапке (запрет ответов анкеты сформулировать без этих слов; city ловит и capacity).
- SupportScreen.tsx в NO_STORAGE_FILES НЕ добавлять (это правка готового теста). Вместо этого SupportScreen.test.ts сам проверяет исходник SupportScreen.tsx на те же два списка (свои массивы в своём тесте).
- Существующие экспорты и сигнатуры drafts.ts не менять: createDraftStore, createMemoryDraftStore, createSerialDraftStore, openDraft, saveDraft, finishDraft, parseStoredDraft (v2), sanitizeDraft, withTimeout, DRAFT_TTL_MS, DRAFT_FUTURE_SKEW_MS, EMPTY_DRAFT; тест «createDraftStore() → есть seal» должен остаться зелёным.
- SupportScreen.tsx пишет на устройство только через функции drafts.ts. Текст вопроса — не в лог, не в адрес, не в query.
- Меню не делать; кнопку в OnboardingFlow не ставить; тексты в text_registry не добавлять.

## 12. Критерии готовности
«Помощь» есть только в later и app; 8 тем; проверка текста как на сервере (минимум после trim, максимум по сырому тексту, кодовые точки); один op_id на попытку; черновик тема + текст, привязка к tg_user_id, 24 ч, стирание после 201; ошибки по 7.4; check miniapp зелёный; существующие тесты не менялись.

## 13. Оценка
Часы Автора ≈ 1 (КОДЕР: 2 ответа, 4 части пакета). Кредиты: 0 (Р0+).

## 14. РЕВЬЮЕР
Нет: initData, 18+, согласия, rate-limit, роли/GRANT и оплату задача не трогает.

## Задетые тесты (правило «Т»)
Нет — сверил ШТАБ по коду @1aeae18: ApiError в onbForm.test, startup.test, OnboardingFlow.test — 3 аргумента и проверка кодов, toEqual на ApiError нет; client.test.ts — только normalizeBaseUrl и buildUrl; тестов App и routes нет; drafts.test.ts состав ключей и хранилищ не сверяет. Риск — только запреты подстрок (раздел 11).

## Канон и решения
- (а) 04-onboarding §4.6 и YAML support_button: everywhere.
- (б) Противоречат Р-19 [Автор против канона → DECISIONS Р-19]; YAML уже в «Устарело» Р-19.
- (в) Правка 04 §4.6 — DOCS-пакет ШТАБа (bot-sup-1); в этой карточке правок канона нет.
- Открытый вопрос до 0-Б: текст вопроса хранится и на устройстве (IndexedDB, до 24 ч) — к юристу вместе с outbox.
