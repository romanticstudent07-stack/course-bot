# projector-1 — журнал participant_events: миграция 0005 + бэкфилл, событие в first-launch (D-16, D-11)

## 1. Паспорт
- id: projector-1 · PR: «projector-1: participant_events + бэкфилл + событие first-launch (миграция 0005)» · ветка: feat/projector-1-events
- Режим: Р0+ · зависит от: prep-projector (STATE, D-11/D-16 записаны), 1e-1 (first-launch, consent_events).
- Миграция: revision 0005_participant_events, down_revision 0004_consent_events. Начинать после мержа prep-projector.
  Единственная миграция пачки. Цепочка: projector-1 → projector-2 → projector-3 → miniapp-csp.
- Заменяет часть docs/tasks/projector.md (удалён в PR docs/tasks-projector; карточка разрезана по правилу 3-Б).
- Первый файл пакета — docs/STATE.md (строки от ШТАБа).

## 2. Цель
First-launch пишет событие в журнал participant_events. Участники, уже давшие C1, получают событие бэкфиллом
в миграции. participant_state строит проектор (projector-2). API в participant_state не пишет никогда (E1, INV-1).

## 3. Решения Автора (дословно)
- «6А» — FSM из I2, после согласий — onboarding. «7 да (participant_events, D-15)».
  Номер дефекта: D-15 занят ревью #38 → журнал participant_events = D-16 (ШТАБ, 02.10).
- STATE: «participant_state пишет только проектор (отдельная задача). lifecycle_phase — D-11.»
- Бэкфилл — да: миграция 0005 каждому pid с consent_events (kind C1, action give) без события вставляет
  participant_events kind 'mini_app_first_consent'.

## 4. Выдержки архитектуры и кода
- errata-unified E1: «обычная таблица, наполняемая проектором … Запись разрешена только роли
  participant_state_projector, чтение — participant_state_reader, проектор живёт в блоке 10.»
- I2 participant_state_contract.storage.event_log: «table: participant_events; append_only: true;
  columns: [id, pid, kind, payload, publish_epoch, at, actor, actor_role]; indexes: [(pid, at), (kind, at)]»;
  «checkpoint_table: participant_state_checkpoints (pid, last_event_id, at)».
- I2 fsm_participant: «states: [pre_registered, onboarding, active, sleeping, muted, erased]»;
  «pre_registered → onboarding: {trigger: mini_app_first_consent, actor: system}».
- 0001_init: participant_state (pid uuid PK, lifecycle_phase text NOT NULL, status_flags text[] DEFAULT '{}',
  author_pause_reason, updated_at NOT NULL, projector_version int NOT NULL, last_seen_publish_epoch xid8).
- onboarding.py (a4c5e29), docstring: «Порядок (docs/tasks/1e-1.md, раздел 7 — НЕ МЕНЯТЬ): 1) initData (роутер)
  → 2) тело (Pydantic) → 3) возраст БЕЗ БД → 403 → 4) обязательные согласия → 422 → 5) ОДНА транзакция: тексты
  согласий из text_registry (нет текста → откат, 503) → участник (get_or_create) → consent_events: give …».
- participants.py (не читать): get_or_create_participant без COMMIT — транзакцией владеет вызывающий;
  возвращает Participant(pid, short_no, created) — created True, если создан этим вызовом.
- models.py: participant_state (0001) НЕ моделируется (xid8). test_db_models: compare_metadata только по таблицам моделей.
- Миграции — стиль 0004: docstring с источниками, кортеж DDL, op.execute в upgrade.

## 5. ЧТО ПРОЧИТАТЬ (размеры по a4c5e29)
docs/process/CODER.md 11,1 КБ; AGENT-BRIEF.md 11,2; docs/STATE.md ≈ 10; эта карточка ≈ 9;
apps/api/app/routers/onboarding.py 13,8; apps/api/app/db/models.py 6,3;
apps/api/migrations/versions/2026_10_01_1200-0004_consent_events_consent_events.py 2,7;
apps/api/tests/conftest.py 5,7; apps/api/tests/test_db_models.py 3,9; apps/api/tests/expected_tables.txt 0,6.
**Чтение КОДЕРА ≈ 75 КБ.**
Не читать: tests/test_first_launch.py (24,7 — не меняется), participants.py, config.py, session.py, compose,
docs/DEFECTS-*.md.

## 6. Файлы (7 + STATE)
Создать: apps/api/migrations/versions/<ГГГГ_ММ_ДД>_1200-0005_participant_events_participant_events.py (дата — день
работы, формат имени как у 0004); apps/api/tests/test_participant_events.py.
Изменить: apps/api/app/db/models.py (ParticipantEvent, ParticipantStateCheckpoint; participant_state не моделировать — xid8);
apps/api/app/routers/onboarding.py (событие в той же транзакции; в docstring — строка про событие);
apps/api/tests/conftest.py (TRUNCATE: + participant_events; participant_state_checkpoints и participant_state — FK нет,
перечислить явно); apps/api/tests/test_db_models.py (13 таблиц; цикл начинается с head → 0004);
apps/api/tests/expected_tables.txt — целиком: шапка и блоки 0001–0004 как есть, в конце:
    # 0005_participant_events
    participant_events
    participant_state_checkpoints
Итого 13 таблиц.

## 7. Контракт
- First-launch: только когда участник СОЗДАН (не при повторе) — INSERT participant_events (pid, kind
  'mini_app_first_consent', payload {"schema_version": 1}, actor 'system', actor_role 'system') в ТОЙ ЖЕ транзакции,
  что pid и consent_events. Порядок проверок first-launch не менять.
- Место: шаг 5, после INSERT consent_events, до commit; participant.created == False → ничего. Ошибка INSERT события
  идёт тем же путём, что ошибка INSERT consent_events (откат, pid не создан); новых кодов ответа нет.
- Участники, созданные ДО этой задачи и давшие C1, получают событие бэкфиллом миграции 0005 (раздел 8);
  проектор строит им participant_state так же, как новым. Участники без C1 (созданные до 1e-1) события не получают.
- models.py: константы EVENT_KIND_MINI_APP_FIRST_CONSENT = "mini_app_first_consent", ACTOR_SYSTEM = "system"
  (их импортирует projector-2); ParticipantEvent (payload — JSONB, FK pid → tg_user_registry.pid, индексы с именами
  раздела 8); ParticipantStateCheckpoint. В docstring моделей — блок про 0005 в стиле файла.

## 8. БД — миграция 0005_participant_events
- participant_events: id bigserial PK; pid uuid NOT NULL REFERENCES tg_user_registry(pid); kind text NOT NULL;
  payload jsonb NOT NULL; publish_epoch bigint NULL; at timestamptz NOT NULL DEFAULT now(); actor text NOT NULL;
  actor_role text NOT NULL. Индексы (pid, at), (kind, at). Партиций pid_bucket в И1 нет (D-16).
  Имена индексов: participant_events_pid_at_idx, participant_events_kind_at_idx.
- participant_state_checkpoints: pid uuid PK; last_event_id bigint NOT NULL; at timestamptz NOT NULL DEFAULT now().
- ALTER TABLE participant_state ADD CONSTRAINT participant_state_lifecycle_phase_check
  CHECK (lifecycle_phase IN ('pre_registered','onboarding','active','sleeping','muted','erased')) — решение 6А.
- Бэкфилл (после CREATE TABLE, в той же миграции, op.execute): для каждого pid, у которого есть consent_events
  с kind 'C1' и action 'give', и нет participant_events kind 'mini_app_first_consent', — один INSERT:
  kind 'mini_app_first_consent', payload {"schema_version": 1, "backfill": "0005"}, at = время самого раннего give C1,
  actor 'migration_0005', actor_role 'system'. Одно событие на pid (DISTINCT ON pid / GROUP BY pid), NOT EXISTS —
  повтор не создаёт дублей. consent_events и tg_user_registry бэкфилл только читает. participant_state не пишет —
  строит проектор. Образец:
    INSERT INTO participant_events (pid, kind, payload, at, actor, actor_role)
    SELECT ce.pid, 'mini_app_first_consent', '{"schema_version": 1, "backfill": "0005"}'::jsonb,
           min(ce.at), 'migration_0005', 'system'
    FROM consent_events ce
    WHERE ce.kind = 'C1' AND ce.action = 'give'
      AND NOT EXISTS (SELECT 1 FROM participant_events pe
                      WHERE pe.pid = ce.pid AND pe.kind = 'mini_app_first_consent')
    GROUP BY ce.pid
    ORDER BY min(ce.at), ce.pid
- downgrade: DROP CONSTRAINT, DROP TABLE participant_state_checkpoints, DROP TABLE participant_events
  (события бэкфилла уходят вместе с таблицей).

## 9. Тесты (с БД — только CI; check.sh api их пропускает)
test_participant_events.py:
1. first-launch нового tg_user_id → ровно 1 событие: kind mini_app_first_consent, payload {"schema_version": 1},
   actor 'system', actor_role 'system'.
2. Повтор first-launch → по-прежнему 1.
3. CHECK: INSERT participant_state (pid gen_random_uuid(), lifecycle_phase 'banned_soft', updated_at now(),
   projector_version 1) → IntegrityError; то же с 'onboarding' — проходит. SQL прямо в тесте (статический тест E1
   из projector-2 смотрит только apps/api/app/**).
4. Бэкфилл: downgrade до 0004 → вставить pid A (consent_events C0 + C1 give) и pid B (только tg_user_registry, без C1) →
   upgrade 0005 → у A ровно 1 событие mini_app_first_consent с actor 'migration_0005' и at = at give C1, у B событий нет;
   повторный downgrade 0004 / upgrade head → у A по-прежнему 1. Alembic — через _alembic_config из conftest;
   в finally — upgrade head. Участник: INSERT tg_user_registry (pid, tg_user_id, created_via, created_at) VALUES
   (gen_random_uuid(), 2201, 'mini_app_first_launch', now()). Согласие: text_key 'legal.consent_c1_pdn' /
   'legal.consent_c0_age_18_plus' (seed заливает db_engine), ver_of_text, text_snapshot, created_via 'mini_app_first_launch'.
test_db_models.py: таблицы = expected_tables.txt (13); цикл head → 0004 (нет participant_events и
participant_state_checkpoints) → 0003 → 0002 → 0001 → base → head; модели = схема.
Перенесено в projector-2: «once → у A onboarding, у B строки participant_state нет».
Цель check.sh: api. Только CI: тесты с БД.

## 10. Живые проверки (после мержа; СЕРВЕРНЫЙ; в выводе только числа, без pid)
1. СЕРВЕРНЫЙ сначала: SELECT count(DISTINCT pid) FROM consent_events WHERE kind = 'C1' AND action = 'give'
   (только число, без строк) — запомнить N.
2. Бэкап ОБЯЗАТЕЛЕН до миграции: ручной pg_dump -Fc (before-0005). Нет бэкапа → upgrade не запускать.
   Downgrade ниже 0004 запрещён; откат 0005 на сервере — только через бэкап и по решению Автора.
3. pull → пересборка api → exec api alembic upgrade head → alembic current = 0005_participant_events → таблиц 13
   (= expected_tables.txt) → SELECT count(*) FROM participant_events → N → SELECT count(*) FROM participant_state → 0
   (проектора ещё нет) → 6/6 Up, 4 healthy.
4. Автор на своём аккаунте: закрыть и открыть Mini App (кэш) → повторный first-launch → 201 тот же pid;
   SELECT count(*) FROM participant_events → по-прежнему N.

## 11. Запреты
AGENT-BRIEF §3. Плюс: API не пишет participant_state; миграция не пишет participant_state (только бэкфилл событий);
consent_events и tg_user_registry не менять; состояний banned_* нет; роли и GRANT не трогать (это B-3a);
порядок проверок first-launch и запись consent_events не менять; test_first_launch.py не трогать;
проектор и compose — не здесь; docs/DEFECTS-*.md не читать и не править.

## 12. Готово, когда
CI 7/7; сервер 1–4: событий N, повтор Автора дублей не дал.

## 13. Оценка
Часы Автора ~1,5 (с бэкапом и миграцией); запросов КОДЕРА 2–3; кредиты 0 (Р0+).

## 14. РЕВЬЮЕР: нет — обоснование (дословно из docs/tasks/projector.md)
Не трогает initData, 18+, rate-limit, оплату; согласия не меняются — в first-launch только добавляется INSERT события
в готовую транзакцию, порядок проверок прежний, тесты 1e-1 остаются; бэкфилл consent_events только читает.
Роли и GRANT проектора — в B-3 (там РЕВЬЮЕР есть).
Условие: КОДЕР меняет порядок проверок first-launch или запись consent_events → ставим «да».
