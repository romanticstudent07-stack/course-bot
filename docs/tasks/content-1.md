# content-1 — дни 3–6 модуля 1 (заглушки)

## 1. Паспорт
- id: content-1 · PR: «feat(content): дни 3–6 модуля 1 — заглушки (content-1)» · ветка: feat/content-1
- Режим: Р0+ (бесплатный КОДЕР) · зависит: — (миграции нет) · пачка iter2-rest, шаг 1 из 6.

## 2. Цель
Дать А1 пройти дни 3–6 на IRONCLAD (тест дня рефлексии 6, research iter2-rest.md §5).
Четыре файла контента по образцу day_02.json и 40 ключей-заглушек B9. Код не трогать.

## 3. Решения
- В3 = Б [Автор 30.10, К-6]: «общая механика 6/13-M/13-P сейчас; вердикт, фазы, тайная пауза и оплата — позже; контент дня 13 не добавлять до модерации» (research §9).
- Ш1 [ШТАБ]: «заглушки дней 3–6 + CI» (research §9).
- §3 (а) [Автор В1 А, В3 Б]: «День рефлексии — день 6 любого модуля и день 13» — определяет код по day_no (api-refl-1); поля рефлексии в контенте нет [ШТАБ, указание окну К-1].
- Тексты курса до 0-Б — только заглушки [DESIGNER «Правила»; README «Публичный репо»].

## 4. Выдержки канона
- 03 §3.12 (research §1): «рефлексия — обязательное поле отчёта дней 6, 13-M, 13-P» — делает api-refl-1, не эта задача.
- 03 §3.14 (research §4): «авто-прохода нет»; passed на дне 13 увёл бы участника на день 14 → день 13 и дальше НЕ добавлять.
- По коду (research §2, routers/day.py): «passed → day_no + 1, только если день есть в контенте». После выката passed на дне 2 ведёт на день 3; на дне 6 участник остаётся (дня 7 нет).

## Канон и решения
(а) 03 §3.12, §3.14 (выдержки research §1, §4). (б) Противоречий с DECISIONS нет. (г) Правок канона нет.

## 5. ЧТО ПРОЧИТАТЬ (КОДЕР)
- apps/api/content/module_1/day_02.json — 0,9 КБ
- apps/api/content/day.schema.json — 1,6 КБ
- apps/api/config/texts/day.json — 7,1 КБ
- apps/api/tests/test_day_content.py — 4,7 КБ
Чтение КОДЕРА ≈ 14,3 КБ.

## 6. Файлы
- Создать: apps/api/content/module_1/day_03.json, apps/api/content/module_1/day_04.json, apps/api/content/module_1/day_05.json, apps/api/content/module_1/day_06.json.
- Изменить: apps/api/config/texts/day.json; apps/api/tests/test_day_content.py.
- Удалить: —.

## 7. Контракт
API не меняется. Файл day_NN.json (NN = 03, 04, 05, 06) — копия day_02.json, отличия:
- "day_no": N (3, 4, 5, 6);
- во всех title_key и help_key d02 → dNN (пример: B9.day_m1_d03_task_1_title);
- stage_no 1, module_no 1, min_optional 2, пять блоков task_1…task_5, critical только у task_1 — как в day_02 [ПРОЕКТИРОВЩИК-тех: один образец, схему проверит загрузчик];
- новых полей нет (в схеме additionalProperties: false).
day.json:
- "version": "0.5.0" → "0.6.0";
- 40 новых записей сразу после B9.day_m1_d02_task_5_help, порядок: d03 task_1 title, help, task_2 title, help … d06 task_5 help;
- key B9.day_m1_dNN_task_K_title → text «[ЗАГЛУШКА] Модуль 1, день N: название задания K.»;
- key B9.day_m1_dNN_task_K_help → text «[ЗАГЛУШКА] Модуль 1, день N: справка к заданию K.»;
- N в тексте без нуля (день 3), K = 1…5; tone neutral, legal_status pre-legal-review;
- у первой новой записи notes: «content-1: дни 3–6 модуля 1. Заглушки до 0-Б.»;
- прочие записи файла не трогать.

## 8. БД
Нет.

## 9. Тесты
- test_day_content.py::test_stub_content_is_valid — дописать: для d в 3, 4, 5, 6 content.get(1, 1, d) не None и в нём 5 блоков; content.get(1, 1, 7) is None; content.get(1, 1, 13) is None (страж research §4).
- Без правки покрывают задачу: test_day_content.py::test_all_title_and_help_keys_in_seed (ключи дней 3–6 есть в seed); test_texts.py::test_all_seed_entries_are_placeholders; test_texts.py::test_load_seed_reads_repo_files.
- Codespaces: bash tools/check.sh api. Только CI: test_texts с БД (test_load_twice_same_rows — 79 записей).

## Задетые тесты (правило «Т»)
- apps/api/tests/test_day_content.py — правка из раздела 9 (усиление, не поломка).
- Проверено чтением: test_texts.py — счёт текстов динамический (len(entries)), версию day.json не сверяет → правки нет.
- Не проверено (ШТАБ сверяет до мержа): тесты на реальном контенте с допущением «после дня 2 следующего дня нет». Поиск: grep -n "day_no\|next_position" в apps/api/tests/test_day_report_submit.py, test_day_queue.py, test_projector_day_report.py, test_day_current.py. Если нашлось — правка: в тесте последним днём взять 6 или подать временный каталог (load_day_content(tmp_path)).

## 10. Живые проверки (после мержа, IRONCLAD, только main, СЕРВЕРНЫЙ)
Схема БД не меняется — бэкап не нужен. Число текстов:
- до: text_registry 39 (ladder-1 выкачен) или 36 (не выкачен);
- после: 79 (B4 8 + legal 4 + day 67).
Шаги:
1. git pull; DC --profile tools build migrate (новые тексты — build migrate до texts load).
2. DC --profile tools run --rm --no-deps migrate python -m app.texts load → «загружено 40, обновлено 39, лишних в БД 0» (если ladder-1 не был выкачен: «загружено 43, обновлено 36, лишних в БД 0»).
3. DC build api && DC up -d api → в логе api «контент дня: загружено дней 6»; /healthz 200; 7/7 Up, 5 healthy.
4. А1: после passed на дне 2 и следующего 04:00 — день 3 с пятью заданиями-заглушками.
Когда выкатывать, решает ШТАБ (вопрос Ш-3): до выката clocks-1 и api-refl-1 пропуск дня 6 считается обычным пропуском, а поля рефлексии нет.

## 11. Запреты
AGENT-BRIEF §3. Плюс: не добавлять day_07 и дальше, в том числе день 13; не добавлять поле рефлексии ни в контент, ни в схему; не менять day.schema.json, app/day_content.py, routers; тексты — только «[ЗАГЛУШКА] …».

## 12. Критерии готовности
4 файла дней загружаются; в day.json 40 новых ключей, версия 0.6.0; check.sh api зелёный; CI 7/7; на сервере 79 текстов и 6 дней.

## 13. Оценка
Часы Автора 0,5 (пакет + выкат). Кредиты 0 (Р0+).

## 14. РЕВЬЮЕР
Нет: initData, 18+, согласия, rate-limit, роли/GRANT БД и оплата не затронуты.
