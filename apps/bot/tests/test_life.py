"""Тесты /life +N | -N (bot-life-1): разбор, check, has_flag, предпросмотр, подтверждение. Без сети и Postgres."""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.methods import AnswerCallbackQuery, EditMessageText, GetMe, SendMessage
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from psycopg.types.json import Jsonb

from bot import life, texts
from bot.app import build_dispatcher
from bot.config import BotConfig
from bot.life import EVENT, FIND, KEY, LOCK, STATE

FAKE_TOKEN = "4702:TEST-token-not-real"
BOT_ID = 4702  # часть FAKE_TOKEN до «:» = Bot.id
GROUP, CARDS, ADMIN, STRANGER, TG_USER, MID, SHORT = 4701, 4703, 4704, 4705, 4706, 4707, 4708
PID = "00000000-0000-0000-0000-000000004709"
OP = "0123456789abcdef"


def cfg(**kw) -> BotConfig:
    base = dict(bot_token=FAKE_TOKEN, webapp_url="", log_level="INFO", database_url="postgresql://x/y",
                work_group_id=GROUP, cards_topic_id=CARDS, access_admin_ids=frozenset({ADMIN}))
    base.update(kw)
    return BotConfig(**base)


# --- подделка соединения (по образцу test_access) ---

class FakeCursor:
    def __init__(self, row=None, rowcount=1):
        self.row, self.rowcount = row, rowcount

    async def fetchone(self):
        return self.row


class _Tx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        self.conn.log.append("begin")

    async def __aexit__(self, exc_type, exc, tb):
        self.conn.log.append("rollback" if exc_type else "commit")
        return False


class FakeConn:
    def __init__(self, answer):
        self.answer, self.log, self.closed = answer, [], False

    async def execute(self, sql, params=None):
        self.log.append((sql, params))
        return self.answer(sql, params)

    def transaction(self):
        return _Tx(self)

    async def close(self):
        self.closed = True

    def sqls(self):
        return [e[0] for e in self.log if isinstance(e, tuple)]

    def params_of(self, sql):
        return [e[1] for e in self.log if isinstance(e, tuple) and e[0] == sql]


def db(state=("active", [], 2), found=True, key_rowcount=1):
    def answer(sql, params):
        if sql == FIND:
            return FakeCursor((PID, TG_USER) if found else None)
        if sql == STATE:
            return FakeCursor(state)
        if sql == KEY:
            return FakeCursor(None, rowcount=key_rowcount)
        return FakeCursor(None)
    return FakeConn(answer)


# --- разбор ---

@pytest.mark.parametrize(("args", "expected"), [
    ("+1", ("ok", None, 1)),
    ("-3", ("ok", None, -3)),
    ("#123456 +2", ("ok", 123456, 2)),
    ("2", (life.USAGE, None, None)),
    ("#123456 2", (life.USAGE, None, None)),
    ("+0", (life.USAGE, None, None)),
    ("+4", (life.USAGE, None, None)),
    ("abc", (life.USAGE, None, None)),
    ("#12x +1", (life.USAGE, None, None)),
    ("", (life.USAGE, None, None)),
    ("#9223372036854775808 +1", (life.NOT_FOUND, None, None)),
])
def test_parse_args(args, expected):
    assert life.parse_args(args) == expected


# --- check и has_flag ---

def test_check_codes_and_order():
    assert life.check("sleeping", [], 0, 1) == life.REFUSE_REVIVE          # REVIVE раньше фазы
    assert life.check("active", ["block_lives"], 2, 1) == life.REFUSE_REVIVE
    assert life.check("muted", [], 2, 1) == life.REFUSE_PHASE
    assert life.check("erased", [], 0, 1) == life.REFUSE_PHASE              # muted/erased раньше REVIVE
    assert life.check("active", [], 3, 1) == life.REFUSE_ABOVE_MAX
    assert life.check("active", [], 1, -2) == life.REFUSE_BELOW_ZERO
    assert life.check("onboarding", [], 2, -1) is None
    assert life.check(None, None, None, 1) == life.NOT_FOUND
    assert life.check("active", [], None, -1) == life.NOT_FOUND


def test_has_flag():
    assert life.has_flag(["block_lives"], "block_lives") is True
    assert life.has_flag(["other"], "block_lives") is False
    assert life.has_flag({"block_lives": True}, "block_lives") is True
    assert life.has_flag({"block_lives": False}, "block_lives") is False
    assert life.has_flag(None, "block_lives") is False


# --- подтверждение: life.apply ---

def test_apply_sql_order_payload_actor():
    conn = db(state=("active", [], 3))
    code = asyncio.run(life.apply(conn, SHORT, -1, OP))
    assert code == life.DONE
    assert conn.sqls() == [FIND, LOCK, STATE, KEY, EVENT]
    assert conn.log[0] == "begin" and conn.log[-1] == "commit"
    assert conn.params_of(LOCK) == [(PID,)] and isinstance(conn.params_of(LOCK)[0][0], str)
    assert conn.params_of(KEY) == [(f"life_op:{PID}:{OP}", "-1")]
    (pid, payload), = conn.params_of(EVENT)
    assert pid == PID and isinstance(payload, Jsonb)
    assert payload.obj == {"delta": -1, "reason": "author_cmd"} and type(payload.obj["delta"]) is int
    assert "'bot', 'owner'" in EVENT and "'life_op'" in EVENT
    for sql in (FIND, LOCK, STATE, KEY, EVENT):
        assert "RETURNING" not in sql.upper()


def test_apply_repeat_already_no_event():
    conn = db(key_rowcount=0)
    assert asyncio.run(life.apply(conn, SHORT, -1, OP)) == life.ALREADY
    assert EVENT not in conn.sqls()


@pytest.mark.parametrize(("state", "delta", "code"), [
    (("active", [], 3), 1, life.REFUSE_ABOVE_MAX),
    (("sleeping", [], 0), 1, life.REFUSE_REVIVE),
    (None, -1, life.NOT_FOUND),
])
def test_apply_refusal_no_key_no_event(state, delta, code):
    conn = db(state=state)
    assert asyncio.run(life.apply(conn, SHORT, delta, OP)) == code
    assert KEY not in conn.sqls() and EVENT not in conn.sqls()
    assert conn.log[-1] == "rollback"


# --- через Dispatcher (Bot API перехвачен) ---

async def _feed(config, update, conn):
    bot = Bot(token=FAKE_TOKEN)
    calls: list = []
    connected: list = []

    async def fake_request(_bot, method, timeout=None):
        calls.append(method)
        if isinstance(method, GetMe):
            return User(id=BOT_ID, is_bot=True, first_name="B", username="course_bot")
        if isinstance(method, SendMessage):
            return Message(message_id=MID + 1, date=datetime.now(), chat=Chat(id=method.chat_id, type="supergroup"),
                           text=method.text)
        return True

    bot.session.make_request = AsyncMock(side_effect=fake_request)

    async def connect(_dsn):
        connected.append(1)
        return conn

    dp = build_dispatcher(config, connect)
    await dp.feed_update(bot, update)
    await bot.session.close()
    return calls, connected


def _cmd(text, chat_id=GROUP, user=ADMIN):
    return Update(update_id=1, message=Message(
        message_id=MID, date=datetime.now(), chat=Chat(id=chat_id, type="supergroup"),
        from_user=User(id=user, is_bot=False, first_name="A"), text=text))


def _button(data, chat_id=GROUP, user=ADMIN, age=timedelta(0)):
    return Update(update_id=2, callback_query=CallbackQuery(
        id="cb1", from_user=User(id=user, is_bot=False, first_name="A"), chat_instance="ci", data=data,
        message=Message(message_id=MID, chat=Chat(id=chat_id, type="supergroup"), text="предпросмотр",
                        date=datetime.now(timezone.utc) - age)))


def _no_send_to_participant(calls):
    assert all(c.chat_id == GROUP for c in calls if isinstance(c, SendMessage))
    assert all(c.chat_id != TG_USER for c in calls if hasattr(c, "chat_id"))


def test_preview_no_insert_two_buttons_callback_len():
    conn = db(state=("active", [], 3))
    calls, _ = asyncio.run(_feed(cfg(), _cmd("/life@course_bot #004708 -1"), conn))
    assert conn.sqls() == [FIND, STATE]
    assert not any("INSERT" in s.upper() for s in conn.sqls())
    sends = [c for c in calls if isinstance(c, SendMessage)]
    assert len(sends) == 1
    assert sends[0].text == texts.LIFE_PREVIEW.format(num="004708", before=3, after=2)
    buttons = sends[0].reply_markup.inline_keyboard[0]
    assert len(buttons) == 2
    assert buttons[1].callback_data == "life:n"
    assert life.parse_callback(buttons[0].callback_data)[:3] == (life.CONFIRM, SHORT, -1)
    longest = life.confirm_data(life.BIGINT_MAX, -3, "f" * 16)
    for data in (buttons[0].callback_data, buttons[1].callback_data, longest):
        assert len(data.encode()) <= 64
    _no_send_to_participant(calls)


def test_preview_refusal_text_no_buttons():
    calls, _ = asyncio.run(_feed(cfg(), _cmd("/life #004708 +2"), db(state=("active", [], 2))))
    sends = [c for c in calls if isinstance(c, SendMessage)]
    assert [s.text for s in sends] == [texts.LIFE_REFUSE_ABOVE_MAX] and sends[0].reply_markup is None
    _no_send_to_participant(calls)


def test_confirm_done_edits_preview():
    conn = db(state=("active", [], 3))
    calls, _ = asyncio.run(_feed(cfg(), _button(life.confirm_data(SHORT, -1, OP)), conn))
    assert conn.sqls() == [FIND, LOCK, STATE, KEY, EVENT]
    edits = [c for c in calls if isinstance(c, EditMessageText)]
    assert len(edits) == 1 and edits[0].reply_markup is None and texts.LIFE_DONE in edits[0].text
    _no_send_to_participant(calls)


def test_confirm_repeat_already():
    conn = db(key_rowcount=0)
    calls, _ = asyncio.run(_feed(cfg(), _button(life.confirm_data(SHORT, -1, OP)), conn))
    assert EVENT not in conn.sqls()
    edits = [c for c in calls if isinstance(c, EditMessageText)]
    assert len(edits) == 1 and texts.LIFE_ALREADY in edits[0].text
    _no_send_to_participant(calls)


def test_confirm_stale_no_connect():
    conn = db()
    calls, connected = asyncio.run(_feed(cfg(), _button(life.confirm_data(SHORT, -1, OP),
                                                        age=timedelta(hours=1, seconds=5)), conn))
    assert connected == [] and conn.log == []
    edits = [c for c in calls if isinstance(c, EditMessageText)]
    assert len(edits) == 1 and edits[0].reply_markup is None and texts.LIFE_STALE in edits[0].text
    _no_send_to_participant(calls)


def test_cancel_no_db():
    conn = db()
    calls, connected = asyncio.run(_feed(cfg(), _button("life:n"), conn))
    assert connected == []
    edits = [c for c in calls if isinstance(c, EditMessageText)]
    assert len(edits) == 1 and edits[0].reply_markup is None and texts.LIFE_CANCELLED in edits[0].text
    _no_send_to_participant(calls)


@pytest.mark.parametrize(("chat_id", "user"), [(GROUP + 99, ADMIN), (GROUP, STRANGER)])
def test_command_stranger_ignored(chat_id, user):
    conn = db()
    calls, connected = asyncio.run(_feed(cfg(), _cmd("/life #004708 -1", chat_id=chat_id, user=user), conn))
    assert calls == [] and connected == []


@pytest.mark.parametrize(("chat_id", "user"), [(GROUP + 99, ADMIN), (GROUP, STRANGER)])
def test_button_stranger_answer_without_text(chat_id, user):
    conn = db()
    calls, connected = asyncio.run(_feed(cfg(), _button(life.confirm_data(SHORT, -1, OP), chat_id=chat_id,
                                                        user=user), conn))
    assert len(calls) == 1 and isinstance(calls[0], AnswerCallbackQuery) and calls[0].text is None
    assert connected == []


def test_router_not_included_when_card_disabled():
    dp = build_dispatcher(cfg(cards_topic_id=None))
    assert "life" not in [r.name for r in dp.sub_routers]
    assert "life" in [r.name for r in build_dispatcher(cfg()).sub_routers]
