# iter2-api-2a — замок pid + тестовый вход в день (флаг) + отметки блоков

## 1. Паспорт
- id: iter2-api-2a. PR: «iter2-api-2a: замок pid, test-enter под флагом, PUT day/marks, kind day_entered».
- Ветка: feat/iter2-api-2a. Режим: Р0+. Начинать после мержа iter2-api-1. Миграций нет.

## 2. Цель
Тестовый вход в день 1 под флагом (только IRONCLAD, по умолчанию выкл.) через событие day_entered.
Проектор ставит позицию и day_started_at. Отметки блоков пишутся в day_marks.
Все писатели событий существующего pid — под одним advisory lock.

## 3. Решения Автора (дословно)
- «В3 — А (флаг только IRONCLAD, по умолчанию выкл., C0/C1 не пропускает, РЕВЬЮЕР)».
- «В10 — А (перевыдача дня — новый day_started_at)»; «В16 — А»; «В19 — А»; «В20 — да (расхождение с I2B → DEFECTS)»; «В21 — А»; «В22 — А».
- Флаг включается отдельным заданием после выката (Ш5).
- Источник контракта — docs/research/iter2-api.md §3–§6.

## 4. Выдержки
- 03-day-mechanics.md §3.3: «(состояние переключаемо до отправки отчёта)».
- projector.py, docstring: «Порядок внутри одного pid держится, пока у pid один писатель событий … новые писатели событий — пересмотреть курсор».
  Решение — research §4: замок pg_advisory_xact_lock(hashtext('participant:' || pid)) до INSERT, держится до commit.
- E1: API в participant_state не пишет никогда (INV-1).
- Требования РЕВЬЮЕРА #95:
  - pid только из initData через tg_user_registry;
  - day_started_at из participant_state в той же транзакции;
  - белый список block_id + длина;
  - tombstoned — не писать;
  - тест «pid и day_started_at из тела игнорируются».

## 5. ЧТО ПРОЧИТАТЬ (КОДЕР)
AGENT-BRIEF.md 15,0; apps/api/app/projector.py 11,3; apps/api/app/config.py 5,5; apps/api/app/participants.py 4,8;
apps/api/app/routers/day.py (из iter2-api-1); apps/api/app/day_keys.py, day_content.py (из iter2-api-1);
apps/api/app/routers/onboarding.py (проверка C0/C1 и Ш2; КБ — ШТАБ); compose-файл сервиса api и .env.example (пути — ШТАБ);
tests проектора (образец; КБ — ШТАБ). Чтение КОДЕРА ≈ 37 КБ + файлы ШТАБа.

## 6. Файлы
Создать:
- apps/api/app/participant_lock.py;
- tests/test_participant_lock.py, tests/test_day_test_enter.py, tests/test_day_marks.py, tests/test_projector_day_entered.py.
Изменить:
- app/config.py: day_test_entry_enabled: bool = False;
- app/routers/day.py: POST /day/test-enter, PUT /day/marks; в GET test_entry = флаг и позиция пуста;
- app/projector.py; compose api: DAY_TEST_ENTRY_ENABLED=${DAY_TEST_ENTRY_ENABLED:-false};
- .env.example: «только IRONCLAD, по умолчанию false»;
- app/routers/onboarding.py — только если Ш2 = да.
Итого 10–11 файлов, ≈ 550 строк.

## 7. Контракт
participant_lock.py:
- lock_participant(session, pid): SELECT pg_advisory_xact_lock(hashtext('participant:' || :pid)).
- active_pid_locked(session, tg_user_id) → pid | None: find_active_participant → замок → повторный SELECT tg_user_registry
  (pid, tombstoned_at IS NULL); строки нет → None (ничего не писать).
- Порядок: сначала замок, потом запись. Строк tg_user_registry FOR UPDATE под замком не брать.

Ш2: КОДЕР проверяет, пишет ли first-launch participant_events для УЖЕ существующего pid (reconsent).
Если да — lock_participant до этого INSERT (после FOR UPDATE строки реестра); итог указать в PR.

POST /miniapp/v1/day/test-enter (тела нет):
1. Флаг выключен → 404 NOT_FOUND (до любых запросов к БД).
2. active_pid_locked → None → 404 PARTICIPANT_NOT_FOUND.
3. C0 или C1 не действует → 409 RECONSENT_REQUIRED (проверка — та же, что в onboarding).
4. Строки participant_state нет → 409 DAY_STATE_SYNCING + Retry-After: 1 (проектор ещё не применил first-consent).
5. Позиция есть → 200 {status: already}.
6. Есть ключ day_enter → 202 {status: entering}, без события.
7. Иначе INSERT idempotency_keys (day_enter, ttl '3650 days'),
   затем INSERT participant_events kind day_entered,
   payload {stage_no: 1, module_no: 1, day_no: 1, source: "test_flag"}, actor system (поля — как у first-launch).
8. commit → 202 {status: entering}.
Фаза участника не меняется (В21).

PUT /miniapp/v1/day/marks, тело {block_id: str ^[a-z0-9_]{1,32}$, value: done | not_done}:
- лишние поля игнорируются; X-Client-Op-Id не нужен.
- Проверки: active_pid_locked → None → 404; позиции нет → 409 DAY_NOT_STARTED;
  block_id нет среди блоков текущего дня → 422 BLOCK_NOT_IN_DAY; есть ключ day_done → 409 DAY_ALREADY_SUBMITTED.
- Запись: INSERT day_marks (pid и day_started_at — с сервера, value done = true, at now())
  ON CONFLICT (pid, day_started_at, block_id) DO UPDATE SET value = EXCLUDED.value.
- at не меняется: at = время первой отметки блока, «пришёл» = min(at) (В19).
- commit → 200 {block_id, value}.
- Все 503 — как в iter2-api-1.

## 8. БД и проектор
- Миграций нет.
- В выборку пачки добавить e.at, e.payload; в лог по-прежнему только id и kind.
- PROJECTOR_VERSION → 2. mini_app_first_consent не менять.
- kind day_entered:
  - UPDATE participant_state SET stage_no, module_no, day_no (из payload), day_started_at = e.at,
    missed_streak = 0, updated_at = now(), projector_version WHERE pid = :pid AND day_no IS NULL;
  - 0 строк → WARNING (id, kind), пропуск, checkpoint сдвигается;
  - без ON CONFLICT; status_flags, lifecycle_phase, author_pause_reason в SQL не упоминаются.
- Docstring курсора: «писатели событий существующего pid берут замок participant:pid (participant_lock.py)».

## 9. Тесты
test_participant_lock:
- пока замок держит одна сессия, вторая pg_try_advisory_xact_lock на тот же ключ → false;
- tombstoned после find → None.

test_day_test_enter:
- флаг выкл → 404, событий нет;
- C0 или C1 не действует → 409; нет строки state → 409 + Retry-After;
- первый вызов → 202, одно событие и один ключ; повтор → 202 без нового события;
- после проекции → 200 already; tombstoned → 404, ничего не записано.

test_day_marks:
- запись и переключение: value меняется, at — нет;
- 422 на чужой block_id и на длину 33;
- 409 при ключе day_done; 409 без позиции; tombstoned → 404 без записи.
- «pid и day_started_at из тела игнорируются»: в теле чужой pid и другой day_started_at → строка своего pid
  с day_started_at из state.

test_projector_day_entered:
- Ш3: mini_app_first_consent и day_entered одного pid в одной пачке → позиция записана, day_started_at = at события,
  status_flags = '{}' как после first-consent;
- строка со status_flags = '{block_lives}' → после day_entered те же флаги;
- повторный day_entered при уже заданной позиции → пропуск;
- lifecycle_phase не изменён.

Ш2: если first-launch пишет событие для существующего pid — тест: lock_participant вызван (monkeypatch-счётчик).
tools/check.sh — быстрые; с БД — CI.

## 10. Сервер (после мержа)
- Миграций нет. Пересобрать и перезапустить api и projector ВМЕСТЕ, одной командой (Ш5).
  Иначе старый проектор пропустит day_entered как неизвестный kind.
- Проверки:
  - флаг в контейнере api выключен:
    python -c "from app.config import get_settings; print(get_settings().day_test_entry_enabled)" → False;
  - projector once → «обработано K, пропущено 0»; в логе проектора нет WARNING;
  - число таблиц не изменилось (фильтр table_name <> 'alembic_version').
- Флаг не включать. Включение — отдельное задание ШТАБа после выката.

## 11. Запреты
- AGENT-BRIEF §3. API не пишет participant_state.
- Флаг не включать по умолчанию нигде (compose, .env.example, тесты — только через фикстуру).
- Без миграций и GRANT. Тексты — только заглушки. Жизни не трогать.

## 12. Готовность
- CI 7/7; РЕВЬЮЕР — 0 блокирующих.
- Ш2 выполнен и описан в PR. Живые проверки ✅.

## 13. Оценка
Автор ≈ 1,0 ч (+ РЕВЬЮЕР); кредиты 0.

## 14. РЕВЬЮЕР
Да — замок, флаг (В3), новый kind, initData → pid.

## Проверить ШТАБу до старта КОДЕРА
П1 (блокер): права app_projector — SELECT (at, payload) на participant_events и UPDATE новых колонок participant_state (0006/0007).
Если нет — нужна миграция с GRANT до этой карточки.
