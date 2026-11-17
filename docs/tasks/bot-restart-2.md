# bot-restart-2 — рестарт: слово через clean_word, устаревшая заявка 48 ч, недостающие тесты
Hash main 917b262. Продолжение docs/tasks/bot-restart-1.md (T6c). Правило К — docs/process/CANON-CHECK.md. Сначала прочитай docs/decisions/DECISIONS.md целиком.

## 1. Паспорт
- id: bot-restart-2 · PR: «bot-restart-2: рестарт — clean_word, заявка старше 48 ч, тесты» · ветка: feat/bot-restart-2
- Режим: Р0+ (КОДЕР, бесплатно). Зависит от: bot-restart-1 (#241, main 917b262). Миграций нет. Область — бот.

## 2. Цель
Закрыть замечания РЕВЬЮЕРА PR #241. Кодовое слово рестарта проверять так же, как слово доступа (access.clean_word, до 64 знаков). Кнопки на заявке старше 48 ч не пишут в БД. Добавить тесты двойного «Выдать» и сбоя COMMIT.

## 3. Решения (метка К-6)
- Р-20, Р-2 (DECISIONS.md): рестарт по промокоду через админ-тему [Выдать]/[Запретить] [Автор]. О длине слова и сроке заявки молчат.
- ШТАБ 17.11 (К-5, источник — РЕВЬЮЕР PR #241): слово проверяется через access.clean_word. Если вернулось None — тишина, как при «не eligible»: в тему ничего, ключ не пишется, участнику ничего. Новых текстов для участника нет. access.py не менять [ШТАБ-тех].
- ШТАБ 17.11 (К-5): «Выдать»/«Запретить» на заявке старше 48 ч (по callback.message.date) → в БД не ходить, отказ в теме, кнопки снять, участнику ничего. Образец — LIFE_STALE в life_handlers.py. Порог — константа в restart.py. Ровно 48 ч — заявка действует (строгое >) [ШТАБ-тех].
- ШТАБ 17.11 (К-5): живая проверка «ждать 48 ч» не нужна, хватает тестов [ШТАБ-тех].
- Следствие п.1: текст из одних пробелов теперь тоже даёт тишину (раньше уходила заявка с пустым словом).

## 4. Выдержки (подсказка; файлы читать целиком, §5)
- access.py: WORD_MAX_LEN = 64; clean_word(text) — strip; пусто или длиннее 64 → None, иначе слово. aware(dt) — дату без пояса считает UTC.
- life_handlers.py: проверка STALE стоит после проверки чата и whitelist и до БД. Условие: now - дата предпросмотра > порога → _finish(callback, texts.LIFE_STALE), answer без текста.
- access_handlers.py, on_private: при вердикте NOTHING вызывает restart.submit_request в try. Любое исключение → лог и код restart.TRY_LATER. Затем restart.user_text_for(code); None → ничего не отправлять. Поэтому NOTHING из submit_request = тишина, а сбой COMMIT = RESTART_TRY_LATER без правки кода.
- restart_handlers.after_commit(bot, config, result, chat_id, message_id, original_html, now): дописывает к заявке restart.admin_note_for(result) и снимает кнопки. Участнику пишет, только если есть tg_user_id и текст.
- idempotency_keys: по коду очистки по ttl нет (миграция 0007: «UPDATE, DELETE и TRUNCATE idempotency_keys не получает никто… очистка по ttl — отдельная задача позже»).

## 5. ЧТО ПРОЧИТАТЬ (целиком, по hash main)
CODER.md 6,1; docs/process/PACK.md 11,8; AGENT-BRIEF.md 17,1; docs/decisions/DECISIONS.md 7,7; эта карточка ≈ 9; apps/bot/bot/restart.py 10,8; apps/bot/bot/restart_handlers.py 5,2; apps/bot/bot/texts.py 13,6; apps/bot/tests/test_restart.py 12,3; apps/bot/bot/access.py 15,2 (clean_word, aware); apps/bot/bot/life_handlers.py 7,4 (образец LIFE_STALE); apps/bot/bot/access_handlers.py 11,3 (on_private — путь сбоя COMMIT).
Чтение КОДЕРА ≈ 128 КБ.

## 6. Файлы
- изменить: apps/bot/bot/restart.py, apps/bot/bot/restart_handlers.py, apps/bot/bot/texts.py, apps/bot/tests/test_restart.py
- не менять: access.py, access_handlers.py, life.py, life_handlers.py, app.py, миграции, api. Сверх списка — только с причиной в описании PR.

## 7. Контракт
П.1 — restart.py, submit_request:
- импорт: к from bot.access добавить clean_word;
- первой строкой функции, до любого SQL и до Bot API:
    word = clean_word(word_text)
    if word is None:
        return NOTHING
- в текст заявки (request_text) передавать word вместо (word_text or "").strip(); html.escape остаётся;
- в лог слово не писать (как сейчас).
П.2 — restart.py:
- STALE_HOURS = 48 и код STALE = "stale";
- функция is_stale(message_date, now) -> bool:
    if message_date is None: return True
    return now - aware(message_date) > timedelta(hours=STALE_HOURS)
  InaccessibleMessage (старое сообщение) даёт дату 0 или None → True, без исключения;
- admin_note_for: STALE → texts.RESTART_STALE; текст участнику для STALE — None (как у прочих отказов).
П.2 — restart_handlers.py, on_button: после проверки темы и whitelist, до connect:
    if restart.is_stale(getattr(msg, "date", None), now):
        logger.info("restart: заявка устарела")
        await after_commit(callback.bot, config, restart.Result(restart.STALE),
                           msg.chat.id, msg.message_id, getattr(msg, "html_text", "") or "", now)
        try: await callback.answer()
        except Exception as exc: logger.warning(как в основном пути)
        return
now = _now() брать до этой проверки. connect и decide не вызываются. Docstring модуля дополнить строкой про 48 ч.
П.2 — texts.py, после RESTART_REFUSED_STATE:
    # bot.restart_stale
    RESTART_STALE = "[заглушка] Заявка старше 48 ч — решение не записано."

## 8. БД
Миграций нет. SQL не меняется. Ключи restart_req и restart как в bot-restart-1 §7.

## 9. Тесты (apps/bot/tests/test_restart.py; ID в новых тестах 4901–4999)
Новые:
- test_word_too_long_silent: granted + eligible, текст "я"*65 → SendMessage нет (ни в тему, ни участнику), в conn.sqls() нет restart.FIND_BY_TG и restart.REQUEST_KEY, conn.keys пуст;
- test_word_blank_silent: текст "   " → то же;
- test_word_64_ok: "я"*64 → заявка в тему ушла (контроль границы clean_word);
- test_stale_grant_no_db и test_stale_deny_no_db: mid 4901 и 4902, дата сообщения NOW - 48 ч - 1 с → conn.log == [], один EditMessageText с RESTART_STALE и reply_markup None, SendMessage нет, AnswerCallbackQuery без текста;
- test_stale_boundary_48h_valid: дата NOW - 48 ч ровно, mid 4903, «Выдать» → обычная выдача: EVENT в SQL, участнику RESTART_GRANTED;
- test_is_stale_none: restart.is_stale(None, NOW) is True;
- test_double_grant_already: mid 4904, два «Выдать» подряд через _feed на одном FakeConn → EVENT выполнен один раз. Второе нажатие: в тему RESTART_ALREADY.format(result=RESTART_RESULT_GRANTED), кнопки сняты, участнику второй SendMessage не ушёл;
- test_commit_fails_after_send: FakeConn(fail_commit=True), заявка через _feed(_private()) → заявка в тему отправлена, участнику RESTART_TRY_LATER, conn.keys пуст.
Задетые тесты (правило «Т»):
- apps/bot/tests/test_restart.py:
  (1) _button(): добавить параметр date=NOW, в Message передавать date=date вместо datetime.now();
  (2) фикстура _fixed_now: добавить monkeypatch.setattr(restart_handlers, "_now", lambda: NOW); в импорт from bot import дописать restart_handlers;
  (3) FakeConn: необязательный параметр fail_commit=False. При True выход из транзакции пишет "commit_failed" в log, бросает RuntimeError и не переносит ключи транзакции в conn.keys. По умолчанию поведение прежнее;
  (4) из-за (1)–(2) задеты test_grant_order_payload_actor_no_returning, test_grant_muted_refused, test_grant_erased_refused, test_grant_tombstoned_refused, test_deny_then_grant_already — тела не менять. test_button_foreign_chat_or_not_whitelist не задет: фильтр темы стоит до STALE. WORD (16 знаков) не задет.
- apps/bot/tests/test_access.py: не задет (по коду, ШТАБ 917b262): Dispatcher-сценариев «granted + текст» нет; "x"*65 и "   " — только в test_new_request_recheck_no_send, ветку рестарта он не проходит.
- Сверка texts.py целиком: в test_bot, test_card, test_life, test_support, test_render таких тестов нет. test_outbox.py и test_outbox_group.py — не проверено, риск низкий. Упадёт — стоп по правилу «Т», ИТОГ.
check.sh: bash tools/check.sh bot. Только в CI: нет.

## 10. Живая проверка (дополнение к bot-restart-1 §10; аккаунт А3, А1 не трогать)
Выкат только bot, миграций нет. block_lives у А3 — через /life до 0 (bot-life-1).
1. А3 с block_lives пишет боту слово из 65 знаков → в админ-теме ничего, А3 ничего не получил.
2. Логи: без кодового слова, tg_user_id, pid.

## 11. Запреты
AGENT-BRIEF §3. access.py, access_handlers.py, life*.py не менять. Код ttl idempotency_keys не трогать. Новых текстов участнику нет. RESTART_STALE — только заглушка. Не делать сейчас (долг, отдельные задачи): замок participant:pid на время send_message; заявку-сироту при сбое COMMIT (закрывается п.2); хвосты life.py (re.ASCII, тест ошибки БД).

## 12. Готово
Слово > 64 и пустое → тишина. Кнопки на заявке старше 48 ч → отказ в теме без БД, ровно 48 ч — действует. Тесты §9 есть. check.sh bot зелёный.

## 13. Оценка
≈ 40 строк кода, ≈ 140 строк тестов, задетый test_restart.py (фикстуры). Кредиты 0 (Р0+). Часы Автора ≈ 0,3.

## 14. РЕВЬЮЕР: да, короткое
Поток Р-2 (промокод), рестарт (оплата в личке, Р-1).

## Канон и решения
(а) Используется: Р-2, Р-20 (DECISIONS.md); механика — bot-restart-1 §7.
(б) Противоречий с DECISIONS.md нет: о длине слова и сроке заявки решения молчат, это технические мелочи, решил ШТАБ (К-5).
(в) Предупреждение (по коду, 0007): будущая очистка idempotency_keys по ttl не должна удалять ключи restart_req и restart.
(г) Правок канона нет.
