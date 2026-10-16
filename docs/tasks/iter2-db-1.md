# iter2-db-1 — миграция 0007_day_state: жизни, позиция дня и пояс в participant_state, idempotency_keys, права

## 1. Паспорт
- id: iter2-db-1 · область: API · режим: Р0+ (КОДЕР — бесплатный чат, пакет + tools/unpack.py).
- Заголовок PR: feat(db): 0007 — жизни, позиция дня, пояс в participant_state, idempotency_keys, права (iter2-db-1)
- Ветка: iter2-db-1 · Зависит от: нет (последняя миграция в main — 0006_app_roles).
- Следующая миграция — iter2-db-2 (0008); её начинать только после мержа этой задачи.

## 2. Цель
Добавить в participant_state жизни, позицию дня (этап, модуль, день), начало текущего дня, пропуски подряд и пояс.
Создать таблицу idempotency_keys по канону I2B. Выдать app_api и app_projector минимальные права, в том числе
INSERT в participant_events для проектора (В9 = А). Код API и проектора в этой задаче не меняется.

## 3. Решения Автора (дословно)
- 16.10: «В2 — А (Europe/Moscow временно, поле пояса сразу); В3 — А (флаг только IRONCLAD, по умолчанию выкл., C0/C1 не пропускает, РЕВЬЮЕР); В5 — как предложено; В6 — А; В7 — да; В1 и В4 — после второго окна ИССЛЕДОВАНИЕ»
- 16.10: «В1 — Б (day_marks отдельно, позиция и жизни в participant_state); В4 — В («часы» в проекторе, доставка — бот с ролью app_bot); В8 — А (права прямо app_*, соответствие — комментарием и в DEFECTS)»
- 16.10 (карточки): «В9 — А (INSERT participant_events + USAGE participant_events_id_seq для app_projector — в 0007).» «В10 — А (day_started_at в ключе day_marks, DELETE ни у кого).»
- ШТАБ 16.10 снял Н2 по docs/architecture/normative/I2-wave-b.md@2be268c: «business_logic: must use reader role except in Б10 projector process».
  Следствие: participant_state и жизни пишет ТОЛЬКО app_projector; app_api — только SELECT participant_state.

## 4. Выдержки архитектуры (КОДЕР docs/architecture/** не читает)
- I2B (цитаты ШТАБа, docs/research/iter2-2.md §2): participant_state — обычная таблица, пишет только проектор (E1).
  Жизни — participant_state.lives, границы [0, 3]; 0 жизней → sleeping (Р477).
  life_op: advisory lock → SELECT lives FOR UPDATE → INSERT participant_events kind 'life_op'.
  client_op_id обязателен, TTL 1 ч; таблица idempotency_keys [key, kind, created_at, ttl, result_ref, params_hash_optional];
  ключ «life_op:{pid}:{client_op_id}».
- db-schema.sql, «БЛОК 10»: «GRANT INSERT, UPDATE ON participant_state TO participant_state_projector;
  GRANT SELECT ON participant_state TO participant_state_reader;» INV-1: единственный писатель participant_state — participant_state_projector.
- DM (по docs/research/iter2.md §1): 3.1 — задания открываются в 04:00 по поясу участника; 3.6 — 2 дня молчания подряд = −1 жизнь,
  счётчики обнуляются; 3.21 — смена пояса действует со следующего дня. AL 2.2 — 3 жизни на Этап, шаг −1, точка (этап, модуль, день).
- PostgreSQL: SELECT FOR UPDATE требует право UPDATE хотя бы на одну колонку. У app_api его нет, поэтому заблокировать строку
  participant_state он не может; тест это закрепляет.
- Ключ advisory lock в I2B записан двумя способами ('life:' и 'participant:'). Здесь не решается: запись в DEFECTS делает ШТАБ.
  В миграции замков (advisory lock) нет.

## 5. ЧТО ПРОЧИТАТЬ (КОДЕР)
| Файл | КБ | Зачем |
|---|---|---|
| docs/process/CODER.md | 11,1 | правила окна |
| AGENT-BRIEF.md | 15,0 | факты и запреты |
| docs/STATE.md | 25,8 | состояние |
| docs/tasks/iter2-db-1.md (эта карточка) | ≈ 12 | задача |
| apps/api/migrations/versions/2026_10_09_1200-0006_app_roles_app_roles.py | 5,6 | образец PRIVILEGES и downgrade (не менять) |
| apps/api/tests/test_db_roles.py | 9,3 | правишь одну строку; образец тестов ролей |
| apps/api/tests/expected_tables.txt | 0,8 | правишь целиком |
Чтение КОДЕРА ≈ 80 КБ. Файлы 0005, 0001 и conftest.py не давать: нужные выдержки есть в разделах 8 и 9.

## 6. Файлы
- Создать: apps/api/migrations/versions/2026_10_16_1200-0007_day_state_day_state.py
- Создать: apps/api/tests/test_db_roles_0007.py
- Изменить: apps/api/tests/test_db_roles.py — удалить из PROJECTOR_DENIED ровно одну строку
  "INSERT INTO participant_events (pid) VALUES (gen_random_uuid())", остальное в файле не трогать.
- Изменить: apps/api/tests/expected_tables.txt — целиком, полный текст ниже (14 таблиц).
- Изменить: docs/STATE.md — только если ШТАБ дал строки (первым файлом пакета).

Полный текст expected_tables.txt (шапку из 4 строк # оставить как есть, затем):
    # 0001_init
    participant_state
    stage_publish_log
    outbox
    outbox_dlq
    issuance_log
    anomaly_log
    erasure_blacklist
    privacy_audit_log
    # 0002_tg_user_registry
    tg_user_registry
    # 0003_text_registry
    text_registry
    # 0004_consent_events
    consent_events
    # 0005_participant_events
    participant_events
    participant_state_checkpoints
    # 0007_day_state
    idempotency_keys

## 7. Контракт
Эндпоинтов нет. Новые колонки имеют DEFAULT или NULL, поэтому текущий UPSERT проектора работает без правок (это проверяет тест 1).

## 8. БД — миграция 0007_day_state
revision = "0007_day_state"; down_revision = "0006_app_roles" (точная строка из файла 0006).
Create Date: 2026-10-16 12:00:00. Шапка такая же, как в 0006: from collections.abc import Sequence; branch_labels и depends_on = None.

DDL (upgrade, по порядку):
    ALTER TABLE participant_state
        ADD COLUMN lives smallint NOT NULL DEFAULT 3,
        ADD COLUMN stage_no smallint,
        ADD COLUMN module_no smallint,
        ADD COLUMN day_no smallint,
        ADD COLUMN day_started_at timestamptz,
        ADD COLUMN missed_streak smallint NOT NULL DEFAULT 0,
        ADD COLUMN tz text NOT NULL DEFAULT 'Europe/Moscow'
    ALTER TABLE participant_state ADD CONSTRAINT ck_participant_state_lives_range CHECK (lives BETWEEN 0 AND 3)
    ALTER TABLE participant_state ADD CONSTRAINT ck_participant_state_missed_streak_nonneg CHECK (missed_streak >= 0)
    ALTER TABLE participant_state ADD CONSTRAINT ck_participant_state_tz_not_empty CHECK (tz <> '')
    ALTER TABLE participant_state ADD CONSTRAINT ck_participant_state_day_position CHECK (
        (stage_no IS NULL AND module_no IS NULL AND day_no IS NULL AND day_started_at IS NULL)
        OR (stage_no IS NOT NULL AND module_no IS NOT NULL AND day_no IS NOT NULL AND day_started_at IS NOT NULL
            AND stage_no >= 1 AND module_no >= 1 AND day_no >= 1))
    CREATE TABLE idempotency_keys (
        key         text PRIMARY KEY,
        kind        text NOT NULL,
        created_at  timestamptz NOT NULL DEFAULT now(),
        ttl         interval NOT NULL DEFAULT interval '1 hour',
        result_ref  text,
        params_hash text,
        CONSTRAINT ck_idempotency_keys_key_not_empty CHECK (key <> ''),
        CONSTRAINT ck_idempotency_keys_ttl_positive CHECK (ttl > interval '0'))
    CREATE INDEX idempotency_keys_created_at_idx ON idempotency_keys (created_at)
Почему IS NOT NULL написан явно: в CHECK результат NULL считается «пройдено». Без явного IS NOT NULL позиция
«stage_no NULL, остальные заданы» прошла бы проверку. Не упрощать. Позиция NULL — участник ещё не начал день.
Правильность пояса (что это реальный IANA-пояс) проверяет код, а не CHECK. params_hash — это params_hash_optional канона (NULL допустим).

PRIVILEGES — кортеж (право, объект, роль), как в 0006. GRANT — в upgrade после DDL:
    ("INSERT", "TABLE participant_events", "app_projector"),
    ("USAGE", "SEQUENCE participant_events_id_seq", "app_projector"),
    ("SELECT, INSERT", "TABLE idempotency_keys", "app_api"),
    ("SELECT, INSERT", "TABLE idempotency_keys", "app_projector"),
Обоснование (переносится в docstring миграции):
- app_projector INSERT participant_events и USAGE последовательности: life_op по канону выполняет процесс проектора (В9 = А).
  bigserial берёт номер из последовательности; RETURNING id покрыт SELECT из 0006.
- idempotency_keys SELECT и INSERT у app_api: отчёт дня пишет ключ в той же транзакции, что и событие;
  повтор с тем же ключом читает result_ref. SELECT нужен и для RETURNING.
- idempotency_keys SELECT и INSERT у app_projector: ключ «life_op:{pid}:{client_op_id}».
- UPDATE, DELETE и TRUNCATE не получает никто: result_ref пишется сразу при INSERT в той же транзакции;
  очистка по ttl — отдельная задача позже. FK у таблицы нет.
- participant_state: новых GRANT нет (Н4, см. ниже). advisory lock доступен через PUBLIC.
Docstring обязан содержать (В8): соответствие ролям канона — app_projector = participant_state_projector + participant_state_reader
(членство из 0006); app_api = participant_state_reader (членство из 0006); outbox_writer и outbox_relay — в 0009 (iter2-db-3);
idempotency_keys в каноне ролей нет, поэтому права выданы прямо app_*. Плюс фраза «0001–0006 не меняются».
Н4 подтверждено по коду 0001: GRANT на participant_state выданы на ВСЮ таблицу, а не на колонки. Поэтому новые колонки
сразу доступны: app_projector на запись (INSERT, UPDATE), app_api только на чтение.

downgrade — по образцу 0006: сначала REVOKE в обратном порядке (reversed(PRIVILEGES)), пока таблица существует; затем
    DROP TABLE IF EXISTS idempotency_keys
    ALTER TABLE participant_state DROP CONSTRAINT IF EXISTS <каждое из 4 имён ck_participant_state_…>
    ALTER TABLE participant_state DROP COLUMN IF EXISTS lives, DROP COLUMN IF EXISTS stage_no, (и так все 7 колонок)
Колоночных прав в 0007 нет. Если появятся — отзывать их отдельной строкой, как в 0006.
Образец ALTER, CHECK и downgrade из 0005 (выдержка, сам файл не читать):
    f"""
    ALTER TABLE participant_state ADD CONSTRAINT {PHASE_CHECK}
        CHECK (lifecycle_phase IN (...список...))
    """,
    def downgrade() -> None:
        op.execute(f"ALTER TABLE participant_state DROP CONSTRAINT IF EXISTS {PHASE_CHECK}")
        op.execute(f"DROP TABLE IF EXISTS {CHECKPOINTS_TABLE}")

## 9. Тесты — apps/api/tests/test_db_roles_0007.py (только CI; в Codespaces тесты с БД пропускаются)
Выдержка из tests/conftest.py: migrated_db — фикстура на всю сессию, DSN схемы на head; db_engine — engine суперпользователя,
перед каждым тестом TRUNCATE participant_events, participant_state_checkpoints, participant_state, consent_events,
tg_user_registry RESTART IDENTITY CASCADE; db_api_client — TestClient с настоящей БД.
idempotency_keys db_engine НЕ чистит, поэтому ключи в тестах — уникальные (uuid4). tg_user_id в тестах — 3201–3299.
Из tests.test_db_roles импортировать только обычные функции: role_engine, _assert_denied, _first_launch.
Фикстуры api_engine, projector_engine и api_as_app_api объявить в новом файле копией из test_db_roles.py
(не импортировать: линтер посчитает их неиспользуемыми).
1. Значения по умолчанию после проектора: first-launch под app_api → run_once(projector_engine) → через db_engine
   lives, missed_streak, tz, stage_no, module_no, day_no, day_started_at = (3, 0, 'Europe/Moscow', None × 4).
2. CHECK (под db_engine; строку participant_state вставить напрямую: pid, lifecycle_phase 'onboarding', updated_at now(),
   projector_version 1 — FK у таблицы нет). Каждое из следующих значений → IntegrityError с orig = psycopg CheckViolation:
   lives 4, lives −1, missed_streak −1, tz '', только stage_no = 1, все 4 заданы но day_no = 0, stage_no NULL при трёх заданных.
   Все 4 заданы с номерами ≥ 1 — запись проходит.
3. Н4 через has_column_privilege по 7 новым колонкам: app_projector UPDATE — True; app_api SELECT — True; app_api UPDATE — False.
4. app_projector обновляет новые колонки: UPDATE participant_state SET lives = 2, missed_streak = 1 по своей строке → rowcount 1.
5. app_api читает: SELECT lives, tz, stage_no FROM participant_state — без ошибки.
6. Запреты app_api (параметризованный тест, _assert_denied): UPDATE participant_state SET lives = 2;
   UPDATE participant_state SET tz = 'UTC'; SELECT lives FROM participant_state FOR UPDATE;
   UPDATE idempotency_keys SET result_ref = 'x'; DELETE FROM idempotency_keys; TRUNCATE idempotency_keys.
7. Запреты app_projector: UPDATE participant_events SET actor = 'x'; DELETE FROM participant_events; TRUNCATE participant_events;
   UPDATE idempotency_keys SET result_ref = 'x'; DELETE FROM idempotency_keys; TRUNCATE idempotency_keys.
8. app_projector МОЖЕТ записать событие: first-launch → под projector_engine (engine.begin()) INSERT participant_events
   (pid, kind, payload, actor, actor_role) VALUES (:pid, 'test_0007', CAST('{}' AS jsonb), 'test', 'system') RETURNING id → id > 0.
9. idempotency_keys под каждой ролью: INSERT (key, kind, result_ref) RETURNING created_at, ttl → ttl = timedelta(hours=1);
   SELECT по key находит строку; повтор INSERT того же key → IntegrityError (UniqueViolation);
   INSERT с ON CONFLICT DO NOTHING → 0 строк. Под db_engine: kind NULL → NotNullViolation; ttl '0' → CheckViolation.
10. ПОСЛЕДНИМ в файле — downgrade до "0006_app_roles", в finally — command.upgrade(cfg, "head") (как в test_db_roles.py).
    До и после: to_regclass('public.idempotency_keys') IS NOT NULL; has_table_privilege('app_projector','participant_events','INSERT');
    has_sequence_privilege('app_projector','participant_events_id_seq','USAGE'); колонка lives есть в information_schema.columns.
    До — True × 4, после — False × 4. Права 0006 целы и до, и после (True × 3):
    has_table_privilege('app_projector','participant_events','SELECT'), has_sequence_privilege('app_api','participant_events_id_seq','USAGE'),
    pg_has_role('app_projector','participant_state_projector','MEMBER').
Старый test_downgrade_revokes_privileges (вниз до 0005) с 0007 в цепочке: проверено, ни одна из его 7 проверок не касается
прав, которые выдаёт 0007. 0007 отзывает USAGE последовательности только у app_projector, а проверка 4 смотрит app_api.
Значит, True × 7 и False × 7 остаются; проверки НЕ менять. Упадёт — стоп-правило: права не трогать, лог отдать ШТАБу.
Цель Codespaces: bash tools/check.sh api. Только CI проверит: все тесты с БД и alembic upgrade/downgrade на postgres:16.

## 10. Сервер (отдельное задание ШТАБа после мержа; по SERVER-IRONCLAD.md, «Миграции и тексты (B-3d)»)
1. git pull main. 2. Бэкап: ручной pg_dump -Fc с именем before-0007. 3. DC --profile tools build migrate
   (образ migrate собран на коде 113acb8, в нём нет 0007). 4. alembic upgrade head — только через DC run --rm migrate.
5. Ожидаем: alembic current = 0007_day_state; таблиц 14; у старых строк participant_state lives 3, tz Europe/Moscow;
   has_column_privilege('app_api','participant_state','lives','UPDATE') = false; 7/7 Up, 5 healthy; за 10 мин нет Traceback в projector.
   api и projector не пересобирать: их код не менялся. Откат: downgrade до 0006_app_roles допустим, пока lives никто не пишет
   (до задач iter2-api-*); после этого — только восстановление из бэкапа.

## 11. Запреты
- Не трогать: app/projector.py, app/routers/**, app/db/models.py, tests/conftest.py, миграции 0001–0006, ci.yml, docs/architecture/**.
- Не выдавать права сверх раздела 8. ALTER DEFAULT PRIVILEGES не использовать. advisory lock в миграции не использовать.
- Новых зависимостей нет. Запреты из AGENT-BRIEF.md, раздел 3.
- Стоп-правило: permission denied в живых тестах на право вне раздела 8 → права не расширять, отдать ШТАБу.

## 12. Готовность
Миграция с точным down_revision; 4 CHECK с именами; 4 строки PRIVILEGES; docstring с В8 и Н4; downgrade чистый;
test_db_roles.py — минус одна строка; expected_tables.txt — 14 таблиц; CI 7/7 зелёный; РЕВЬЮЕР — 0 блокирующих.

## 13. Оценка
Автор ≈ 1 ч + сервер 1 задание; кредиты 0 (Р0+).

## 14. РЕВЬЮЕР: да — роли и GRANT БД (B-3), новое право INSERT participant_events у app_projector.
