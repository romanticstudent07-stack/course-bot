# api-melochi — projector: нет драйвера DSN = битый DSN; точные классы в test_dsn

## 1. Паспорт
- id: api-melochi · режим: Р0+ (пакет КОДЕРА) · область: API (apps/api), без БД, без миграций.
- Заголовок PR: fix(api): projector — нет драйвера DSN = битый DSN; точные классы в test_dsn
- Ветка КОДЕРА: api-melochi
- Зависит от: нет (поверх main 9e0bdd7 или новее). Карточка — ветка docs/tasks-api-melochi.
- Источник: docs/STATE.md, «Мелочи» (test_dsn «любой класс» и ImportError в main() проектора).

## 2. Цель
1) main() проектора ловит ImportError (нет драйвера диалекта, например postgresql+asyncpg://)
   тем же путём, что битый DSN: WARNING с именем класса, код 1, без traceback и без DSN.
2) test_projector_main_bad_dsn проверяет для каждого битого DSN ТОЧНЫЙ класс и строку лога,
   а не «ArgumentError или ValueError».

## 3. Решения Автора (дословно)
- «1 — А»: texts.run_load: ImportError — в Мелочах (ШТАБ, 15.10). В эту карточку не входит.
- «2 — да»: в лог — настоящее имя класса (ModuleNotFoundError), без особого случая в коде.
- 15.10: выкат на сервер — одним заданием ШТАБа после мержа (вместе с #87), build api, projector.
- Действующий контракт B-3c (app/projector.py@a8d707d, docstring): «Битый DSN (B-3c): WARNING
  только с именем класса ошибки, код выхода 1, цикл не стартует.»

## 4. Факты (исследование ПРОЕКТИРОВЩИКА; перепроверять не нужно)
Архитектура не нужна. SQLAlchemy 2.0.54 (apps/api/requirements.txt), код rel_2_0_54:
get_engine (app/db/session.py) → _engine_for(dsn) → create_engine(dsn) → make_url → _parse_url.

| DSN в тесте | где падает | класс |
|---|---|---|
| postgresql+psycopg://u:pw-bad-1@db:abc/d | _parse_url: int("abc") для порта | ValueError |
| not-a-dsn-pw-bad-2 | _parse_url: шаблон не совпал (нет «://») | ArgumentError |
| postgresql+asyncpg://u:pw-bad-3@db:5432/d | create_engine → import_dbapi() → __import__("asyncpg") | ModuleNotFoundError |

- ModuleNotFoundError — подкласс ImportError. Он возникает ВНУТРИ create_engine, то есть в
  get_engine(...) внутри уже существующего try в main(), а не при первом connect.
  Поэтому достаточно правки except в main(); app/db/session.py не трогать.
- Модуль sqlalchemy.dialects.postgresql.asyncpg при загрузке asyncpg не импортирует (только в
  import_dbapi), поэтому sys.modules["asyncpg"] = None даёт ModuleNotFoundError ровно там.
- Неизвестный драйвер (postgresql+nosuch://) → NoSuchModuleError, подкласс ArgumentError —
  уже ловится; отдельный тест не нужен.
- Тексты этих трёх исключений DSN не содержат, но другие ArgumentError SQLAlchemy могут
  показать значения — поэтому в лог по-прежнему только имя класса.
- Кэш не мешает: lru_cache у _engine_for не запоминает вызов, бросивший исключение, а у трёх
  DSN разные строки. Кэш в тесте НЕ чистить (clean_env уже чистит get_settings).

## 5. ЧТО ПРОЧИТАТЬ
- apps/api/app/projector.py — 9,7 КБ (main(), docstring модуля).
- apps/api/tests/test_dsn.py — 9,1 КБ (test_projector_main_bad_dsn, фикстура clean_env).
Чтение КОДЕРА ≈ CODER.md 11,1 + AGENT-BRIEF.md 11 + STATE.md 25,2 + карточка 7 + 18,8 ≈ 73 КБ.
session.py и config.py не открывать — нужные факты в разделе 4.

## 6. Файлы
- Изменить: apps/api/app/projector.py; apps/api/tests/test_dsn.py.
- Создать / удалить: нет. docs/STATE.md — только если ШТАБ дал строки.

## 7. Контракт main() (python -m app.projector run | once)
- Неверный аргумент → usage, код 2 — без изменений.
- get_engine бросил SQLAlchemyError, ValueError или ImportError →
  logger.warning("projector: bad database url (%s)", type(exc).__name__), return 1;
  run_once и run_forever не вызываются. Для once и для run одинаково.
- В stdout, stderr и лог не попадают: DSN, пароль, str(exc), traceback
  (без exc_info, без logger.exception).
- Правка кода — одна строка:
      except (SQLAlchemyError, ValueError) as exc:
  заменить на
      except (SQLAlchemyError, ValueError, ImportError) as exc:
  Другой код main() не менять. Exception целиком не ловить.
- Комментарий над try: фразу «в тексте ArgumentError — вся строка DSN с паролем» заменить на
  «текст исключения может содержать части DSN»; добавить «нет драйвера диалекта (ImportError,
  в том числе ModuleNotFoundError) — тем же путём (api-melochi)».
- Docstring модуля, строку «Битый DSN (B-3c): …» заменить на:
  «Битый DSN или нет драйвера диалекта (B-3c, api-melochi): WARNING только с именем класса
  ошибки (ArgumentError, ValueError, ModuleNotFoundError), код выхода 1, цикл не стартует.»

## 8. БД
Нет. Миграций нет, expected_tables.txt не трогать.

## 9. Тесты (apps/api/tests/test_dsn.py, без БД)
Переписать test_projector_main_bad_dsn (комментарий «B-3c 4» оставить, дописать «+ api-melochi»):
- parametrize "mode": ["once", "run"] — как сейчас.
- parametrize "bad, cls, secret" — ровно 3 тройки из таблицы раздела 4, ids
  "port-abc", "not-a-url", "no-driver":
      ("postgresql+psycopg://u:pw-bad-1@db:abc/d", "ValueError", "pw-bad-1")
      ("not-a-dsn-pw-bad-2", "ArgumentError", "pw-bad-2")
      ("postgresql+asyncpg://u:pw-bad-3@db:5432/d", "ModuleNotFoundError", "pw-bad-3")
  Итого 6 прогонов.
- Только для случая с asyncpg, внутри теста:
      if "+asyncpg" in bad:
          clean_env.setitem(sys.modules, "asyncpg", None)
  clean_env — это monkeypatch: после теста он сам вернёт sys.modules. import sys — в шапку.
- get_engine не подменять (ошибку даёт настоящий create_engine); run_once и run_forever →
  pytest.fail — как сейчас.
- Проверки: main([mode]) == 1; secret нет в out.out, out.err, caplog.text;
  "Traceback" нет в out.err и caplog.text;
  f"projector: bad database url ({cls})" есть в caplog.text.
- Старую проверку «"ArgumentError" in caplog.text or "ValueError" in caplog.text» убрать.
- Docstring файла: добавить строку «api-melochi: битый DSN — точный класс на каждый DSN;
  нет драйвера → ModuleNotFoundError».
Другие тесты файла не менять.
Цели: bash tools/check.sh api. CI: job api (тесты с БД не затронуты).

## 10. Сервер (после мержа; команды пишет ШТАБ, выкат вместе с #87)
Живой запуск с битым DSN не делаем (.env на сервере не трогаем). Ожидание после build api
и projector:
- projector Up, RestartCount 0;
- в логе projector нет строки «bad database url» и нет Traceback.
Бэкап не нужен (миграций нет).

## 11. Запреты
- AGENT-BRIEF.md, раздел 3: не править docs/architecture/**, .github/**, .githooks/**, .env;
  не пушить в main; DSN, пароль и секреты не логировать.
- Не трогать app/texts.py (его ImportError — в «Мелочах»), app/db/session.py, app/config.py,
  compose, Mini App, rate-limit.
- Новых зависимостей нет: asyncpg НЕ ставить — тест не зависит от того, установлен ли он.
- Кэш _engine_for не чистить; в лог — не str(exc), не exc_info, не DSN.

## 12. Критерии готовности
- main() ловит ImportError: в логе «projector: bad database url (ModuleNotFoundError)»,
  код 1, цикл не стартует.
- test_projector_main_bad_dsn: 6 прогонов, у каждого точный класс; старое «or» убрано.
- check.sh api зелёный; CI 7/7 зелёный; изменено ровно 2 файла (+ STATE.md, если ШТАБ дал строки).

## 13. Оценка
Автор ≈ 0,5 ч (КОДЕР 1 окно, CI 1 круг) + выкат в общем задании ШТАБа. Кредиты 0.

## 14. РЕВЬЮЕР
Нет: initData, 18+, согласия (B-2), rate-limit (B-1), роли/GRANT БД (B-3) и оплата не
затрагиваются; меняется только обработка ошибки старта проектора.
