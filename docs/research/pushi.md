# Исследование: пуши и лестница напоминаний (pushi)
Окно ИССЛЕДОВАНИЕ, З2 25.10.2026, main 8833b18 (#132), PR #133. Правило К — docs/process/CANON-CHECK.md. Ссылки «путь@8833b18». Тексты — заглушки до 0-Б. Карточки пишет окно КАРТОЧКИ.

## 0. Решения (К-6)
- НП1 А — полуденное в 12:00 по ТЗ участника [Автор; 03 §3.18].
- НП2 А — пуша в 04:00 нет [Автор; 03 §3.1].
- НП3 А — после очереди и после онбординга «Задания откроются … в 04:00 по Вашему времени», заглушка [Автор; 03 §3.19, 09 R257].
- В1 А — НП3 после онбординга пишут «часы» в проекторе (app_projector, права 0009); миграции нет; задержка до одного тика (30 с) допустима [Автор, канон молчит].
- В2 Б — два текста; выбор по местному времени в момент записи в outbox: до 04:00 — «сегодня», с 04:00 — «завтра» [Автор, канон молчит].
- В3 А — полуденное, пропущенное из-за простоя, догоняется до 18:00 по ТЗ; с 18:00 не отправляется; ключ пишется только при отправке [Автор, канон молчит].
- Р-6 тумблеров нет [STATE Р-6] = 09 R123-FINAL, NR-215. Р-8 ключ = раздел + имя маленькими, seed JSON [STATE Р-8].
- Таймер — шаг в проекторе [решил ШТАБ: 0009 В4 = В; В1 А].

## 1. Outbox и права
- Бот: CLAIM, MARK, DLQ, «Нет: INSERT в outbox» — apps/bot/bot/outbox.py@8833b18.
- «Часы»: «Outbox здесь не пишется» — apps/api/app/life_ops.py@8833b18.
- 0001: INSERT outbox — outbox_writer; SELECT, UPDATE — outbox_relay (2026_09_23_1700-0001_init_init.py@8833b18).
- 0009: app_projector INSERT (aggregate_id, event_type, payload, tx_id) + USAGE outbox_id_seq; SELECT на outbox нет, поэтому RETURNING нельзя. Схема В4 = В: событие и outbox — одна транзакция (2026_10_17_1200-0009_app_bot_app_bot.py@8833b18).
- app_api прав на outbox нет: 0006, 0007, 0008, 0010 [ШТАБ проверил].
- CHECK на idempotency_keys.kind нет, есть только на key и ttl (2026_10_16_1200-0007_day_state_day_state.py@8833b18) [ШТАБ] → новый kind без миграции.
Вывод: миграций в пачке нет.

## 2. Таймер 12:00
- Место: новый модуль app/notify_ops.py, вызов из projector run_forever рядом с life_ops.tick, тот же интервал. Время — аргумент now, функции day_clock. Образец транзакций — life_ops: кандидаты только чтением, потом каждый pid — своя транзакция под lock_participant с повторной проверкой; ключ ON CONFLICT DO NOTHING + outbox в одной транзакции.
- Ключ: noon:{pid}:{местная дата YYYY-MM-DD}, kind noon, ttl 3650 days, по образцу apps/api/app/day_keys.py@8833b18. Раз в сутки участника (03 §3.18 «ежедневно»).
- Окно отправки: 12:00 ≤ местное время < 18:00 (В3). Тик в окне шлёт, если условия выполнены; ключ — только вместе с outbox. С 18:00 — ничего не писать.
- Пояс: tz из participant_state; смена пояса — со следующего дня (03 yaml timezone_change). При смене пояса возможны 2 T3 за 24 ч (09 R260) — допустимо как редкий случай, D-e.

## 3. Условия полуденного
Канон: 12:00 и ноль активности сегодня (нажатие или сообщение); не слать активному или сдавшему (03 §3.18); гейт T3-NOON-NUDGE: has_open_step AND day_not_13P AND not_shadow; общий гейт T3: не ban, erased, refund_final, shadow_pause; не больше 1 T3 за 24 ч (09 tiers, R260).
| Условие | Проверка | Источник |
|---|---|---|
| фаза onboarding или active | PHASES | life_ops.py |
| пауза, блок | author_pause_reason IS NULL, нет BLOCKING_FLAGS | life_ops.py |
| sleeping | вне PHASES | life_ops.py |
| has_open_step | day_clock.window = open | day_clock.py |
| нет активности, не сдан | нет day_marks по текущему day_started_at, нет day_done | life_ops, day_keys |
| проектор догнал pid | как _PENDING_EVENT | life_ops.py |
| day_not_13P | день 13 module_1 = 13-M → истина | 03 §3.13 |
| tombstone | «часы» не видят; бот: MARK без отправки | outbox.py |
Не проверено: где хранится muted; пишется ли в БД активность-сообщение в боте (сейчас активность = отметки).

## 4. НП3: когда и кто
- После очереди. life-ops-b в main: сдача пишет ключ day_queue:{pid}:{dsa(next_started)}, GET /day/current сам считает queued_until (apps/api/app/routers/day.py@8833b18) [ШТАБ]. Outbox не умеет «не раньше»: бот берёт строку сразу (outbox.py). Писатель — «часы»: есть day_queue, now ≥ queued_until, нет ключа tasks_open → ключ tasks_open:{pid}:{dsa(next_started)} + outbox одной транзакцией.
- После онбординга (В1 А): «часы» видят конец онбординга → тот же ключ tasks_open:{pid}:{dsa(started первого дня)}, если онбординг ставит day_started_at; иначе отдельный kind tasks_open_onb:{pid} — решит окно КАРТОЧКИ по коду.
- Текст (В2 Б): местное время записи < 04:00 → B9.day_tasks_open_today, иначе B9.day_tasks_open_tomorrow.
- Простой: если запись позже 04:00 следующего утра — задания уже открыты, «завтра» неверно → вопрос В4.

## 5. Как бот отрисует
outbox.py@8833b18: aggregate_id = pid строкой; payload: text_id (ключ text_registry), payload_vars (по умолчанию {}), tier. event_type — только в логах. Нет текста → DLQ text_not_found; нет переменной → missing_var. Бот не меняется.
Домены схемы: только B2, B4, B5, B7, B9, B10, B14, B15, B16, legal (apps/api/config/text_registry.schema.json@8833b18) [ШТАБ]. Тексты дня — B9.day_* в apps/api/config/texts/day.json@8833b18 (например B9.day_queue_wait) [ШТАБ]. Схема не меняется.
| event_type | text_id | tier | текст |
|---|---|---|---|
| noon_nudge | B9.day_noon_nudge | T3 | [ЗАГЛУШКА] Полуденное напоминание |
| tasks_open_notice | B9.day_tasks_open_tomorrow | T2 | [ЗАГЛУШКА] Задания откроются завтра в 04:00 по Вашему времени |
| tasks_open_notice | B9.day_tasks_open_today | T2 | [ЗАГЛУШКА] Задания откроются сегодня в 04:00 по Вашему времени |
| ladder_reminder | B9.day_ladder_plus1h | T2 | [ЗАГЛУШКА] Лестница: +1 ч |
| ladder_reminder | B9.day_ladder_minus2h | T2 | [ЗАГЛУШКА] Лестница: 22:00 |
| ladder_reminder | B9.day_ladder_minus30m | T2 | [ЗАГЛУШКА] Лестница: 23:30 |
Все — legal_status pre-legal-review, payload_vars пустые. После выката texts load: «загружено 3» (notify-1 и noon-1) и «загружено 3» (ladder-1).

## 6. Лестница DM 3.17
Шаги участнику: +1 ч после первой отметки, 22:00, 23:30 по ТЗ, если день не сдан. Ключ ladder:{pid}:{dsa}:{шаг}. Первая отметка = min(day_marks.at) по pid и day_started_at; SELECT у app_projector есть (0008@8833b18) [ШТАБ]. min(at) или перезапись at при UPDATE (value, at) — сверить окну КАРТОЧКИ по коду marks. Алерт Автору «день 2» — вне пачки (бот адресует только pid).

## 7. Карточки (одна область — API+projector; строго по порядку, один модуль)
- 1) pushi-notify-1: модуль app/notify_ops.py + вызов из projector; НП3 после очереди и после онбординга; kind tasks_open в day_keys.py; 2 текста в day.json. Агент 600–900 + 60–100 за задетый тест. РЕВЬЮЕР нет.
- 2) pushi-noon-1: полуденное, окно 12:00–18:00, kind noon, текст. После мержа 1. Агент 400–600. РЕВЬЮЕР нет.
- 3) pushi-ladder-1: лестница 3.17, kind ladder, 3 текста. После мержа 2. Агент 500–800. РЕВЬЮЕР нет.
Выкат каждой: пересборка projector + texts load; projector 88dc8d4 не трогать до живой проверки «C» (STATE).
Тесты — кандидаты по именам (apps/*/tests@8833b18), читать окну КАРТОЧКИ: apps/api/tests/test_projector_static.py, test_projector_v3.py, test_projector_day_report.py, test_day_queue.py, test_day_marks.py, test_day_report_submit.py, test_life_ops_race.py, test_texts_load_errors.py, test_onb*.py; по маске сверить test_life_ops*.py, test_day_clock*.py, test_texts*.py. Бот (test_render.py, тест outbox) — не ожидается.

## 8. Окну КАРТОЧКИ взять
- apps/api/app/projector.py — место вызова шага, интервал, нужен ли подъём PROJECTOR_VERSION.
- apps/bot/bot/render.py — как подставляются payload_vars и tier, усечение T3.
- apps/api/app/routers/day.py — next_started, запись day_queue, расчёт queued_until (каким started_at), day_done.
- apps/api/app/routers/onboarding.py — событие «онбординг окончен», ставится ли day_started_at.
- код marks — min(at) против перезаписи at.
- тесты из раздела 7 — правило «Т».

## 9. Предложения D-* (в DEFECTS-FOUND не вносить)
- D-a: 03 §3.18 «категория „отключаемые“» ↔ 09 R123-FINAL, NR-215, Р-6. Правка: убрать слово.
- D-b: 03 §3.18 «половина дня Участника» ↔ НП1 12:00 (день 04:00–00:00, середина 14:00). Нужна ли строка «перекрывающие канон» — ШТАБ (К-7).
- D-c: tombstone не виден «часам» → строка outbox стёртому (бот закроет без отправки); NR-207 до 0-Б.
- D-d: конверт 09 emit_envelope (must_deliver, drop_on_overload, coalesce_key, addressee) ↔ бот читает только text_id, payload_vars, tier.
- D-e: ключ по местной дате ↔ 09 R260 (1 T3 за 24 ч) при смене пояса.
- D-f: тексты механики дня (блок 3) в каноне без домена; схема даёт B9.day_* — записать в канон.

## 10. Вопрос Автору
- В4. НП3 запоздал из-за простоя до времени после 04:00 (задания уже открыты). А — не отправлять, ключ записать. Б — отправить «завтра». Мнение: А. Канон: проверено 03 §3.1, 3.19; 09 R257, tiers — молчит; текст курса.

## 11. Прочитано
З1: DESIGNER, STATE, AGENT-BRIEF, README, CANON-CHECK, CODER, 03, 09 (хвост около 1 КБ не открылся, gzip), outbox.py, life_ops.py, day_clock.py, 0009; сверх списка 0001 (роли outbox), day_keys.py (образец ключей). З2: ничего (решение ШТАБа); факты ШТАБа помечены [ШТАБ].
