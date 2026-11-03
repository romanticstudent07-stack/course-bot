# miniapp-refl-1 — поле рефлексии на экране отчёта
Правило К — docs/process/CANON-CHECK.md. Карточка по docs/research/iter2-rest.md (§3 а, §9: В1 = А, В3 = Б), ответам ШТАБа 03.11 и коду @e4069b0.

## 1. Паспорт
- id: miniapp-refl-1. Заголовок PR: «feat(miniapp): поле рефлексии в отчёте дня (miniapp-refl-1)». Ветка: feat/miniapp-refl-1.
- Режим: Р0+ (бесплатный КОДЕР); другой режим — решит ШТАБ.
- Зависит от: api-refl-1 (смержена: GET отдаёт reflection_required, submit — 422 REFLECTION_REQUIRED).

## 2. Цель
В день рефлексии (reflection_required = true) под блоками — поле рефлексии. «Отправить отчёт» неактивна, пока в поле меньше 2 символов после trim.
Текст уходит в POST /day/report/submit полем reflection; 422 REFLECTION_REQUIRED показывается своим сообщением и перечитывает день.

## 3. Решения Автора и ШТАБа
- 03 §3.12 / В1 = А: поле обязательно, минимум 2 символа, смысл не оценивается.
- В3 = Б (Автор 30.10): 13-M / 13-P без кнопок модерации; экран о модерации ничего не показывает.
- Т10, Т11 [ПРОЕКТИРОВЩИК-тех, принято ШТАБом 03.11]; Т12 [принято ШТАБом 03.11 с правкой]; Д1 [ШТАБ 03.11] — в §7.

## 4. Выдержки архитектуры (через iter2-rest §1 @e4069b0)
- 03 §3.12: «рефлексия — обязательное поле отчёта дней 6, 13-M, 13-P; без поля "Отправить" нельзя; минимум 2 символа; смысл не оценивается».
- DM 3.3 / 3.10 / 3.11 (шапка DayPage.tsx): «Отправить отчёт» — когда отмечены все блоки; после первого нажатия гаснет; «Отправлено» — только после 200. Ответы на устройстве не хранятся.

## 5. ЧТО ПРОЧИТАТЬ
- apps/miniapp/src/api/client.ts — 10,0 (правка).
- apps/miniapp/src/components/dayMarks.ts — 5,4 (правка).
- apps/miniapp/src/pages/DayPage/DayPage.tsx — 17,4 (правка).
- apps/miniapp/src/components/dayMarks.test.ts — 9,4 (новые тесты в конец).
- Чтение КОДЕРА ≈ 42 КБ.

## 6. Файлы
- Изменить: apps/miniapp/src/api/client.ts, apps/miniapp/src/components/dayMarks.ts, apps/miniapp/src/pages/DayPage/DayPage.tsx, apps/miniapp/src/components/dayMarks.test.ts.

## 7. Контракт
client.ts (Д1):
- DayCurrent: reflection_required?: boolean | null — НЕОБЯЗАТЕЛЬНОЕ (фикстуры openDay и withDay его не задают; обязательное сломает typecheck).
- DayReportIn: reflection?: string.
- Комментарий postDayReport: 422 REFLECTION_REQUIRED — день рефлексии без текста.
dayMarks.ts:
- REFLECTION_MIN = 2, REFLECTION_MAX = 2000.
- reflectionRequired(day) → day?.reflection_required === true.
- Т10: reflectionFilled(text) → Array.from(text.trim()).length >= REFLECTION_MIN (символы как на сервере; эмодзи — 1 символ, а не 2 по .length).
- Т12: canSendReport(view, day, busy, marks, reflection = '') — прежнее условие И (!reflectionRequired(day) || reflectionFilled(reflection)). Старые вызовы без 5-го аргумента работают как сейчас.
- Т12 дополнение: reportBody(blocks, marks, reflection?) — при reflection === undefined в теле НЕТ ключа reflection (тест сравнивает тело целиком через toEqual); иначе {marks, reflection}. Текст уходит как введён: обрезает сервер.
- Т12 правка: submitErrorAction — 422 REFLECTION_REQUIRED → 'refetch' (как MARKS_INCOMPLETE): экран перечитывает GET и получает reflection_required.
- REFLECTION_REQUIRED_MESSAGE = 'Напишите рефлексию: минимум 2 символа.' (строка интерфейса); actionMessage: код REFLECTION_REQUIRED → эта строка, проверка раньше DAY_CHANGED_CODES (там этого кода нет и не добавлять).
- REFLECTION_LABEL = 'Рефлексия' (строка интерфейса, не текст курса).
DayPage.tsx (Т11):
- Состояние reflection (useState, строка). Поле показывается при view open и reflectionRequired(day): подпись REFLECTION_LABEL, многострочное поле (textarea), maxLength REFLECTION_MAX, disabled по тому же правилу, что кнопки отметок (canPressMark).
- canSendReport получает reflection; reportBody получает reflection только при reflectionRequired(day), иначе undefined.
- reuseOpId сравнивает тело: другой текст → новый X-Client-Op-Id сам (D-17); новой логики не нужно.
- Фоновый GET (таймер, «Обновить», refetch) текст не сбрасывает. После 200 — поле очищается. На устройство (localStorage, drafts) текст не пишется.
- Где ошибка — как сейчас: notice через actionMessage.
- Шапка DayPage.tsx: строка «miniapp-refl-1: поле рефлексии (03 §3.12) — …» с кратким описанием.

## 8. БД
Нет.

## 9. Тесты — новые в конце dayMarks.test.ts
1. reflectionFilled: "" → false; " а " → false; "ок" → true; "  ок  " → true; "😀" → false; "😀😀" → true.
2. canSendReport: день с reflection_required true, всё отмечено — '' → false, 'ок' → true; без reflection_required — как раньше (без 5-го аргумента → true).
3. reportBody без reflection → toEqual({marks}) (ключа нет); с 'ок' → toEqual({marks, reflection: 'ок'}).
4. submitErrorAction(ApiError(422, 'REFLECTION_REQUIRED')) → 'refetch'.
5. actionMessage(ApiError(422, 'REFLECTION_REQUIRED'), 'report') → REFLECTION_REQUIRED_MESSAGE.
Цели check.sh: miniapp (имя цели сверит ШТАБ). Только CI: сборка и e2e, если есть.

## 10. Живая проверка (после мержа)
Выкат один на три задачи: migrate 0012 (db-2) → api (api-refl-1) → miniapp (эта задача).
1. Аккаунт на дне 1–5: поля нет, отчёт отправляется как раньше.
2. Аккаунт на дне 6 (метку А1–А4 и время назначит ШТАБ; тестовый день А1 без указания ШТАБа не трогать): поле видно; при всех отметках и пустом поле «Отправить отчёт» неактивна; 1 символ — неактивна; 2 символа — активна.
3. Отправить → «Отправлено»; пост в теме «Рефлексии» (проверяет ШТАБ / Автор в группе).
4. До дня 6 надо дойти (около 4–5 суток) — сроки решает ШТАБ.

## 11. Запреты
- AGENT-BRIEF §3. Текст рефлексии не хранить на устройстве и не логировать в консоль.
- Окно дня и «день рефлексии» клиент не считает: только reflection_required из GET.
- Новых зависимостей нет. Тексты курса — нет (только строки интерфейса).
- Упал тест вне «Задетых тестов» → не чинить, стоп и ИТОГ.

## 12. Готово, когда
Тесты §9 зелёные, typecheck и lint зелёные, старые тесты без правок; CI зелёный.

## 13. Оценка
Р0+: 0 кредитов (Р1 — 400–600, iter2-rest §6). Часы Автора: ≈ 0,5.

## 14. РЕВЬЮЕР
Нет (initData, согласия, роли, оплата не задеты).

## Задетые тесты (сверено ШТАБом @e4069b0)
- dayMarks.test.ts — старые тесты без правок (Д1; reportBody без ключа reflection; «прочее → retry» не содержит REFLECTION_REQUIRED); только новые тесты §9.
- dayScreen.test.ts — без правок (Д1).

## Канон и решения
(а) 03 §3.12 (через iter2-rest §1); DM 3.3, 3.10, 3.11 (шапка DayPage.tsx). (б) Противоречий с DECISIONS.md нет. (г) Правок канона нет.

## Вне задачи
Серверная проверка, лог, outbox — api-refl-1; доставка в тему — bot-group-1; кнопки модерации 13-M / 13-P и контент дня 13 (iter2-rest §4); показ истории рефлексий участнику.
