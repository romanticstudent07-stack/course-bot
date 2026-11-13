"""apps/bot/bot/texts.py — ВРЕМЕННЫЕ тексты бота (Итерация 0-А).

По И4 единственный источник текстов — text_registry ({домен}.{имя}, три тона,
legal_status). Он появится в Итерации 1; тогда эти строки переедут туда.
Ключи ниже — предварительные имена в формате {домен}.{имя}.
"""
from __future__ import annotations

# bot.start_welcome
START_WELCOME = (
    "Здравствуйте! Это бот курса.\n\n"
    "Всё обучение проходит в Mini App — откройте его кнопкой меню внизу "
    "или кнопкой под этим сообщением."
)

# bot.miniapp_button
MINIAPP_BUTTON = "Открыть Mini App"

# bot.fallback_update_telegram (DIVISION.md, «Fallback-заглушка»)
FALLBACK_UPDATE_TELEGRAM = (
    "Установите последнюю версию Telegram и откройте кнопку меню."
)

# bot.miniapp_not_connected — WEBAPP_URL пуст или не HTTPS: публичный
# HTTPS-вход для Mini App ещё не подключён. Совет «обновите Telegram» здесь
# НЕ даём — причина на нашей стороне, а не в клиенте пользователя.
# TODO(Итерация 1): перенести в text_registry.
MINIAPP_NOT_CONNECTED = (
    "Здравствуйте! Это бот курса.\n\n"
    "Mini App ещё не подключён. Когда он заработает, здесь появится кнопка для входа."
)


# --- Доступ по промокоду (bot-access-1, Р-2). Заглушки на «Вы». ---

# bot.access_prompt
ACCESS_PROMPT = "Введите, пожалуйста, промокод."
# bot.access_request_sent
ACCESS_REQUEST_SENT = "Спасибо! Заявка отправлена, дождитесь ответа."
# bot.access_pending
ACCESS_PENDING = "Ваша заявка на проверке, дождитесь ответа."
# bot.access_send_text
ACCESS_SEND_TEXT = "Отправьте кодовое слово текстом."
# bot.access_granted
ACCESS_GRANTED = "Доступ открыт, можно продолжать."
# bot.access_denied_retry — {n}: сколько попыток осталось
ACCESS_DENIED_RETRY = "Код не подошёл. Попробуйте ещё раз. Осталось попыток: {n}."
# bot.access_denied_last
ACCESS_DENIED_LAST = "Код не подошёл. Осталась 1 попытка."
# bot.access_locked — {until}: «дд.мм.гггг чч:мм МСК»
ACCESS_LOCKED = "Попытки закончились. Попробуйте после {until}."
# bot.access_try_later
ACCESS_TRY_LATER = "Не удалось отправить заявку, попробуйте позже."

# --- Админ-тема Рабочей группы (HTML; подстановки экранирует bot/access.py) ---

# bot.access_admin_request — {word}: кодовое слово, {who}: «Имя (@username · ID N) → написать»
ACCESS_ADMIN_REQUEST = "Заявка на доступ\nКод: <code>{word}</code>\n{who}"
# bot.access_admin_write — текст ссылки tg://user?id
ACCESS_ADMIN_WRITE = "написать"
# bot.access_button_grant
ACCESS_BUTTON_GRANT = "Выдать доступ"
# bot.access_button_deny
ACCESS_BUTTON_DENY = "Запретить"
# bot.access_admin_granted — {time}: «дд.мм.гггг чч:мм МСК»
ACCESS_ADMIN_GRANTED = "Выдан доступ · {time}"
# bot.access_admin_denied — {k} из {max}, {time}
ACCESS_ADMIN_DENIED = "Запрещено {k} из {max} · {time}"
# bot.access_already_granted
ACCESS_ALREADY_GRANTED = "Доступ уже выдан."
# bot.access_already_decided
ACCESS_ALREADY_DECIDED = "Уже решено."
# bot.access_reply_required
ACCESS_REPLY_REQUIRED = "Ответьте командой на сообщение-заявку."
# bot.access_request_not_found
ACCESS_REQUEST_NOT_FOUND = "Заявка не найдена: ответьте на сообщение-заявку бота."

# --- Темы Рабочей группы (bot-group-1, Р-15). HTML; подстановки экранирует bot/outbox.py ---

# bot.group_who — {num}: short_no из 6 цифр или «—», {tg_id}: числовой id, {link}: ссылка tg://user?id
GROUP_WHO = "Участник #{num} (ID {tg_id}) → {link}"
# bot.group_write — текст ссылки tg://user?id
GROUP_WRITE = "написать"
# bot.group_day2_alert — {who}: подпись GROUP_WHO
GROUP_DAY2_ALERT = "[заглушка] День 2: пришёл, но не отправил.\n{who}"
# bot.group_reflection — {s}, {m}, {d}: этап, модуль, день; {time}: «дд.мм.гггг чч:мм МСК»; {body}: текст
GROUP_REFLECTION = "[заглушка] Рефлексия · этап {s} · модуль {m} · день {d} · {time}\n{who}\n\n{body}"

# --- Карточка (bot-i3-1). Заглушки. HTML; подстановки из БД экранирует bot/card.py ---

# bot.card_button — кнопка под постами (ставит bot-i3-2)
CARD_BUTTON = "📇 Карточка"
# bot.card_ask_id
CARD_ASK_ID = "[заглушка] Уточните участника: /card #NNNNNN или ответом на пост бота."
# bot.card_not_found
CARD_NOT_FOUND = "[заглушка] Участник не найден."
# bot.card_try_later
CARD_TRY_LATER = "[заглушка] Не удалось собрать карточку, попробуйте позже."
# bot.card_sent
CARD_SENT = "[заглушка] Карточка отправлена в тему «Карточки»."
# bot.card_title
CARD_TITLE = "[заглушка] Карточка участника"
# bot.card_no_data
CARD_NO_DATA = "нет данных"
# bot.card_tz — {tz}: IANA-пояс или «нет данных»
CARD_TZ = "[заглушка] Часовой пояс: {tz}"
# bot.card_weight — {start}, {current}: вес или «нет данных»
CARD_WEIGHT = "[заглушка] Вес: {start} → {current}"
# bot.card_zone — {start}, {last}: код зоны; {mark}: пометка или пусто
CARD_ZONE = "[заглушка] Чек-Ап-зона: {start} → {last}{mark}"
# bot.card_zone_better
CARD_ZONE_BETTER = "[заглушка] улучшение"
# bot.card_zone_worse
CARD_ZONE_WORSE = "[заглушка] ухудшение"
# bot.card_zone_same
CARD_ZONE_SAME = "[заглушка] зона прежняя"
# bot.card_position — {s}, {m}, {d}: этап, модуль, день
CARD_POSITION = "[заглушка] Позиция: этап {s} · модуль {m}.{d}"
# bot.card_status_active
CARD_STATUS_ACTIVE = "Заглушка: активен"
# bot.card_status_sleeping
CARD_STATUS_SLEEPING = "Заглушка: спящий"
# bot.card_status_raw — {code}: lifecycle_phase как есть (экранирован)
CARD_STATUS_RAW = "статус: {code}"
# bot.card_lives — {n}: осталось жизней
CARD_LIVES = "Жизни: осталось {n}"
# bot.card_lives_log
CARD_LIVES_LOG = "Заглушка: журнал списаний — позже"
# bot.card_payments — {value}
CARD_PAYMENTS = "[заглушка] Оплаты: {value}"
# bot.card_pauses — {value}
CARD_PAUSES = "[заглушка] Паузы: {value}"
# bot.card_returns — {value}
CARD_RETURNS = "[заглушка] Возвраты на закрепление: {value}"
# bot.card_registered — {date}: «дд.мм.гггг чч:мм МСК»
CARD_REGISTERED = "[заглушка] Дата регистрации: {date}"
