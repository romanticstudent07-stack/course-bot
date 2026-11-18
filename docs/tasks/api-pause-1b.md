# api-pause-1b — T2b: часы пауз (pause_ops.tick), виды ключей, НП3 после паузы
Hash main: edbd726 · Область: API (часы проектора) · Начинать после T2a (docs/tasks/api-pause-1a.md) в том же промпте.
Оценка и РЕВЬЮЕР — в api-pause-1a (пара 1 300 / стоп 1 950; РЕВЬЮЕР нет). Миграция не нужна.
Решения Р1–Р15 и контракт — api-pause-1a, разделы 2 и 5; здесь их не повторять, только ссылаться.

## 1. Зачем
Кто-то должен в 00:00 начинать одобренные паузы, гасить неодобренные заявки и заканчивать паузы по сроку. Это часы в run_forever, как life_ops.tick. И после паузы участник должен получить НП3 «задания открыты» про перевыданный день.

## 2. Решения (метка К-6)
- Ч1 pause_ops.tick(engine, now) вызывает run_forever раз в PAUSE_OPS_INTERVAL_S, сразу после life_ops.tick; once его не вызывает (как life_ops). [ШТАБ-тех; pause-2 §9]
- Ч2 Часы пишут только idempotency_keys и participant_events; статус и состояние применяет проектор. [канон E1/INV-1; по коду: life_ops docstring]
- Ч3 Кандидаты (своя транзакция, только чтение; не больше MAX_PER_TICK, самые старые start_at / planned_end_at; остальные — в следующем тике): A — kind user, status approved, start_at ≤ now; B — kind user, status requested, start_at ≤ now; C — kind user, status active, planned_end_at ≤ now. [Р2, Р5, Р14 — api-pause-1a]
- Ч4 Каждый pid — отдельная транзакция под lock_participant (как life_ops); строки паузы и состояния читаются заново; проектор не догнал pid (life_ops._PENDING_EVENT) — пропуск до следующего тика. [по коду: ШТАБ З2 п.4]
- Ч5 A: вчерашний день должен быть закрыт — day_clock.is_overdue(...) = False (иначе пропуск: сначала закрытие дня life_ops, потом пауза; без гонки в 00:02). Затем pause_rules.start_refusal: None → ключ pause_start + pause_started {pause_id}; иначе ключ pause_start + pause_start_failed {pause_id, reason}. [ШТАБ-тех; Р13, Р15]
- Ч6 B: ключ pause_start + pause_start_failed {pause_id, reason: "not_approved"}. [Автор 18.11 — Р14]
- Ч7 C: ключ pause_end + pause_ended {pause_id, reason: "expired"}. [Р5]
- Ч8 Ключи: новые виды day_keys pause_start (на pause_id: started и start_failed взаимно исключают друг друга) и pause_end (на pause_id); формат ключа и TTL — как у вида life_op (по коду day_keys). Повтор тика ключ не пишет второй раз. [ШТАБ-тех]
- Ч9 НП3 после паузы: в notify_ops.REISSUE_KINDS добавить "pause_ended" (комментарий «T2 дополнит» убрать). Правило is_reissue сейчас: next_midnight(at, tz) = текущий day_started_at. Для pause_ended reason by_participant оно верно (D = next_midnight). Для reason expired ожидаемый D = day_clock.last_midnight(at, tz) (Р5): ветка по (kind, payload.reason) в is_reissue / _REISSUE_ALL / _REISSUE_ONE — где проверка, там и правка, по коду. D в payload не класть (Ш2: D из at события). [по коду: ШТАБ З2 п.4; ШТАБ-тех]

## 3. Что уже в main
life_ops.tick (образец целиком: кандидаты, lock_participant, _PENDING_EVENT, ключ + события, TickResult), BLOCKING_FLAGS, day_keys.TTL_BY_KIND, notify_ops.REISSUE_KINDS = ("restart_paid", "revive_by_author") (по коду: ШТАБ З2 п.4).

## 4. Что сделать
- apps/api/app/pause_ops.py — новый: tick → TickResult(started, failed, ended, skipped); ручная проверка python -m app.pause_ops dry-run <pid> (роль проектора, только SELECT, ROLLBACK; печатает кандидата и решение «если сейчас»), как life_ops.
- apps/api/app/projector.py — вызов pause_ops.tick в run_forever (Ч1), константа PAUSE_OPS_INTERVAL_S рядом с LIFE_OPS_INTERVAL_S (то же значение). PROJECTOR_VERSION не меняется (8 из T2a).
- apps/api/app/day_keys.py — виды pause_start, pause_end и их TTL (Ч8).
- apps/api/app/notify_ops.py — Ч9.

## 5. Файлы (≤ 12)
Новые: apps/api/app/pause_ops.py; apps/api/tests/test_pause_ops.py; apps/api/tests/test_notify_pause.py.
Правка: apps/api/app/projector.py; apps/api/app/day_keys.py; apps/api/app/notify_ops.py; apps/api/tests/test_day_current.py; apps/api/tests/test_projector_revive.py.

## 6. Задетые тесты (правило «Т»; по коду: ШТАБ З2 п.4)
- tests/test_day_current.py:84 — TTL_BY_KIND сверяется целиком → добавить pause_start, pause_end.
- tests/test_projector_revive.py:82 — assert REISSUE_KINDS == ("restart_paid", "revive_by_author") → добавить "pause_ended".
- Не задеты: tests/test_projector_restart.py:75 ("restart_paid" in REISSUE_KINDS); tests/test_life_ops.py:408 (BLOCKING_FLAGS).

## 7. Новые тесты
test_pause_ops.py: A при открытом вчерашнем дне — пропуск, после day_closed — pause_started; A с block_lives / no_budget → pause_start_failed с reason; B → not_approved; C → pause_ended expired; проектор не догнал — пропуск; два тика подряд — одно событие (ключ); MAX_PER_TICK; полный путь tick → проектор → active → tick → ended; кандидаты не берут kind author / shadow.
test_notify_pause.py: после pause_ended by_participant и после expired НП3 tasks_open приходит про перевыданный день один раз; во время паузы НП1 / НП3 / лестницы нет (BLOCKING_FLAGS, без правок).

## 8. Чтение Агента (T2b)
Сверх прочитанного в T2a: эта карточка ≈ 6; apps/api/app/life_ops.py 17,7; apps/api/app/notify_ops.py 26,6; apps/api/app/day_keys.py (размер — ШТАБ); apps/api/tests/test_day_current.py, tests/test_projector_revive.py — только строки раздела 6.
Пара одним промптом выходит > 140 КБ (T2a ≈ 129 + T2b ≈ 50 + day_keys) → ШТАБ делит на два промпта.

## 9. Готово, когда
CI зелёный; run_forever вызывает pause_ops.tick, once — нет; часы пишут только ключи и события; REISSUE_KINDS содержит pause_ended; в описании PR — отличия от карточки или «нет».

## 10. Вне задачи
Уведомления о паузе (одобрено, началась, закончилась) — T4. Эндпоинты — T3. kind author / shadow — Панель.

## 11. Прочитано (ПРОЕКТИРОВЩИК)
Как в api-pause-1a §12; life_ops, notify_ops, day_keys, test_day_current, test_projector_revive — по выписке ШТАБа З2 п.4 (сам не читал целиком).
