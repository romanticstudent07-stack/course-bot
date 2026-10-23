"""Тесты доступа по промокоду (bot-access-1): чистые функции и подделка соединения, без сети и Postgres."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.methods import EditMessageText, SendMessage
from aiogram.types import Chat, Message, Update, User

from bot import access, texts
from bot.access import (
    DENY_UPDATE, FIND_BY_MESSAGE, GRANT_UPDATE, LOCK, STATE, STATE_FOR_UPDATE, UPSERT_REQUEST, Row,
)
from bot.access_handlers import IGNORE, OK, REPLY_REQUIRED, command_precheck
from bot.app import build_dispatcher
from bot.config import BotConfig, ConfigError

FAKE_TOKEN = "123456:TEST-token-not-real"
WEBAPP = "https://miniapp.example.test/"
GROUP, TOPIC, ADMIN, USER, MID = -1001234, 77, 555, 4242, 900
WORD = "Секрет<b>&слово"
NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


def cfg(**kw) -> BotConfig:
    base = dict(bot_token=FAKE_TOKEN, webapp_url=WEBAPP, log_level="INFO", database_url="postgresql://x/y",
                work_group_id=GROUP, access_admin_topic_id=TOPIC, access_admin_ids=frozenset({ADMIN}))
    base.update(kw)
    return BotConfig(**base)


# --- подделка соединения (по образцу test_outbox.FakeConn) ---

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
        res = self.answer(sql, params)
        if isinstance(res, BaseException):
            raise res
        return res

    def transaction(self):
        return _Tx(self)

    async def close(self):
        self.closed = True

    def sqls(self):
        return [e[0] for e in self.log if isinstance(e, tuple)]

    def all_params(self):
        return [e[1] for e in self.log if isinstance(e, tuple)]


def db(row=None, deny_rowcount=1, by_message=USER, fail_on=None):
    def answer(sql, params):
        if fail_on and sql == fail_on:
            return RuntimeError("boom")
        if sql in (STATE, STATE_FOR_UPDATE):
            return FakeCursor(row)
        if sql == FIND_BY_MESSAGE:
            return FakeCursor(None if by_message is None else (by_message,))
        if sql == DENY_UPDATE:
            return FakeCursor(None, rowcount=deny_rowcount)
        return FakeCursor(None)
    return FakeConn(answer)


def pending_row(deny_count=0, mid=MID):
    return ("pending", deny_count, None, mid)


# --- раздел 7: переходы ---

def test_classify_transitions():
    assert access.classify(None, NOW).kind == access.NEW
    assert access.classify(Row("granted", 0, None, 1), NOW).kind == access.NOTHING
    assert access.classify(Row("pending", 2, None, 1), NOW).kind == access.PENDING
    locked = access.classify(Row("denied", 5, NOW + timedelta(hours=1), 1), NOW)
    assert locked.kind == access.LOCKED and locked.locked_until == NOW + timedelta(hours=1)
    ended = access.classify(Row("denied", 5, NOW, 1), NOW)  # locked_until ≤ сейчас → сброс
    assert ended.kind == access.NEW and ended.deny_count == 0
    again = access.classify(Row("denied", 3, None, 1), NOW)
    assert again.kind == access.NEW and again.deny_count == 3


@pytest.mark.parametrize(("text", "ok"), [("", False), ("   ", False), (None, False), ("x" * 65, False),
                                          ("x" * 64, True), ("  код ", True)])
def test_clean_word(text, ok):
    assert (access.clean_word(text) is not None) is ok


def test_fourth_deny_leaves_one_fifth_locks_exactly():
    c = cfg()
    assert access.deny_result(4, c.access_max_denies, c.access_lock_hours, NOW) is None
    d4 = access.Decision(access.DENIED, USER, 4, None)
    assert access.user_text_for_decision(d4, 5) == texts.ACCESS_DENIED_LAST
    until = access.deny_result(5, c.access_max_denies, c.access_lock_hours, NOW)
    assert until - NOW == timedelta(hours=24)
    d5 = access.Decision(access.DENIED, USER, 5, until)
    assert access.user_text_for_decision(d5, 5) == texts.ACCESS_LOCKED.format(until="24.10.2026 15:00 МСК")
    d1 = access.Decision(access.DENIED, USER, 1, None)
    assert access.user_text_for_decision(d1, 5) == texts.ACCESS_DENIED_RETRY.format(n=4)


def test_fmt_msk():
    assert access.fmt_msk(NOW) == "23.10.2026 15:00 МСК"
    assert access.fmt_msk(NOW.replace(tzinfo=None)) == "23.10.2026 15:00 МСК"  # без пояса = UTC


def test_html_escape_name_and_word():
    who = access.user_label(USER, "<Ann>", "&Co", "u_<x>")
    assert "&lt;Ann&gt; &amp;Co" in who and "@u_&lt;x&gt;" in who and "<Ann>" not in who
    assert f'<a href="tg://user?id={USER}">' in who and f"ID {USER}" in who
    text = access.admin_request_text(WORD, who)
    assert "<code>Секрет&lt;b&gt;&amp;слово</code>" in text


def test_callback_parse():
    assert access.parse_callback(f"acc:g:{USER}") == ("g", USER)
    assert access.parse_callback(f"acc:d:{USER}") == ("d", USER)
    for bad in ("acc:x:1", "acc:g:abc", "acc:g:-5", "other:g:1", None):
        assert access.parse_callback(bad) is None
    kb = access.admin_keyboard(USER).inline_keyboard[0]
    assert [b.callback_data for b in kb] == [f"acc:g:{USER}", f"acc:d:{USER}"]


# --- фильтры ---

def test_admin_context_filters():
    c = cfg()
    assert access.is_admin_context(c, GROUP, TOPIC, ADMIN)
    assert not access.is_admin_context(c, -1, TOPIC, ADMIN)       # чужой чат
    assert not access.is_admin_context(c, GROUP, TOPIC + 1, ADMIN)  # чужая тема
    assert not access.is_admin_context(c, GROUP, TOPIC, 999)        # не whitelist
    assert not access.is_admin_context(cfg(access_admin_ids=frozenset()), GROUP, TOPIC, ADMIN)


def _cmd(chat_id=GROUP, thread=TOPIC, user=ADMIN, reply_id=None):
    reply = None
    if reply_id is not None:
        reply = Message(message_id=reply_id, date=datetime.now(), chat=Chat(id=chat_id, type="supergroup"),
                        text="заявка")
    return Message(message_id=1000, date=datetime.now(), chat=Chat(id=chat_id, type="supergroup"),
                   from_user=User(id=user, is_bot=False, first_name="A"), text="/access_deny",
                   message_thread_id=thread, reply_to_message=reply)


def test_command_precheck():
    c = cfg()
    assert command_precheck(c, _cmd(chat_id=-1, reply_id=MID)) == IGNORE
    assert command_precheck(c, _cmd(thread=1, reply_id=MID)) == IGNORE
    assert command_precheck(c, _cmd(user=1, reply_id=MID)) == IGNORE
    assert command_precheck(c, _cmd()) == REPLY_REQUIRED
    assert command_precheck(c, _cmd(reply_id=TOPIC)) == REPLY_REQUIRED  # reply на начало темы
    assert command_precheck(c, _cmd(reply_id=MID)) == OK


# --- config ---

def test_config_empty_disabled_warning_without_values(caplog):
    caplog.set_level(logging.WARNING)
    c = BotConfig.from_env({"BOT_TOKEN": FAKE_TOKEN, "BOT_DATABASE_URL": "postgresql://u:topsecret@db/x"})
    assert not c.access_enabled
    assert c.access_max_denies == 5 and c.access_lock_hours == 24
    build_dispatcher(c)
    msgs = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("WORK_GROUP_ID" in m and "ACCESS_ADMIN_TOPIC_ID" in m and "ACCESS_ADMIN_IDS" in m for m in msgs)
    assert "topsecret" not in caplog.text and "BOT_DATABASE_URL" not in " ".join(msgs)


def test_config_full_enabled():
    c = BotConfig.from_env({"BOT_TOKEN": FAKE_TOKEN, "BOT_DATABASE_URL": "postgresql://x/y",
                            "WORK_GROUP_ID": str(GROUP), "ACCESS_ADMIN_TOPIC_ID": str(TOPIC),
                            "ACCESS_ADMIN_IDS": f" {ADMIN}, 7 ", "ACCESS_MAX_DENIES": "3"})
    assert c.access_enabled and c.access_admin_ids == {ADMIN, 7} and c.access_max_denies == 3


@pytest.mark.parametrize(("name", "value"), [("WORK_GROUP_ID", "abc12"), ("ACCESS_ADMIN_TOPIC_ID", "1.5"),
                                             ("ACCESS_ADMIN_IDS", "1,zz9"), ("ACCESS_MAX_DENIES", "0"),
                                             ("ACCESS_LOCK_HOURS", "x7")])
def test_config_bad_number(name, value):
    with pytest.raises(ConfigError) as err:
        BotConfig.from_env({"BOT_TOKEN": FAKE_TOKEN, name: value})
    assert value not in str(err.value) and name in str(err.value)


# --- подделка соединения: decide ---

def test_decide_grant_one_transaction_for_update():
    conn = db(pending_row())
    d = asyncio.run(access.decide(conn, cfg(), access.GRANT, USER, MID, ADMIN, NOW))
    assert d.kind == access.GRANTED
    assert conn.log[0] == "begin" and conn.log[-1] == "commit"
    assert conn.sqls() == [STATE_FOR_UPDATE, GRANT_UPDATE]
    assert "FOR UPDATE" in conn.sqls()[0]


def test_decide_exception_rolls_back():
    conn = db(pending_row(), fail_on=GRANT_UPDATE)
    with pytest.raises(RuntimeError):
        asyncio.run(access.decide(conn, cfg(), access.GRANT, USER, MID, ADMIN, NOW))
    assert conn.log[-1] == "rollback" and "commit" not in conn.log


def test_grant_in_lock_resets_counter():
    conn = db(("denied", 5, NOW + timedelta(hours=3), MID))
    d = asyncio.run(access.decide(conn, cfg(), access.GRANT, USER, MID, ADMIN, NOW))
    assert d.kind == access.GRANTED
    assert "deny_count = 0" in GRANT_UPDATE and "locked_until = NULL" in GRANT_UPDATE


def test_repeat_grant_already_granted_no_update():
    conn = db(("granted", 0, None, MID))
    d = asyncio.run(access.decide(conn, cfg(), access.GRANT, USER, MID, ADMIN, NOW))
    assert d.kind == access.ALREADY_GRANTED
    assert GRANT_UPDATE not in conn.sqls()
    assert access.admin_reply_for(d) == texts.ACCESS_ALREADY_GRANTED


def test_deny_sql_conditions_and_increment():
    conn = db(pending_row(deny_count=1))
    d = asyncio.run(access.decide(conn, cfg(), access.DENY, USER, MID, ADMIN, NOW))
    assert "status = 'pending'" in DENY_UPDATE and "admin_message_id = %s" in DENY_UPDATE
    assert conn.sqls() == [STATE_FOR_UPDATE, DENY_UPDATE]
    assert conn.all_params()[-1] == (None, NOW, ADMIN, USER, MID)
    assert d.kind == access.DENIED and d.deny_count == 2
    assert access.user_text_for_decision(d, 5) == texts.ACCESS_DENIED_RETRY.format(n=3)


def test_deny_fifth_locks():
    conn = db(pending_row(deny_count=4))
    d = asyncio.run(access.decide(conn, cfg(), access.DENY, USER, MID, ADMIN, NOW))
    assert d.locked_until == NOW + timedelta(hours=24)


# --- подделка соединения: новая заявка ---

def test_new_request_lock_first_then_for_update_then_upsert(caplog):
    caplog.set_level(logging.DEBUG)
    conn = db(None)
    bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=MID)))
    who = access.user_label(USER, "Ann", None, "ann")
    kind, _ = asyncio.run(access.submit_request(conn, bot, cfg(), USER, f"  {WORD} ", who, NOW))
    assert kind == access.SENT
    sqls = conn.sqls()
    assert sqls[0] == LOCK and "'access_grants:'" in sqls[0] and "pg_advisory_xact_lock" in sqls[0]
    assert sqls[1] == STATE_FOR_UPDATE and sqls[2] == UPSERT_REQUEST
    assert conn.log[0] == "begin" and conn.log[-1] == "commit"
    kw = bot.send_message.await_args.kwargs
    assert kw["chat_id"] == GROUP and kw["message_thread_id"] == TOPIC and kw["parse_mode"] == "HTML"
    assert "<code>Секрет&lt;b&gt;&amp;слово</code>" in kw["text"]
    # Слово — ни в параметрах SQL, ни в логе.
    for p in conn.all_params():
        assert all(WORD.strip() not in str(v) for v in (p or ()))
    assert "Секрет" not in caplog.text


def test_new_request_send_fail_rollback_try_later(caplog):
    caplog.set_level(logging.DEBUG)
    conn = db(("denied", 2, None, 1))
    bot = SimpleNamespace(send_message=AsyncMock(side_effect=RuntimeError("tg down")))
    kind, _ = asyncio.run(access.submit_request(conn, bot, cfg(), USER, WORD, "who", NOW))
    assert kind == access.TRY_LATER
    assert conn.log[-1] == "rollback" and UPSERT_REQUEST not in conn.sqls()
    assert "Секрет" not in caplog.text


@pytest.mark.parametrize(("row", "text", "kind"), [
    (pending_row(), WORD, access.PENDING),
    (("denied", 5, NOW + timedelta(hours=1), 1), WORD, access.LOCKED),
    (("granted", 0, None, 1), WORD, access.NOTHING),
    (None, "x" * 65, access.SEND_TEXT),
    (None, "   ", access.SEND_TEXT),
])
def test_new_request_recheck_no_send(row, text, kind):
    conn = db(row)
    bot = SimpleNamespace(send_message=AsyncMock())
    got, _ = asyncio.run(access.submit_request(conn, bot, cfg(), USER, text, "who", NOW))
    assert got == kind
    bot.send_message.assert_not_awaited()
    assert UPSERT_REQUEST not in conn.sqls()


def test_new_request_after_lock_end_resets_counter():
    conn = db(("denied", 5, NOW - timedelta(seconds=1), 1))
    bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=MID)))
    asyncio.run(access.submit_request(conn, bot, cfg(), USER, WORD, "who", NOW))
    assert conn.all_params()[-1] == (USER, MID, NOW, 0)


# --- через Dispatcher (Bot API перехвачен) ---

async def _feed(config, update, conn):
    bot = Bot(token=FAKE_TOKEN)
    calls: list = []

    async def fake_request(_bot, method, timeout=None):
        calls.append(method)
        return True

    bot.session.make_request = AsyncMock(side_effect=fake_request)

    async def connect(_dsn):
        return conn

    dp = build_dispatcher(config, connect)
    await dp.feed_update(bot, update)
    await bot.session.close()
    return calls


def _private(text=None, sticker=False):
    user = User(id=USER, is_bot=False, first_name="Ann")
    kw = {"text": text} if not sticker else {}
    return Update(update_id=1, message=Message(message_id=1, date=datetime.now(),
                                                chat=Chat(id=USER, type="private"), from_user=user, **kw))


def test_start_without_access_prompts_no_menu():
    calls = asyncio.run(_feed(cfg(), _private("/start"), db(None)))
    sends = [c for c in calls if isinstance(c, SendMessage)]
    assert [s.text for s in sends] == [texts.ACCESS_PROMPT]
    assert len(calls) == 1  # меню-кнопку не ставим


def test_start_granted_as_before():
    calls = asyncio.run(_feed(cfg(), _private("/start"), db(("granted", 0, None, 1))))
    sends = [c for c in calls if isinstance(c, SendMessage)]
    assert sends[0].text.startswith(texts.START_WELCOME)


def test_sticker_send_text_no_request():
    conn = db(None)
    calls = asyncio.run(_feed(cfg(), _private(sticker=True), conn))
    assert [c.text for c in calls if isinstance(c, SendMessage)] == [texts.ACCESS_SEND_TEXT]
    assert LOCK not in conn.sqls()


def test_other_command_send_text():
    calls = asyncio.run(_feed(cfg(), _private("/help"), db(None)))
    assert [c.text for c in calls if isinstance(c, SendMessage)] == [texts.ACCESS_SEND_TEXT]


def _group_cmd(text, reply_id=MID, thread=TOPIC, user=ADMIN):
    return Update(update_id=2, message=_cmd(thread=thread, user=user, reply_id=reply_id).model_copy(
        update={"text": text}))


def test_command_without_reply_asks_reply():
    calls = asyncio.run(_feed(cfg(), _group_cmd("/access_deny", reply_id=None), db(pending_row())))
    assert [c.text for c in calls if isinstance(c, SendMessage)] == [texts.ACCESS_REPLY_REQUIRED]


def test_command_from_stranger_ignored():
    conn = db(pending_row())
    calls = asyncio.run(_feed(cfg(), _group_cmd("/access_grant", user=1), conn))
    assert calls == [] and conn.log == []


def test_command_reply_not_request():
    calls = asyncio.run(_feed(cfg(), _group_cmd("/access_grant"), FakeConn(lambda s, p: FakeCursor(None))))
    assert [c.text for c in calls if isinstance(c, SendMessage)] == [texts.ACCESS_REQUEST_NOT_FOUND]


def test_command_deny_already_decided_nothing_to_user():
    conn = db(pending_row(), deny_rowcount=0)
    calls = asyncio.run(_feed(cfg(), _group_cmd("/access_deny"), conn))
    assert not [c for c in calls if isinstance(c, EditMessageText)]
    sends = [c for c in calls if isinstance(c, SendMessage)]
    assert [s.chat_id for s in sends] == [GROUP] and sends[0].text == texts.ACCESS_ALREADY_DECIDED


def test_command_deny_edits_topic_and_tells_user():
    conn = db(pending_row())
    calls = asyncio.run(_feed(cfg(), _group_cmd("/access_deny"), conn))
    edits = [c for c in calls if isinstance(c, EditMessageText)]
    assert len(edits) == 1 and edits[0].reply_markup is None and "Запрещено 1 из 5" in edits[0].text
    sends = [c for c in calls if isinstance(c, SendMessage)]
    assert [(s.chat_id, s.text) for s in sends] == [(USER, texts.ACCESS_DENIED_RETRY.format(n=4))]
