"""Тесты воркера outbox (send-1b): подделка БД и бота, asyncio.run, без сети и Postgres."""
import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import psycopg
import pytest
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.methods import SendMessage

from bot import app as bot_app
from bot import outbox
from bot.config import BotConfig, ConfigError
from bot.outbox import ADDRESSEE, CLAIM, MARK, TEXT, TO_DLQ, OutboxWorker

PID = uuid.UUID("11111111-2222-4333-8444-555555555555")
TG_ID = 987654321
SECRET_TEXT = "Привет-секрет"
FAKE_TOKEN = "123456:TEST-token-not-real"
METHOD = SendMessage(chat_id=1, text="x")


class FakeCursor:
    def __init__(self, row=None, rowcount=1):
        self.row = row
        self.rowcount = rowcount

    async def fetchone(self):
        return self.row


class _Tx:
    def __init__(self, conn, force_rollback=False):
        self.conn = conn
        self.force_rollback = force_rollback

    async def __aenter__(self):
        self.conn.log.append("begin")

    async def __aexit__(self, exc_type, exc, tb):
        self.conn.log.append("rollback" if exc_type or self.force_rollback else "commit")
        return False


class FakeConn:
    """execute(sql, params) пишет пару в журнал; ответы — функция answer(sql, params)."""

    def __init__(self, answer):
        self.answer = answer
        self.log: list = []

    async def execute(self, sql, params=None):
        self.log.append((sql, params))
        res = self.answer(sql, params)
        if isinstance(res, BaseException):
            raise res
        return res

    def transaction(self, force_rollback=False):
        return _Tx(self, force_rollback)

    def sqls(self):
        return [e[0] for e in self.log if isinstance(e, tuple)]

    def params(self, sql):
        return [e[1] for e in self.log if isinstance(e, tuple) and e[0] == sql]


def make_db(*, rows=None, aggregate_id=None, payload=None, created_at=None, addressee="ok", text=SECRET_TEXT):
    """rows — сколько раз CLAIM отдаёт строку (дальше None)."""
    state = {"claims": 0, "rows": 1 if rows is None else rows}
    row = (
        7,
        str(PID) if aggregate_id is None else aggregate_id,
        "send1_test",
        {"text_id": "t.key", "tier": "T2"} if payload is None else payload,
        created_at or datetime.now(timezone.utc),
    )

    def answer(sql, params):
        if sql == CLAIM:
            state["claims"] += 1
            return FakeCursor(row if state["claims"] <= state["rows"] else None)
        if sql == ADDRESSEE:
            if addressee == "missing":
                return FakeCursor(None)
            tomb = datetime.now(timezone.utc) if addressee == "tombstoned" else None
            return FakeCursor((TG_ID, tomb))
        if sql == TEXT:
            return FakeCursor(None if text is None else (text,))
        return FakeCursor(None, rowcount=1)

    return FakeConn(answer)


def make_bot(*effects):
    return SimpleNamespace(send_message=AsyncMock(side_effect=list(effects) or None))


def one(conn, bot, stop=None):
    w = OutboxWorker(bot, stop or asyncio.Event())
    return w, asyncio.run(w.process_one(conn))


@pytest.fixture
def sleeps(monkeypatch):
    """Паузы не ждут: записываются; stop по-прежнему прерывает."""
    log: list = []

    async def fake_pause(stop, seconds):
        log.append(seconds)
        return stop.is_set()

    monkeypatch.setattr(outbox, "_pause", fake_pause)
    return log


def dlq_codes(conn):
    return [p[2] for p in conn.params(TO_DLQ)]


# 1
def test_success_order_uuid_html_commit(caplog, sleeps):
    caplog.set_level(logging.DEBUG)
    conn, bot = make_db(), make_bot()
    _, res = one(conn, bot)
    assert res[0] == outbox.DONE
    assert conn.sqls() == [CLAIM, ADDRESSEE, TEXT, MARK]
    assert isinstance(conn.params(ADDRESSEE)[0][0], uuid.UUID)
    kw = bot.send_message.await_args.kwargs
    assert kw["parse_mode"] == "HTML" and kw["chat_id"] == TG_ID and kw["request_timeout"] == 20
    assert conn.log[0] == "begin" and conn.log[-1] == "commit"
    _no_pii(caplog)


# 2
def test_bad_aggregate_id_to_dlq_without_addressee(caplog, sleeps):
    caplog.set_level(logging.DEBUG)
    conn, bot = make_db(aggregate_id="not-a-uuid"), make_bot()
    one(conn, bot)
    assert conn.sqls() == [CLAIM, TO_DLQ, MARK]
    assert dlq_codes(conn) == ["bad_aggregate_id"]
    bot.send_message.assert_not_awaited()
    _no_pii(caplog)


# 3
def test_tombstoned_mark_without_send_and_dlq(caplog, sleeps):
    caplog.set_level(logging.DEBUG)
    conn, bot = make_db(addressee="tombstoned"), make_bot()
    one(conn, bot)
    assert conn.sqls() == [CLAIM, ADDRESSEE, MARK]
    bot.send_message.assert_not_awaited()
    assert "skipped: tombstoned" in caplog.text
    _no_pii(caplog)


# 4
@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"addressee": "missing"}, "addressee_not_found"),
        ({"text": None}, "text_not_found"),
        ({"text": "Привет, {name}"}, "missing_var"),
        ({"payload": {"tier": "T1"}}, "bad_payload"),
        ({"payload": ["x"]}, "bad_payload"),
        ({"payload": {"text_id": "k", "payload_vars": "x"}}, "bad_payload"),
    ],
)
def test_dlq_codes(kwargs, code, caplog, sleeps):
    caplog.set_level(logging.DEBUG)
    conn, bot = make_db(**kwargs), make_bot()
    one(conn, bot)
    assert dlq_codes(conn) == [code]
    assert conn.sqls()[-2:] == [TO_DLQ, MARK]
    assert conn.log[-1] == "commit"
    bot.send_message.assert_not_awaited()
    _no_pii(caplog)


# 5
def test_expired_to_dlq_without_send(caplog, sleeps):
    caplog.set_level(logging.DEBUG)
    conn = make_db(created_at=datetime.now(timezone.utc) - timedelta(hours=25))
    bot = make_bot()
    one(conn, bot)
    assert dlq_codes(conn) == ["expired"]
    assert ADDRESSEE not in conn.sqls()
    bot.send_message.assert_not_awaited()
    _no_pii(caplog)


# 6
def test_retry_after_short_waits_inside_tx(caplog, sleeps):
    caplog.set_level(logging.DEBUG)
    conn = make_db()
    bot = make_bot(TelegramRetryAfter(method=METHOD, message="flood", retry_after=3), None)
    _, res = one(conn, bot)
    assert res[0] == outbox.DONE
    assert sleeps == [3]
    assert conn.sqls().count(MARK) == 1 and TO_DLQ not in conn.sqls()
    assert bot.send_message.await_count == 2
    _no_pii(caplog)


def _three_parts_text():
    return "abcd " * 2000  # render режет на 3 части


# 6б (У1)
def test_retry_after_long_rolls_back_then_resumes(caplog, sleeps):
    caplog.set_level(logging.DEBUG)
    conn = make_db(rows=2, text=_three_parts_text())
    bot = make_bot(None, TelegramRetryAfter(method=METHOD, message="flood", retry_after=40), None, None)
    w = OutboxWorker(bot, asyncio.Event())
    res1 = asyncio.run(w.process_one(conn))
    assert res1 == (outbox.LATER, 40)
    assert MARK not in conn.sqls() and conn.log[-1] == "rollback"
    assert sleeps == []  # внутри транзакции не ждали
    res2 = asyncio.run(w.process_one(conn))
    assert res2[0] == outbox.DONE
    assert conn.sqls().count(MARK) == 1 and TO_DLQ not in conn.sqls()
    texts = [c.kwargs["text"] for c in bot.send_message.await_args_list]
    assert len(texts) == 4
    assert texts.count(texts[0]) == 1  # часть 1 ровно один раз
    assert "(часть 1 из 3)" in texts[0]
    assert "(часть 2 из 3)" in texts[1] and "(часть 2 из 3)" in texts[2] and "(часть 3 из 3)" in texts[3]
    _no_pii(caplog)


def test_run_long_retry_after_pauses_outside_tx(monkeypatch):
    """Цикл run: LATER → пауза вне транзакции (после rollback), затем снова CLAIM."""
    conn = make_db(rows=2)
    stop = asyncio.Event()
    bot = make_bot(TelegramRetryAfter(method=METHOD, message="flood", retry_after=40), None)
    w = OutboxWorker(bot, stop)
    sleeps = []

    async def fake_pause(st, seconds):
        sleeps.append((seconds, conn.log[-1]))
        if seconds == outbox.IDLE_SECONDS:
            stop.set()
        return stop.is_set()

    monkeypatch.setattr(outbox, "_pause", fake_pause)
    asyncio.run(w.run(lambda: _aconn(conn)))
    assert sleeps[0] == (40, "rollback")  # пауза уже после выхода из транзакции
    assert conn.log.index("rollback") < [i for i, e in enumerate(conn.log) if e == (CLAIM, None)][1]
    assert conn.sqls().count(MARK) == 1


async def _aconn(conn):
    conn.close = AsyncMock()
    return conn


# 7
def test_network_error_backoff_then_success(caplog, sleeps):
    caplog.set_level(logging.DEBUG)
    conn = make_db(rows=3)
    stop = asyncio.Event()
    bot = make_bot(TelegramNetworkError(method=METHOD, message="net"),
                   TelegramNetworkError(method=METHOD, message="net"), None)
    w = OutboxWorker(bot, stop)
    marks_before_success = []
    for _ in range(2):
        outcome, _ = asyncio.run(w.process_one(conn))
        assert outcome == outbox.NET_RETRY
        marks_before_success.append(conn.sqls().count(MARK) + conn.sqls().count(TO_DLQ))
        sleeps.append(w.next_backoff())
    assert marks_before_success == [0, 0]
    assert sleeps == [1, 2]
    outcome, _ = asyncio.run(w.process_one(conn))
    assert outcome == outbox.DONE and conn.sqls().count(MARK) == 1
    assert w.net_failures == 0
    assert conn.log.count("rollback") == 2
    _no_pii(caplog)


# 8
def test_three_parts_network_fail_on_second_resumes(caplog, sleeps):
    caplog.set_level(logging.DEBUG)
    conn = make_db(rows=2, text=_three_parts_text())
    bot = make_bot(None, TelegramNetworkError(method=METHOD, message="net"), None, None)
    w = OutboxWorker(bot, asyncio.Event())
    assert asyncio.run(w.process_one(conn))[0] == outbox.NET_RETRY
    assert asyncio.run(w.process_one(conn))[0] == outbox.DONE
    texts = [c.kwargs["text"] for c in bot.send_message.await_args_list]
    assert len(texts) == 4
    assert sum("(часть 1 из 3)" in t for t in texts) == 1
    assert conn.sqls().count(MARK) == 1
    assert w.sent == {}
    _no_pii(caplog)


# 9
def test_cant_parse_entities_falls_back_to_plain(caplog, sleeps):
    caplog.set_level(logging.DEBUG)
    conn = make_db(text="A & B <b>x</b>")
    bot = make_bot(TelegramBadRequest(method=METHOD, message="Bad Request: Can't parse entities: x"), None)
    _, res = one(conn, bot)
    assert res[0] == outbox.DONE
    calls = bot.send_message.await_args_list
    assert calls[0].kwargs["parse_mode"] == "HTML"
    assert calls[1].kwargs["parse_mode"] is None and calls[1].kwargs["text"] == "A & B x"
    assert conn.sqls().count(MARK) == 1 and TO_DLQ not in conn.sqls()
    _no_pii(caplog)


# 10
@pytest.mark.parametrize(
    ("exc", "code"),
    [
        (TelegramForbiddenError(method=METHOD, message="Forbidden: bot was blocked by the user"), "tg_forbidden"),
        (TelegramBadRequest(method=METHOD, message="Bad Request: chat not found"), "tg_bad_request"),
    ],
)
def test_final_telegram_errors(exc, code, caplog, sleeps):
    caplog.set_level(logging.DEBUG)
    conn, bot = make_db(), make_bot(exc)
    one(conn, bot)
    assert dlq_codes(conn) == [code]
    payload = conn.params(TO_DLQ)[0][1]
    assert payload.obj == {"text_id": "t.key", "tier": "T2"}
    assert "blocked" not in caplog.text and "chat not found" not in caplog.text
    _no_pii(caplog)


# 11
def test_stop_during_send_finishes_row_no_second_claim(sleeps):
    conn = make_db(rows=5)
    stop = asyncio.Event()

    async def send(**kw):
        stop.set()

    bot = SimpleNamespace(send_message=AsyncMock(side_effect=send))
    asyncio.run(OutboxWorker(bot, stop).run(lambda: _aconn(conn)))
    assert conn.sqls().count(CLAIM) == 1
    assert conn.sqls().count(MARK) == 1 and conn.log[-1] == "commit"


# 11б (У2)
def test_stop_during_retry_after_pause_no_mark_no_claim(monkeypatch):
    conn = make_db(rows=5, text=_three_parts_text())
    stop = asyncio.Event()

    async def pause(st, seconds):
        stop.set()  # stop пришёл во время паузы
        return True

    monkeypatch.setattr(outbox, "_pause", pause)
    bot = make_bot(None, TelegramRetryAfter(method=METHOD, message="flood", retry_after=3))
    asyncio.run(OutboxWorker(bot, stop).run(lambda: _aconn(conn)))
    assert conn.sqls().count(CLAIM) == 1
    assert MARK not in conn.sqls() and TO_DLQ not in conn.sqls()
    assert conn.log[-1] == "rollback"


def test_stop_during_long_retry_after_pause_outside_tx(monkeypatch):
    conn = make_db(rows=5)
    stop = asyncio.Event()

    async def pause(st, seconds):
        stop.set()
        return True

    monkeypatch.setattr(outbox, "_pause", pause)
    bot = make_bot(TelegramRetryAfter(method=METHOD, message="flood", retry_after=40))
    asyncio.run(OutboxWorker(bot, stop).run(lambda: _aconn(conn)))
    assert conn.sqls().count(CLAIM) == 1 and MARK not in conn.sqls()


def test_operational_error_reconnects_without_dsn(caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    stop = asyncio.Event()
    calls = {"n": 0}

    async def connect():
        calls["n"] += 1
        if calls["n"] == 1:
            raise psycopg.OperationalError("connection to postgresql://u:pw@db failed")
        stop.set()
        return await _aconn(make_db(rows=0))

    async def pause(st, seconds):
        return stop.is_set()

    monkeypatch.setattr(outbox, "_pause", pause)
    asyncio.run(OutboxWorker(make_bot(), stop).run(connect))
    assert calls["n"] == 2
    assert "OperationalError" in caplog.text and "pw@db" not in caplog.text


# 12 — общая проверка логов в тестах 1–10
def _no_pii(caplog):
    text = caplog.text
    assert str(TG_ID) not in text
    assert str(PID) not in text
    assert SECRET_TEXT not in text and "abcd" not in text


# 13
def test_config_database_url():
    base = {"BOT_TOKEN": FAKE_TOKEN}
    cfg = BotConfig.from_env(base)
    assert cfg.database_url == ""
    assert bot_app.start_outbox_worker(SimpleNamespace(), cfg, asyncio.Event()) is None
    secret_dsn = "postgresql+psycopg://coursebot_bot:pw123@db:5432/x"
    with pytest.raises(ConfigError) as ei:
        BotConfig.from_env({**base, "BOT_DATABASE_URL": secret_dsn})
    assert "pw123" not in str(ei.value) and "coursebot_bot" not in str(ei.value)
    good = BotConfig.from_env({**base, "BOT_DATABASE_URL": "  postgresql://u:pw123@db:5432/x "})
    assert good.database_url == "postgresql://u:pw123@db:5432/x"
    assert "pw123" not in repr(good) and FAKE_TOKEN not in repr(good)


# 14
class _Denied(psycopg.errors.InsufficientPrivilege):
    pass


def _selfcheck_conn(second_ok=False):
    def answer(sql, params):
        if sql == outbox.WHOAMI:
            return FakeCursor(("coursebot_bot", "coursebot_bot", True))
        if "consent_events" in sql:
            return _Denied("denied")
        if "outbox" in sql:
            return FakeCursor(None) if second_ok else _Denied("denied")
        raise AssertionError(sql)

    return FakeConn(answer)


def test_selfcheck_ok(capsys):
    conn = _selfcheck_conn()
    assert asyncio.run(outbox.selfcheck(conn)) == 0
    out = capsys.readouterr().out
    assert out.count("denied OK") == 2 and "coursebot_bot" in out
    assert conn.log.count("rollback") == 2


def test_selfcheck_fail_when_select_passes(capsys):
    assert asyncio.run(outbox.selfcheck(_selfcheck_conn(second_ok=True))) == 1
    assert "FAIL" in capsys.readouterr().out


def test_selfcheck_empty_dsn(monkeypatch, capsys):
    monkeypatch.delenv("BOT_DATABASE_URL", raising=False)
    assert outbox.main(["selfcheck"]) == 1
