# iter2-api-1 — контент дня (заглушка) + GET /miniapp/v1/day/current

## 1. Паспорт
- id: iter2-api-1. PR: «iter2-api-1: контент дня (заглушка) + GET day/current». Ветка: feat/iter2-api-1.
- Режим: Р0+. Зависит от: мерж PR docs/tasks-iter2-api (исследование + карточки). Миграций нет.

## 2. Цель
Mini App видит текущий день: позицию, блоки с отметками, жизни и статус. Это только чтение, без записи в БД.
Контент дня — JSON-заглушка с JSON Schema; при битом контенте api не стартует.
Здесь же общий модуль ключей idempotency_keys (нужен GET для статусов entering и submitted).

## 3. Решения Автора (дословно)
- «В2 — А (Europe/Moscow временно, поле пояса сразу)»; «В7 — да» (справка — только текст).
- «В17 — А» — названия блоков — ключи text_registry + заглушки.
- «В22 — А (ключ day_done в idempotency_keys; проверки «догнал» нет; риск — в api-3)».
- Источник контракта — docs/research/iter2-api.md §3, §6 (CT read-only; DOCS PR — после карточек, Ш6).

## 4. Выдержки архитектуры
- 03-day-mechanics.md §3.2: «Пока текущий день не сдан, Участнику виден только экран текущего дня.»
- §3.3: «В дне 4–5 блоков заданий. Под каждым блоком — 2 кнопки: «✅ Выполнил» / «⬜ Не выполнил» (состояние переключаемо до отправки отчёта). Кнопка «Отправить отчёт» активируется только после того, как все задания отмечены.»
- §3.5 (по research §2): гейтинг — все критические (⭐) + N желательных.
- errata E1 (projector.py, docstring): «participant_state — обычная таблица, наполняемая проектором; API туда не пишет никогда (INV-1).»
- Тексты курса — только заглушки до 0-Б (репо публичный).

## 5. ЧТО ПРОЧИТАТЬ (КОДЕР)
AGENT-BRIEF.md 15,0; apps/api/app/db/models.py 8,8; apps/api/main.py 3,4; apps/api/app/participants.py 4,8;
apps/api/app/routers/consents.py 6,1 (образец: pid из initData, 503); файл заглушек текстов для python -m app.texts load (путь и КБ — ШТАБ);
образец теста с БД — tests/test_consents*.py (КБ — ШТАБ). Чтение КОДЕРА ≈ 38 КБ + файлы ШТАБа.

## 6. Файлы
Создать:
- apps/api/content/day.schema.json — JSON Schema (draft 2020-12).
- apps/api/content/module_1/day_01.json, day_02.json — заглушки (.gitkeep удалить).
- apps/api/app/day_content.py — загрузка и проверка контента, поиск дня по (stage_no, module_no, day_no).
- apps/api/app/day_keys.py — ключи idempotency_keys и {dsa}.
- apps/api/app/routers/day.py — GET /day/current.
- apps/api/tests/test_day_content.py, apps/api/tests/test_day_current.py (в нём же тесты day_keys).
Изменить:
- apps/api/app/db/models.py — DayMark, IdempotencyKey.
- apps/api/main.py — day.router в build_miniapp_v1_router; load_day_content() в create_app.
- файл заглушек текстов — ключи title и help для блоков.
Итого 11 файлов, ≈ 450 строк.

## 7. Контракт
Контент (схема, additionalProperties: false):
- {stage_no ≥1, module_no ≥1, day_no ≥1, min_optional ≥0, blocks: 4..5 × {block_id ^[a-z0-9_]{1,32}$, critical: bool, title_key, help_key}}.
- Сверх схемы, в коде: block_id уникальны; ≥1 critical; min_optional ≤ числа некритических; day_no совпадает с именем файла.
- Ошибка → исключение при старте (api не стартует), в лог — путь файла и причина.

day_keys.py:
- dsa(ts) = ts.astimezone(timezone.utc).isoformat() (Ш4); naive datetime → ValueError.
- key_day_enter(pid) = «day_enter:{pid}»; key_day_done(pid, ts) = «day_done:{pid}:{dsa}»;
  key_day_report(pid, op_id) = «day_report:{pid}:{op_id}».
- Константы kind: day_enter, day_done, day_report. TTL: '3650 days', '3650 days', '1 hour'.
- Срок ttl в логике не проверяется (UPDATE и DELETE ни у кого нет: строка есть → ключ есть).

GET /miniapp/v1/day/current (initData и rate-limit — через miniapp_v1):
- pid только через find_active_participant (tg_user_id из initData); нет активного pid → 404 PARTICIPANT_NOT_FOUND.
- participant_state читается text-SQL SELECT (lives, stage_no, module_no, day_no, day_started_at). Это не запись: test_projector_static не нарушается.
- 200 {status, lives, test_entry, position?, day_started_at?, blocks?, min_optional?, can_submit?}:
  - нет строки state → status not_started, lives 3 (DEFAULT колонки);
  - day_no NULL → entering, если есть ключ day_enter, иначе not_started;
  - позиция есть → open или submitted (есть ключ day_done по текущему day_started_at);
  - blocks — [{block_id, title_key, help_key, critical, mark: done | not_done | null}];
  - отметки — из day_marks только по pid и текущему day_started_at (true → done);
  - can_submit = все блоки отмечены и статус open;
  - test_entry в этой задаче всегда false (флаг — iter2-api-2a).
- Позиция есть, а контента дня нет → 503 DAY_CONTENT_MISSING, в лог ERROR (stage, module, day; без pid).
- БД недоступна → 503 SERVICE_UNAVAILABLE (как consents.py).
- Лог INFO: tg_user_id и status.

## 8. БД
Миграций нет. Модели повторяют живую схему 0007/0008:
- DayMark: pid uuid, day_started_at timestamptz, block_id text, value boolean, at timestamptz; PK (pid, day_started_at, block_id).
- IdempotencyKey: key text PK, kind text, created_at timestamptz, ttl interval, result_ref text NULL, params_hash text NULL.
- Типы, FK и server_default сверить по tests/test_db_models.py (CI). expected_tables.txt не меняется.

## 9. Тесты
- test_day_content:
  - заглушки валидны;
  - по одному отказу на каждое правило (схема, уникальность, critical, min_optional, имя файла);
  - каждый title_key и help_key есть в файле заглушек текстов.
- test_day_current:
  - 401 без initData; 404 без участника и для tombstoned;
  - not_started (нет строки state; day_no NULL); entering (есть ключ day_enter);
  - open с отметками; submitted (ключ day_done);
  - отметки другого day_started_at не видны; can_submit; 503 при отсутствии контента дня.
- Ш4: ключ day_done из day_started_at, прочитанного из БД, равен ключу из Python-datetime с тем же моментом
  в другом поясе (+03:00); naive → ValueError.
- Строки state и ключи тест вставляет владельцем БД (фикстура).
- tools/check.sh — быстрые (без БД); тесты с БД и test_db_models — только CI.

## 10. Сервер (после мержа)
- Миграций нет, бэкап не нужен. Пересобрать и перезапустить api (по SERVER.md).
- Проверки:
  - /healthz 200; GET /miniapp/v1/day/current без initData → 401;
  - в логе api нет ошибок контента;
  - в контейнере api: python -c "from app.day_content import load_day_content; load_day_content()" без ошибок;
  - число таблиц то же, что до выката (SQL с фильтром table_name <> 'alembic_version').

## 11. Запреты
- AGENT-BRIEF §3. Не писать в participant_state, participant_events, day_marks, idempotency_keys.
- Реальные тексты курса не писать — только «Заглушка …».
- Не принимать pid или день из запроса. Не трогать projector.py, миграции, docs/architecture/**.

## 12. Готовность
- CI 7/7.
- Контент валиден, битый контент роняет старт.
- GET отдаёт все 4 статуса.
- Живые проверки ✅.

## 13. Оценка
Автор ≈ 0,7 ч; кредиты 0.

## 14. РЕВЬЮЕР
Нет (только чтение; initData — существующий механизм; Ш7).

## Проверить ШТАБу до старта КОДЕРА
- П2: попадает ли apps/api/content в Docker-образ api (Dockerfile).
- П3: путь и размер файла заглушек текстов; шаблон ключа (CHECK 0003).
