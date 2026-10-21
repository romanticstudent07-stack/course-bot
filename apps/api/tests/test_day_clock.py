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


# Н7 (ревью #111): обе границы диапазона достижимы — pid подобраны перебором и захардкожены.
# Формула с «% 50» (10..59) этот тест не пройдёт.
def test_queue_delay_both_bounds_reachable():
    started = msk(2026, 10, 21, 4, 0)
    assert queue_delay(uuid.UUID(int=46), started) == timedelta(minutes=10)
    assert queue_delay(uuid.UUID(int=34), started) == timedelta(minutes=60)


# Н8: регистр строки pid не влияет; не UUID → ValueError.
def test_queue_delay_pid_normalized():
    started = msk(2026, 10, 21, 4, 0)
    pid = uuid.UUID("abcdefab-cdef-4abc-8def-abcdefabcdef")
    assert queue_delay(str(pid).upper(), started) == queue_delay(pid, started)
    with pytest.raises(ValueError):
        queue_delay("not-a-uuid", started)


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


def test_bad_zone_warning_truncated(caplog):
    bad = "X" * 500
    with caplog.at_level(logging.WARNING, logger="app.day_clock"):
        zone(bad)
    messages = [r.getMessage() for r in caplog.records if r.name == "app.day_clock"]
    assert messages
    assert all("X" * 65 not in m for m in messages)
    assert any("X" * 64 in m for m in messages)


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


@pytest.mark.parametrize("lives", [-1, 4, 0, True])
def test_close_outcome_lives_out_of_range(lives):
    with pytest.raises(ValueError):
        close_outcome(False, 0, lives)


# Н6: missed_streak < 0, bool или не int → ValueError.
@pytest.mark.parametrize("streak", [-1, -5, True, False, 1.0, "1"])
def test_close_outcome_bad_streak(streak):
    with pytest.raises(ValueError):
        close_outcome(False, streak, 3)


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


# --- Б1 (ревью #111): сравнения и сложения — в UTC, даже если вход в поясе участника ---
HAVANA = "America/Havana"
SANTIAGO = "America/Santiago"
UTC = timezone.utc


def test_b1_havana_overdue_with_local_now():
    # 2026-11-01 час 00:00–00:59 повторяется; дедлайн — первое 00:00 (−04:00) = 04:00Z.
    started = datetime(2026, 10, 31, 0, 0, tzinfo=UTC)  # 30.10 20:00 Гавана → активация 31.10
    assert deadline_at(started, HAVANA).astimezone(UTC) == datetime(2026, 11, 1, 4, 0, tzinfo=UTC)
    now_utc = datetime(2026, 11, 1, 5, 1, tzinfo=UTC)  # +61 мин после дедлайна
    now_local = now_utc.astimezone(zone(HAVANA))
    assert is_overdue(started, HAVANA, now_utc) is True
    assert is_overdue(started, HAVANA, now_local) is True
    assert is_overdue(started.astimezone(zone(HAVANA)), HAVANA, now_local) is True
    assert window(started, HAVANA, now_local) == "closed"


def test_b1_santiago_deadline_moment_open_utc_and_local():
    # 2026-09-06: 00:00 нет; дедлайн = момент перехода 04:00Z.
    started = datetime(2026, 9, 5, 0, 0, tzinfo=UTC)  # 04.09 20:00 Сантьяго → активация 05.09
    deadline_utc = datetime(2026, 9, 6, 4, 0, tzinfo=UTC)
    assert deadline_at(started, SANTIAGO).astimezone(UTC) == deadline_utc
    local = deadline_utc.astimezone(zone(SANTIAGO))
    assert window(started, SANTIAGO, deadline_utc) == "open"
    assert window(started, SANTIAGO, local) == "open"
    assert window(started.astimezone(zone(SANTIAGO)), SANTIAGO, local) == "open"
    one_sec = timedelta(seconds=1)
    assert window(started, SANTIAGO, (deadline_utc + one_sec).astimezone(zone(SANTIAGO))) == "closed"


@pytest.mark.parametrize(
    ("tz", "started_utc"),
    [
        # Santiago 2026-04-04 23:50 −03:00 → в 00:00 часы назад на 23:00 (−04:00).
        (SANTIAGO, datetime(2026, 4, 5, 2, 50, tzinfo=UTC)),
        # Santiago 2026-09-05 23:50 −04:00 → в 00:00 часы вперёд на 01:00 (−03:00).
        (SANTIAGO, datetime(2026, 9, 6, 3, 50, tzinfo=UTC)),
        # Moscow без перевода — контроль.
        (TZ, datetime(2026, 10, 21, 1, 0, tzinfo=UTC)),
    ],
)
def test_b1_queue_until_across_dst_utc_difference(tz, started_utc):
    started_local = started_utc.astimezone(zone(tz))
    delay = queue_delay(PID_A, started_local)
    until = queue_until(PID_A, started_local)
    assert until.astimezone(UTC) - started_utc == delay
    assert until.tzinfo is started_local.tzinfo
    # Сравнение — в UTC: межпоясное == для fold=1 всегда False (PEP 495).
    assert queue_until(PID_A, started_utc).astimezone(UTC) == until.astimezone(UTC)


def test_b1_active_from_local_started_at_same_as_utc():
    started_utc = datetime(2026, 11, 1, 4, 30, tzinfo=UTC)  # 00:30 Гавана (первое вхождение)
    local = started_utc.astimezone(zone(HAVANA))
    assert active_from(local, HAVANA).astimezone(UTC) == active_from(started_utc, HAVANA).astimezone(UTC)
    assert deadline_at(local, HAVANA).astimezone(UTC) == deadline_at(started_utc, HAVANA).astimezone(UTC)


# --- Н1 (ревью #111): _at_local на днях без 00:00 и с повтором 00:00 ---
def test_n1_santiago_no_midnight_is_transition_moment():
    # 2026-09-06 00:00 нет → момент перехода: 04:00Z = 01:00 −03:00.
    now = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
    boundary = last_midnight(now, SANTIAGO)
    assert boundary.astimezone(UTC) == datetime(2026, 9, 6, 4, 0, tzinfo=UTC)
    assert boundary.utcoffset() == timedelta(hours=-3)
    # Одна граница, без сдвига на сутки; по часам день 04:00 → 01:00 (21 ч), реально — 20 ч.
    started = datetime(2026, 9, 5, 0, 0, tzinfo=UTC)
    span = deadline_at(started, SANTIAGO).astimezone(UTC) - active_from(started, SANTIAGO).astimezone(UTC)
    assert span == timedelta(hours=20)


def test_n1_havana_no_midnight_2026_03_08():
    # 2026-03-08 00:00 нет (часы с 00:00 −05:00 на 01:00 −04:00) → момент перехода 05:00Z.
    now = datetime(2026, 3, 8, 12, 0, tzinfo=UTC)
    boundary = last_midnight(now, HAVANA)
    assert boundary.astimezone(UTC) == datetime(2026, 3, 8, 5, 0, tzinfo=UTC)
    # Перед переходом — ещё прошлая полночь.
    before = datetime(2026, 3, 8, 4, 59, 59, tzinfo=UTC)
    assert last_midnight(before, HAVANA).astimezone(UTC) == datetime(2026, 3, 7, 5, 0, tzinfo=UTC)


def test_n1_havana_repeated_midnight_first_occurrence():
    # 2026-11-01 00:00 дважды (04:00Z и 05:00Z) → берётся первое вхождение, 04:00Z.
    first = datetime(2026, 11, 1, 4, 0, tzinfo=UTC)
    assert last_midnight(first, HAVANA).astimezone(UTC) == first
    # Во втором вхождении 00:30 граница та же — одна, не две.
    second_pass = datetime(2026, 11, 1, 5, 30, tzinfo=UTC)
    assert last_midnight(second_pass, HAVANA).astimezone(UTC) == first
    assert last_midnight(second_pass.astimezone(zone(HAVANA)), HAVANA).astimezone(UTC) == first
