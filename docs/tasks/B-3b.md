# B-3b — формат ошибок 422 / 500 (D-18), явный rollback и тесты отката first-launch (D-15 г)

Заменяет часть docs/tasks/B-3.md (удалён в PR docs/tasks-1e-2b: B-3 разрезан на B-3a и B-3b, ответ Автора 4).

## 1. Паспорт
- id: B-3b · PR: «B-3b: ошибки 422/500 в формате Error, rollback first-launch (D-18, D-15 г)» · ветка: feat/b3b-errors
- Режим: Р0+ · зависит от: 1e-2b-1 (запись D-18); начинать после фазы Б сервера (B-3a-2, раздел 10): выкаты по одному; файлов с B-3a-1…3 не делит (session.py меняет только B-3b). Миграции нет.
- Первый файл пакета — docs/STATE.md (строки от ШТАБа).
- ДО старта КОДЕРА Автор выполняет и вставляет вывод в стартовое сообщение:
      grep -rn -B3 -A1 '"detail"' apps/api/tests/

## 2. Цель
Ошибки валидации тела и непойманные исключения — в формате контракта `Error`, без значений полей
и параметров SQL в ответе и в логе. Явный rollback сессии при любом исключении; тесты отката first-launch.

## 3. Решения Автора (дословно)
- 03.10: «D-18 в B-3». Туда же (ШТАБ): «прочие исключения в first-launch и /consents дают 500 со
  стандартным traceback (возможны параметры SQL) → общий обработчик в B-3».
- 4: «B-3b (D-18, обработчик 500, тесты D-15 г). DEFECTS-FOUND.md убрать из чтения и правки КОДЕРА».
- ШТАБ (д): текст D-18 из З1 принят — включая `hide_parameters=True` у движка.

## 4. Выдержки
- Контракт `components.schemas.Error`: `code`, `message`, `details`.
- D-18 (1): `RequestValidationError` → `{"detail": [...]}` с полем `input` (дата рождения уходит клиенту).
- D-15 (г): «в B-3 добавить тесты: откат после get_or_create (OperationalError на INSERT consent_events →
  0 строк участника); гонка для участника до 0004 (8 потоков → ровно 2 give); явный rollback для любых
  исключений в first-launch».
- D-15 (е): «compare_metadata не сравнивает CHECK: ограничения consent_events сейчас
  сверены глазами; тест через pg_constraint — позже.» Имена CHECK (миграция 0004):
  consent_events_kind_check, consent_events_action_check, consent_events_created_via_check.  
- Код (18cf0ac): errors.py ловит только HTTPException; main.py — FastAPI без debug, install_error_handlers;
  session.py — `_engine_for(dsn)` (lru_cache) и `get_db_session` (yield, finally close).
- conftest (не читать): `api_client` (БД недоступна), `db_api_client`, `db_engine`, `valid_init_data`,
  `count_registry_rows(engine, tg_user_id)`, `count_consent_rows(engine, pid)`; overrides на `main.app`.

## 5. ЧТО ПРОЧИТАТЬ (размеры по 18cf0ac)
docs/process/CODER.md 11,1 КБ; AGENT-BRIEF.md 11,2; docs/STATE.md 16,3; эта карточка ≈ 6;
apps/api/app/errors.py 0,7; apps/api/app/db/session.py 1,5; вывод grep от Автора. **Чтение КОДЕРА ≈ 47 КБ.**
Не читать и не переписывать: tests/test_first_launch.py (24,7 КБ), onboarding.py (13,8), conftest.py,
docs/DEFECTS-FOUND.md.

## 6. Файлы (4 + STATE + ручная правка)
Изменить: apps/api/app/errors.py, apps/api/app/db/session.py.
Создать: apps/api/tests/test_errors.py, apps/api/tests/test_first_launch_rollback.py.
Тесты с `"detail"` в 422 (по выводу grep) правит Автор вручную по блоку «ДЛЯ РУЧНОЙ ПРАВКИ» от КОДЕРА:
файл, номер строки, было → стало (обычно `r.json()["code"] == "VALIDATION_ERROR"`).

## 7. Контракт
- 422 (RequestValidationError): `{"code": "VALIDATION_ERROR", "message": "Неверный формат запроса.",
  "details": {"errors": [{"loc": [...], "type": "..."}]}}` — только loc и type; без input, ctx, msg.
- 500 (любое непойманное исключение): `{"code": "INTERNAL_ERROR", "message": "Внутренняя ошибка.
  Попробуйте позже."}`. Делать http-middleware в install_error_handlers (try: call_next; except Exception),
  НЕ `exception_handler(Exception)`: Starlette после такого обработчика бросает исключение заново,
  и uvicorn пишет traceback. В лог (logger "app.errors", ERROR) — только `type(exc).__name__`, без str(exc)
  и без traceback.
- HTTPException (401/403/422 с code/429/503) — как было.
- session.py: `create_engine(..., hide_parameters=True)`; в `get_db_session`:
  `except Exception: session.rollback(); raise` перед finally.
- Mini App не меняется: клиент берёт code из тела.

## 8. БД
Нет миграции. Тесты создают и удаляют временный триггер.

## 9. Тесты
test_errors.py (без БД; TestClient(app, raise_server_exceptions=False)):
1. Тестовое FastAPI + install_error_handlers, маршрут бросает RuntimeError("secret-param-123") → 500,
   тело == {code, message}; "secret-param-123" нет ни в r.text, ни в caplog.text; в логе есть "RuntimeError".
2. Там же POST с моделью {birth_date: date}, тело {"birth_date": "1990-13-45"} → 422 VALIDATION_ERROR;
   у каждого элемента ключи ровно {loc, type}; "1990-13-45" нет в r.text.
3. main.app через api_client: POST first-launch с валидной initData и birth_date "1990-13-45" → 422
   VALIDATION_ERROR, значение не в ответе; без initData → 401 TG_INIT_MISSING (как было).
4. `_engine_for("postgresql+psycopg://u:p@127.0.0.1:1/x").hide_parameters is True`.
test_first_launch_rollback.py (с БД, CI):
5. Триггер BEFORE INSERT ON consent_events: `RAISE EXCEPTION 'b3b-test' USING ERRCODE = '57P01'`
   (→ OperationalError) → first-launch нового tg_user_id: статус 500 или 503; строк участника 0, согласий 0.
6. То же без ERRCODE (→ InternalError): статус 500 или 503, в теле есть code, "b3b-test" нет в r.text;
   строк участника 0.
7. Участник до 0004: `INSERT INTO tg_user_registry (pid, tg_user_id, created_via, created_at) VALUES
   (gen_random_uuid(), 2101, 'mini_app_first_launch', now())`; 8 потоков (ThreadPoolExecutor, у каждого свой
   TestClient(main.app)) → все 201, один pid; give по pid ровно 2 (C0 и C1).
8. (D-15 е) CHECK consent_events через pg_constraint: SELECT conname, pg_get_constraintdef(oid)
   FROM pg_constraint WHERE conrelid = 'consent_events'::regclass AND contype = 'c' → ровно 3 имени
   из раздела 4; в определении kind — все C0…C6, action — give и revoke, created_via —
   mini_app_first_launch. Проверять вхождение значений, не точную строку определения.   
Триггер и функцию удалять в finally (DROP … IF EXISTS). NOT NULL на другой колонке → добавить, записать в PR.
Цель check.sh: api. Только CI: 5–8.

## 10. Живые проверки (после мержа; сервер пересобирает api)
Все сервисы Up, healthy; Автор открывает Mini App — работает; logs api за 10 мин без «Traceback».

## 11. Запреты
AGENT-BRIEF §3. Не переписывать test_first_launch.py целиком (только ручная правка строк Автором);
не трогать onboarding.py, consents.py, main.py; не менять коды HTTPException; новых зависимостей нет;
docs/DEFECTS-FOUND.md не читать и не править (отметку «D-18 закрыт» вносит Автор docs-задачей).

## 12. Готово, когда
check.sh api зелёный; CI 7/7; РЕВЬЮЕР без блокирующих; живая проверка пройдена.

## 13. Оценка
Часы Автора ~1; запросов КОДЕРА 2; кредиты 0 (Р0+).

## 14. РЕВЬЮЕР: да
Ответы first-launch (18+: дата рождения перестаёт возвращаться в 422) и транзакция согласий (rollback).
