"""Тесты бота (Итерация 0-А): конфиг, /start, Menu Button — без сети."""
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.methods import SendMessage, SetChatMenuButton
from aiogram.types import Chat, Message, MenuButtonWebApp, Update, User

from bot import texts
from bot.app import build_dispatcher
from bot.config import BotConfig, ConfigError, is_valid_webapp_url

# Формально валидный токен (формат id:secret) — Bot() проверяет только формат.
FAKE_TOKEN = "123456:TEST-token-not-real"
WEBAPP = "https://miniapp.example.test/"


def make_config(webapp_url: str = WEBAPP) -> BotConfig:
    return BotConfig(bot_token=FAKE_TOKEN, webapp_url=webapp_url, log_level="INFO")


def test_config_requires_token():
    with pytest.raises(ConfigError):
        BotConfig.from_env({})


def test_config_reads_env():
    cfg = BotConfig.from_env({"BOT_TOKEN": FAKE_TOKEN, "WEBAPP_URL": f"  {WEBAPP} "})
    assert cfg.webapp_url == WEBAPP
    assert cfg.webapp_enabled


@pytest.mark.parametrize(
    ("url", "ok"),
    [(WEBAPP, True), ("http://insecure.test", False), ("", False), ("https://", False)],
)
def test_webapp_url_must_be_https(url, ok):
    assert is_valid_webapp_url(url) is ok


def _start_update(chat_type: str = "private") -> Update:
    user = User(id=42, is_bot=False, first_name="Test")
    chat = Chat(id=42 if chat_type == "private" else -100, type=chat_type)
    msg = Message(message_id=1, date=datetime.now(), chat=chat, from_user=user, text="/start")
    return Update(update_id=1, message=msg)


async def _feed(config: BotConfig, update: Update) -> list:
    bot = Bot(token=FAKE_TOKEN)
    calls: list = []

    async def fake_request(_bot, method, timeout=None):  # перехват всех Bot API вызовов
        calls.append(method)
        return True

    bot.session.make_request = AsyncMock(side_effect=fake_request)
    dp = build_dispatcher(config)
    await dp.feed_update(bot, update)
    await bot.session.close()
    return calls


def test_start_private_sets_menu_button_and_greets():
    calls = asyncio.run(_feed(make_config(), _start_update()))
    menu = [c for c in calls if isinstance(c, SetChatMenuButton)]
    sends = [c for c in calls if isinstance(c, SendMessage)]
    assert len(menu) == 1 and menu[0].chat_id == 42
    assert isinstance(menu[0].menu_button, MenuButtonWebApp)
    assert menu[0].menu_button.web_app.url == WEBAPP
    assert len(sends) == 1
    kb = sends[0].reply_markup.inline_keyboard
    assert kb[0][0].web_app.url == WEBAPP


def test_start_with_webapp_url_keeps_current_text():
    # Поведение при заданном WEBAPP_URL не меняется: приветствие + кнопка.
    calls = asyncio.run(_feed(make_config(), _start_update()))
    sends = [c for c in calls if isinstance(c, SendMessage)]
    assert len(sends) == 1
    assert sends[0].text == f"{texts.START_WELCOME}\n\n{texts.FALLBACK_UPDATE_TELEGRAM}"
    assert sends[0].reply_markup is not None


@pytest.mark.parametrize("webapp_url", ["", "http://insecure.test/"])
def test_start_without_https_webapp_url_says_not_connected(webapp_url):
    calls = asyncio.run(_feed(make_config(webapp_url=webapp_url), _start_update()))
    assert not [c for c in calls if isinstance(c, SetChatMenuButton)]
    sends = [c for c in calls if isinstance(c, SendMessage)]
    assert len(sends) == 1 and sends[0].reply_markup is None
    assert sends[0].text == texts.MINIAPP_NOT_CONNECTED
    assert "ещё не подключён" in sends[0].text
    # Совет «обновите Telegram» здесь не к месту.
    assert "последнюю версию Telegram" not in sends[0].text


def test_start_in_group_is_ignored():
    calls = asyncio.run(_feed(make_config(), _start_update(chat_type="supergroup")))
    assert calls == []


def test_wait_until_no_webhook_polls_until_cleared(monkeypatch):
    from types import SimpleNamespace

    from bot import app as bot_app

    infos = [SimpleNamespace(url="https://x.test/webhook/telegram"), SimpleNamespace(url="")]
    bot = SimpleNamespace(get_webhook_info=AsyncMock(side_effect=infos))
    sleeps: list[int] = []

    async def fake_sleep(sec):
        sleeps.append(sec)

    monkeypatch.setattr(bot_app.asyncio, "sleep", fake_sleep)
    asyncio.run(bot_app.wait_until_no_webhook(bot, recheck_seconds=7))
    assert sleeps == [7]
    assert bot.get_webhook_info.await_count == 2
