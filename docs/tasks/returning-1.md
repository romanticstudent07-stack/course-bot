# returning-1 — API: GET /onboarding/status + повторное согласие в first-launch

## 1. Паспорт
- id: returning-1 · PR: «returning-1: GET /miniapp/v1/onboarding/status, give при отзыве/смене текста»
- Ветка: feat/returning-1 · Режим: Р0+ · Зависит от: нет (main = #60). Миграции НЕТ.
- Область: только API (apps/api).

## 2. Цель
Сервер по initData говорит Mini App, кто открыл приложение: «returning» (свой номер),
«reconsent» (нужно заново дать C0/C1) или «new». first-launch начинает писать новый give,
если согласие по kind не действует (отозвано или сменился текст). Без этого повтор экранов
согласий даёт круг: give не пишется, а status снова отвечает «reconsent».

## 3. Решения Автора (дословно)
- 06.10, вариант А: «вернувшийся сразу видит номер; повтор экранов только при отзыве согласия /
  новой ver_of_text / erased». Срок отсутствия НЕ критерий; «ушёл совсем» — фазы FSM, не таймер.
- З1 вопрос 1 — Б: согласие «новое», только если изменился сам текст (сравнение с text_snapshot);
  версия файла legal.json — не критерий.
- З1 вопрос 3 — да: sleeping в этой пачке не трогаем, в D-22 «позже».

## 4. Выдержки и факты (архитектуру КОДЕР не читает)
- miniapp-api-contract.yaml, first-launch: «Идемпотентность через tg_user_id: повторный вызов
  возвращает существующий pid»; там же «уже данные согласия повторно не записываются» —
  меняется этой задачей (D-22), правка DOCS отдельно.
- D-15 (а), архив: «дано» решает ПОСЛЕДНЕЕ событие по kind (как fold_events в consents.py).
- SEAM-1 / D-9 п.2: 403 для неизвестного tg_user_id НЕ отдаётся.
- И1 Р243: после tombstone тот же tg_user_id получает НОВЫЙ pid.
- INV-1 / AGENT-BRIEF: participant_state пишет только проектор (с задержкой) — для решения
  «пускать ли» его и projector НЕ использовать; источник — только consent_events + text_registry.
- Проверено по коду main: text_snapshot = TextRegistry.body без преобразований; registry_version =
  версия файла seed (legal.json 0.2.0), поэтому ver_of_text в решении не участвует (ответ 1 Б).

## 5. ЧТО ПРОЧИТАТЬ (целиком)
- apps/api/app/routers/onboarding.py — 15 КБ (меняется; читать ЦЕЛИКОМ)
- apps/api/app/routers/consents.py — 6 КБ (меняется: _active_pid)
- apps/api/app/participants.py — 4 КБ (меняется)
- apps/api/app/db/models.py — 9 КБ (поля ConsentEvent, TgUserRegistry; не меняется)
- apps/api/tests/conftest.py — 6 КБ (фикстуры БД и initData, UNREACHABLE_DSN)
- apps/api/tests/test_consents.py — 9,5 КБ (образец: как в тесте вставить revoke)
Код ≈ 50 КБ + CODER.md 11 + AGENT-BRIEF.md 11 + STATE.md 16 + карточка ≈ 13.
Итог чтения КОДЕРА ≈ 100 КБ. test_first_launch.py (25 КБ) НЕ читать; если CI упадёт в нём —
открыть только упавший тест (AGENT-BRIEF §1, исключение).

## 6. Файлы
- создать: apps/api/app/consent_status.py
- создать: apps/api/tests/test_onboarding_status.py
- изменить: apps/api/app/routers/onboarding.py, apps/api/app/routers/consents.py,
  apps/api/app/participants.py
- main.py НЕ меняется: status живёт в роутере onboarding, он уже подключён через miniapp_v1.

## 7. Контракт и логика
### 7.1 consent_status.py (общий код для status и first-launch)
- Перенести сюда CONSENT_TEXT_KEYS и ConsentTextMissingError; onboarding.py импортирует их
  под теми же именами (существующие тесты импортируют их из onboarding — не ломать).
- snapshot_of(body: str) -> str — возвращает body без изменений. ЕДИНСТВЕННОЕ преобразование:
  first-launch пишет text_snapshot=snapshot_of(body), проверка сравнивает с snapshot_of(body).
- Чистая функция consent_problem(events, kind, current_key, current_body) -> None | "missing" |
  "revoked" | "text_changed"; events — строки (kind, action, text_key, text_snapshot) в порядке
  (at, id). Берётся ПОСЛЕДНЕЕ событие по kind: нет событий → missing; revoke → revoked;
  give с text_key != current_key или text_snapshot != snapshot_of(current_body) → text_changed;
  иначе None (действует).
- REASONS — закрытый перечень (порядок вывода такой же): C0_missing, C0_revoked,
  C0_text_changed, C1_missing, C1_revoked, C1_text_changed. reasons(...) -> список по kind C0, C1.
- load_events(session, pid) — SELECT kind, action, text_key, text_snapshot FROM consent_events
  WHERE pid ORDER BY at, id. current_texts(session, kinds) -> {key: body}; нет ключа →
  ConsentTextMissingError.
### 7.2 participants.py
- find_active_participant(session, tg_user_id) -> (pid, short_no) | None: та же выборка, что в
  get_or_create (tg_user_id и tombstoned_at IS NULL), без блокировки. consents._active_pid
  вызывает её (поведение /consents не меняется).
### 7.3 GET /miniapp/v1/onboarding/status (onboarding.py)
- Параметров и тела нет; tg_user_id — только из InitDataContext. Только чтение, без commit.
- 200, ровно одна из трёх форм (без null-полей; response_model_exclude_none или явные модели):
  - {"status":"returning","short_no":"#000001"} — активная строка есть, C0 и C1 действуют;
  - {"status":"reconsent","reasons":["C1_revoked"]} — строка есть, хоть одно не действует;
    short_no НЕ отдаётся (номер вернёт first-launch);
  - {"status":"new"} — строки нет ИЛИ строка tombstoned (erased). Тело побайтно одинаковое.
- pid в ответе нет никогда. Чужие данные запросить нельзя: параметров нет.
- 401 — require_init_data; 429 — rate_limit (B-1): оба через роутер miniapp_v1, как у всех.
- 503 SERVICE_UNAVAILABLE — БД недоступна; 503 SERVICE_MISCONFIGURED — нет текста C0/C1
  (fail closed, как first-launch). 403 не отдаётся.
- Лог одной строкой: «status: tg_user_id=%s status=%s». short_no, pid, reasons, initData,
  тексты в лог не пишутся.
### 7.4 first-launch (register_with_consents)
- Порядок шагов 1–5 не меняется: initData → тело → 18+ без БД → обязательные согласия → транзакция.
- Внутри транзакции: тексты (как сейчас) → get_or_create_participant (блокировка строки) →
  load_events ПОСЛЕ получения участника → для каждого ПРИСЛАННОГО kind: give пишется, только
  если consent_problem(...) is not None. Действующее согласие → 0 новых строк.
- Новый give: ver_of_text=registry_version (как сейчас), text_key, text_snapshot=snapshot_of(body).
- revoke не пишется и не меняется. participant_events — только при participant.created (как
  в projector-1); reconsent события НЕ пишет.
- Параллельные first-launch при reconsent защищены блокировкой строки: SELECT … FOR UPDATE в
  get_or_create держит её до commit; второй вызов читает события после commit первого и видит
  согласие действующим → 0 строк. В docstring — одна строка об этом.
- Ответ, коды и лог first-launch не меняются (consents_recorded = число новых give).

## 8. БД
Миграции нет. Таблицы не меняются (13 таблиц, alembic 0005). expected_tables.txt не трогать.

## 9. Тесты (apps/api/tests/test_onboarding_status.py; check.sh api; с БД — CI)
Правило для тестов 4 и 10: UPDATE text_registry фикстура не откатывает (тексты сидит миграция /
seed, а не транзакция теста) → исходный текст сохранить ДО UPDATE и вернуть в finally:
try: UPDATE … ; проверки  finally: UPDATE text_registry SET text = <исходный> WHERE key = …
(образец try/finally — test_backfill_0005 в tests/test_participant_events.py).
1. consent_problem — чистые случаи: give → None; give, revoke → revoked; revoke, give → None;
   give со старым snapshot → text_changed; give с другим text_key → text_changed; пусто → missing;
   порядок решает (at, id).
2. status returning: после first-launch тело == {"status":"returning","short_no":"#00000N"},
   ровно 2 ключа, ключа pid нет.
3. status reconsent (revoke C1, вставка строки revoke в тесте) → reasons == ["C1_revoked"], нет short_no.
4. status reconsent (UPDATE text_registry.text у legal.consent_c0_age_18_plus) → ["C0_text_changed"];
   try/finally — исходный текст вернуть.
5. status new: строки нет; строка tombstoned (UPDATE tombstoned_at=now()) → response.content
   обоих побайтно равны и == b'{"status":"new"}'.
6. 401 без заголовка initData.
7. у маршрута /miniapp/v1/onboarding/status среди зависимостей есть require_init_data и rate_limit.
8. лог (caplog): есть «status=returning» и tg_user_id; нет short_no, pid, «C1_», initData.
9. first-launch после revoke C1 → consents_recorded=1 (новый give только C1), потом status returning.
10. first-launch после смены текста C0 → новый give C0, text_snapshot == новый текст; status returning;
    try/finally — исходный текст вернуть.
11. повтор first-launch при действующих согласиях → 0 новых строк consent_events.
12. first-launch при reconsent → число participant_events не изменилось (одно, от создания).
13. status при недоступной БД → 503, code == "SERVICE_UNAVAILABLE": фикстура api_client
    (UNREACHABLE_DSN из conftest), как другие тесты 503.
Старые тесты first-launch и /consents должны остаться зелёными без правок.

## 10. Живые проверки (СЕРВЕРНЫЙ; бэкап не нужен — миграции нет)
ДО выкатки — один SQL обычным входом psql (выводит только kind, action, версию и true/false):
    SELECT ce.kind, ce.action, ce.ver_of_text, (ce.text_snapshot = tr.text) AS same_text
    FROM consent_events ce JOIN text_registry tr ON tr.key = ce.text_key
    ORDER BY ce.at, ce.id;
Ожидание: C0 и C1, action=give, same_text=true.
После мержа: пересобрать и перезапустить api И projector (общий код app/); 7/7 Up.
- GET /miniapp/v1/onboarding/status без initData → 401.
- С подписанной initData Автора (так же, как проверяли /consents в 1e-2) → при same_text=true:
  {"status":"returning","short_no":"#000001"}; если same_text=false → reconsent с C*_text_changed
  (это ожидаемо, не ошибка — сообщить ШТАБу).
- Лог api: строка «status: tg_user_id=… status=returning», без initData и номера.
- projector run без ошибок; state по-прежнему onboarding|1.

## 11. Запреты
- AGENT-BRIEF §3 целиком. participant_state, projector, participant_events НЕ читать для решения.
- Не менять порядок проверок first-launch, коды ответов, revoke, main.py, миграции.
- Не отдавать pid и чужие данные; не логировать short_no, тексты, initData, дату рождения.
- Не сравнивать ver_of_text; без новых зависимостей. docs/DEFECTS-FOUND.md не менять.

## 12. Готово, когда
CI 7/7 зелёный; тесты 1–13 есть; живые проверки §10 пройдены.

## 13. Оценка
Автор ~0,7 ч (КОДЕР 1 окно, CI 1–2 круга, РЕВЬЮЕР 1 окно); кредиты 0.

## 14. РЕВЬЮЕР: ДА (initData, согласия B-2: ветка решает, писать ли give; изоляция пользователей).

## Приложение. Запись D-22 — НЕ задача КОДЕРА
Записывает ШТАБ отдельной задачей CB-docs-3 после returning-2 (вместе с отметкой «е — исполнено»
и правкой контракта DOCS). Текст для ШТАБа:
    ## D-22. Вернувшийся участник: GET /onboarding/status и повторное согласие

    - **Файл архитектуры (зеркало):** `docs/architecture/build/miniapp-api-contract.yaml`
      (POST /onboarding/first-launch; пути status нет).
    - **Файл реализации:** `apps/api/app/routers/onboarding.py`, `apps/api/app/consent_status.py`;
      Mini App — `apps/miniapp/src/components/App.tsx`, `drafts.ts` (returning-2).
    - **Суть расхождения:** 1) в контракте нет способа узнать «кто я» без экранов 18+ и C1 —
      Mini App при каждом открытии проводил онбординг заново; 2) в контракте «уже данные согласия
      повторно не записываются» — после отзыва или смены текста повторное согласие не записалось
      бы (круг); 3) что видит в Mini App фаза sleeping — не определено.
    - **Решение Автора (06.10, вариант А; ответы З1 returning: 1 Б, 2 Б, 3 да):**
      а) GET /miniapp/v1/onboarding/status, 200 одной из форм: {status: returning, short_no} /
         {status: reconsent, reasons} / {status: new}; «нет участника» и «erased» — одно и то же
         тело; pid не отдаётся; 401/429/503 как у /miniapp/v1/**; 403 нет;
      б) reasons — закрытый перечень: C0_missing, C0_revoked, C0_text_changed, C1_missing,
         C1_revoked, C1_text_changed;
      в) «согласие действует» = последнее событие по kind — give, и его text_snapshot совпадает с
         текущим текстом ключа (одно преобразование snapshot_of при записи и проверке);
         ver_of_text (версия файла) — не критерий; participant_state не используется;
      г) first-launch пишет give по присланному kind, только если согласие не действует; revoke
         не трогает; participant_events — только при создании pid;
      д) sleeping — позже (задача, которая введёт /block);
      е) D-19 «Остаётся» (метка finished, 24 ч) — закрывается returning-2: при «Перейти к курсу»
         черновик стирается целиком, решение «пускать ли» принимает сервер.
    - **Правка DOCS:** отдельной пачкой после returning-2 — miniapp-api-contract.yaml: путь status,
      схема OnboardingStatus, перечень reasons, новый текст про повторный give в first-launch.
    - **Ждём решения Автора:** нет (правка DOCS — очередь ШТАБа).
