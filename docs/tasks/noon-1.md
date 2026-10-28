# noon-1 — полуденное уведомление (НП1): 12:00 по ТЗ, догон до 18:00

## 0. Паспорт
- Область: apps/api — notify_ops, day_keys, тексты. Миграций нет. Проектор не меняется: ШТАБ проверил по 00bff0b, projector.py зовёт только notify_ops.tick.
- Зависит от pushi-notify-1 (#135, в main). Следующая — ladder-1, только после мержа noon-1.
- Ветка задачи: feat/noon-1. check.sh: api. Режим: очередь Агента (STATE) — решает ШТАБ.
- Оценка: 550–750 кредитов (база 400–600 по pushi.md §7 + 2 задетых файла по правилу «Т»).
- Правило К — docs/process/CANON-CHECK.md. Сначала прочитай docs/decisions/DECISIONS.md целиком.
- Агенту docs/architecture/** не открывать: выдержки — §4.

## 1. Цель
Каждый день в 12:00 по ТЗ участника тому, у кого день открыт и нет ни одной отметки, бот шлёт одно мягкое уведомление (текст — заглушка). Пропущенное из-за простоя догоняется до 18:00; с 18:00 не шлётся. Ключ пишется только при отправке.

## 2. Решения (К-6)
Из pushi.md §0 дословно:
- НП1 А — полуденное в 12:00 по ТЗ участника [Автор; 03 §3.18].
- В3 А — полуденное, пропущенное из-за простоя, догоняется до 18:00 по ТЗ; с 18:00 не отправляется; ключ пишется только при отправке [Автор, канон молчит].
- Р-6 тумблеров нет [STATE Р-6] = 09 R123-FINAL, NR-215. Р-8 ключ = раздел + имя маленькими, seed JSON [STATE Р-8].
Ответы Автора 28.10 (запись НП в DECISIONS — этот же PR):
- В5 А — «1 T3 за 24 ч» = одно полуденное в местные сутки; ключ по местной дате [Автор против канона → DECISIONS НП].
- В6 А — активность = только строки day_marks; сообщения боту в БД не пишутся (задача activity-1) [Автор против канона → DECISIONS НП].
Решения карточки [ШТАБ-тех]:
- Т1. Вход один — notify_ops.tick; внутри по очереди правила tick_tasks_open (бывший tick) и tick_noon; у каждого свой NotifyResult. Почему: проектор не меняется; счётчики НП3 не смешиваются с полуденными (фикстура не чистит outbox и idempotency_keys).
- Т2. Константы 12:00 и 18:00 — в notify_ops: время пушей, а не границы дня; day_clock не трогаем.
- Т3. Тесты полуденного — новый файл test_notify_noon.py (test_notify_ops.py уже 13,2 КБ).

## 3. Канон и решения
(а) Использует: 03 §3.18, yaml midday_inactivity, §3.13 (13-P), §3.21 (смена пояса); 09 NR-211, T3_default_gate_on_missing_signal, T3_gates.noon_nudge_eligible, R260, NR-239.
(б) Противоречат DECISIONS: 03 §3.18 «категория „отключаемые“» — Р-6; «половина дня» — НП (12:00); «ни нажатий, ни сообщений» — НП (В6 А, до activity-1, канон не правим); 09 R260 и NR-239 «1 T3 за 24 ч» — НП (В5 А).
(в) Правки DOCS (маленький PR и sync ДО промпта Агенту):
1. architecture/03-day-mechanics.md · найди «Ежедневно, когда проходит половина дня Участника по его ТЗ и» · замени на «Ежедневно в 12:00 по ТЗ Участника (пропущенное из-за простоя — до 18:00, не позже) и»
2. architecture/03-day-mechanics.md · найди «одно мягкое мотивационное уведомление (категория «отключаемые»).» · замени на «одно мягкое мотивационное уведомление (настроек уведомлений нет — Р-6).»
3. architecture/03-day-mechanics.md · найди «when: "половина дня участника по ТЗ + ноль активности сегодня"» · замени на «when: "12:00 по ТЗ участника (догон до 18:00) + ноль активности сегодня"»
4. architecture/03-day-mechanics.md · найди «# категория "отключаемые"» · замени на «# Р-6: настроек уведомлений нет»
5. architecture/09-communications.md · найди «Мотивационные сообщения получают жёсткую крышу: не более одного T3-сообщения на участника за 24 часа, независимо от количества триггеров;» · замени на «Мотивационные сообщения получают жёсткую крышу: не более одного полуденного T3-сообщения (T3-NOON-NUDGE) на участника в местные сутки (DECISIONS НП, В5 А), независимо от количества триггеров;». YAML R260 в added_rules (стр. ≈411–422) и строку NR-239 (п.6) ШТАБ сверяет поиском в Codespace DOCS перед PR DOCS.
6. architecture/09-communications.md · найди «  - NR-239: no_more_than_one_T3_per_24h_per_participant» · замени на «  - NR-239: no_more_than_one_noon_T3_per_local_day_per_participant   # DECISIONS НП (В5 А)»
(г) Остальное (§3.13, §3.21, NR-211, T3_gates) — правок нет.

## 4. Выдержки канона
- 03 §3.18: «Тем, кто уже проявил активность/сдал — не шлёт. Это отдельное событие от алерта Автору про „галочки без отправки“». «Бот НЕ видит факт „Участник открыл и читает, ничего не нажимая“».
- 03 §3.13: 13-M — переход М1→М2, М3→М4; 13-P — переход М2→М3, М4→М5 (день 13 чётного модуля).
- 03 §3.21: смена ТЗ — со следующего дня, не задним числом.
- 09: гейт T3-NOON-NUDGE = has_open_step AND day_not_13P AND not_shadow; NR-211 T3_gated_by_ban_erased_refund_final_shadow; T3_default_gate_on_missing_signal: suppress.

## 5. Файлы (6)
1. apps/api/app/day_keys.py — KIND_NOON = "noon", TTL_NOON = "3650 days", в TTL_BY_KIND; key_noon(pid, local_date: date) → "noon:{pid}:{YYYY-MM-DD}"; строка в docstring.
2. apps/api/app/notify_ops.py — §6.
3. apps/api/config/texts/day.json — §7; version 0.3.0 → 0.4.0.
4. apps/api/tests/test_notify_noon.py — новый, §9.
5. apps/api/tests/test_notify_ops.py — задет, §8.
6. apps/api/tests/test_day_current.py — задет, §8.

## 6. notify_ops: что сделать
- tick → tick_tasks_open: тело, NotifyResult, тексты логов НП3 («notify_ops: tick sent=… late=… skipped=…», «notify_ops: error on notify (…)») не меняются.
- Общий цикл можно вынести в _run_rule(engine, now, label, candidates, one) → NotifyResult: на каждый pid try/except, WARNING «notify_ops: error on <label> (<Class>)»; для НП3 label = "notify".
- Новый tick(engine, now) → NotifyTick (dataclass: tasks_open, noon — по NotifyResult). Сначала _require_aware(now); каждое правило в своём try/except Exception: WARNING «notify_ops: rule <name> failed (<Class>)», его результат — NotifyResult(0, 0, 0), следующее правило идёт.
- Константы: NOON_FROM = time(12, 0), NOON_UNTIL = time(18, 0), NOON_EVENT_TYPE = "noon_nudge", NOON_TIER = "T3", TEXT_NOON = "B9.day_noon_nudge".
- Чистые функции:
  - noon_window(now, tz) — NOON_FROM ≤ местное время < NOON_UNTIL; пояс — day_clock.zone(tz).
  - noon_local_date(now, tz) — местная дата (для ключа).
  - is_13p(module_no, day_no) — day_no == 13 и module_no чётный [канон 03 §3.13].
  - decide_noon(now, tz, started_at, module_no, day_no, marked, done, has_key) → "send" | None. "send" только если: noon_window; окно дня = WINDOW_OPEN (функция окна day_clock — имя и сигнатура по коду day_clock.py); не marked; не done; не has_key; не is_13p.
- tick_noon(engine, now) → NotifyResult (late всегда 0):
  1. Кандидаты — одна транзакция, только чтение: фильтр life_ops (фазы onboarding/active, author_pause_reason IS NULL, day_no NOT NULL, нет BLOCKING_FLAGS). Нужны tz, day_started_at, module_no, day_no; если life_ops._CANDIDATES их не отдаёт — свой SELECT с тем же WHERE (life_ops не менять). В Python сразу отсев по noon_window. Батчем: ключи noon и day_done (_EXISTING_KEYS); отметки — новый запрос «SELECT pid, day_started_at FROM day_marks WHERE pid = ANY(…) GROUP BY pid, day_started_at»; day_started_at сравнивать в UTC. decide_noon; не больше MAX_PER_TICK.
  2. Каждый pid — своя транзакция как в notify_one: SET LOCAL lock_timeout, lock_participant, life_ops._STATE заново, life_ops._eligible, «проектор догнал pid» (та же проверка, что у НП3), ключи и отметки заново, decide_noon заново.
  3. Запись: _INSERT_KEY (kind noon, ttl TTL_NOON); 0 строк → rollback; затем _INSERT_OUTBOX: aggregate_id = str(pid), event_type noon_nudge, payload {"text_id": TEXT_NOON, "payload_vars": {}, "tier": "T3"}. Один commit.
  4. Итог — одна строка INFO «notify_ops: noon sent=%s skipped=%s». В логах нет pid, tz и payload.
- Docstring модуля дополнить: noon-1, НП1 А, В3 А, В5 А, В6 А.

## 7. Тексты (day.json, version 0.4.0)
- key B9.day_noon_nudge · tone soft · legal_status pre-legal-review · text «[ЗАГЛУШКА] Задания сегодняшнего дня ждут Вас. Загляните, когда будет минутка.» · notes «noon-1: НП1, пишет notify_ops (T3). Заглушки до 0-Б.»
- В text_registry после texts load — 36 ключей (было 35).

## 8. Задетые тесты (правило «Т» и «Общие списки»)
- apps/api/tests/test_day_current.py::test_kinds_and_ttl — в словарь TTL_BY_KIND добавить строку «"noon": "3650 days",  # noon-1».
- apps/api/tests/test_notify_ops.py — в импорте из app.notify_ops: tick → tick_tasks_open; все вызовы tick(db_engine, …) в тестах 7–10 → tick_tasks_open(db_engine, …). Заглушку notify_ops.tick в тесте 6 (шаг проектора) не трогать.
- Проверено ШТАБом: test_texts, test_day_content, test_texts_load_errors, test_projector_static day.json и его версию целиком не сверяют. Упал тест вне списка → не чинить, «тест X вне списка» в ИТОГ, стоп.

## 9. Новые тесты — apps/api/tests/test_notify_noon.py
Без БД:
1. noon_window: 11:59 → нет; 12:00 и 17:59 → да; 18:00 → нет; Europe/Moscow и Asia/Vladivostok; тот же момент в UTC — тот же ответ.
2. decide_noon: marked, done или has_key → None; день не активен (started_at сегодня 10:00 — сдача утром; active_from завтра 04:00; now сегодня 12:30) → None; окно closed → None; is_13p → None.
3. is_13p: (2, 13) да; (1, 13), (2, 12), (3, 13) нет.
4. key_noon: формат, местная дата, naive не нужен (дата); TTL_BY_KIND["noon"] == "3650 days".
5. Статика: TEXT_NOON есть в day.json; версию day.json не сверять (ladder-1 её поднимет).
С БД (образец фикстур — test_notify_ops.py: register_with_consents, enter_day_by_test_flag, run_once, UPDATE владельцем; отметку вставлять владельцем, как _mark в test_day_current.py):
6. 12:00:30 местного, без отметок → noon.sent == 1, ключ noon, 1 строка outbox (noon_nudge, text_id, tier T3); второй tick → 0, outbox по pid по-прежнему 1.
7. Есть отметка за текущий day_started_at → 0; отметка за старый day_started_at не мешает → 1.
8. Ключ day_done → 0. 18:00 → 0, ключа нет; догон 17:59 → 1.
9. Пропуск (параметры, как тест 10 НП3): пауза, флаг, sleeping, не догнанное событие → 0, ни ключа, ни outbox.
10. tick: tick_tasks_open подменён на raise → WARNING «rule tasks_open failed (RuntimeError)», полуденное отправлено. Результат проверять по полям (r.noon.sent), NotifyTick целиком не сравнивать — ladder-1 добавит поле.

## 10. Не делать
- Не менять projector.py, life_ops.py, day_clock.py, миграции, бота.
- Не писать participant_state и participant_events (E1 / INV-1). Не проверять muted: такого поля нет, тумблеров нет (Р-6).
- Не писать активность сообщений (activity-1). Не трогать алерт Автору.

## 11. Живая проверка (аккаунты — метки, без имён)
- А1 (тестовый день) не трогать без указания ШТАБа.
- Ожидаемое состояние А2/А3 — по отчёту сервера до выката (29.10).
- А2: день открыт, отметок нет. В 12:00–12:01 по его ТЗ — 1 строка outbox noon_nudge, 1 доставка, dlq без новых; следующий тик — без повтора. После доставки А2 ставит одну отметку (иначе день молчания: missed_streak + 1).
- А3: до 12:00 есть отметка → полуденного нет.

## 12. Команды для Автора на IRONCLAD (через СЕРВЕРНЫЙ, после мержа, только main)
- Бэкап не нужен (миграций нет). Сборка api/projector/migrate; build migrate до texts load; texts load (36 ключей); пересоздать projector.
- Лог projector: «notify_ops: noon sent=…» каждый тик; Traceback 0, WARNING 0. projector once рядом с run не запускать.

## 13. Для ШТАБА
- Сверить до промпта: бот доставляет tier "T3" так же, как "T2" (apps/bot/bot/outbox.py) — иначе полуденное уйдёт в DLQ.
- Сверить: module_no сквозной (М2→М3 по 03 §3.13)? Если внутри этапа — is_13p меняется, вопрос мне или Автору.
- Сверить: тест 5 test_notify_ops.py (test_static_outbox_insert_and_kinds) — в выводе обрезан; не перечисляет ли он kind или тексты notify_ops целиком.
- Флаг refund_final в BLOCKING_FLAGS нет (NR-211; Р-4 — возвраты учётные); tombstone «часы» не видят — как у НП3, до 0-Б.
- NR-239 после правки касается только полуденного: появятся другие T3 (T3-REVIVE-WARMTH, дайджест этапа) — вернуться к общему лимиту.
- D-g → будущая задача activity-1: бот пишет факт сообщения (pid + время, без текста); вопрос Автору «сообщение боту = „пришёл“?» — в её карточке.
- D-h (docstring life_ops упоминает muted, поля нет), D-i (AGENT-BRIEF §6 устарел: PROJECTOR_VERSION, код БД в боте) — в docs-пакет.
- Строка STATE после выката: text_registry 36; в projector «часы» life_ops и notify_ops (НП3, НП1).

## 14. РЕВЬЮЕР
Не нужен: нет initData, 18+, оплаты, прав БД.
