# miniapp-i3-1b — Mini App: экран onb.checkup (Чек-Ап онбординга)

## 1. Паспорт
- id: miniapp-i3-1b · PR: «feat(miniapp): экран onb.checkup — Чек-Ап онбординга (miniapp-i3-1b)» · ветка: feat/miniapp-i3-1b-checkup
- Режим: Агент Р1 · РЕВЬЮЕР: нет (§14).
- Зависит от: мерж api-i3-4 и miniapp-i3-1a; запись Р-18 в DECISIONS. Карточка впрок: до этого Агента не запускать.
- Основа: docs/research/miniapp-i3-1.md (#186) §2–§7, указания ШТАБа. «Как сейчас» ниже — по карточке miniapp-i3-1a; ШТАБ сверяет с main после её мержа и даёт hash.
- Оценка: 550–700 кредитов (§13). Тесты сверх §9 не добавлять. Упал тест вне «Задетых тестов» — не чинить: «тест X вне списка» в ИТОГ и стоп.

## 2. Цель
Шаг checkup вместо заглушки: 15 вопросов по одному, только кнопки 0–3, «Вопрос N из 15», «Исправить», отправка POST /checkup/submit, итог — зона и дисклеймер (балла нет). Ответы — только в памяти экрана: закрыл приложение — опрос с вопроса 1 (2А, Р-18). «Пройден ли Чек-Ап» решает сервер (GET /checkup/status, 1А).

## 3. Решения Автора (дословно)
- 1А (research §2): «Признак «Чек-Ап пройден» даёт сервер.» [Автор, канон проверен 04 §4.9 «Прогресс онбординга сохраняется в БД»]
- 2А (research §2): «Ответы Чек-Апа — только в памяти экрана; закрыл приложение → с вопроса 1.» [Автор против канона 05 Fail-safe: «Сохранение прогресса опроса (продолжение с прерванного вопроса)»] Действует после записи Р-18 в DECISIONS.
- Р-16 (DECISIONS): «ФИО, телефон, email не собираем, в черновике тоже.» — на устройстве только step.

## 4. Выдержки архитектуры
- 05 Fail-safe (ШТАБ, по a56b172, дословно): «Только кнопки 0–3 (никакого ручного ввода баллов). Сохранение прогресса опроса (продолжение с прерванного вопроса). Кнопка «Исправить». Индикатор «Вопрос N из 15». Идемпотентность кнопок.» Второе предложение перекрыто Р-18. В yaml блока 5 ключа прогресса нет.
- 05 §5.2–5.4 (research §2): «вопросы по одному, кнопки 0–3, заголовок блока, «Вопрос N из 15», результат — зона и текст, балла нет».
- 04 §4.7, §4.9, Fail-safe блока 4 (ШТАБ по 1ce76e2) — как в miniapp-i3-1a §4.
- apps/api/config/checkup/checkup.v1.json: version «v1-stub», scale 0–3, 4 блока (id, title), 15 вопросов q01–q15 (block 1–4), zones (id, title, text), disclaimer; все тексты — «Заглушка: …».

## Канон и решения
(а) 05 §5.2–5.4, Fail-safe; 04 §4.7, §4.9, Fail-safe блока 4; контракт /checkup/config, /checkup/submit, /checkup/status (DOCS-пакет ШТАБа к api-i3-4).
(б) 05 Fail-safe «Сохранение прогресса опроса (продолжение с прерванного вопроса).» — против Р-18 (2А).
(в) DOCS · architecture/05-checkup.md · найди: «Сохранение прогресса опроса (продолжение с прерванного вопроса).» · замени: «Прогресс опроса не сохраняется: закрыл приложение — опрос с вопроса 1 (Р-18).» Применять после записи Р-18; PR DOCS и sync — до промпта Агенту. Остальное в 05 не трогать.
Метки (К-6): [Автор] — §3; [ШТАБ-тех по канону 04 §4.7, §4.9, Fail-safe] — возврат §7.4; [ШТАБ-тех, по коду 0014: уникальность только (pid, client_op_id)] — 409 CHECKUP_EXISTS; [ШТАБ-тех] — остальное с меткой.

## 5. ЧТО ПРОЧИТАТЬ (Чтение Агента ≈ 98 КБ; размеры — после мержа А, уточняет ШТАБ)
AGENT-BRIEF.md 17,1 · docs/decisions/DECISIONS.md ≈ 8,5 · эта карточка ≈ 9 · apps/miniapp/src/api/client.ts ≈ 12,5 · apps/miniapp/src/components/: App.tsx ≈ 7,5 · LaterSteps.tsx ≈ 11 · startup.ts ≈ 4,3 · startup.test.ts ≈ 6,5 · OnboardingFlow.test.ts ≈ 19 · apps/api/config/checkup/checkup.v1.json 3,0.
OnboardingFlow.tsx не читать и не менять; экспорты — как в miniapp-i3-1a §5 (errorMessage(err): string и др.).

## 6. Файлы (9; ожидаемо ≈ 600 строк: код ≈ 330, тесты ≈ 270)
- Изменить: apps/miniapp/src/api/client.ts; apps/miniapp/src/components/LaterSteps.tsx, App.tsx, startup.ts, OnboardingFlow.test.ts, startup.test.ts.
- Создать: apps/miniapp/src/components/Checkup.tsx (контейнер и вид CheckupQuestionView), checkup.ts (чистые функции и checkupReducer), checkup.test.ts.
- Удалить: нет. drafts.ts не меняется.

## 7. Контракт и поведение
### 7.1 API (в client.ts — 3 функции и типы)
- getCheckupConfig(): GET /miniapp/v1/checkup/config → 200 {version, scale: {min, max}, blocks: [{id, title}], questions: [{id, block, text}], zones: [{id, title, text}], disclaimer} (research §1, checkup.py).
- getCheckupStatus(): GET /miniapp/v1/checkup/status → 200 {completed: boolean, created_at: string|null}; 401, 404 PARTICIPANT_NOT_FOUND, 429, 503. Только чтение, без X-Client-Op-Id [контракт api-i3-4, ШТАБ].
- postCheckupSubmit(body, clientOpId): POST /miniapp/v1/checkup/submit + X-Client-Op-Id; тело {occasion: 'onboarding', answers: 15 целых 0–3} → 200 {zone, config_version, created_at}; 404 PARTICIPANT_NOT_FOUND; 409 RECONSENT_REQUIRED / IDEMPOTENCY_CONFLICT / CHECKUP_EXISTS (Чек-Ап онбординга уже есть, новый op_id; api-i3-4); 422; 401, 429, 503.
### 7.2 Шаги (LaterSteps.tsx)
- Новое действие {type: 'checkupDone'}: только на checkup → rules; 'next' на checkup состояние не меняет; canGoNext: checkup → false.
- На checkup контейнер передаёт в body (проп из А) Checkup: intro = текст B4.onb_checkup, onDone → checkupDone, onRestart. LATER_TEXT_KEYS не меняются.
- Новый проп LaterSteps initialStep?: LaterStep — шаг старта, когда черновика нет (по умолчанию offer).
### 7.3 Экран onb.checkup (Checkup.tsx, checkup.ts)
- Открытие: getCheckupConfig() и getCheckupStatus() параллельно, «Загрузка…». completed = true → onDone() сразу. Ошибка → errorMessage(err) и «Повторить»; 404 или 409 RECONSENT_REQUIRED → экран restart (как в miniapp-i3-1a §7.3) [ШТАБ-тех].
- Вопрос по одному: над ним title блока (по question.block); «Вопрос N из M», M = questions.length (в конфиге 15); 4 кнопки от scale.min до scale.max (0–3), ввода с клавиатуры нет. Нажатие → ответ и следующий вопрос.
- Идемпотентность кнопок: действие несёт номер вопроса {type: 'answer', index, value}; index ≠ текущему → игнор (двойное нажатие не перескакивает вопрос).
- «Исправить» (с вопроса 2 и на экране отправки) → предыдущий вопрос, прежний ответ отмечен (aria-pressed и «✓»); новый ответ заменяет прежний [ШТАБ-тех].
- После последнего вопроса — экран «Заглушка: ответы готовы» с [Отправить] [Исправить] [ШТАБ-тех].
- «Отправить»: один op_id на прохождение (newClientOpId() при первом нажатии); повтор после ошибки — с тем же; «Исправить» после неудачной отправки → новый op_id (тело уже другое) [ШТАБ-тех]. Пока запрос идёт, кнопка неактивна.
- Ответ (checkupErrorAction): 200 → итог: title и text зоны по zone из config (не нашли → «Заглушка: результат сохранён»), disclaimer, «Далее» → onDone(); балла нет. 409 CHECKUP_EXISTS → onDone() («уже пройден → дальше»). 409 IDEMPOTENCY_CONFLICT → новый op_id и «Повторить». 404 или 409 RECONSENT_REQUIRED → restart. 422 → «Заглушка: проверьте ответы» и «Исправить». Прочее (401, 429, 503, сеть) → errorMessage(err) и «Повторить».
- Ответы и зона — только state React: не в черновик, не в лог (console не использовать), не в URL [2А, Р-16]. Закрыл приложение → черновик step = checkup → опрос с вопроса 1.
### 7.4 Возврат (App.tsx, startup.ts) [ШТАБ-тех по канону 04 §4.7, §4.9, Fail-safe]
- routeByDraft: незаконченный черновик → later (как сейчас). Черновика нет → getForm(): false → later с оферты; true → getCheckupStatus(): completed → app, иначе later с initialStep 'checkup'. Ошибка любого GET → start-error, сброс routingRef и routing.
- startup.ts: AfterNumber = 'later' | 'checkup' | 'app'; afterNumber(draft, formSubmitted: boolean, checkupCompleted: boolean) — третий аргумент обязательный: незаконченный черновик → 'later'; !formSubmitted → 'later'; !checkupCompleted → 'checkup'; иначе 'app'. App: 'checkup' → phase later + initialStep 'checkup'. GET checkup/status — только при formSubmitted = true.

## 8. БД
Нет.

## 9. Тесты (checkup.test.ts: vitest, environment node, без DOM)
1. checkupReducer answer: ответ записан, индекс +1; answer со старым index — без изменений.
2. fix: индекс −1, прежний ответ сохранён; на первом вопросе — без изменений.
3. Новый ответ после fix заменяет прежний, остальные ответы сохранены.
4. questionLabel: «Вопрос 1 из 15», «Вопрос 15 из 15».
5. blockTitle: title по question.block.
6. buildSubmitBody: {occasion: 'onboarding', answers} — 15 целых 0–3; ответов меньше 15 → null.
7. checkupErrorAction: 409 CHECKUP_EXISTS → done; 409 IDEMPOTENCY_CONFLICT → conflict; 409 RECONSENT_REQUIRED и 404 → restart; 422 → invalid; 503 и TypeError → retry.
8. zoneView: zone из config → title и text; неизвестная zone → заглушка; числа баллов в выводе нет.
9. CheckupQuestionView (renderToStaticMarkup): 4 кнопки 0–3, «Вопрос N из 15», отмеченный ответ.
10. Исходники Checkup.tsx и checkup.ts: нет 'console.'.
Быстрые тесты — цели tools/check.sh для Mini App по AGENT-BRIEF.md; остальное — CI.

## Задетые тесты (правило «Т»; чинить только этот список)
OnboardingFlow.test.ts:
1. NO_STORAGE_FILES: добавить './Checkup.tsx' и './checkup.ts'.
2. «Порядок шагов»: на checkup (next) → остаётся checkup; (checkupDone) → rules; (next) → finished.
startup.test.ts:
3. afterNumber — все вызовы с тремя аргументами: (null, false, false) = 'later'; (null, true, false) = 'checkup'; (null, true, true) = 'app'; (draft('finished'), true, true) = 'app'; (draft('form'), false, false) и (draft('offer'), false, false) = 'later'.
drafts.test.ts — не ожидается (drafts.ts не меняется).

## 10. Живые проверки (после мержа и выката)
- А4 после анкеты: checkup → заголовок блока, «Вопрос N из 15», только кнопки 0–3; двойное нажатие → вперёд на один вопрос; «Исправить» → прежний ответ отмечен.
- А4: закрыть на вопросе 7 и открыть → опрос с вопроса 1. Пройти → «Отправить» → зона и дисклеймер, балла нет → rules. Открыть снова → status completed → Чек-Ап не повторяется.
- Журнал сервера: один 200 на submit; ответов и зоны в журнале Mini App нет.
- А1–А3: как в miniapp-i3-1a §10; дополнительно анкета отправлена, Чек-Апа нет → шаг checkup. Ответ ШТАБа на вопрос из miniapp-i3-1a §10 — до этой проверки.

## 11. Запреты
- AGENT-BRIEF §3. docs/architecture/** не открывать. OnboardingFlow.tsx и drafts.ts не менять. Новых зависимостей нет; ci.yml не трогать.
- Ответы Чек-Апа и зона — не на устройство, не в лог, не в URL (2А). Ручного ввода баллов нет (05 Fail-safe).
- Тексты экранов — только «Заглушка: …». innerHTML и аналоги — нет (R342).
- Тесты сверх §9 не добавлять; тесты вне «Задетых тестов» не чинить.

## 12. Готово, когда
- check.sh зелёный, CI 7/7; задетые тесты исправлены ровно по списку; 9 файлов §6; отличия от карточки — в описании PR.

## 13. Оценка
Часы Автора ≈ 0,5. Кредиты 550–700: ≈ 600 строк, 9 файлов (2 задетых тест-файла).

## 14. РЕВЬЮЕР: нет
research Т-10: ответы хранит только сервер, drafts.ts не меняется, initData / согласия / rate-limit не трогаются.
