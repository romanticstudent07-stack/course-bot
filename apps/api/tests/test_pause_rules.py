"""pause_rules (api-pause-1a, раздел 8): чистые функции, без БД."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app import pause_rules
from app.pause_rules import anniversary, pause_days, refund_days, roll_cycle, start_refusal

MSK_NAME = "Europe/Moscow"
MSK = ZoneInfo(MSK_NAME)
BERLIN_NAME = "Europe/Berlin"
BERLIN = ZoneInfo(BERLIN_NAME)


def _u(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc)


# ------------------------------ anniversary ------------------------------


def test_anniversary_plain():
    start = datetime(2026, 11, 20, 0, 0, tzinfo=MSK)
    assert _u(anniversary(start, MSK_NAME)) == _u(datetime(2027, 11, 20, 0, 0, tzinfo=MSK))


def test_anniversary_feb29():
    start = datetime(2028, 2, 29, 0, 0, tzinfo=MSK)
    assert _u(anniversary(start, MSK_NAME)) == _u(datetime(2029, 2, 28, 0, 0, tzinfo=MSK))


def test_anniversary_dst_zone():
    # Старт зимой (UTC+1), годовщина — та же местная 00:00, а не +365×24 ч.
    start = datetime(2026, 3, 1, 0, 0, tzinfo=BERLIN)
    got = anniversary(start, BERLIN_NAME)
    assert _u(got) == _u(datetime(2027, 3, 1, 0, 0, tzinfo=BERLIN))
    start_summer = datetime(2026, 7, 1, 0, 0, tzinfo=BERLIN)
    got_summer = anniversary(start_summer, BERLIN_NAME)
    assert _u(got_summer) == datetime(2027, 6, 30, 22, 0, tzinfo=timezone.utc)


def test_anniversary_naive():
    with pytest.raises(ValueError):
        anniversary(datetime(2026, 11, 20), MSK_NAME)


# ------------------------------ roll_cycle ------------------------------

START = datetime(2026, 11, 20, 0, 0, tzinfo=MSK)
ANNIV = datetime(2027, 11, 20, 0, 0, tzinfo=MSK)


def test_roll_cycle_before_anniversary():
    at = ANNIV - timedelta(seconds=1)
    start, left = roll_cycle(START, 3, at, MSK_NAME)
    assert _u(start) == _u(START) and left == 3


def test_roll_cycle_exact_midnight():
    start, left = roll_cycle(START, 3, ANNIV, MSK_NAME)
    assert _u(start) == _u(ANNIV) and left == pause_rules.BUDGET_DAYS


def test_roll_cycle_two_years():
    at = datetime(2028, 12, 1, 12, 0, tzinfo=MSK)
    start, left = roll_cycle(START, 0, at, MSK_NAME)
    assert _u(start) == _u(datetime(2028, 11, 20, 0, 0, tzinfo=MSK)) and left == 14


# ------------------------------ pause_days ------------------------------


@pytest.mark.parametrize("n", [1, 7])
def test_pause_days_ok(n):
    s = datetime(2026, 11, 21, 0, 0, tzinfo=MSK)
    assert pause_days(s, s + timedelta(days=n), MSK_NAME) == n


@pytest.mark.parametrize("n", [0, 8])
def test_pause_days_out_of_range(n):
    s = datetime(2026, 11, 21, 0, 0, tzinfo=MSK)
    with pytest.raises(ValueError):
        pause_days(s, s + timedelta(days=n), MSK_NAME)


def test_pause_days_not_midnight():
    s = datetime(2026, 11, 21, 0, 0, tzinfo=MSK)
    with pytest.raises(ValueError):
        pause_days(s + timedelta(hours=1), s + timedelta(days=3), MSK_NAME)
    with pytest.raises(ValueError):
        pause_days(s, s + timedelta(days=3, minutes=1), MSK_NAME)


def test_pause_days_naive():
    with pytest.raises(ValueError):
        pause_days(datetime(2026, 11, 21), datetime(2026, 11, 22), MSK_NAME)


def test_pause_days_dst_spring():
    # Берлин: 28.03.2027 переход на летнее; 7 местных суток = 167 ч.
    s = datetime(2027, 3, 25, 0, 0, tzinfo=BERLIN)
    e = datetime(2027, 4, 1, 0, 0, tzinfo=BERLIN)
    assert _u(e) - _u(s) == timedelta(hours=167)
    assert pause_days(s, e, BERLIN_NAME) == 7


# ------------------------------ refund_days ------------------------------


def test_refund_first_day():
    # Пауза 21..24 (3 дня); нажал 21-го днём → D = 22, возврат 2 (день нажатия потрачен).
    planned_end = datetime(2026, 11, 24, 0, 0, tzinfo=MSK)
    d = datetime(2026, 11, 22, 0, 0, tzinfo=MSK)
    assert refund_days(planned_end, d, MSK_NAME) == 2


def test_refund_last_day():
    planned_end = datetime(2026, 11, 24, 0, 0, tzinfo=MSK)
    assert refund_days(planned_end, planned_end, MSK_NAME) == 0
    assert refund_days(planned_end, planned_end + timedelta(days=1), MSK_NAME) == 0


# ------------------------------ start_refusal ------------------------------

S_AT = datetime(2026, 11, 21, 0, 0, tzinfo=MSK)


def _ok(**overrides):
    args = dict(
        status="approved",
        flags=[],
        phase="active",
        day_no=3,
        days=3,
        days_left=14,
        stage_taken=False,
        last_ended_at=None,
        start_at=S_AT,
    )
    args.update(overrides)
    return start_refusal(**args)


def test_start_refusal_none():
    assert _ok() is None
    assert _ok(phase="onboarding") is None
    assert _ok(last_ended_at=S_AT - timedelta(hours=24)) is None
    assert _ok(days=14, days_left=14) is None


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"status": "requested"}, "not_approved"),
        ({"flags": ["block_lives"]}, "block_lives"),
        ({"phase": "sleeping"}, "state"),
        ({"phase": "muted"}, "state"),
        ({"day_no": None}, "state"),
        ({"flags": ["pause_user"]}, "state"),
        ({"last_ended_at": S_AT - timedelta(hours=23, minutes=59)}, "gap_24h"),
        ({"stage_taken": True}, "stage_taken"),
        ({"days": 5, "days_left": 4}, "no_budget"),
    ],
)
def test_start_refusal_each(overrides, reason):
    assert _ok(**overrides) == reason


def test_start_refusal_order():
    everything = dict(
        status="requested",
        flags=["block_lives", "pause_user"],
        phase="sleeping",
        day_no=None,
        last_ended_at=S_AT - timedelta(hours=1),
        stage_taken=True,
        days=7,
        days_left=0,
    )
    expected = list(pause_rules.REFUSAL_REASONS)
    got = []
    for drop in [
        {"status": "approved"},
        {"flags": ["pause_user"]},
        {"flags": [], "phase": "active", "day_no": 1},
        {"last_ended_at": None},
        {"stage_taken": False},
        {"days_left": 14},
    ]:
        got.append(_ok(**everything))
        everything.update(drop)
    assert got == expected
    assert _ok(**everything) is None
