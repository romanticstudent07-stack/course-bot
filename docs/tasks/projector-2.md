# projector-2 — процесс-проектор: participant_events → participant_state (E1/INV-1)

## 1. Паспорт
- id: projector-2 · PR: «projector-2: проектор participant_state (python -m app.projector)» · ветка: feat/projector-2-projector
- Режим: Р0+ · зависит от: projector-1 (таблицы 0005, модели, бэкфилл). Миграции нет. Начинать после мержа projector-1.
- Заменяет часть docs/tasks/projector.md (удалён в PR docs/tasks-projector). Дальше — projector-3 (compose).
- Первый файл пакета — docs/STATE.md (строки от ШТАБа).

## 2. Цель
Отдельный процесс строит participant_state из журнала participant_events. Запуск: python -m app.projector run | once.
Постоянный контейнер — в projector-3. API в participant_state не пишет никогда (E1, INV-1).

## 3. Решения Автора (дословно)
- «6А» — FSM из I2, после согласий — onboarding.
- STATE: «participant_state пишет только проектор (отдельная задача). lifecycle_phase — D-11.»

## 4. Выдержки архитектуры и кода
- errata-unified E1: «обычная таблица, наполняемая проектором … Запись разрешена только роли
  participant_state_projector, чтение — participant_state_reader, проектор живёт в блоке 10.»
- I2 fsm_participant: «states: [pre_registered, onboarding, active, sleeping, muted, erased]»;
  «pre_registered → onboarding: {trigger: mini_app_first_consent, actor: system}».
- I2: «checkpoint_table: participant_state_checkpoints (pid, last_event_id, at)».
- 0001_init: participant_state (pid uuid PK, lifecycle_phase text NOT NULL, status_flags text[] DEFAULT '{}',
  author_pause_reason, updated_at NOT NULL, projector_version int NOT NULL, last_seen_publish_epoch xid8).
- projector-1: participant_events (id bigserial, pid → tg_user_registry, kind, payload jsonb, publish_epoch, at, actor,
  actor_role); participant_state_checkpoints (pid PK, last_event_id, at); CHECK participant_state_lifecycle_phase_check;
  в app/db/models.py — ParticipantEvent, ParticipantStateCheckpoint, EVENT_KIND_MINI_APP_FIRST_CONSENT.
  Бэкфилл: actor 'migration_0005', payload {"schema_version": 1, "backfill": "0005"}.
- session.py: get_engine(settings) — engine по DSN настроек (кэш по DSN); config.get_settings().

## 5. ЧТО ПРОЧИТАТЬ (размеры: a4c5e29; после projector-1 — уточнит ШТАБ)
docs/process/CODER.md 11,1 КБ; AGENT-BRIEF.md 11,2; docs/STATE.md ≈ 10; эта карточка ≈ 9;
apps/api/app/db/models.py ≈ 8; миграция 0005 (…0005_participant_events_participant_events.py) ≈ 5;
apps/api/app/db/session.py 1,5; apps/api/app/config.py 3,5; apps/api/tests/conftest.py ≈ 6 (фикстуры и очистка).
**Чтение КОДЕРА ≈ 65 КБ.**
Не читать: onboarding.py, test_first_launch.py, миграции 0001–0004, compose, docs/DEFECTS-*.md.

## 6. Файлы (3 + STATE)
Создать: apps/api/app/projector.py; apps/api/tests/test_projector.py (с БД);
apps/api/tests/test_projector_static.py (без БД).

## 7. Контракт
- `python -m app.projector run`: цикл раз в 1 с, пачка до 500 событий; `once` — один проход (для тестов).
  pg_advisory_lock(hashtext('participant_state_projector')) — второй экземпляр ждёт.
- Курсор — по pid: брать события e с e.id > coalesce(c.last_event_id, 0) через LEFT JOIN participant_state_checkpoints c
  USING (pid), ORDER BY e.id, LIMIT 500. Глобальный max(last_event_id) не использовать: коммиты разных pid идут не по порядку id.
- Запись в комментарий модуля (app/projector.py, дословно): «Порядок внутри одного pid держится, пока у pid один писатель
  событий (сейчас — first-launch); новые писатели событий — пересмотреть курсор (заметка для будущих карточек).»
- На пачку — одна транзакция:
  mini_app_first_consent → upsert participant_state (lifecycle_phase 'onboarding', status_flags '{}', updated_at now(),
  projector_version 1); переход разрешён только из «нет строки» или pre_registered.
  Неизвестный kind или запрещённый переход → WARNING (kind и id события, без payload), событие пропустить,
  checkpoint сдвинуть. Checkpoint (pid, last_event_id, at) — upsert.
- Функции: `run_once(engine) -> ProjectorResult(processed, skipped)` — пачки по 500, пока новые события есть;
  `main(argv) -> int`. Аргумент не run и не once → usage, exit 2, к БД не обращаться.
  once печатает «projector once: обработано K, пропущено S».
- Блокировка: run — держит lock на отдельном соединении всё время работы; once — lock → проход → unlock.
- Upsert: INSERT … ON CONFLICT (pid) DO UPDATE … WHERE participant_state.lifecycle_phase = 'pre_registered';
  строка есть с другой фазой → запрещённый переход. author_pause_reason и last_seen_publish_epoch не трогать.
- Логи: logger "app.projector". WARNING «projector: skip event id=<id> kind=<kind> (<причина>)» — без payload и pid.
  Сбой БД в run → WARNING «projector: db error (<ИмяКласса>)», пауза 5 с, повтор; без traceback и текста исключения.
  В обычной работе ERROR нет (живая проверка projector-3 ищет ERROR).
- SQL записи в participant_state — только в app/projector.py.

## 8. БД
Миграции нет. Пишет participant_state и participant_state_checkpoints; participant_events только читает.

## 9. Тесты
test_projector.py (с БД — CI). Участник: INSERT tg_user_registry (pid, tg_user_id, created_via, created_at) VALUES
(gen_random_uuid(), <id>, 'mini_app_first_launch', now()); событие — INSERT participant_events напрямую.
1. Событие mini_app_first_consent → run_once → lifecycle_phase 'onboarding', status_flags '{}', projector_version 1;
   checkpoint pid = id события.
2. once повторно → без изменений (processed 0, updated_at прежний).
3. Неизвестный kind → пропущен, checkpoint сдвинут, строки participant_state нет; WARNING в caplog с kind и id;
   метка "secret-payload-1" из payload в caplog.text отсутствует.
4. Запрещённый переход: строка participant_state с 'active' → событие → WARNING; фаза 'active'; checkpoint сдвинут.
5. Сквозной: first-launch через db_api_client → run_once → у pid onboarding.
6. Бэкфилл (перенесено из projector-1): A — событие как от бэкфилла (actor 'migration_0005', payload с "backfill"),
   B — участник без события → once → у A onboarding, у B строки participant_state нет.
7. Пачка: 501 событие (501 участник) → run_once → processed 501; у каждого pid checkpoint = id его события.
10. Пропуск по порядку: событие pid B (бо́льший id) обработано и записано в checkpoint раньше, затем вставлено
   событие pid A с меньшим id (явный id через INSERT … (id, …) или setval) → run_once → у A onboarding
   (событие не потеряно). Явные id брать большими (например 1000000002 для B и 1000000001 для A), чтобы
   не столкнуться с id из sequence.
test_projector_static.py (без БД):
8. E1: в apps/api/app/** нет INSERT INTO participant_state / UPDATE participant_state (регистр не важен; после имени
   граница слова — participant_state_checkpoints не совпадает) вне app/projector.py.
9. main(["bad"]) → 2; БД не трогали (DSN недоступной БД из conftest — без 503 и без ожидания).
Цель check.sh: api. Только CI: 1–7 и 10.

## 10. Живые проверки (после мержа; СЕРВЕРНЫЙ; только числа)
1. pull → пересборка api (projector.py в образе) → 6/6 Up, 4 healthy.
2. exec api python -m app.projector once → «обработано N, пропущено 0» (N — из projector-1).
3. SELECT count(*) FROM participant_state → N (все участники с C1 получили строку из бэкфилла).
   SELECT lifecycle_phase, count(*) FROM participant_state GROUP BY 1 → onboarding | N.
4. Повтор once → «обработано 0, пропущено 0». logs api за 10 мин без ERROR.

## 11. Запреты
AGENT-BRIEF §3. Плюс: participant_state пишет только app/projector.py; миграций нет; compose не трогать (projector-3);
роли, GRANT, отдельный DSN — B-3a; payload и pid в лог не писать; onboarding.py, models.py, conftest.py не менять
(нужна правка — стоп, вопрос ШТАБу); новых зависимостей нет; docs/DEFECTS-*.md не читать и не править.

## 12. Готово, когда
CI 7/7; сервер 1–4.

## 13. Оценка
Часы Автора ~1; запросов КОДЕРА 2–3; кредиты 0 (Р0+).

## 14. РЕВЬЮЕР: нет — обоснование
Отдельный процесс: читает participant_events, пишет только participant_state и checkpoints. Не трогает initData, 18+,
согласия (consent_events не читает и не пишет), rate-limit, оплату. Роли и GRANT проектора — B-3a (там РЕВЬЮЕР есть).
Условие: КОДЕР трогает onboarding.py, consent_events или роли/GRANT → ставим «да».
