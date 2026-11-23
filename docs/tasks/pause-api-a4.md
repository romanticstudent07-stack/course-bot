# pause-api-a4 — POST /pause/cancel и /pause/resume: цель pause_id и X-Client-Op-Id

## 1. Шапка
- id: pause-api-a4 · заголовок PR: «feat(api): pause cancel/resume — цель pause_id и X-Client-Op-Id (pause-api-a4)»
- ветка кода: feat/pause-api-a4 · режим: Р1, Агент Opus (транзакция, замок, порядок отката и аудита) · РЕВЬЮЕР: да
- зависит от: pause-api-a1 (#284), pause-api-a2 (#286), обе смержены. Миграции нет.
- Бюджет чтения Агента: раздел 5 ≈ 69,2 КБ + AGENT-BRIEF.md 17,1 + DECISIONS.md 7,8 + CANON-CHECK.md 4,9 + карточка ≈ 13 = ≈ 112 КБ (≤ 135).

## 2. Цель
POST /pause/cancel и /pause/resume принимают X-Client-Op-Id (UUID4, обязателен) и тело {"pause_id": int} (обязательно). Сейчас _finish_pause сам выбирает строку из _OPEN_SQL по статусу, цели в запросе нет (по коду: routers/pause.py@8e7395f). Новая логика под замком participant:pid: проверка пары (pid, pause_id); повтор того же op с той же целью → прежний 202 без события; тот же op с другой целью → доказанная коллизия → rollback, запись client_op_id_conflict в security_events, 409 IDEMPOTENCY_CONFLICT. Бизнес-отказы — без аудита.

## 3. Решения Автора (дословно)
- R-2026-11-21.md «Область конфликтного 409»: «Очистка и аудит безопасности — только при доказанной коллизии op-id. Обычный бизнес-отказ — сообщение и перечитывание состояния, без удаления черновиков.»
- R-2026-11-21.md «Носитель события client_op_id_conflict (22.11.2026)»: «событие client_op_id_conflict пишется долговечной записью в новую отдельную таблицу security_events, в отдельной транзакции, чтобы запись не терялась при откате транзакции запроса перед ответом 409.»
- AGENT-BRIEF §7: «Идемпотентность: client_op_id обязателен для финансовых и state-меняющих операций.»

## 4. Выдержки архитектуры (Агент docs/architecture не открывает)
- И2 §idempotency_keys: «client_op_id_required: true»; «same_result: return cached result_ref»; «conflicting_params: return 409 + log conflict event» (по docs/research/miniapp-pause-canon.md, таблица «Основания и минимальный контракт»).
- И4 §R339_indexeddb_cache: «retry_policy: exponential backoff, per client_op_id»; «idempotency: client_op_id from И2 idempotency_keys».
- Вывод исследования miniapp-pause-canon.md: «cancel/resume не получают цель и op-id; под замком заново выбирают подходящую строку… GET перед POST оставляет гонку: исходная пауза может исчезнуть, а другая — открыться. Один UUID без цели не устраняет её при первой доставке.» Сохранить: проверки статуса, ключей часов и ключи действий по pause_id.
- OVERRIDES §AD-01: бизнес-409 без аудита; §AD-03: TTL 3650 days для ключей пауз.

## 5. ЧТО ПРОЧИТАТЬ (целиком)
- apps/api/app/routers/pause.py — 26,9
- apps/api/app/day_keys.py — 8,4
- apps/api/tests/test_pause_api_db.py — 18,9
- apps/api/tests/test_pause_api.py — 3,1
- apps/api/tests/test_day_current.py — 11,9
Итог раздела ≈ 69,2 КБ. app/security_events.py не читать и не менять: сигнатура видна из вызова в _run.

## 6. Файлы
Изменить: apps/api/app/routers/pause.py; apps/api/app/day_keys.py; apps/api/tests/test_pause_api_db.py; apps/api/tests/test_pause_api.py; apps/api/tests/test_day_current.py. Создать и удалить — нет.

## 7. Контракт и логика
Запрос: заголовок X-Client-Op-Id — Annotated[UUID4, Header(alias=CLIENT_OP_ID_HEADER)], как у /pause/request; тело PauseTargetIn {pause_id: int = Field(ge=1)}. Нет заголовка, не UUID4, нет тела, pause_id не целое или < 1 → 422 VALIDATION_ERROR. Нет initData → 401 раньше 422 (require_init_data на роутере, main.py).
Ответы: 202 {"status": "accepted"}; 404 PARTICIPANT_NOT_FOUND; 409 PAUSE_NOT_CANCELLABLE (cancel) / PAUSE_NOT_ACTIVE (resume) / IDEMPOTENCY_CONFLICT; 422; 503. В responses маршрутов дописать IDEMPOTENCY_CONFLICT и 422.
day_keys.py [ШТАБ-тех; И4 per client_op_id; AD-03]:

    KIND_PAUSE_OP = "pause_op"
    TTL_PAUSE_OP = "3650 days"   # в TTL_BY_KIND, станет 15 видов
    def key_pause_op(pid, op_id) -> str: f"{KIND_PAUSE_OP}:{pid}:{op_id}"

Строку ключа дописать в docstring: pause_op:{pid}:{op_id} — cancel или resume по client_op_id; result_ref = pause_id, params_hash — хеш цели (pause-api-a4; пишет routers/pause).
pause.py, новое [ШТАБ-тех]:

    OP_KIND_CANCEL = "pause_cancel"; OP_KIND_RESUME = "pause_resume"
    ACTION_CANCEL = "cancel"; ACTION_RESUME = "resume"
    def _target_hash(action, pause_id) -> str:
        sha256(json.dumps({"action": action, "pause_id": pause_id},
               sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    _TARGET_SQL: SELECT id, status FROM participant_pauses
        WHERE pid = :pid AND id = :pause_id AND kind = 'user'
    class _OpIdConflict(Exception): pid, op, op_kind

Канонизация в _target_hash та же, что в _params_hash (a2); _params_hash не трогать.
Вынос без изменения поведения (единственное место в request): _OpIdConflict получает поле op_kind; _repeat вызывает _OpIdConflict(pid, op, OP_KIND_REQUEST); _run пишет op_kind=exc.op_kind вместо константы. Для /pause/request запись в security_events та же (op_kind pause_request).
_finish_pause(session, tg_user_id, op_id, pause_id, now, *, action, op_kind, statuses, clock_key, own_kind, own_key, event_kind, payload_extra, refuse). Порядок под замком, одна транзакция:
1) active_pid_locked — нет → 404.
2) op = str(op_id), h = _target_hash(action, pause_id), ключ key_pause_op(pid, op), чтение _KEY_HASH_SQL. Ключ есть: hash равен → commit, «repeat», 202 без проверок и без события; не равен (в том числе NULL) → raise _OpIdConflict(pid, op, op_kind).
3) _TARGET_SQL; строки нет (чужая или нет такой паузы) или status не в statuses → refuse() → 409 без аудита [ШТАБ-тех Б1; R-2026-11-21, AD-01]. Ответ одинаковый — чужие паузы не раскрываются.
4) ключ часов clock_key(pid, pause_id) есть → refuse() (как сейчас).
5) INSERT own_key(pid, pause_id) через _INSERT_KEY_SQL (ON CONFLICT DO NOTHING, как сейчас). Пусто → действие уже сделано другим op: шаг 7, commit, «repeat», 202 без события.
6) событие (как сейчас): pause_cancel {"pause_id"} / pause_ended {"pause_id", "reason": "by_participant"}, at = now.
7) INSERT ключа pause_op через тот же _INSERT_REQUEST_KEY_SQL, что у pause_request в a2 (без ON CONFLICT): kind pause_op, ttl TTL_BY_KIND, ref = str(pause_id), h. Конфликт → IntegrityError → 503 (под замком невозможен).
8) commit → «accepted».
_run: ветка _OpIdConflict не меняется, кроме op_kind=exc.op_kind: сначала _rollback(session), затем record_security_event(session.get_bind(), …); False → всё равно 409 IDEMPOTENCY_CONFLICT.
cancel_pause / resume_pause передают op_id и pause_id; маршруты — body: PauseTargetIn и client_op_id, как post_pause_request.
Ограничение [ШТАБ-тех]: тот же op на /pause/request и на cancel/resume не сверяется (разные виды ключа) — клиент даёт новый UUID на каждую операцию.
Старые ключи pause_cancel:{pid}:{pause_id} / pause_resume:{pid}:{pause_id} остаются маркером действия; ключ pause_op и маркер — одна транзакция [ШТАБ-тех г]. Часы (pause_ops.py) читают и пишут только pause_start / pause_end, ключей pause_cancel, pause_resume, pause_op не видят (по коду: pause_ops.py@8e7395f, _INSERT_KEY, plan).
Логи: формат прежний — tg_user_id и итог (accepted / repeat / код; при коллизии audit=ok|failed). pid, op, pause_id, initData не писать. Docstring pause.py: разделы cancel/resume и строку «без тела» переписать по этому разделу.

## 8. БД
Миграции нет [ШТАБ-тех]: params_hash есть в idempotency_keys с 0007; права app_api (SELECT, INSERT idempotency_keys; INSERT security_events 0022) достаточны. CHECK 0022 op_kind: «op_kind IS NOT NULL AND char_length(op_kind) BETWEEN 1 AND 64» — pause_cancel и pause_resume подходят. expected_tables.txt не меняется.

## 9. Тесты
test_pause_api.py (без БД):
- test_target_validation_is_422 (parametrize по cancel и resume × 4: нет X-Client-Op-Id; op uuid1; нет тела; {"pause_id": "x"}) → 422 VALIDATION_ERROR.
- test_no_init_data_without_body_is_401 (cancel, resume; без тела и заголовка) → 401 TG_INIT_MISSING.
test_pause_api_db.py (tg_user_id 8841–8850; security_events — через db_engine владельцем):
- test_cancel_other_op_same_pause_no_event: cancel op1 → 202; cancel op2 тот же pause_id → 202; событий 1; оба ключа pause_op есть.
- test_op_collision_other_pause_id: cancel op → 202; тот же op с другим pause_id → 409 IDEMPOTENCY_CONFLICT; security_events [("client_op_id_conflict", "pause_cancel", op)]; событий 1.
- test_op_collision_cancel_then_resume: cancel op → 202; resume тем же op → 409; security_events [("client_op_id_conflict", "pause_resume", op)].
- test_foreign_pause_409_no_audit: пауза участника A; cancel от B с её pause_id → 409 PAUSE_NOT_CANCELLABLE; resume от B с active-паузой A → 409 PAUSE_NOT_ACTIVE; событий 0, ключей pause_cancel/pause_resume A нет, security_events B пусто.
- test_target_is_given_pause: строка ended (pause_id X) и строка requested (Y); cancel с X → 409 PAUSE_NOT_CANCELLABLE; ключа pause_cancel для Y нет, событий 0.
- test_target_audit_after_rollback: как test_audit_after_rollback, сценарий cancel с другим pause_id; перед «audit» — «rollback».
test_pause_api.py::test_key_formats — дописать key_pause_op, KIND_PAUSE_OP == "pause_op", TTL 3650 days.
Цели: bash tools/check.sh api. Только CI: тесты с БД (REQUIRE_DB_TESTS=1).

## Задетые тесты (правило «Т»; строки — по имени функции, main 8e7395f)
- test_pause_api.py::test_no_init_data_is_401 — для cancel/resume в kwargs json {"pause_id": 1} (заголовок уже есть). test_key_formats — см. раздел 9.
- test_day_current.py::test_kinds_and_ttl — в полное равенство TTL_BY_KIND добавить "pause_op": "3650 days",  # pause-api-a4.
- test_pause_api_db.py: _cancel и _resume → (client, user_id, pause_id, op=None): заголовок X-Client-Op-Id (op или uuid4), json {"pause_id": pause_id}. test_cancel_and_repeat — повтор тем же op (_cancel(..., pause_id, op=op) дважды), событий 1, плюс ключ pause_op есть; test_cancel_after_clock_start_key, test_resume_after_clock_end_key, test_resume_and_repeat (повтор тем же op), test_db_error_is_503_and_rolls_back (ключ pause_op тоже не создан), test_log_has_no_pid_or_op — передать pause_id; test_resume_not_active — pause_id созданной заявки; test_cancel_without_open — pause_id = 999999 (строки нет) → 409 PAUSE_NOT_CANCELLABLE.
- Регрессия, не менять (по карточке pause-api-a2, по одному ключу TTL_BY_KIND): test_clocks_1.py:79, test_day_clock.py:262–263, test_notify_ladder.py:127, test_notify_noon.py:95, test_notify_ops.py:95. Тесты request и GET — не менять.
Тест вне списка упал → не чинить, «тест X вне списка» в ИТОГ.

## Канон и решения
(а) И2 §idempotency_keys; И4 §R339_indexeddb_cache; OVERRIDES §AD-01…AD-04; R-2026-11-21 «Область конфликтного 409»; build/miniapp-api-contract.yaml раздел /pause/cancel и /pause/resume.
(б) Код противоречит выводу miniapp-pause-canon.md (цели и op-id нет) — чинит эта задача. DECISIONS.md противоречий не даёт.
(в) Normative — правок нет. miniapp-api-contract.yaml (/pause/cancel и /pause/resume: X-Client-Op-Id, тело pause_id, 409 IDEMPOTENCY_CONFLICT) — ШТАБ отдельным циклом DOCS после мержа; в эту карточку не входит.
(г) Правок normative нет.

## 10. Живые проверки
Выкат позже (PLAN §4; очередь SHTAB-DEBTS §1, с образом api после 0022). После выката: повтор cancel тем же op с другим pause_id → 409 IDEMPOTENCY_CONFLICT; под владельцем SELECT count(*) FROM security_events — +1.

## 11. Запреты
AGENT-BRIEF §3. Не трогать: security_events.py, participant_lock.py, pause_ops.py, миграции, expected_tables.txt; /pause/request и GET — только вынос op_kind (раздел 7). Под app_api — без SELECT и RETURNING по security_events. record_security_event — только после rollback. В лог не писать pid, op, pause_id, initData. Без новых зависимостей. Без heredoc.

## 12. Критерии готовности
Файлы раздела 6; check api зелёный; CI api зелёный; задетые тесты исправлены по списку; описание PR по AGENT-BRIEF §10.

## 13. Оценка
Часы Автора ≈ 0,5. Кредиты: Opus ≈ 600–850 (по факту a2: оценка 550–800, факт 752; 3 файла «Задетых» включены).

## 14. РЕВЬЮЕР
Да: привязка pid к pause_id из initData, коллизия op-id, аудит в отдельной транзакции после отката, бизнес-409 без аудита, чужие паузы не раскрываются.
КОНЕЦ ЧАСТИ 1 из 1: файлов 1
