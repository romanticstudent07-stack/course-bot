"""Тесты рестарта по промокоду (bot-restart-1, §9): подделка соединения, Bot API перехвачен; без сети и Postgres."""
import asyncio
import logging
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from aiogram import Bot
from aiogram.methods import AnswerCallbackQuery, EditMessageReplyMarkup, EditMessageText, GetMe, SendMessage
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from bot import access, access_handlers, restart, texts
from bot.app import build_dispatcher
from bot.config import BotConfig
from bot.life import LOCK

FAKE_TOKEN = "123456:TEST-token-not-real"
BOT_ID = 123456
GROUP, TOPIC, ADMIN, USER, SHORT, MID, STAGE = -4801, 4802, 4803, 4804, 4805, 4806, 2
PID = UUID("00000000-0000-0000-0000-000000004807")
WORD = "Рестарт<b>&слово"
NOW = datetime(2026, 11, 17, 21, 0, tzinfo=timezone.utc)  # граница суток: в МСК уже 18.11
KEY_TODAY = f"restart_req:{PID}:2026-11-18"


def cfg(**kw) -> BotConfig:
    base = dict(bot_token=FAKE_TOKEN, webapp_url="", log_level="INFO", database_url="postgresql://x/y",
                work_group_id=GROUP, access_admin_topic_id=TOPIC, access_admin_ids=frozenset({ADMIN}))
    base.update(kw)
    return BotConfig(**base)


# --- подделка соединения (по образцу test_access.FakeConn) ---

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
        self.conn.pending = {}

    async def __aexit__(self, exc_type, exc, tb):
        self.conn.log.append("rollback" if exc_type else "commit")
        if not exc_type:
            self.conn.keys.update(self.conn.pending)
        return False


class FakeConn:
    """Ключи idempotency_keys хранятся только после commit (откат их не сохраняет)."""

    def __init__(self, state=("active", ["block_lives"], STAGE), found=True, keys=None):
        self.state, self.found = state, found
        self.keys, self.pending, self.log, self.closed = dict(keys or {}), {}, [], False

    async def execute(self, sql, params=None):
        self.log.append((sql, params))
        if sql == access.STATE_FOR_UPDATE or sql == access.STATE:
            return FakeCursor(("granted", 0, None, 1))
        if sql == restart.FIND_BY_TG:
            return FakeCursor((PID, SHORT) if self.found else None)
        if sql == restart.FIND_BY_SHORT:
            return FakeCursor((PID, USER) if self.found else None)
        if sql == restart.STATE:
            return FakeCursor(self.state)
        if sql in (restart.REQUEST_KEY, restart.DECISION_KEY):
            key = params[0]
            if key in self.keys or key in self.pending:
                return FakeCursor(None, rowcount=0)
            self.pending[key] = params[1] if len(params) > 1 else None
            return FakeCursor(None)
        if sql == restart.RESULT:
            return FakeCursor((self.keys[params[0]],) if params[0] in self.keys else None)
        return FakeCursor(None)

    def transaction(self):
        return _Tx(self)

    async def close(self):
        self.closed = True

    def sqls(self):
        return [e[0] for e in self.log if isinstance(e, tuple)]

    def params_of(self, sql):
        return [e[1] for e in self.log if isinstance(e, tuple) and e[0] == sql]


async def _feed(config, update, conn, fail=()):
    bot = Bot(token=FAKE_TOKEN)
    calls: list = []

    async def fake_request(_bot, method, timeout=None):
        calls.append(method)
        if isinstance(method, GetMe):
            return User(id=BOT_ID, is_bot=True, first_name="B", username="course_bot")
        if type(method) in fail:
            raise RuntimeError("tg fail")
        if isinstance(method, SendMessage):
            return Message(message_id=MID, date=datetime.now(), chat=Chat(id=method.chat_id, type="supergroup"))
        return True

    bot.session.make_request = AsyncMock(side_effect=fake_request)

    async def connect(_dsn):
        return conn

    dp = build_dispatcher(config, connect)
    await dp.feed_update(bot, update)
    await bot.session.close()
    return calls


def _private(text=WORD):
    user = User(id=USER, is_bot=False, first_name="Ann")
    return Update(update_id=1, message=Message(message_id=1, date=datetime.now(),
                                                chat=Chat(id=USER, type="private"), from_user=user, text=text))


def _button(action="g", user=ADMIN, chat=GROUP, thread=TOPIC, mid=MID):
    return Update(update_id=2, callback_query=CallbackQuery(
        id="cb1", from_user=User(id=user, is_bot=False, first_name="A"), chat_instance="ci",
        data=f"rst:{action}:{SHORT}",
        message=Message(message_id=mid, chat=Chat(id=chat, type="supergroup"), message_thread_id=thread,
                        text="заявка", date=datetime.now())))


@pytest.fixture(autouse=True)
def _fixed_now(monkeypatch):
    monkeypatch.setattr(access_handlers, "_now", lambda: NOW)


def _sends(calls):
    return [c for c in calls if isinstance(c, SendMessage)]


# --- eligible ---

def test_eligible():
    assert restart.eligible("active", ["block_lives"], STAGE) is True
    assert restart.eligible("sleeping", ["block_lives"], STAGE) is True
    assert restart.eligible("active", [], STAGE) is False
    assert restart.eligible("active", None, STAGE) is False
    assert restart.eligible("active", ["block_lives"], None) is False
    assert restart.eligible("muted", ["block_lives"], STAGE) is False
    assert restart.eligible("erased", ["block_lives"], STAGE) is False


def test_callback_data_len_and_parse():
    kb = restart.admin_keyboard(restart.BIGINT_MAX).inline_keyboard[0]
    assert [b.text for b in kb] == [texts.RESTART_BUTTON_GRANT, texts.RESTART_BUTTON_DENY]
    for b in kb:
        assert len(b.callback_data.encode()) <= 64
    assert restart.parse_callback(f"rst:g:{SHORT}") == ("g", SHORT)
    assert restart.parse_callback(f"rst:d:{SHORT}") == ("d", SHORT)
    for bad in ("rst:x:1", "rst:g:abc", "rst:g:0", "rst:g:-5", "acc:g:1", None):
        assert restart.parse_callback(bad) is None


# --- заявка (личка, вердикт доступа NOTHING) ---

def test_request_key_msk_date_and_topic_message(caplog):
    caplog.set_level(logging.DEBUG)
    conn = FakeConn()
    calls = asyncio.run(_feed(cfg(), _private(), conn))
    assert conn.params_of(restart.REQUEST_KEY) == [(KEY_TODAY,)]
    assert restart.request_key(PID, NOW.replace(hour=20, minute=59)) == f"restart_req:{PID}:2026-11-17"
    sql = conn.sqls()
    assert sql.index(LOCK) < sql.index(restart.REQUEST_KEY)
    sends = _sends(calls)
    assert len(sends) == 2
    topic, user = sends
    assert (topic.chat_id, topic.message_thread_id, topic.parse_mode) == (GROUP, TOPIC, "HTML")
    assert "<code>Рестарт&lt;b&gt;&amp;слово</code>" in topic.text and f"#{SHORT:06d}" in topic.text
    assert [b.callback_data for b in topic.reply_markup.inline_keyboard[0]] == [f"rst:g:{SHORT}", f"rst:d:{SHORT}"]
    assert (user.chat_id, user.text) == (USER, texts.RESTART_REQUEST_SENT)
    assert conn.keys == {KEY_TODAY: None}
    for _, params in (e for e in conn.log if isinstance(e, tuple)):
        assert all("Рестарт" not in str(v) for v in (params or ()))
    assert "Рестарт" not in caplog.text and str(USER) not in caplog.text and str(PID) not in caplog.text


def test_request_repeat_same_day_already_today():
    conn = FakeConn(keys={KEY_TODAY: None})
    calls = asyncio.run(_feed(cfg(), _private(), conn))
    assert [(s.chat_id, s.text) for s in _sends(calls)] == [(USER, texts.RESTART_ALREADY_TODAY)]


@pytest.mark.parametrize("state", [("active", [], STAGE), ("muted", ["block_lives"], STAGE), None])
def test_request_not_eligible_silence(state):
    conn = FakeConn(state=state)
    calls = asyncio.run(_feed(cfg(), _private(), conn))
    assert _sends(calls) == []
    assert not [s for s in conn.sqls() if "INSERT" in s and s not in (access.UPSERT_REQUEST,)]
    assert restart.REQUEST_KEY not in conn.sqls()


def test_request_send_fail_rollback_try_later():
    conn = FakeConn()
    bot = AsyncMock()
    bot.send_message.side_effect = RuntimeError("tg down")
    code = asyncio.run(restart.submit_request(conn, bot, cfg(), USER, WORD, NOW))
    assert code == restart.TRY_LATER and restart.user_text_for(code) == texts.RESTART_TRY_LATER
    assert conn.log[-1] == "rollback" and conn.keys == {}


# --- выдача ---

def test_grant_order_payload_actor_no_returning():
    conn = FakeConn()
    calls = asyncio.run(_feed(cfg(), _button("g"), conn))
    assert conn.sqls() == [restart.FIND_BY_SHORT, LOCK, restart.DECISION_KEY, restart.STATE, restart.EVENT]
    assert conn.log[0] == "begin" and conn.log[-1] == "commit"
    pid, payload = conn.params_of(restart.EVENT)[0]
    assert pid == PID and payload.obj == {"admin_message_id": MID}
    assert "'restart_paid'" in restart.EVENT and "'bot', 'owner'" in restart.EVENT
    assert all("RETURNING" not in s.upper() for s in conn.sqls())
    assert conn.keys == {f"restart:{PID}:{MID}": "granted"}
    edits = [c for c in calls if isinstance(c, EditMessageText)]
    assert len(edits) == 1 and edits[0].reply_markup is None and "Рестарт выдан" in edits[0].text
    assert [(s.chat_id, s.text) for s in _sends(calls)] == [(USER, texts.RESTART_GRANTED)]


def _assert_refused(conn, calls, text):
    assert restart.EVENT not in conn.sqls()
    assert conn.log[-1] == "rollback" and conn.keys == {}
    edits = [c for c in calls if isinstance(c, EditMessageText)]
    assert len(edits) == 1 and edits[0].chat_id == GROUP and edits[0].reply_markup is None
    assert text in edits[0].text
    assert _sends(calls) == []  # участнику ничего


def test_grant_muted_refused():
    conn = FakeConn(state=("muted", ["block_lives"], STAGE))
    calls = asyncio.run(_feed(cfg(), _button("g"), conn))
    _assert_refused(conn, calls, texts.RESTART_REFUSED_PHASE)


def test_grant_erased_refused():
    conn = FakeConn(state=("erased", ["block_lives"], STAGE))
    calls = asyncio.run(_feed(cfg(), _button("g"), conn))
    _assert_refused(conn, calls, texts.RESTART_REFUSED_PHASE)


def test_grant_tombstoned_refused():
    conn = FakeConn(found=False)
    calls = asyncio.run(_feed(cfg(), _button("g"), conn))
    assert conn.sqls() == [restart.FIND_BY_SHORT]
    _assert_refused(conn, calls, texts.RESTART_REFUSED_STATE)


# --- запрет ---

def test_deny_then_grant_already():
    conn = FakeConn()
    calls = asyncio.run(_feed(cfg(), _button("d"), conn))
    assert conn.keys == {f"restart:{PID}:{MID}": "denied"}
    assert restart.EVENT not in conn.sqls() and restart.STATE not in conn.sqls()
    assert [(s.chat_id, s.text) for s in _sends(calls)] == [(USER, texts.RESTART_DENIED)]
    conn.log.clear()
    calls = asyncio.run(_feed(cfg(), _button("g"), conn))
    assert restart.EVENT not in conn.sqls() and conn.sqls()[-1] == restart.RESULT
    sends = _sends(calls)
    assert [(s.chat_id, s.text) for s in sends] == [
        (GROUP, texts.RESTART_ALREADY.format(result=texts.RESTART_RESULT_DENIED))]
    marks = [c for c in calls if isinstance(c, EditMessageReplyMarkup)]
    assert len(marks) == 1 and marks[0].reply_markup is None


# --- фильтры ---

@pytest.mark.parametrize("kw", [{"chat": -4899}, {"thread": 4898}, {"user": 4897}])
def test_button_foreign_chat_or_not_whitelist(kw):
    conn = FakeConn()
    calls = asyncio.run(_feed(cfg(), _button("g", **kw), conn))
    assert len(calls) == 1 and isinstance(calls[0], AnswerCallbackQuery) and calls[0].text is None
    assert conn.log == []


# --- access_grants ---

def test_no_access_grants_sql_in_restart():
    conn = FakeConn()
    bot = AsyncMock()
    asyncio.run(restart.submit_request(conn, bot, cfg(), USER, WORD, NOW))
    for action in ("g", "d"):
        asyncio.run(restart.decide(conn, action, SHORT, MID + (action == "d")))
    assert conn.sqls() and all("access_grants" not in s for s in conn.sqls())
