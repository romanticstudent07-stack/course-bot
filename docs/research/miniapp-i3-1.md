# miniapp-i3-1 — исследование: экраны onb.form и onb.checkup в Mini App

Hash: a56b172 (main). Окно ИССЛЕДОВАНИЕ, З2 (ответы Автора и ШТАБа), 09.11. Карточки пишет окно КАРТОЧКИ по этому файлу.

## 1. Как сейчас (по коду @a56b172)
- LaterSteps.tsx: шаги offer → email → city → checkup → rules → finished (LATER_STEPS в drafts.ts); email — необязательное поле, city — 3 кнопки CITY_OPTIONS, checkup — текст и «Далее». На сервер ничего не уходит.
- drafts.ts: Draft = {step, email, city}, DRAFT_VERSION = 1, IndexedDB, TTL 24 ч. Долг iter3-2 Л1 п.(4) подтверждён: email в черновике (тип Draft, sanitizeDraft, parseStoredDraft, EMAIL_MAX_LENGTH) — против Р-16. Город — тоже против Р-16.
- App.tsx: returning → номер → routeByDraft: черновик моложе 24 ч → later, иначе → app. Сервер про анкету не спрашивают.
- OnboardingFlow.tsx (до pid) не меняется.
- client.ts: функций анкеты и Чек-Апа нет; apiRequest, ApiError, newClientOpId готовы.
- checkup.py: GET /checkup/config → {version, scale, blocks, questions, zones [id, title, text], disclaimer}; POST /checkup/submit {occasion: "onboarding", answers: 15 целых 0–3} + X-Client-Op-Id → 200 {zone, config_version, created_at}; 404 PARTICIPANT_NOT_FOUND; 409 RECONSENT_REQUIRED / IDEMPOTENCY_CONFLICT; 422; 503. Защита от повтора — только тот же op_id (ON CONFLICT (pid, client_op_id)). Признака «Чек-Ап пройден» нет → api-i3-4 (§4).
- Анкета (api-i3-2-docs13.md): GET form/config → {version, genders, wellbeing_question, wellbeing [code, text], weight {min, max, step}, timezones [11 × {tz, city}], fallback_title, cities [[город, регион, i]]}; GET form → {submitted, created_at}; POST form {tz, gender, wellbeing_code, weight_kg} + X-Client-Op-Id → 200 {created_at}; 409 RECONSENT_REQUIRED / ONBOARDING_FORM_EXISTS / IDEMPOTENCY_CONFLICT; 422.
- cities-1 §7: region готов к показу; у городов федерального значения region = city.

## 2. Канон и решения (метки К-6)
- miniapp-screens §Онбординг: onb.offer → onb.form → onb.checkup → onb.rules.
- 04 §4.4–4.5: «Всё верно? [Да] [Исправить]», «Назад», «Шаг N из M». 05 §5.2–5.4: вопросы по одному, кнопки 0–3, заголовок блока, «Вопрос N из 15», результат — зона и текст, балла нет.
- Р-16: только tz, пол, самочувствие, вес; в черновике тоже нет ФИО, телефона, email, города. Р-17 (cities-1 §3): подсказки с 2 букв, до 10, рядом область, только выбор, «Моего города нет» → заглушка → 11 кнопок.
- 1А. Признак «Чек-Ап пройден» даёт сервер. [Автор, канон проверен 04 §4.9 «Прогресс онбординга сохраняется в БД»].
- 2А. Ответы Чек-Апа — только в памяти экрана; закрыл приложение → с вопроса 1. [Автор против канона 05 Fail-safe: «Сохранение прогресса опроса (продолжение с прерванного вопроса)»]. Действует по К-7 после записи Р-18 в DECISIONS (docs-пакет ШТАБа).
- 3А. Подсказка города — две строки: город, под ним мелко область; для Москвы, Санкт-Петербурга, Севастополя — только город. [Автор, канон проверен Р-17 (cities-1.md §3) — вид не задан].
- [ШТАБ-тех] 2 карточки А (onb.form, РЕВЬЮЕР да) → Б (onb.checkup); Draft = {step}, DRAFT_VERSION = 2; при возврате экран проверяет GET /miniapp/v1/onboarding/form.
- Расхождения: 04 §4.9 «прогресс онбординга в БД» против черновика в IndexedDB — известное расхождение, черновик хранит только шаг; анкета и Чек-Ап — на сервере. 04 §4.4 «кнопки-города» — DOCS №14 (cities-1). 05 Fail-safe — DOCS по 2А (§5).

## 3. Нарезка и порядок: api-i3-4 ‖ А → Б
- А miniapp-i3-1a (onb.form, Агент Р1, РЕВЬЮЕР да). Изменить: api/client.ts (+getFormConfig, getForm, postForm); components/LaterSteps.tsx (email и city → form, «Шаг N из 4»); components/drafts.ts (Draft = {step}, v2); components/App.tsx (GET form в routeByDraft); components/startup.ts (если меняется afterNumber); тесты §6. Создать: components/OnbForm.tsx, components/onbForm.ts, components/onbForm.test.ts. Около 10 файлов, около 550 строк.
- Б miniapp-i3-1b (onb.checkup, Агент Р1, РЕВЬЮЕР нет). Старт после мержа api-i3-4 и А и после записи Р-18. Изменить: client.ts (+getCheckupConfig, getCheckupStatus, postCheckupSubmit); LaterSteps.tsx; App.tsx (GET checkup/status после GET form); OnboardingFlow.test.ts. Создать: components/Checkup.tsx, components/checkup.ts, components/checkup.test.ts. Около 7 файлов, около 420 строк.
- Почему так: А и Б вместе больше лимита DESIGNER «Размеры»; у них общие LaterSteps.tsx, client.ts, App.tsx — параллельно нельзя. api-i3-4 не пересекается с А по файлам.

## 4. api-i3-4 «статус Чек-Апа» (КОДЕР Р0+, РЕВЬЮЕР нет)
- Форма (К-5, ПРОЕКТИРОВЩИК): отдельный GET /miniapp/v1/checkup/status в checkup.py. Почему не поле в GET form: у анкеты и Чек-Апа разные таблицы, ошибки и время; Чек-Ап повторяется после каждого Этапа (05 §5.1), анкета — нет; ответ по образцу GET form.
- Ответ 200 {completed: bool, created_at: string|null} — есть ли запись Чек-Апа с occasion onboarding у активного pid. Зоны, балла и ответов в ответе нет.
- Ошибки: 401 (роутер miniapp_v1), 404 PARTICIPANT_NOT_FOUND, 429, 503 SERVICE_UNAVAILABLE (SQLAlchemyError, в лог — имя класса). Повтор согласия (reconsent) — как в GET form; поведение GET form в роутере анкеты не проверено.
- Только чтение: без X-Client-Op-Id, без записи; лог INFO — tg_user_id и completed.
- Повторный Чек-Ап онбординга: если в 0014 нет уникальности на (pid, occasion) для onboarding — в api-i3-4 добавить: POST submit с новым op_id при уже имеющемся Чек-Апе онбординга → 409 CHECKUP_EXISTS (код — К-5, имя не проверено с контрактом); способ (индекс или проверка в транзакции) — вопрос ШТАБу, миграция — по одной.
- Файлы: apps/api/app/routers/checkup.py; новый apps/api/tests/test_checkup_status_db.py; при 409 — apps/api/tests/test_checkup_submit_db.py. Правка контракта (miniapp-api-contract.yaml) — DOCS-пакет ШТАБа до промпта.
- Задетые тесты: test_checkup_submit_db.py — только при 409; test_checkup_config.py — нет. Есть ли тест со списком маршрутов — не проверено.

## 5. Правка канона DOCS для 2А (после Р-18)
- файл: architecture/05-checkup.md
- найди: «Сохранение прогресса опроса (продолжение с прерванного вопроса)» — строка взята из ответа Автора; точную строку и yaml-блок 05 окну КАРТОЧКИ сверить по файлу.
- замени: «Прогресс опроса не сохраняется: ответы — только в памяти экрана; закрыл приложение — опрос с вопроса 1 (Р-18)».

## 6. Технические решения (К-5, ПРОЕКТИРОВЩИК)
- Т-1 Черновик = только step; DRAFT_VERSION 1 → 2: старые записи с email и city не пройдут parseStoredDraft и удалятся при открытии. Поля анкеты и ответы Чек-Апа — только память React.
- Т-2 Шаги: offer → form → checkup → rules → finished; «Шаг N из 4».
- Т-3 Анкета есть: шаг form и App.routeByDraft вызывают GET form; submitted=true → checkup. Чек-Ап пройден (Б): GET checkup/status, completed=true → rules. Ошибка GET → экран «Повторить».
- Т-4 Подсказки: нижний регистр, ё → е, без крайних пробелов; совпадение с начала; с 2 символов; до 10 в порядке файла. Две строки, город = регион → одна (3А). Выбор → tz = timezones[i].tz; правка текста сбрасывает выбор.
- Т-5 Вес: запятая → точка; не больше 1 знака после точки; min ≤ x ≤ max из config.
- Т-6 POST form: один op_id на экран, повтор — с ним же (D-17). 409 ONBOARDING_FORM_EXISTS → шаг checkup. 409 RECONSENT_REQUIRED или 404 → заглушка и «Открыть заново» (проп onRestart → App checking). 422 → «Проверьте ответы».
- Т-7 Чек-Ап: один op_id на прохождение; 409 и 404 — как Т-6; 409 CHECKUP_EXISTS (если будет) → rules; после 200 — зона из config и disclaimer, «Далее» → rules.
- Т-8 Тексты — заглушки «Заглушка: …»; B4.onb_email и B4.onb_city убрать из LATER_TEXT_KEYS.
- Т-9 cities (около 1 100) — один раз с form/config, в памяти.
- Т-10 РЕВЬЮЕР: А — да (пол, самочувствие, вес; меняется drafts.ts: на устройство и в лог — только step). Б — нет.

## 7. Задетые тесты (правило «Т»)
OnboardingFlow.test.ts:
- А: убрать импорт canContinueEmail; LATER_TEXT_KEY_LIST — без B4.onb_email и B4.onb_city;
- А: «порядок шагов» → offer, form, checkup, rules, finished; удалить тесты «email: …», «city: только город из списка» и блок «формы email и city, Enter»;
- А: «индикатор прогресса» → «Шаг 1 из 4», checkup — «Шаг 3 из 4»;
- А: NO_STORAGE_FILES + './OnbForm.tsx', './onbForm.ts'; Б: + './Checkup.tsx', './checkup.ts';
- А: «drafts.ts: нет даты рождения» — добавить запреты 'email', 'city', 'gender', 'weight', 'wellbeing'.
- drafts.test.ts — задет (email, city, CITY_OPTIONS, EMAIL_MAX_LENGTH, DRAFT_VERSION); startup.test.ts и startup.ts — если меняется afterNumber.

## 8. Риски
- Живые проверки (GET form, GET checkup/status, POST) — только после выката api 10.11 и мержа api-i3-4.
- Вид cities в form/config — по docs13, роутер не читал.

## 9. Вопросы Автору (К-4)
Нет.

## 10. Надо дочитать окну КАРТОЧКИ
- apps/api/migrations/versions/2026_11_07_1200-0014_measurements_log_measurements_log.py — есть ли уникальность на (pid, occasion) для onboarding, имена колонок; если нет — требование 409 в api-i3-4 и вопрос ШТАБу.
- apps/api/app/routers/onboarding_form.py — вид cities, reconsent в GET form.
- drafts.test.ts, startup.ts, startup.test.ts (§7); 05-checkup.md Fail-safe и yaml (§5).

## 11. Прочитано (@a56b172, КБ)
База: DESIGNER.md 23,1; STATE.md 18,6; AGENT-BRIEF.md 17,1; process/README.md 8,9; DECISIONS.md 7,8; CANON-CHECK.md 4,9. Mini App: OnboardingFlow.tsx 16,9; OnboardingFlow.test.ts 21,0; LaterSteps.tsx 13,6; client.ts 10,7; App.tsx 6,8; routes.tsx 0,4. API: api-i3-2-docs13.md 6,4; checkup.py 11,2; form.json 1,3; checkup.v1.json 3,0. Канон: miniapp-screens.md 5,5; cities-1.md 9,3. Сверх списка: drafts.ts 13,7; 04-onboarding.md 13,4; 05-checkup.md 7,6 (Fail-safe пришёл с пропуском). З2: только списки файлов (api contents) для путей §10.
