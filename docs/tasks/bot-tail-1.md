# bot-tail-1 — хвосты бота: re.ASCII в /life и тест-долги ревью #240, #243

Режим: Р1 «Агент-исполнитель». Область: bot. РЕВЬЮЕР: нет (только regex-флаг и тесты).
Карточка ШТАБа, сверена с кодом по d5579e9 (22.11). Правило К — docs/process/CANON-CHECK.md.
Оценка: 250–350 кредитов.

## 1. Цель
Закрыть низкие находки РЕВЬЮЕРОВ: #240 п.2 (re.ASCII в разборе /life), #240 п.6 (тест ветки ошибки БД),
#243 п.1 (commit_failed ровно один раз и после REQUEST_KEY), #243 п.2 (caplog в путях STALE и clean_word).
Поведение для правильного ввода не меняется. Новых текстов, SQL, миграций нет.

## 2. Канон и метки (К-6)
- re.ASCII: номер участника и N — только цифры 0–9 — [ШТАБ-тех] (#240, коммент ШТАБа 17.11, находка 2).
- Ошибка БД → texts.LIFE_TRY_LATER (предпросмотр — ответом в группе; подтверждение — всплывающим ответом
  на кнопку, кнопки остаются) — [канон: docs/tasks/bot-life-1.md, принято ШТАБом в #240 (К-5)].
- Логи без слова, tg_user_id, pid — [канон: bot-restart-1 / bot-restart-2, docstring life.py].

## 3. Файлы
Правка: apps/bot/bot/life.py; apps/bot/tests/test_life.py; apps/bot/tests/test_restart.py.
Только чтение: apps/bot/bot/life_handlers.py.
Остальное не трогать.

## 4. Что сделать
1. life.py: добавить флаг re.ASCII в оба шаблона — _ARGS_RE и _CONFIRM_RE. Больше в life.py ничего не менять.
2. test_life.py, новые тесты:
   а) parse_args("+٣") == (life.USAGE, None, None); parse_args("#١٢٣ +1") == (life.USAGE, None, None);
      life.parse_callback("life:y:١٢٣:-1:0123456789abcdef") is None.
   б) Ошибка БД на предпросмотре: FakeConn, у которого execute бросает RuntimeError; через _feed с _cmd("/life #004708 -1")
      → ровно один SendMessage в GROUP с текстом texts.LIFE_TRY_LATER, без reply_markup; _no_send_to_participant.
   в) Ошибка БД на подтверждении: тот же FakeConn; через _feed с _button(life.confirm_data(SHORT, -1, OP))
      → AnswerCallbackQuery с text == texts.LIFE_TRY_LATER; EditMessageText нет; _no_send_to_participant.
3. test_restart.py, правки:
   а) test_commit_fails_after_send: вместо `"commit_failed" in conn.log` —
      conn.log.count("commit_failed") == 1 и индекс записи (restart.REQUEST_KEY, …) в conn.log меньше
      conn.log.index("commit_failed"). Остальные assert теста не трогать.
   б) caplog в путях STALE и clean_word: test_stale_grant_no_db и test_word_too_long_silent принимают caplog,
      caplog.set_level(logging.DEBUG); проверить, что в caplog.text нет str(USER), str(PID), а для слова — нет "я" * 65.
      Тела остальных тестов не менять.

## 5. Задетые тесты (правило «Т», сверено ШТАБом по d5579e9)
- Изменить: apps/bot/tests/test_life.py, apps/bot/tests/test_restart.py.
- Регрессия, не менять: все прочие apps/bot/tests/** (test_restart импортирует из bot.life только LOCK).
Упал тест вне «Изменить» → не чинить, стоп и ИТОГ с именем теста и текстом ошибки.

## 6. Нельзя
apps/api/**, apps/miniapp/**, apps/bot/bot/** кроме life.py, docs/**, .github/**, infra/**, миграции, новые зависимости,
новые тексты. ID в новых тестах — из уже объявленных констант файла.

## 7. Готово, когда
bash tools/check.sh bot зелёный (1 прогон); изменены только 3 файла из §3; всё из §4.

## 8. Открытые вопросы
нет. miniapp-help-static (Р-19 «внизу Mini App») — вне этой карточки, решит ШТАБ вместе с T5.
