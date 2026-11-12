# miniapp-i3-2a — Mini App: экран me.card (/me), маршрут и вход с экрана дня

## 1. Паспорт
- id: miniapp-i3-2a · PR: «feat(miniapp): экран me.card — карточка участника (miniapp-i3-2a)» · ветка: feat/miniapp-i3-2a-me-card
- Режим: Агент Р1 · РЕВЬЮЕР: нет (§14) · Зависит от: ничего (API готов: #197, api-i3-3). Следом — miniapp-i3-2b.
- Основа: PLAN §5 п.11; З1 и решения ШТАБа Ш-1…Ш-8 (окно miniapp-i3-2). «Как сейчас» — по коду @c5e0a3f.
- Оценка: 550–700 кредитов (§13). Тесты сверх §9 не добавлять. Упал тест вне «Задетых тестов» — не чинить: «тест X вне списка» в ИТОГ и стоп.

## 2. Цель
Экран «Моя карточка» по адресу /me: номер, дата регистрации, пояс, позиция, жизни, вес и зона Чек-Апа (старт и последнее) из GET /miniapp/v1/me/card. Вход — ссылкой с экрана дня, обратно — ссылкой на /day. Нет данных → «нет данных»; балла Чек-Апа нет нигде. На устройстве ничего не хранится.

## 3. Решения (дословно)
Автора (по docs/tasks/api-i3-3.md §3 и DECISIONS):
- Р-16: «ФИО, телефон, email не собираем; город → только tz, город не хранится.» [К-6: Автор]
- Р-3: «фото участников нет → слоя photo4 нет. Р-6: настроек уведомлений нет.» [К-6: Автор]
- Л5 А: «пустых экранов нет; где данных нет — «нет данных» (в API: null или []).» [К-6: Автор]
- Р-18, 1А: «Признак „Чек-Ап пройден“ даёт сервер.» Участнику — только зона, балла нет (I3 §C.7). [К-6: Автор]
ШТАБа (З2 окна miniapp-i3-2):
- Ш-2: «Вариант А (Link из react-router-dom, новых зависимостей нет) + (б): ссылка «Заглушка: моя карточка» видна только в основном виде экрана дня и только когда поле рефлексии пустое (после trim) и отчёт не отправляется (sending false). На экранах «Загрузка», ошибки и unknown ссылки нет. Системная кнопка «Назад» Telegram — не в этой задаче.» [К-6: ШТАБ]
- Ш-3 (часть для этой карточки): «Показывать только дату, без времени. tz null или не распознан (Intl бросил исключение) → дата по UTC. Функция даты — чистая, в me.ts, с тестом.» [К-6: ШТАБ]
- Ш-4: «(а): местные заглушки зон в me.ts. /checkup/config не запрашивать.» [К-6: ШТАБ]
- Ш-7: «Ошибки трёх экранов: текст через готовую dayErrorMessage (dayScreen.ts) + кнопка «Повторить»; автоповтора при 503 нет.» [К-6: ШТАБ]
- Ш-8: «DayPage.tsx в NO_STORAGE_FILES не добавлять.» [К-6: ШТАБ]

## 4. Выдержки (Агент архитектуру не читает)
- 06 §6.1 (по api-i3-3 §4): «Карточка формируется свежей из БД в момент запроса (не хранится готовой).»
- build/miniapp-screens.md, «Карточка участника»: «| `me.card` | `/me` | Моя карточка (данные, замеры, позиция, жизни) |».
- 14 §14.3 (по api-i3-3 §4): «inflammation_zone (0=green, 1=yellow, 2=red; direction=lower_better, enum_zone)».
- api-i3-3 §4: «даты — UTC ISO; локальный день считает клиент по tz из /me/card (tz_change_log нет)».
- По коду me.py (сверил ШТАБ, c5e0a3f): даты приводятся к UTC; short_no — format_short_no, вид «#000123»; lives — всегда число.
- По коду App.tsx: HashRouter и маршруты монтируются только в фазе app; маршруты берутся из массива routes; любой другой путь → /day.
- По коду DayPage.tsx: текст рефлексии — useState reflection, только в памяти экрана; при уходе с /day экран размонтируется.

## Канон и решения
(а) Используются: build/miniapp-screens.md «Карточка участника»; 06 §6.1; 14 §14.1–14.4 (по выдержкам api-i3-3 §4); DECISIONS Р-3, Р-6, Р-16, Р-18.
(б) Расходятся с решениями: три строки build/miniapp-screens.md (Л4 А, слой Чек-Апа, Р-6).
(в) Правки DOCS — применяет ШТАБ DOCS-пакетом; промпт Агенту от них не зависит (выдержки — в карточке). Файл architecture/build/miniapp-screens.md:
1. найди: «| `me.consents` | `/me/consents` | Мои согласия C0–C6 (фото-согласия нет — Р-3) |» · замени: «| `me.consents` | `/me/consents` | Мои согласия C0–C6: только просмотр, отзыв — с И4 (Л4 А); фото-согласия нет — Р-3 |»
2. найди: «(антропометрия / самочувствие / функциональные; слоя «фото» нет — Р-3)» · замени: «(антропометрия / самочувствие / Чек-Ап — только зона / функциональные; слоя «фото» нет — Р-3)»
3. найди строку целиком: «| `me.settings-notifications` | `/me/notifications` | Настройки уведомлений (чекбоксы reminders / motivational, P-5) |» · удали; после таблицы добавь строку: «Экрана настроек уведомлений нет (решение Автора Р-6).»
Канон молчит о переходах между day.current и me.card → решение Ш-2 [К-6: ШТАБ, К-5].
Метки К-6: [Автор] и [ШТАБ] — §3; [ПРОЕКТИРОВЩИК-тех] — у пунктов §7 с этой меткой.

## 5. ЧТО ПРОЧИТАТЬ (точный список; чтение Агента ≈ 122 КБ)
- AGENT-BRIEF.md 17,1 · docs/decisions/DECISIONS.md 7,8 · эта карточка ≈ 18.
- apps/miniapp/src/api/client.ts 14,7 — правится (добавление в конец).
- apps/miniapp/src/pages/DayPage/DayPage.tsx 19,1 — правится (ссылка); образец контейнера (mountedRef, requestIdRef, экраны «Загрузка…» и ошибки).
- apps/miniapp/src/components/dayScreen.ts 6,3 — dayErrorMessage; не менять.
- apps/miniapp/src/navigation/routes.tsx 0,4 · apps/miniapp/src/components/App.tsx 8,8 — правятся.
- apps/miniapp/src/components/checkup.ts 4,8 и checkup.test.ts 6,5 — образцы чистой логики и тестов.
- apps/miniapp/src/components/OnboardingFlow.test.ts 18,6 — правится (только список NO_STORAGE_FILES).

## 6. Файлы (8; ожидаемо ≈ 360 строк: код ≈ 240, тесты ≈ 120)
- Создать: apps/miniapp/src/pages/MePage/MeCardPage.tsx (≈ 100); apps/miniapp/src/components/me.ts (≈ 95); apps/miniapp/src/components/me.test.ts (≈ 120).
- Изменить: apps/miniapp/src/api/client.ts (+30); apps/miniapp/src/navigation/routes.tsx (+4); apps/miniapp/src/pages/DayPage/DayPage.tsx (+8); apps/miniapp/src/components/App.tsx (1 строка комментария); apps/miniapp/src/components/OnboardingFlow.test.ts (+2).
- Удалить: нет. dayScreen.ts, dayMarks.ts, drafts.ts, startup.ts не менять.

## 7. Контракт и поведение
### 7.1 API (client.ts — добавить в конец файла)
- getMeCard(): GET /miniapp/v1/me/card, без тела и без X-Client-Op-Id (только чтение) → 200, ровно эти ключи (api-i3-3 §7):
  - short_no: string (вид «#000123»); registered_at: string (date-time, UTC);
  - tz: string | null; position: {stage_no, module_no, day_no} | null (тип DayPosition уже есть); lives: number;
  - measurements: {weight_start_kg: number | null, weight_current_kg: number | null, checkup_completed: boolean, zone_start: 'green' | 'yellow' | 'red' | null, zone_last: 'green' | 'yellow' | 'red' | null}.
- Ошибки: 401; 404 PARTICIPANT_NOT_FOUND; 429; 503 SERVICE_UNAVAILABLE.
- Типы: ZoneId, MeMeasurements, MeCard. Полей балла (score, answers) в типах нет.
### 7.2 Чистая логика (me.ts — без React и без запросов)
- Импорты в новых файлах — только относительные ('../api/client.ts'), не '@/': me.test.ts импортирует эти файлы, алиас в vitest не проверен [ПРОЕКТИРОВЩИК-тех].
- ME_TEXT — объект констант, каждое значение начинается с «Заглушка: »: cardTitle «Заглушка: моя карточка» (он же текст ссылки с экрана дня), toDay «Заглушка: к экрану дня», подписи строк: shortNo, registered, tz, position, lives, weightStart, weightCurrent, checkup, zoneStart, zoneLast; checkupDone «Заглушка: Чек-Ап пройден», checkupNotDone «Заглушка: Чек-Ап не пройден».
- NO_DATA = «Заглушка: нет данных». ZONE_TITLES: green «Заглушка: зелёная зона», yellow «Заглушка: жёлтая зона», red «Заглушка: красная зона».
- localDate(iso: unknown, tz: string | null | undefined): string | null — дата «ДД.ММ.ГГГГ» без времени. Не строка или Date.parse дал NaN → null. Сборка — из Intl.DateTimeFormat('ru-RU', {timeZone, day: '2-digit', month: '2-digit', year: 'numeric'}).formatToParts (части day, month, year). tz пустой или Intl бросил исключение → то же с timeZone 'UTC'.
- zoneTitle(zone: unknown): string — green / yellow / red → ZONE_TITLES; иначе NO_DATA.
- weightText(v: unknown): string — конечное число → «<число> кг» (String(v)); иначе NO_DATA.
- positionText(p: unknown): string — три целых номера → «Заглушка: этап S, модуль M, день D»; иначе NO_DATA.
- cardRows(card: MeCard): {label: string; value: string}[] — ровно 10 строк в порядке: номер (short_no), регистрация (localDate(registered_at, tz) ?? NO_DATA), пояс (tz ?? NO_DATA), позиция, жизни (String(lives)), вес на старте, вес сейчас, Чек-Ап (checkupDone / checkupNotDone), зона на старте, зона последняя. Пустых значений нет (Л5).
- canOpenCard(reflection: string, sending: boolean): boolean — reflection.trim() === '' && !sending (Ш-2).
### 7.3 Экран (MeCardPage.tsx)
- MeCardView({card}) — экспортируемый вид без хуков и без Link: заголовок ME_TEXT.cardTitle и список cardRows(card) (подпись и значение). Ссылок, полей ввода, балла нет.
- MeCardPage — контейнер: при монтировании один getMeCard(); «Загрузка…» → готово (MeCardView) либо ошибка: dayErrorMessage(err) и кнопка «Повторить» → новый GET. Автоповтора и таймеров нет (Ш-7). Защита от ответа после размонтирования — как в DayPage (mountedRef, номер запроса).
- Ссылка Link to="/day" с текстом ME_TEXT.toDay — в готовом виде и на экране ошибки; на «Загрузка…» ссылки нет [ПРОЕКТИРОВЩИК-тех].
- Служебные «Загрузка…», «Повторить» и текст dayErrorMessage — как на экране дня (по коду DayPage.tsx); все прочие тексты — только ME_TEXT, NO_DATA, ZONE_TITLES [ПРОЕКТИРОВЩИК-тех].
- Ответ живёт только в state React: не на устройство, не в лог, не в адрес.
### 7.4 Маршрут и вход (routes.tsx, DayPage.tsx, App.tsx)
- routes.tsx: добавить { path: '/me', Component: MeCardPage }; комментарий: «/me — me.card (miniapp-screens.md)».
- DayPage.tsx: импорт Link из 'react-router-dom' и { ME_TEXT, canOpenCard } из '@/components/me.ts'. В последнем return (основной вид), после кнопки «Обновить»: canOpenCard(reflection, sending) → Link to="/me" с текстом ME_TEXT.cardTitle, иначе null. В трёх ранних return («Загрузка…», ошибка, unknown) ссылки нет. Одна строка в шапке-комментарии файла. Больше в DayPage ничего не менять.
- App.tsx: логику не менять; одна строка комментария: «miniapp-i3-2: маршруты фазы app — список в navigation/routes.tsx; логика фаз не менялась».
- Известное поведение: уход на /me размонтирует экран дня; при возврате — «Загрузка…» и новый GET /day/current. Отметки не теряются (уходят на сервер сразу); рефлексия не теряется, потому что при непустом поле ссылки нет.

## 8. БД
Нет. Новых ключей text_registry нет; seed и списки ключей не трогать.

## 9. Тесты (ровно этот список) — me.test.ts: vitest, environment node, без DOM, рендер через createElement + renderToStaticMarkup
1. localDate: «2026-10-22T22:30:00Z» и tz «Asia/Yekaterinburg» → «23.10.2026».
2. localDate: tz null, undefined, «Плохо/Пояс» → «22.10.2026» (UTC); iso «плохо», undefined, 42 → null.
3. zoneTitle: green, yellow, red → три разные строки ZONE_TITLES; «purple», null → NO_DATA.
4. weightText: 72.5 → «72.5 кг»; null, NaN, «72» → NO_DATA.
5. positionText: {stage_no: 1, module_no: 2, day_no: 3} → строка с 1, 2, 3; null и объект без day_no → NO_DATA.
6. cardRows, полная карточка: 10 строк; значения номера «#000123», жизней «3», веса, зоны и даты — по функциям выше.
7. cardRows, карточка сразу после first-launch (tz null, position null, веса null, зоны null, checkup_completed false): 10 строк, пустых значений нет, NO_DATA ровно в 6 строках, Чек-Ап — checkupNotDone.
8. canOpenCard: ('', false) и ('   ', false) → true; ('ab', false) и ('', true) → false.
9. MeCardView: в разметке есть «#000123» и ME_TEXT.cardTitle; нет «score», нет «<a », нет «<input».
10. Все значения ME_TEXT, ZONE_TITLES и NO_DATA начинаются с «Заглушка: ».
Быстрые тесты — цель tools/check.sh для Mini App по AGENT-BRIEF.md (tsc + vitest); прочее проверит CI.

## Задетые тесты (правило «Т»; чинить только этот список)
- apps/miniapp/src/components/OnboardingFlow.test.ts → в массив NO_STORAGE_FILES добавить две строки: '../pages/MePage/MeCardPage.tsx' и './me.ts'. Других правок в файле нет.
- Поиск ШТАБа и ПРОЕКТИРОВЩИКА по c5e0a3f: readFileSync есть только в onbForm.test.ts (читает ./OnbForm.tsx и ./onbForm.ts) и OnboardingFlow.test.ts; client.test.ts, startup.test.ts, dayScreen.test.ts правкой не задеты (DayPage, App и routes они не импортируют).
- App.tsx и client.ts уже стоят в NO_STORAGE_FILES: их правка проходит ту же проверку слов (§11).

## 10. Живые проверки — после общего выката И3 (PLAN §4); выкат этой карточкой не назначается
- Экран дня, основной вид → внизу ссылка «Заглушка: моя карточка» → /me: номер вида «#000123», дата регистрации без времени, жизни; балла нет.
- Участник без анкеты и Чек-Апа: в строках пояса, позиции, веса и зон — «Заглушка: нет данных».
- На /me ссылка «Заглушка: к экрану дня» → экран дня, один новый GET /day/current.
- День рефлексии: в поле набран текст → ссылки на карточку нет; поле очищено → ссылка есть.
- Журнал сервера: «me/card: tg_user_id=… status=ok»; веса и зоны в журнале нет.

## 11. Запреты
- AGENT-BRIEF §3. docs/architecture/** не открывать. Новых зависимостей нет; ci.yml не трогать. Логику App.tsx не менять.
- Во всём тексте новых файлов, client.ts и App.tsx, включая комментарии, без учёта регистра не должно быть слов (BANNED_STORAGE, 11): localstorage, sessionstorage, indexeddb, dexie, document.cookie, console., sendbeacon, pushstate, replacestate, location.hash, persist( — и (BANNED_HTML, 3): innerhtml, insertadjacenthtml, document.write.
- Ответ /me/card — не на устройство, не в лог, не в адрес. Балла Чек-Апа нет нигде. Фото (Р-3), настроек уведомлений (Р-6), экрана me.legal-data, отзыва согласий здесь нет.
- Экраны me.consents и me.change-map, getMeChangeMap — не в этой карточке (miniapp-i3-2b).
- Тексты — только константы «Заглушка: …» в me.ts (исключение — §7.3, служебные). /checkup/config и /texts/bulk не запрашивать.
- Тесты сверх §9 не добавлять; тесты вне «Задетых тестов» не чинить: «тест X вне списка» в ИТОГ и стоп.

## 12. Готово, когда
- check.sh зелёный, CI зелёный; 8 файлов §6; задетый тест исправлен ровно по списку; отличия от карточки — в описании PR.

## 13. Оценка
- Строки по файлам: MeCardPage.tsx 100 + me.ts 95 + me.test.ts 120 + client.ts 30 + routes.tsx 4 + DayPage.tsx 8 + App.tsx 1 + OnboardingFlow.test.ts 2 = 360.
- Множитель ×1,6 (урок 11.11) → ≈ 580 строк. Кредиты: 550–700 (ориентир miniapp-i3-1b: ≈ 600 строк — 550–700; 1 задетый тест-файл уже в счёте). Часы Автора ≈ 0,5.

## 14. РЕВЬЮЕР: нет
Только чтение своей карточки: initData, 18+, запись согласий (B-2), rate-limit (B-1), роли и GRANT БД (B-3), оплата не трогаются; на устройстве ничего не хранится.
