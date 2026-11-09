# miniapp-i3-1 — исследование: экраны onb.form и onb.checkup в Mini App

Hash: a56b172 (main). Окно ИССЛЕДОВАНИЕ, З1, 09.11. Карточки пишет окно КАРТОЧКИ по этому файлу.

## 1. Как сейчас (по коду @a56b172)
- LaterSteps.tsx: шаги offer → email → city → checkup → rules → finished (LATER_STEPS в drafts.ts). email — необязательное поле; city — 3 кнопки CITY_OPTIONS; checkup — текст B4.onb_checkup и «Далее». На сервер ничего не уходит.
- drafts.ts: Draft = {step, email, city}, DRAFT_VERSION = 1, IndexedDB, TTL 24 ч. Долг iter3-2 Л1 п.(4) подтверждён: email в черновике (тип Draft, sanitizeDraft, parseStoredDraft, EMAIL_MAX_LENGTH) — против Р-16. Город в черновике — тоже против Р-16.
- App.tsx: returning → номер → routeByDraft: есть черновик моложе 24 ч → later, иначе → app. Сервер про анкету не спрашивают: черновик пропал — участник идёт в курс без анкеты.
- OnboardingFlow.tsx (до pid) не меняется; LaterSteps берёт из него makeSubmitHandler, pickText, textsErrorMessage, textsToMap.
- client.ts: функций анкеты и Чек-Апа нет; apiRequest, ApiError, newClientOpId готовы.
- checkup.py: GET /checkup/config (без БД) → {version, scale, blocks, questions, zones [id, title, text], disclaimer}; POST /checkup/submit {occasion: "onboarding", answers: 15 целых 0–3} + X-Client-Op-Id → 200 {zone, config_version, created_at}; 404 PARTICIPANT_NOT_FOUND; 409 RECONSENT_REQUIRED / IDEMPOTENCY_CONFLICT; 422; 503. GET статуса Чек-Апа НЕТ (Б-1).
- Анкета (api-i3-2-docs13.md): GET form/config → {version, genders, wellbeing_question, wellbeing [code, text], weight {min, max, step}, timezones [11 × {tz, city}], fallback_title, cities [[город, регион, i]]}, i — индекс в timezones; GET form → {submitted, created_at}; POST form {tz, gender, wellbeing_code, weight_kg} + X-Client-Op-Id → 200 {created_at}; 409 RECONSENT_REQUIRED / ONBOARDING_FORM_EXISTS / IDEMPOTENCY_CONFLICT; 422 VALIDATION_ERROR.
- form.json: нет genders и cities, их собирает роутер из cities.csv. Роутер анкеты не читал — не проверено.
- cities-1 §7: region готов к показу («Свердловская область», «Республика Адыгея»); у городов федерального значения region = city.

## 2. Канон и решения
- miniapp-screens §Онбординг: onb.offer → onb.form → onb.checkup → onb.rules; onb.form — пояс по городу, пол, самочувствие, вес; ФИО, телефона, email нет (Р-16).
- 04 §4.4–4.5: экран «Всё верно? [Да] [Исправить]»; «Назад»; «Шаг N из M».
- 05 §5.2–5.4, Fail-safe: вводный текст; вопросы по одному, кнопки 0–3; заголовок блока перед его вопросами; «Вопрос N из 15»; «Исправить»; результат — зона и расшифровка, балла нет; «сохранение прогресса опроса».
- 04 §4.9: «прогресс онбординга сохраняется в БД» — в коде черновик на устройстве (старое расхождение).
- Р-16: только tz, пол, самочувствие, вес; ФИО, телефон, email не собираем, в черновике тоже. Р-17 (cities-1 §3): подсказки с 2 букв, до 10, рядом область, засчитывается только выбор, «Моего города нет» → заглушка → 11 кнопок.
- Новых правок канона нет; 04 §4.4 «кнопки-города» — DOCS №14 из cities-1 (после записи Р-17 в DECISIONS).

## 3. Нарезка: 2 карточки, порядок А → Б
- А miniapp-i3-1a (onb.form). Изменить: apps/miniapp/src/api/client.ts (+getFormConfig, getForm, postForm, типы); components/LaterSteps.tsx (email и city → form, прогресс из 4); components/drafts.ts (Draft = {step}); components/App.tsx (GET form в routeByDraft); components/startup.ts (если меняется afterNumber); тесты §5. Создать: components/OnbForm.tsx (город с подсказками, 11 запасных кнопок, пол, самочувствие, вес, подтверждение, отправка); components/onbForm.ts (чистые функции: подсказки, вес, тело POST); components/onbForm.test.ts. Около 10 файлов, около 550 строк.
- Б miniapp-i3-1b (onb.checkup). Изменить: client.ts (+getCheckupConfig, postCheckupSubmit, типы); LaterSteps.tsx (checkup → экран); OnboardingFlow.test.ts. Создать: components/Checkup.tsx; components/checkup.ts (порядок, заголовки блоков, тело POST); components/checkup.test.ts. Около 6 файлов, около 400 строк.
- Почему 2: вместе около 13 файлов и 900 строк — больше лимита DESIGNER «Размеры». А первой: снимает долг Р-16, а Б опирается на новые шаги. Параллельно нельзя: общие LaterSteps.tsx, client.ts, OnboardingFlow.test.ts.

## 4. Технические решения (К-5, ПРОЕКТИРОВЩИК)
- Т-1 Черновик = только step; DRAFT_VERSION 1 → 2: старые записи с email и city не пройдут parseStoredDraft, и readDraft удалит их при первом открытии. Поля анкеты и ответы Чек-Апа живут только в памяти React.
- Т-2 Шаги: offer → form → checkup → rules → finished; «Шаг N из 4».
- Т-3 «Анкета уже есть»: на шаге form LaterSteps вызывает GET form, submitted=true → checkup. В App.routeByDraft: GET form; submitted=false → later с шага form. Ошибка GET form → экран «Повторить».
- Т-4 Подсказки: нижний регистр, ё → е, обрезка пробелов; совпадение с начала названия; с 2 символов; до 10, в порядке файла. Выбор → tz = timezones[i].tz. Правка текста после выбора сбрасывает выбор.
- Т-5 Вес: запятая → точка; не больше 1 знака после точки; min ≤ x ≤ max из config; не округляем.
- Т-6 POST form: один op_id на экран (ref), повтор после ошибки — с ним же (D-17). 409 ONBOARDING_FORM_EXISTS → как успех, шаг checkup. 409 RECONSENT_REQUIRED или 404 → заглушка и «Открыть заново» → App снова checking (новый проп onRestart). 422 → «Проверьте ответы», назад к вводу.
- Т-7 Чек-Ап: один op_id на прохождение; 409 и 404 — как в Т-6; после 200 — экран зоны (title и text из config по zone, disclaimer), «Далее» → rules.
- Т-8 Тексты — заглушки «Заглушка: …», подписи пола тоже. B4.onb_email и B4.onb_city убрать из LATER_TEXT_KEYS; есть ли они в seed texts — не проверено, seed не трогаем.
- Т-9 cities (около 1 100 строк) — один раз с form/config, держим в памяти.
- Т-10 РЕВЬЮЕР: А — да (п.14 прямо не требует; по указанию ШТАБа: пол, самочувствие и вес — данные о здоровье, плюс меняется хранилище drafts.ts; проверить, что на устройство и в лог уходит только step). Б — нет: только память, а новый файл покрывает тест D-19.

## 5. Задетые тесты (правило «Т»)
OnboardingFlow.test.ts:
- А: убрать импорт canContinueEmail;
- А: «LATER_TEXT_KEY_LIST — 5 ключей» → список без B4.onb_email и B4.onb_city;
- А: «LaterSteps: порядок шагов» → offer, form, checkup, rules, finished, без setCity;
- А: удалить тесты «email: …» и «city: только город из списка»;
- А: «индикатор прогресса» → «Шаг 1 из 4», шаг checkup — «Шаг 3 из 4»;
- А: удалить блок «формы email и city, Enter» (форма анкеты — в onbForm.test.ts);
- А: NO_STORAGE_FILES + './OnbForm.tsx', './onbForm.ts'; Б: + './Checkup.tsx', './checkup.ts';
- А: «drafts.ts: нет даты рождения» — добавить запреты 'email', 'city', 'gender', 'weight', 'wellbeing';
- Б: «индикатор прогресса» — сверить, если меняется вид шага checkup.
- drafts.test.ts (17,6 КБ) — задет (email, city, CITY_OPTIONS, EMAIL_MAX_LENGTH, DRAFT_VERSION); не читал, точные правки — окно КАРТОЧКИ.
- startup.test.ts (6,1 КБ) и startup.ts (4,1 КБ) — задеты, если меняется afterNumber или поля Draft; не читал.
- dayMarks.test.ts, dayScreen.test.ts: client.ts только расширяется — по виду правки не задеты (не читал).

## 6. Блокеры и риски
- Б-1 Нет серверного признака «Чек-Ап пройден» → вопрос 1.
- Р-1 Повтор POST /checkup/submit с новым op_id: будет ли вторая строка onboarding — уникальность в миграции не проверял.
- Р-2 Живые проверки — только после выката api 10.11.
- Р-3 Вид cities в config — по docs13; роутер не читал.

## 7. Вопросы Автору (К-4)
1. Как Mini App узнаёт, что Чек-Ап уже пройден?
Канон: проверено 05 §Fail-safe, 04 §4.9, checkup.py — противоречит: канон «прогресс онбординга сохраняется в БД», в API признака нет.
А — маленькая API-задача до Б: GET /checkup/status или поле в GET form. Плюс: решает сервер, повторов нет. Минус: ещё одна задача.
Б — только черновик: черновик пропал, анкета есть → Чек-Ап снова. Плюс: без API. Минус: возможна вторая запись.
В — черновик пропал → считать пройденным. Плюс: просто. Минус: Чек-Ап можно пропустить.
Мнение: А (Р0+, параллельно с карточкой А).
2. Прогресс внутри Чек-Апа, если приложение закрыли.
Канон: проверено 05 §5.2, §Fail-safe — «продолжение с прерванного вопроса»; DECISIONS молчит; противоречит коду: сервер прогресс не хранит.
А — ответы только в памяти, после закрытия — с вопроса 1. Плюс: ничего о здоровье на устройстве. Минус: 15 вопросов заново.
Б — ответы в черновике IndexedDB на 24 ч. Плюс: продолжение. Минус: данные о здоровье на устройстве.
Мнение: А.
3. Вид подсказки города с областью (долг «miniapp-1 вид регионов»).
Канон: проверено 04 §4.4, miniapp-screens onb.form, DECISIONS Р-16, Р-17 (cities-1 §3) — молчит.
А — две строки: город, ниже мелко область. Б — «Город, Область». В — «Город (Область)». Город = регион → только город (К-5).
Мнение: А.

## 8. Прочитано (@a56b172, КБ)
База: DESIGNER.md 23,1; STATE.md 18,6; AGENT-BRIEF.md 17,1; process/README.md 8,9; DECISIONS.md 7,8; CANON-CHECK.md 4,9. Mini App: OnboardingFlow.tsx 16,9; OnboardingFlow.test.ts 21,0; LaterSteps.tsx 13,6; client.ts 10,7; App.tsx 6,8; routes.tsx 0,4. API: api-i3-2-docs13.md 6,4; checkup.py 11,2; form.json 1,3; checkup.v1.json 3,0. Канон: miniapp-screens.md 5,5; cities-1.md 9,3. Сверх списка: drafts.ts 13,7 (черновик и email); 04-onboarding.md 13,4 (§4.4–4.9); 05-checkup.md 7,6 (экран Чек-Апа).
Надо дочитать окну КАРТОЧКИ: drafts.test.ts, startup.ts, startup.test.ts (§5); роутер анкеты api (Р-3).
