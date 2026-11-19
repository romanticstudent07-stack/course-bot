# T4 bot-pause-1 — уведомления о паузе и кнопки Автора (П.2)
Hash main c0c5288. Область: бот. Правило К — docs/process/CANON-CHECK.md. Сначала прочитай docs/decisions/DECISIONS.md целиком.
Контракт T3/T4 — docs/tasks/api-pause-1a.md §5 (нормативный, не менять) с поправкой api-pause-3 (решение Автора 18.11, §3).

## 1. Паспорт
- id: T4 bot-pause-1 · PR: «bot-pause-1: карточка заявки паузы, кнопки Автора, уведомления» · ветка: feat/bot-pause-1, после коммита db-pause-0021.
- Режим: Р1 (Агент). Зависит от: 0021_bot_pauses_select (первый коммит ветки) и api-pause-3 (в main). Без api-pause-3 в main не стартовать.

## 2. Цель
Участник подаёт заявку на паузу в Mini App (T3). Бот:
- выкладывает Автору карточку заявки с кнопками ✅/✖ (один тап) и пишет событие решения;
- уведомляет участника о смене статуса;
- шлёт Автору алерт, если пауза началась без его решения.
Статус, флаги и бюджет меняет только проектор, старт и конец — часы pause_ops. Бот пишет только событие и свои ключи.

## 3. Решения (К-6)
- Р1. Молчание Автора до start_at = авто-разрешение: часы переводят requested → active напрямую. Позднее pause_approved не отменяет заявку. Р14 api-pause-1a (сгорание, not_approved) отменён [Автор 18.11; канон 02 П.2; исправление — api-pause-3].
- Р2. Решение пишется только при status = 'requested' AND now() < start_at. now() берётся из БД в той же транзакции: at события = DEFAULT now(), а права на колонку at у бота нет [api-pause-1a §5; ПРОЕКТИРОВЩИК-тех].
- Р3. Один тап: ✅ Одобрить / ✖ Отклонить, без предпросмотра [канон 02 П.2; ШТАБ З2 Ш4].
- Р4. Событие pause_approved или pause_rejected, payload {"pause_id": <int>} (ровно по api-pause-1a §5), actor 'bot', actor_role 'owner' — как у revive_by_author [ШТАБ З2 Ш5; проверку actor проектором v8 ШТАБ сверит до промпта].
- Р5. Канал — свои права (0021) и фоновый наблюдатель раз в 60 с; outbox и projector.py не трогаем [ШТАБ З2 Ш1].
- Р6. Карточка и алерт — в WORK_GROUP_ID, тема ACCESS_ADMIN_TOPIC_ID. Роутер и наблюдатель работают при config.access_enabled; роутер подключается перед роутером доступа и ловит только callback «pse:…» [ШТАБ З2 Ш2].
- Р7. Уведомления [ШТАБ З2 Ш6, К-5; канон 02 П.2, П.4, П.5]:
  - Автору: карточка (requested и now < start_at); алерт «пауза началась без решения Автора» (active и нет ключа pause_decide:{pid}:{pause_id}).
  - Участнику: approved; rejected; cancelled (одна нейтральная заглушка — причину бот не различает); active («пауза активна», при N ≥ 3 плюс предупреждение П.5); ending; ended.
- Р8. ending: active, N ≥ 2 и 0 < planned_end_at − now() < 24 h. При N = 1 ending не шлётся: иначе оно пришло бы сразу после active [ПРОЕКТИРОВЩИК-тех; ШТАБ может отменить].
- Р9. Шлём только по ТЕКУЩЕМУ статусу строки. Пропущенные статусы (бот лежал) не досылаются; исключение — алерт Автору [ПРОЕКТИРОВЩИК-тех].
- Р10. Даты — по поясу участника (participant_state.tz, право есть, по коду card.py). tz пуст или неизвестен → даты по UTC с пометкой «(UTC)». N = (местная дата planned_end_at − местная дата start_at) в днях; последний день паузы = местная дата planned_end_at − 1 день [ШТАБ З2 Ш7; ПРОЕКТИРОВЩИК-тех].
- Р11. Подпись участника в карточке — «#<short_no>», как в /revive (по коду revive_handlers.py).
- Р12. Тексты — только «[заглушка] …», включая кнопки; тексты курса пишет Автор.
- Вне задачи: перенос паузы (П.7); отмена Автором авто-разрешённой паузы (П.8, Панель /unpause_user).

## 4. Права app_bot (по коду 0018, 0020, 0021, card.py) — SQL ниже использует только их
- participant_pauses: SELECT (id, pid, kind, status, start_at, planned_end_at, created_at) (0021);
- tg_user_registry: SELECT (pid, tg_user_id, tombstoned_at, short_no);
- participant_state: SELECT (…, tz);
- participant_events: INSERT (pid, kind, payload, actor, actor_role);
- idempotency_keys: INSERT (key, kind, result_ref, ttl); SELECT (key, result_ref).
Только параметры %s, без RETURNING. LOCK — из bot.life (как в revive.apply).

## 5. SQL (bot/pause.py)
    WATCH = """SELECT p.id, p.pid, p.status, p.start_at, p.planned_end_at,
      r.tg_user_id, r.short_no, s.tz, now() AS db_now,
      (p.status = 'requested' AND now() < p.start_at) AS open
    FROM participant_pauses p
    JOIN tg_user_registry r ON r.pid = p.pid
    LEFT JOIN participant_state s ON s.pid = p.pid
    WHERE p.kind = 'user' AND r.tombstoned_at IS NULL
      AND p.created_at > now() - interval '10 days'
    ORDER BY p.id"""
    DECIDE_ROW = "SELECT pid FROM participant_pauses WHERE id = %s AND kind = 'user'"
    DECIDE_CHECK = "SELECT status = 'requested' AND now() < start_at FROM participant_pauses WHERE id = %s"
    KEY_TTL = ("INSERT INTO idempotency_keys (key, kind, result_ref, ttl) "
               "VALUES (%s, %s, %s, interval '30 days') ON CONFLICT (key) DO NOTHING")
    KEY_EXISTS = "SELECT key FROM idempotency_keys WHERE key = %s"
    EVENT = ("INSERT INTO participant_events (pid, kind, payload, actor, actor_role) "
             "VALUES (%s, %s, %s, 'bot', 'owner')")
Окно 10 дней: от заявки до старта ≤ 1 сутки, пауза ≤ 169 ч, плюс запас.
Ключи:
- pause_note:{pid}:{pause_id}:{метка}, kind 'pause_note', где метка ∈ requested, approved, rejected, cancelled, active, ending, ended, auto;
- pause_decide:{pid}:{pause_id}, kind 'pause_decide', result_ref 'approved' | 'rejected'.
Чистые функции (с тестами): local_dates(start_at, planned_end_at, tz) → (первый день, последний день, N, пометка UTC); is_ending(row, N); labels_for(row, N, decided) → список меток по Р7–Р9.

## 6. Наблюдатель (bot/pause_watch.py)
- start_pause_watcher(bot, config, stop) — по образцу start_outbox_worker в app.py. Тот же stop; остановка — как у воркера outbox (ожидание, затем cancel). PAUSE_WATCH_SECONDS = 60.
- Тик: WATCH в своей транзакции. Для каждой строки метки по labels_for:
  - requested — только при open;
  - active — сначала auto (если KEY_EXISTS по pause_decide пусто), затем active, затем ending (если is_ending);
  - остальные статусы — метка, равная статусу.
- Каждая метка — своя транзакция:
  1. KEY_TTL; rowcount 0 → пропуск.
  2. Отправка:
     - requested — карточка Автору с кнопками «pse:a:<id>» и «pse:r:<id>»;
     - auto — алерт Автору;
     - остальное — участнику в личку (tg_user_id).
  3. Итог отправки:
     - успех → COMMIT;
     - TelegramForbiddenError или TelegramBadRequest → COMMIT + WARNING (повторять нет смысла);
     - прочая ошибка Telegram → ROLLBACK (повтор в следующем тике).
- Ошибка БД в тике → WARNING с именем класса, следующий тик.
- Логи: только метка, код и счётчики; без tg_user_id, pid, short_no и дат.
- Соединение с БД — как у bot.life и bot.access (BOT_DATABASE_URL).

## 7. Кнопки (bot/pause_handlers.py)
- Роутер ловит только callback, F.data.startswith("pse:"). Разбор строго по ^pse:(a|r):(\d{1,18})$; не разобралось → answerCallbackQuery без текста + лог.
- Сообщение не из WORK_GROUP_ID или пользователь не в ACCESS_ADMIN_IDS → answerCallbackQuery без текста + лог, без БД (как в revive_handlers).
- pause.decide(conn, pause_id, approve) — одна транзакция:
  1. DECIDE_ROW; строки нет → GONE.
  2. LOCK(pid).
  3. DECIDE_CHECK; не True → NOT_OPEN.
  4. KEY_TTL pause_decide; rowcount 0 → ALREADY.
  5. EVENT: kind 'pause_approved' | 'pause_rejected', Jsonb({"pause_id": id}).
  6. Итог → APPROVED или REJECTED.
- Ошибка БД → TRY_LATER. Итог дописывается к карточке, кнопки снимаются (свой _finish по образцу revive_handlers). При TRY_LATER кнопки остаются.
- Участнику кнопка ничего не шлёт: уведомляет только наблюдатель (один путь, без дублей).

## 8. Подключение (bot/app.py)
- build_dispatcher: в ветке config.access_enabled — pause_handlers.build_router(config) ПЕРЕД роутером доступа.
- run(): при config.access_enabled — запуск наблюдателя после start_outbox_worker, остановка в finally.
- Docstring app.py — абзац про паузы.

## 9. Тексты (bot/texts.py, ключи bot.pause_*; комментарий-ключ над каждой константой)
- PAUSE_CARD = "[заглушка] Заявка на паузу: {who}, с {first} по {last} включительно ({days} дн.)."
- PAUSE_BTN_APPROVE = "[заглушка] ✅ Одобрить"
- PAUSE_BTN_REJECT = "[заглушка] ✖ Отклонить"
- PAUSE_DONE_APPROVED = "[заглушка] Одобрено."
- PAUSE_DONE_REJECTED = "[заглушка] Отклонено."
- PAUSE_ALREADY = "[заглушка] Уже решено."
- PAUSE_NOT_OPEN = "[заглушка] Решение не записано: заявка уже не ждёт ответа."
- PAUSE_GONE = "[заглушка] Заявка не найдена."
- PAUSE_TRY_LATER = "[заглушка] Не удалось, попробуйте позже."
- PAUSE_AUTO_ALERT = "[заглушка] Пауза {who} началась без решения Автора: с {first} по {last}."
- PAUSE_USER_APPROVED = "[заглушка] Пауза одобрена: с {first} по {last}."
- PAUSE_USER_REJECTED = "[заглушка] Заявка на паузу отклонена."
- PAUSE_USER_CANCELLED = "[заглушка] Заявка на паузу не действует."
- PAUSE_USER_ACTIVE = "[заглушка] Пауза активна до {last} включительно."
- PAUSE_USER_LONG_WARN = "[заглушка] Во время паузы упражнения не выполняются; длительный перерыв рискует прогрессом."
- PAUSE_USER_ENDING = "[заглушка] Пауза заканчивается: продолжение с {resume} 00:00 по вашему поясу."
- PAUSE_USER_ENDED = "[заглушка] Пауза закончилась."
Даты — «дд.мм»; при tz по UTC к датам добавляется « (UTC)». При N ≥ 3 active = PAUSE_USER_ACTIVE + "\n\n" + PAUSE_USER_LONG_WARN.

## 10. Тесты и задетые
- Новый apps/bot/tests/test_pause.py по образцу test_revive.py:
  - local_dates: МСК, UTC-фолбэк, переход часов; N = 1, 3, 7;
  - labels_for: все статусы; open = False; auto с ключом и без; ending при N = 1, 2, 7;
  - разбор callback;
  - decide на фейковом соединении — все 6 кодов и порядок SQL;
  - handlers: чужой чат и не-whitelist без БД;
  - тик: ключ вставился → отправка → COMMIT; ключ есть → без отправки; сетевая ошибка → ROLLBACK; Forbidden → COMMIT;
  - все PAUSE_* начинаются с «[заглушка]».
- Кандидаты, сверяет ШТАБ до промпта: тесты build_dispatcher и списка или порядка роутеров; тесты run() и start_outbox_worker; сверка texts.py целиком — в apps/bot/tests. Найдено — ШТАБ вписывает файл в §11; в бюджете ≈ 7 КБ, больше — резать.

## 11. Чтение Агента (≈ 133 КБ из 140) и запреты
- Читать: AGENT-BRIEF.md 17,1; docs/decisions/DECISIONS.md 7,7; эта карточка ≈ 14; bot/revive.py 10,5; bot/revive_handlers.py 8,4; bot/life.py 8,0; bot/access.py 15,2; bot/app.py 10,1; bot/texts.py 16,3; bot/config.py 11,6; tests/test_revive.py 13,7.
- Не трогать: apps/api, миграции, outbox.py, projector.py.
- Нельзя: писать в participant_pauses и participant_state; добавлять свои тексты, кроме §9; ждать CI (А-CI).

## 12. Готово
- Три новых модуля, правки app.py и texts.py, test_pause.py; tools/check.sh bot зелёный.
- Ручная проверка Автором при выкате: заявка → карточка → ✅ → участнику «одобрена»; заявка без решения → после 00:00 алерт Автору и участнику «пауза активна».

## 13. Оценка
- ≈ 650 кредитов: pause.py ≈ 150 строк, наблюдатель ≈ 120, handlers ≈ 100, тесты ≈ 350; задетые 1–3 файла × 60–100.
- Пачка с 0021: ≈ 1 000, стоп 1 500 (факты: bot-revive-1 + 0020 — 706 при оценке 1 000; T3 — 953 при 1 600).

## 14. РЕВЬЮЕР: нет
GRANT вынесен в 0021; initData и оплаты не задеты.

## Канон и решения
(а) Канон: 02-access-lives-pause.md П.2, П.4, П.5 — по выдержке ШТАБа З2 (окно 02 не читало); Р-6а — DECISIONS.md.
(б) Р14 api-pause-1a §2 расходится с 02 П.2 → решение Автора 18.11 (молчание = авто-разрешение); исправление — api-pause-3. Запись в DECISIONS.md — за ШТАБом.
(в)–(г) Правок канона нет. П.7 (перенос) и П.8 (отмена Автором) — вне задачи.
