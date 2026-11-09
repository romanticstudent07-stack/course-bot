# miniapp-i3-1a — Mini App: экран onb.form (анкета онбординга)

## 1. Паспорт
- id: miniapp-i3-1a · PR: «feat(miniapp): экран onb.form, черновик только step (miniapp-i3-1a)» · ветка: feat/miniapp-i3-1a-form
- Режим: Агент Р1 · РЕВЬЮЕР: да (§14) · Зависит от: api-i3-2 (смержен; живые проверки — после выката api 10.11).
- Основа: docs/research/miniapp-i3-1.md (#186) §2–§7, решения ШТАБа З1/З2; код читан по 1ce76e2.
- Оценка: 750–900 кредитов (§13). Тесты сверх §9 не добавлять. Упал тест вне «Задетых тестов» — не чинить: «тест X вне списка» в ИТОГ и стоп.

## 2. Цель
Шаги после pid: offer → form → checkup (пока заглушка) → rules → finished, «Шаг N из 4». Экран onb.form один раз отправляет на сервер tz, пол, самочувствие и вес. Черновик на устройстве — только шаг: Draft = {step}, DRAFT_VERSION = 2; email и город с устройства убираются (Р-16). Возврат без черновика: GET form → анкета не отправлена → онбординг с оферты.

## 3. Решения Автора (дословно)
- Р-16 (DECISIONS): «Делаем: город → только tz (IANA), город не храним; пол; вопрос «самочувствие» (текст даст Автор); стартовые замеры — в таблицу Чек-Апа. ФИО, телефон, email не собираем, в черновике тоже.»
- Р-17 (research §2; cities-1 §3): «подсказки с 2 букв, до 10, рядом область, только выбор, «Моего города нет» → заглушка → 11 кнопок».
- 3А (research §2): «Подсказка города — две строки: город, под ним мелко область; для Москвы, Санкт-Петербурга, Севастополя — только город.» [Автор, канон проверен Р-17 (cities-1 §3) — вид не задан]

## 4. Выдержки архитектуры
- miniapp-screens §Онбординг (research §2): «onb.offer → onb.form → onb.checkup → onb.rules».
- 04 §4.4–4.5 (research §2): «Всё верно? [Да] [Исправить]», «Назад», «Шаг N из M».
- 04 §4.7 (ШТАБ по 1ce76e2): «доступ к дню 1.1 НЕ открывается… Доступ только после полного прохождения всех шагов»; Fail-safe блока 4: «Блокировка старта дня 1.1 без полностью пройденного онбординга (Q-95)».
- 04 §4.9 (ШТАБ по 1ce76e2): «Прогресс онбординга сохраняется в БД; продолжение с прерванного шага/вопроса».

## Канон и решения
(а) miniapp-screens §Онбординг; 04 §4.4, §4.5, §4.7, §4.9, Fail-safe; контракт onboarding/form/config и onboarding/form (DOCS №13 — docs/tasks/api-i3-2-docs13.md); cities-1 §3.
(б) 04 §4.1 шаг 4, §4.4 и miniapp-screens onb.form — против Р-16 (DECISIONS: «В каноне устарело»); 04 §4.4 «кнопки-города» — против Р-17; 04 §4.9 «в БД» — против черновика в IndexedDB: известное расхождение, на устройстве только step, анкета на сервере.
(в) В этой карточке правок канона нет: Р-17 — DOCS №14 (cities-1), Р-16 — правка ШТАБа; точный текст 04 окно КАРТОЧКИ не открывало — не проверено.
Метки решений (К-6): [Автор] — §3; [ШТАБ-тех по канону 04 §4.7, §4.9, Fail-safe] — возврат §7.4; [ШТАБ-тех] — остальное в §7 с меткой.

## 5. ЧТО ПРОЧИТАТЬ (Чтение Агента ≈ 128,5 КБ)
AGENT-BRIEF.md 17,1 · docs/decisions/DECISIONS.md 7,8 · эта карточка ≈ 10 · apps/miniapp/src/api/client.ts 10,7 · apps/miniapp/src/components/: App.tsx 6,8 · LaterSteps.tsx 13,6 · drafts.ts 13,7 · drafts.test.ts 17,6 · startup.ts 4,1 · startup.test.ts 6,1 · OnboardingFlow.test.ts 21,0.
OnboardingFlow.tsx не читать и не менять. Его экспорты (по использованию в LaterSteps.tsx, startup.ts): makeSubmitHandler(enabled, onOk) — onSubmit формы; pickText(texts, key); textsToMap(resp); textsErrorMessage(err); errorMessage(err): string — тексты 401 / 429 / 503 / сеть / прочее.

## 6. Файлы (11; ожидаемо ≈ 800 строк: код ≈ 450, тесты ≈ 350)
- Изменить: apps/miniapp/src/api/client.ts; apps/miniapp/src/components/LaterSteps.tsx, drafts.ts, App.tsx, startup.ts, OnboardingFlow.test.ts, drafts.test.ts, startup.test.ts.
- Создать: apps/miniapp/src/components/OnbForm.tsx (контейнер и вид OnbFormView), onbForm.ts (чистые функции и formReducer), onbForm.test.ts.
- Удалить: нет.

## 7. Контракт и поведение
### 7.1 API (DOCS №13 = docs/tasks/api-i3-2-docs13.md; в client.ts — 3 функции и типы)
- getFormConfig(): GET /miniapp/v1/onboarding/form/config → 200 {version, genders: ('male'|'female')[], wellbeing_question, wellbeing: [{code, text}], weight: {min, max, step}, timezones: [{tz, city}] (11 шт.), fallback_title, cities: [string, string, number][]} — [город, регион, i], i — индекс в timezones; 401, 429, 503.
- getForm(): GET /miniapp/v1/onboarding/form → 200 {submitted: boolean, created_at: string|null}; 401, 404 PARTICIPANT_NOT_FOUND, 429, 503. Только чтение, без X-Client-Op-Id.
- postForm(body, clientOpId): POST /miniapp/v1/onboarding/form + X-Client-Op-Id; тело ровно {tz, gender, wellbeing_code, weight_kg} → 200 {created_at}; повтор с тем же op_id → 200; 404; 409 RECONSENT_REQUIRED / ONBOARDING_FORM_EXISTS / IDEMPOTENCY_CONFLICT; 422 VALIDATION_ERROR; 401, 429, 503. Города в теле нет (Р-16).
### 7.2 Шаги и черновик [ШТАБ-тех, research Т-1, Т-2]
- drafts.ts: LATER_STEPS = ['offer', 'form', 'checkup', 'rules', 'finished']; Draft = {step}; EMPTY_DRAFT = {step: 'offer'}; DRAFT_VERSION = 2. Убрать CITY_OPTIONS, EMAIL_MAX_LENGTH, isCity и оба поля из sanitizeDraft, parseStoredDraft, StoredDraft. Запись v1 не проходит parseStoredDraft → очистка, как битая. TTL, очередь, seal, правило finished — как сейчас.
- В drafts.ts слов email, city, gender, weight, wellbeing нет нигде, и в комментариях тоже: тест сверяет весь исходник (Задетые тесты, п.8).
- LaterSteps.tsx: LATER_TEXT_KEYS = {offer, checkup, rules}; PROGRESS_STEPS = offer, form, checkup, rules → «Шаг N из 4». Убрать isEmailValid, canContinueEmail, isCityOption, действия setEmail / skipEmail / setCity и формы email и city.
- canGoNext: form и finished → false, прочие → true. Новое действие {type: 'formDone'}: только на form → checkup; 'next' на form состояние не меняет.
- LaterStepView: новый необязательный проп body (ReactNode); на form рисует прогресс, body и «Назад». Контейнер на form передаёт body = OnbForm (onDone → formDone, onRestart). Новый проп LaterSteps: onRestart: () => void. checkup в этой задаче — прежняя заглушка (текст и «Далее»).
### 7.3 Экран onb.form (OnbForm.tsx, onbForm.ts)
- Открытие: getFormConfig() и getForm() параллельно, пока ждём — «Загрузка…». submitted = true → onDone() сразу. Ошибка → errorMessage(err) и «Повторить» (оба запроса заново); 404 или 409 RECONSENT_REQUIRED → экран restart.
- Город [Р-17, 3А; ШТАБ-тех, Т-4]: поле ввода; normalizeQuery — нижний регистр, ё → е, без крайних пробелов; suggestCities — с 2 символов, совпадение с начала названия, до 10, в порядке cities. Подсказка — две строки (город; ниже мелко регион); регион = город → одна строка. Выбор → tz = timezones[i].tz; правка текста сбрасывает выбор.
- Кнопка «Моего города нет» → fallback_title и 11 кнопок timezones (подпись — city); выбор → tz. cities — один раз из config, только в памяти (Т-9).
- Пол: 2 кнопки по genders, подписи «Заглушка: пол male» / «Заглушка: пол female». Самочувствие: wellbeing_question и кнопки wellbeing[].text (выбор — code).
- Вес [ШТАБ-тех, Т-5]: поле inputMode="decimal"; parseWeight — запятая → точка, не больше 1 знака после точки, min ≤ x ≤ max из config, иначе null.
- «Далее» активна, когда заданы tz, пол, самочувствие и вес → экран «Заглушка: всё верно?» со сводкой и кнопками [Да] [Исправить] (04 §4.4). «Исправить» → поля, значения сохранены.
- «Да»: op_id = newClientOpId() при первом нажатии; живёт до 200 или до «Исправить»; повтор после ошибки — с тем же op_id (по коду client.ts: «повтор после ошибки уходит с тем же id (D-17)»). Пока запрос идёт, «Да» неактивна: двойное нажатие — один POST.
- Ответ POST (formErrorAction): 200 → onDone(); 409 ONBOARDING_FORM_EXISTS → onDone(); 409 IDEMPOTENCY_CONFLICT → новый op_id и «Повторить» [ШТАБ-тех]; 404 или 409 RECONSENT_REQUIRED → restart; 422 → «Заглушка: проверьте ответы» и «Исправить»; прочее (401, 429, 503, сеть) → errorMessage(err) и «Повторить».
- Экран restart: «Заглушка: нужно открыть приложение заново» и «Повторить» → onRestart() (App → checking → GET status → reconsent → OnboardingFlow). Образца для 409 RECONSENT_REQUIRED в client.ts и LaterSteps.tsx нет → [ШТАБ-тех].
- Значения анкеты — только state React: не в черновик, не в лог (console не использовать), не в URL [Р-16, 2А].
### 7.4 Возврат (App.tsx, startup.ts) [ШТАБ-тех по канону 04 §4.7, §4.9, Fail-safe]
- routeByDraft: openDraft → незаконченный черновик → later (как сейчас). Черновика нет, finished или ошибка хранилища → getForm(): submitted = true → app; false → later с оферты. Ошибка GET form (любая, и 404 / 409) → start-error с этой ошибкой, routingRef и routing сбросить; «Повторить» → checking.
- startup.ts: afterNumber(draft: Draft | null, formSubmitted: boolean): незаконченный черновик → 'later'; иначе formSubmitted ? 'app' : 'later'.
- App: LaterSteps получает onRestart = retry (со сбросом routingRef).

## 8. БД
Нет.

## 9. Тесты (onbForm.test.ts: vitest, environment node, без DOM)
1. normalizeQuery: регистр, ё → е, крайние пробелы.
2. suggestCities: 1 символ → []; совпадение только с начала; не больше 10; порядок cities.
3. cityLines: регион = город → одна строка; иначе две.
4. parseWeight: «72,5» → 72.5; «72.55» → null; меньше min и больше max → null; «abc» и пусто → null.
5. formReducer: правка текста сбрасывает tz; «Моего города нет» + выбор ставит tz; без одного поля «всё верно?» не открывается; «Исправить» сохраняет значения.
6. buildFormBody: ключи ровно gender, tz, weight_kg, wellbeing_code (города нет).
7. formErrorAction: 409 ONBOARDING_FORM_EXISTS → done; 409 IDEMPOTENCY_CONFLICT → conflict; 409 RECONSENT_REQUIRED и 404 → restart; 422 → invalid; 503 и TypeError → retry.
8. OnbFormView (renderToStaticMarkup): экран подтверждения — «Да» и «Исправить»; без веса «Далее» disabled.
9. Исходники OnbForm.tsx и onbForm.ts: нет 'console.'.
Быстрые тесты — цели tools/check.sh для Mini App по AGENT-BRIEF.md; остальное — CI.

## Задетые тесты (правило «Т»; чинить только этот список)
OnboardingFlow.test.ts:
1. Импорт из LaterSteps.tsx: убрать canContinueEmail и canGoNext (после п.5 не используются; лишний импорт ломает tsc).
2. Тест LATER_TEXT_KEY_LIST: ровно 3 ключа — legal.offer, B4.onb_checkup, B4.onb_rules.
3. «Порядок шагов»: offer →(next) form →(next) form →(formDone) checkup →(next) rules →(next) finished.
4. Тест «Назад»: at('checkup') → 'form', at('form') → 'offer'; строку finished → rules оставить.
5. Удалить тесты «email: …», «city: …» и весь describe «формы email и city, Enter».
6. Индикатор: offer → «Шаг 1 из 4», rules → «Шаг 4 из 4», renderLater(at('checkup')) → «Шаг 3 из 4».
7. NO_STORAGE_FILES: добавить './OnbForm.tsx' и './onbForm.ts'.
8. «drafts.ts: нет даты рождения и console»: в список запретов добавить 'email', 'city', 'gender', 'weight', 'wellbeing'.
9. Литералы Draft с полями email / city (хелперы, если есть) → только step (иначе tsc).
drafts.test.ts:
10. Импорт: убрать CITY_OPTIONS и EMAIL_MAX_LENGTH. DRAFT = { step: 'checkup' }.
11. validStored, STORED и все литералы store.put / get: v: 2, без email и city.
12. Тест ключей черновика: ровно ['savedAt', 'step', 'tgUserId', 'v'].
13. Список «плохих» записей: убрать {v: 2}, строки с email, city: 'Атлантида'; добавить {v: 1}, {step: 'email'}, {step: 'city'}.
14. sanitizeDraft: ожидаем {step: 'offer'}.
15. Тест seal и «saveDraft перед finishDraft»: city: CITY_OPTIONS[1] → step: 'rules'. Из названий тестов убрать «email / город».
16. Новый тест: запись v1 с email и city → openDraft = null, хранилище пусто.
startup.test.ts:
17. Хелпер draft → ({ step }); draft('email') → draft('form').
18. afterNumber: «черновика нет» → afterNumber(null, true) = 'app' и новый afterNumber(null, false) = 'later'; «step finished» → afterNumber(draft('finished'), true) = 'app'; «незаконченный шаг» → afterNumber(draft('form'), false) и (draft('offer'), false) = 'later'.

## 10. Живые проверки (после мержа и выката api 10.11 и Mini App)
- А4 (новый, доступ выдан): offer → form; подсказка от 2 букв, регион второй строкой, Москва — одной; «Моего города нет» → 11 кнопок; «Всё верно?» → «Да» → checkup. Двойное «Да» → в журнале сервера один POST (значений полей в журнале нет).
- А4: закрыть и открыть → номер → «Продолжить»: черновик есть → шаг checkup; черновика нет → GET form submitted = true → курс. Анкета второй раз не открывается.
- IndexedDB (DevTools): в записи только v, tgUserId, savedAt, step.
- А1–А3 (по коду App.tsx, startup.ts): returning → номер → «Продолжить» → черновика нет → GET form. Если анкеты нет (эндпоинт новый; по БД не проверено) → онбординг с оферты; экран дня (у А1 — день 4) недоступен до «Перейти к курсу» (04 §4.7).
- Шаги онбординга Mini App дневных запросов (day/*) не шлют (по коду client.ts, LaterSteps.tsx) → отметки не меняются. Жизни (серверный счёт) и действие tz_set у участника с идущим курсом — по коду Mini App не видно, не проверено → вопрос ШТАБу.
- Вопрос ШТАБу (до живой проверки): А1 (курс идёт, день 4) после выката попадёт в онбординг с оферты и отправит анкету; docs13: «событие tz_set (проектор пишет participant_state.tz до начала первого дня; INV-1)». Что сервер делает с tz_set после начала курса и не снимаются ли жизни, пока А1 в онбординге? Проверять на А1 или только на А4?

## 11. Запреты
- AGENT-BRIEF §3. docs/architecture/** не открывать. OnboardingFlow.tsx не менять. Новых зависимостей нет; ci.yml не трогать.
- Email, город, пол, самочувствие, вес — не на устройство (IndexedDB, localStorage, cookie), не в лог, не в URL (Р-16).
- Тексты экранов — только «Заглушка: …» (репо публичный). innerHTML и аналоги — нет (R342).
- Тесты сверх §9 не добавлять; тесты вне «Задетых тестов» не чинить.

## 12. Готово, когда
- check.sh зелёный, CI 7/7; задетые тесты исправлены ровно по списку; 11 файлов §6; отличия от карточки — в описании PR.

## 13. Оценка
Часы Автора ≈ 0,5. Кредиты 750–900: ≈ 800 строк, 11 файлов (3 задетых тест-файла); поправка по уроку api-i3-1 (+1204 строки → 905 кредитов).

## 14. РЕВЬЮЕР: да
Пол, самочувствие, вес (ПДн) и drafts.ts (что пишется на устройство). Смотреть: тело POST, запись черновика, отсутствие значений в логах и URL.
