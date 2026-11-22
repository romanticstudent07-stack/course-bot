# pause-api-a2 — POST /pause/request: сверка параметров повтора, аудит коллизии op-id, start_date

## 1. Шапка
- id: pause-api-a2 · заголовок PR: «feat(api): pause/request — сверка повтора, аудит коллизии, start_date (pause-api-a2)»
- ветка: feat/pause-api-a2 · режим: Р1, Opus; запуск — только после «да» Автора · РЕВЬЮЕР: да
- зависит от: pause-api-a1 (#284, смержен: security_events 0022, app/security_events.py). Миграции нет, номер 0023 не занимается.
- Почему Агент, а не КОДЕР: apps/api/app/routers/pause.py ≈21,2 КБ — больше 350 строк, КОДЕРУ целиком не выдаётся (урок 22.11-б); деление на 2 задачи режет одну функцию request_pause. Агент правит файлы в репо сам, без пакета и без heredoc. Opus — порядок транзакции, отката и аудита (решение ШТАБа 22.11).
- Бюджет чтения Агента (≤ 135 КБ): AGENT-BRIEF.md 17,1 + DECISIONS.md 7,8 + CANON-CHECK.md 4,9 + карточка ≈12 + раздел 5 без test_day_current.py 47,4 = ≈89,2 КБ + test_day_current.py (размер — ШТАБ; больше 20 КБ → читать только test_kinds_and_ttl и импорты).

## 2. Цель
POST /pause/request сверяет параметры повтора по params_hash в idempotency_keys: тот же op с теми же параметрами → прежний результат; с другими → доказанная коллизия: откат сессии запроса, запись client_op_id_conflict в security_events отдельной транзакцией, 409 IDEMPOTENCY_CONFLICT. Новое обязательное поле start_date: дата не сдвигается молча — не совпала с серверной → 409 PAUSE_REFUSED start_date_passed. Бизнес-409 — без аудита. cancel/resume не меняются: op-id у них нет (по коду: pause.py, _finish_pause).

## 3. Решения Автора (дословно)
- R-2026-11-21.md «Поздняя первая доставка»: «Не сдвигать дату автоматически. Если операция ещё не применена и исходная дата уже недопустима — показать отказ и запросить новое подтверждение. Если применена — вернуть прежний результат. Не вводить часовой срок намерения.»
- R-2026-11-21.md «Область конфликтного 409»: «Очистка и аудит безопасности — только при доказанной коллизии op-id. Обычный бизнес-отказ — сообщение и перечитывание состояния, без удаления черновиков.»
- R-2026-11-21.md «Носитель события client_op_id_conflict (22.11.2026)»: «событие client_op_id_conflict пишется долговечной записью в новую отдельную таблицу security_events, в отдельной транзакции, чтобы запись не терялась при откате транзакции запроса перед ответом 409.»
- R-2026-11-21.md «Поздняя доставка: форма (22.11.2026)» [Автор 22.11, К-4 №1 = А]: «клиент присылает в POST /pause/request дату начала паузы start_date (местная дата, YYYY-MM-DD), подтверждённую участником. Операция ещё не применена, а дата уже не совпадает с датой, которую сервер считает началом паузы, — отказ 409 PAUSE_REFUSED (reason start_date_passed) и новое подтверждение; применена — прежний результат. start_date входит в сверку параметров повтора.»

## 4. Выдержки архитектуры (Агент docs/architecture не открывает)
- И2 §idempotency_keys.behavior_on_collision: «same_result: return cached result_ref»; «conflicting_params: return 409 + log conflict event» (по docs/research/pause-api-a.md §1).
- И2 §idempotency_keys: params_hash_optional; по коду 0007: params_hash text NULL, app_api — SELECT и INSERT на всю таблицу, UPDATE/DELETE нет ни у кого; GC нет (pause-api-a2.md §2).
- И4 §R339.conflict_ux: «log: security_audit event client_op_id_conflict»; OVERRIDES §AD-01: аудит — только доказанная коллизия op-id, бизнес-409 — без аудита и очистки.
- build/miniapp-api-contract.yaml: 409 IDEMPOTENCY_CONFLICT (pause-api-a2.md §1, строки 247, 280, 326).

## 5. ЧТО ПРОЧИТАТЬ (целиком)
- apps/api/app/routers/pause.py — 21,2
- apps/api/app/security_events.py — 1,8 (record_security_event, CLIENT_OP_ID_CONFLICT; не менять)
- apps/api/app/day_keys.py — 7,8
- apps/api/tests/test_pause_api_db.py — 14,3
- apps/api/tests/test_pause_api.py — 2,3
- apps/api/tests/test_day_current.py — размер ШТАБ (test_kinds_and_ttl, :78–100)
Итог раздела без test_day_current.py — 47,4 КБ. Чтение Агента ≈ 89,2 КБ + test_day_current.py.

## 6. Файлы
Изменить: apps/api/app/routers/pause.py; apps/api/app/day_keys.py; apps/api/tests/test_pause_api_db.py; apps/api/tests/test_pause_api.py; apps/api/tests/test_day_current.py. Создать и удалить — нет.

## 7. Контракт и логика
Тело POST /pause/request: {"days": 1..7, "start_date": "YYYY-MM-DD"}, оба обязательны; start_date — тип date в PauseRequestIn; нет поля или не дата → 422 VALIDATION_ERROR. Ответы: 201 {"pause"}; 404 PARTICIPANT_NOT_FOUND; 409 PAUSE_ALREADY_OPEN / PAUSE_REFUSED (details.reason: причины pause_rules или start_date_passed) / IDEMPOTENCY_CONFLICT; 422; 503. В responses маршрута дописать новые коды 409.
day_keys.py [ШТАБ-тех]:

    KIND_PAUSE_REQUEST = "pause_request"
    TTL_PAUSE_REQUEST = "3650 days"   # как прочие pause_*; в TTL_BY_KIND (станет 14 видов)
    def key_pause_request(pid, op_id) -> str: f"{KIND_PAUSE_REQUEST}:{pid}:{op_id}"

Строку ключа дописать в docstring модуля (пишет routers/pause, pause-api-a2).
pause.py, новое:

    OP_KIND_REQUEST = "pause_request"
    REFUSAL_START_DATE_PASSED = "start_date_passed"  # как already_open: в pause_rules нет
    def _params_hash(days, start_date) -> str:
        sha256(json.dumps({"days": days, "start_date": start_date.isoformat()},
               sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    _KEY_HASH_SQL: SELECT params_hash FROM idempotency_keys WHERE key = :key
    _INSERT_REQUEST_KEY_SQL: INSERT INTO idempotency_keys (key, kind, ttl, result_ref, params_hash)
        VALUES (:key, :kind, CAST(:ttl AS interval), :ref, :h)   # без ON CONFLICT
    class _OpIdConflict(Exception): pid, op   # не HTTPException

Порядок request_pause (всё под замком participant:pid, одна транзакция):
1) active_pid_locked — нет → 404 (как сейчас).
2) op, h = _params_hash(days, start_date), ключ key_pause_request(pid, op). Ключ есть: hash равен → строка по op (_BY_OP_SQL .one()), commit, «repeat», 201 с ней; hash не равен (в том числе NULL) → raise _OpIdConflict(pid, op). Ключа нет, строка по op есть → прежний результат 201 без аудита (коллизия не доказана) [канон OVERRIDES §AD-01]. Ничего нет → шаг 3.
3) открытая или активная строка → 409 PAUSE_ALREADY_OPEN (как сейчас).
4) state, tz, _bounds → start_at; start_at.astimezone(day_clock.zone(tz)).date() != start_date → 409 PAUSE_REFUSED reason start_date_passed, ничего не пишется [Автор 22.11, К-4 №1 = А].
5) _refusal (как сейчас).
6) INSERT строки (как сейчас; IntegrityError OPEN_INDEX → 409). Пусто (ON CONFLICT) → повторить шаг 2.
7) INSERT ключа: kind pause_request, ttl из TTL_BY_KIND, ref = str(id строки), h. Конфликт ключа → IntegrityError → 503 (под замком невозможен).
8) commit → 201 «created».
_run — новая ветка до HTTPException:

    except _OpIdConflict as exc:
        _rollback(session)                      # сначала откат: соединение уходит в пул, замок снят
        saved = record_security_event(session.get_bind(), event_type=CLIENT_OP_ID_CONFLICT,
            pid=exc.pid, op_kind=OP_KIND_REQUEST, client_op_id=exc.op)
        logger.info("%s: tg_user_id=%s status=IDEMPOTENCY_CONFLICT audit=%s", name, tg_user_id,
                    "ok" if saved else "failed")
        raise _idempotency_conflict() from None  # 409 при любом saved

record_security_event вызывать ТОЛЬКО после rollback (требование РЕВЬЮЕРА A1: иначе второе соединение пула при открытой сессии). Пул пуст (pool timeout 30 с) или любой отказ → False, 409 всё равно уходит. Импорт `from app.security_events import CLIENT_OP_ID_CONFLICT, record_security_event` — именем модуля pause (тесты подменяют pause.record_security_event). Engine — session.get_bind(): тот же пул, что у сессии, и в тестах тоже [ШТАБ-тех; отличие от a1 §7 get_engine(settings)].
_idempotency_conflict(): 409, code IDEMPOTENCY_CONFLICT, message «Операция уже выполнена с другими параметрами. Обновите экран.»
Бизнес-409 (PAUSE_ALREADY_OPEN, PAUSE_REFUSED, PAUSE_NOT_CANCELLABLE, PAUSE_NOT_ACTIVE) — без record_security_event и без новых действий [Автор, R-2026-11-21; OVERRIDES §AD-01]. GET, cancel, resume — поведение не меняется. Docstring pause.py: шаги request переписать по этому разделу; строку «тело повтора не сравнивается» убрать.

## 8. БД
Миграции нет [ШТАБ-тех]: params_hash уже есть в 0007, права app_api на idempotency_keys достаточны (SELECT, INSERT), security_events — INSERT app_api (0022). expected_tables.txt не меняется.

## 9. Тесты
test_pause_api_db.py (tg_user_id 8831–8840; таблицу security_events читает владелец через db_engine, фильтр по pid):
- test_request_collision_409_and_audit (parametrize: другие days; другая start_date): первый 201, тот же op с другим параметром → 409 IDEMPOTENCY_CONFLICT; в security_events одна запись (client_op_id_conflict, pause_request, op); строк паузы 1, она не изменилась.
- test_request_repeat_same_params: тот же op, те же параметры → 201, тот же id; ключ pause_request с params_hash не NULL; security_events 0.
- test_request_row_without_key_is_repeat: строка с op вставлена владельцем (_pause_row(..., op=op), status requested), ключа нет → 201 с этой строкой; ключ не создан; security_events 0.
- test_request_start_date_mismatch (parametrize: сегодня 2026-11-20; послезавтра 2026-11-22) → 409 PAUSE_REFUSED start_date_passed; строк нет, ключа нет, security_events 0.
- test_business_409_no_audit: test_request_other_op_already_open и один _refused-сценарий — security_events 0.
- test_audit_failed_still_409: monkeypatch pause.record_security_event → False → 409 IDEMPOTENCY_CONFLICT.
- test_audit_after_rollback: monkeypatch pause._rollback (обёртка, пишет «rollback» в список и зовёт исходный) и pause.record_security_event (пишет «audit», True); перед «audit» в списке — «rollback».
test_pause_api.py (без БД): test_start_date_missing_or_bad_is_422 (parametrize: нет поля; "21.11.2026") → 422 VALIDATION_ERROR.
Цели: bash tools/check.sh api. Только CI: тесты с БД (REQUIRE_DB_TESTS=1).

## Задетые тесты (правило «Т»; grep ШТАБа по pause/request, pause_request, TTL_BY_KIND, X-Client-Op-Id, params_hash; файлы открыты ПРОЕКТИРОВЩИКОМ)
- apps/api/tests/test_pause_api_db.py: _request — параметр start_date: str | None, по умолчанию TOMORROW.date().isoformat(), json {"days", "start_date"}; _pause_row — параметр op: str | None = None (None → uuid4, как сейчас); test_request_repeat_same_op заменить на test_request_repeat_same_params (сейчас повтор с days=5 ждёт 201 — после A2 это коллизия); хелпер _security_events(engine, pid); новые тесты раздела 9. Регрессия, не менять: прочие тесты request/GET/cancel/resume, test_db_error_is_503_and_rolls_back, test_log_has_no_pid_or_op (повтор с теми же параметрами).
- apps/api/tests/test_pause_api.py: :37, :47, :57 — в json добавить "start_date": "2026-11-21"; test_key_formats — дописать key_pause_request и TTL pause_request; новый 422-тест.
- apps/api/tests/test_day_current.py::test_kinds_and_ttl (:84) — полное равенство TTL_BY_KIND: добавить "pause_request": "3650 days".
- Регрессия, не менять: test_clocks_1.py:79, test_day_clock.py:262–263, test_notify_ladder.py:127, test_notify_noon.py:95, test_notify_ops.py:95 (по одному ключу TTL_BY_KIND).
- Не задеты: test_checkup_config, test_checkup_status_db, test_checkup_submit_db, test_day_queue, test_day_reflection, test_day_report_submit, test_day_report_unit, test_me_db, test_onboarding_form_config, test_onboarding_form_db, test_support_db — совпадение по X-Client-Op-Id и params_hash других роутеров; /pause/request и TTL_BY_KIND пауз не вызывают. test_db_roles_0007 — колонки idempotency_keys не меняются.
Тест вне списка упал → не чинить, «тест X вне списка» в ИТОГ.

## Канон и решения
(а) И2 §idempotency_keys (behavior_on_collision, params_hash_optional); И4 §R339.conflict_ux; OVERRIDES.yaml §AD-01, §AD-02 (closed — по старту ШТАБа); build/miniapp-api-contract.yaml (409 IDEMPOTENCY_CONFLICT).
(б) Код противоречил R-2026-11-21 «Поздняя первая доставка» (по коду: pause.py, _bounds — дата сдвигалась молча) — чинит эта задача. Поле start_date и reason start_date_passed в контракте не описаны.
(в) Normative (И2, И4, OVERRIDES) — правок нет. build/miniapp-api-contract.yaml — правка в цикле DOCS (тело /pause/request + start_date; 409 PAUSE_REFUSED start_date_passed; 409 IDEMPOTENCY_CONFLICT для /pause/request); точный текст «найди / замени» не дан: contract.yaml в этом окне не читался, есть ли там /pause — не проверено → «Для ШТАБА». По DESIGNER «Канон и решения» правка DOCS идёт до промпта Агенту — порядок решает ШТАБ.
(г) Правок normative нет.

## 10. Живые проверки
Выкат позже (PLAN §4; очередь SHTAB-DEBTS §1, вместе с образом api). Миграции нет. После выката: POST с тем же X-Client-Op-Id и другим days → 409 IDEMPOTENCY_CONFLICT; под владельцем SELECT count(*) FROM security_events — +1.

## 11. Запреты
AGENT-BRIEF §3. Не трогать: security_events.py, participant_lock.py (дефект замка — не здесь), миграции, expected_tables.txt, cancel/resume, GET. Под app_api — без SELECT и RETURNING по security_events. В лог не писать pid, op, pause_id, tz, start_date, initData. Без новых зависимостей. Без heredoc.

## 12. Критерии готовности
Файлы раздела 6; check api зелёный; CI api зелёный; record_security_event — только после rollback; описание PR по AGENT-BRIEF §10.

## 13. Оценка
Часы Автора ≈ 0,5. Кредиты: Opus ≈ 550–800 (3 файла «Задетых» по правилу «Т» включены).

## 14. РЕВЬЮЕР
Да: initData и привязка pid, коллизии op-id, аудит в отдельной транзакции после отката, отказ записи без утечки в лог, бизнес-409 без аудита.

## Для ШТАБА
- Замок: API hashtext('participant:'||pid), бот hashtextextended — в A2 не чинится (pause-api-a3.md §2, блокер 2).
- Контракт /pause/request + start_date, reason start_date_passed, IDEMPOTENCY_CONFLICT → цикл DOCS.
- TTL pause_request 3650 days против И2 ttl_by_kind default 1h — сверить; срок в логике не проверяется, GC нет.
