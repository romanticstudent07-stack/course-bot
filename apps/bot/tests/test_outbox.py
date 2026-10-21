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
    TelegramConflictError,
    TelegramNetworkError,
    TelegramNotFound,
    TelegramRetryAfter,
    TelegramServerError,
    TelegramUnauthorizedError,
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
PII_NAME = "Анастасия-ПДн"
PII_VARS = {"name": PII_NAME, "phone": "+79990001122"}
PII_PAYLOAD = {"text_id": "t.key", "tier": "T2", "payload_vars": PII_VARS}
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


def make_db(*, rows=None, aggregate_id=None, payload=None, created_at=None, addressee="ok", text=SECRET_TEXT,
            mark_rowcount=1):
    """rows — сколько раз CLAIM отдаёт строку (дальше None)."""
    state = {"claims": 0, "rows": 1 if rows is None else rows, "marked": False}
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
            # Помеченную строку CLAIM больше не отдаёт (журнал транзакций не моделируется).
            give = state["claims"] <= state["rows"] and not state["marked"]
            return FakeCursor(row if give else None)
        if sql == ADDRESSEE:
            if addressee == "missing":
                return FakeCursor(None)
            tomb = datetime.now(timezone.utc) if addressee == "tombstoned" else None
            return FakeCursor((TG_ID, tomb))
        if sql == TEXT:
            return FakeCursor(None if text is None else (text,))
        if sql == MARK:
            state["marked"] = True
            return FakeCursor(None, rowcount=mark_rowcount)
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
    conn, bot = make_db(aggregate_id="not-a-uuid", payload=PII_PAYLOAD, text=SECRET_TEXT + " {name}"), make_bot()
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
        ({"addressee": "missing", "payload": PII_PAYLOAD}, "addressee_not_found"),
        ({"text": None, "payload": PII_PAYLOAD}, "text_not_found"),
        ({"text": SECRET_TEXT + " {name} {absent}", "payload": PII_PAYLOAD}, "missing_var"),
        ({"payload": {"tier": "T1", "payload_vars": PII_VARS}}, "bad_payload"),
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
    conn = make_db(created_at=datetime.now(timezone.utc) - timedelta(hours=25), payload=PII_PAYLOAD,
                   text=SECRET_TEXT + " {name}")
    bot = make_bot()
    one(conn, bot)
    assert dlq_codes(conn) == ["expired"]
    assert conn.sqls() == [CLAIM, ADDRESSEE, TO_DLQ, MARK]  # Ф7: expired после tombstone-гейта
    bot.send_message.assert_not_awaited()
    _no_pii(caplog)


def test_expired_naive_created_at_is_utc(sleeps):
    """Ф9: created_at без пояса считается UTC."""
    naive = datetime.now(timezone.utc).replace(tzinfo=None)
    conn = make_db(created_at=naive - timedelta(hours=25))
    one(conn, make_bot())
    assert dlq_codes(conn) == ["expired"]
    conn = make_db(created_at=naive - timedelta(hours=1))
    one(conn, make_bot())
    assert dlq_codes(conn) == [] and conn.sqls().count(MARK) == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"created_at": datetime.now(timezone.utc) - timedelta(hours=25)},
        {"payload": {"tier": "T1", "payload_vars": PII_VARS}},
        {"text": None},
    ],
)
def test_tombstoned_beats_expired_bad_payload_no_dlq(kwargs, caplog, sleeps):
    """Ф7: стёртый адресат + просроченная/битая строка → только MARK, DLQ пуст, payload не копируется."""
    caplog.set_level(logging.DEBUG)
    conn, bot = make_db(addressee="tombstoned", **kwargs), make_bot()
    one(conn, bot)
    assert conn.sqls() == [CLAIM, ADDRESSEE, MARK]
    assert TO_DLQ not in conn.sqls()
    bot.send_message.assert_not_awaited()
    _no_pii(caplog)


def test_mark_rowcount_zero_warns_and_commits(caplog, sleeps):
    """Ф11."""
    caplog.set_level(logging.DEBUG)
    conn = make_db(mark_rowcount=0)
    _, res = one(conn, make_bot())
    assert res[0] == outbox.DONE
    assert conn.log[-1] == "commit"
    assert any(r.levelno == logging.WARNING and "rowcount=0" in r.getMessage() for r in caplog.records)


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


# 7 (Ф10: через run)
def test_network_error_backoff_then_success(caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    conn = make_db(rows=3)
    stop = asyncio.Event()
    bot = make_bot(TelegramNetworkError(method=METHOD, message="net"),
                   TelegramNetworkError(method=METHOD, message="net"), None)
    pauses = []

    async def fake_pause(st, seconds):
        # Пауза после неудачи: строка не помечена и не в DLQ, транзакция откатилась.
        pauses.append((seconds, conn.log[-1], conn.sqls().count(MARK), conn.sqls().count(TO_DLQ)))
        if len(pauses) == 3:
            stop.set()
        return stop.is_set()

    monkeypatch.setattr(outbox, "_pause", fake_pause)
    w = OutboxWorker(bot, stop)
    asyncio.run(w.run(lambda: _aconn(conn)))
    assert pauses[:2] == [(1, "rollback", 0, 0), (2, "rollback", 0, 0)]
    assert pauses[2] == (outbox.IDLE_SECONDS, "commit", 1, 0)  # после успеха — пустой CLAIM
    assert conn.sqls().count(MARK) == 1 and TO_DLQ not in conn.sqls()
    assert w.net_failures == 0
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
    assert w.progress == {}
    _no_pii(caplog)


# 9
def test_cant_parse_entities_falls_back_to_plain(caplog, sleeps):
    caplog.set_level(logging.DEBUG)
    conn = make_db(text="A &amp; B <b>x</b>")
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
        (TelegramNotFound(method=METHOD, message="Not Found: chat not found"), "tg_not_found"),
        (TelegramConflictError(method=METHOD, message="Conflict: chat not found"), "tg_api_error"),
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
    assert PII_NAME not in text and "+79990001122" not in text


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


# Ф12: 5xx и таймаут — повтор без MARK
@pytest.mark.parametrize(
    "exc",
    [TelegramServerError(method=METHOD, message="Internal Server Error"), asyncio.TimeoutError()],
)
def test_server_error_and_timeout_retry_without_mark(exc, sleeps):
    conn = make_db(rows=2)
    bot = make_bot(exc, None)
    w = OutboxWorker(bot, asyncio.Event())
    assert asyncio.run(w.process_one(conn))[0] == outbox.NET_RETRY
    assert MARK not in conn.sqls() and TO_DLQ not in conn.sqls() and conn.log[-1] == "rollback"
    assert asyncio.run(w.process_one(conn))[0] == outbox.DONE
    assert conn.sqls().count(MARK) == 1


# Ф12: Unauthorized — доставка прекращена, ERROR сразу и раз в 10 мин, пауза прерывается stop
def test_unauthorized_stops_delivery_and_repeats_error(caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    conn = make_db(rows=5)
    stop = asyncio.Event()
    pauses = []

    async def fake_pause(st, seconds):
        pauses.append(seconds)
        if len(pauses) == 3:
            stop.set()
        return stop.is_set()

    monkeypatch.setattr(outbox, "_pause", fake_pause)
    bot = make_bot(TelegramUnauthorizedError(method=METHOD, message="Unauthorized"))
    asyncio.run(OutboxWorker(bot, stop).run(lambda: _aconn(conn)))
    assert pauses == [600, 600, 600]
    errors = [r for r in caplog.records if r.levelno == logging.ERROR and "Unauthorized" in r.getMessage()]
    assert len(errors) == 3
    assert conn.sqls().count(CLAIM) == 1 and MARK not in conn.sqls()
    assert bot.send_message.await_count == 1
    assert FAKE_TOKEN not in caplog.text


# Ф1: неожиданная ошибка — oid и класс в логе; 5 подряд → DLQ internal_error + MARK
def test_internal_error_five_times_then_dlq(caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    conn = make_db(rows=10, payload=PII_PAYLOAD, text=SECRET_TEXT + " {name}")
    stop = asyncio.Event()
    pauses = []

    async def fake_pause(st, seconds):
        pauses.append(seconds)
        if seconds == outbox.IDLE_SECONDS or len(pauses) > 20:
            stop.set()
        return stop.is_set()

    monkeypatch.setattr(outbox, "_pause", fake_pause)
    bot = make_bot(*[KeyError("boom")] * 5)
    w = OutboxWorker(bot, stop)
    asyncio.run(w.run(lambda: _aconn(conn)))
    assert pauses[:5] == [outbox.DB_RETRY_SECONDS] * 5
    assert bot.send_message.await_count == 5
    assert dlq_codes(conn) == ["internal_error"]
    i = conn.sqls().index(TO_DLQ)
    assert conn.sqls()[i + 1] == MARK
    errs = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errs) == 5 and all("outbox 7:" in m and "KeyError" in m for m in errs)
    assert w.failures == {}
    _no_pii(caplog)


def test_internal_error_dlq_failed_pauses_60(caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)

    def answer(sql, params):
        if sql == CLAIM:
            return FakeCursor((7, str(PID), "send1_test", {"text_id": "t.key"}, datetime.now(timezone.utc)))
        if sql == TO_DLQ:
            return RuntimeError("dlq broken")
        if sql == ADDRESSEE:
            return FakeCursor((TG_ID, None))
        if sql == TEXT:
            return FakeCursor(("x",))
        return FakeCursor(None)

    conn = FakeConn(answer)
    stop = asyncio.Event()
    pauses = []

    async def fake_pause(st, seconds):
        pauses.append(seconds)
        if len(pauses) == 6:
            stop.set()
        return stop.is_set()

    monkeypatch.setattr(outbox, "_pause", fake_pause)
    w = OutboxWorker(make_bot(*[ValueError()] * 5), stop)
    asyncio.run(w.run(lambda: _aconn(conn)))
    assert pauses == [5, 5, 5, 5, 5, 60]
    assert any("outbox 7: DLQ internal_error не удался" in r.getMessage() for r in caplog.records)


# Ф5: бюджет ожиданий retry_after внутри одной транзакции — 25 с
def test_retry_after_budget_exceeded_rolls_back(sleeps):
    conn = make_db(rows=2)
    flood = [TelegramRetryAfter(method=METHOD, message="f", retry_after=10) for _ in range(3)]
    bot = make_bot(*flood, None)
    w = OutboxWorker(bot, asyncio.Event())
    assert asyncio.run(w.process_one(conn)) == (outbox.LATER, 10)
    assert sleeps == [10, 10]  # третье ожидание (сумма 30 > 25) — уже вне транзакции
    assert MARK not in conn.sqls() and conn.log[-1] == "rollback"
    assert asyncio.run(w.process_one(conn))[0] == outbox.DONE
    assert conn.sqls().count(MARK) == 1


# Ф6: сохранённый прогресс не совпал (другое число частей) → с первой части
def test_progress_mismatch_restarts_from_first_part(sleeps):
    conn = make_db(rows=1, text=_three_parts_text())
    bot = make_bot()
    w = OutboxWorker(bot, asyncio.Event())
    w.progress[7] = (1, 2, "html")  # было 2 части, теперь 3
    asyncio.run(w.process_one(conn))
    texts = [c.kwargs["text"] for c in bot.send_message.await_args_list]
    assert len(texts) == 3 and "(часть 1 из 3)" in texts[0]


def test_progress_matching_resumes_mode_mismatch_restarts(sleeps):
    # Совпало (3 части, html) → только часть 3.
    bot = make_bot()
    w = OutboxWorker(bot, asyncio.Event())
    w.progress[7] = (2, 3, "html")
    asyncio.run(w.process_one(make_db(text=_three_parts_text())))
    assert bot.send_message.await_count == 1
    # Сохранено html, а шаблон теперь даёт plain (голый &) → с первой части.
    bot2 = make_bot()
    w2 = OutboxWorker(bot2, asyncio.Event())
    w2.progress[7] = (2, 3, "html")
    asyncio.run(w2.process_one(make_db(text="abcd & " * 1500)))
    calls = bot2.send_message.await_args_list
    assert len(calls) == 3 and calls[0].kwargs["parse_mode"] is None
    assert "(часть 1 из 3)" in calls[0].kwargs["text"]


# Ф8
def test_connect_timeout_argument(monkeypatch):
    seen = {}

    async def fake_connect(dsn, **kw):
        seen.update(kw, dsn=dsn)
        return "conn"

    monkeypatch.setattr(outbox.psycopg.AsyncConnection, "connect", fake_connect)
    assert asyncio.run(outbox._connect("postgresql://u@db/x")) == "conn"
    assert seen == {"dsn": "postgresql://u@db/x", "autocommit": True, "connect_timeout": 10}


# Ф2
def test_run_start_polling_keeps_session(monkeypatch):
    calls = {}

    class FakeDp:
        def resolve_used_update_types(self):
            return []

        async def start_polling(self, bot, **kw):
            calls.update(kw)

    closed = AsyncMock()
    fake_bot = SimpleNamespace(session=SimpleNamespace(close=closed))
    monkeypatch.setattr(bot_app, "Bot", lambda token: fake_bot)
    monkeypatch.setattr(bot_app, "build_dispatcher", lambda cfg: FakeDp())
    monkeypatch.setattr(bot_app, "wait_until_no_webhook", AsyncMock())
    cfg = BotConfig(bot_token=FAKE_TOKEN, webapp_url="", log_level="INFO")
    asyncio.run(bot_app.run(cfg))
    assert calls["close_bot_session"] is False
    closed.assert_awaited_once()
