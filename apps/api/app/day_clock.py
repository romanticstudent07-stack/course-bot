"""Часы дня (life-ops-a): границы дня, дедлайн, пауза закрытия, очередь, исход закрытия дня.

Все константы времени дня — только здесь. Чистые функции: без БД и логов, кроме WARNING
о плохом поясе (имя пояса, без pid). Пишут события по этим часам задачи life-ops-b и
life-ops-c; после life-ops-a этими функциями никто не пользуется.

Решения Автора (docs/tasks/life-ops-a.md, раздел 3; выдержки DM — раздел 4):
  - кнопки под заданиями дня активны с 04:00 по поясу участника (DM 3.1);
  - отчёт сдаётся до 00:00 следующих суток после активации; время сдачи — по серверу,
    «≤ дедлайна — принят» (DM 3.9);
  - CLOSE_GRACE — пауза 120 с после дедлайна перед закрытием дня;
  - очередь показа заданий следующего дня — от 10 до 60 мин после сдачи, детерминирована
    по (pid, day_started_at), хранить не надо (ЛО-1, DM 3.19); на счёт дня не влияет;
  - после простоя — одна граница (В32): last_midnight;
  - исход закрытия (В27 = А, DM 3.4 / 3.6): «пришёл» → счётчик 0, жизнь цела; полное молчание →
    missed_streak + 1; на 2 → −1 жизнь и счётчик 0; 0 жизней → sleeping (Р477).

Все datetime — aware; naive → ValueError (как day_keys.dsa). Результаты — в поясе участника.

Сравнения и сложения — только в UTC (ревью #111, Б1). В Python два aware-datetime с одним и тем
же объектом tzinfo сравниваются и складываются по «настенному» времени (без смещения и fold),
а ZoneInfo(name) кэшируется — поэтому now, started_at и кандидаты границ перед каждым
сравнением и сложением переводятся в UTC. Пояс участника нужен только для даты и для
04:00 / 00:00 на этой дате. Вызывающим (life-ops-b, life-ops-c): результаты сравнивать
с другими моментами тоже только после astimezone(timezone.utc) — или через эти функции.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.day_keys import dsa

logger = logging.getLogger("app.day_clock")

ACTIVATION_TIME = time(4, 0)  # кнопки дня активны с 04:00 по поясу
DEADLINE_TIME = time(0, 0)  # дедлайн — 00:00 следующих суток после активации
CLOSE_GRACE = timedelta(seconds=120)
QUEUE_MIN_MINUTES = 10
QUEUE_MAX_MINUTES = 60
DEFAULT_TZ = "Europe/Moscow"
MAX_LIVES = 3

WINDOW_NOT_ACTIVE = "not_active"
WINDOW_OPEN = "open"
WINDOW_CLOSED = "closed"

OUTCOME_CAME = "came"
OUTCOME_SILENT = "silent"
# Столько дней полного молчания подряд = −1 жизнь (DM 3.6).
SILENT_DAYS_PER_LIFE = 2


@dataclass(frozen=True)
class CloseOutcome:
    outcome: str  # "came" | "silent"
    missed_streak: int
    life_delta: int  # 0 или −1
    sleeping: bool


def _require_aware(ts: datetime, name: str) -> None:
    if ts.tzinfo is None or ts.tzinfo.utcoffset(ts) is None:
        raise ValueError(f"day_clock: {name} — нужен datetime с часовым поясом (naive запрещён)")


def utcnow() -> datetime:
    """Единственный источник «сейчас» для life-ops-b и life-ops-c (тесты подменяют)."""
    return datetime.now(timezone.utc)


def zone(tz_name: str | None) -> ZoneInfo:
    """ZoneInfo пояса; пустой или неизвестный → DEFAULT_TZ + WARNING (только имя пояса)."""
    if tz_name:
        try:
            return ZoneInfo(tz_name)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            pass
    # Строка пояса приходит от клиента — в лог не больше 64 символов (ревью #111, Н9).
    shown = tz_name[:64] if isinstance(tz_name, str) else tz_name
    logger.warning("day_clock: bad timezone %r, using %s", shown, DEFAULT_TZ)
    return ZoneInfo(DEFAULT_TZ)


def _utc(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc)


def _at_local(day: date, at: time, tz: ZoneInfo) -> datetime:
    """Момент «day at» по поясу tz — в UTC.

    datetime.combine с fold=0 (ревью #111, Н1):
      - нет такого часа (перевод часов вперёд, напр. America/Santiago 2026-09-06 и
        America/Havana 2026-03-08 — 00:00 нет) → момент перехода часов (Santiago:
        00:00−04:00 = 04:00Z = 01:00−03:00); сдвига на сутки нет, день короче на час;
      - час повторяется (перевод назад, напр. America/Havana 2026-11-01 — 00:00 дважды) →
        первое вхождение (00:00−04:00 = 04:00Z).
    """
    return _utc(datetime.combine(day, at, tzinfo=tz))


def _active_from_utc(started_at: datetime, z: ZoneInfo) -> tuple[datetime, date]:
    """(первая 04:00 по поясу ≥ started_at — в UTC, местная дата этой 04:00)."""
    _require_aware(started_at, "started_at")
    started_u = _utc(started_at)
    day = started_u.astimezone(z).date()
    candidate = _at_local(day, ACTIVATION_TIME, z)
    if candidate < started_u:
        day = day + timedelta(days=1)
        candidate = _at_local(day, ACTIVATION_TIME, z)
    return candidate, day


def _deadline_at_utc(started_at: datetime, z: ZoneInfo) -> datetime:
    _, day = _active_from_utc(started_at, z)
    return _at_local(day + timedelta(days=1), DEADLINE_TIME, z)


def active_from(started_at: datetime, tz: str | None) -> datetime:
    """Первая 04:00 по поясу, которая ≥ started_at."""
    z = zone(tz)
    return _active_from_utc(started_at, z)[0].astimezone(z)


def deadline_at(started_at: datetime, tz: str | None) -> datetime:
    """00:00 по поясу на дату (active_from.date + 1 день)."""
    z = zone(tz)
    return _deadline_at_utc(started_at, z).astimezone(z)


def window(started_at: datetime, tz: str | None, now: datetime) -> str:
    """not_active (now < active_from) | open (active_from ≤ now ≤ deadline) | closed."""
    _require_aware(now, "now")
    z = zone(tz)
    now_u = _utc(now)
    if now_u < _active_from_utc(started_at, z)[0]:
        return WINDOW_NOT_ACTIVE
    if now_u <= _deadline_at_utc(started_at, z):
        return WINDOW_OPEN
    return WINDOW_CLOSED


def is_overdue(started_at: datetime, tz: str | None, now: datetime) -> bool:
    """now > deadline_at + CLOSE_GRACE."""
    _require_aware(now, "now")
    return _utc(now) > _deadline_at_utc(started_at, zone(tz)) + CLOSE_GRACE


def last_midnight(now: datetime, tz: str | None) -> datetime:
    """Последняя 00:00 по поясу, которая ≤ now (после простоя — одна граница, В32)."""
    _require_aware(now, "now")
    z = zone(tz)
    now_u = _utc(now)
    day = now_u.astimezone(z).date()
    candidate = _at_local(day, DEADLINE_TIME, z)
    if candidate > now_u:
        candidate = _at_local(day - timedelta(days=1), DEADLINE_TIME, z)
    return candidate.astimezone(z)


def queue_delay(pid: uuid.UUID | str, started_at: datetime) -> timedelta:
    """Пауза очереди 10–60 мин, детерминирована по (pid, dsa(started_at)) (ЛО-1).

    pid нормализуется через uuid.UUID (регистр строки не влияет, ревью #111, Н8);
    не UUID → ValueError.
    """
    pid_str = str(uuid.UUID(str(pid)))
    digest = hashlib.sha256(f"{pid_str}:{dsa(started_at)}".encode()).hexdigest()
    span = QUEUE_MAX_MINUTES - QUEUE_MIN_MINUTES + 1
    return timedelta(minutes=QUEUE_MIN_MINUTES + int(digest, 16) % span)


def queue_until(pid: uuid.UUID | str, started_at: datetime) -> datetime:
    """started_at + queue_delay — сложение в UTC (перевод часов не меняет паузу), результат —
    в поясе started_at."""
    delay = queue_delay(pid, started_at)
    return (_utc(started_at) + delay).astimezone(started_at.tzinfo)


def close_outcome(came: bool, missed_streak: int, lives: int) -> CloseOutcome:
    """Исход закрытия дня (В27 = А).

    lives вне [0, 3] → ValueError; lives = 0 → ValueError (спящему день не закрывают,
    ревью #111, Н6); missed_streak < 0, bool или не int → ValueError.
    """
    if isinstance(lives, bool) or not isinstance(lives, int) or not 0 <= lives <= MAX_LIVES:
        raise ValueError("close_outcome: lives вне [0, 3]")
    if lives == 0:
        raise ValueError("close_outcome: lives = 0 (участник уже sleeping)")
    if isinstance(missed_streak, bool) or not isinstance(missed_streak, int) or missed_streak < 0:
        raise ValueError("close_outcome: missed_streak — int ≥ 0")
    if came:
        return CloseOutcome(OUTCOME_CAME, 0, 0, False)
    streak = missed_streak + 1
    life_delta = 0
    if streak >= SILENT_DAYS_PER_LIFE:
        life_delta = -1
        streak = 0
    return CloseOutcome(OUTCOME_SILENT, streak, life_delta, lives + life_delta == 0)
