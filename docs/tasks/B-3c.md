# B-3c — долг B-3 в коде: DSN не в repr, проверка user/пароля, битый DSN проектора, дубль констант тестов

## 1. Паспорт
- id: B-3c · PR: «B-3c: DSN скрыты в repr, битый DSN проектора без пароля, константы из conftest» ·
  ветка: feat/b3c-dsn-debt
- Режим: Р0+ · зависит от: B-3b. Начинать после мержа B-3b (порядок мержа B-3b → B-3c). Миграции нет.
- Файлов с B-3b не делит. D-24 (compose, B-3d) сюда не входит.
- Первый файл пакета — docs/STATE.md (строки от ШТАБа).

## 2. Цель
Пароли трёх DSN не попадают в repr/str настроек и в лог проектора при битом DSN; тесты DSN проверяют
user, пароль и host, а не только строку; тестовые константы — из одного места (tests/conftest.py).

## 3. Решения Автора (дословно, 10.10)
- «B-3c (а): DSN-поля Settings (database_url, projector_database_url, migrations_database_url) →
  Field(default=None, repr=False), тип str | None остаётся. Не SecretStr: test_dsn сравнивает поля со строкой,
  projector.main делает model_copy(update={"database_url": ...}). Методы sqlalchemy_dsn / projector_dsn /
  migrations_dsn — имена и поведение прежние.»
- ШТАБ (10.10): from tests.conftest import FAKE_BOT_TOKEN, UNREACHABLE_DSN — безопасно (tests/__init__.py есть,
  pytest из apps/api в CI и в check.sh, --import-mode по умолчанию; conftest грузится один раз как
  tests.conftest). conftest.py не меняется. _init_data в test_db_roles — через valid_init_data; имя
  _init_data и его вызовы остаются.
- ШТАБ (10.10): ValueError от битого порта в texts.run_load — в «Мелочи», не в B-3c.

## 4. Выдержки (код 95e554d)
- config.py: database_url: str | None = None; projector_database_url: str | None = None;
  migrations_database_url: str | None = None (с комментариями над двумя последними). Field уже
  импортирован (from pydantic import Field, SecretStr). postgres_password — SecretStr (не трогать).
  sqlalchemy_dsn(): database_url или f"postgresql+psycopg://{postgres_user}:{password}@{host}:{port}/{db}";
  projector_dsn() = projector_database_url or sqlalchemy_dsn(); migrations_dsn() = migrations_database_url
  or sqlalchemy_dsn().
- pydantic v2: repr=False убирает поле и из repr(), и из str() модели.
- projector.main (после проверки аргументов): settings = get_settings(); logging.basicConfig(...);
      engine = get_engine(settings.model_copy(update={"database_url": settings.projector_dsn()}))
  — вызов ДО любого try. Ветка once: try: run_once(engine) except SQLAlchemyError as exc:
  logger.warning("projector: db error (%s)", type(exc).__name__); return 1. Ветка run: signal.signal(SIGTERM,
  _stop); try: run_forever(engine) except KeyboardInterrupt: pass; return 0.
  create_engine с нераспознаваемой строкой → sqlalchemy.exc.ArgumentError, в тексте вся строка DSN (с паролем);
  нечисловой порт → ValueError.
- texts.main: get_engine вызывается внутри writer(entries), а он — в try … except SQLAlchemyError (печатает
  только имя класса) → утечки пароля нет, texts.py не трогать.
- Имена projector.get_engine, projector.get_settings, projector.run_once и сигнатура get_engine(settings)
  не менять — их подменяют test_dsn.py и test_projector_static.py.
- tests/conftest.py (КОДЕРУ не читать; строки дословно по 95e554d):
      FAKE_BOT_TOKEN = "123456:TEST-fake-token-for-pytest-only"
      UNREACHABLE_DSN = "postgresql+psycopg://nobody:nopass@127.0.0.1:1/none"
      def valid_init_data(**kwargs) -> str:          # функция, не фикстура
          return sign_init_data(make_fields(**kwargs))
      def make_fields(user: dict | None = None, auth_date: int | None = None, **extra: str) -> dict[str, str]
  make_fields: auth_date — сейчас, query_id "AAHdF6IQAAAAAN0XohDhrOrc", user — json.dumps(user,
  ensure_ascii=False, separators=(",", ":")); подпись — FAKE_BOT_TOKEN. Это ровно то, что сейчас собирает
  _init_data в test_db_roles.py → valid_init_data(user={"id": tg_user_id, "first_name": "Test"}).
- test_db_roles.py: docstring — «conftest.py как модуль не импортируется … продублированы ниже;
  FAKE_BOT_TOKEN обязан совпадать с conftest.py»; константы FAKE_BOT_TOKEN, UNREACHABLE_DSN с
  комментарием «# Те же значения, что в conftest.py.»; импорты json, time, urlencode, compute_hash нужны
  только _init_data. API_DIR остаётся.
- test_dsn.py: docstring — «conftest не импортируем (урок B-3a-1): все константы — здесь.»; свои DSN_API
  (api_user:pw-api-1), DSN_PROJECTOR (proj_user:pw-proj-1), DSN_MIGRATIONS (owner_user:pw-mig-1), host db;
  фикстура clean_env, _settings(**kw) = Settings(postgres_user="u", postgres_password="x", postgres_db="d", …),
  _assert_no_secret(secret, capsys, caplog).

## 5. ЧТО ПРОЧИТАТЬ (размеры по 95e554d)
docs/process/CODER.md 11,1 КБ; AGENT-BRIEF.md 11,2; docs/STATE.md 18,8; эта карточка ≈ 9;
apps/api/app/config.py 5,1; apps/api/app/projector.py 10,5; apps/api/tests/test_dsn.py 5,9;
apps/api/tests/test_db_roles.py 10,0. Чтение КОДЕРА ≈ 81,6 КБ (над лимитом 80 — решение ШТАБа).
Не читать: tests/conftest.py (нужное — в разделе 4), texts.py, session.py, main.py.

## 6. Файлы (4 + STATE)
Изменить: apps/api/app/config.py, apps/api/app/projector.py, apps/api/tests/test_dsn.py,
apps/api/tests/test_db_roles.py.

## 7. Контракт (поведение)
(а) config.py: три DSN-поля → Field(default=None, repr=False), тип str | None. Комментарии сохранить.
    Методы DSN — без изменений.
(б) test_dsn.py: проверки DSN через sqlalchemy.engine.make_url — username, password, host (раздел 9).
(в) projector.main: создание engine — в своём try сразу после basicConfig:
        try: engine = get_engine(settings.model_copy(update={"database_url": settings.projector_dsn()}))
        except (SQLAlchemyError, ValueError) as exc:
            logger.warning("projector: bad database url (%s)", type(exc).__name__); return 1
    Только имя класса, без str(exc), без exc_info. Действует и для once, и для run (до signal и run_forever).
    Ветки once / run дальше — как были. Комментарий «DSN не логируем» оставить.
(г) test_db_roles.py: from tests.conftest import FAKE_BOT_TOKEN, UNREACHABLE_DSN, valid_init_data;
    локальные FAKE_BOT_TOKEN и UNREACHABLE_DSN удалить; тело _init_data(tg_user_id) →
    return valid_init_data(user={"id": tg_user_id, "first_name": "Test"}); неиспользуемые импорты
    (json, time, urlencode, compute_hash) удалить. Docstring: абзац про «conftest не импортируется»
    заменить на «Константы и подпись initData — из tests.conftest (B-3c).».
    Если FAKE_BOT_TOKEN после замены не используется — из импорта убрать.
    test_dsn.py docstring: «conftest не импортируем (урок B-3a-1)…» → «Свои DSN-константы — здесь;
    общие тестовые константы при необходимости — from tests.conftest import … (B-3c).»
conftest.py не меняется.

## 8. БД
Нет.

## 9. Тесты (все без БД, кроме уже существующих в test_db_roles)
В test_dsn.py добавить:
1. test_settings_repr_hides_dsn: s = Settings(database_url=DSN_API, projector_database_url=DSN_PROJECTOR,
   migrations_database_url=DSN_MIGRATIONS); в repr(s) и str(s) нет "pw-api-1", "pw-proj-1", "pw-mig-1";
   при этом s.database_url == DSN_API (значения полей прежние).
2. test_dsn_parts (parametrize): s = _settings(database_url=DSN_API, projector_database_url=DSN_PROJECTOR,
   migrations_database_url=DSN_MIGRATIONS); make_url(s.sqlalchemy_dsn()) → ("api_user", "pw-api-1", "db");
   projector_dsn → ("proj_user", "pw-proj-1", "db"); migrations_dsn → ("owner_user", "pw-mig-1", "db")
   — сравнивать (url.username, url.password, url.host).
3. test_dsn_parts_from_postgres: _settings() без трёх DSN → у всех трёх методов ("u", "x", "db").
4. test_projector_main_bad_dsn: parametrize bad in ("postgresql+psycopg://u:pw-bad-1@db:abc/d",
   "not-a-dsn-pw-bad-2") × mode in ("once", "run"); clean_env: DATABASE_URL=DSN_API,
   PROJECTOR_DATABASE_URL=bad; caplog.set_level(logging.DEBUG); get_engine НЕ подменять;
   run_once и run_forever подменить заглушкой pytest.fail (цикл не должен стартовать);
   projector.main([mode]) == 1; "pw-bad-1" и "pw-bad-2" нет в capsys (out, err) и caplog.text
   (через _assert_no_secret по обоим секретам). В caplog есть "ArgumentError" или "ValueError".
Существующие тесты test_dsn.py и test_db_roles.py — зелёные без правки логики.
Цель check.sh: api. Только CI: test_db_roles.py (с БД).

## 10. Живые проверки (после мержа; сервер пересобирает api и projector)
Все сервисы Up, healthy; projector в логах без ошибок за 10 мин; Автор открывает Mini App — работает.

## 11. Запреты
AGENT-BRIEF §3. Не трогать conftest.py, texts.py, session.py, errors.py, main.py, ci.yml, infra/**;
не менять тип DSN-полей на SecretStr; не менять имена и поведение методов DSN, имена
projector.get_engine / get_settings / run_once и сигнатуру get_engine; не печатать и не логировать DSN,
str(exc) и traceback; новых зависимостей нет.

## 12. Готово, когда
check.sh api зелёный; CI 7/7; РЕВЬЮЕР без блокирующих; живая проверка пройдена.

## 13. Оценка
Часы Автора ~0,7; запросов КОДЕРА 2; кредиты 0 (Р0+).

## 14. РЕВЬЮЕР: да
DSN и пароли БД (область B-3): repr настроек, лог проектора при битом DSN.
