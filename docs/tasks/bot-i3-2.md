# bot-i3-2 — кнопка «📇 Карточка» под постами бота в Рабочей группе (PLAN §5 п.12)

## 1. Паспорт
- id: bot-i3-2
- Заголовок PR: feat(bot): кнопка «📇 Карточка» под постами в темах группы (bot-i3-2)
- Ветка Агента: feat/bot-i3-2-card-button
- Режим: Р1, исполнитель — Агент Р1.
- Зависит от: bot-i3-1 (#206, смержен, main ba82b3e).
- Источник: docs/research/bot-i3.md §1, §5, §6. Карточка написана по исследованию, а не по канону.
- Правило К — docs/process/CANON-CHECK.md. Сначала прочитай docs/decisions/DECISIONS.md целиком.

## 2. Цель
Под каждым постом бота в темах «Рефлексии» (reflection_submitted) и «Отчёты и активность»
(ladder_day2_alert) должна стоять одна inline-кнопка «📇 Карточка» с callback_data «card:<short_no>».
Нажатие уже обрабатывает bot/card_handlers.py из bot-i3-1, его не трогаем.
Если у участника нет номера (в подписи {num} = «—»), пост уходит без кнопки.

## 3. Решения Автора и ШТАБа
- Р-15 (DECISIONS, дословно): «подпись в группе. Делаем: „Участник #NNNNNN (ID N) → написать“, ссылка
  tg://user?id=N; имя и username не берём». Подпись постов эта задача не меняет.
- [ШТАБ] (bot-i3.md §1): callback_data — «card:<short_no цифрами>»; pid в сообщения не выносим.
- [ШТАБ-тех] (bot-i3.md §1): если {num} = «—», то есть short_no is None, кнопку не ставить.
- [ШТАБ] (bot-i3.md §5): кнопка ставится в _send_group через reply_markup, для обоих маршрутов GROUP_ROUTES.
- [ШТАБ] З2, ответ 1: импорт верхнеуровневый — from bot.card import card_button. ШТАБ сверил bot/card.py
  по ba82b3e: он импортирует только bot.texts, bot.access (fmt_msk) и aiogram, а bot.outbox не импортирует,
  так что цикла нет.
- [ШТАБ] З2, ответ 2: кнопка ставится всегда, когда short_no задан. От card_enabled и cards_topic_id она
  не зависит. Основание: bot выкатывается только после того, как Автор задаст CARDS_TOPIC_ID (очередь И3);
  если карточка выключена, app.py при старте пишет WARNING «Карточка выключена». make_cfg в тестах не менять.

## 4. Выдержки (канон — через bot-i3.md; docs/architecture/** не открывать)
- P8 = 08-working-group.md §8.6, цитата в bot-i3.md §1: «Callback строго привязан к participant_id».
  [ШТАБ] Привязка идёт через номер: short_no — identity UNIQUE (AGENT-BRIEF §6).
- Маршруты, по коду OB@ba82b3e (докстринг): reflection_submitted → тема «Рефлексии» (REFLECTIONS_TOPIC_ID),
  ladder_day2_alert → тема «Отчёты и активность» (REPORTS_TOPIC_ID), чат WORK_GROUP_ID.
- Из bot/card.py@ba82b3e берутся только эти две вещи (дословно; сам файл не читать):
      CALLBACK_PREFIX = "card"
      def card_button(short_no: int) -> InlineKeyboardMarkup:
  Функция возвращает одну кнопку «📇 Карточка» с callback_data «card:<short_no>».
  Текст кнопки уже лежит в texts.py как CARD_BUTTON = "📇 Карточка", новых текстов не нужно.

## 5. ЧТО ПРОЧИТАТЬ (Агент)
- AGENT-BRIEF.md — 17,1 КБ
- docs/decisions/DECISIONS.md — 7,5 КБ
- docs/tasks/bot-i3-2.md — эта карточка
- apps/bot/bot/outbox.py — 28,7 КБ
- apps/bot/tests/test_outbox_group.py — 14,2 КБ
Чтение Агента ≈ 67,5 КБ плюс карточка. Читать только эти файлы. card.py, card_handlers.py и texts.py не открывать.

## 6. Файлы
- Изменить: apps/bot/bot/outbox.py
- Изменить: apps/bot/tests/test_outbox_group.py
- Создать и удалить: ничего.

## 7. Что сделать в коде (outbox.py)
1. Добавить верхнеуровневый импорт: from bot.card import card_button.
2. У _send_group появляется необязательный параметр reply_markup (по умолчанию None).
   Он передаётся в КАЖДЫЙ вызов bot.send_message внутри _send_group, в том числе в повтор после retry_after.
3. В ветке группы, там, где вызывается _send_group: short_no уже получен из GROUP_ADDRESSEE.
   Если short_no is None, клавиатура равна None. Иначе клавиатура = card_button(int(short_no)).
   Её нужно передать в _send_group. Так работают оба маршрута GROUP_ROUTES.
4. Личный путь (_deliver, лички) не трогать: reply_markup туда не передаётся.
5. Логи остаются прежними: callback_data и short_no в лог не писать.
6. В докстринг модуля, раздел «Темы Рабочей группы», добавить одну строку:
   «Под постом — кнопка „📇 Карточка“ (card:<short_no>, bot-i3-2); short_no нет — без кнопки».
Контракт: callback_data = «card:» + short_no десятичными цифрами без ведущих нулей (как отдаёт card_button).
Новых эндпоинтов, полей и кодов DLQ нет.

## 8. БД
Миграции нет. Новых прав и SQL нет: GROUP_ADDRESSEE уже читает short_no (0011).

## 9. Тесты (apps/bot/tests/test_outbox_group.py)
Новые тесты, номера по порядку:
1. day2: событие ladder_day2_alert, SHORT_NO = 4242. В kw["reply_markup"] ровно один ряд и одна кнопка:
   text == CARD_BUTTON (from bot.texts import CARD_BUTTON), callback_data == "card:4242".
2. reflection: то же для reflection_submitted (тема REFLECTIONS).
3. short_no=None: GROUP_ADDRESSEE отдаёт (TG_ID, None, None), ожидается kw.get("reply_markup") is None.
   Подпись «Участник #— », как и раньше.
4. retry_after: TelegramRetryAfter(retry_after=3), затем успех. В обоих вызовах send_message
   reply_markup с callback_data "card:4242".
5. Личный путь: событие send1_test — проверка "reply_markup" not in kw.
В тестах 1–2 и 4 вызвать _no_pii(caplog): SHORT_NO уже проверяется, значит callback_data не попал в лог.
Тесты сверх этого перечня не добавлять.

Задетые тесты: 0. Поиск сделан ПРОЕКТИРОВЩИКОМ по ba82b3e в test_outbox_group.py и test_outbox.py.
Аргументы send_message везде читаются по отдельным ключам (kw[...]) или через await_count и assert_not_awaited.
Проверок полного набора аргументов (assert_awaited_once_with, сравнение всего kwargs) нет.
Новых элементов в общие списки задача не добавляет. ШТАБ сверит этот вывод с кодом до промпта.
Упал тест вне списка — не чинить, написать «тест X вне списка» в ИТОГ и остановиться.
Цели: bash tools/check.sh bot. SQL бота CI на настоящей БД не проверяет; SQL эта задача не меняет.

## 10. Живая проверка (общая сессия И3, после выката bot)
Предусловия: тема «Карточки» создана, CARDS_TOPIC_ID задан, bot выкачен.
1. А1 сдаёт рефлексию. Ожидание: пост в теме «Рефлексии», под ним кнопка «📇 Карточка».
2. А1 (админ из ACCESS_ADMIN_IDS) нажимает кнопку. Ожидание: карточка пришла в тему «Карточки»,
   появился всплывающий ответ CARD_SENT.
3. Пост участника, у которого номер «—», выходит без кнопки. Если такого участника нет — пишем «не проверено».
4. Пост «День 2» (ladder_day2_alert) с кнопкой — проверяется, если он случится в сессии; иначе «не проверено».
В отчёте только метки А1–А3, без имён.

## 11. ЗАПРЕЩЕНО Агенту
- Править bot/card.py, bot/card_handlers.py, bot/texts.py, bot/config.py, bot/app.py, bot/access*.py,
  bot/handlers.py, bot/render.py, infra/**, .env.example, docs/**.
- Добавлять новые зависимости.
- Писать в логи callback_data и short_no.
- Выносить pid в callback_data или в текст поста.
- Действуют общие запреты AGENT-BRIEF §3: docs/architecture/**, .github/**, .githooks/**, .env; в main не пушить.
- Свои догадки о механике в код не вносить. Что-то неясно — вопрос ШТАБу в ИТОГЕ.

## 12. Критерии готовности
- Под постами обоих маршрутов стоит кнопка card:<short_no>; при short_no None кнопки нет.
- В личном пути ничего не изменилось.
- Тесты 1–5 из §9 зелёные, существующие тесты bot не правились.
- bash tools/check.sh bot зелёный.
- Описание PR по AGENT-BRIEF §10. «Команды для Автора»: до мержа — ничего; после мержа — выкат bot
  вместе с очередью И3, порядок назначит ШТАБ; миграции нет, бэкап не нужен.

## 13. Оценка
2 файла: outbox.py ≈ 10 строк, test_outbox_group.py ≈ 50 строк. Около 250–300 кредитов, около 0,5 ч Автора.

## 14. РЕВЬЮЕР
Да [ШТАБ]: кнопка открывает админу данные участника (callback привязан к участнику, P8 §8.6).

## Канон и решения
(а) Используются P8 §8.6 (callback привязан к participant_id) и P8 §8.5 (подпись — через Р-15, не меняется).
(б) С DECISIONS.md ничего не противоречит: Р-15 действует, задача подпись не трогает.
(в) Правок нет.
(г) Правок канона нет.
