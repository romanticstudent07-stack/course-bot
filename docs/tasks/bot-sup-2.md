# bot-sup-2 — карточка «Доступ» вместо «Оплаты»; промпт ✉️ удаляется после ответа

## 1. Паспорт
- id: bot-sup-2 · заголовок PR: «bot-sup-2: карточка — «Доступ»; промпт ✉️ удаляется после ответа» · ветка: feat/bot-sup-2
- Режим: Р0+ КОДЕР (0 кредитов). РЕВЬЮЕР: нет (§10). Миграций нет.
- Карточка написана ШТАБом без ПРОЕКТИРОВЩИКА (SHTAB.md §3-Б: одна область, 3 файла, без исследования) по коду @96f4552.
- Правило К — docs/process/CANON-CHECK.md. Сначала прочитай docs/decisions/DECISIONS.md целиком.
- Выкат — по PLAN §4, вместе с ближайшим выкатом бота; отдельного выката нет.

## 2. Цель
1) В карточке участника строка «[заглушка] Оплаты: нет данных» становится «[заглушка] Доступ: нет данных».
2) После того как админ ответил (reply) на промпт ✉️ и бот отправил предпросмотр, бот удаляет свой промпт, и плашка ответа над полем ввода пропадает. Следующая плашка появится только после нового нажатия «✉️ Ответить».

## 3. Решения Автора (15.11, дословно по смыслу; в DECISIONS — docs-пакетом ШТАБа)
- «В карточке участника вместо: [заглушка] Оплаты: нет данных - [заглушка] Доступ: нет данных. То есть меняем слово Оплата на слово Доступ!» [К-6: Автор]
- Б1: бот удаляет промпт ✉️ после ответа; отдельной кнопки «Отмена» под промптом нет. [К-6: Автор]
- Ограничения Telegram, принятые Автором: кнопка не может открыть плашку ответа; крестик на плашке бот не видит; ответ без reply бот не принимает (состояния в памяти нет, bot-sup-1). [ШТАБ, Bot API]

## 4. Как сейчас (по коду @96f4552)
- apps/bot/bot/texts.py: CARD_PAYMENTS = "[заглушка] Оплаты: {value}" (комментарий над строкой: # bot.card_payments — {value}).
- apps/bot/bot/card.py, render_card: lines.append(texts.CARD_PAYMENTS.format(value=texts.CARD_NO_DATA)).
- apps/bot/bot/support_handlers.py, on_answer: проверки «нет текста» → SUPPORT_SEND_TEXT, «длиннее 2000» → SUPPORT_TOO_LONG, затем
      await _safe("предпросмотр не отправлен", message.reply(texts.SUPPORT_PREVIEW.format(n=n) + "\n\n" + message.text, reply_markup=support.preview_markup(n)))
  Промпт (message.reply_to_message) остаётся в теме навсегда.
- apps/bot/tests/test_support.py: make_tg_bot() — SimpleNamespace(id, send_message, edit_message_reply_markup, edit_message_text), delete_message нет; make_message кладёт этот бот в message.bot, reply_to_message.message_id = 600.

## 5. Файлы (только эти 3)
- apps/bot/bot/texts.py — изменить
- apps/bot/bot/support_handlers.py — изменить
- apps/bot/tests/test_support.py — изменить (задетый, §8)
card.py и test_card.py НЕ трогать: имя константы CARD_PAYMENTS остаётся, меняется только текст.

## 6. Что сделать
6.1 texts.py: CARD_PAYMENTS = "[заглушка] Доступ: {value}"; комментарий над строкой: # bot.card_access — {value} (15.11, было «Оплаты»; имя константы прежнее).
6.2 support_handlers.py, on_answer: результат отправки предпросмотра сохранить в переменную (_safe уже возвращает True/False). Только если True —
      await _safe("промпт не удалён", message.bot.delete_message(chat_id=message.chat.id, message_id=message.reply_to_message.message_id))
  - Ответ «нет текста» или «длиннее 2000» → промпт НЕ удалять (админ отвечает на него ещё раз).
  - Ошибка удаления (в том числе промпт старше 48 ч) → только WARNING из _safe с именем класса, исключение наружу не идёт, предпросмотр остаётся.
  - Ответ админа (его сообщение) не удалять.
  - В докстринге модуля, пункт «Ответ админа reply на промпт…», дописать: «после успешного предпросмотра промпт удаляется (bot-sup-2)».
6.3 Логи — как в bot-sup-1 §7.7: только имя класса ошибки; никогда tg_user_id, pid, short_no, N, номер темы, тексты.

## 7. Нельзя
- Файлы вне §5; docs/**, .github/**, infra/**, apps/api/**, apps/miniapp/**; новые зависимости; запись в БД; состояние в памяти процесса.
- Менять callback_data, тексты промпта и предпросмотра, фильтр _is_admin_reply.

## 8. Задетые тесты (Правило «Т», сверено ШТАБом по коду @96f4552)
- apps/bot/tests/test_support.py: make_tg_bot() — добавить delete_message=AsyncMock(). Без этого падают test_admin_reply_preview и test_admin_reply_not_text_and_too_long (AttributeError у message.bot).
- test_card.py не задет: test_render_card_full берёт строку из texts.CARD_PAYMENTS.
- Другие тесты не задеты (test_bot, test_access, test_outbox, test_outbox_group delete_message не используют). Упал тест вне списка → не чинить, стоп и ИТОГ с именем теста.

## 9. Тесты (в test_support.py, сверх — не добавлять)
1) test_admin_reply_preview: дописать assert msg.bot.delete_message.await_args == call(chat_id=WG, message_id=600).
2) test_admin_reply_not_text_and_too_long: для «нет текста» и «2001 знак» — msg.bot.delete_message.assert_not_awaited(); для «2000 знаков» — delete_message.await_count == 1.
3) Новый test_prompt_kept_when_preview_failed: msg.reply.side_effect = RuntimeError("down") → delete_message.assert_not_awaited(); исключения нет.
4) Новый test_prompt_delete_failure_logged: msg.bot.delete_message.side_effect = TelegramBadRequest(method=METHOD, message="Bad Request: message to delete not found") → исключения нет; в caplog WARNING, начинающийся с «support: промпт не удалён (TelegramBadRequest)»; _no_pii(caplog).
5) Новый test_card_access_text: texts.CARD_PAYMENTS.format(value="x") == "[заглушка] Доступ: x" и «Оплаты» нет в texts.CARD_PAYMENTS.

## 10. РЕВЬЮЕР: нет
initData, 18+, согласия, rate-limit, GRANT, оплата не затронуты.

## 11. Живая проверка (после выката бота, А2 → А1)
А2 задаёт вопрос → А1 ✉️ → плашка есть → А1 отвечает reply → предпросмотр пришёл, промпт исчез, плашки нет при повторном входе в тему → «Отправить» → А2 получил ответ. Карточка: «[заглушка] Доступ: нет данных».

## 12. Критерии готовности
3 файла §5, других нет; bash tools/check.sh bot зелёный; тесты §9 есть; другие готовые тесты не менялись.

## 13. Оценка
≈ 60 строк (код ~15, тесты ~45). КОДЕР, 1 окно, 0 кредитов. Часы Автора ~0,3.

## Канон и решения
(а) Использует: Р-19 (DECISIONS); bot-sup-1 §7.4 (ответ ✉️).
(б) Текст «Доступ» в карточке — решение Автора 15.11; соответствие 06 §6.4 (поле оплат) в этом окне не проверено — ШТАБ сверит в DOCS-пакете.
(в) Долги ШТАБа: Р-решение «Доступ» в DECISIONS; докстринг card.py «Оплаты, паузы, возвраты» и имя константы CARD_PAYMENTS → CARD_ACCESS — в следующую карточку бота.
