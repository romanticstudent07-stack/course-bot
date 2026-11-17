# T6c bot-restart-1 — рестарт по промокоду (restart_paid)
Hash main bd27f44. Основа — docs/research/pause-2.md §5, §6, §9; docs/research/sleep-1.md §2 Р7. Правило К — docs/process/CANON-CHECK.md. Сначала прочитай docs/decisions/DECISIONS.md целиком.

## 1. Паспорт
- id: T6c bot-restart-1 · PR: «bot-restart-1: рестарт по промокоду — restart_paid» · ветка: feat/bot-restart-1
- Режим: Р1 (Агент). Зависит от: T6b bot-life-1 — начинать после её мержа (общие app.py, texts.py, замок participant:pid). Миграций нет. Область — бот.

## 2. Цель
Участник с block_lives пишет боту промокод. Бот отправляет заявку в админ-тему с кнопками [Выдать рестарт] / [Запретить]. На [Выдать рестарт] бот одной транзакцией пишет restart_paid. Проектор v6 снимает block_lives, ставит 3 жизни и выдаёт день 1 модуля 1 текущего Этапа с 00:00.

## 3. Решения (метка К-6)
- Р-20 (DECISIONS.md): «из block_lives — рестарт по промокоду (Р-1/Р-2; день 1 модуля 1 текущего Этапа, 3 жизни, лимиты пауз сброшены; имя restart_paid прежнее)» [Автор].
- Р-2: промокод → админ-тема → [Выдать]/[Запретить] [Автор].
- ШТАБ 17.11 (З2, в.1, К-5): вариант В, без миграции. access_grants и гейт Р-2 бот не трогает; api не меняется. Заявка живёт только как сообщение в админ-теме; callback содержит short_no. Ключ restart_req:{pid}:{дата МСК} — одна заявка в сутки. Принятое ограничение: счётчика отказов и паузы, как у доступа, нет. Основание: канон и Р-20 о хранении молчат; pause-2 §6 («purpose в 0018») по коду не выполнено.
- ШТАБ 17.11 (К-5, обязательно): фаза muted или erased → restart_paid не пишется; Автору отказ в теме, участнику ничего. Причина: проектор v6 проверяет только block_lives и stage_no.
- ШТАБ 17.11 (К-5): сообщение участнику бот шлёт сам после COMMIT — у app_bot нет INSERT в outbox (0009). Это отступление от pause-2 §5.
- ШТАБ 17.11 (К-5): различение промокода — по состоянию (вердикт доступа NOTHING → tg_user_registry → participant_state).
- ШТАБ 17.11 (К-5): actor = 'bot', actor_role = 'owner'.

## 4. Выдержки
- Проектор v6 (сверено ШТАБом): restart_paid — payload dict (содержимое не читается), at DEFAULT now(); D считается из at. Применяется при block_lives и stage_no NOT NULL, фазу НЕ проверяет.
- 0010 access_grants: PK tg_user_id; колонки purpose нет; UPSERT ON CONFLICT (tg_user_id). Вторая строка «restart» невозможна (pause-2 §9, ответ по коду).
- 0007, 0005, права app_bot — как в docs/tasks/bot-life-1.md §4.
- Ответы на pause-2 §9 (по коду): (1) UNIQUE access_grants = PK tg_user_id, строки restart нет и не будет — вариант В. (2) Промокод доступа отличается от рестарта по состоянию: access.submit_request/classify при granted дают NOTHING, и тогда бот ищет участника с block_lives. (3) Гейт Р-2 first-launch не меняется: в access_grants только строки доступа.

## 5. ЧТО ПРОЧИТАТЬ
AGENT-BRIEF.md 17,1; DECISIONS.md 7,7; apps/bot/bot/access_handlers.py 10,4 (on_private, кнопки acc, after_commit); apps/bot/bot/access.py 15,2; apps/bot/bot/life.py (из T6b: замок, has_flag) ≈ 8; apps/bot/bot/app.py 8,9; apps/bot/bot/texts.py 9,8; apps/bot/tests/test_access.py 21,8. Чтение КОДЕРА ≈ 99 КБ + карточка.

## 6. Файлы
- создать: apps/bot/bot/restart.py (SQL, условия), apps/bot/bot/restart_handlers.py (кнопки rst), apps/bot/tests/test_restart.py
- изменить: apps/bot/bot/access_handlers.py (ветка в on_private), apps/bot/bot/app.py (роутер restart при access_enabled), apps/bot/bot/texts.py (заглушки RESTART_*)

## 7. Контракт
Заявка (личка, on_private). Ветка срабатывает там, где итог для пользователя — access.NOTHING (granted); раньше в этом месте была тишина.
    SELECT pid, short_no FROM tg_user_registry WHERE tg_user_id = %s AND tombstoned_at IS NULL
    SELECT lifecycle_phase, status_flags, stage_no FROM participant_state WHERE pid = %s
restart.eligible(phase, flags, stage_no) возвращает True, если has_flag(flags, "block_lives"), stage_no IS NOT NULL и фаза не muted и не erased. Иначе тишина, как раньше. Если True — одна транзакция:
    SELECT pg_advisory_xact_lock(hashtextextended('participant:' || %s, 0))
    INSERT INTO idempotency_keys (key, kind, result_ref) VALUES (%s, 'restart_req', NULL) ON CONFLICT (key) DO NOTHING
key = "restart_req:{pid}:{YYYY-MM-DD по Europe/Moscow}". При rowcount 0 → участнику RESTART_ALREADY_TODAY. Иначе — внутри транзакции отправка в WORK_GROUP_ID / ACCESS_ADMIN_TOPIC_ID сообщения RESTART_REQUEST (номер участника, Этап, кодовое слово — html.escape) с кнопками:
    [Выдать рестарт] "rst:g:<short_no>"    [Запретить] "rst:d:<short_no>"
Сбой отправки → откат (ключ не сохраняется) → RESTART_TRY_LATER. Успех → COMMIT → участнику RESTART_REQUEST_SENT. Кодовое слово в БД и в лог не попадает.

Решение (кнопки rst; принимаются только из админ-темы и от ACCESS_ADMIN_IDS, иначе answer без текста + лог). mid = callback.message.message_id. Одна транзакция:
    SELECT pid, tg_user_id FROM tg_user_registry WHERE short_no = %s AND tombstoned_at IS NULL
    SELECT pg_advisory_xact_lock(hashtextextended('participant:' || %s, 0))
    INSERT INTO idempotency_keys (key, kind, result_ref) VALUES (%s, 'restart', %s) ON CONFLICT (key) DO NOTHING
key = "restart:{pid}:{mid}", result_ref = 'granted' или 'denied'. При rowcount 0 → SELECT result_ref; в тему RESTART_ALREADY (с итогом), кнопки снять.
- rst:g — повторная проверка под замком:
    SELECT lifecycle_phase, status_flags, stage_no FROM participant_state WHERE pid = %s
  Участник не найден или стёрт (tombstoned) → RESTART_REFUSED_STATE. Фаза muted или erased → RESTART_REFUSED_PHASE. Нет block_lives или stage_no NULL → RESTART_REFUSED_STATE. Во всех трёх случаях — откат (ключ не пишется), отказ Автору в теме, кнопки снять, участнику ничего. Иначе:
    INSERT INTO participant_events (pid, kind, payload, actor, actor_role) VALUES (%s, 'restart_paid', %s, 'bot', 'owner')
  payload = Jsonb({"admin_message_id": mid}). После COMMIT: к заявке дописать RESTART_DONE, кнопки снять; участнику send_message(tg_user_id, RESTART_GRANTED).
- rst:d — ключ с 'denied', событие не пишется. После COMMIT: дописать RESTART_DENIED_ADMIN, кнопки снять; участнику RESTART_DENIED.
Ошибка Telegram после COMMIT — только лог. Ошибка БД → answer RESTART_TRY_LATER. Логи — без слова, tg_user_id, pid, номера.

## 8. БД
Миграций нет. access_grants, гейт Р-2 и api не меняются.

## 9. Тесты (apps/bot/tests/test_restart.py; FakeConn)
- eligible: block_lives + stage → True; нет флага, stage NULL, muted, erased → False;
- заявка: granted + текст + eligible → ключ restart_req с датой МСК (граница суток 21:00 UTC) → SendMessage в тему с двумя кнопками, слово экранировано; повтор за сутки → RESTART_ALREADY_TODAY, в теме ничего; не eligible → тишина, SQL без INSERT; сбой отправки → ключа нет (откат), RESTART_TRY_LATER;
- выдача: порядок SQL; payload {"admin_message_id": mid}; actor 'bot', 'owner'; участнику RESTART_GRANTED; нет RETURNING;
- muted → события нет, ключа нет, отказ в теме, SendMessage участнику нет (обязательно);
- erased → то же (обязательно);
- tombstoned (FIND вернул None) → отказ, события нет;
- запрет → ключ denied, события нет, участнику RESTART_DENIED; после запрета [Выдать] → RESTART_ALREADY;
- чужой чат или не whitelist → answer без текста, БД не вызывалась;
- access_grants: ни одного SQL к access_grants в сценариях рестарта.
check.sh: bash tools/check.sh bot. Только CI: нет.
Задетые тесты: apps/bot/tests/test_access.py — проверить сценарии лички с вердиктом granted. FakeConn на FIND по tg_user_id вернёт None → тишина, правка не ожидается. Если тест сверяет conn.log целиком — дополнить список строкой restart.FIND_BY_TG. Остальные — как в bot-life-1 §9 (ШТАБ: grep до промпта).

## 10. Живая проверка (после мержа T6b и T6c)
Выкат только bot, после T6b; миграций нет; api не пересобирать. Аккаунт — А3. А1 не трогать.
Не проверено: как у А3 появляется флаг block_lives (по sleep-1 Ф2 проектор при 0 жизней ставит sleeping и флаги не трогает). ШТАБ указывает способ до проверки.
1. А3 с block_lives пишет боту промокод → в админ-теме заявка с кнопками; А3 получил RESTART_REQUEST_SENT.
2. Повтор в тот же день → RESTART_ALREADY_TODAY.
3. [Выдать рестарт] → после проектора /card А3: 3 жизни, Этап прежний, модуль 1, день 1; кнопки 04:00 и дедлайн 00:00 — со следующих 00:00. А3 получил RESTART_GRANTED.
4. Логи: без кодового слова, tg_user_id, pid.

## 11. Запреты
AGENT-BRIEF §3. Не трогать access_grants и гейт Р-2; не писать participant_state и outbox. Миграций и правок api/projector нет. Кодовое слово не хранить и не логировать. RETURNING нет. Тексты — заглушки.

## 12. Готово
Заявка, выдача и запрет работают; при muted и erased событие не пишется (тесты есть); тесты и check.sh bot зелёные.

## 13. Оценка
≈ 260 строк кода, 280 строк тестов, задетый test_access.py ≈ 80 (У12). Кредиты ≈ 700, стоп 1 050. Часы Автора ≈ 0,7.

## 14. РЕВЬЮЕР: да
pause-2 §6; поток доступа Р-2 (промокод), оплата в личке (Р-1), запись app_bot в participant_events (B-3).

## Канон и решения
(а) Используется: Р-2, Р-20 (DECISIONS.md); механика — через pause-2 §5 и sleep-1 §2 Р7.
(б) Противоречий с DECISIONS.md нет. pause-2 §6 («purpose в 0018») — ошибка исследования, а не канона; закрыта вариантом В.
(в)–(г) Правок канона нет.
