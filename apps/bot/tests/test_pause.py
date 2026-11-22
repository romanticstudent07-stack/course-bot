"""Тесты пауз (bot-pause-1): local_dates, labels_for, разбор callback, decide, кнопки, тик. Без сети и Postgres."""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramNetworkError
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from psycopg.types.json import Jsonb

from bot import pause, pause_watch, texts
from bot.app import build_dispatcher
from bot.config import BotConfig
from bot.life import LOCK
from bot.pause import DECIDE_CHECK, DECIDE_ROW, EVENT, KEY_EXISTS, KEY_TTL, WATCH

FAKE_TOKEN = "4401:TEST-token-not-real"
GROUP, TOPIC, ADMIN, STRANGER, TG_USER, MID, SHORT = 4402, 4403, 4404, 4405, 4406, 4407, 4408
PID = "00000000-0000-0000-0000-000000004409"
PAUSE_ID = 4410
UTC = timezone.utc
NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
# 20.11 00:00 МСК … 23.11 00:00 МСК → N = 3, последний день 22.11
START = datetime(2026, 11, 19, 21, 0, tzinfo=UTC)
END = datetime(2026, 11, 22, 21, 0, tzinfo=UTC)


def cfg(**kw) -> BotConfig:
    base = dict(bot_token=FAKE_TOKEN, webapp_url="", log_level="INFO", database_url="postgresql://x/y",
                work_group_id=GROUP, access_admin_topic_id=TOPIC, access_admin_ids=frozenset({ADMIN}))
    base.update(kw)
    return BotConfig(**base)


def row(status="requested", start=START, end=END, tz="Europe/Moscow", now=NOW, open_=True) -> pause.Row:
    return pause.Row(PAUSE_ID, PID, status, start, end, TG_USER, SHORT, tz, now, open_)


# --- подделка соединения (по образцу test_revive) ---

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


def db(found=True, open_=True, key_rowcount=1, fail_on=None, watch_rows=(), decided=False):
    def answer(sql, params):
        if sql == fail_on:
            raise RuntimeError("db down")
        if sql == DECIDE_ROW:
            return FakeCursor((PID,) if found else None)
        if sql == DECIDE_CHECK:
            return FakeCursor((open_,))
        if sql == KEY_TTL:
            return FakeCursor(None, rowcount=key_rowcount)
        if sql == KEY_EXISTS:
            return FakeCursor((params[0],) if decided else None)
        if sql == WATCH:
            return FakeCursor(rows=[tuple(r) for r in watch_rows])
        return FakeCursor(None)
    return FakeConn(answer)


# --- local_dates ---

def test_local_dates_msk_n3():
    first, last, n, utc = pause.local_dates(START, END, "Europe/Moscow")
    assert (first.isoformat(), last.isoformat(), n, utc) == ("2026-11-20", "2026-11-22", 3, False)


@pytest.mark.parametrize("tz", [None, "", "Mars/Olympus"])
def test_local_dates_utc_fallback(tz):
    first, last, n, utc = pause.local_dates(START, END, tz)
    # по UTC: 19.11 21:00 … 22.11 21:00
    assert (first.isoformat(), last.isoformat(), n, utc) == ("2026-11-19", "2026-11-21", 3, True)
    assert pause.fmt_day(first, utc) == "19.11 (UTC)"


def test_local_dates_dst_transition():
    # Europe/Berlin: 25.10.2026 переход CEST → CET; 24.10 00:00 (UTC+2) … 27.10 00:00 (UTC+1)
    start = datetime(2026, 10, 23, 22, 0, tzinfo=UTC)
    end = datetime(2026, 10, 26, 23, 0, tzinfo=UTC)
    first, last, n, utc = pause.local_dates(start, end, "Europe/Berlin")
    assert (first.isoformat(), last.isoformat(), n, utc) == ("2026-10-24", "2026-10-26", 3, False)


@pytest.mark.parametrize("days", [1, 3, 7])
def test_local_dates_n(days):
    first, last, n, _ = pause.local_dates(START, START + timedelta(days=days), "Europe/Moscow")
    assert n == days and (last - first).days == days - 1


# --- labels_for ---

def test_labels_for_statuses():
    assert pause.labels_for(row("requested"), 3, False) == ["requested"]
    assert pause.labels_for(row("requested", open_=False), 3, False) == []
    assert pause.labels_for(row("approved", open_=False), 3, True) == ["approved"]
    assert pause.labels_for(row("rejected", open_=False), 3, True) == ["rejected"]
    assert pause.labels_for(row("cancelled", open_=False), 3, False) == ["cancelled"]
    assert pause.labels_for(row("ended", open_=False), 3, True) == ["ended"]
    assert pause.labels_for(row("strange", open_=False), 3, True) == []


def test_labels_for_active_auto():
    active = row("active", now=START + timedelta(hours=1), open_=False)
    assert pause.labels_for(active, 3, decided=False) == ["auto", "active"]
    assert pause.labels_for(active, 3, decided=True) == ["active"]


@pytest.mark.parametrize(("days", "expected"), [(1, False), (2, True), (7, True)])
def test_labels_for_ending(days, expected):
    end = START + timedelta(days=days)
    r = row("active", end=end, now=end - timedelta(hours=5), open_=False)
    assert pause.is_ending(r, days) is expected
    assert ("ending" in pause.labels_for(r, days, True)) is expected
    far = row("active", end=end, now=end - timedelta(hours=25), open_=False)
    assert pause.is_ending(far, days) is False


# --- разбор callback ---

@pytest.mark.parametrize(("data", "expected"), [
    ("pse:a:4410", (True, 4410)),
    ("pse:r:4410", (False, 4410)),
    ("pse:r:" + "9" * 18, (False, int("9" * 18))),
    ("pse:a:" + "9" * 19, None),
    ("pse:x:4410", None),
    ("pse:a:", None),
    ("pse:a:-1", None),
    ("pse:a:4410:1", None),
    ("acc:g:4410", None),
    (None, None),
])
def test_parse_callback(data, expected):
    assert pause.parse_callback(data) == expected


# --- decide ---

def _assert_no_returning():
    for sql in (WATCH, DECIDE_ROW, DECIDE_CHECK, KEY_TTL, KEY_EXISTS, EVENT, LOCK):
        assert "RETURNING" not in sql.upper()


@pytest.mark.parametrize(("approve", "code", "kind"), [(True, pause.APPROVED, "pause_approved"),
                                                       (False, pause.REJECTED, "pause_rejected")])
def test_decide_writes_event(approve, code, kind):
    conn = db()
    assert asyncio.run(pause.decide(conn, PAUSE_ID, approve)) == code
    assert conn.sqls() == [DECIDE_ROW, LOCK, DECIDE_CHECK, KEY_TTL, EVENT]
    assert conn.log[0] == "begin" and conn.log[-1] == "commit"
    assert conn.params_of(LOCK) == [(PID,)]
    assert conn.params_of(KEY_TTL) == [(f"pause_decide:{PID}:{PAUSE_ID}", "pause_decide", code)]
    (pid, ev_kind, payload), = conn.params_of(EVENT)
    assert pid == PID and ev_kind == kind and isinstance(payload, Jsonb)
    assert payload.obj == {"pause_id": PAUSE_ID} and type(payload.obj["pause_id"]) is int
    assert "'bot', 'owner'" in EVENT
    _assert_no_returning()


def test_decide_gone():
    conn = db(found=False)
    assert asyncio.run(pause.decide(conn, PAUSE_ID, True)) == pause.GONE
    assert conn.sqls() == [DECIDE_ROW]


def test_decide_not_open():
    conn = db(open_=False)
    assert asyncio.run(pause.decide(conn, PAUSE_ID, True)) == pause.NOT_OPEN
    assert conn.sqls() == [DECIDE_ROW, LOCK, DECIDE_CHECK]


def test_decide_already():
    conn = db(key_rowcount=0)
    assert asyncio.run(pause.decide(conn, PAUSE_ID, False)) == pause.ALREADY
    assert conn.sqls() == [DECIDE_ROW, LOCK, DECIDE_CHECK, KEY_TTL]


def test_decide_db_error_try_later():
    conn = db(fail_on=EVENT)
    assert asyncio.run(pause.decide(conn, PAUSE_ID, True)) == pause.TRY_LATER
    assert conn.log[-1] == "rollback"


# --- кнопки через Dispatcher (Bot API перехвачен) ---

async def _feed(config, update, conn):
    bot = Bot(token=FAKE_TOKEN)
    calls: list = []
    connected: list = []

    async def fake_request(_bot, method, timeout=None):
        calls.append(method)
        return True

    bot.session.make_request = AsyncMock(side_effect=fake_request)

    async def connect(_dsn):
        connected.append(1)
        return conn

    dp = build_dispatcher(config, connect)
    await dp.feed_update(bot, update)
    await bot.session.close()
    return calls, connected


def _button(data, chat_id=GROUP, user=ADMIN):
    return Update(update_id=2, callback_query=CallbackQuery(
        id="cb1", from_user=User(id=user, is_bot=False, first_name="A"), chat_instance="ci", data=data,
        message=Message(message_id=MID, chat=Chat(id=chat_id, type="supergroup"), text="карточка",
                        date=datetime.now(UTC))))


@pytest.mark.parametrize(("chat_id", "user"), [(GROUP + 99, ADMIN), (GROUP, STRANGER)])
def test_button_stranger_without_db(chat_id, user):
    conn = db()
    calls, connected = asyncio.run(_feed(cfg(), _button(f"pse:a:{PAUSE_ID}", chat_id=chat_id, user=user), conn))
    assert len(calls) == 1 and isinstance(calls[0], AnswerCallbackQuery) and calls[0].text is None
    assert connected == [] and conn.log == []


def test_button_admin_approve_edits_card():
    conn = db()
    calls, _ = asyncio.run(_feed(cfg(), _button(f"pse:a:{PAUSE_ID}"), conn))
    edits = [c for c in calls if isinstance(c, EditMessageText)]
    answers = [c for c in calls if isinstance(c, AnswerCallbackQuery)]
    assert len(edits) == 1 and edits[0].reply_markup is None
    assert texts.PAUSE_DONE_APPROVED in edits[0].text
    assert len(answers) == 1 and answers[0].text is None
    assert not [c for c in calls if isinstance(c, SendMessage)]


def test_button_admin_try_later_buttons_stay():
    conn = db(fail_on=EVENT)
    calls, _ = asyncio.run(_feed(cfg(), _button(f"pse:r:{PAUSE_ID}"), conn))
    answers = [c for c in calls if isinstance(c, AnswerCallbackQuery)]
    assert len(answers) == 1 and answers[0].text == texts.PAUSE_TRY_LATER
    assert not [c for c in calls if isinstance(c, EditMessageText)]
    assert not [c for c in calls if isinstance(c, SendMessage)]


# --- тик наблюдателя ---

class FakeBot:
    def __init__(self, error=None):
        self.error, self.sent = error, []

    async def send_message(self, **kw):
        self.sent.append(kw)
        if self.error is not None:
            raise self.error


def _tick(conn, bot):
    return asyncio.run(pause_watch.tick(conn, bot, cfg()))


def test_tick_key_inserted_send_commit():
    conn = db(watch_rows=[row("requested")])
    bot = FakeBot()
    counts = _tick(conn, bot)
    assert counts["sent"] == 1
    assert conn.sqls() == [WATCH, KEY_TTL]
    assert conn.params_of(KEY_TTL) == [(f"pause_note:{PID}:{PAUSE_ID}:requested", "pause_note", "requested")]
    assert conn.log[-1] == "commit"
    (msg,) = bot.sent
    assert msg["chat_id"] == GROUP and msg["message_thread_id"] == TOPIC
    assert msg["text"] == texts.PAUSE_CARD.format(who="#004408", first="20.11", last="22.11", days=3)
    datas = [b.callback_data for b in msg["reply_markup"].inline_keyboard[0]]
    assert datas == [f"pse:a:{PAUSE_ID}", f"pse:r:{PAUSE_ID}"]


def test_tick_key_exists_no_send():
    conn = db(watch_rows=[row("approved", open_=False)], key_rowcount=0)
    bot = FakeBot()
    counts = _tick(conn, bot)
    assert counts["skip"] == 1 and bot.sent == []


def test_tick_network_error_rollback():
    method = SendMessage(chat_id=TG_USER, text="x")
    conn = db(watch_rows=[row("approved", open_=False)])
    bot = FakeBot(TelegramNetworkError(method=method, message="net"))
    counts = _tick(conn, bot)
    assert counts["retry"] == 1 and conn.log[-1] == "rollback"
    assert bot.sent[0]["chat_id"] == TG_USER


def test_tick_forbidden_commit():
    method = SendMessage(chat_id=TG_USER, text="x")
    conn = db(watch_rows=[row("approved", open_=False)])
    bot = FakeBot(TelegramForbiddenError(method=method, message="blocked"))
    counts = _tick(conn, bot)
    assert counts["dropped"] == 1 and conn.log[-1] == "commit"


def test_tick_active_not_decided_sends_auto_alert():
    r = row("active", now=START + timedelta(hours=1), open_=False)
    conn = db(watch_rows=[r], decided=False)
    bot = FakeBot()
    _tick(conn, bot)
    alert = texts.PAUSE_AUTO_ALERT.format(who="#004408", first="20.11", last="22.11")
    assert any(m["chat_id"] == GROUP and m["text"] == alert for m in bot.sent)
    assert KEY_EXISTS in conn.sqls()


def test_tick_active_decided_no_auto_alert():
    r = row("active", now=START + timedelta(hours=1), open_=False)
    conn = db(watch_rows=[r], decided=True)
    bot = FakeBot()
    _tick(conn, bot)
    alert = texts.PAUSE_AUTO_ALERT.format(who="#004408", first="20.11", last="22.11")
    assert all(m["text"] != alert for m in bot.sent)


# --- тексты ---

def test_all_pause_texts_are_stubs():
    names = [n for n in dir(texts) if n.startswith("PAUSE_")]
    assert len(names) == 17
    for name in names:
        assert getattr(texts, name).startswith("[заглушка]"), name
