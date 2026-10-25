# Исследование: пуши и лестница напоминаний (pushi)
Окно ИССЛЕДОВАНИЕ, 25.10.2026, main 8833b18 (#132). Правило К — docs/process/CANON-CHECK.md. Ссылки «путь@8833b18». Тексты — заглушки до 0-Б. Карточки пишет окно КАРТОЧКИ.

## 0. Решения (К-6)
- НП1 А — полуденное в 12:00 по ТЗ участника [Автор, канон проверен 03 §3.18].
- НП2 А — пуша в 04:00 нет [Автор, канон проверен 03 §3.1].
- НП3 А — после очереди и после онбординга «Задания откроются завтра в 04:00 по Вашему времени» (заглушка) [Автор, канон проверен 03 §3.19, 09 R257].
- Р-6 тумблеров нет [STATE Р-6]; совпадает с 09 R123-FINAL, NR-201, NR-215.
- Р-8 ключ = раздел B2…B16 + имя маленькими, seed JSON [STATE Р-8].

## 1. Кто пишет outbox, права
- Бот: CLAIM, MARK, DLQ; «Нет: INSERT в outbox» — apps/bot/bot/outbox.py@8833b18.
- «Часы»: «Outbox здесь не пишется» — apps/api/app/life_ops.py@8833b18.
- 0001: GRANT INSERT ON outbox TO outbox_writer; SELECT, UPDATE — outbox_relay (2026_09_23_1700-0001_init_init.py@8833b18). Члены outbox_writer — не проверено.
- 0009: app_projector INSERT (aggregate_id, event_type, payload, tx_id) + USAGE outbox_id_seq, SELECT нет (RETURNING нельзя); app_bot SELECT, UPDATE (sent_at), INSERT outbox_dlq (2026_10_17_1200-0009_app_bot_app_bot.py@8833b18). Схема В4 = В: «часы» в проекторе пишут событие и outbox одной транзакцией.
- app_api: в 0001 и 0009 прав на outbox нет; 0002–0008, 0010 не читал — не проверено.
- Писателя outbox в прочитанном коде нет (на сервере 3 тестовые строки send-1b, STATE). day.py, onboarding.py, projector.py не читал — не проверено.
Вывод: все пуши пишут «часы» в проекторе → миграция не нужна. API пишет НП3 (В1 = Б) → миграция 0011 отдельной карточкой (down_revision 0010_access_grants), РЕВЬЮЕР да (B-3). До карточек проверить: нет ли CHECK на idempotency_keys.kind (0007, не читал); есть — новый kind тоже требует миграции.

## 2. Где таймер 12:00
- А. Шаг в проекторе рядом с life_ops.tick, свой модуль (например app/notify_ops.py), интервал 30 с. Плюсы: схема 0009 В4 = В; права уже есть (outbox; idempotency_keys, day_marks, participant_events, participant_state использует life_ops); образец кода и тестов; время — аргумент now через day_clock. Минусы: пересборка projector (на сервере 88dc8d4, ждёт живую проверку «C» 26.10); тяжелее тик.
- Б. Планировщик в боте. Минусы: у app_bot нет SELECT на participant_state → миграция; бизнес-логика в транспорте (09 ownership: does_not_own business_logic).
- В. Отдельный APScheduler или Celery (03 §3.19 упоминает для очереди). Минусы: новая зависимость, память (сейчас 1920 из 2048 МБ).
Мнение: А [ШТАБ-тех: 0009 В4 = В].
Ключ (образец apps/api/app/day_keys.py@8833b18: {kind}:{pid}:{...}, ON CONFLICT DO NOTHING RETURNING, ttl 3650 days): noon:{pid}:{местная дата YYYY-MM-DD} — раз в сутки участника (03 §3.18 «ежедневно»), не зависит от смен day_started_at. Ключ и outbox — одна транзакция под lock_participant (как life_ops шаг 7).
Простой в 12:00: канон о догоне молчит (03 §3.18; 09 T3: must_deliver false, droppable). У «часов» после простоя — одна граница (day_clock.last_midnight, В32). → вопрос В3.

## 3. Условия полуденного
Канон: 12:00 (НП1) и ноль активности сегодня, активность = нажатие или сообщение (03 §3.18); не слать активному или сдавшему; гейт T3-NOON-NUDGE: has_open_step AND day_not_13P AND not_shadow; общий гейт T3: не ban, erased, refund_final, shadow_pause_active (09 tiers, NR-211); не больше 1 T3 за 24 ч (09 R260).
| Условие | Проверка | Источник |
|---|---|---|
| фаза onboarding или active | PHASES | life_ops.py |
| пауза Автора, флаги | author_pause_reason IS NULL, нет BLOCKING_FLAGS | life_ops.py; 09 гейт T3 |
| sleeping, muted | вне PHASES (У3) | life_ops.py; где хранится muted — не проверено |
| has_open_step | day_clock.window = open | day_clock.py |
| нет активности, не сдан | нет day_marks по текущему day_started_at, нет day_done | life_ops _HAS_MARKS, day_keys |
| проектор догнал pid | как _PENDING_EVENT | life_ops.py |
| day_not_13P | module_1: день 13 = 13-M → истина | 03 §3.13; контент не читал |
| tombstone | «часы» не видят; бот: MARK без отправки | life_ops.py, outbox.py |
| R260 | других T3 нет → хватит ключа по дате | 09 R260 |
Активность в боте (сообщения) в БД не пишется — не проверено.
Кандидаты D-* (не вношу):
- D-a: 03 §3.18 «категория „отключаемые“» ↔ 09 R123-FINAL, NR-201, NR-215, Р-6. Правка канона: убрать слово.
- D-b: 03 §3.18 «половина дня Участника» ↔ НП1 12:00 (день 04:00–00:00, середина 14:00). Уточнить канон; ШТАБу решить, нужна ли строка «перекрывающие канон» (К-7).
- D-c: tombstone не виден «часам» → полуденное стёртому создаст строку outbox (бот закроет без отправки); NR-207 до GRANT (до 0-Б).
- D-d: конверт 09 contracts_out.emit_envelope (must_deliver, drop_on_overload, coalesce_key, addressee) ↔ бот читает только text_id, payload_vars, tier.

## 4. НП3: когда и кто
- После очереди: очередь = day_clock.queue_until(pid, started_at), 10–60 мин, не хранится (day_clock.py@8833b18; 03 §3.19). Outbox не умеет «не раньше»: бот берёт строку сразу (CLAIM по created_at; колонки времени отправки нет — outbox.py, 0001). Писать из транзакции сдачи нельзя — уйдёт до конца очереди. Писатель — «часы»: now ≥ queue_until, ключа нет → ключ tasks_open:{pid}:{dsa сданного дня} + outbox одной транзакцией. Ключ day_queue в day_keys описан для life-ops-b; сделан ли life-ops-b — не проверено.
- После онбординга: «часы» или API в транзакции онбординга (миграция) → В1.
- Конец очереди или онбординга между 00:00 и 04:00 — «завтра» неверно → В2.
Окну КАРТОЧКИ взять:
- day.py: kind и payload события сдачи (day_started_at сданного дня), где пишется day_done, когда появляется day_started_at дня N+1, использует ли GET /day/current queue_until.
- onboarding.py: какое событие = «онбординг окончен»; ставится ли day_started_at.
- projector.py: где run_forever вызывает life_ops.tick; PROJECTOR_VERSION.

## 5. Как бот отрисует
outbox.py@8833b18: aggregate_id = pid (UUID строкой); payload — dict: text_id (ключ text_registry), payload_vars (dict, по умолчанию {}), tier (в build_html_parts; T3 — усечение 900, 09). event_type — только в логах. Нет текста → DLQ text_not_found; нет переменной → missing_var. Бот не меняется.
| event_type | text_id | tier | заглушка |
|---|---|---|---|
| noon_nudge | B3.noon_nudge | T3 | [заглушка] Полуденное напоминание |
| tasks_open_notice | B3.tasks_open_0400 | T2 | [заглушка] Задания откроются завтра в 04:00 по Вашему времени |
При В2 = Б ещё B3.tasks_open_0400_today. Лестница 3.17: B3.ladder_plus1h, B3.ladder_minus2h, B3.ladder_minus30m (T2). Раздел B3 — событие механики дня (03); шаблон ключа в text_registry.schema.json не читал — не проверено. После выката texts load: «загружено N» (сейчас норма «загружено 0, обновлено 33»).

## 6. Карточки
- pushi-db-1 (БД), только при В1 = Б или CHECK на kind: 0011, GRANT app_api INSERT (aggregate_id, event_type, payload, tx_id) на outbox + USAGE outbox_id_seq; первой. Агент 400–600. РЕВЬЮЕР да.
- pushi-noon-1 (API+projector): модуль уведомлений (полуденное, НП3 после очереди, после онбординга при В1 = А), вызов из projector, ключи в day_keys.py, seed и схема. После ответов В1–В3. Около 8–10 файлов. Агент 700–1 000 + 60–100 за задетый тест. РЕВЬЮЕР нет.
- pushi-ladder-1 (тот же модуль): 03 §3.17 участнику (+1 ч после первой отметки, 22:00, 23:30 по ТЗ), ключ ladder:{pid}:{dsa}:{шаг}. Нужна метка времени первой отметки в day_marks — не проверено. Алерт Автору «день 2» — позже (бот адресует только pid). После мержа pushi-noon-1. Агент 500–800. РЕВЬЮЕР нет.
Задетые тесты — кандидаты по именам (apps/*/tests@8833b18), читать окну КАРТОЧКИ: apps/api/tests/test_projector_static.py, test_projector.py, test_projector_v3.py, test_life_ops.py, test_day_clock.py, test_day_queue.py, test_day_writers.py, test_texts.py; при миграции test_db_roles_0009.py, test_db_models.py; при В1 = Б test_first_launch.py, test_onboarding_status.py. Бот (test_outbox.py, test_render.py) — не ожидается.

## 7. Вопросы Автору
- В1. Кто пишет «Задания откроются…» после онбординга. А — «часы» в проекторе (без миграции, задержка до 30 с). Б — API в транзакции онбординга (миграция 0011, РЕВЬЮЕР). Мнение: А. Канон: проверено 03 §3.19, 09 contracts_out, 0009 В4 — молчит, кто пишет; архитектурный выбор.
- В2. Конец очереди или онбординга с 00:00 до 04:00. А — один текст «завтра» всегда. Б — второй текст «сегодня в 04:00» (ключ …_today). Мнение: Б. Канон: проверено 03 §3.1, 3.19, 09 R257 — молчит; текст курса.
- В3. Сервер стоял в 12:00. А — догнать до 18:00 по ТЗ, позже пропустить. Б — до 22:00. В — не догонять. Мнение: А. Канон: проверено 03 §3.18, 09 tiers T3 — молчит.

## 8. Надо дочитать (решает ШТАБ)
- apps/api/config/text_registry.schema.json — шаблон ключа B3.*.
- apps/bot/bot/render.py — переменные и tier.
- apps/api/app/projector.py — место шага, версия.
- 0007 (idempotency_keys: CHECK на kind, права app_projector).
- 0002–0008, 0010 или test_db_roles*.py — нет ли у app_api INSERT на outbox.
- day.py, onboarding.py — окно КАРТОЧКИ (п. 4).

## 9. Прочитано (КБ)
- docs/process/DESIGNER.md 17,3 — правило «Т», файл исследования до 15 КБ.
- docs/STATE.md 20,4 — НП1–НП3; Р-6, Р-8; projector 88dc8d4 не трогать до 26.10.
- AGENT-BRIEF.md 17,1 — запреты, тексты — заглушки.
- docs/process/README.md 8,7 — миграции по одной.
- docs/process/CANON-CHECK.md 4,8 — К-4, К-6.
- docs/process/CODER.md 11,3 — команды «Под пакетом З1».
- docs/architecture/03-day-mechanics.md 26,2 — §3.1, 3.17–3.19.
- docs/architecture/09-communications.md 38,2 — T3-NOON-NUDGE, R257, R260; хвост YAML около 1 КБ не открылся (ошибка gzip), R260 взят из выжимки.
- apps/bot/bot/outbox.py 20,6 — конверт text_id, payload_vars, tier.
- apps/api/app/life_ops.py 17,0 — фильтр, ключ + события одной транзакцией; outbox не пишет.
- apps/api/app/day_clock.py 10,0 — window, queue_until, last_midnight.
- 0009_app_bot 5,1 — INSERT outbox у app_projector.
- сверх списка: 0001_init 9,6 — таблица outbox и роли outbox_writer, outbox_relay.
- сверх списка: apps/api/app/day_keys.py 2,9 — образец ключей.
