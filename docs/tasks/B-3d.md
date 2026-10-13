# B-3d — сервис migrate: alembic и texts load отдельно, у api нет пароля владельца БД (D-24)

## 1. Паспорт
- id: B-3d · PR: «B-3d: сервис migrate; у api нет пароля владельца БД (D-24)» · ветка: feat/b3d-migrate
- Режим: Р0+ · зависит от: B-3c (закрыт, #74). Мерж — когда Автор готов сразу пройти раздел 10 (та же сессия).
- Область: infra (+ Dockerfile-комментарий, texts.py, config.py-docstring, 1 тест). Миграции нет.
- Первый файл пакета — docs/STATE.md, только если ШТАБ дал строки.

## 2. Цель
Пароль владельца БД есть только у одноразового сервиса migrate (alembic и загрузчик текстов).
У api нет env_file: только явный список переменных, без POSTGRES_PASSWORD, MIGRATIONS_DATABASE_URL и чужих секретов.

## 3. Решения (дословно)
- Автор 10.10: «D-24 = А: alembic и texts load — отдельный одноразовый сервис compose; у api нет пароля владельца».
- Автор З1: «1А 2А 3А(sed) 4да 5да 6 — сразу после выката B-3d, когда я у ноутбука».
- Автор про 6: «не надо привязываться ни к какому времени! Будем делать именно тогда когда это необходимо сделать!»
- 1А: migrate с profiles: ["tools"], только ручной запуск; перед run — DC build migrate.
- 2А: у api убрать env_file, явный environment; у числовых — дефолты как в config.py.
- 3А(sed): строки infra/README.md правит Автор командой sed в ветке КОДЕРА (текст — раздел 7).
- 4да: texts.py run_load — ValueError без traceback + тест; docstring config.py. 5да: MEM_LIMIT_MIGRATE 128M.
- ШТАБ: migrate без env_file, без restart, без портов; D-24 в DEFECTS-FOUND.md — не в этой задаче.

## 4. Факты (по 6e433b9)
- api читает окружение через app/config.py (Settings, get_settings); main.py — только get_settings.
- Нужные api поля: BOT_TOKEN, WEBAPP_URL, DATABASE_URL, REDIS_URL, LOG_LEVEL, APP_HOST, APP_PORT, TZ,
  SERVER_TIMEZONE, RATE_LIMIT_PER_MINUTE, INIT_DATA_MAX_AGE_SECONDS, S3_ENDPOINT, S3_REGION, S3_BUCKET_PHOTOS.
  WEBHOOK_SECRET не используется (long polling, D-4). POSTGRES_* у api — только запасной путь DSN: без них и
  без DATABASE_URL api не подключится к БД (безопасный отказ, 503), пароля владельца нет.
- Пустая строка в int-поле ломает старт pydantic → у числовых ${VAR:-дефолт из config.py}.
- migrations/env.py: MIGRATIONS_DATABASE_URL → DATABASE_URL → POSTGRES_* (при пустых всех — KeyError, пароля нет).
- texts.py: python -m app.texts load из /app; DSN — Settings.migrations_dsn(); ловит SQLAlchemyError (имя класса),
  ValueError от нечислового порта в DSN даёт traceback.
- Dockerfile: ENV ALEMBIC_CONFIG=/app/migrations/alembic.ini; комментарий ссылается на «exec api alembic upgrade head».
- SERVER-IRONCLAD.md: миграции — «DC run --rm api alembic upgrade head»; после B-3d этот путь падает с ошибкой
  доступа (роль coursebot_api) — это ожидаемо.
- Сборка образа не подхватывает новые миграции без пересборки → DC build migrate перед run.
- Память: сейчас 1792 МБ (API 384, BOT 512, DB 384, REDIS 64, GARAGE 192, MINIAPP 128, PROJECTOR 128);
  + MIGRATE 128 = 1920 МБ ≤ 2048 (решение Автора 25.09: ≤ 2 GB).

## 5. ЧТО ПРОЧИТАТЬ (размеры по 6e433b9)
docs/process/CODER.md 11,1; AGENT-BRIEF.md ≈ 11; docs/STATE.md 20,2; эта карточка ≈ 9;
infra/docker-compose.dev.yml 9,8; .env.example ≈ 8; infra/SERVER-IRONCLAD.md 12,2; apps/api/Dockerfile 2,0;
apps/api/app/config.py 5,3; apps/api/app/texts.py 10,6. **Чтение КОДЕРА ≈ 99 КБ.**
Не читать: infra/README.md (27,5; правка — sed по разделу 7), docs/DEFECTS-FOUND.md, migrations/env.py (не меняется).

## 6. Файлы (8)
Изменить: infra/docker-compose.dev.yml, .env.example, infra/SERVER-IRONCLAD.md, apps/api/Dockerfile (только
комментарий), apps/api/app/texts.py, apps/api/app/config.py (только docstring), infra/README.md (sed Автора).
Создать: apps/api/tests/test_texts_load_errors.py.

## 7. Контракт
compose, новый сервис migrate (рядом с api):
    migrate:
      build: (как у api — тот же context и dockerfile)
      profiles: ["tools"]
      command: ["alembic", "upgrade", "head"]
      environment:
        MIGRATIONS_DATABASE_URL: ${MIGRATIONS_DATABASE_URL}
        TZ: ${TZ}
      depends_on:
        db:
          condition: service_healthy
      healthcheck:
        disable: true
      networks: [course-bot_net]
      deploy:
        resources:
          limits:
            memory: ${MEM_LIMIT_MIGRATE:-128M}
  Нет: env_file, restart, ports, container_name. ALEMBIC_CONFIG — из ENV образа. У db нет healthcheck → стоп, вопрос.
compose, сервис api: env_file убрать; environment ровно (TZ уже есть — слить, не дублировать):
    BOT_TOKEN: ${BOT_TOKEN}
    WEBAPP_URL: ${WEBAPP_URL}
    DATABASE_URL: ${DATABASE_URL}
    REDIS_URL: ${REDIS_URL}
    S3_ENDPOINT: ${S3_ENDPOINT}
    S3_REGION: ${S3_REGION}
    S3_BUCKET_PHOTOS: ${S3_BUCKET_PHOTOS}
    LOG_LEVEL: ${LOG_LEVEL:-INFO}
    APP_HOST: ${APP_HOST:-0.0.0.0}
    APP_PORT: ${APP_PORT:-8080}
    RATE_LIMIT_PER_MINUTE: ${RATE_LIMIT_PER_MINUTE:-60}
    INIT_DATA_MAX_AGE_SECONDS: ${INIT_DATA_MAX_AGE_SECONDS:-86400}
    SERVER_TIMEZONE: ${SERVER_TIMEZONE}
    TZ: ${TZ}
  Дефолты сверить с config.py: расходится — брать из config.py и указать в PR. В config.py есть поле, которого нет
  в списке и нет в разделе 4 (кроме DSN проектора/миграций, POSTGRES_*, WEBHOOK_SECRET) → стоп, вопрос.
  Прочие ключи api (build, ports, depends_on, healthcheck, restart, deploy) — как были.
  Шапка compose: у api, projector, bot нет env_file; пароль владельца — только у migrate (D-24 = А, B-3d).
.env.example: MEM_LIMIT_MIGRATE=128M в блоке лимитов, сумма в комментарии → 1920 МБ;
  у MIGRATIONS_DATABASE_URL комментарий: «только сервис migrate (alembic, python -m app.texts load)».
SERVER-IRONCLAD.md: раздел «Миграции и тексты (B-3d)» — порядок: бэкап pg_dump → DC build migrate →
  DC run --rm migrate (alembic upgrade head) → при новых текстах DC run --rm migrate python -m app.texts load;
  «DC run --rm api alembic …» и «exec api alembic» после B-3d падают с ошибкой доступа — ожидаемо, не чинить;
  migrate не стартует при up -d и после перезагрузки (profiles); в «Роли БД (B-3)» — alembic и загрузчик
  через migrate; у api env_file нет — новая переменная только явно; сумма лимитов → 1920 МБ.
Dockerfile: комментарий у ALEMBIC_CONFIG → «docker compose ... run --rm migrate (infra/SERVER-IRONCLAD.md)».
texts.py run_load: ValueError ловить там же, где SQLAlchemyError (создание engine и запись), тот же вывод —
  только имя класса, exit 1; ValueError из проверки seed-файлов этим не перекрывать. Docstring — пункт про migrate.
config.py: только docstring — у api env_file нет (B-3d), загрузчик и alembic — сервис migrate.
Тест test_texts_load_errors.py (без БД): MIGRATIONS_DATABASE_URL с нечисловым портом и паролем-маркером
  (postgresql+psycopg://u:pw-marker-b3d@db:notaport/x), get_settings.cache_clear() до и после →
  run_load() == 1; в stdout+stderr есть «ValueError», нет «Traceback» и «pw-marker-b3d».
infra/README.md — sed Автора (КОДЕР даёт sed и grep -n до/после; по 6e433b9 ≈ строки 396 и 398, раздел
«Обновление после мержа PR»). Старая строка 1 целиком:
    Если менялись миграции БД:
  новая:
    Если менялись миграции БД (сначала бэкап и порядок — infra/SERVER-IRONCLAD.md, «Миграции и тексты (B-3d)»):
  Старая строка 2 целиком:
    cd ~/course-bot && docker compose --env-file .env -f infra/docker-compose.dev.yml exec api alembic upgrade head
  новая:
    cd ~/course-bot && docker compose --env-file .env -f infra/docker-compose.dev.yml build migrate && docker compose --env-file .env -f infra/docker-compose.dev.yml run --rm migrate
  grep -n "exec api alembic" infra/README.md после sed → пусто; grep -c "run --rm migrate" → 1.

## 8. БД
Нет (миграций нет, схема 0006_app_roles).

## 9. Тесты
Цель check.sh: api. Сборку образов проверит CI docker. Если в Codespaces есть docker:
docker compose --env-file .env.example -f infra/docker-compose.dev.yml config --quiet → без ошибок.

## 10. Живые проверки (после мержа; СЕРВЕРНЫЙ). DC = cd ~/course-bot && docker compose --env-file .env -f infra/docker-compose.dev.yml
.env на сервере до мержа не трогать; после мержа правка .env не нужна (MEM_LIMIT_MIGRATE имеет дефолт).
Env целиком, docker compose config и DSN в чат не выводить.
- Ф1. git pull → .env по счётчикам: grep -c '^DATABASE_URL=..*' .env = 1; grep -c '^MIGRATIONS_DATABASE_URL=..*' .env = 1.
- Ф2. Бэкап before-b3d (pg_dump -Fc, как прошлые before-*), размер > 0 — ДО первого запуска migrate.
- Ф3. DC build migrate → DC run --rm migrate alembic current → 0006_app_roles (head).
- Ф4. DC run --rm migrate python -m app.texts load → «загружено N, обновлено M, лишних в БД K», exit 0.
- Ф5. DC up -d --force-recreate api → DC exec api env | cut -d= -f1 | sort: есть DATABASE_URL, BOT_TOKEN,
  REDIS_URL; НЕТ POSTGRES_PASSWORD, MIGRATIONS_DATABASE_URL, PROJECTOR_DATABASE_URL, GARAGE_*, S3_SECRET_KEY,
  S3_ACCESS_KEY, PSP_*, WEBHOOK_SECRET. Пользователь api (без пароля):
    DC exec api python -c "from sqlalchemy.engine import make_url; from app.config import get_settings; print(make_url(get_settings().sqlalchemy_dsn()).username)"
  → coursebot_api.
- Ф6. Живые: 401 TG_INIT_MISSING; Mini App status 200 returning; first-launch 201; consents 200; /start с кнопкой.
- Ф7. DC logs --since 10m api → Traceback 0. DC ps → 7/7 Up, 4 healthy, migrate нет.
- Откат: revert-PR → git pull → DC up -d --force-recreate api (.env не менялся — api снова с env_file).
Фаза П — перезагрузка (сразу после Ф7, в ту же сессию, Автор у ноутбука; часов нет; не во время автобэкапа 03:30 MSK):
- П1. До: systemctl is-enabled docker → enabled; grep -c 'restart: unless-stopped' infra/docker-compose.dev.yml → 7.
- П2. sudo reboot (Автор подтверждает). Чужие контейнеры (maxmover и др.) не трогать.
- П3. После: DC ps → 7/7 Up, 4 healthy, migrate НЕ запущен; RestartCount 0 у всех 7
  (docker inspect -f '{{.Name}} {{.RestartCount}}' $(DC ps -q)); DC logs projector → «lock acquired»;
  tailscale serve status — на месте; /start с кнопкой Mini App; Mini App открывается (status 200).

## 11. Запреты
AGENT-BRIEF §3. Плюс: .env, docs/DEFECTS-FOUND.md, migrations/**, projector и bot в compose, порты, тома — не менять;
секретов, реальных ID, IP, имён хостов нет; infra/README.md не читать — только sed по разделу 7.

## 12. Готово, когда
check.sh api зелёный; CI 7/7; РЕВЬЮЕР без блокирующих; сервер: Ф1–Ф7 и П1–П3 пройдены.
После — docs-задача ШТАБа «B-3 закрыт» (D-13, D-24).

## 13. Оценка
КОДЕР 2–3 запроса; часы Автора ~0,7 (раскладка, sed, PR) + сервер ~0,8 (Ф1–Ф7 ~0,5, перезагрузка ~0,3); кредиты 0.

## 14. РЕВЬЮЕР: да
Роли и пароли БД (область B-3): кто получает пароль владельца, полнота списка env api, вывод ошибок без DSN.
