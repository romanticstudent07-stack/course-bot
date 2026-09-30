# projector — журнал participant_events + проектор participant_state (E1/INV-1)

## 1. Паспорт
- id: projector · PR: «projector: participant_events + бэкфилл + проектор participant_state (миграция 0005)» · ветка: feat/projector
- Режим: Р0+ · зависит от: 1e-2 (порядок), 1e-1 (first-launch, consent_events).
- Миграция: revision 0005_participant_events, down_revision 0004_consent_events. Начинать после мержа 1e-2.

## 2. Цель
First-launch пишет событие в журнал participant_events; отдельный процесс-проектор строит из него participant_state.
Участники, уже давшие C1, получают событие бэкфиллом в миграции. API в participant_state не пишет никогда (E1, INV-1).

## 3. Решения Автора (дословно)
- «6А» — FSM из I2, после согласий — onboarding. «7 да (participant_events, D-15)».
- STATE: «participant_state пишет только проектор (отдельная задача). lifecycle_phase — D-11.»
- Бэкфилл — да: миграция 0005 каждому pid с consent_events (kind C1, action give) без события вставляет
  participant_events kind 'mini_app_first_consent'.

## 4. Выдержки архитектуры
- errata-unified E1: «обычная таблица, наполняемая проектором … Запись разрешена только роли
  participant_state_projector, чтение — participant_state_reader, проектор живёт в блоке 10.»
- I2 participant_state_contract.storage.event_log: «table: participant_events; append_only: true;
  columns: [id, pid, kind, payload, publish_epoch, at, actor, actor_role]; indexes: [(pid, at), (kind, at)]»;
  «checkpoint_table: participant_state_checkpoints (pid, last_event_id, at)».
- I2 fsm_participant: «states: [pre_registered, onboarding, active, sleeping, muted, erased]»;
  «pre_registered → onboarding: {trigger: mini_app_first_consent, actor: system}».
- build-order.md, Уровень 2, п.1: «participant_state_projector (владелец Б10) — читает state_transition_log,
  пишет participant_state» — расхождение имён → D-15.
- 0001_init: participant_state (pid uuid PK, lifecycle_phase text NOT NULL, status_flags text[] DEFAULT '{}',
  author_pause_reason, updated_at NOT NULL, projector_version int NOT NULL, last_seen_publish_epoch xid8).

## 5. ЧТО ПРОЧИТАТЬ
apps/api/app/routers/onboarding.py, apps/api/app/participants.py, apps/api/app/db/models.py, apps/api/app/db/session.py,
apps/api/app/config.py, миграции 0001 и 0004, apps/api/tests/conftest.py, apps/api/tests/test_first_launch.py,
apps/api/tests/expected_tables.txt, infra/docker-compose.dev.yml, docs/DEFECTS-FOUND.md.

## 6. Файлы (10)
Создать: apps/api/migrations/versions/<дата>-0005_participant_events_participant_events.py; apps/api/app/projector.py;
apps/api/tests/test_projector.py.
Изменить: apps/api/app/db/models.py (ParticipantEvent, ParticipantStateCheckpoint; participant_state не моделировать — xid8);
apps/api/app/routers/onboarding.py (событие в той же транзакции); apps/api/tests/test_first_launch.py;
apps/api/tests/conftest.py (TRUNCATE новых таблиц, CASCADE);
apps/api/tests/expected_tables.txt (+ «# 0005_participant_events»: participant_events, participant_state_checkpoints → 13);
infra/docker-compose.dev.yml (сервис projector); docs/DEFECTS-FOUND.md (D-11 → решено 6А; новая D-15).

## 7. Контракт
- First-launch: только когда участник СОЗДАН (не при повторе) — INSERT participant_events (pid, kind
  'mini_app_first_consent', payload {"schema_version": 1}, actor 'system', actor_role 'system') в ТОЙ ЖЕ транзакции,
  что pid и consent_events. Порядок проверок first-launch не менять.
- Участники, созданные ДО этой задачи и давшие C1, получают событие бэкфиллом миграции 0005 (раздел 8);
  проектор строит им participant_state так же, как новым. Участники без C1 (созданные до 1e-1) события не получают.
- `python -m app.projector run`: цикл раз в 1 с, пачка до 500 событий; `once` — один проход (для тестов).
  pg_advisory_lock(hashtext('participant_state_projector')) — второй экземпляр ждёт.
  Курсор = max(last_event_id) из checkpoints. На пачку — одна транзакция:
  mini_app_first_consent → upsert participant_state (lifecycle_phase 'onboarding', status_flags '{}', updated_at now(),
  projector_version 1); переход разрешён только из «нет строки» или pre_registered.
  Неизвестный kind или запрещённый переход → WARNING (kind и id события, без payload), событие пропустить,
  checkpoint сдвинуть. Checkpoint (pid, last_event_id, at) — upsert.
- Compose: сервис projector — образ api, command python -m app.projector run, тот же env_file, depends_on db (healthy),
  restart unless-stopped, mem_limit 128m (сумма 1664 → 1792 МБ ≤ 2 ГБ), healthcheck: disable: true
  (HEALTHCHECK Dockerfile api стучится на /healthz — у проектора его нет).

## 8. БД — миграция 0005_participant_events
- participant_events: id bigserial PK; pid uuid NOT NULL REFERENCES tg_user_registry(pid); kind text NOT NULL;
  payload jsonb NOT NULL; publish_epoch bigint NULL; at timestamptz NOT NULL DEFAULT now(); actor text NOT NULL;
  actor_role text NOT NULL. Индексы (pid, at), (kind, at). Партиций pid_bucket в И1 нет (D-15).
- participant_state_checkpoints: pid uuid PK; last_event_id bigint NOT NULL; at timestamptz NOT NULL DEFAULT now().
- ALTER TABLE participant_state ADD CONSTRAINT participant_state_lifecycle_phase_check
  CHECK (lifecycle_phase IN ('pre_registered','onboarding','active','sleeping','muted','erased')) — решение 6А.
- Бэкфилл (после CREATE TABLE, в той же миграции, op.execute): для каждого pid, у которого есть consent_events
  с kind 'C1' и action 'give', и нет participant_events kind 'mini_app_first_consent', — один INSERT:
  kind 'mini_app_first_consent', payload {"schema_version": 1, "backfill": "0005"}, at = время самого раннего give C1,
  actor 'migration_0005', actor_role 'system'. Одно событие на pid (DISTINCT ON pid / GROUP BY pid), NOT EXISTS —
  повтор не создаёт дублей. consent_events и tg_user_registry бэкфилл только читает. participant_state не пишет —
  строит проектор.
- downgrade: DROP CONSTRAINT, DROP TABLE participant_state_checkpoints, DROP TABLE participant_events
  (события бэкфилла уходят вместе с таблицей).
- D-15: build-order — state_transition_log, I2 — participant_events (выбрано); партиции pid_bucket отложены;
  ранние участники с C1 получают событие бэкфиллом 0005 (actor 'migration_0005'), без C1 — нет. Ждём правки зеркала: да.

## 9. Тесты (с БД — CI)
first-launch → ровно 1 событие; повтор → по-прежнему 1; once → lifecycle_phase = 'onboarding'; once повторно →
без изменений; неизвестный kind → пропущен, checkpoint сдвинут; CHECK отклоняет 'banned_soft'; expected_tables = 13.
Бэкфилл: downgrade до 0004 → вставить pid A (consent_events C0 + C1 give) и pid B (только tg_user_registry, без C1) →
upgrade 0005 → у A ровно 1 событие mini_app_first_consent с actor 'migration_0005' и at = at give C1, у B событий нет;
повторный downgrade 0004 / upgrade head → у A по-прежнему 1; once → у A onboarding, у B строки participant_state нет.
Без БД: статический тест — в apps/api/app/** нет INSERT/UPDATE participant_state вне app/projector.py (E1).

## 10. Живые проверки (после мержа)
1. СЕРВЕРНЫЙ сначала: SELECT count(DISTINCT pid) FROM consent_events WHERE kind = 'C1' AND action = 'give'
   (только число, без строк) — запомнить N.
2. Бэкап → upgrade head (0005) → таблиц 13 → SELECT count(*) FROM participant_events → N → 7/7 Up (добавился projector),
   4 healthy → logs projector без ERROR.
3. SELECT count(*) FROM participant_state → N (все участники с C1 получили строку из бэкфилла).
4. Автор на своём аккаунте: открыть Mini App → повторный first-launch → 201 тот же pid; SELECT count(*) FROM
   participant_events → по-прежнему N; SELECT lifecycle_phase, count(*) FROM participant_state GROUP BY 1 →
   onboarding | N (без pid в выводе). Новый аккаунт не нужен.

## 11. Запреты
AGENT-BRIEF §3. Плюс: API не пишет participant_state; миграция не пишет participant_state (только бэкфилл событий);
consent_events и tg_user_registry не менять; состояний banned_* нет; роли и GRANT не трогать (это B-3).

## 12. Готово, когда
CI 7/7; D-11 и D-15 записаны; сервер 7/7 Up; participant_state = N (onboarding) после бэкфилла; повтор Автора дублей не дал.

## 13. Оценка
Часы Автора 2–3; запросов КОДЕРА 2–3; кредиты 0 (Р0+).

## 14. РЕВЬЮЕР: нет — обоснование
Не трогает initData, 18+, rate-limit, оплату; согласия не меняются — в first-launch только добавляется INSERT события
в готовую транзакцию, порядок проверок прежний, тесты 1e-1 остаются; бэкфилл consent_events только читает.
Роли и GRANT проектора — в B-3 (там РЕВЬЮЕР есть).
Условие: КОДЕР меняет порядок проверок first-launch или запись consent_events → ставим «да».
