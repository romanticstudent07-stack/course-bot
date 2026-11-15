"""Тесты поддержки (bot-sup-1, Р-19): пост вопроса в тему по topic_code и ответ ✉️ с предпросмотром.

Подделка БД и бота — копия образца test_outbox_group.py (без сети и Postgres).
"""
import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, call

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendMessage
from aiogram.types import ForceReply

from bot import app as bot_app
from bot import outbox, support, support_handlers, texts
from bot.config import (
    SUPPORT_REQUIRED_VARS,
    SUPPORT_TOPIC_VARS,
    BotConfig,
    ConfigError,
)
from bot.outbox import CLAIM, GROUP_ADDRESSEE, MARK, TO_DLQ, OutboxWorker
from bot.support import PARTICIPANT, SUPPORT_Q

PID = uuid.UUID("11111111-2222-4333-8444-555555555555")
OTHER_PID = uuid.UUID("99999999-2222-4333-8444-555555555555")
TG_ID = 4401
ADMIN = 4402
STRANGER = 4403
BOT_ID = 4404
SHORT_NO = 4455
N = 777001
WG = -1001234567890
S3 = 31
OTHER = 39
BODY = "Секретный-вопрос <b>x</b>"
ANSWER = "Секретный-ответ <i>y</i>"
FAKE_TOKEN = "123456:TEST-token-not-real"
METHOD = SendMessage(chat_id=1, text="x")
PAYLOAD = {"pid": str(PID), "question_id": N}
DEFAULT = object()


def make_cfg(**kw):
    base = {
        "bot_token": FAKE_TOKEN,
        "webapp_url": "",
        "log_level": "INFO",
        "database_url": "postgresql://u@db/x",
        "work_group_id": WG,
        "access_admin_ids": frozenset({ADMIN}),
        "support_s3_topic_id": S3,
        "support_other_topic_id": OTHER,
    }
    base.update(kw)
    return BotConfig(**base)


class FakeCursor:
    def __init__(self, row=None, rowcount=1):
        self.row = row
        self.rowcount = rowcount

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
        self.answer = answer
        self.log: list = []
        self.closed = False

    async def execute(self, sql, params=None):
        self.log.append((sql, params))
        return self.answer(sql, params)

    def transaction(self, force_rollback=False):
        return _Tx(self)

    async def close(self):
        self.closed = True

    def sqls(self):
        return [e[0] for e in self.log if isinstance(e, tuple)]

    def params(self, sql):
        return [e[1] for e in self.log if isinstance(e, tuple) and e[0] == sql]


def make_db(*, payload=PAYLOAD, created_at=None, addressee="ok", short_no=SHORT_NO, question="ok",
            topic_code="s3"):
    row = (7, str(PID), "support_question", payload, created_at or datetime.now(timezone.utc))
    state = {"marked": False}

    def answer(sql, params):
        if sql == CLAIM:
            return FakeCursor(None if state["marked"] else row)
        if sql == GROUP_ADDRESSEE:
            tomb = datetime.now(timezone.utc) if addressee == "tombstoned" else None
            return FakeCursor((TG_ID, short_no, tomb))
        if sql == SUPPORT_Q:
            if question is None:
                return FakeCursor(None)
            q_pid = OTHER_PID if question == "other" else PID
            return FakeCursor((q_pid, topic_code, BODY, datetime.now(timezone.utc)))
        if sql == MARK:
            state["marked"] = True
        return FakeCursor(None, rowcount=1)

    return FakeConn(answer)


def make_bot(*effects):
    return SimpleNamespace(send_message=AsyncMock(side_effect=list(effects) or None))


def one(conn, bot, config=DEFAULT):
    cfg = make_cfg() if config is DEFAULT else config
    w = OutboxWorker(bot, asyncio.Event(), config=cfg)
    return w, asyncio.run(w.process_one(conn))


@pytest.fixture
def sleeps(monkeypatch):
    log: list = []

    async def fake_pause(stop, seconds):
        log.append(seconds)
        return stop.is_set()

    monkeypatch.setattr(outbox, "_pause", fake_pause)
    return log


def dlq_codes(conn):
    return [p[2] for p in conn.params(TO_DLQ)]


def _no_pii(caplog):
    text = caplog.text
    for value in (TG_ID, ADMIN, STRANGER, SHORT_NO, N, PID):
        assert str(value) not in text
    assert "Секретный-вопрос" not in text and "Секретный-ответ" not in text


# --- outbox: support_question ---

# 1
@pytest.mark.parametrize(("topic_code", "thread_id"), [("s3", S3), ("other", OTHER)])
def test_support_question_posted_to_topic(topic_code, thread_id, caplog, sleeps):
    caplog.set_level(logging.DEBUG)
    conn, bot = make_db(topic_code=topic_code), make_bot()
    _, res = one(conn, bot)
    assert res[0] == outbox.DONE
    assert conn.sqls() == [CLAIM, GROUP_ADDRESSEE, SUPPORT_Q, MARK]
    assert conn.params(SUPPORT_Q)[0] == (N,)
    kw = bot.send_message.await_args.kwargs
    assert kw["chat_id"] == WG and kw["message_thread_id"] == thread_id
    assert kw["parse_mode"] == "HTML"
    assert "&lt;b&gt;x&lt;/b&gt;" in kw["text"] and "<b>x</b>" not in kw["text"]
    assert f'<a href="tg://user?id={TG_ID}">' in kw["text"] and "Участник #004455" in kw["text"]
    rows = kw["reply_markup"].inline_keyboard
    assert len(rows) == 1 and len(rows[0]) == 2
    assert rows[0][0].text == texts.CARD_BUTTON and rows[0][0].callback_data == f"card:{SHORT_NO}"
    assert rows[0][1].text == texts.SUPPORT_BUTTON_REPLY and rows[0][1].callback_data == f"sup:r:{N}"
    assert conn.log[-1] == "commit"
    _no_pii(caplog)


# 2
def test_support_question_without_short_no_only_reply_button(sleeps):
    conn, bot = make_db(short_no=None), make_bot()
    one(conn, bot)
    rows = bot.send_message.await_args.kwargs["reply_markup"].inline_keyboard
    assert len(rows) == 1 and len(rows[0]) == 1
    assert rows[0][0].callback_data == f"sup:r:{N}"


# 3
def test_support_question_tombstoned_only_mark(caplog, sleeps):
    caplog.set_level(logging.DEBUG)
    conn, bot = make_db(addressee="tombstoned"), make_bot()
    one(conn, bot)
    assert conn.sqls() == [CLAIM, GROUP_ADDRESSEE, MARK]
    bot.send_message.assert_not_awaited()
    _no_pii(caplog)


# 4
def test_support_question_expired(sleeps):
    conn = make_db(created_at=datetime.now(timezone.utc) - timedelta(hours=25))
    bot = make_bot()
    one(conn, bot)
    assert dlq_codes(conn) == ["expired"]
    bot.send_message.assert_not_awaited()


# 5
@pytest.mark.parametrize("config", [None, make_cfg(work_group_id=None)])
def test_support_question_no_work_group(config, caplog, sleeps):
    caplog.set_level(logging.DEBUG)
    conn, bot = make_db(), make_bot()
    one(conn, bot, config=config)
    assert dlq_codes(conn) == ["group_not_configured"]
    assert conn.sqls() == [CLAIM, GROUP_ADDRESSEE, TO_DLQ, MARK]
    bot.send_message.assert_not_awaited()
    _no_pii(caplog)


# 6
@pytest.mark.parametrize("topic_code", ["s5", "unknown"])
def test_support_question_topic_not_configured(topic_code, caplog, sleeps):
    caplog.set_level(logging.DEBUG)
    conn, bot = make_db(topic_code=topic_code), make_bot()
    one(conn, bot)
    assert dlq_codes(conn) == ["group_not_configured"]
    assert conn.sqls() == [CLAIM, GROUP_ADDRESSEE, SUPPORT_Q, TO_DLQ, MARK]
    bot.send_message.assert_not_awaited()
    _no_pii(caplog)


# 7
@pytest.mark.parametrize(
    "payload",
    [
        {"pid": str(PID), "question_id": True},
        {"pid": str(PID), "question_id": "5"},
        {"pid": str(PID), "question_id": 0},
        {"pid": str(PID), "question_id": -1},
        {"pid": str(PID)},
    ],
)
def test_support_question_bad_question_id(payload, caplog, sleeps):
    caplog.set_level(logging.DEBUG)
    conn, bot = make_db(payload=payload), make_bot()
    one(conn, bot)
    assert dlq_codes(conn) == ["bad_payload"]
    assert SUPPORT_Q not in conn.sqls()
    bot.send_message.assert_not_awaited()
    _no_pii(caplog)


# 8
def test_support_question_not_found(sleeps):
    conn, bot = make_db(question=None), make_bot()
    one(conn, bot)
    assert dlq_codes(conn) == ["support_not_found"]
    bot.send_message.assert_not_awaited()


# 9
def test_support_question_other_pid(caplog, sleeps):
    caplog.set_level(logging.DEBUG)
    conn, bot = make_db(question="other"), make_bot()
    one(conn, bot)
    assert dlq_codes(conn) == ["bad_payload"]
    bot.send_message.assert_not_awaited()
    _no_pii(caplog)


# --- config ---

# 10
def test_config_support_topics():
    assert SUPPORT_TOPIC_VARS == (
        "SUPPORT_S1_TOPIC_ID", "SUPPORT_S2_TOPIC_ID", "SUPPORT_S3_TOPIC_ID", "SUPPORT_S4_TOPIC_ID",
        "SUPPORT_S5_TOPIC_ID", "SUPPORT_S6_TOPIC_ID", "SUPPORT_S7_TOPIC_ID", "SUPPORT_OTHER_TOPIC_ID",
    )
    base = {"BOT_TOKEN": FAKE_TOKEN}
    env = {name: str(100 + i) for i, name in enumerate(SUPPORT_TOPIC_VARS)}
    full = BotConfig.from_env({**base, **env, "BOT_DATABASE_URL": "postgresql://u@db/x",
                               "WORK_GROUP_ID": "-100", "ACCESS_ADMIN_IDS": "4402"})
    assert [full.support_topic_id(c) for c in ("s1", "s2", "s3", "s4", "s5", "s6", "s7", "other")] == \
        list(range(100, 108))
    assert full.support_topic_id("s8") is None and full.support_topic_id(None) is None
    assert full.support_thread_ids() == frozenset(range(100, 108))
    assert full.support_missing_vars() == [] and full.support_enabled
    empty = BotConfig.from_env(base)
    assert empty.support_thread_ids() == frozenset()
    assert empty.support_missing_vars() == list(SUPPORT_REQUIRED_VARS) + list(SUPPORT_TOPIC_VARS)
    assert not empty.support_enabled
    no_topics = BotConfig.from_env({**base, "BOT_DATABASE_URL": "postgresql://u@db/x",
                                    "WORK_GROUP_ID": "-100", "ACCESS_ADMIN_IDS": "4402"})
    assert not no_topics.support_enabled
    part = make_cfg()
    assert part.support_enabled and part.support_thread_ids() == frozenset({S3, OTHER})
    assert "SUPPORT_S3_TOPIC_ID" not in part.support_missing_vars()
    assert "SUPPORT_S1_TOPIC_ID" in part.support_missing_vars()
    assert not make_cfg(database_url="").support_enabled
    for name in SUPPORT_TOPIC_VARS:
        with pytest.raises(ConfigError) as ei:
            BotConfig.from_env({**base, name: "abc"})
        assert "abc" not in str(ei.value) and name in str(ei.value)
    assert empty.group_missing_vars() == ["REFLECTIONS_TOPIC_ID", "REPORTS_TOPIC_ID"]


# --- app.build_dispatcher ---

def _support_warnings(caplog):
    return [r.getMessage() for r in caplog.records
            if r.levelno == logging.WARNING and r.getMessage().startswith("Поддержка выключена")]


def _router_names(dp):
    return [r.name for r in dp.sub_routers]


# 11
def test_build_dispatcher_support(caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    dp = bot_app.build_dispatcher(make_cfg(database_url=""))
    assert "support" not in _router_names(dp)
    warns = _support_warnings(caplog)
    assert len(warns) == 1 and warns[0].startswith("Поддержка выключена: не заданы")
    assert "BOT_DATABASE_URL" in warns[0] and "postgresql" not in warns[0]

    caplog.clear()
    seen = {}
    real = support_handlers.build_support_router

    def fake_build(config, connect=None):
        seen["connect"] = connect
        return real(config, connect)

    monkeypatch.setattr(support_handlers, "build_support_router", fake_build)
    marker = AsyncMock()
    dp = bot_app.build_dispatcher(make_cfg(), connect=marker)
    assert "support" in _router_names(dp)
    assert seen["connect"] is marker
    warns = _support_warnings(caplog)
    assert len(warns) == 1 and warns[0].startswith("Поддержка выключена для тем")
    assert "SUPPORT_S1_TOPIC_ID" in warns[0] and "SUPPORT_S3_TOPIC_ID" not in warns[0]
    assert str(S3) not in warns[0] and str(WG) not in warns[0]


# --- support.py ---

# 12
def test_support_pure_functions():
    assert support.parse_callback(f"sup:r:{N}") == ("r", N)
    assert support.parse_callback("sup:s:1") == ("s", 1)
    assert support.parse_callback("sup:x:9223372036854775807") == ("x", 9223372036854775807)
    for bad in ("sup:x:9223372036854775808", "sup:r:12345678901234567890", "sup:q:1", "sup:r:",
                "sup:r:1 ", "xsup:r:1", "card:1", "", None, "sup:r:-1"):
        assert support.parse_callback(bad) is None
    prompt = texts.SUPPORT_PROMPT.format(n=N)
    assert support.n_from_prompt(prompt) == N
    assert support.n_from_prompt(prompt + "\nещё") == N
    assert support.n_from_prompt("x" + prompt) is None and support.n_from_prompt(None) is None
    assert support.n_from_prompt(texts.SUPPORT_PROMPT.format(n="9223372036854775808")) is None
    preview = texts.SUPPORT_PREVIEW.format(n=N) + "\n\n" + "строка1\n\nстрока2"
    assert support.n_from_preview(preview) == (N, "строка1\n\nстрока2")
    assert support.n_from_preview(texts.SUPPORT_PREVIEW.format(n=N)) is None
    assert support.n_from_preview(texts.SUPPORT_DELIVERED.format(n=N) + "\n\nx") is None
    rows = support.question_markup(SHORT_NO, N).inline_keyboard
    assert [[b.callback_data for b in r] for r in rows] == [[f"card:{SHORT_NO}", f"sup:r:{N}"]]
    rows = support.question_markup(None, N).inline_keyboard
    assert [[b.callback_data for b in r] for r in rows] == [[f"sup:r:{N}"]]
    rows = support.preview_markup(N).inline_keyboard
    assert [[(b.text, b.callback_data) for b in r] for r in rows] == [[
        (texts.SUPPORT_BUTTON_SEND, f"sup:s:{N}"), (texts.SUPPORT_BUTTON_CANCEL, f"sup:x:{N}"),
    ]]


# --- support_handlers: фейки апдейтов ---

def make_tg_bot():
    return SimpleNamespace(
        id=BOT_ID,
        send_message=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
        edit_message_text=AsyncMock(),
    )


def make_router(connect=None, config=None):
    router = support_handlers.build_support_router(config or make_cfg(), connect=connect)
    return router, router.message.handlers[0], router.callback_query.handlers[0]


def make_callback(data, *, user=ADMIN, chat=WG, thread=S3, text="пост", bot=None):
    bot = bot or make_tg_bot()
    msg = SimpleNamespace(chat=SimpleNamespace(id=chat, type="supergroup"), message_thread_id=thread,
                          message_id=500, text=text, reply=AsyncMock())
    return SimpleNamespace(data=data, from_user=SimpleNamespace(id=user), message=msg, bot=bot,
                           answer=AsyncMock())


def make_message(text=ANSWER, *, user=ADMIN, chat=WG, thread=S3, chat_type="supergroup",
                 reply_text=None, reply_from=BOT_ID, reply_id=600):
    bot = make_tg_bot()
    reply = None
    if reply_text is not None or reply_id == thread:
        reply = SimpleNamespace(message_id=reply_id, from_user=SimpleNamespace(id=reply_from),
                                text=reply_text)
    return SimpleNamespace(chat=SimpleNamespace(id=chat, type=chat_type), message_thread_id=thread,
                           from_user=SimpleNamespace(id=user), reply_to_message=reply, text=text,
                           bot=bot, reply=AsyncMock())


def passes(handler, message):
    return all(f.callback(message) for f in handler.filters)


def run(handler, event):
    asyncio.run(handler.callback(event))


# 13
def test_reply_button_force_reply(caplog):
    caplog.set_level(logging.DEBUG)
    _, _, on_button = make_router()
    cb = make_callback(f"sup:r:{N}")
    run(on_button, cb)
    args, kwargs = cb.message.reply.await_args
    assert args[0] == texts.SUPPORT_PROMPT.format(n=N)
    markup = kwargs["reply_markup"]
    assert isinstance(markup, ForceReply) and not markup.selective
    assert cb.answer.await_args == call()
    _no_pii(caplog)


@pytest.mark.parametrize("kw", [{"user": STRANGER}, {"chat": -100999}, {"thread": 77}, {"thread": None}])
def test_reply_button_not_allowed(kw, caplog):
    caplog.set_level(logging.DEBUG)
    _, _, on_button = make_router()
    cb = make_callback(f"sup:r:{N}", **kw)
    run(on_button, cb)
    cb.message.reply.assert_not_awaited()
    assert cb.answer.await_args == call()
    _no_pii(caplog)


# 14
def test_admin_reply_preview(caplog):
    caplog.set_level(logging.DEBUG)
    _, on_answer, _ = make_router()
    msg = make_message(reply_text=texts.SUPPORT_PROMPT.format(n=N))
    assert passes(on_answer, msg)
    run(on_answer, msg)
    args, kwargs = msg.reply.await_args
    assert args[0] == texts.SUPPORT_PREVIEW.format(n=N) + "\n\n" + ANSWER
    assert "parse_mode" not in kwargs
    assert [[b.callback_data for b in r] for r in kwargs["reply_markup"].inline_keyboard] == \
        [[f"sup:s:{N}", f"sup:x:{N}"]]
    _no_pii(caplog)


def test_admin_reply_not_text_and_too_long():
    _, on_answer, _ = make_router()
    msg = make_message(text=None, reply_text=texts.SUPPORT_PROMPT.format(n=N))
    assert passes(on_answer, msg)
    run(on_answer, msg)
    assert msg.reply.await_args == call(texts.SUPPORT_SEND_TEXT)
    msg = make_message(text="я" * 2001, reply_text=texts.SUPPORT_PROMPT.format(n=N))
    run(on_answer, msg)
    assert msg.reply.await_args == call(texts.SUPPORT_TOO_LONG)
    msg = make_message(text="я" * 2000, reply_text=texts.SUPPORT_PROMPT.format(n=N))
    run(on_answer, msg)
    assert msg.reply.await_args.args[0].startswith(texts.SUPPORT_PREVIEW.format(n=N))


@pytest.mark.parametrize(
    "kw",
    [
        {"reply_text": "просто сообщение бота"},
        {"reply_text": texts.SUPPORT_PROMPT.format(n=N), "reply_from": STRANGER},
        {"reply_text": texts.SUPPORT_PROMPT.format(n=N), "user": STRANGER},
        {"reply_text": texts.SUPPORT_PROMPT.format(n=N), "chat": -100999},
        {"reply_text": texts.SUPPORT_PROMPT.format(n=N), "thread": 77},
        {"reply_text": texts.SUPPORT_PROMPT.format(n=N), "chat_type": "private"},
        {"reply_text": None, "reply_id": S3},
        {"reply_text": None, "reply_id": 600},
    ],
)
def test_admin_reply_filter_rejects(kw):
    _, on_answer, _ = make_router()
    assert not passes(on_answer, make_message(**kw))


# 15
def make_connect(*, participant="ok", fail=False):
    conns = []

    async def connect(dsn):
        if fail:
            raise OSError("db down")

        def answer(sql, params):
            if sql == SUPPORT_Q:
                return FakeCursor((PID, "s3", BODY, datetime.now(timezone.utc)))
            if sql == PARTICIPANT:
                if participant is None:
                    return FakeCursor(None)
                tomb = datetime.now(timezone.utc) if participant == "tombstoned" else None
                return FakeCursor((TG_ID, tomb))
            return FakeCursor(None)

        conn = FakeConn(answer)
        conns.append(conn)
        return conn

    connect.conns = conns
    return connect


PREVIEW_TEXT = texts.SUPPORT_PREVIEW.format(n=N) + "\n\n" + ANSWER


def test_send_delivered(caplog):
    caplog.set_level(logging.DEBUG)
    connect = make_connect()
    _, _, on_button = make_router(connect)
    cb = make_callback(f"sup:s:{N}", text=PREVIEW_TEXT)
    run(on_button, cb)
    conn = connect.conns[0]
    assert conn.sqls() == [SUPPORT_Q, PARTICIPANT] and conn.closed
    assert conn.params(SUPPORT_Q)[0] == (N,) and conn.params(PARTICIPANT)[0] == (PID,)
    bot = cb.bot
    assert bot.edit_message_reply_markup.await_args.kwargs["reply_markup"] is None
    kw = bot.send_message.await_args.kwargs
    assert kw["chat_id"] == TG_ID
    assert kw["text"] == texts.SUPPORT_ANSWER_PREFIX + "\n\n" + ANSWER
    assert "parse_mode" not in kw
    assert bot.edit_message_text.await_args.kwargs["text"] == texts.SUPPORT_DELIVERED.format(n=N) + "\n\n" + ANSWER
    assert cb.answer.await_args == call()
    _no_pii(caplog)


def test_send_second_press_not_modified(caplog):
    caplog.set_level(logging.DEBUG)
    _, _, on_button = make_router(make_connect())
    bot = make_tg_bot()
    bot.edit_message_reply_markup.side_effect = TelegramBadRequest(
        method=METHOD, message="Bad Request: message is not modified")
    cb = make_callback(f"sup:s:{N}", text=PREVIEW_TEXT, bot=bot)
    run(on_button, cb)
    bot.send_message.assert_not_awaited()
    bot.edit_message_text.assert_not_awaited()
    assert cb.answer.await_args == call()
    _no_pii(caplog)


@pytest.mark.parametrize("participant", ["tombstoned", None])
def test_send_tombstoned_not_delivered(participant, caplog):
    caplog.set_level(logging.DEBUG)
    _, _, on_button = make_router(make_connect(participant=participant))
    cb = make_callback(f"sup:s:{N}", text=PREVIEW_TEXT)
    run(on_button, cb)
    cb.bot.send_message.assert_not_awaited()
    kw = cb.bot.edit_message_text.await_args.kwargs
    assert kw["text"] == texts.SUPPORT_NOT_DELIVERED.format(n=N) + "\n\n" + ANSWER
    assert kw["reply_markup"] is None
    _no_pii(caplog)


def test_send_db_error_try_later(caplog):
    caplog.set_level(logging.DEBUG)
    _, _, on_button = make_router(make_connect(fail=True))
    cb = make_callback(f"sup:s:{N}", text=PREVIEW_TEXT)
    run(on_button, cb)
    assert cb.answer.await_args == call(texts.SUPPORT_TRY_LATER)
    cb.bot.edit_message_reply_markup.assert_not_awaited()
    cb.bot.edit_message_text.assert_not_awaited()
    cb.bot.send_message.assert_not_awaited()
    _no_pii(caplog)


def test_send_n_mismatch_ignored(caplog):
    caplog.set_level(logging.DEBUG)
    connect = make_connect()
    _, _, on_button = make_router(connect)
    cb = make_callback(f"sup:s:{N + 1}", text=PREVIEW_TEXT)
    run(on_button, cb)
    assert connect.conns == []
    cb.bot.send_message.assert_not_awaited()
    cb.bot.edit_message_reply_markup.assert_not_awaited()
    assert cb.answer.await_args == call()
    _no_pii(caplog)


# 16
def test_cancel_removes_buttons(caplog):
    caplog.set_level(logging.DEBUG)
    connect = make_connect()
    _, _, on_button = make_router(connect)
    cb = make_callback(f"sup:x:{N}", text=PREVIEW_TEXT)
    run(on_button, cb)
    assert cb.bot.edit_message_reply_markup.await_args.kwargs["reply_markup"] is None
    cb.bot.send_message.assert_not_awaited()
    assert connect.conns == []
    assert cb.answer.await_args == call()
    _no_pii(caplog)
