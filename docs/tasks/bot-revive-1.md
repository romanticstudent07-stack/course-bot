# T7b bot-revive-1 — команда /revive: revive_by_author от Автора
Hash main f87bc27. Основа: docs/research/pause-2.md §5, §8 А2; docs/tasks/api-revive-1.md §7.1 (контракт события, проектор v7 в main, #245); образец оболочки — bot-life-1. Правило К — docs/process/CANON-CHECK.md. Сначала прочитай docs/decisions/DECISIONS.md целиком.

## 1. Паспорт
- id: T7b bot-revive-1 · PR: «bot-revive-1: /revive — revive_by_author (+ миграция 0020)» · ветка: feat/bot-revive-1
- Режим: Р1 (Агент). Зависит от: db-revive-0020 (тот же промпт Агента, миграция первым коммитом); api-revive-1 (#245, в main). Область — бот.

## 2. Цель
Автор в Рабочей группе выполняет /revive для участника с block_lives. Шаг 1 — предпросмотр без записи: позиция, точка отката, lives_returned, сколько жизней станет. Шаг 2 — одна транзакция под замком: проверки, подсчёт lives_returned по life_writeoffs, INSERT revive_by_author. Жизни, флаг и день меняет проектор v7; participant_state бот не пишет. После COMMIT бот пишет участнику сам.

## 3. Решения (метка К-6)
- Р-20: «из block_lives — … revive (min(3, 1 + возврат §2.6), команда бота, после 0019)» [Автор].
- pause-2 §8 А2: «откат на позицию, выбранную Автором (обычно день 1 текущего модуля) … прошлые Этапы не трогать» [Автор 15.11].
- Ш1 = А: lives_returned считает бот (SELECT life_writeoffs под замком, в транзакции INSERT) [ШТАБ]. Гонки нет: при block_lives life_ops участника пропускает [ШТАБ, по коду life_ops.py].
- Правило подсчёта (§7.4) — канон 02 §2.6 и §2.4, вопроса К-4 нет [ШТАБ 18.11, канон проверен].
- ШТАБ 18.11 (К-5, приняты решения З1): имя /revive; аргумент М.Д в текущем Этапе; callback rvb:y:<short_no>:<m>:<d>:<op16> и rvb:n, lives_returned в callback не кладётся; порядок отказов §7.3; ключ revive:{pid}:{op}, kind 'revive'; устаревание 1 ч без БД; LOCK, has_flag, FIND берутся из life.py; Ш3 принят [ШТАБ, К-5].
- Почему аргумент, а не кнопки: тот же вид «М.Д», что у /revert в реестре, без лишнего шага и клавиатуры [ШТАБ-тех].
- muted/erased → событие не пишется (проектор v7 фазу не проверяет), как в bot-restart-1 [ШТАБ, по коду restart.py].
- Участнику — только при DONE, после COMMIT, через send_message бота: у app_bot нет INSERT в outbox [ШТАБ, по коду].

## 4. Выдержки (КОДЕР архитектуру не читает)
- 02 §2.6: «Откат внутри текущего Этапа: возвращаются только жизни, списанные на днях ≥ точки отката (частичный возврат). … Принцип единый: «возвращаем жизни, потраченные в зоне, которую отматываем».» YAML: within_stage «возврат жизней, списанных на днях >= точки отката».
- 02 §2.4: «Рестарт = всё с начала … полные 3 жизни заново, все счётчики и прогресс обнуляются». Поэтому restart_paid — тоже точка отсчёта :after.
- api-revive-1 §7.1: kind "revive_by_author"; actor 'bot', actor_role 'owner'; payload {"target": {"stage_no", "module_no", "day_no"}, "lives_returned": int}; поля target — int (не bool), ≥ 1; lives_returned — int, ≥ 0. Проектор пропускает: нет block_lives, позиция NULL, другой Этап, (module, day) target больше текущей позиции; target, равный позиции, допустим; lives = min(3, 1 + lives_returned).
- 0019: app_bot — SELECT (pid, event_id, stage_no, module_no, day_no) на life_writeoffs. Бэкфилла нет: по списаниям до 0019 revive даёт только +1. /life −N в журнал не пишется.
- Права app_bot после 0020: participant_state SELECT (pid, lifecycle_phase, status_flags, stage_no, module_no, day_no, lives, tz) (0013); tg_user_registry SELECT (pid, tg_user_id, tombstoned_at, short_no) (0009, 0011, 0013); idempotency_keys INSERT (key, kind, result_ref), SELECT (key, result_ref) (0018); participant_events INSERT (pid, kind, payload, actor, actor_role) (0018) + SELECT (id, pid, kind) (0020). RETURNING не используется.
- 0007 idempotency_keys: kind text NOT NULL, ttl DEFAULT '1 hour'; CHECK на kind в выдержке bot-life-1 §4 нет (ШТАБ сверяет по 0007).
- Граница дня в модуле: контент лежит в apps/api/content, в образ бота он не попадает (apps/bot/Dockerfile: COPY из apps/bot) → не проверяется, риск (§7.6).

## 5. ЧТО ПРОЧИТАТЬ (Агент; общее с db-revive-0020)
AGENT-BRIEF.md 17,1; docs/decisions/DECISIONS.md 7,7; эта карточка ≈ 11; apps/bot/bot/life.py 8,0; apps/bot/bot/life_handlers.py 7,4; apps/bot/bot/app.py 8,9; apps/bot/bot/texts.py 13,7; apps/bot/tests/test_life.py ≈ 20 (FakeConn — образец; ШТАБ уточнит размер). Итого ≈ 94 КБ; вместе с db-revive-0020 ≈ 120 КБ (≤ 140).

## 6. Файлы
- Создать: apps/bot/bot/revive.py (SQL, разбор, check, count_returned, preview, apply); apps/bot/bot/revive_handlers.py (роутер); apps/bot/tests/test_revive.py.
- Изменить: apps/bot/bot/app.py — build_revive_router в ветке config.card_enabled, рядом с /life (по коду life_handlers.py, docstring); apps/bot/bot/texts.py — REVIVE_*.
- life.py, restart.py не менять.

## 7. Контракт
7.1 Команда — только в Рабочей группе (тема любая) и только от ACCESS_ADMIN_IDS; иначе игнор и лог без Bot API и БД (как у /life).
    /revive                    ответом на пост бота; target = день 1 текущего модуля
    /revive 2.3                ответом на пост бота; target = модуль 2, день 3 текущего Этапа
    /revive #NNNNNN
    /revive #NNNNNN 2.3
Разбор: fullmatch «(?:#(\d+))?\s*(?:(\d{1,3})\.(\d{1,3}))?» после strip. М и Д — 1…999, 0 → REVIVE_USAGE. Нет номера и нет reply → USAGE. Номер больше bigint → NOT_FOUND. Reply — как life._target (card.number_from_reply, служебный reply темы не считается).
7.2 SQL (только %s):
    FIND, LOCK — из bot.life
    STATE     = SELECT lifecycle_phase, status_flags, stage_no, module_no, day_no FROM participant_state WHERE pid = %s
    AFTER     = SELECT coalesce(max(id), 0) FROM participant_events WHERE pid = %s AND kind IN ('revive_by_author', 'restart_paid')
    WRITEOFFS = SELECT event_id, stage_no, module_no, day_no FROM life_writeoffs WHERE pid = %s AND event_id > %s ORDER BY event_id
    KEY       = INSERT INTO idempotency_keys (key, kind, result_ref) VALUES (%s, 'revive', %s) ON CONFLICT (key) DO NOTHING
    EVENT     = INSERT INTO participant_events (pid, kind, payload, actor, actor_role) VALUES (%s, 'revive_by_author', %s, 'bot', 'owner')
7.3 check(phase, flags, stage, module, day, target) → код или None, порядок:
1. phase None (нет строки) → NOT_FOUND; 2. muted/erased → REFUSE_PHASE; 3. нет block_lives (has_flag) → REFUSE_NOT_BLOCKED («для прибавки — /life»); 4. stage, module или day NULL → REFUSE_NO_POSITION; 5. target.stage_no ≠ stage → REFUSE_STAGE; 6. (tm, td) > (module, day) → REFUSE_AHEAD. Равенство допустимо.
target.stage_no — всегда stage, прочитанный в той же транзакции. Поэтому п.5 в потоке недостижим: это защита чистой функции, её проверяет unit-тест.
7.4 count_returned(rows, target) — чистая функция: число строк, у которых (stage_no, module_no, day_no) >= target при сравнении кортежей. Строки уже отобраны по event_id > :after. Строки прошлых Этапов в счёт не попадают сами. Результат — int ≥ 0, без обрезки: min(3, 1 + x) делает проектор.
7.5 Шаг 1 — preview(conn, short_no, mt, dt) без записи и без замка: FIND → STATE → (target = (stage, mt or module, dt or 1)) → check → AFTER → WRITEOFFS → count. При отказе — текст отказа в тему. Иначе REVIVE_PREVIEW (номер; позиция сейчас «Э.М.Д»; откат «Э.М.Д»; lives_returned x; «станет min(3, 1 + x)») и кнопки:
    [Подтвердить]  rvb:y:<short_no>:<m>:<d>:<op>     (≤ 50 байт; тест ≤ 64)
    [Отмена]       rvb:n
op = life.new_op(). При разборе callback m и d — 1…999.
7.6 Шаг 2 — [Подтвердить]. Проверки чата и whitelist — как у /life; не прошли → answerCallbackQuery без текста + лог.
1. message.date старше life.STALE_SECONDS → REVIVE_STALE, кнопки снять, в БД не ходить.
2. apply(conn, short_no, m, d, op) → Result(code, tg_user_id), одна транзакция: FIND → LOCK(str(pid)) → STATE → check (отказ → откат) → AFTER → WRITEOFFS → x = count_returned → KEY (key "revive:{pid}:{op}", result_ref str(x); rowcount 0 → ALREADY, события нет) → EVENT, payload Jsonb({"target": {"stage_no": s, "module_no": m, "day_no": d}, "lives_returned": x}), все значения — int.
3. После COMMIT: к предпросмотру дописать итог (REVIVE_DONE «записано, применит проектор»), кнопки снять. Только при DONE: bot.send_message(tg_user_id, REVIVE_USER). Ошибка Telegram — WARNING с именем класса.
[Отмена] → REVIVE_CANCELLED, БД не трогать. Ошибка БД → REVIVE_TRY_LATER.
Риск: день target внутри модуля не проверяется — контента у бота нет. В текущем модуле «не впереди» не пускает на несуществующий день; в прошлых модулях Автор отвечает за номер дня сам.
7.7 Ш3 (риск принят ШТАБом): :after берёт любое событие revive_by_author или restart_paid, включая неприменённое или пропущенное проектором. Такое событие сдвигает точку отсчёта, и следующий revive может вернуть меньше. Отказы бота до записи сужают риск, но не закрывают его.
7.8 Логи: без tg_user_id, pid, short_no, target — только код результата.

## 8. БД
Миграция — db-revive-0020 (первый коммит этого же PR). Здесь таблиц и прав не меняется.

## 9. Тесты — apps/bot/tests/test_revive.py (без сети и Postgres, FakeConn по образцу test_life.py; ID 5021–5099)
- разбор: пусто, «2.3», «#123456», «#123456 2.3», @BotName, «0.1», «2.0», «2.», «abc», номер > bigint;
- check: каждый код и порядок (muted с block_lives → PHASE; active без флага → NOT_BLOCKED; block_lives при NULL → NO_POSITION; другой stage → STAGE; (2,3,5) и target (2,3,6), (2,4,1) → AHEAD; равенство → None; target (2,1,1) → None);
- count_returned: строки (2,2,4), (2,3,1), (2,3,5), (1,5,5) при target (2,3,1) → 2; при target (2,3,5) → 1; пусто → 0; день-цель включительно;
- предпросмотр: в SQL нет INSERT и LOCK; по умолчанию target (stage, module, 1); две кнопки; длина callback при short_no на 19 цифр и m = d = 999 ≤ 64;
- подтверждение: порядок SQL (FIND, LOCK, STATE, AFTER, WRITEOFFS, KEY, EVENT); параметр WRITEOFFS — значение из AFTER; payload по §7.6, type is int у всех полей; actor 'bot', 'owner'; RETURNING нет нигде;
- повтор (rowcount 0) → ALREADY, нет EVENT и нет SendMessage участнику;
- отказ на шаге 2 → нет KEY и EVENT; muted → REFUSE_PHASE;
- DONE → ровно один send_message участнику после транзакции; ошибка send_message → итог DONE в теме, лог;
- устаревший предпросмотр → STALE, connect не вызывался;
- чужой чат или не whitelist → игнор; кнопка → answer без текста;
- роутер не подключён при card_enabled = False.
Цели: bash tools/check.sh bot (и api — для db-revive-0020). Только CI: тесты с БД из db-revive-0020.
Задетые тесты (кандидаты; ШТАБ сверяет по коду до промпта):
- grep -rn "include_router\|build_.*_router" apps/bot/tests — тесты, сверяющие список роутеров целиком (test_bot.py, test_access.py);
- grep -rn "rvb:\|\"revive\"\|'revive'" apps/bot apps/api — пересечение префикса и kind ключа;
- test_life.py, test_restart.py — не задеты (life.py и restart.py не меняются).

## 10. Живая проверка (после выката 0020 и бота)
Аккаунт А2. Подготовка: /life #<А2> −N до 0 → после проектора у А2 block_lives (/card).
1. /revive #<А2> → предпросмотр: откат на день 1 текущего модуля, lives_returned 0 (/life −N в журнал не идёт), «станет 1» → [Подтвердить] → «записано, применит проектор»; в личку А2 пришла заглушка; после проектора /card — 1 жизнь, день 1 модуля.
2. Повторно /revive #<А2> → REFUSE_NOT_BLOCKED.
3. /revive #<А2> 9.9 при block_lives → REFUSE_AHEAD (если позиция ниже).
4. Логи бота: нет tg_user_id, pid, номера.

## 11. Запреты
AGENT-BRIEF §3. Не писать participant_state, outbox, life_writeoffs; не менять life.py, restart.py, api, projector; RETURNING не использовать; lives_returned не обрезать и не класть в callback; тексты — только «[заглушка] …»; реальных ID нет.

## 12. Готово
/revive работает в два шага; отказы до записи; на один op — одно событие; подсчёт по §7.4; участнику — только при DONE; check.sh bot и api зелёные.

## 13. Оценка
≈ 300 строк кода + 300 строк тестов → ≈ 650; задетые 0–2 × 60–100 → ≈ 800. Вместе с db-revive-0020 (≈ 200) промпт ≈ 1 000, стоп 1 500 (1,5 ×). Часы Автора ≈ 0,7 (мерж, выкат 0020 и бота, живая проверка).

## 14. РЕВЬЮЕР: да
Бот пишет событие от app_bot и меняет жизни; в том же PR — GRANT (B-3).

## Канон и решения
(а) Используется: 02 §2.6 (возврат «≥ точки отката»), 02 §2.4 (рестарт обнуляет — restart_paid в :after); Р-20; pause-2 §5, §8 А2; build/bot-commands-registry.yaml (lifecycle).
(б) 02 §2.6, ветка «откат в прошлый Этап → все 3 жизни» к revive не относится: revive только внутри текущего Этапа (pause-2 §8 А2 [Автор]; проектор v7 пропускает другой Этап). 02 §2.4 «повторная оплата» снята Р-20.
(в) DOCS · architecture/build/bot-commands-registry.yaml: в группу lifecycle после последней записи добавить
    - name: "/revive"
      role: owner
      hard_confirm: true
      audit_layer: как у /life (ШТАБ сверит)
      surface: work_group_reply
    params — по образцу /revert, если поле есть. Заголовок «реестр 34 команд» → 35; total_declared: 34 → 35 (комментарий «+/revive, bot-revive-1»); «5.1. Жизненный цикл (8)» → (9); строку «Итого: 8 + 5 + 3 + 6 + 3 + 9 = 34» заменить на «Итого: 9 + 5 + 3 + 6 + 3 + 9 = 35». Число 34 в appendix/C-registries.md раздел 5 — не проверено, ШТАБ сверит. Агент docs/architecture не трогает; PR в DOCS и sync — до промпта.
(г) Других правок канона нет.
