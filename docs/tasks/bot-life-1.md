# T6b bot-life-1 — команда /life +N | -N (двухшаг, life_op author_cmd)
Hash main bd27f44. Основа — docs/research/pause-2.md §5, §6; docs/research/sleep-1.md §2 Р4. Правило К — docs/process/CANON-CHECK.md. Сначала прочитай docs/decisions/DECISIONS.md целиком.

## 1. Паспорт
- id: T6b bot-life-1 · PR: «bot-life-1: /life +N | -N — life_op author_cmd» · ветка: feat/bot-life-1
- Режим: Р1 (Агент). Зависит от: T6a-1 api-sleep-1a (projector v5) и T6a-2 api-sleep-1b (v6) — оба в main. Миграций нет. Область — бот.

## 2. Цель
Автор в Рабочей группе меняет жизни участника: /life +N или /life -N (N = 1…3). Шаг 1 — предпросмотр с кнопками. Шаг 2 — [Подтвердить]: бот проверяет причины отказа и пишет в participant_events событие life_op {delta, reason 'author_cmd'}. Жизни меняет проектор (v5); participant_state бот не пишет.

## 3. Решения (метка К-6)
- ШТАБ 16.11 Ш1: reason = 'author_cmd' [ШТАБ, К-5; проектор v5].
- ШТАБ 17.11: отказы с текстом — до записи события, причины те же, что у проектора: lives_zero_use_revive (+N при 0 или при block_lives: Автору «используй revive», участнику ничего), life_above_max, life_below_zero; фаза не onboarding и не active → отказ [ШТАБ, К-5; sleep-1 §2 Р4].
- ШТАБ 17.11 (З2, в.2): после /life участнику ничего; Автору — «записано, применит проектор» [ШТАБ, К-5; R-2026-11-15 §2 А2: «участнику ничего» прямо сказано только для отказа при 0].
- ШТАБ 17.11 (З2, в.3): [Подтвердить] позже 1 ч от даты предпросмотра → отказ «предпросмотр устарел, повтори /life»; ttl ключа — DEFAULT 1 ч в БД (0007), бот его не пишет [ШТАБ, К-5].
- ШТАБ 17.11 (З2): actor = 'bot', actor_role = 'owner' [ШТАБ, К-5; CHECK на них в 0005 нет; реестр: /life owner].
- pause-2 §5: замок participant:pid, idempotency life_op:{pid}:{client_op_id}, TTL 1 ч [исследование, канон через pause-2].

## 4. Выдержки (КОДЕР архитектуру не читает)
- build/bot-commands-registry.yaml, lifecycle: /life — role owner, hard_confirm true, surface work_group_reply (pause-2 §1).
- Проектор v6 (сверено ШТАБом по bd27f44). life_op author_cmd: payload {"delta": int, "reason": "author_cmd"}; delta — int (не bool), ≠ 0, |delta| ≤ 3; day_started_at не читается. Применяется только в фазе onboarding/active и при 0 ≤ lives + delta ≤ 3; прибавка — только при lives > 0 и без block_lives. Если условие не выполнено, проектор молча пропускает событие, поэтому бот отказывает сам и заранее.
- 0005 participant_events: pid uuid NOT NULL FK, kind text NOT NULL, payload jsonb NOT NULL, at DEFAULT now(), actor text NOT NULL, actor_role text NOT NULL.
- 0007 idempotency_keys: key text PK (CHECK key <> ''), kind text NOT NULL, ttl interval DEFAULT '1 hour', result_ref text.
- Права app_bot. На participant_state: SELECT (pid, lifecycle_phase, status_flags, stage_no, module_no, day_no, lives, tz) (0013). На tg_user_registry: SELECT (pid, tg_user_id, tombstoned_at, short_no, created_at) (0009, 0011, 0013). На participant_events: INSERT (pid, kind, payload, actor, actor_role) + USAGE participant_events_id_seq (0018). На idempotency_keys: INSERT (key, kind, result_ref) + SELECT (key, result_ref) (0018). RETURNING запрещён (SELECT на participant_events нет).

## 5. ЧТО ПРОЧИТАТЬ
AGENT-BRIEF.md 17,1; docs/decisions/DECISIONS.md 7,7; apps/bot/bot/card_handlers.py 6,0 (образец: whitelist, reply, _reply); apps/bot/bot/card.py 8,4 (FIND по short_no, number_from_reply); apps/bot/bot/access.py 15,2 (connect, образец замка); apps/bot/bot/app.py 8,9; apps/bot/bot/texts.py 9,8; apps/bot/tests/test_access.py 21,8 (FakeConn, _feed). Чтение КОДЕРА ≈ 95 КБ + карточка.

## 6. Файлы
- создать: apps/bot/bot/life.py (SQL, разбор, check, has_flag), apps/bot/bot/life_handlers.py (роутер), apps/bot/tests/test_life.py
- изменить: apps/bot/bot/app.py (подключить роутер при config.card_enabled, рядом с /card), apps/bot/bot/texts.py (заглушки LIFE_*)

## 7. Контракт
Команда принимается только в Рабочей группе WORK_GROUP_ID (тема любая) и только от ACCESS_ADMIN_IDS. В остальных случаях — игнор и лог, без вызовов Bot API и БД (как у /card).
    /life +N            ответом на пост бота (номер — card.number_from_reply)
    /life #NNNNNN +N
    /life #NNNNNN -N
N = 1…3, знак обязателен; Command учитывает @BotName. Неверный формат (нет знака, 0, N > 3, мусор, нет ни номера, ни reply) → LIFE_USAGE. Номер больше bigint → LIFE_NOT_FOUND.

Шаг 1 — предпросмотр, без записи: FIND → STATE → check. Отказ → текст отказа в ту же тему. Иначе — LIFE_PREVIEW (номер; жизни сейчас → после) с кнопками:
    [Подтвердить]  callback_data "life:y:<short_no>:<delta со знаком>:<op>"
    [Отмена]       callback_data "life:n"
op (client_op_id) = uuid4().hex[:16]. Длина callback_data ≤ 64 байт — проверяется тестом.

Шаг 2 — [Подтвердить]. Проверки чата и whitelist те же; не прошли → answerCallbackQuery без текста + лог.
1. callback.message.date старше 1 ч → LIFE_STALE, кнопки снять, в БД не ходить.
2. Одна транзакция (соединение access.connect; async with conn.transaction()):
    SELECT pid, tg_user_id FROM tg_user_registry WHERE short_no = %s AND tombstoned_at IS NULL
    SELECT pg_advisory_xact_lock(hashtextextended('participant:' || %s, 0))
    SELECT lifecycle_phase, status_flags, lives FROM participant_state WHERE pid = %s
   В замок pid передаётся как text. check вернул код → откат, текст отказа, кнопки снять.
    INSERT INTO idempotency_keys (key, kind, result_ref) VALUES (%s, 'life_op', %s) ON CONFLICT (key) DO NOTHING
   key = "life_op:{pid}:{op}", result_ref = str(delta). rowcount 0 → LIFE_ALREADY, событие не пишется.
    INSERT INTO participant_events (pid, kind, payload, actor, actor_role) VALUES (%s, 'life_op', %s, 'bot', 'owner')
   payload = psycopg Jsonb({"delta": delta, "reason": "author_cmd"}), delta — int.
3. После COMMIT: к предпросмотру дописать LIFE_DONE («записано, применит проектор»), кнопки снять. Участнику — ничего. Ошибка Telegram после COMMIT — только лог.
[Отмена]: кнопки снять, дописать LIFE_CANCELLED, БД не трогать. Ошибка БД на любом шаге → LIFE_TRY_LATER.

check(phase, flags, lives, delta) → код или None. Порядок проверок:
1. участника нет, строки participant_state нет или lives NULL → LIFE_NOT_FOUND;
2. фаза muted или erased → LIFE_REFUSE_PHASE;
3. delta > 0 и (lives == 0 или has_flag(flags, "block_lives")) → LIFE_REFUSE_REVIVE («используй revive»);
4. фаза не onboarding и не active → LIFE_REFUSE_PHASE;
5. lives + delta > 3 → LIFE_REFUSE_ABOVE_MAX; lives + delta < 0 → LIFE_REFUSE_BELOW_ZERO.
Пункт 3 идёт раньше пункта 4 намеренно: при 0 жизней проектор ставит фазу sleeping, и Автор должен увидеть «используй revive», а не «фаза». has_flag работает для list и dict, для None возвращает False (тип status_flags в окне не сверялся). Принятое ограничение: бот видит participant_state до применения проектором прошлого события. Поэтому два быстрых /life могут оба пройти check бота; второе тогда отсечёт проектор.
Логи: без tg_user_id, pid, short_no — только код результата.

## 8. БД
Миграций нет. Таблицы и права не меняются.

## 9. Тесты (apps/bot/tests/test_life.py; без сети и Postgres; FakeConn по образцу test_access)
- разбор: +1, -3, #123456 +2, @BotName, без знака, 0, +4, мусор, номер > bigint;
- check: каждый код и порядок проверок — sleeping + 0 жизней + delta > 0 → REVIVE; block_lives + delta > 0 → REVIVE; muted и erased → PHASE; 3 + 1 → ABOVE_MAX; 1 − 2 → BELOW_ZERO; onboarding, 2 − 1 → None;
- has_flag: list, dict, None;
- предпросмотр: в SQL нет INSERT; две кнопки; длина callback_data ≤ 64;
- подтверждение: порядок SQL (FIND, замок, STATE, ключ, событие); payload {"delta": -1, "reason": "author_cmd"}; type(delta) is int; actor 'bot', actor_role 'owner'; нигде нет RETURNING;
- повтор (rowcount 0 на ключе) → LIFE_ALREADY, события нет;
- отказ на шаге 2 → нет ни ключа, ни события;
- устаревший предпросмотр → LIFE_STALE, connect не вызывался;
- чужой чат или не whitelist: команда → игнор; кнопка → answer без текста;
- SendMessage участнику нет ни в одном сценарии;
- роутер не подключён при card_enabled = False.
check.sh: bash tools/check.sh bot. Только CI: нет.
Задетые тесты: не ожидается. Поиск: test_bot.py — общих списков команд и кнопок нет (только /start, конфиг, webhook). test_access.py — роутеры подключаются через build_dispatcher; новый роутер ловит только Command("life") и callback "life:", личку не ловит. ШТАБ до промпта: grep -rn "include_router\|callback_data" apps/bot/tests (test_card*, test_support, test_outbox, test_render в окне не читались).

## 10. Живая проверка (после мержа)
Выкат одним разом: bot + projector v5 + v6 (уже в main); миграций нет; api не пересобирать. Аккаунт — А2 (фаза onboarding/active, 3 жизни). А1 не трогать.
1. Рабочая группа: /life #<номер А2> -1 → предпросмотр 3 → 2 → [Подтвердить] → «записано, применит проектор». После цикла проектора /card А2 показывает 2 жизни. В личку А2 ничего не пришло.
2. /life #<номер А2> +2 → LIFE_REFUSE_ABOVE_MAX, кнопок нет.
3. /life #<номер А2> +1 → [Подтвердить] → после проектора 3 жизни.
4. Логи бота: нет tg_user_id, pid и номера.

## 11. Запреты
AGENT-BRIEF §3. Не писать participant_state, outbox, access_grants. Миграций и правок api и projector нет. RETURNING не использовать. Тексты — только заглушки «[заглушка] …» в texts.py. Участнику не писать. Реальных ID в тестах и логах нет.

## 12. Готово
/life работает в два шага; отказы — до записи; на один client_op_id — одно событие; тесты и check.sh bot зелёные.

## 13. Оценка
≈ 330 строк кода и 300 строк тестов (У12). Кредиты ≈ 600, стоп 900. Часы Автора ≈ 0,5 (мерж, выкат, живая проверка).

## 14. РЕВЬЮЕР: да
pause-2 §6. Команда Автора меняет жизни; бот пишет в participant_events от роли app_bot (B-3: права 0018).

## Канон и решения
(а) Используется: build/bot-commands-registry.yaml (/life); Р-20 и механика /life — через pause-2 §5 и sleep-1 §2 Р4 (docs/architecture в окне не читался).
(б) Противоречий с DECISIONS.md нет.
(в)–(г) Правок канона нет.
