# miniapp-i3-2b — Mini App: экраны me.consents (/me/consents) и me.change-map (/me/change-map)

## 1. Паспорт
- id: miniapp-i3-2b · PR: «feat(miniapp): экраны me.consents и me.change-map (miniapp-i3-2b)» · ветка: feat/miniapp-i3-2b-me-screens
- Режим: Агент Р1 · РЕВЬЮЕР: нет (§14).
- Зависит от: мерж miniapp-i3-2a; перед промптом ШТАБ сверяет §«Файлы» и «Задетые тесты» с кодом после мержа 2a.
- Основа: PLAN §5 п.11; З1 и решения ШТАБа Ш-1…Ш-8 (окно miniapp-i3-2). «Как сейчас» — по коду @c5e0a3f и по карточке miniapp-i3-2a; hash после мержа 2a даёт ШТАБ.
- Оценка: 650–800 кредитов (§13). Тесты сверх §9 не добавлять. Упал тест вне «Задетых тестов» — не чинить: «тест X вне списка» в ИТОГ и стоп.

## 2. Цель
Два экрана только для просмотра. /me/consents — свои согласия: «<id> — дано <дата>» и «действует» либо «отозвано <дата>» (отзыв — И4). /me/change-map — Карта изменений: 4 слоя, старт и до 5 последних значений. Вход — ссылками с карточки /me, обратно — ссылкой на /me. Нет данных → «нет данных»; балла Чек-Апа и кода самочувствия на экране нет.

## 3. Решения (дословно)
Автора (по docs/tasks/api-i3-3.md §3 и DECISIONS):
- Л4 А (I3 §C.12): «согласия в И3 — только просмотр, отзыв — И4.» [К-6: Автор]
- Л5 А: «пустых экранов нет; где данных нет — «нет данных» (в API: null или []).» [К-6: Автор]
- Р-3: «фото участников нет → слоя photo4 нет.» [К-6: Автор]
- Р-18, 1А: «Признак „Чек-Ап пройден“ даёт сервер.» Участнику — только зона, балла нет (I3 §C.7). [К-6: Автор]
ШТАБа (З2 окна miniapp-i3-2):
- Ш-3: «(а): под-экраны запрашивают /me/card ради tz параллельно со своим GET; ошибка любого — ошибка экрана. Показывать только дату, без времени. tz null или не распознан (Intl бросил исключение) → дата по UTC. Функция даты — чистая, в me.ts, с тестом.» [К-6: ШТАБ]
- Ш-4: «(а): местные заглушки зон в me.ts. /checkup/config не запрашивать.» [К-6: ШТАБ]
- Ш-5: «(а): wellbeing — «Заглушка: ответ записан, <дата>», код на экран не выводить.» [К-6: ШТАБ]
- Ш-6: «legal_status не показывать. На экране: «<id> — дано <дата>» и «действует» либо «отозвано <дата>». Пустой список → «нет данных» (Л5).» [К-6: ШТАБ]
- Ш-7: «Ошибки трёх экранов: текст через готовую dayErrorMessage (dayScreen.ts) + кнопка «Повторить»; автоповтора при 503 нет.» [К-6: ШТАБ]
- Открытый вопрос до 0-Б (152-ФЗ ст. 10): показ wellbeing_code. Автору не задавать; до решения код на экран не выводится (Ш-5).

## 4. Выдержки (Агент архитектуру не читает)
- build/miniapp-screens.md, «Карточка участника»: «| `me.consents` | `/me/consents` | Мои согласия C0–C6 (фото-согласия нет — Р-3) |»; «| `me.change-map` | `/me/change-map` | Полная Карта изменений (антропометрия / самочувствие / функциональные; слоя «фото» нет — Р-3) |».
- 14 §14.2 (по api-i3-3 §4): «Пять слоёв: anthro (число), photo4 (приватное ПДн-медиа), wellbeing (шкальные), functional (число), checkup»; врезка Р-3: фото нет.
- 14 §14.4 (по api-i3-3 §4): «окно K=6 по умолчанию (baseline + 5 последних + текущий) … хранение UTC … участник — только своё».
- 14 §14.3 (по api-i3-3 §4): «inflammation_zone (0=green, 1=yellow, 2=red; direction=lower_better, enum_zone)».
- api-i3-3 §4: «слой checkup — только зона: тренда суммы и детализации по 15 утверждениям нет (I3 §C.7, 05 §5.4); photo4 нет (Р-3); functional — нет данных»; «даты — UTC ISO; локальный день считает клиент по tz из /me/card (tz_change_log нет)».
- По коду consents.py: «нет участника → 200 []»; «последнее give → revoked_at = null; последнее revoke → revoked_at = время отзыва; given_at — время последнего give; kind без единого give в ответ не попадает».
- По коду client.ts: getConsents() и тип ConsentOut {id, given_at, revoked_at, legal_status} уже есть — не менять.

## Канон и решения
(а) Используются: build/miniapp-screens.md «Карточка участника» (me.consents, me.change-map); 14 §14.1–14.4 и 06 §6.1 (по выдержкам api-i3-3 §4); DECISIONS Р-3, Р-18.
(б) Расходятся с решениями: строки me.consents (Л4 А) и me.change-map (слой Чек-Апа) в build/miniapp-screens.md.
(в) Правки DOCS — те же, что в карточке miniapp-i3-2a; применяет ШТАБ DOCS-пакетом, промпт Агенту от них не зависит. Файл architecture/build/miniapp-screens.md:
1. найди: «| `me.consents` | `/me/consents` | Мои согласия C0–C6 (фото-согласия нет — Р-3) |» · замени: «| `me.consents` | `/me/consents` | Мои согласия C0–C6: только просмотр, отзыв — с И4 (Л4 А); фото-согласия нет — Р-3 |»
2. найди: «(антропометрия / самочувствие / функциональные; слоя «фото» нет — Р-3)» · замени: «(антропометрия / самочувствие / Чек-Ап — только зона / функциональные; слоя «фото» нет — Р-3)»
Открытый вопрос до 0-Б (152-ФЗ ст. 10): показ wellbeing_code — решения Автора о показе кода нет; правки канона по нему нет.
Метки К-6: [Автор] и [ШТАБ] — §3; [ПРОЕКТИРОВЩИК-тех] — у пунктов §7 с этой меткой.

## 5. ЧТО ПРОЧИТАТЬ (точный список; чтение Агента ≈ 97 КБ; размеры файлов 2a — после её мержа, уточняет ШТАБ)
- AGENT-BRIEF.md 17,1 · docs/decisions/DECISIONS.md 7,8 · эта карточка ≈ 17.
- apps/miniapp/src/api/client.ts ≈ 15,7 — правится (добавление в конец).
- apps/miniapp/src/components/me.ts ≈ 4 и me.test.ts ≈ 6 — правятся (дописать); apps/miniapp/src/pages/MePage/MeCardPage.tsx ≈ 4 — правится, он же образец контейнера.
- apps/miniapp/src/navigation/routes.tsx ≈ 0,5 — правится.
- apps/miniapp/src/components/dayScreen.ts 6,3 — dayErrorMessage; не менять.
- apps/miniapp/src/components/OnboardingFlow.test.ts ≈ 18,7 — правится (только список NO_STORAGE_FILES).

## 6. Файлы (8; ожидаемо ≈ 406 строк: код ≈ 294, тесты ≈ 112)
- Создать: apps/miniapp/src/pages/MePage/MeConsentsPage.tsx (≈ 75); apps/miniapp/src/pages/MePage/MeChangeMapPage.tsx (≈ 90).
- Изменить: apps/miniapp/src/api/client.ts (+28); apps/miniapp/src/navigation/routes.tsx (+5); apps/miniapp/src/pages/MePage/MeCardPage.tsx (+6); apps/miniapp/src/components/me.ts (+90); apps/miniapp/src/components/me.test.ts (+110); apps/miniapp/src/components/OnboardingFlow.test.ts (+2).
- Удалить: нет. App.tsx, DayPage.tsx, dayScreen.ts не менять.

## 7. Контракт и поведение
### 7.1 API (client.ts — добавить в конец файла)
- getMeChangeMap(): GET /miniapp/v1/me/change-map, без тела и без X-Client-Op-Id → 200 {layers: [4 объекта, порядок anthro, wellbeing, checkup, functional]} (api-i3-3 §7):
  - слой: {layer, metric, baseline: Point | null, recent: [Point]}; Point = {value, at: date-time UTC};
  - anthro: metric weight_kg, value — number; wellbeing: metric wellbeing_code, baseline — из анкеты (value — код), recent всегда []; checkup: metric inflammation_zone, value — зона (string); functional: metric null, baseline null, recent [];
  - baseline — первая строка; recent — до 5 последних строк после baseline, по возрастанию; baseline в recent не входит; нет данных в слое → baseline null, recent [], слой всё равно есть (Л5).
- Ошибки getMeChangeMap: 401; 404 PARTICIPANT_NOT_FOUND; 429; 503 SERVICE_UNAVAILABLE.
- getConsents() (уже есть): GET /miniapp/v1/consents → 200 [{id, given_at, revoked_at, legal_status}]; нет участника → 200 []; 401; 503.
- Типы: ChangeMapPoint {value: number | string; at: string}; ChangeMapLayer {layer: string; metric: string | null; baseline: ChangeMapPoint | null; recent: ChangeMapPoint[]}; MeChangeMap {layers: ChangeMapLayer[]}.
### 7.2 Чистая логика (me.ts — дописать; готовое из 2a не менять)
- Новые константы в ME_TEXT (каждая начинается с «Заглушка: »): consentsTitle «Заглушка: мои согласия», changeMapTitle «Заглушка: карта изменений», toCard «Заглушка: назад к карточке», consentActive «Заглушка: действует», wellbeingRecorded «Заглушка: ответ записан», baselineLabel «Заглушка: старт», recentLabel «Заглушка: последние». LAYER_TITLES: anthro «Заглушка: вес», wellbeing «Заглушка: самочувствие», checkup «Заглушка: Чек-Ап», functional «Заглушка: функциональные».
- dateOrNoData(iso: unknown, tz: string | null | undefined): string — localDate(iso, tz) ?? NO_DATA.
- consentRows(list: unknown, tz): {id: string; given: string; state: string}[] — не массив → []; порядок — по id по возрастанию (C0…C6); given = «Заглушка: <id> — дано <дата>»; state = при revoked_at null → ME_TEXT.consentActive, иначе «Заглушка: отозвано <дата>»; <дата> — dateOrNoData. legal_status в результат не попадает (Ш-6).
- pointLine(layer: string, point: ChangeMapPoint, tz): string — anthro → «<weightText(value)>, <дата>»; checkup → «<zoneTitle(value)>, <дата>»; wellbeing → «<ME_TEXT.wellbeingRecorded>, <дата>» (value не читается и не выводится, Ш-5); прочее → NO_DATA.
- changeMapView(map: unknown, tz): {layer: string; title: string; baseline: string; recent: string[]}[] — всегда ровно 4 элемента в порядке anthro, wellbeing, checkup, functional, даже если тело битое; слой ищется по полю layer; слоя нет или baseline null → baseline = NO_DATA, recent = []; recent — pointLine по каждой точке, порядок сервера [ПРОЕКТИРОВЩИК-тех].
### 7.3 Экраны и маршруты
- MeConsentsView({rows}) в MeConsentsPage.tsx — вид без хуков и без Link: заголовок ME_TEXT.consentsTitle; rows пуст → NO_DATA; иначе на каждое согласие две строки: given и state. Кнопок отзыва нет.
- MeChangeMapView({layers}) в MeChangeMapPage.tsx — вид без хуков и без Link: заголовок ME_TEXT.changeMapTitle; по каждому из 4 слоёв: title, строка «<baselineLabel>: <baseline>»; recent не пуст → recentLabel и список строк.
- MeConsentsPage: Promise.all([getConsents(), getMeCard()]) → rows = consentRows(список, card.tz). MeChangeMapPage: Promise.all([getMeChangeMap(), getMeCard()]) → layers = changeMapView(карта, card.tz). «Загрузка…» → готово либо ошибка любого из двух запросов: dayErrorMessage(err) и «Повторить» → оба GET заново. Автоповтора и таймеров нет (Ш-7). Защита от ответа после размонтирования — как в MeCardPage.
- Ссылка Link to="/me" с текстом ME_TEXT.toCard — в готовом виде и на экране ошибки обоих экранов; на «Загрузка…» ссылки нет [ПРОЕКТИРОВЩИК-тех].
- MeCardPage.tsx: в готовом виде добавить две ссылки: Link to="/me/consents" (ME_TEXT.consentsTitle) и Link to="/me/change-map" (ME_TEXT.changeMapTitle). MeCardView не менять.
- routes.tsx: добавить { path: '/me/consents', Component: MeConsentsPage } и { path: '/me/change-map', Component: MeChangeMapPage }.
- Импорты в новых файлах — только относительные, не '@/' (как в 2a). Служебные «Загрузка…», «Повторить» и текст dayErrorMessage — как на экране дня; все прочие тексты — только константы me.ts.
- Ответы живут только в state React: не на устройство, не в лог, не в адрес.

## 8. БД
Нет. Новых ключей text_registry нет; seed и списки ключей не трогать.

## 9. Тесты (ровно этот список) — дописать в me.test.ts (номера продолжают 2a; тесты 1–10 не менять)
11. consentRows: действующее C1, given_at «2026-10-22T22:30:00Z», tz «Asia/Yekaterinburg» → given содержит «C1» и «23.10.2026»; state = ME_TEXT.consentActive.
12. consentRows: отозванное согласие → state содержит «отозвано» и дату отзыва; значение legal_status («pre-legal-review») не встречается в JSON.stringify результата.
13. consentRows: null, {} и [] → []; вход в порядке C2, C0, C1 → результат C0, C1, C2.
14. changeMapView: null, {} и {layers: []} → 4 элемента в порядке anthro, wellbeing, checkup, functional; у каждого baseline = NO_DATA и recent = [].
15. Слой anthro: baseline и 2 точки recent → baseline содержит «кг» и дату по tz; recent — 2 строки в порядке сервера.
16. Слой wellbeing: baseline {value: 'w3', at} → baseline содержит ME_TEXT.wellbeingRecorded и дату; «w3» не встречается в JSON.stringify результата.
17. Слой checkup: value «green» → baseline содержит ZONE_TITLES.green; слой functional (metric null, baseline null) → NO_DATA.
18. MeConsentsView: rows [] → в разметке NO_DATA; две строки → в разметке «C0» и «C1»; нет «<a », «<button», «score».
19. MeChangeMapView с layers = changeMapView(карта с wellbeing 'w3', tz): в разметке 4 заголовка LAYER_TITLES; нет «w3», «score», «<a ».
20. Все значения LAYER_TITLES начинаются с «Заглушка: » (новые значения ME_TEXT покрывает тест 10).
Быстрые тесты — цель tools/check.sh для Mini App по AGENT-BRIEF.md (tsc + vitest); прочее проверит CI.

## Задетые тесты (правило «Т»; чинить только этот список)
- apps/miniapp/src/components/OnboardingFlow.test.ts → в массив NO_STORAGE_FILES добавить две строки: '../pages/MePage/MeConsentsPage.tsx' и '../pages/MePage/MeChangeMapPage.tsx'. Других правок в файле нет.
- me.test.ts — не задетый: в него дописываются тесты 11–20 из §9, тесты 1–10 не меняются.
- Поиск ШТАБа по c5e0a3f: других тестов, читающих исходники или импортирующих routes.tsx и страницы, нет. После мержа 2a ШТАБ сверяет этот раздел заново (§1).

## 10. Живые проверки — после общего выката И3 (PLAN §4); выкат этой карточкой не назначается
- /me → ссылки «Заглушка: мои согласия» и «Заглушка: карта изменений» открывают /me/consents и /me/change-map.
- /me/consents: на каждое согласие — id, дата без времени, «действует»; кнопок отзыва нет; legal_status на экране нет.
- /me/change-map: 4 слоя; вес и зона — старт с датой; самочувствие — «ответ записан» и дата, кода нет; функциональные — «нет данных»; балла нет.
- На обоих экранах ссылка «Заглушка: назад к карточке» → /me.
- Журнал сервера: «me/change-map: tg_user_id=… status=ok» и «consents: tg_user_id=… count=N»; веса, зоны и кода самочувствия в журнале нет.

## 11. Запреты
- AGENT-BRIEF §3. docs/architecture/** не открывать. Новых зависимостей нет; ci.yml не трогать. App.tsx и DayPage.tsx не менять.
- Во всём тексте новых файлов, me.ts, MeCardPage.tsx и client.ts, включая комментарии, без учёта регистра не должно быть слов (BANNED_STORAGE, 11): localstorage, sessionstorage, indexeddb, dexie, document.cookie, console., sendbeacon, pushstate, replacestate, location.hash, persist( — и (BANNED_HTML, 3): innerhtml, insertadjacenthtml, document.write.
- Ответы — не на устройство, не в лог, не в адрес. На экран не выводить: legal_status (Ш-6), код самочувствия (Ш-5), балл Чек-Апа. Отзыва согласий (И4), фото (Р-3), настроек уведомлений (Р-6), экрана me.legal-data здесь нет.
- /checkup/config, /onboarding/form/config и /texts/bulk не запрашивать. getConsents и ConsentOut в client.ts не менять.
- Тексты — только константы «Заглушка: …» в me.ts (исключение — служебные из §7.3).
- Тесты сверх §9 не добавлять; тесты вне «Задетых тестов» не чинить: «тест X вне списка» в ИТОГ и стоп.

## 12. Готово, когда
- check.sh зелёный, CI зелёный; 8 файлов §6; задетый тест исправлен ровно по списку; отличия от карточки — в описании PR.

## 13. Оценка
- Строки по файлам: MeConsentsPage.tsx 75 + MeChangeMapPage.tsx 90 + client.ts 28 + routes.tsx 5 + MeCardPage.tsx 6 + me.ts 90 + me.test.ts 110 + OnboardingFlow.test.ts 2 = 406.
- Множитель ×1,6 (урок 11.11) → ≈ 650 строк: выше порога ≈ 600, резать ли дальше — решает ШТАБ. Кредиты: 650–800 (1 задетый тест-файл уже в счёте). Часы Автора ≈ 0,5.

## 14. РЕВЬЮЕР: нет
Экран согласий — только чтение через готовый GET /consents (1e-2), его код не меняется; записи и отзыва согласий (B-2) нет; initData, 18+, rate-limit (B-1), роли и GRANT БД (B-3), оплата не трогаются.
