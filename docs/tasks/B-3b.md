# B-3b — формат ошибок 422 / 500 (D-18), явный rollback и тесты отката first-launch (D-15 г, е)

Заменяет часть docs/tasks/B-3.md (B-3 разрезан на B-3a и B-3b, ответ Автора 4). Обновлена по 95e554d.

## 1. Паспорт
- id: B-3b · PR: «B-3b: ошибки 422/500 в формате Error, rollback first-launch (D-18, D-15 г)» · ветка: feat/b3b-errors
- Режим: Р0+ · зависит от: B-3a-3 (#71), сервер ✅ 95e554d. Миграции нет.
- Порядок мержа: B-3b → B-3c. Файлов с B-3c не делит (session.py меняет только B-3b).
- Первый файл пакета — docs/STATE.md (строки от ШТАБа).
- ДО старта КОДЕРА Автор выполняет и вставляет вывод в стартовое сообщение:
      grep -rn -B3 -A1 '"detail"' apps/api/tests/

## 2. Цель
Ошибки валидации тела и непойманные исключения — в формате контракта Error, без значений полей
и параметров SQL в ответе и в логе. Явный rollback сессии при любом исключении; тесты отката
first-launch, гонки участника до 0004 и CHECK consent_events через pg_constraint.

## 3. Решения Автора (дословно)
- 03.10: «D-18 в B-3». Туда же (ШТАБ): «прочие исключения в first-launch и /consents дают 500 со
  стандартным traceback (возможны параметры SQL) → общий обработчик в B-3».
- 4: «B-3b (D-18, обработчик 500, тесты D-15 г). DEFECTS-FOUND.md убрать из чтения и правки КОДЕРА».
- ШТАБ (д): текст D-18 из З1 принят — включая hide_parameters=True у движка.
- 10.10 (ШТАБ): импорт из conftest — from tests.conftest import … безопасен (tests/__init__.py есть,
  pytest запускается из apps/api в CI и в check.sh, conftest грузится один раз как tests.conftest).

## 4. Выдержки (код 95e554d)
- Контракт components.schemas.Error: code, message, details.
- D-18 (1): RequestValidationError → {"detail": [...]} с полем input (дата рождения уходит клиенту).
- D-15 (г): «в B-3 добавить тесты: откат после get_or_create (OperationalError на INSERT consent_events →
  0 строк участника); гонка для участника до 0004 (8 потоков → ровно 2 give); явный rollback для любых
  исключений в first-launch».
- D-15 (е): «compare_metadata не сравнивает CHECK: ограничения consent_events сейчас сверены глазами;
  тест через pg_constraint — позже.»
- Миграция 0004 (сверено ШТАБом по 95e554d), CHECK consent_events — ровно три:
  consent_events_kind_check — CHECK (kind IN ('C0','C1','C2','C3','C4','C5','C6'));
  consent_events_action_check — CHECK (action IN ('give','revoke'));
  consent_events_created_via_check — CHECK (created_via IN ('mini_app_first_launch')).
  Ещё 2 FK (consent_events_pid_fkey, consent_events_text_key_fkey) — contype 'f', тест 8 их не видит.
- tg_user_registry (0002; 0004 её не меняет): NOT NULL — pid uuid PK, tg_user_id bigint CHECK > 0,
  created_via text CHECK IN ('mini_app_first_launch'), created_at timestamptz DEFAULT now();
  short_no — GENERATED ALWAYS AS IDENTITY (в INSERT не указывать); tombstoned_at — NULL.
- errors.py: install_error_handlers(app) — только @app.exception_handler(HTTPException):
  detail-dict с "code" → как есть, иначе {"code": f"HTTP_{status}", "message": str(detail)}; headers сохраняются.
- main.py: create_app() — FastAPI без debug; install_error_handlers(app) до include_router. main.py не трогать.
- session.py: _engine_for(dsn) — @lru_cache(maxsize=4), create_engine(dsn, pool_pre_ping=True, pool_size=5,
  max_overflow=5, connect_args={"connect_timeout": 5}); get_engine(settings) → _engine_for(settings.sqlalchemy_dsn());
  get_db_session: sessionmaker(bind=get_engine(settings), expire_on_commit=False); try: yield session;
  finally: session.close(). Имена и сигнатуры не менять: test_db_roles подменяет app.db.session._engine_for,
  test_dsn подменяет get_engine.
- Starlette: HTTPException и RequestValidationError обрабатывает ExceptionMiddleware ВНУТРИ http-middleware —
  до middleware 500 они не доходят; порядок регистрации в install_error_handlers не важен.
- CI (ci.yml, job api): DATABASE_URL — суперпользователь образа postgres:16 (docstring test_db_roles.py:
  «соединение CI — суперпользователь»). db_engine и db_api_client ходят по DATABASE_URL без SET ROLE →
  CREATE FUNCTION / TRIGGER / DROP и чтение pg_constraint в тестах 5–8 разрешены; отдельный engine не нужен.
- tests/conftest.py (КОДЕРУ не читать; строки дословно по 95e554d):
      FAKE_BOT_TOKEN = "123456:TEST-fake-token-for-pytest-only"
      UNREACHABLE_DSN = "postgresql+psycopg://nobody:nopass@127.0.0.1:1/none"
      def valid_init_data(**kwargs) -> str:          # функция, не фикстура
          return sign_init_data(make_fields(**kwargs))
      def make_fields(user: dict | None = None, auth_date: int | None = None, **extra: str) -> dict[str, str]
          # user по умолчанию {"id": 42, "first_name": "Test"}; auth_date — сейчас
      def count_registry_rows(engine, tg_user_id: int | None = None) -> int
      def count_consent_rows(engine, pid=None) -> int
  Фикстуры: api_client — TestClient(main.app), overrides get_settings → Settings(bot_token=FAKE_BOT_TOKEN,
  database_url=UNREACHABLE_DSN); db_engine — engine по DATABASE_URL, TRUNCATE участников/согласий/событий +
  seed текстов; db_api_client(db_engine, migrated_db) — TestClient(main.app) с настоящей БД. Overrides
  ставятся на main.app и чистятся в finally.
  Импорт в новых тестах: from tests.conftest import FAKE_BOT_TOKEN, valid_init_data (conftest не меняется).
- first-launch (как в test_db_roles.py@95e554d): POST /miniapp/v1/onboarding/first-launch, заголовок
  X-Telegram-Init-Data, тело {"birth_date": "1990-01-01", "consents": ["C0", "C1"]} → 201 {pid, short_no}.

## 5. ЧТО ПРОЧИТАТЬ (размеры по 95e554d)
docs/process/CODER.md 11,1 КБ; AGENT-BRIEF.md 11,2; docs/STATE.md 18,8; эта карточка ≈ 10;
apps/api/app/errors.py 0,7; apps/api/app/db/session.py 1,5; вывод grep от Автора ≈ 1. Чтение КОДЕРА ≈ 54 КБ.
Не читать и не переписывать: tests/test_first_launch.py, routers/onboarding.py, tests/conftest.py,
main.py, docs/DEFECTS-FOUND.md.

## 6. Файлы (4 + STATE + ручная правка)
Изменить: apps/api/app/errors.py, apps/api/app/db/session.py.
Создать: apps/api/tests/test_errors.py, apps/api/tests/test_first_launch_rollback.py.
Тесты с "detail" в 422 (по выводу grep) правит Автор вручную по блоку «ДЛЯ РУЧНОЙ ПРАВКИ» от КОДЕРА:
файл, номер строки, было → стало (обычно r.json()["code"] == "VALIDATION_ERROR").

## 7. Контракт
- 422 (RequestValidationError, @app.exception_handler): {"code": "VALIDATION_ERROR", "message": "Неверный
  формат запроса.", "details": {"errors": [{"loc": [...], "type": "..."}]}} — только loc и type;
  без input, ctx, msg, url.
- 500 (любое непойманное исключение): {"code": "INTERNAL_ERROR", "message": "Внутренняя ошибка.
  Попробуйте позже."}. Делать @app.middleware("http") в install_error_handlers (try: return await
  call_next(request); except Exception), НЕ exception_handler(Exception): Starlette после такого обработчика
  бросает исключение заново, и uvicorn пишет traceback. Лог: logging.getLogger("app.errors"), уровень ERROR,
  только type(exc).__name__; без str(exc), без exc_info, без logger.exception.
- HTTPException (401/403/422 с code/429/503) — как было.
- session.py: create_engine(..., hide_parameters=True) — остальные параметры прежние; в get_db_session:
  except Exception: session.rollback(); raise — перед finally (close остаётся).
- Mini App не меняется: клиент берёт code из тела.

## 8. БД
Нет миграции. Тесты создают и удаляют временные функцию и триггер.

## 9. Тесты
test_errors.py (без БД; TestClient(app, raise_server_exceptions=False)):
1. Тестовое FastAPI() + install_error_handlers, маршрут бросает RuntimeError("secret-param-123") → 500,
   тело == {code, message} из раздела 7; "secret-param-123" нет ни в r.text, ни в caplog.text;
   в caplog есть "RuntimeError" (caplog.set_level(logging.DEBUG)).
2. Там же POST с моделью {birth_date: date}, тело {"birth_date": "1990-13-45"} → 422 VALIDATION_ERROR;
   у каждого элемента details.errors ключи ровно {loc, type}; "1990-13-45" нет в r.text.
3. main.app через api_client: POST first-launch с заголовком valid_init_data() и
   {"birth_date": "1990-13-45", "consents": ["C0", "C1"]} → 422 VALIDATION_ERROR, значения нет в r.text;
   без заголовка → 401 TG_INIT_MISSING (как было).
4. _engine_for("postgresql+psycopg://u:p@127.0.0.1:1/x").hide_parameters is True (соединения нет).
test_first_launch_rollback.py (с БД, только CI; фикстуры db_api_client, db_engine):
5. Функция + триггер BEFORE INSERT ON consent_events FOR EACH ROW:
   RAISE EXCEPTION 'b3b-test' USING ERRCODE = '57P01' (→ OperationalError) → first-launch нового
   tg_user_id (valid_init_data(user={"id": 2001, "first_name": "Test"})): статус 500 или 503;
   count_registry_rows(db_engine, 2001) == 0, count_consent_rows(db_engine) == 0.
6. То же без ERRCODE (→ InternalError), tg_user_id 2002: статус 500 или 503, в теле есть "code",
   "b3b-test" нет в r.text; строк участника 0.
7. Участник до 0004: INSERT INTO tg_user_registry (pid, tg_user_id, created_via, created_at) VALUES
   (gen_random_uuid(), 2101, 'mini_app_first_launch', now()); db_api_client ставит overrides, затем
   8 потоков (ThreadPoolExecutor, у каждого свой TestClient(main.app)) → все 201, один pid,
   он же — pid вставленной строки; SELECT count(*) FROM consent_events WHERE pid = :p AND action = 'give'
   == 2 (kind C0 и C1).
8. (D-15 е) SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint
   WHERE conrelid = 'consent_events'::regclass AND contype = 'c' → множество имён ровно три из раздела 4;
   в определении kind — каждое из C0…C6, action — give и revoke, created_via — mini_app_first_launch.
   Проверять вхождение значений, не точную строку определения.
Триггер и функцию удалять в finally (DROP TRIGGER IF EXISTS … ON consent_events; DROP FUNCTION IF EXISTS …).
NOT NULL на другой колонке tg_user_registry (миграции 0005–0006) → добавить в INSERT, записать в PR.
Цель check.sh: api (1–4; 5–8 там пропускаются). Только CI: 5–8.

## 10. Живые проверки (после мержа; сервер пересобирает api)
Все сервисы Up, healthy; Автор открывает Mini App — работает (status, first-launch, consents);
logs api за 10 мин без «Traceback».

## 11. Запреты
AGENT-BRIEF §3. Не переписывать test_first_launch.py целиком (только ручная правка строк Автором);
не трогать onboarding.py, consents.py, main.py, conftest.py; не менять коды HTTPException; имена
_engine_for / get_engine / get_db_session не менять; новых зависимостей нет;
docs/DEFECTS-FOUND.md не читать и не править (отметку «D-18 закрыт» вносит Автор docs-задачей).

## 12. Готово, когда
check.sh api зелёный; CI 7/7; ручная правка "detail" внесена; РЕВЬЮЕР без блокирующих; живая проверка пройдена.

## 13. Оценка
Часы Автора ~1; запросов КОДЕРА 2; кредиты 0 (Р0+).

## 14. РЕВЬЮЕР: да
18+ (дата рождения перестаёт возвращаться в 422) и транзакция согласий (rollback first-launch).
