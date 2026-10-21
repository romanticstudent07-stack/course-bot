"""Гонка «часов» с отчётом (life-ops-c, §9, У6). С БД — только CI.

Время — monkeypatch day_clock.utcnow (как в test_day_report_submit.py); tick получает now
аргументом. Отчёт — через обработчик POST /day/report/submit.
  1) submit в 23:59:59 (окно open) → tick в 00:02:01 до run_once → пропуск (проектор не догнал);
     после run_once → день сдвинут отчётом, tick → ничего, жизнь не списана;
  2) tick в 00:02:01 закрыл день → submit со старым днём → 409, не 200.
"""
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import day_clock
from app.day_content import get_day_content
from app.life_ops import TickResult, tick
from app.projector import run_once
from app.routers.day import DayReportIn, enter_day_by_test_flag, post_day_report_submit
from app.routers.onboarding import register_with_consents
from app.telegram_init_data import InitDataContext, TelegramUser

_CLOCK: dict[str, datetime] = {}


@pytest.fixture(autouse=True)
def _clock(monkeypatch):
    _CLOCK["now"] = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(day_clock, "utcnow", lambda: _CLOCK["now"])
    return _CLOCK


def _u(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc)


def _open_day(engine, tg_user_id: int):
    with Session(engine) as session:
        pid = register_with_consents(session, tg_user_id, ["C0", "C1"]).participant.pid
    run_once(engine)
    with Session(engine) as session:
        enter_day_by_test_flag(session, tg_user_id, True)
    run_once(engine)
    with engine.begin() as conn:
        # Второе молчание подряд списало бы жизнь — так видно, что списания нет.
        conn.execute(
            text("UPDATE participant_state SET missed_streak = 1 WHERE pid = :p"), {"p": pid}
        )
    return pid, _state(engine, pid)


def _state(engine, pid):
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT day_no, day_started_at, missed_streak, lives, tz "
                "FROM participant_state WHERE pid = :p"
            ),
            {"p": pid},
        ).one()


def _deadline(state) -> datetime:
    return _u(day_clock.deadline_at(state.day_started_at, state.tz))


def _ctx(tg_user_id: int) -> InitDataContext:
    return InitDataContext(user=TelegramUser(id=tg_user_id), auth_date=int(time.time()))


def _body() -> DayReportIn:
    blocks = get_day_content().get(1, 1, 1).blocks
    return DayReportIn.model_validate(
        {"marks": [{"block_id": b.block_id, "value": "done"} for b in blocks]}
    )


def _submit(engine, tg_user_id: int):
    with Session(engine) as session:
        return post_day_report_submit(
            _body(), uuid.uuid4(), _ctx(tg_user_id), session, get_day_content()
        )


def _life_events(engine, pid) -> list[str]:
    with engine.connect() as conn:
        return list(
            conn.execute(
                text(
                    "SELECT kind FROM participant_events WHERE pid = :p "
                    "AND kind IN ('life_op', 'day_closed') ORDER BY id"
                ),
                {"p": pid},
            ).scalars()
        )


def test_submit_235959_then_tick_000201(db_engine):
    tg = 9751
    pid, state = _open_day(db_engine, tg)
    deadline = _deadline(state)
    _CLOCK["now"] = deadline - timedelta(seconds=1)  # 23:59:59
    _submit(db_engine, tg)  # 200: окно open
    tick_at = deadline + timedelta(seconds=121)  # 00:02:01
    # До run_once: отчёт ещё не применён — проектор не догнал pid, пропуск.
    assert tick(db_engine, tick_at) == TickResult(closed=0, skipped=1)
    assert _life_events(db_engine, pid) == []
    run_once(db_engine)
    after = _state(db_engine, pid)
    assert _u(after.day_started_at) > _u(state.day_started_at)  # день сдвинут отчётом
    assert tick(db_engine, tick_at) == TickResult(0, 0)
    assert _life_events(db_engine, pid) == []
    run_once(db_engine)
    final = _state(db_engine, pid)
    assert (final.lives, final.missed_streak) == (3, 0)


def test_tick_closed_then_submit_old_day_409(db_engine):
    tg = 9752
    pid, state = _open_day(db_engine, tg)
    deadline = _deadline(state)
    tick_at = deadline + timedelta(seconds=121)  # 00:02:01
    assert tick(db_engine, tick_at) == TickResult(1, 0)
    assert _life_events(db_engine, pid) == ["life_op", "day_closed"]
    # Отчёт со старым днём: проектор ещё не применил day_closed — окно старого дня закрыто.
    _CLOCK["now"] = tick_at + timedelta(seconds=1)
    with pytest.raises(HTTPException) as exc:
        _submit(db_engine, tg)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "DAY_CLOSED"
    run_once(db_engine)
    final = _state(db_engine, pid)
    assert final.lives == 2 and final.missed_streak == 0
    assert final.day_no == 1  # позицию «часы» не меняют
