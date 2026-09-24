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
