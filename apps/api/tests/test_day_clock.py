"""life-ops-a: app/day_clock.py — быстрые тесты без БД (docs/tasks/life-ops-a.md, раздел 9)."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app import day_clock
from app.day_clock import (
    CLOSE_GRACE,
    DEFAULT_TZ,
    CloseOutcome,
    active_from,
    close_outcome,
    deadline_at,
    is_overdue,
    last_midnight,
    queue_delay,
    queue_until,
    window,
    zone,
)
from app.day_keys import (
    KIND_DAY_CLOSE,
    KIND_DAY_QUEUE,
    TTL_BY_KIND,
    key_day_close,
    key_day_queue,
)

MSK = ZoneInfo("Europe/Moscow")
TZ = "Europe/Moscow"
PID_A = uuid.UUID("11111111-1111-4111-8111-111111111111")
PID_B = uuid.UUID("22222222-2222-4222-8222-222222222222")


def msk(*args) -> datetime:
    return datetime(*args, tzinfo=MSK)


# --- active_from: 04:00 ± 1 с ---
def test_active_from_before_four_same_day():
    assert active_from(msk(2026, 10, 21, 3, 59, 59), TZ) == msk(2026, 10, 21, 4, 0)


def test_active_from_exactly_four_is_itself():
    assert active_from(msk(2026, 10, 21, 4, 0, 0), TZ) == msk(2026, 10, 21, 4, 0)


def test_active_from_after_four_next_day():
    assert active_from(msk(2026, 10, 21, 4, 0, 1), TZ) == msk(2026, 10, 22, 4, 0)


def test_active_from_utc_input_returns_local_zone():
    started = datetime(2026, 10, 21, 0, 59, 59, tzinfo=timezone.utc)  # 03:59:59 МСК
    result = active_from(started, TZ)
    assert result == msk(2026, 10, 21, 4, 0)
    assert result.tzinfo == MSK


def test_active_from_other_zone():
    tz = "Asia/Yekaterinburg"  # UTC+5
    started = datetime(2026, 10, 21, 0, 0, tzinfo=timezone.utc)  # 05:00 по Екатеринбургу
    expected = datetime(2026, 10, 22, 4, 0, tzinfo=ZoneInfo(tz))
    assert active_from(started, tz) == expected


# --- deadline_at ---
def test_deadline_is_midnight_after_activation():
    assert deadline_at(msk(2026, 10, 21, 3, 0), TZ) == msk(2026, 10, 22, 0, 0)
    assert deadline_at(msk(2026, 10, 21, 12, 0), TZ) == msk(2026, 10, 23, 0, 0)


# --- window ---
STARTED = msk(2026, 10, 20, 18, 0)  # активация 21.10 04:00, дедлайн 22.10 00:00


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (msk(2026, 10, 21, 3, 59, 59), "not_active"),
        (msk(2026, 10, 21, 4, 0, 0), "open"),
        (msk(2026, 10, 21, 23, 59, 59), "open"),
        (msk(2026, 10, 22, 0, 0, 0), "open"),
        (msk(2026, 10, 22, 0, 0, 1), "closed"),
    ],
)
def test_window(now, expected):
    assert window(STARTED, TZ, now) == expected


# --- is_overdue: +120 и +121 с ---
def test_is_overdue_grace():
    deadline = deadline_at(STARTED, TZ)
    assert CLOSE_GRACE == timedelta(seconds=120)
    assert is_overdue(STARTED, TZ, deadline) is False
    assert is_overdue(STARTED, TZ, deadline + timedelta(seconds=120)) is False
    assert is_overdue(STARTED, TZ, deadline + timedelta(seconds=121)) is True


# --- last_midnight ---
def test_last_midnight():
    assert last_midnight(msk(2026, 10, 21, 0, 0, 0), TZ) == msk(2026, 10, 21, 0, 0)
    assert last_midnight(msk(2026, 10, 21, 0, 0, 1), TZ) == msk(2026, 10, 21, 0, 0)
    assert last_midnight(msk(2026, 10, 20, 23, 59, 59), TZ) == msk(2026, 10, 20, 0, 0)


def test_last_midnight_after_downtime_is_one_boundary():
    # Простой трое суток: граница — только последняя полночь (В32).
    now = msk(2026, 10, 24, 15, 30)
    assert last_midnight(now, TZ) == msk(2026, 10, 24, 0, 0)


def test_last_midnight_utc_input():
    now = datetime(2026, 10, 20, 21, 0, 1, tzinfo=timezone.utc)  # 00:00:01 МСК 21.10
    result = last_midnight(now, TZ)
    assert result == msk(2026, 10, 21, 0, 0)
    assert result.tzinfo == MSK


# --- queue_delay ---
def test_queue_delay_range_and_determinism():
    started = msk(2026, 10, 21, 4, 0)
    delays = set()
    for i in range(300):
        pid = uuid.UUID(int=i + 1)
        delay = queue_delay(pid, started)
        assert timedelta(minutes=10) <= delay <= timedelta(minutes=60)
        assert delay.total_seconds() % 60 == 0
        assert queue_delay(pid, started) == delay
        delays.add(delay)
    assert len(delays) > 10  # разброс по всему диапазону


def test_queue_delay_differs_between_pids():
    started = msk(2026, 10, 21, 4, 0)
    assert queue_delay(PID_A, started) != queue_delay(PID_B, started)


def test_queue_delay_same_moment_any_zone():
    started = msk(2026, 10, 21, 4, 0)
    assert queue_delay(PID_A, started) == queue_delay(PID_A, started.astimezone(timezone.utc))
    assert queue_delay(PID_A, started) == queue_delay(str(PID_A), started)


def test_queue_until():
    started = msk(2026, 10, 21, 4, 0)
    assert queue_until(PID_A, started) == started + queue_delay(PID_A, started)


# --- zone: плохой пояс → Moscow + WARNING ---
@pytest.mark.parametrize("bad", ["", None, "Mars/Olympus", "../etc/passwd"])
def test_bad_zone_falls_back_to_moscow(bad, caplog):
    with caplog.at_level(logging.WARNING, logger="app.day_clock"):
        assert zone(bad) == ZoneInfo(DEFAULT_TZ)
    assert any(r.levelno == logging.WARNING for r in caplog.records if r.name == "app.day_clock")


def test_good_zone_no_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="app.day_clock"):
        assert zone("Asia/Vladivostok") == ZoneInfo("Asia/Vladivostok")
    assert not [r for r in caplog.records if r.name == "app.day_clock"]


def test_bad_zone_in_active_from_uses_moscow():
    assert active_from(msk(2026, 10, 21, 3, 0), "Nope/Nope") == msk(2026, 10, 21, 4, 0)


# --- naive → ValueError ---
NAIVE = datetime(2026, 10, 21, 4, 0)


@pytest.mark.parametrize(
    "call",
    [
        lambda: active_from(NAIVE, TZ),
        lambda: deadline_at(NAIVE, TZ),
        lambda: window(NAIVE, TZ, STARTED),
        lambda: window(STARTED, TZ, NAIVE),
        lambda: is_overdue(STARTED, TZ, NAIVE),
        lambda: is_overdue(NAIVE, TZ, STARTED),
        lambda: last_midnight(NAIVE, TZ),
        lambda: queue_delay(PID_A, NAIVE),
        lambda: queue_until(PID_A, NAIVE),
    ],
)
def test_naive_raises(call):
    with pytest.raises(ValueError):
        call()


# --- close_outcome ---
def test_close_outcome_came():
    assert close_outcome(True, 1, 3) == CloseOutcome("came", 0, 0, False)


def test_close_outcome_silent_first_day():
    assert close_outcome(False, 0, 3) == CloseOutcome("silent", 1, 0, False)


def test_close_outcome_silent_second_day_costs_life():
    assert close_outcome(False, 1, 3) == CloseOutcome("silent", 0, -1, False)


def test_close_outcome_last_life_sleeping():
    assert close_outcome(False, 1, 1) == CloseOutcome("silent", 0, -1, True)


def test_close_outcome_silent_no_life_loss_not_sleeping():
    assert close_outcome(False, 0, 1) == CloseOutcome("silent", 1, 0, False)


@pytest.mark.parametrize("lives", [-1, 4])
def test_close_outcome_lives_out_of_range(lives):
    with pytest.raises(ValueError):
        close_outcome(False, 0, lives)


# --- day_keys: day_close / day_queue ---
def test_day_close_and_queue_keys():
    started = msk(2026, 10, 21, 4, 0)
    dsa = "2026-10-21T01:00:00+00:00"
    assert key_day_close(PID_A, started) == f"day_close:{PID_A}:{dsa}"
    assert key_day_queue(PID_A, started) == f"day_queue:{PID_A}:{dsa}"
    assert TTL_BY_KIND[KIND_DAY_CLOSE] == "3650 days"
    assert TTL_BY_KIND[KIND_DAY_QUEUE] == "3650 days"
    with pytest.raises(ValueError):
        key_day_close(PID_A, NAIVE)


def test_utcnow_is_aware_utc():
    now = day_clock.utcnow()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)
