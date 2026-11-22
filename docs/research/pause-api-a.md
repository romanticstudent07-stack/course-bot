# pause-api-a — З1

Срез `4ea7fd7940953fb95c15fdc5e6567b0ff1b54759`. Все пути — @4ea7fd7. A=apps/api; T=A/tests; M=A/migrations/versions; N=docs/architecture/normative; P=docs/process; D=docs/decisions; R=docs/research. Пункты 1–4 #272 закрыты частично; пункт 5 вне окна. Карточка A не готова.

## 1. Аудит

[канон N/I2-wave-b.md §idempotency_keys.behavior_on_collision; N/I4-wave-d.md §R339] «same_result: return cached result_ref»; «conflicting_params: return 409 + log conflict event»; «log: security_audit event client_op_id_conflict». [Автор, канон проверен И4 §AD-01] D/R-2026-11-21.md и N/OVERRIDES.yaml §AD-01: бизнес-409 — сообщение и перечитывание, без аудита и wipe. Q1–Q3 не переоткрывать.

| Звено | Закрыто: путь@4ea7fd7 / блокер |
|---|---|
| Событие/producer | Имя и триггер закрыты по И2/И4/AD-01. [ШТАБ-тех; по коду: A/app/routers/pause.py] Обе ветки повтора request не сверяют аргументы; producer не установлен. |
| Формат/фильтр | [ШТАБ-тех; AGENT-BRIEF.md §3] Секреты, initData и ПДн не логировать. Схема и корреляторы не установлены. |
| Транспорт | [ШТАБ-тех; по коду: A/main.py] basicConfig не доказывает доставку; транспорт не установлен. |
| Приёмник/хранение | [ШТАБ-тех; R/pause-api-preflight.md] CSP и privacy_audit_log не подтверждены как приёмники коллизий. Приёмник, фиксация и срок не установлены. |
| Права | [ШТАБ-тех; по коду: M/0001:153] SELECT audit_reader на privacy_audit_log не доказывает INSERT app_api. Права канала не установлены. |
| Проверка | [ШТАБ-тех; по коду: T/test_pause_api_db.py] test_log_has_no_pid_or_op проверяет app.pause, не доставку и сохранение security_audit. |

[ШТАБ-тех; по коду: A/app/routers/pause.py] `_released/_run` откатывают транзакцию на HTTPException: INSERT аудита в ней перед 409 потеряется. По двум именам в apps 0 совпадений; иной канал не исключён. Сквозной контракт: [DATA NOT AVAILABLE].

**К-4 №1 — отложен до дочитывания.** Канон: проверено И2 §behavior_on_collision, И4 §R339.conflict_ux и строки §AD-01, OVERRIDES §AD-01/02 частично — о доставке в прочитанном молчит: «log: security_audit event client_op_id_conflict» задаёт событие. Если обязательный канал не найден: существующий совместимый канал (меньше изменений, нужна проверка); структурированный серверный канал (не зависит от получения 409, нужна гарантия доставки); долговечная запись с доставкой (проверяемая фиксация, нужны DDL и права). Предпочтение: сначала проверить первый, иначе третий вариант. Серверное событие не считать заменой обязанности И4 без сверки. Политика отказа открыта. [ШТАБ-предложение, К-4]

## 2. DDL, права, данные

[ШТАБ-тех; по коду: M/2026_11_16_1200-0018_pauses_pauses.py] Закрыто: `participant_pauses`: `id` bigint auto PK; `pid` UUID FK → `tg_user_registry.pid`; `kind,status,client_op_id` text; `start_at,planned_end_at,created_at` timestamptz, `created_at DEFAULT now()`; nullable только `ended_at` timestamptz и `stage_no,restart_no` smallint. UNIQUE `(pid,client_op_id)`. CHECK: kind user/author/shadow; status requested/approved/active/ended/cancelled/rejected; конец > старта; user ≤169 часов; user active/ended требует stage/restart; ended требует ended_at; stage>=1/restart>=0 если заданы; длина op 1–64, не UUID-check. Частичные UNIQUE `participant_pauses_{one_active_uq,one_open_user_uq,stage_taken_uq}`: (pid) active; (pid) user requested/approved; (pid,stage_no,restart_no) user active/ended.

[ШТАБ-тех; по коду: M/0018] app_api: колоночный SELECT всех тогдашних колонок пауз, INSERT только `(pid,kind,status,start_at,planned_end_at,client_op_id)`, USAGE `participant_pauses_id_seq`, колоночный SELECT `pause_budgets`. UPDATE/DELETE 0018 не выдаёт. Сумма 0001–0021 — блокер [DATA NOT AVAILABLE]: grep не раскрывает аргументы генераторов. SELECT state, INSERT events, SELECT/INSERT keys описаны в pause.py, не сверены по всей цепочке.

[ШТАБ-тех; по коду: A/app/routers/pause.py] Request хранит op и вычисленные даты, не исходные days; ответ повтора из текущей строки. Cancel/resume атомарно пишут событие и action-ключ по pid/pause_id с `result_ref=str(pause_id)`, без `params_hash`. #272 @4319d0d: 0007 содержит nullable `params_hash` и `result_ref`; точное DDL не дочитано. Отпечаток не исходные аргументы, ссылка не снимок ответа. [канон И2 §idempotency_keys, по #272] default TTL 1h, почасовой GC; TTL не дедлайн намерения. Реализация GC не установлена [DATA NOT AVAILABLE]: найденные DELETE — ролевой тест. Утрата квитанции не разрешает повторное применение. Хранение, совместимость, срок восстановления — блокер.

## 3. InitData, поколение, замки

[ШТАБ-тех; по коду: A/app/telegram_init_data.py:81, A/main.py, A/app/routers/pause.py] Определение InitDataContext найдено; POST берут `ctx.tg_user_id` через require_init_data; initData перед rate-limit. [ШТАБ-тех; по коду: A/app/participants.py] Активная запись — `tombstoned_at IS NULL`; INSERT с `uuid.uuid4()` даёт новый pid при прежнем Telegram ID после tombstone. Маркер поколения не установлен.

[ШТАБ-тех; по коду: A/app/participant_lock.py, A/app/routers/pause.py] POST: поиск → advisory xact-lock `participant:pid` через hashtext → обычный SELECT активного pid, без FOR UPDATE → запись. Нет pid — нет записи; commit/rollback у вызывающего. Registry FOR UPDATE в first-launch не заменяет замок. В 24 строках tombstone фильтр не показал SET/values/прямого присваивания `tombstoned_at`; это не исключает писателей. Сериализация с erasure: [DATA NOT AVAILABLE].

[Автор, канон проверен D/R-2026-11-21.md; ШТАБ-тех, рекомендация] Под замком: владелец/поколение → сверка неизменных аргументов и цели того же pid → если первое применение, исходная дата и бизнес-условия → атомарный результат и квитанция. Чужая цель не доказывает коллизию. Поздняя доставка — отказ и новое подтверждение либо прежний результат при доказанном повторе. Поля не назначать; старый POST не fallback.

## 4. Правило Т

[ШТАБ-тех; по коду: T/test_pause_api.py, T/test_pause_api_db.py] Прямые совпадения по POST и именам функций — только эти файлы:
- `test_pause_api.py`: сохранить 401 и 422 для days; missing/non-v4 op расширить на cancel/resume; проверить цель/поколение по контракту. `test_key_formats`: сохранить action-ключи/TTL.
- `test_pause_api_db.py`: обновить `_request/_cancel/_resume`; `test_request_repeat_same_op` разделить: равные аргументы → прежний ответ, разные days → 409/аудит, одна строка. Сохранить создание, GET, 404, `test_request_other_op_already_open` и `test_refused_{block_lives,state,gap_24h,stage_taken,no_budget}` без аудита. `test_get_without_budget_row`: словарь менять только при изменении GET.
- `test_{cancel,resume}_and_repeat`: повтор после смены статуса/паузы без второго события. Сохранить `test_cancel_after_clock_start_key`, `test_resume_after_clock_end_key`, `test_cancel_without_open`, `test_resume_not_active` с валидной целью; 422 тестировать отдельно. `test_db_error_is_503_and_rolls_back` дополнить откатом квитанции; `test_log_has_no_pid_or_op` сохранить. Добавить смену владельца/поколения, tombstone, чужую цель, позднюю доставку, параллельные повторы, утрату квитанции и отказ аудита.

[ШТАБ-тех; по коду: T/test_day_current.py:78–84, T/test_db_models.py, .github/workflows/ci.yml:96–103] Новый kind → обновить полное равенство `test_kinds_and_ttl`; отдельные TTL в day_clock/clocks_1/notify_ladder/notify_noon/notify_ops не менять автоматически. Новая таблица → полный T/expected_tables.txt; сравнения схемы в CI и test_db_models.py сохранить; .github не править. Сверить `test_expected_tables_count_after_0019` и при необходимости обновить счётчик; `test_expected_tables_file_includes_0001` сохранить. Имя теста равенства и полный список зависимостей не установлены.

[ШТАБ-тех; по коду: T/test_pause_api_db.py, T/conftest.py (имена)] Сохранить api_client, db_api_client, db_engine, valid_init_data, grant_access, override часов и first-launch с доступом. Подготовка владельцем не доказывает права app_api. Для новой схемы/ACL проверить минимальные права и отказ лишних UPDATE/DELETE; точные правки ролевых тестов — блокер.

## Разбивка и дочитывание

[ШТАБ-тех, рекомендация] A1 — аудит, квитанции, права; DDL только при обосновании, без номера. A2 после A1 — три POST и тесты. Цикл DOCS до реализации; порядок A→B→C.

Надо дочитать после решения ШТАБа:
1. И2 §idempotency_keys, И4 §AD-01/R339.conflict_ux, OVERRIDES §AD-01/02, два совпадения И3; затем N/errata-unified.md и docs/architecture/{14*,15*,build/db-schema.sql,build/miniapp-api-contract.yaml} узко по аудиту; A/app/routers/security.py.
2. Генераторы ACL и аргументы 0001–0021; DDL 0007, модель и точки запуска GC.
3. Совпадения tombstone (пути в журнале), модель и фактические erase-писатели; A/app/pause_ops.py по замкам часов; тело InitDataContext и выдачу привязки.
4. T/conftest.py, expected_tables.txt, test_db_models.py и test_db_roles_0007/0018/0021.py; A/app/{day_keys,day_report,db/models}.py; T/test_day_{current,clock,reflection,report_submit,report_unit}.py, test_clocks_1.py, test_notify_{ladder,noon,ops}.py — связи ключей и списков. A/app/routers/day.py и T/test_db_roles_0018.py — только совпадения и до 30 строк контекста.

## Прочитано

Целиком, Б (КБ = Б/1000); DECISIONS первым:

| Путь | Б | Факт |
|---|---:|---|
| D/DECISIONS.md | 7809 | Приоритет решений. |
| P/DESIGNER.md | 21971 | Бюджет и правило Т. |
| P/PACK.md | 12747 | Метка конца есть. |
| P/CANON-CHECK.md | 4856 | К-4/К-6. |
| docs/STATE.md | 16282 | A→B→C. |
| AGENT-BRIEF.md | 17110 | Логи и стандарт PR. |
| D/R-2026-11-21.md | 4317 | Q1–Q3; поля не утверждены. |
| R/pause-api-preflight.md | 20864 | Долги аудита, прав и Т. |
| R/miniapp-pause-canon.md | 23560 | Инварианты A. |
| A/app/routers/pause.py | 21186 | Нет сверки; finish выбирает цель заново. |
| A/app/participants.py | 4791 | Новый pid после tombstone. |
| A/app/participant_lock.py | 3300 | Повторный SELECT под замком. |
| T/test_pause_api.py | 2339 | 401/422 и TTL. |
| T/test_pause_api_db.py | 14266 | Регрессии POST и rollback. |
| A/main.py | 6677 | Общая auth/rate-limit. |
| M/2026_11_16_1200-0018_pauses_pauses.py | 14475 | DDL и колоночные права. |

Целиком 196550 Б; с фрагментами и именами 200062 Б без повторов, 200727 Б с ними. Лимит 200000 Б превышен. Полный журнал и grep — в ответе. Репозиторий не менялся, проверки не запускались.
