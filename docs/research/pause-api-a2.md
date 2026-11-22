# pause-api-a2 — З1 (окно ПРОДОЛЖЕНИЕ)

Срез 4ea7fd7940953fb95c15fdc5e6567b0ff1b54759 (@4ea7fd7). Прошлое окно: docs/research/pause-api-a.md@ad1f52b. Сокращения: A=apps/api; M=A/migrations/versions; N=docs/architecture/normative; B=docs/architecture/build; T=A/tests. Закрыты п.1–2 «Надо дочитать» pause-api-a.md; п.3–4 остаются за ШТАБом. Q1–Q3 из R-2026-11-21.md не переоткрываются; номер миграции не назначается; пункт 5 #272 (IndexedDB) не делается.

## 1. Канал аудита client_op_id_conflict — звенья

Канон: [N/I4-wave-d.md §mini_app_client.R339_indexeddb_cache.conflict_ux@4ea7fd7, строки 599–604] «log: security_audit event client_op_id_conflict»; [N/I2-wave-b.md §idempotency_keys.behavior_on_collision@4ea7fd7, строки 492–494] «conflicting_params: return 409 + log conflict event». [Автор, канон проверен И4 §AD-01; N/OVERRIDES.yaml §AD-01@4ea7fd7, строки 146–167] аудит — только доказанная коллизия op-id; бизнес-409 — сообщение и перечитывание, без аудита. Совпадения в И3: [N/I3-wave-c.md@4ea7fd7, строки 67 и 790] security_audit упомянут только для фото-конвейера (EXIF, утечка метаданных); client_op_id_conflict в И3 нет.

| Звено | Исход |
|---|---|
| Событие/триггер | Закрыто каноном: доказанная коллизия — один op-id с несовпадающими параметрами [И4 §conflict_ux@4ea7fd7; OVERRIDES §AD-01]. |
| Producer в коде | Блокер: [по коду: grep apps/ — 0 совпадений client_op_id_conflict и security_audit] писателей нет; A/app/routers/pause.py событие не пишет. |
| Канон приёмника | Блокер: [канон молчит] N/errata-unified.md — 0 совпадений по «security_audit»/«conflict»; B/db-schema.sql@4ea7fd7 (строки 114–127, Блок 15) — только privacy_audit_log, назначение «152-ФЗ, каждый доступ к ПДн», GRANT SELECT → audit_reader, INV-2 append-only; связь с коллизиями op-id не установлена. B/miniapp-api-contract.yaml@4ea7fd7 (строки 247, 280, 326) — только 409 IDEMPOTENCY_CONFLICT, канала аудита нет. |
| Транспорт | Блокер: [по коду: A/app/routers/security.py@4ea7fd7, целиком, 872 Б] единственный security-роут — POST /security/csp-report (E2 ERRATA), пишет logger.warning("csp"), без initData; транспорта security_audit-событий нет. |
| Права записи | Блокер: [по коду: M/0001@4ea7fd7 строка 153] app_api INSERT privacy_audit_log не выдан (таблица §2); иных кандидатов в GRANT миграций нет. |
| Транзакция | Блокер (перенос из pause-api-a.md §1): _released/_run откатывают транзакцию на HTTPException — INSERT аудита в той же транзакции перед 409 теряется; запись обязана идти вне откатываемой транзакции. |
| Проверка | Блокер: [по коду: T/test_pause_api_db.py@ad1f52b] test_log_has_no_pid_or_op проверяет app.pause, не доставку и сохранение события. |

Итог: событие задано каноном, но producer, приёмник, транспорт, права и тест отсутствуют — сквозной канал не существует.

**К-4 №1 — носитель события client_op_id_conflict.** Канон: проверено И2 §idempotency_keys.behavior_on_collision — «conflicting_params: return 409 + log conflict event»; И4 §R339.conflict_ux — «log: security_audit event client_op_id_conflict»; OVERRIDES §AD-01 — «один HTTP-статус 409 не включает очистку и аудит client_op_id_conflict»; И3 строки 67, 790 — security_audit только для фото-событий; errata-unified.md, db-schema.sql, miniapp-api-contract.yaml — молчат о носителе: security_audit как таблица или транспорт в каноне не определён. Варианты:
- A. privacy_audit_log как приёмник. Плюсы: таблица есть (db-schema Блок 15), append-only (INV-2), ролевой тест есть. Минусы: назначение — «каждый доступ к ПДн» (152-ФЗ), коллизия op-id не является доступом к ПДн; нужен INSERT app_api и смена смысла таблицы; откат транзакции требует отдельной транзакции в любом случае.
- B. Структурированный серверный лог (logging вне БД, запись после отката). Плюсы: нет DDL и прав, не теряется при откате, простая проверка в тесте. Минусы: нет проверяемой фиксации и срока хранения, транспорт сейчас basicConfig, выборка только вручную.
- C. Долговечная запись в новой таблице security_events (запись в отдельной транзакции после отката основной). Плюсы: проверяемая фиксация, переживает откат, права по правилу 0006. Минусы: новый DDL (номер не назначать), строка в expected_tables.txt, ролевые тесты.
Рекомендация: C [ШТАБ-предложение, К-4]. Вариант A проверен первым (предпочтение прошлого окна) и отклонён по назначению таблицы и правам; B не даёт фиксации, которую требует слово «аудит». При любом варианте: писать вне транзакции _released/_run; секреты, initData и ПДн не логировать [AGENT-BRIEF §3, из pause-api-a.md].

## 2. Права app_api (сумма 0001–0021), DDL idempotency_keys, GC

Генератор ACL: общего хелпера нет; в каждой миграции — константа PRIVILEGES: tuple[(право, объект, роль), …] и цикл for privilege, target, role in PRIVILEGES: op.execute(f"GRANT {privilege} ON {target} TO {role}"); downgrade — REVOKE в обратном порядке. В 0006 дополнительно цикл членств GRANT granted TO member. [по коду: M/0006@4ea7fd7 строки 93–95, M/0007:125, M/0008:69, M/0010:151, M/0011:121, M/0014, M/0017, M/0018]

| Таблица | Права app_api | Миграция |
|---|---|---|
| tg_user_registry | SELECT, INSERT; UPDATE (created_via) | 0006 |
| text_registry | SELECT | 0006 |
| consent_events | SELECT, INSERT; USAGE consent_events_id_seq | 0006 |
| participant_events | INSERT; SELECT (id); USAGE consent_events_id_seq, participant_events_id_seq | 0006 |
| participant_state | чтение через членство app_api = participant_state_reader; GRANT 0001 выдан на всю таблицу | 0006 |
| idempotency_keys | SELECT, INSERT (вся таблица); UPDATE, DELETE, TRUNCATE не выданы никому | 0007 |
| day_marks | SELECT, INSERT; UPDATE (value, at) | 0008 |
| access_grants | SELECT (tg_user_id, status) | 0010 |
| reflections_log | INSERT (pid, stage_no, module_no, day_no, day_started_at, body); SELECT (id, pid, stage_no, module_no, day_no, day_started_at, body, created_at); USAGE reflections_log_id_seq | 0011 |
| outbox | INSERT (aggregate_id, event_type, payload, tx_id); USAGE outbox_id_seq; SELECT не выдан (RETURNING запрещён) | 0012 |
| measurements_log | INSERT (pid, kind, occasion, stage_no, checkup_answers, checkup_score, checkup_zone, checkup_config_version, weight_kg, client_op_id); SELECT (id, pid, kind, occasion, stage_no, checkup_answers, checkup_score, checkup_zone, checkup_config_version, weight_kg, client_op_id, created_at); USAGE measurements_log_id_seq | 0014 |
| onboarding_form | INSERT (pid, gender, wellbeing_code); SELECT (pid, gender, wellbeing_code, created_at) | 0015 |
| support_questions | INSERT (pid, topic_code, body, client_op_id); SELECT (id, pid, client_op_id, created_at); USAGE support_questions_id_seq | 0017 |
| participant_pauses | INSERT (pid, kind, status, start_at, planned_end_at, client_op_id); SELECT (id, pid, kind, status, start_at, planned_end_at, ended_at, stage_no, restart_no, client_op_id, created_at); USAGE participant_pauses_id_seq | 0018 |
| pause_budgets | SELECT (pid, days_budget_remaining_annual, cycle_start_at, restart_no) | 0018 |

Без прав app_api: 0009, 0013, 0020, 0021 — только app_bot; 0019 — app_bot + app_projector; 0016 не существует (номер пропущен). privacy_audit_log: app_api прав нет — только GRANT SELECT audit_reader [M/0001@4ea7fd7:153]. [по коду: M/0006, 0009, 0013, 0019, 0020, 0021]

DDL idempotency_keys [канон И2 §idempotency_keys; по коду: M/2026_10_16_1200-0007_day_state_day_state.py@4ea7fd7, upgrade()]: key text PRIMARY KEY; kind text NOT NULL; created_at timestamptz NOT NULL DEFAULT now(); ttl interval NOT NULL DEFAULT interval '1 hour'; result_ref text NULL; params_hash text NULL (= params_hash_optional канона); CHECK ck_idempotency_keys_key_not_empty (key <> ''); CHECK ck_idempotency_keys_ttl_positive (ttl > interval '0'); INDEX idempotency_keys_created_at_idx (created_at); FK нет. Модель совпадает: [по коду: A/app/db/models.py@4ea7fd7:327–345] класс IdempotencyKey, те же колонки, CHECK и индекс.

GC: [канон И2 §idempotency_keys.gc@4ea7fd7] frequency hourly, action DELETE WHERE created_at + ttl < now() AND kind != erasure. По коду GC нет: DELETE FROM idempotency_keys в apps/ встречается только в ролевом тесте T/test_db_roles_0007.py@4ea7fd7:63,72 (проверка отказа DELETE); scheduler/cron/celery в apps/api не найдены; docstring M/0007: «очистка по ttl — отдельная задача позже». [ШТАБ-тех]

## Прочитано (это окно, @4ea7fd7; R/ — по ad1f52b)

Целиком: P/PACK.md 12747 — метка конца есть; D/DECISIONS.md 7809 — приоритет решений; P/DESIGNER.md 21971 — бюджет и правило Т; P/CANON-CHECK.md 4856 — К-4/К-6; R/pause-api-a.md 14271 — исходные звенья и «Надо дочитать».
Выборки (sed по строкам): N/I2-wave-b.md 40437, строки 460–560 — behavior_on_collision, gc, stable_key_recipes; N/I4-wave-d.md 60986, строки 28–40 и 585–615 — врезки AD-01/02 и §R339.conflict_ux; N/OVERRIDES.yaml 12618, строки 140–200 — §AD-01 canonical, §AD-02; N/I3-wave-c.md 71196, строки 67, 790 — security_audit фото-события; N/errata-unified.md 53969, строки 18–96 — заголовки блоков; аудита коллизий нет; B/db-schema.sql 8851, строки 23, 82–131 — privacy_audit_log и роли; B/miniapp-api-contract.yaml 27908, строки 90, 247, 280, 326 — 409; A/app/routers/security.py 872 — только CSP-report.
Код (grep, затем sed): M/0001:153; M/0006:50–95; M/0007:20–130; M/0008:60–69; M/0010:59–81; M/0011:51–65; M/0012:37–42; M/0014:121–139; M/0015:44–58; M/0017:49–72; M/0018:140–165; M/0019:26–46; M/0020:18–55; M/0021:23–69; A/app/db/models.py:327–345; T/test_db_roles_0007.py:63,72; A/app/routers/pause.py:120. Итог: целиком ≈ 61654 Б + выборки ≈ 31000 Б — в лимите 200000 Б. Полный журнал grep — в ответе окна, в файл не входит. Репозиторий не менялся, проверки не запускались.

КОНЕЦ pause-api-a2.md
