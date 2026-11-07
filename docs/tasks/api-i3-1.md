# api-i3-1 — Чек-Ап (api): конфиг-файл, GET config, POST submit

## 1. Паспорт
- id: api-i3-1 · ветка: api/i3-1-checkup · режим: Р1 (Агент; промпт пишет ШТАБ по карточке) · PLAN §5 п.9 · РЕВЬЮЕР: нет (раздел 14).
- Заголовок PR: «api: Чек-Ап — конфиг-файл, GET /checkup/config, POST /checkup/submit (api-i3-1)».
- Зависит от: db-i3-2 (0014_measurements_log в main; на сервере пока нет — тесты с БД гоняет CI). До промпта Агенту — PR DOCS с правками раздела «Канон и решения» (в) и sync.
- Дальше: miniapp-1 (экран onb.checkup) — после этой задачи и api-2.

## 2. Цель
Сервер отдаёт конфиг Чек-Апа из файла в репо (15 утверждений, шкала 0–3, 3 зоны, дисклеймер; без границ зон) и принимает 15 ответов: сам считает балл и зону, пишет строку в measurements_log с версией конфига, участнику отдаёт только зону. Повтор с тем же X-Client-Op-Id — тот же 200 без новой строки. Все тексты — заглушки (репо публичный).

## 3. Решения (метки К-6)
- Р-7 [Автор, DECISIONS; по выдержке ШТАБа]: связь балл↔зона — только в конфиге, не в БД; API считает балл и зону сам по 15 ответам; границы 0–9 / 10–22 / 23–45 включительно.
- Л2 [ШТАБ-тех, К-5; канон I3 §C.7 — порядок, правка №12]: до Панели (И6) конфиг — файл в репо с версией, версия пишется в результат; участнику только зона, балл не показываем.
- Только onboarding [ШТАБ, К-5; канон I3 §C.7 — опрос этапа по событию stage_completed, 05 fail-safe — не доверяем клиенту]: occasion = Literal["onboarding"]; stage_end → 422 VALIDATION_ERROR. stage_end включается отдельной задачей вместе с этапами.
- Согласия [ШТАБ, К-5; образец day.py test-enter, шаг 3; канон: отдельного согласия на ответы Чек-Апа нет — (а)]: перед записью C0 и C1 должны действовать, иначе 409 RECONSENT_REQUIRED.
- Только measurements_log [ШТАБ, К-5]: participant_events, outbox, проектор, checkup.scored — не здесь.
- Гейт Legal [К-6 тех; I3 §C.3, §C.7, §C.12]: в GET config проверки нет — см. «Канон и решения» (б).
- Зона фиксируется при записи [канон I3 §C.7]: повтор отдаёт сохранённые зону и версию, не пересчитывает.
- [К-6 тех] Конфиг — JSON (стандартная библиотека, новых зависимостей нет). Путь — константа модуля CHECKUP_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "checkup" / "checkup.v1.json" (в образе /app/config/checkup/checkup.v1.json; .dockerignore .json не исключает — проверил ШТАБ).
- [К-6 тех] Границы зон (min, max) и legal_status клиенту не отдаются: участнику только зона (I3 §C.7), лишнего не отдаём.
- [К-6 тех] Ответ submit — {zone, config_version, created_at}; название и текст зоны клиент берёт из GET config по id зоны.
- [К-6 тех] Каждый текст конфига начинается с «Заглушка» — это проверяет тест. Тексты зон и дисклеймер переедут в text_registry в И4 (I3 §C.12).
- [К-6 тех] Новый X-Client-Op-Id — новая строка (04 §4.8 «старая неприкосновенна»). idempotency_keys не используются: повтор гасит UNIQUE (pid, client_op_id).

## 4. Выдержки архитектуры (Агент архитектуру не читает)
- 05 §5.1: «15 утверждений, шкала 0–3, максимум 45 баллов. Проводится: на старте (Шаг 4.5 онбординга) + после каждого Этапа.»
- 05 §5.2: «Перед вопросами каждого блока — заголовок блока (Блок 1 ЖКТ / Блок 2 Энергия / Блок 3 Когнитивные / Блок 4 Тело). После 15-го вопроса — серверный подсчёт суммы».
- 05 §5.3: «🟢 0–9 — Зелёная», «🟡 10–22 — Жёлтая», «🔴 23–45 — Красная»; «границы включительные, жёстко в конфиге»; «Тексты расшифровок — в конфиге. Обязательный тест на граничные значения (9, 10, 22, 23).»
- 05 §5.5: «Храним все 15 ответов (не только сумму/зону) + балл + зона + дата.»
- 05 fail-safe: «Только кнопки 0–3 (никакого ручного ввода баллов)»; «Идемпотентность кнопок. Серверный пересчёт суммы из сохранённых ответов (не доверяем клиенту).»
- I3 §C.7: «Участник видит только зону, не сырой балл (R306/R307), а зона в событии фиксируется на момент вычисления и позже не переинтерпретируется.» «Зон три».
- 04 §4.8: «добавочная запись в журнал замеров, старая неприкосновенна».
- contract.yaml: GET /miniapp/v1/checkup/config — «Проходит гейт Legal (И3)»; POST /miniapp/v1/checkup/submit — заголовок X-Client-Op-Id, required, uuid.
- db-i3-2 §7: «INSERT … ON CONFLICT (pid, client_op_id) DO NOTHING RETURNING id»; «Повтор (RETURNING дал 0 строк): SELECT … WHERE pid = :pid AND client_op_id = :op → тот же 200».
- db-i3-2 §8 (CHECK): occasion onboarding ⇔ stage_no NULL; checkup_answers — smallint[], ровно 15, каждый 0–3; checkup_score = сумма 15 ответов; checkup_zone ∈ green / yellow / red; checkup_config_version — 1–64 символа после btrim; client_op_id — 1–64 символа.

## 5. ЧТО ПРОЧИТАТЬ (Агент)
- AGENT-BRIEF.md — 17,1; эта карточка ≈ 13.
- apps/api/main.py — 4,1 (build_miniapp_v1_router, проверка контента при старте — образец для конфига).
- apps/api/app/routers/consents.py — 6,1 (образец небольшого роутера с initData и 503).
- apps/api/app/consent_status.py — 5,4 (current_texts, load_events, reasons, STATUS_KINDS, ConsentTextMissingError).
- apps/api/app/participant_lock.py — 2,6 (active_pid_locked); apps/api/app/participants.py — 4,8.
- apps/api/app/routers/day.py — ТОЛЬКО enter_day_by_test_flag и обработчики ошибок (_participant_not_found, 503, RECONSENT_REQUIRED, IDEMPOTENCY_CONFLICT), разбор X-Client-Op-Id из report/submit; целиком не читать.
- apps/api/app/errors.py — 3,3; apps/api/app/db/models.py — только класс MeasurementsLog и константы (CHECKUP_ZONES и соседние).
- apps/api/tests/conftest.py — 8,1 (api_client, valid_init_data, фикстуры БД). Чтение Агента ≈ 75 КБ.

## 6. Файлы
- Создать: apps/api/config/checkup/checkup.v1.json; apps/api/app/checkup_config.py; apps/api/app/routers/checkup.py; apps/api/tests/test_checkup_config.py (без БД); apps/api/tests/test_checkup_submit_db.py (с БД, CI).
- Изменить: apps/api/main.py — импорт checkup, checkup.router в build_miniapp_v1_router, строки GET /miniapp/v1/checkup/config и POST /miniapp/v1/checkup/submit в докстринге «Маршруты», вызов get_checkup_config() в create_app (битый конфиг → api не стартует, как с контентом дня).
- Не трогать: миграции, models.py, expected_tables.txt, day_keys.py, ci.yml, text_registry.

## 7. Контракт
Конфиг-файл (поля): version (строка); scale {min: 0, max: 3}; blocks [{id 1–4, title}]; questions [{id "q01"…"q15", block, text}]; zones [{id, min, max, title, text, legal_status}] в порядке green, yellow, red, у всех legal_status "pre-legal-review"; disclaimer. Значения: version "v1-stub"; зоны 0–9, 10–22, 23–45; все title, text и disclaimer начинаются с «Заглушка».
Загрузчик app/checkup_config.py: load_checkup_config(path) → неизменяемый объект; get_checkup_config() — functools.lru_cache без аргументов, путь читает из CHECKUP_CONFIG_PATH в момент вызова (не аргументом по умолчанию); score_and_zone(answers, cfg) → (score, zone_id), чистая функция. CheckupConfigError, если: файла нет или он не JSON; version пустая после strip или длиннее 64; scale не {0, 3}; блоков не 4 или id повторяются; вопросов не 15, id повторяются или block не из blocks; зон не 3 или id не green, yellow, red по порядку; первая min ≠ 0, дырка или перекрытие (min следующей ≠ max предыдущей + 1), min > max, последняя max ≠ 45; title, text или disclaimer пустые; legal_status не approved / pre-legal-review.
GET /miniapp/v1/checkup/config (initData — роутер miniapp_v1; БД не нужна, участник не обязателен; гейта Legal нет — (б)):
- 200 {version, scale {min, max}, blocks [{id, title}], questions [{id, block, text}], zones [{id, title, text}], disclaimer}. В zones нет min, max, legal_status.
- 401 — роутер; 429 — rate-limit.
POST /miniapp/v1/checkup/submit. Заголовок X-Client-Op-Id — UUID v4, обязателен: нет, не UUID или не v4 → 422 VALIDATION_ERROR (как report/submit). Тело {occasion: "onboarding", answers: 15 целых 0–3}. Проверка — StrictInt: true/false и "1" не проходят. Лишние поля (score, zone, stage_no) игнорируются. Иначе → 422 VALIDATION_ERROR.
Одна транзакция, порядок:
1) active_pid_locked(session, tg_user_id): None → rollback, 404 PARTICIPANT_NOT_FOUND «Участник не найден. Пройдите онбординг.»;
2) texts = current_texts(session, STATUS_KINDS): ConsentTextMissingError → rollback, 503 SERVICE_MISCONFIGURED (message — тот же, что у day.py в этом случае); reasons(load_events(session, pid), texts) не пусто → rollback, 409 RECONSENT_REQUIRED «Нужно заново подтвердить согласия.»;
3) score, zone = score_and_zone(answers, cfg); версия = cfg.version;
4) INSERT INTO measurements_log (pid, kind, occasion, stage_no, checkup_answers, checkup_score, checkup_zone, checkup_config_version, client_op_id) VALUES (:pid, 'checkup', 'onboarding', NULL, CAST(:answers AS smallint[]), :score, :zone, :ver, :op) ON CONFLICT (pid, client_op_id) DO NOTHING RETURNING checkup_zone, checkup_config_version, created_at; :op = str(uuid);
5) 0 строк → SELECT kind, checkup_zone, checkup_config_version, created_at FROM measurements_log WHERE pid = :pid AND client_op_id = :op. Если kind ≠ 'checkup' (op_id занят весом из api-2) → rollback, 409 IDEMPOTENCY_CONFLICT (message — как в day.py). Иначе — сохранённые значения: ответы повтора не пересчитываются;
6) commit → 200 {zone, config_version, created_at}. Балла в ответе нет никогда. Ответ строится только после успешного commit.
SQLAlchemyError (и на commit) → rollback, 503 SERVICE_UNAVAILABLE «Сервис временно недоступен. Попробуйте позже.»; в лог только имя класса.
Лог (logger app.checkup): INFO только tg_user_id и status (created / repeat). pid, op_id, ответов, балла и зоны в логе нет: это данные о здоровье.

## 8. БД
Миграций нет. Таблица, CHECK и права app_api (INSERT, SELECT, USAGE на sequence) — 0014 (db-i3-2 §7–§8). RETURNING checkup_zone, checkup_config_version, created_at покрыт SELECT app_api.

## 9. Тесты
Изоляция кеша: в обоих файлах autouse-фикстура вызывает get_checkup_config.cache_clear() до и после каждого теста. Подмена пути — monkeypatch.setattr(app.checkup_config, "CHECKUP_CONFIG_PATH", tmp_path / "bad.json"), затем cache_clear.
test_checkup_config.py (без БД; tools/check.sh):
- настоящий файл грузится: 15 вопросов, 4 блока, 3 зоны, version непустая; все тексты начинаются с «Заглушка»;
- score_and_zone: 0 и 9 → green, 10 и 22 → yellow, 23 и 45 → red (наборы: [3,3,3]+[0]*12 = 9; [3,3,3,1]+[0]*11 = 10; [3]*7+[1]+[0]*7 = 22; [3]*7+[2]+[0]*7 = 23); балл = сумма;
- битый конфиг (tmp_path, load_checkup_config) → CheckupConfigError, по тесту на случай: дырка (yellow min 11), перекрытие (yellow min 9), первая min 1, последняя max 44, 14 и 16 вопросов, повтор id вопроса, block 5, scale max 4, version нет / пустая / 65 символов, зоны не green-yellow-red, пустой disclaimer, legal_status "draft", не JSON;
- create_app() при CHECKUP_CONFIG_PATH на битый файл (подмена выше) → CheckupConfigError, api не стартует;
- GET config с valid_init_data → 200; в zones нет ключей min, max, legal_status; нигде нет ключа score;
- POST submit: без X-Client-Op-Id → 422; op_id не v4 → 422; occasion "stage_end" → 422; 14 ответов → 422; ответ 4 → 422; ответ true → 422; всё верно, БД недоступна (api_client) → 503 SERVICE_UNAVAILABLE.
test_checkup_submit_db.py (с БД — только CI; фикстуры — как у соседних тестов с БД в conftest.py):
- суммы 9 / 10 / 22 / 23 → zone green / yellow / red; строка: kind checkup, occasion onboarding, stage_no NULL, checkup_score = сумма, checkup_config_version = версия файла; в ответе нет score;
- тело с "score": 45, "zone": "green" для [0]*15 → zone green, score 0 в БД;
- повтор того же op_id с другими ответами → тот же 200 (то же тело), строк 1; новый op_id → строк 2;
- нет участника → 404 PARTICIPANT_NOT_FOUND; C1 отозвано или текст сменился → 409 RECONSENT_REQUIRED; нет текста согласия в text_registry → 503 SERVICE_MISCONFIGURED; во всех трёх строк 0;
- caplog: в записях app.checkup нет ответов, балла, pid и op_id.

## 10. Живые проверки на сервере (после мержа). Если 0014 на сервере ещё нет — submit отвечает 503 SERVICE_UNAVAILABLE, это ожидаемо; проверки ниже — только 401
- Сборка и рестарт api — как обычно (СЕРВЕРНЫЙ); 7/7 Up, api healthy.
- GET /miniapp/v1/checkup/config без initData → 401; POST /miniapp/v1/checkup/submit без initData → 401.
- Лог api после старта: Traceback 0. Бэкап не нужен: миграции нет.

## 11. Запреты
- AGENT-BRIEF §3. Не писать participant_events, outbox, idempotency_keys; не трогать проектор и бот.
- Не делать: checkup.scored, пост результата в группу или карточку (05 §5.4), сравнение с прошлым разом и алерт «Тревожная динамика», автоэскалацию красной зоны (OVERRIDES OPEN_C I3.red_zone.auto_escalation_60s), stage_end, проверку legal_status (гейт Legal).
- Балл — не в ответ и не в лог. Балл и зону от клиента не принимать. Настоящих текстов не писать — только заглушки.
- Не менять consent_status.py, participant_lock.py, errors.py, миграции, models.py.

## 12. Критерии готовности
- tools/check.sh зелёный; CI 7/7 зелёный, в том числе тесты с БД.
- Тесты 9 / 10 / 22 / 23 и все случаи битого конфига есть и проходят. test_every_miniapp_v1_route_requires_init_data проходит без правки.
- В описании PR — каждое отличие от карточки и файлы, открытые вне раздела 5.

## 13. Оценка
Кредиты ≈ 500–600 (Р1, Агент); часы Автора ≈ 1.

## 14. РЕВЬЮЕР
Нет. Решил ШТАБ (К-5): согласия только читаются готовой функцией consent_status (B-2 не меняется), initData и rate-limit — существующий роутер.

## Канон и решения
(а) Задача использует: 05 §5.1–5.5, fail-safe, yaml; I3 §C.3, §C.7, §C.12; 04 §4.1 (Шаг 4.5), §4.8, §4.10; I1 R_318 (C5 photo_consent — единственное отдельное согласие по ст. 10) — отменён Р-3; build/miniapp-api-contract.yaml (/checkup/config, /checkup/submit, ServiceUnavailable); db-i3-2 §7–§8.
(б) Противоречат:
- 05 §5.4 и yaml to_participant «балл + зона + расшифровка» — против I3 §C.7 и Л2 (правка №8);
- contract «5 зон» — против 05 §5.3 и I3 §C.7 «Зон три» (правка №5);
- I3 §C.7 checkup_config_versions и /publish_checkup_config — порядок работ (Л2): до И6 — файл (правка №12);
- contract «Проходит гейт Legal (И3)» у GET config. По канону гейт Legal — гейт публикации: I3 §C.7 «CI-чек запрещает публиковать версию, в которой хоть один текст красной зоны ждёт юридической вычитки», §C.12 «публикация конфигурации Чек-Апа закрыта гейтом одобрения Legal». Решение [К-6 тех]: проверки в GET нет — публикация конфига по Л2 откладывается до Панели (И6), тексты сейчас — заглушки с legal_status pre-legal-review, а по I3 §C.3 pre-legal-review «по шлюзу И1 блокирует prod-launch». Гейт закрывается до прода: строка «К проду» в «Для ШТАБА»; в Панели (И6) — CI-чек публикации. Правки DOCS не нужно: contract не говорит, что гейт проверяется в GET.
(в) Правки DOCS (пути architecture/; один PR и sync до промпта Агенту):
- №8 · architecture/05-checkup.md §5.4 · найди: «Участнику — сразу, красивым сообщением: балл + зона + расшифровка.» · замени: «Участнику — сразу, красивым сообщением: зона + расшифровка; балл не показывается (I3 §C.7).»
- №8 · 05-checkup.md, yaml · найди: «to_participant: instant              # балл + зона + расшифровка, красиво» · замени: «to_participant: instant              # зона + расшифровка, балл не показывается (I3 §C.7)». §5.1 «Результат = балл + зона + расшифровка» — то, что хранится; не меняется.
- №5 · architecture/build/miniapp-api-contract.yaml · найди: «summary: "Конфигурация Чек-Апа (5 зон, шкала, дисклеймер)"» · замени: «summary: "Конфигурация Чек-Апа (3 зоны green / yellow / red, шкала, дисклеймер; границы и балл участнику не отдаются — I3 §C.7)"».
- №12 · architecture/normative/I3-wave-c.md — врезка в шапку после цитаты «Переопределено/дополнено ERRATA-UNIFIED» (образец — врезка в I1-wave-a.md), тело и OVERRIDES не трогать: «> **Уточнено реализацией (course-bot).** C.7: таблица `checkup_config_versions` и `/publish_checkup_config` — с Панелью (И6); до того конфиг Чек-Апа — файл в репо (`apps/api/config/checkup/`), версия пишется в результат (measurements_log.checkup_config_version). YAML ниже не меняется.»
(г) Остальное из (а) не противоречит DECISIONS.

## Задетые тесты
Не ожидается. Поиск по общим спискам: TTL_BY_KIND не меняется (idempotency_keys не используются); новых text_id нет; новый роутер в main.py проверяют test_telegram_init_data (test_every_miniapp_v1_route_requires_init_data — обходит все пути сам; test_openapi_has_only_expected_public_routes — только публичные), test_rate_limit и test_api — правка не нужна; файлов про checkup в apps/api/tests нет; test_db_roles_0014 — миграция, не задевается (сверено ШТАБом @11eb4be).

## Для ШТАБА
- Кандидат на сторону бота (в PLAN): checkup.scored и пост результата в группу или карточку (I3 §C.7, 05 §5.4); автоэскалация красной зоны (OVERRIDES OPEN_C I3.red_zone.auto_escalation_60s).
- Кандидат: stage_end в submit — вместе с этапами (I3 §C.7, stage_completed).
- Строка STATE «К проду»: «юр-проверка текстов красной зоны Чек-Апа и гейт Legal (I3 §C.7, §C.12); сейчас legal_status pre-legal-review, проверки нет».
- Строка STATE «К проду»: «юр-ревью: хватает ли C0/C1 для ответов Чек-Апа (возможно, данные о здоровье, ст.10 152-ФЗ) или нужен отдельный пункт согласия; prod_launch_gate I1».
- Строка STATE: «api-i3-1 карточка (PR #178); DOCS №5, №8, №12 (врезка, без OVERRIDES) — до промпта Агенту».

## Вопросы ШТАБу
Нет: вопросы 1 (согласие) и 2 (РЕВЬЮЕР) закрыты ШТАБом в З3.
