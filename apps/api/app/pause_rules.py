"""Правила пауз участника (api-pause-1a, T2a; Р-6а / Р-20) — чистые функции, без БД и логов.

Карточка: docs/tasks/api-pause-1a.md, разделы 2 и 4.1; контракт T3/T4 — раздел 5.
Пользуются: проектор (pause_started / pause_ended), часы T2b и API T3 (до записи заявки).

  - BUDGET_DAYS — бюджет дней за годовой цикл; MAX_DAYS — длина одной паузы; MIN_GAP — между
    паузами (Р-6а);
  - anniversary / roll_cycle — годовщина цикла лениво, по at события (Р9): местная дата
    cycle_start + 1 год, 00:00 по поясу; 29.02 → 28.02; крона нет;
  - pause_days — длина паузы в местных сутках (Р3): обе границы — 00:00 по поясу, 1..7;
  - refund_days — возврат при досрочном выходе (Р6): местная дата planned_end_at − местная
    дата D, не меньше 0;
  - start_refusal — причина отказа старта или None; порядок причин фиксирован (раздел 4.1;
    причина state — с уточнением ШТАБа 18.11: фаза не onboarding / active, или day_no NULL,
    или у pid уже есть активная пауза — флаг паузы в status_flags).

Все datetime — aware; naive → ValueError (как day_clock). Сравнения — только в UTC
(day_clock, ревью #111, Б1). Нет 00:00 из-за перевода часов → момент перехода, как у
day_clock.next_midnight (datetime.combine с fold=0).
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app import day_clock

BUDGET_DAYS = 14
MAX_DAYS = 7
MIN_GAP = timedelta(hours=24)

STATUS_APPROVED = "approved"
FLAG_BLOCK_LIVES = "block_lives"
# Флаги паузы: любой из них у pid — активная пауза (причина state).
PAUSE_FLAGS = ("pause_user", "author_pause", "pause_shadow")
# Фазы, в которых старт паузы допустим (уточнение ШТАБа 18.11).
START_PHASES = ("onboarding", "active")

REASON_NOT_APPROVED = "not_approved"
REASON_BLOCK_LIVES = "block_lives"
REASON_STATE = "state"
REASON_GAP_24H = "gap_24h"
REASON_STAGE_TAKEN = "stage_taken"
REASON_NO_BUDGET = "no_budget"
# Порядок проверки в start_refusal и список reason у pause_start_failed (раздел 5).
REFUSAL_REASONS = (
    REASON_NOT_APPROVED,
    REASON_BLOCK_LIVES,
    REASON_STATE,
    REASON_GAP_24H,
    REASON_STAGE_TAKEN,
    REASON_NO_BUDGET,
)

_MIDNIGHT = time(0, 0)


def _require_aware(ts: datetime, name: str) -> None:
    if not isinstance(ts, datetime) or ts.tzinfo is None or ts.tzinfo.utcoffset(ts) is None:
        raise ValueError(f"pause_rules: {name} — нужен datetime с часовым поясом (naive запрещён)")


def _utc(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc)


def _local_date(ts: datetime, z: ZoneInfo) -> date:
    return _utc(ts).astimezone(z).date()


def _midnight_utc(day: date, z: ZoneInfo) -> datetime:
    return _utc(datetime.combine(day, _MIDNIGHT, tzinfo=z))


def _is_midnight(ts: datetime, z: ZoneInfo) -> bool:
    return _utc(ts) == _midnight_utc(_local_date(ts, z), z)


def _add_year(day: date) -> date:
    try:
        return day.replace(year=day.year + 1)
    except ValueError:  # 29.02 → 28.02
        return day.replace(year=day.year + 1, day=28)


def anniversary(cycle_start_at: datetime, tz: str | None) -> datetime:
    """Годовщина цикла: местная дата cycle_start_at + 1 год, 00:00 по поясу (29.02 → 28.02)."""
    _require_aware(cycle_start_at, "cycle_start_at")
    z = day_clock.zone(tz)
    return _midnight_utc(_add_year(_local_date(cycle_start_at, z)), z).astimezone(z)


def roll_cycle(
    cycle_start_at: datetime, days_left: int, at: datetime, tz: str | None
) -> tuple[datetime, int]:
    """Ленивая смена цикла (Р9): пока at ≥ годовщины — остаток BUDGET_DAYS, цикл = годовщина."""
    _require_aware(cycle_start_at, "cycle_start_at")
    _require_aware(at, "at")
    at_u = _utc(at)
    start = cycle_start_at
    left = days_left
    while at_u >= _utc(nxt := anniversary(start, tz)):
        start = nxt
        left = BUDGET_DAYS
    return start, left


def pause_days(start_at: datetime, planned_end_at: datetime, tz: str | None) -> int:
    """Длина паузы в местных сутках: обе границы — 00:00 по поясу, разность дат 1..MAX_DAYS.

    Иначе ValueError (CHECK 0018 — 169 ч; точные местные сутки проверяет этот код).
    """
    _require_aware(start_at, "start_at")
    _require_aware(planned_end_at, "planned_end_at")
    z = day_clock.zone(tz)
    if not _is_midnight(start_at, z) or not _is_midnight(planned_end_at, z):
        raise ValueError("pause_rules: границы паузы — 00:00 по поясу")
    days = (_local_date(planned_end_at, z) - _local_date(start_at, z)).days
    if not 1 <= days <= MAX_DAYS:
        raise ValueError("pause_rules: длина паузы вне 1..7 дней")
    return days


def refund_days(planned_end_at: datetime, day_start: datetime, tz: str | None) -> int:
    """Возврат при досрочном выходе (Р6): местная дата planned_end_at − местная дата D, ≥ 0."""
    _require_aware(planned_end_at, "planned_end_at")
    _require_aware(day_start, "day_start")
    z = day_clock.zone(tz)
    return max(0, (_local_date(planned_end_at, z) - _local_date(day_start, z)).days)


def start_refusal(
    *,
    status: str,
    flags: Sequence[str] | None,
    phase: str | None,
    day_no: int | None,
    days: int,
    days_left: int,
    stage_taken: bool,
    last_ended_at: datetime | None,
    start_at: datetime,
) -> str | None:
    """Причина отказа старта паузы или None. Порядок: not_approved → block_lives → state →
    gap_24h → stage_taken → no_budget (раздел 4.1; state — уточнение ШТАБа 18.11)."""
    _require_aware(start_at, "start_at")
    if last_ended_at is not None:
        _require_aware(last_ended_at, "last_ended_at")
    flag_list = list(flags or ())
    if status != STATUS_APPROVED:
        return REASON_NOT_APPROVED
    if FLAG_BLOCK_LIVES in flag_list:
        return REASON_BLOCK_LIVES
    if (
        phase not in START_PHASES
        or day_no is None
        or any(flag in PAUSE_FLAGS for flag in flag_list)
    ):
        return REASON_STATE
    if last_ended_at is not None and _utc(start_at) - _utc(last_ended_at) < MIN_GAP:
        return REASON_GAP_24H
    if stage_taken:
        return REASON_STAGE_TAKEN
    if days_left < days:
        return REASON_NO_BUDGET
    return None
