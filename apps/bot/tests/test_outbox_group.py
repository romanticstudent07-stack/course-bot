"""Тесты доставки outbox в темы Рабочей группы (bot-group-1): подделка БД и бота, без сети и Postgres."""
import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import (
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.methods import SendMessage

from bot import app as bot_app
from bot import outbox
from bot.config import BotConfig, ConfigError
from bot.outbox import (
    ADDRESSEE,
    CLAIM,
    GROUP_ADDRESSEE,
    MARK,
    REFLECTION,
    TEXT,
    TO_DLQ,
    OutboxWorker,
)

PID = uuid.UUID("11111111-2222-4333-8444-555555555555")
OTHER_PID = uuid.UUID("99999999-2222-4333-8444-555555555555")
TG_ID = 987654321
SHORT_NO = 4242
WG = -1001234567890
REFLECTIONS = 11
REPORTS = 22
BODY = "Секретная-рефлексия <b>x</b>"
FAKE_TOKEN = "123456:TEST-token-not-real"
METHOD = SendMessage(chat_id=1, text="x")
DAY2_PAYLOAD = {"pid": str(PID)}
REFL_PAYLOAD = {"pid": str(PID), "reflection_id": 5}
DEFAULT = object()


def make_cfg(**kw):
    base = {
        "bot_token": FAKE_TOKEN,
        "webapp_url": "",
        "log_level": "INFO",
        "work_group_id": WG,
        "reflections_topic_id": REFLECTIONS,
        "reports_topic_id": REPORTS,
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

    async def execute(self, sql, params=None):
        self.log.append((sql, params))
        return self.answer(sql, params)

    def transaction(self, force_rollback=False):
        return _Tx(self)

    def sqls(self):
        return [e[0] for e in self.log if isinstance(e, tuple)]

    def params(self, sql):
        return [e[1] for e in self.log if isinstance(e, tuple) and e[0] == sql]


def make_db(*, event_type, payload, aggregate_id=None, created_at=None, addressee="ok", refl="ok", body=BODY):
    row = (
        7,
        str(PID) if aggregate_id is None else aggregate_id,
        event_type,
        payload,
        created_at or datetime.now(timezone.utc),
    )
    state = {"marked": False}

    def answer(sql, params):
        if sql == CLAIM:
            return FakeCursor(None if state["marked"] else row)
        if sql == GROUP_ADDRESSEE:
            if addressee == "missing":
                return FakeCursor(None)
            tomb = datetime.now(timezone.utc) if addressee == "tombstoned" else None
            return FakeCursor((TG_ID, SHORT_NO, tomb))
        if sql == REFLECTION:
            if refl is None:
                return FakeCursor(None)
            r_pid = OTHER_PID if refl == "other" else PID
            return FakeCursor((r_pid, 1, 2, 6, body, datetime.now(timezone.utc)))
        if sql == ADDRESSEE:
            return FakeCursor((TG_ID, None))
        if sql == TEXT:
            return FakeCursor(("Привет",))
        if sql == MARK:
            state["marked"] = True
            return FakeCursor(None, rowcount=1)
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
    assert str(TG_ID) not in text
    assert str(PID) not in text
    assert "Секретная-рефлексия" not in text and "<b>x</b>" not in text
    assert str(SHORT_NO) not in text


# 1
def test_day2_alert_to_reports_topic(caplog, sleeps):
    caplog.set_level(logging.DEBUG)
    conn, bot = make_db(event_type="ladder_day2_alert", payload=DAY2_PAYLOAD), make_bot()
    _, res = one(conn, bot)
    assert res[0] == outbox.DONE
    assert conn.sqls() == [CLAIM, GROUP_ADDRESSEE, MARK]
    assert TEXT not in conn.sqls()
    assert isinstance(conn.params(GROUP_ADDRESSEE)[0][0], uuid.UUID)
    kw = bot.send_message.await_args.kwargs
    assert kw["chat_id"] == WG and kw["message_thread_id"] == REPORTS
    assert kw["parse_mode"] == "HTML" and kw["request_timeout"] == 20
    assert f'<a href="tg://user?id={TG_ID}">' in kw["text"]
    assert "Участник #004242" in kw["text"]
    assert bot.send_message.await_count == 1
    assert conn.log[-1] == "commit"
    _no_pii(caplog)


# 2
def test_reflection_to_reflections_topic_body_escaped(caplog, sleeps):
    caplog.set_level(logging.DEBUG)
    conn, bot = make_db(event_type="reflection_submitted", payload=REFL_PAYLOAD), make_bot()
    _, res = one(conn, bot)
    assert res[0] == outbox.DONE
    assert conn.sqls() == [CLAIM, GROUP_ADDRESSEE, REFLECTION, MARK]
    assert conn.params(REFLECTION)[0] == (5,)
    kw = bot.send_message.await_args.kwargs
    assert kw["chat_id"] == WG and kw["message_thread_id"] == REFLECTIONS
    assert "&lt;b&gt;x&lt;/b&gt;" in kw["text"] and "<b>x</b>" not in kw["text"]
    assert "tg://user?id=" in kw["text"]
    _no_pii(caplog)


def test_short_no_none_shows_dash(sleeps):
    def answer(sql, params):
        if sql == CLAIM:
            return FakeCursor((7, str(PID), "ladder_day2_alert", DAY2_PAYLOAD, datetime.now(timezone.utc)))
        if sql == GROUP_ADDRESSEE:
            return FakeCursor((TG_ID, None, None))
        return FakeCursor(None, rowcount=1)

    bot = make_bot()
    one(FakeConn(answer), bot)
    assert "Участник #— " in bot.send_message.await_args.kwargs["text"]


# 3
@pytest.mark.parametrize(
    ("event_type", "payload", "config"),
    [
        ("ladder_day2_alert", DAY2_PAYLOAD, None),
        ("reflection_submitted", REFL_PAYLOAD, None),
        ("ladder_day2_alert", DAY2_PAYLOAD, make_cfg(reports_topic_id=None)),
        ("reflection_submitted", REFL_PAYLOAD, make_cfg(reflections_topic_id=None)),
        ("ladder_day2_alert", DAY2_PAYLOAD, make_cfg(work_group_id=None)),
    ],
)
def test_group_not_configured(event_type, payload, config, caplog, sleeps):
    caplog.set_level(logging.DEBUG)
    conn, bot = make_db(event_type=event_type, payload=payload), make_bot()
    one(conn, bot, config=config)
    assert dlq_codes(conn) == ["group_not_configured"]
    assert conn.sqls() == [CLAIM, GROUP_ADDRESSEE, TO_DLQ, MARK]
    bot.send_message.assert_not_awaited()
    _no_pii(caplog)


def test_tombstoned_only_mark(caplog, sleeps):
    caplog.set_level(logging.DEBUG)
    conn = make_db(event_type="reflection_submitted", payload=REFL_PAYLOAD, addressee="tombstoned")
    bot = make_bot()
    one(conn, bot, config=None)
    assert conn.sqls() == [CLAIM, GROUP_ADDRESSEE, MARK]
    bot.send_message.assert_not_awaited()
    _no_pii(caplog)


def test_expired(caplog, sleeps):
    caplog.set_level(logging.DEBUG)
    conn = make_db(event_type="ladder_day2_alert", payload=DAY2_PAYLOAD,
                   created_at=datetime.now(timezone.utc) - timedelta(hours=25))
    bot = make_bot()
    one(conn, bot)
    assert dlq_codes(conn) == ["expired"]
    assert conn.sqls() == [CLAIM, GROUP_ADDRESSEE, TO_DLQ, MARK]
    bot.send_message.assert_not_awaited()


def test_bad_aggregate_id_and_addressee_not_found(sleeps):
    conn = make_db(event_type="ladder_day2_alert", payload=DAY2_PAYLOAD, aggregate_id="not-a-uuid")
    one(conn, make_bot())
    assert dlq_codes(conn) == ["bad_aggregate_id"]
    assert conn.sqls() == [CLAIM, TO_DLQ, MARK]
    conn = make_db(event_type="ladder_day2_alert", payload=DAY2_PAYLOAD, addressee="missing")
    one(conn, make_bot())
    assert dlq_codes(conn) == ["addressee_not_found"]


# 4
@pytest.mark.parametrize(
    ("event_type", "payload", "refl"),
    [
        ("ladder_day2_alert", ["x"], "ok"),
        ("ladder_day2_alert", {}, "ok"),
        ("ladder_day2_alert", {"pid": str(OTHER_PID)}, "ok"),
        ("ladder_day2_alert", {"pid": "not-a-uuid"}, "ok"),
        ("reflection_submitted", {"pid": str(PID)}, "ok"),
        ("reflection_submitted", {"pid": str(PID), "reflection_id": 0}, "ok"),
        ("reflection_submitted", {"pid": str(PID), "reflection_id": True}, "ok"),
        ("reflection_submitted", {"pid": str(PID), "reflection_id": "5"}, "ok"),
        ("reflection_submitted", REFL_PAYLOAD, "other"),
    ],
)
def test_bad_payload(event_type, payload, refl, caplog, sleeps):
    caplog.set_level(logging.DEBUG)
    conn, bot = make_db(event_type=event_type, payload=payload, refl=refl), make_bot()
    one(conn, bot)
    assert dlq_codes(conn) == ["bad_payload"]
    assert conn.sqls()[-2:] == [TO_DLQ, MARK]
    bot.send_message.assert_not_awaited()
    _no_pii(caplog)


# 5
def test_reflection_not_found(sleeps):
    conn, bot = make_db(event_type="reflection_submitted", payload=REFL_PAYLOAD, refl=None), make_bot()
    one(conn, bot)
    assert dlq_codes(conn) == ["reflection_not_found"]
    bot.send_message.assert_not_awaited()


def test_forbidden_to_dlq(sleeps):
    conn = make_db(event_type="ladder_day2_alert", payload=DAY2_PAYLOAD)
    bot = make_bot(TelegramForbiddenError(method=METHOD, message="Forbidden: bot was kicked"))
    one(conn, bot)
    assert dlq_codes(conn) == ["tg_forbidden"]


def test_network_error_net_retry_without_mark(sleeps):
    conn = make_db(event_type="ladder_day2_alert", payload=DAY2_PAYLOAD)
    bot = make_bot(TelegramNetworkError(method=METHOD, message="net"))
    _, res = one(conn, bot)
    assert res[0] == outbox.NET_RETRY
    assert MARK not in conn.sqls() and TO_DLQ not in conn.sqls()
    assert conn.log[-1] == "rollback"


def test_retry_after_short_then_done(sleeps):
    conn = make_db(event_type="ladder_day2_alert", payload=DAY2_PAYLOAD)
    bot = make_bot(TelegramRetryAfter(method=METHOD, message="flood", retry_after=3), None)
    _, res = one(conn, bot)
    assert res[0] == outbox.DONE
    assert sleeps == [3]
    assert bot.send_message.await_count == 2
    assert conn.sqls().count(MARK) == 1 and TO_DLQ not in conn.sqls()


# 6
def test_logs_clean_and_dlq_payload_as_is(caplog, sleeps):
    caplog.set_level(logging.DEBUG)
    conn = make_db(event_type="reflection_submitted", payload=REFL_PAYLOAD)
    bot = make_bot(TelegramForbiddenError(method=METHOD, message="Forbidden: x"))
    one(conn, bot)
    assert dlq_codes(conn) == ["tg_forbidden"]
    assert conn.params(TO_DLQ)[0][1].obj == {"pid": str(PID), "reflection_id": 5}
    _no_pii(caplog)


# 7
@pytest.mark.parametrize("event_type", ["send1_test", "some_unknown_type"])
def test_private_path_untouched(event_type, sleeps):
    conn = make_db(event_type=event_type, payload={"text_id": "t.key", "tier": "T2"})
    bot = make_bot()
    _, res = one(conn, bot)
    assert res[0] == outbox.DONE
    assert conn.sqls() == [CLAIM, ADDRESSEE, TEXT, MARK]
    kw = bot.send_message.await_args.kwargs
    assert kw["chat_id"] == TG_ID
    assert "message_thread_id" not in kw


# 8
def test_config_topics_parse_and_missing_vars():
    base = {"BOT_TOKEN": FAKE_TOKEN}
    cfg = BotConfig.from_env({**base, "REFLECTIONS_TOPIC_ID": " 11 ", "REPORTS_TOPIC_ID": "22"})
    assert cfg.reflections_topic_id == 11 and cfg.reports_topic_id == 22
    assert cfg.group_missing_vars() == []
    empty = BotConfig.from_env(base)
    assert empty.reflections_topic_id is None and empty.reports_topic_id is None
    assert empty.group_missing_vars() == ["REFLECTIONS_TOPIC_ID", "REPORTS_TOPIC_ID"]
    half = BotConfig.from_env({**base, "REPORTS_TOPIC_ID": "22"})
    assert half.group_missing_vars() == ["REFLECTIONS_TOPIC_ID"]
    for name in ("REFLECTIONS_TOPIC_ID", "REPORTS_TOPIC_ID"):
        with pytest.raises(ConfigError) as ei:
            BotConfig.from_env({**base, name: "abc"})
        assert "abc" not in str(ei.value) and name in str(ei.value)


def _start(monkeypatch, cfg):
    seen = {}

    async def fake_run_worker(bot, dsn, stop, connect=None, config=None):
        seen["config"] = config

    monkeypatch.setattr(outbox, "run_worker", fake_run_worker)

    async def go():
        task = bot_app.start_outbox_worker(SimpleNamespace(), cfg, asyncio.Event())
        await task

    asyncio.run(go())
    return seen


def test_start_worker_warns_topic_names_only(caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    cfg = BotConfig.from_env({"BOT_TOKEN": FAKE_TOKEN, "BOT_DATABASE_URL": "postgresql://u@db/x"})
    seen = _start(monkeypatch, cfg)
    assert seen["config"] is cfg
    warns = [r.getMessage() for r in caplog.records
             if r.levelno == logging.WARNING and "Темы группы не заданы" in r.getMessage()]
    assert len(warns) == 1
    msg = warns[0]
    assert "REFLECTIONS_TOPIC_ID" in msg and "REPORTS_TOPIC_ID" in msg
    assert "BOT_DATABASE_URL" not in msg and "ACCESS_" not in msg


def test_start_worker_no_topic_warning_when_set(caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    cfg = BotConfig.from_env({
        "BOT_TOKEN": FAKE_TOKEN,
        "BOT_DATABASE_URL": "postgresql://u@db/x",
        "REFLECTIONS_TOPIC_ID": "11",
        "REPORTS_TOPIC_ID": "22",
    })
    seen = _start(monkeypatch, cfg)
    assert seen["config"] is cfg
    assert "Темы группы не заданы" not in caplog.text


def test_worker_config_default_none():
    w = OutboxWorker(make_bot(), asyncio.Event())
    assert w.config is None
