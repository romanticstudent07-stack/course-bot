# Исследование iter2-2: состояние дня и пуши (В1, В4)

Окно ИССЛЕДОВАНИЕ-2, З1, 16.10.2026. Ссылки @2be268c; iter2.md — по ветке docs/tasks-iter2. Карточек нет. Дополняет docs/research/iter2.md.
Сокращения: MO = apps/api/app/db/models.py; PR = apps/api/app/projector.py; DS = docs/architecture/build/db-schema.sql; ET = apps/api/tests/expected_tables.txt; DM = docs/architecture/03-day-mechanics.md; C9 = docs/architecture/09-communications.md; I2B = docs/architecture/normative/I2-wave-b.md (цитаты дал ШТАБ, файл не читал).

## 1. Решения Автора 16.10
«В2 — А (Europe/Moscow временно, поле пояса сразу); В3 — А (флаг только IRONCLAD, по умолчанию выкл., C0/C1 не пропускает, РЕВЬЮЕР); В5 — как предложено; В6 — А; В7 — да; В1 и В4 — после второго окна ИССЛЕДОВАНИЕ»

## 2. Канон состояния (I2B, цитаты ШТАБа)
- participant_state — обычная таблица, пишет только проектор (E1).
- Жизни — participant_state.lives, границы [0, 3]; 0 жизней → sleeping (Р477).
- life_op: pg_advisory_xact_lock(hashtext('life:'||pid)) → SELECT lives … FOR UPDATE → INSERT participant_events kind 'life_op'.
- client_op_id обязателен, TTL 1 ч; таблица idempotency_keys [key, kind, created_at, ttl, result_ref, params_hash_optional]; ключ «life_op:{pid}:{client_op_id}».
Итог: вариант «отдельная таблица жизней» (iter2.md В1-Б) снят.

## 3. Сверка с кодом
| Что | Есть | Факт |
|---|---|---|
| participant_state.lives, позиция дня, пояс | нет | DS: pid, lifecycle_phase, status_flags, author_pause_reason, updated_at, projector_version, last_seen_publish_epoch |
| idempotency_keys | нет | ET: 13 таблиц, такой нет |
| outbox, outbox_dlq | есть с 0001 | DS: outbox (aggregate_id, event_type, payload, created_at, sent_at, tx_id xid8); никто не пишет и не читает |

Проектор (PR): знает один kind mini_app_first_consent; payload не читает; UPSERT ставит status_flags = '{}' при каждом применении — новым kinds нужен свой UPDATE только своих полей, иначе флаги (block_lives и др.) сотрутся. Курсор по pid надёжен при одном писателе событий; в И2 писателей станет 2 и больше (API и «часы»). participant_state в MO не моделируется (xid8).

Находки:
- Н1. Курсор: если каждый INSERT в participant_events берёт pg_advisory_xact_lock(hashtext('life:'||pid)) и держит его до commit, номера событий одного pid идут в порядке commit — курсор остаётся надёжным. first-launch не мешает: его событие у pid первое.
- Н2. По документации PostgreSQL (SELECT, Locking Clause) SELECT … FOR UPDATE требует права UPDATE на таблицу. У app_api его нет и быть не должно (INV-1). Значит, life_op по канону может выполнять только процесс с ролью app_projector. В репо не проверено — ШТАБу сверить по I2B, кто исполнитель life_op.
- Н3. Проектор отстаёт примерно на 1 с: lives может не учитывать ещё не применённое событие. Под lock нужна проверка «проектор догнал pid» (checkpoints.last_event_id ≥ max(id) событий pid), либо life_op выполняется внутри проектора после прохода.
- Н4. Новые колонки participant_state получают права на таблицу автоматически — новых GRANT не нужно. Для новой таблицы idempotency_keys GRANT нужен в той же миграции.

## 4. В1 (остаток): где позиция дня и отметки
Позиция — (этап, модуль, день), начало дня и пропуски подряд. Отметки — «Выполнил / Не выполнил» по блокам до отправки (В6 = А).
- А — всё в participant_state, отметки — jsonb; API пишет только события, проектор переносит. Плюс: одна правда. Минус: каждое нажатие — событие; отметка видна через ~1 с.
- Б — позиция и жизни в participant_state (проектор); отметки — таблица day_marks (pid, день, block_id, value, at), пишет API сразу; первое нажатие дня дополнительно пишет событие day_first_mark (нужно для «пришёл» и «+1 ч», DM 3.4, 3.17). Плюс: мгновенно, черновик отдельно. Минус: миграция 0008; при перевыдаче дня отметки обнулить (DM 3.7).
- В — всё событиями, отметки в отдельной проекции под проектором. Плюс: чистый канон. Минус: сложнее всех.
- Мнение: Б. Галочки без отправки — черновик (DM 3.11), а не состояние участника.
- В любом варианте отчёт = событие day_report_submitted + запись idempotency_keys в одной транзакции; ответ 200 — только после commit (П-31).

## 5. В8: роли канона и наши
| Канон (DS) | Права в каноне | Наша роль |
|---|---|---|
| participant_state_projector | INSERT, UPDATE participant_state | app_projector |
| participant_state_reader | SELECT participant_state | app_api (+ роль «часов/доставки») |
| outbox_writer | INSERT outbox | кто пишет пуш вместе с событием |
| outbox_relay | SELECT, UPDATE outbox | кто отправляет в Telegram |
Не проверено: какие GRANT дала 0006 и создавала ли 0001 роли канона (файлы не читал).
- А — роли канона не создаём, права выдаём прямо app_*, соответствие — комментарием в миграции. Плюс: просто, как сейчас. Минус: имена расходятся с каноном.
- Б — роли канона NOLOGIN, затем GRANT participant_state_reader TO app_api и т.д. Плюс: как в DS. Минус: ещё одна миграция с ролями, РЕВЬЮЕР.
- Мнение: А, запись в DEFECTS (кандидат D-30).

## 6. В4: кто запускает действия по часам
C9 (прочитанная часть):
- Доставкой Б9 не владеет: transport, dedup, retry, dlq — у Б15 (ownership.does_not_own). Конверт в Б15: {text_id, tier, must_deliver, drop_on_overload, coalesce_key, addressee, payload_vars, parse_mode: HTML, no_buttons?}.
- Тексты И2: T2-DEADLINE-LADDER-PLUS1H / -MINUS2H / -MINUS30M (3.17), T2-QUEUE-POSITION (3.19), T2-LIVES-ZERO-PUSH, T1-LIVES-ZERO-SCREEN, T3-NOON-NUDGE, T3-BAD-DAY (раз в 14 дн.), A1-ALL-MISSED. Отдельного id пуша «день открыт в 04:00» нет — кандидат D-31.
- T2 — доставить в пределах TTL; T3 — можно выбросить; не больше одного T3 на участника за 24 ч (Р260).
- Тихих часов нет (NR-203), тумблеров нет (Р123-FINAL, NR-201, NR-215). DM 3.18 называет полуденный пуш «отключаемым» — противоречие (в D-31).
- Форма: только HTML, теги b, i, u, s, code, pre, a, blockquote; 4096 символов, подпись 1024; длинное — «(часть k из N)» (Р253); ошибка разбора → plain-text (Р254); ссылки https, http, tg (Р252); в лестнице «по Вашему времени» (Р257). Лимитов скорости Telegram в прочитанной части нет — это Б15.

Код: планировщика нет; у бота нет DSN и роли БД; projector — цикл раз в 1 с, один экземпляр (advisory lock).
Общая схема для всех вариантов: «часы» решают, что пора → событие + строка outbox одной транзакцией → «доставка» шлёт в Telegram и ставит sent_at, сбой → outbox_dlq.
- А — бот делает и «часы», и доставку (цикл asyncio) + роль app_bot. Плюс: без нового контейнера. Минус: боту нужны DSN и драйвер БД (возможно, новая зависимость); −1 жизнь из бота упирается в Н2.
- Б — новый контейнер worker на образе api (python -m app.worker), роль app_worker, BOT_TOKEN. Плюс: чисто, бот без БД. Минус: память 1920 + 128 = 2048 > 2000 МБ — урезать, например bot 512 → 384; ещё одна роль.
- В — «часы» — шаг в процессе projector (уже есть цикл, один экземпляр, право UPDATE для жизней); доставка — в боте с узкой ролью app_bot (SELECT/UPDATE outbox, SELECT tg_user_registry). Плюс: без нового контейнера, жизни у единственного писателя. Минус: проектор делает больше, чем проекцию; боту нужен DSN.
- Г — APScheduler или Celery (DM 3.19). Минус: новая зависимость, Celery нужен ещё и брокер.
- Мнение: В. Если бот должен остаться совсем без БД — Б с урезкой памяти.

## 7. Надо дочитать (решает ШТАБ)
- C9 обрезан в разделе «YAML-патч», added_rules, R258 (на examples_discouraged). Остаток R258 и всё ниже не прочитаны. Нужны строки от «R258» до конца.
- Шапка C9 ссылается на ERRATA-UNIFIED и I4: носитель текстов — text_registry, render() разделён на три функции по аудитории. Нужны выдержки: из I4 — три функции render и ключи текстов дня и лестницы; из ERRATA — только text_catalog_b9 против text_registry.
- I2B — исполнитель и роль life_op (Н2); kinds событий дня, если есть.
- Блок 15: retry, TTL T2, лимиты Telegram (файл назовёт ШТАБ).
- Миграция 0006 (и 0001, если там CREATE ROLE) — для В8 и GRANT на outbox.
- apps/bot/requirements.txt — есть ли драйвер БД (В4 А и В).

## 8. Разрезка (заменяет iter2.md §5 начиная с пачки 1)
| # | Пачка | Область | Что | Зависит |
|---|---|---|---|---|
| 1 | iter2-docs | docs Р0 | D-25…D-29 + кандидаты D-30, D-31 (номера сверит ШТАБ) | — |
| 2 | iter2-db-1 | API | 0007 от 0006_app_roles: ALTER participant_state (lives smallint DEFAULT 3 CHECK 0–3, позиция, пропуски, tz DEFAULT 'Europe/Moscow') + idempotency_keys + GRANT + ET; РЕВЬЮЕР | В1, В8 |
| 3 | iter2-db-2 | API | 0008 от 0007: day_marks (если В1 = Б) + GRANT + ET | мерж 2 |
| 4 | iter2-db-3 | API | 0009 от 0008: роль app_bot или app_worker (по В4), GRANT outbox; РЕВЬЮЕР | мерж 3, В4 |
| 5 | iter2-api-1 | API | заглушка контента дня + GET day/current + флаг входа (В3, РЕВЬЮЕР) | 2 |
| 6 | iter2-api-2 | API | отметки + POST day/report/submit (П-31, idempotency_keys, lock на pid) + kinds в проекторе | 3, 5 |
| 7 | iter2-api-3 | API | «часы»: 04:00, полночь, −1 жизнь, лестница → outbox | 4, 6 |
| 8 | iter2-miniapp-1 | Mini App | /day, отметки, отправка без ложного успеха, жизни | 5, 6 |
| 9 | iter2-send-1 | bot или worker | outbox → Telegram (HTML, части, plain-fallback, DLQ) | 7 |
Миграции строго по одной; новая таблица — GRANT ролям и ET в том же PR. Если В1 = А, пачки 3 нет и 0009 становится 0008.

## 9. Вопросы Автору
В1 (§4), В4 (§6), В8 (§5). Мнения: В1 — Б, В4 — В, В8 — А.

## 10. Для ШТАБА (строки STATE)
- «Очередь 0: И2 — research iter2-2 (PR #93, без мержа); ждём В1, В4, В8 и выдержки §7.»
- «Решения Автора 16.10: В2 А, В3 А, В5, В6 А, В7 да (дословно — docs/research/iter2-2.md §1).»

## 11. Прочитано (КБ, главный факт)
- docs/process/DESIGNER.md 15,4 — ИССЛЕДОВАНИЕ до 150 КБ, PR без мержа.
- docs/STATE.md 25,8 — 0006, 13 таблиц, память 1920/2000.
- AGENT-BRIEF.md 15,0 — роли app_api / app_projector; API не пишет participant_state.
- docs/process/README.md 8,7 — миграции не параллелить, ET в том же PR.
- docs/research/iter2.md (ветка) 16,8 — В1–В7, разрезка.
- C9 38,2 (около 90 %) — доставка у Б15, тихих часов нет, HTML/4096.
- MO 8,8 — participant_state не моделируется.
- PR 11,3 — один kind, status_flags = '{}', курсор при одном писателе.
- DS 8,9 — нет lives; роли канона и outbox.
- DM 26,2 (взят целиком, нужны 3.17–3.19) — лестница, очередь 10–60 мин.
- Сверх списка: docs/process/CODER.md — команды Codespaces; ET 0,6 — нет idempotency_keys.
