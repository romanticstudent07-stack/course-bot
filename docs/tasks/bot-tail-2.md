# bot-tail-2 — долги #259: тесты кнопок паузы и ветки decided, пустая строка

Режим: Р1 «Агент-исполнитель», Sonnet 5. Область: bot. РЕВЬЮЕР: нет (только тесты и пробел).
Карточка ШТАБа, сверена с кодом по a076e02 (22.11). Правило К — docs/process/CANON-CHECK.md.
Оценка: 250–350 кредитов.

## 1. Цель
Закрыть тест-долги bot-pause-1 (#259, SHTAB-DEBTS §7): нет тестов кнопок ✅/✖ от админа (успех и TRY_LATER),
нет теста ветки decided в тике наблюдателя (алерт AUTO), лишняя пустая строка в конце pause_handlers.py.
Поведение кода не меняется. Новых текстов, SQL, миграций нет.

## 2. Канон и метки (К-6)
- Кнопка: итог дописывается к карточке, кнопки снимаются, участнику ничего; TRY_LATER — всплывающий ответ,
  кнопки остаются — [канон: docs/tasks/bot-pause-1.md §7; docstring pause_handlers.py].
- AUTO: active без ключа pause_decide → алерт Автору PAUSE_AUTO_ALERT; с ключом — без алерта —
  [канон: bot-pause-1, Р1 «молчание Автора = авто-разрешение»; pause.labels_for].
- Пустая строка — [ШТАБ-тех].

## 3. Файлы
Правка: apps/bot/bot/pause_handlers.py (только удалить пустую строку после `return router` в конце файла);
apps/bot/tests/test_pause.py.
Только чтение: apps/bot/bot/pause.py, apps/bot/bot/pause_watch.py.

## 4. Что сделать
1. pause_handlers.py: файл заканчивается строкой `    return router` и одним переводом строки. Больше ничего.
2. test_pause.py, новые тесты через _feed и _button (админ, GROUP):
   а) test_button_admin_approve_edits_card: db() и _button(f"pse:a:{PAUSE_ID}") → ровно один EditMessageText,
      reply_markup is None, texts.PAUSE_DONE_APPROVED в его text; один AnswerCallbackQuery с text is None;
      SendMessage нет ни одного (участнику ничего).
   б) test_button_admin_try_later_buttons_stay: db(fail_on=EVENT) и _button(f"pse:r:{PAUSE_ID}") →
      AnswerCallbackQuery с text == texts.PAUSE_TRY_LATER; EditMessageText нет; SendMessage нет.
3. test_pause.py, тик с веткой decided (по pause_watch.tick; используй row(), FakeBot, _tick):
   r = row("active", now=START + timedelta(hours=1), open_=False).
   а) test_tick_active_not_decided_sends_auto_alert: db(watch_rows=[r], decided=False) → среди bot.sent есть
      сообщение в chat_id GROUP с text == texts.PAUSE_AUTO_ALERT.format(who="#004408", first="20.11", last="22.11");
      KEY_EXISTS есть в conn.sqls().
   б) test_tick_active_decided_no_auto_alert: db(watch_rows=[r], decided=True) → ни в одном bot.sent нет
      текста texts.PAUSE_AUTO_ALERT.format(who="#004408", first="20.11", last="22.11").
   Если pause_watch.tick не вызывает KEY_EXISTS для active или порядок отличается — стоп и один вопрос ШТАБу.

## 5. Задетые тесты (правило «Т», сверено ШТАБом по a076e02)
- Изменить: apps/bot/tests/test_pause.py (только новые тесты; старые тела не трогать).
- Регрессия, не менять: все прочие apps/bot/tests/**.
Упал тест вне «Изменить» → не чинить, стоп и ИТОГ с именем теста и текстом ошибки.

## 6. Нельзя
apps/api/**, apps/miniapp/**, apps/bot/bot/** кроме пустой строки в pause_handlers.py, docs/**, .github/**, infra/**,
миграции, новые зависимости, новые тексты. ID — из констант test_pause.py.

## 7. Готово, когда
bash tools/check.sh bot зелёный (1 прогон); изменены только 2 файла из §3; всё из §4.

## 8. Открытые вопросы
нет. AUTHOR_LABELS, CARD_PAYMENTS → CARD_ACCESS, DEFAULT_LIVES — вне карточки (не сверены / другая область).
