"""Тесты карточки участника (bot-i3-1): config, разбор номера, render_card, /card и кнопка card: — без сети и БД."""
import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.methods import AnswerCallbackQuery, SendMessage
from aiogram.types import (CallbackQuery, Chat, InlineKeyboardButton, InlineKeyboardMarkup, Message,
                           Update, User)

from bot import card, texts
from bot.app import build_dispatcher
from bot.config import BotConfig, ConfigError

FAKE_TOKEN = "123456:TEST-token-not-real"
BOT_ID = 123456
DSN = "postgresql://bot@db/test"
GROUP = -1001
CARDS = 77
ADMIN = 11
STRANGER = 22
PID = "pid-1"
TG = 555
REG = datetime(2026, 11, 1, 9, 30, tzinfo=timezone.utc)


def make_config(**kw) -> BotConfig:
    base = dict(bot_token=FAKE_TOKEN, webapp_url="", log_level="INFO", database_url=DSN,
                work_group_id=GROUP, cards_topic_id=CARDS, access_admin_ids=frozenset({ADMIN}))
    base.update(kw)
    return BotConfig(**base)


class FakeCursor:
    def __init__(self, result):
        self._result = result

    async def fetchone(self):
        return self._result

    async def fetchall(self):
        return self._result or []


class FakeDb:
    """connect(dsn) → соединение; пишет SQL и параметры в общий журнал."""

    def __init__(self, log, find=(PID, TG, REG), state=None, rows=None, fail_audit=False):
        self.log, self.connects = log, 0
        self.results = {card.FIND: find, card.STATE: state, card.MEASUREMENTS: rows or []}
        self.fail_audit = fail_audit
        self.params = {}

    async def __call__(self, dsn):
        self.connects += 1
        db = self

        class Conn:
            async def execute(self, sql, params=None):
                db.log.append(sql)
                db.params[sql] = params
                if sql == card.AUDIT and db.fail_audit:
                    raise RuntimeError("audit failed")
                return FakeCursor(db.results.get(sql))

            async def close(self):
                pass

        return Conn()


async def _feed(config: BotConfig, update: Update, db: FakeDb, log: list) -> list:
    bot = Bot(token=FAKE_TOKEN)
    calls: list = []

    async def fake_request(_bot, method, timeout=None):
        calls.append(method)
        log.append(method)
        return True

    bot.session.make_request = AsyncMock(side_effect=fake_request)
    dp = build_dispatcher(config, connect=db)
    await dp.feed_update(bot, update)
    await bot.session.close()
    return calls


def _msg(text, user_id=ADMIN, chat_id=GROUP, reply=None, thread_id=None) -> Message:
    return Message(message_id=10, date=datetime.now(), chat=Chat(id=chat_id, type="supergroup"),
                   from_user=User(id=user_id, is_bot=False, first_name="A"), text=text,
                   reply_to_message=reply, message_thread_id=thread_id)


def _card_sends(calls):
    return [c for c in calls if isinstance(c, SendMessage) and c.message_thread_id == CARDS]


# 1
def test_config_cards_topic_and_card_enabled():
    env = {"BOT_TOKEN": FAKE_TOKEN, "BOT_DATABASE_URL": DSN, "WORK_GROUP_ID": "-1001",
           "ACCESS_ADMIN_IDS": "11", "CARDS_TOPIC_ID": " 77 "}
    cfg = BotConfig.from_env(env)
    assert cfg.cards_topic_id == 77 and cfg.card_enabled and cfg.card_missing_vars() == []
    with pytest.raises(ConfigError):
        BotConfig.from_env({**env, "CARDS_TOPIC_ID": "x"})
    for name in ("BOT_DATABASE_URL", "WORK_GROUP_ID", "CARDS_TOPIC_ID", "ACCESS_ADMIN_IDS"):
        cfg = BotConfig.from_env({k: v for k, v in env.items() if k != name})
        assert not cfg.card_enabled and cfg.card_missing_vars() == [name]


# 2
def test_parse_arg_and_callback():
    assert card.parse_arg("#000123") == 123
    assert card.parse_arg("  #000123 ") == 123
    for bad in ("123", "@user", "", None, "card:x"):
        assert card.parse_arg(bad) is None
    assert card.parse_callback("card:123") == 123
    for bad in ("card:x", "card:", "123", "", None, "#000123", "acc:g:1"):
        assert card.parse_callback(bad) is None


# 3
def test_number_from_reply():
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="x", callback_data="card:7")]])
    assert card.number_from_reply(SimpleNamespace(reply_markup=kb, text="#000042", caption=None)) == 7
    assert card.number_from_reply(SimpleNamespace(reply_markup=None, text=None, caption="Пост\n#000042 x")) is None
    assert card.number_from_reply(SimpleNamespace(reply_markup=None, text="Пост\n\n#999", caption=None)) is None
    assert card.number_from_reply(SimpleNamespace(reply_markup=None, text="Участник #— (ID 1)", caption=None)) is None


def _rows(*items):
    return [(kind, zone, weight, REG) for kind, zone, weight in items]


# 4
def test_render_card_full():
    state = ("active", 1, 2, 3, 4, "Europe/Moscow")
    rows = _rows(("body", None, Decimal("80.5")), ("checkup", "yellow", None),
                 ("body", None, Decimal("78.0")), ("checkup", "green", None))
    out = card.render_card(42, TG, REG, state, rows)
    assert f'<a href="tg://user?id={TG}">' in out and "#000042" in out
    assert texts.CARD_WEIGHT.format(start="80.5", current="78.0") in out
    assert texts.CARD_ZONE_BETTER in out and "yellow → green" in out
    assert texts.CARD_STATUS_ACTIVE in out
    assert texts.CARD_LIVES.format(n=4) in out and texts.CARD_LIVES_LOG in out
    for line in (texts.CARD_PAYMENTS, texts.CARD_PAUSES, texts.CARD_RETURNS):
        assert line.format(value=texts.CARD_NO_DATA) in out
    assert "Europe/Moscow" in out

    worse = card.render_card(42, TG, REG, state, _rows(("checkup", "green", None), ("checkup", "red", None)))
    assert texts.CARD_ZONE_WORSE in worse
    same = card.render_card(42, TG, REG, state, _rows(("checkup", "red", None), ("checkup", "red", None)))
    assert texts.CARD_ZONE_SAME in same
    one = card.render_card(42, TG, REG, state, _rows(("checkup", "red", None)))
    assert not any(m in one for m in (texts.CARD_ZONE_BETTER, texts.CARD_ZONE_WORSE, texts.CARD_ZONE_SAME))

    sleeping = card.render_card(42, TG, REG, ("sleeping", 1, 2, 3, 4, None), [])
    assert texts.CARD_STATUS_SLEEPING in sleeping
    raw = card.render_card(42, TG, REG, ("<x>", 1, 2, 3, 4, None), [])
    assert texts.CARD_STATUS_RAW.format(code="&lt;x&gt;") in raw and "<x>" not in raw


# 5
def test_render_card_without_state_and_rows():
    out = card.render_card(1, TG, REG, None, [])
    assert texts.CARD_TZ.format(tz=texts.CARD_NO_DATA) in out
    assert texts.CARD_WEIGHT.format(start=texts.CARD_NO_DATA, current=texts.CARD_NO_DATA) in out
    assert texts.CARD_LIVES_LOG in out
    assert texts.CARD_REGISTERED.format(date="01.11.2026 12:30 МСК") in out


# 6
def test_card_by_number_from_admin():
    log: list = []
    db = FakeDb(log, state=("active", 1, 1, 1, 3, "Europe/Moscow"))
    calls = asyncio.run(_feed(make_config(), Update(update_id=1, message=_msg("/card #000123")), db, log))
    sends = [c for c in calls if isinstance(c, SendMessage)]
    assert len(sends) == 1
    send = sends[0]
    assert send.chat_id == GROUP and send.message_thread_id == CARDS and send.parse_mode == "HTML"
    assert log.index(card.AUDIT) < log.index(send)
    assert db.params[card.FIND] == (123,)
    assert db.params[card.AUDIT] == (str(ADMIN), PID)


# 7
def test_card_by_reply_to_bot_post():
    log: list = []
    db = FakeDb(log)
    post = Message(message_id=5, date=datetime.now(), chat=Chat(id=GROUP, type="supergroup"),
                   from_user=User(id=BOT_ID, is_bot=True, first_name="Bot"),
                   caption="[заглушка] Рефлексия\n" + texts.GROUP_WHO.format(num="000042", tg_id=TG, link="написать")
                   + "\n\n#999")
    calls = asyncio.run(_feed(make_config(), Update(update_id=1, message=_msg("/card", reply=post)), db, log))
    assert len(_card_sends(calls)) == 1 and db.params[card.FIND] == (42,)


# 8
@pytest.mark.parametrize(("user_id", "chat_id"), [(STRANGER, GROUP), (ADMIN, -999)])
def test_card_from_stranger_or_other_chat_ignored(user_id, chat_id):
    log: list = []
    db = FakeDb(log)
    msg = _msg("/card #000123", user_id=user_id, chat_id=chat_id)
    calls = asyncio.run(_feed(make_config(), Update(update_id=1, message=msg), db, log))
    assert calls == [] and db.connects == 0


# 9
def test_card_ask_id_and_not_found():
    log: list = []
    db = FakeDb(log)
    calls = asyncio.run(_feed(make_config(), Update(update_id=1, message=_msg("/card")), db, log))
    assert [c.text for c in calls if isinstance(c, SendMessage)] == [texts.CARD_ASK_ID] and db.connects == 0

    log2: list = []
    db2 = FakeDb(log2, find=None)
    calls = asyncio.run(_feed(make_config(), Update(update_id=2, message=_msg("/card #000999")), db2, log2))
    assert [c.text for c in calls if isinstance(c, SendMessage)] == [texts.CARD_NOT_FOUND]
    assert card.AUDIT not in log2


# 10
def test_audit_failure_sends_nothing_to_cards():
    log: list = []
    db = FakeDb(log, fail_audit=True)
    calls = asyncio.run(_feed(make_config(), Update(update_id=1, message=_msg("/card #000123")), db, log))
    assert _card_sends(calls) == []
    assert [c.text for c in calls if isinstance(c, SendMessage)] == [texts.CARD_TRY_LATER]


def _callback(user_id, data="card:123") -> Update:
    msg = Message(message_id=5, date=datetime.now(), chat=Chat(id=GROUP, type="supergroup"),
                  from_user=User(id=BOT_ID, is_bot=True, first_name="Bot"), text="пост")
    cq = CallbackQuery(id="1", from_user=User(id=user_id, is_bot=False, first_name="A"),
                       chat_instance="ci", data=data, message=msg)
    return Update(update_id=1, callback_query=cq)


# 11
def test_callback_card():
    log: list = []
    db = FakeDb(log)
    calls = asyncio.run(_feed(make_config(), _callback(ADMIN), db, log))
    assert len(_card_sends(calls)) == 1
    answers = [c for c in calls if isinstance(c, AnswerCallbackQuery)]
    assert len(answers) == 1 and answers[0].text == texts.CARD_SENT

    log2: list = []
    db2 = FakeDb(log2)
    calls = asyncio.run(_feed(make_config(), _callback(STRANGER), db2, log2))
    assert len(calls) == 1 and isinstance(calls[0], AnswerCallbackQuery) and calls[0].text is None
    assert db2.connects == 0


# 12
def test_card_disabled_without_cards_topic(caplog):
    log: list = []
    db = FakeDb(log)
    with caplog.at_level(logging.WARNING, logger="bot.app"):
        calls = asyncio.run(_feed(make_config(cards_topic_id=None),
                                  Update(update_id=1, message=_msg("/card #000123")), db, log))
    assert not [c for c in calls if isinstance(c, SendMessage)]
    warnings = [r.getMessage() for r in caplog.records if r.getMessage().startswith("Карточка выключена")]
    assert len(warnings) == 1
    assert "CARDS_TOPIC_ID" in warnings[0] and "BOT_DATABASE_URL" not in warnings[0]


# Т1
def test_t1_number_from_reply_only_who_line():
    def post(text):
        return SimpleNamespace(reply_markup=None, text=text, caption=None)

    assert card.number_from_reply(post("Участник #000042 (ID 555) → написать")) == 42
    assert card.number_from_reply(post("Участник #000001 (ID 1) → написать (@u · ID 5) → написать")) is None
    assert card.number_from_reply(post("Код: #000042")) is None


# Т2
def test_t2_nineteen_digits_and_bigint():
    big = 9223372036854775807
    assert card.parse_arg(f"#{big}") == big
    assert card.parse_arg(f"#{big + 1}") is None
    assert card.parse_arg("#" + "1" * 20) is None
    assert card.parse_callback(f"card:{big}") == big
    assert card.parse_callback(f"card:{big + 1}") is None
    assert card.parse_callback("card:" + "1" * 20) is None


# Т3
def test_t3_reply_to_topic_root_asks_id():
    log: list = []
    db = FakeDb(log)
    root = Message(message_id=5, date=datetime.now(), chat=Chat(id=GROUP, type="supergroup"),
                   from_user=User(id=BOT_ID, is_bot=True, first_name="Bot"), text="тема")
    msg = _msg("/card", reply=root, thread_id=5)
    calls = asyncio.run(_feed(make_config(), Update(update_id=1, message=msg), db, log))
    assert [c.text for c in calls if isinstance(c, SendMessage)] == [texts.CARD_ASK_ID]
    assert db.connects == 0


# Т4
def test_t4_reply_to_not_bot_post_not_found():
    log: list = []
    db = FakeDb(log)
    post = Message(message_id=5, date=datetime.now(), chat=Chat(id=GROUP, type="supergroup"),
                   from_user=User(id=STRANGER, is_bot=False, first_name="S"),
                   text="Участник #000042 (ID 555) → написать")
    calls = asyncio.run(_feed(make_config(), Update(update_id=1, message=_msg("/card", reply=post)), db, log))
    assert [c.text for c in calls if isinstance(c, SendMessage)] == [texts.CARD_NOT_FOUND]
    assert db.connects == 0


# Т5
def test_t5_bad_arg_asks_id():
    log: list = []
    db = FakeDb(log)
    calls = asyncio.run(_feed(make_config(), Update(update_id=1, message=_msg("/card abc")), db, log))
    assert [c.text for c in calls if isinstance(c, SendMessage)] == [texts.CARD_ASK_ID]
    assert db.connects == 0


# Т6
def test_t6_callback_from_admin_in_other_chat():
    log: list = []
    db = FakeDb(log)
    msg = Message(message_id=5, date=datetime.now(), chat=Chat(id=-999, type="supergroup"),
                  from_user=User(id=BOT_ID, is_bot=True, first_name="Bot"), text="пост")
    cq = CallbackQuery(id="1", from_user=User(id=ADMIN, is_bot=False, first_name="A"),
                       chat_instance="ci", data="card:123", message=msg)
    calls = asyncio.run(_feed(make_config(), Update(update_id=1, callback_query=cq), db, log))
    assert len(calls) == 1 and isinstance(calls[0], AnswerCallbackQuery) and calls[0].text is None
    assert db.connects == 0


# Т7
def test_t7_reply_failure_does_not_raise(caplog):
    log: list = []
    db = FakeDb(log)

    async def run():
        bot = Bot(token=FAKE_TOKEN)

        async def fake_request(_bot, method, timeout=None):
            if isinstance(method, SendMessage):
                raise RuntimeError("telegram down")
            return True

        bot.session.make_request = AsyncMock(side_effect=fake_request)
        dp = build_dispatcher(make_config(), connect=db)
        await dp.feed_update(bot, Update(update_id=1, message=_msg("/card abc")))
        await bot.session.close()

    with caplog.at_level(logging.WARNING, logger="bot.card_handlers"):
        asyncio.run(run())
    warnings = [r for r in caplog.records if r.name == "bot.card_handlers" and r.levelno == logging.WARNING]
    assert any(r.getMessage().startswith("card: ответ не отправлен") for r in warnings)
    assert db.connects == 0


# Т8
def test_t8_logs_without_ids(caplog):
    msg = Message(message_id=5, date=datetime.now(), chat=Chat(id=-999, type="supergroup"),
                  from_user=User(id=BOT_ID, is_bot=True, first_name="Bot"), text="пост")
    cq = CallbackQuery(id="1", from_user=User(id=ADMIN, is_bot=False, first_name="A"),
                       chat_instance="ci", data="card:123", message=msg)
    with caplog.at_level(logging.DEBUG, logger="bot.card_handlers"):
        log: list = []
        asyncio.run(_feed(make_config(), Update(update_id=1, callback_query=cq), FakeDb(log), log))
        log2: list = []
        asyncio.run(_feed(make_config(), Update(update_id=2, message=_msg("/card #000123")),
                          FakeDb(log2, fail_audit=True), log2))
    messages = [r.getMessage() for r in caplog.records if r.name == "bot.card_handlers"]
    assert messages
    for text in messages:
        assert "555" not in text and "000123" not in text and PID not in text
