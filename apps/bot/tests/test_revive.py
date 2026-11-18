"""Тесты /revive (bot-revive-1): разбор, check, count_returned, предпросмотр, подтверждение. Без сети и Postgres."""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.methods import AnswerCallbackQuery, EditMessageText, GetMe, SendMessage
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from psycopg.types.json import Jsonb

from bot import revive, texts
from bot.app import build_dispatcher
from bot.config import BotConfig
from bot.life import BIGINT_MAX, FIND, LOCK
from bot.revive import AFTER, EVENT, KEY, STATE, WRITEOFFS

FAKE_TOKEN = "5022:TEST-token-not-real"
BOT_ID = 5022  # часть FAKE_TOKEN до «:» = Bot.id
GROUP, CARDS, ADMIN, STRANGER, TG_USER, MID, SHORT = 5021, 5023, 5024, 5025, 5026, 5027, 5028
PID = "00000000-0000-0000-0000-000000005029"
OP = "0123456789abcdef"
AFTER_ID = 5030
BLOCKED = ("active", ["block_lives"], 2, 3, 5)
ROWS = [(5031, 2, 2, 4), (5032, 2, 3, 1), (5033, 2, 3, 5), (5034, 1, 5, 5)]


def cfg(**kw) -> BotConfig:
    base = dict(bot_token=FAKE_TOKEN, webapp_url="", log_level="INFO", database_url="postgresql://x/y",
                work_group_id=GROUP, cards_topic_id=CARDS, access_admin_ids=frozenset({ADMIN}))
    base.update(kw)
    return BotConfig(**base)


# --- подделка соединения (по образцу test_life) ---

class FakeCursor:
    def __init__(self, row=None, rowcount=1, rows=None):
        self.row, self.rowcount, self.rows = row, rowcount, rows or []

    async def fetchone(self):
        return self.row

    async def fetchall(self):
        return self.rows


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


def db(state=BLOCKED, found=True, key_rowcount=1, rows=ROWS):
    def answer(sql, params):
        if sql == FIND:
            return FakeCursor((PID, TG_USER) if found else None)
        if sql == STATE:
            return FakeCursor(state)
        if sql == AFTER:
            return FakeCursor((AFTER_ID,))
        if sql == WRITEOFFS:
            return FakeCursor(rows=rows)
        if sql == KEY:
            return FakeCursor(None, rowcount=key_rowcount)
        return FakeCursor(None)
    return FakeConn(answer)


# --- разбор ---

@pytest.mark.parametrize(("args", "expected"), [
    ("", ("ok", None, None, None)),
    ("2.3", ("ok", None, 2, 3)),
    ("#123456", ("ok", 123456, None, None)),
    ("#123456 2.3", ("ok", 123456, 2, 3)),
    ("0.1", (revive.USAGE, None, None, None)),
    ("2.0", (revive.USAGE, None, None, None)),
    ("2.", (revive.USAGE, None, None, None)),
    ("abc", (revive.USAGE, None, None, None)),
    ("#9223372036854775808", (revive.NOT_FOUND, None, None, None)),
])
def test_parse_args(args, expected):
    assert revive.parse_args(args) == expected


# --- check ---

def test_check_codes_and_order():
    assert revive.check(None, None, None, None, None, (None, None, 1)) == revive.NOT_FOUND
    assert revive.check("muted", ["block_lives"], 2, 3, 5, (2, 3, 1)) == revive.REFUSE_PHASE
    assert revive.check("erased", ["block_lives"], 2, 3, 5, (2, 3, 1)) == revive.REFUSE_PHASE
    assert revive.check("active", [], 2, 3, 5, (2, 3, 1)) == revive.REFUSE_NOT_BLOCKED
    assert revive.check("active", ["block_lives"], None, None, None, (None, 1, 1)) == revive.REFUSE_NO_POSITION
    assert revive.check("active", ["block_lives"], 2, 3, 5, (1, 3, 1)) == revive.REFUSE_STAGE
    assert revive.check("active", ["block_lives"], 2, 3, 5, (2, 3, 6)) == revive.REFUSE_AHEAD
    assert revive.check("active", ["block_lives"], 2, 3, 5, (2, 4, 1)) == revive.REFUSE_AHEAD
    assert revive.check("active", ["block_lives"], 2, 3, 5, (2, 3, 5)) is None
    assert revive.check("active", ["block_lives"], 2, 3, 5, (2, 1, 1)) is None


# --- count_returned ---

def test_count_returned():
    assert revive.count_returned(ROWS, (2, 3, 1)) == 2
    assert revive.count_returned(ROWS, (2, 3, 5)) == 1  # день-цель включительно
    assert revive.count_returned([], (2, 3, 1)) == 0
    assert type(revive.count_returned(ROWS, (2, 3, 1))) is int


# --- через Dispatcher (Bot API перехвачен) ---

async def _feed(config, update, conn, fail_user_send=False):
    bot = Bot(token=FAKE_TOKEN)
    calls: list = []
    connected: list = []
    at_send: list = []

    async def fake_request(_bot, method, timeout=None):
        calls.append(method)
        if isinstance(method, GetMe):
            return User(id=BOT_ID, is_bot=True, first_name="B", username="course_bot")
        if isinstance(method, SendMessage):
            if method.chat_id == TG_USER:
                at_send.append(conn.log[-1] if conn.log else None)
                if fail_user_send:
                    raise RuntimeError("telegram down")
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
    return calls, connected, at_send


def _cmd(text, chat_id=GROUP, user=ADMIN):
    return Update(update_id=1, message=Message(
        message_id=MID, date=datetime.now(), chat=Chat(id=chat_id, type="supergroup"),
        from_user=User(id=user, is_bot=False, first_name="A"), text=text))


def _button(data, chat_id=GROUP, user=ADMIN, age=timedelta(0)):
    return Update(update_id=2, callback_query=CallbackQuery(
        id="cb1", from_user=User(id=user, is_bot=False, first_name="A"), chat_instance="ci", data=data,
        message=Message(message_id=MID, chat=Chat(id=chat_id, type="supergroup"), text="предпросмотр",
                        date=datetime.now(timezone.utc) - age)))


def _user_sends(calls):
    return [c for c in calls if isinstance(c, SendMessage) and c.chat_id == TG_USER]


def _assert_no_returning():
    for sql in (FIND, LOCK, STATE, AFTER, WRITEOFFS, KEY, EVENT):
        assert "RETURNING" not in sql.upper()


# --- предпросмотр ---

def test_preview_no_insert_default_target_two_buttons():
    conn = db()
    calls, _, _ = asyncio.run(_feed(cfg(), _cmd("/revive@course_bot #005028"), conn))
    assert conn.sqls() == [FIND, STATE, AFTER, WRITEOFFS]
    assert not any("INSERT" in s.upper() for s in conn.sqls()) and LOCK not in conn.sqls()
    assert conn.params_of(WRITEOFFS) == [(PID, AFTER_ID)]
    sends = [c for c in calls if isinstance(c, SendMessage)]
    assert len(sends) == 1
    # target по умолчанию — (stage, module, 1) = (2, 3, 1): строки (2,3,1), (2,3,5) → 2
    assert sends[0].text == texts.REVIVE_PREVIEW.format(num="005028", s=2, m=3, d=5, ts=2, tm=3, td=1,
                                                        returned=2, after=3)
    buttons = sends[0].reply_markup.inline_keyboard[0]
    assert len(buttons) == 2
    assert buttons[1].callback_data == "rvb:n"
    assert revive.parse_callback(buttons[0].callback_data)[:4] == (revive.CONFIRM, SHORT, 3, 1)
    longest = revive.confirm_data(BIGINT_MAX, 999, 999, "f" * 16)
    assert len(str(BIGINT_MAX)) == 19
    for data in (buttons[0].callback_data, buttons[1].callback_data, longest):
        assert len(data.encode()) <= 64
    assert _user_sends(calls) == []


def test_preview_usage_without_number_and_reply():
    conn = db()
    calls, connected, _ = asyncio.run(_feed(cfg(), _cmd("/revive"), conn))
    assert connected == []
    assert [c.text for c in calls if isinstance(c, SendMessage)] == [texts.REVIVE_USAGE]


# --- подтверждение: revive.apply ---

def test_apply_sql_order_payload_actor():
    conn = db()
    result = asyncio.run(revive.apply(conn, SHORT, 3, 1, OP))
    assert result == revive.Result(revive.DONE, TG_USER)
    assert conn.sqls() == [FIND, LOCK, STATE, AFTER, WRITEOFFS, KEY, EVENT]
    assert conn.log[0] == "begin" and conn.log[-1] == "commit"
    assert conn.params_of(LOCK) == [(PID,)] and isinstance(conn.params_of(LOCK)[0][0], str)
    assert conn.params_of(WRITEOFFS) == [(PID, AFTER_ID)]
    assert conn.params_of(KEY) == [(f"revive:{PID}:{OP}", "2")]
    (pid, payload), = conn.params_of(EVENT)
    assert pid == PID and isinstance(payload, Jsonb)
    assert payload.obj == {"target": {"stage_no": 2, "module_no": 3, "day_no": 1}, "lives_returned": 2}
    assert all(type(v) is int for v in payload.obj["target"].values())
    assert type(payload.obj["lives_returned"]) is int
    assert "'bot', 'owner'" in EVENT and "'revive_by_author'" in EVENT and "'revive'" in KEY
    _assert_no_returning()


def test_apply_repeat_already_no_event():
    conn = db(key_rowcount=0)
    assert asyncio.run(revive.apply(conn, SHORT, 3, 1, OP)) == revive.Result(revive.ALREADY)
    assert EVENT not in conn.sqls()


@pytest.mark.parametrize(("state", "m", "d", "code"), [
    (("muted", ["block_lives"], 2, 3, 5), 3, 1, revive.REFUSE_PHASE),
    (("active", [], 2, 3, 5), 3, 1, revive.REFUSE_NOT_BLOCKED),
    (BLOCKED, 3, 6, revive.REFUSE_AHEAD),
    (None, 3, 1, revive.NOT_FOUND),
])
def test_apply_refusal_no_key_no_event(state, m, d, code):
    conn = db(state=state)
    assert asyncio.run(revive.apply(conn, SHORT, m, d, OP)).code == code
    assert KEY not in conn.sqls() and EVENT not in conn.sqls()
    assert conn.log[-1] == "rollback"


# --- подтверждение через Dispatcher ---

def test_confirm_done_one_send_after_commit():
    conn = db()
    calls, _, at_send = asyncio.run(_feed(cfg(), _button(revive.confirm_data(SHORT, 3, 1, OP)), conn))
    assert conn.sqls() == [FIND, LOCK, STATE, AFTER, WRITEOFFS, KEY, EVENT]
    edits = [c for c in calls if isinstance(c, EditMessageText)]
    assert len(edits) == 1 and edits[0].reply_markup is None and texts.REVIVE_DONE in edits[0].text
    sends = _user_sends(calls)
    assert len(sends) == 1 and sends[0].text == texts.REVIVE_USER
    assert at_send == ["commit"]


def test_confirm_send_error_still_done(caplog):
    conn = db()
    calls, _, _ = asyncio.run(_feed(cfg(), _button(revive.confirm_data(SHORT, 3, 1, OP)), conn,
                                    fail_user_send=True))
    edits = [c for c in calls if isinstance(c, EditMessageText)]
    assert len(edits) == 1 and texts.REVIVE_DONE in edits[0].text
    assert len(_user_sends(calls)) == 1
    assert any("RuntimeError" in r.getMessage() for r in caplog.records)


def test_confirm_repeat_already_no_user_send():
    conn = db(key_rowcount=0)
    calls, _, _ = asyncio.run(_feed(cfg(), _button(revive.confirm_data(SHORT, 3, 1, OP)), conn))
    assert EVENT not in conn.sqls()
    edits = [c for c in calls if isinstance(c, EditMessageText)]
    assert len(edits) == 1 and texts.REVIVE_ALREADY in edits[0].text
    assert _user_sends(calls) == []


def test_confirm_refused_muted():
    conn = db(state=("muted", ["block_lives"], 2, 3, 5))
    calls, _, _ = asyncio.run(_feed(cfg(), _button(revive.confirm_data(SHORT, 3, 1, OP)), conn))
    assert KEY not in conn.sqls() and EVENT not in conn.sqls()
    edits = [c for c in calls if isinstance(c, EditMessageText)]
    assert len(edits) == 1 and texts.REVIVE_REFUSE_PHASE in edits[0].text
    assert _user_sends(calls) == []


def test_confirm_stale_no_connect():
    conn = db()
    calls, connected, _ = asyncio.run(_feed(cfg(), _button(revive.confirm_data(SHORT, 3, 1, OP),
                                                           age=timedelta(hours=1, seconds=5)), conn))
    assert connected == [] and conn.log == []
    edits = [c for c in calls if isinstance(c, EditMessageText)]
    assert len(edits) == 1 and edits[0].reply_markup is None and texts.REVIVE_STALE in edits[0].text
    assert _user_sends(calls) == []


@pytest.mark.parametrize(("chat_id", "user"), [(GROUP + 99, ADMIN), (GROUP, STRANGER)])
def test_command_stranger_ignored(chat_id, user):
    conn = db()
    calls, connected, _ = asyncio.run(_feed(cfg(), _cmd("/revive #005028", chat_id=chat_id, user=user), conn))
    assert calls == [] and connected == []


@pytest.mark.parametrize(("chat_id", "user"), [(GROUP + 99, ADMIN), (GROUP, STRANGER)])
def test_button_stranger_answer_without_text(chat_id, user):
    conn = db()
    calls, connected, _ = asyncio.run(_feed(cfg(), _button(revive.confirm_data(SHORT, 3, 1, OP), chat_id=chat_id,
                                                           user=user), conn))
    assert len(calls) == 1 and isinstance(calls[0], AnswerCallbackQuery) and calls[0].text is None
    assert connected == []


def test_router_not_included_when_card_disabled():
    dp = build_dispatcher(cfg(cards_topic_id=None))
    assert "revive" not in [r.name for r in dp.sub_routers]
    assert "revive" in [r.name for r in build_dispatcher(cfg()).sub_routers]
