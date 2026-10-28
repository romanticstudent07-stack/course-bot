"""«Часы» НП3 (pushi-notify-1): «Задания откроются сегодня/завтра в 04:00 по Вашему времени».

Запуск: шаг tick вызывает app/projector.py из run_forever раз в NOTIFY_OPS_INTERVAL_S,
сразу после шага life_ops (once — без tick). Образец — app/life_ops.py.

Источник — docs/tasks/pushi-notify-1.md (§3, §7). Решения Автора: НП3 А (после очереди и после
онбординга), В1 А (после онбординга тоже пишут «часы»), В2 Б (два текста по местному времени
записи), В4 А (опоздавший НП3 — задания уже открыты — не отправляется, ключ пишется).
Модуль пишет ТОЛЬКО ключ idempotency_keys (kind tasks_open) и строку outbox; состояние участника
и события участника не пишет (E1 / INV-1).

Триггер для дня D = текущий participant_state.day_started_at:
  - после очереди: есть ключ day_queue:{pid}:{dsa(D)} (submit) и now ≥ day_clock.queue_until(pid, D);
    пока очередь не кончилась — ждём;
  - после онбординга: ключа очереди нет, но есть событие day_entered с at = D (любой источник).
Ключ tasks_open:{pid}:{dsa(D)} — один на день: есть → участник не кандидат.

tick_tasks_open(engine, now) → NotifyResult(sent, late, skipped):
  1. Кандидаты — своя транзакция, только чтение: фильтр life_ops (_CANDIDATES, BLOCKING_FLAGS);
     ключи и события day_entered — двумя запросами на всех; decide; не больше MAX_PER_TICK.
  2. Каждый pid — своя транзакция под lock_participant (lock_timeout LOCK_TIMEOUT): состояние
     заново, life_ops._eligible, «проектор догнал pid», ключи и day_entered заново, decide заново.
  3. Ключ (ON CONFLICT DO NOTHING RETURNING; 0 строк → rollback); "send" → строка outbox
     (aggregate_id = pid строкой, event_type tasks_open_notice, payload {text_id, payload_vars,
     tier}, tx_id = pg_current_xact_id()) — без RETURNING: у app_projector нет SELECT на outbox.
     "late" → только ключ. Один commit на pid.
  Ошибка на pid → rollback, WARNING с именем класса, другие pid идут дальше.
  Ошибка чтения кандидатов — наружу (ловит projector).

Полуденное НП1 (noon-1, docs/tasks/noon-1.md): НП1 А — в 12:00 по ТЗ участника; В3 А — пропущенное
из-за простоя догоняется до 18:00 по ТЗ, с 18:00 не отправляется, ключ пишется только при
отправке; В5 А — одно полуденное в местные сутки (ключ noon:{pid}:{местная дата}); В6 А —
активность = только строки day_marks текущего day_started_at.
tick_noon(engine, now) → NotifyResult(sent, 0, skipped): кандидаты — фильтр life_ops (свой SELECT
с тем же WHERE: нужны module_no и day_no), окно 12:00–18:00, ключи noon и day_done, отметки
day_marks; под замком — всё заново; ключ noon + outbox noon_nudge (T3) — один commit.
Гейт: день открыт (day_clock.window = open), нет отметок, не сдан, не 13-P (канон 03 §3.13).

tick(engine, now) → NotifyTick(tasks_open, noon): единственный вход для projector; правила идут
по очереди, каждое в своём try/except: сбой правила → WARNING с именем класса и NotifyResult(0,0,0),
следующее правило идёт.

Время: now — только аргумент (в run_forever — day_clock.utcnow()); сравнения — в UTC или
функциями day_clock. Лог: без pid, tz, payload и ПДн; итог тика — одной строкой INFO.
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from collections.abc import Callable
from datetime import date, datetime, time, timezone
from typing import Any

from sqlalchemy import Connection, Engine, text

from app import day_clock, life_ops
from app.day_keys import (
    KIND_NOON,
    KIND_TASKS_OPEN,
    TTL_NOON,
    TTL_TASKS_OPEN,
    key_day_done,
    key_day_queue,
    key_noon,
    key_tasks_open,
)
from app.participant_lock import lock_participant

logger = logging.getLogger("app.notify_ops")

NOTIFY_OPS_INTERVAL_S = life_ops.LIFE_OPS_INTERVAL_S
MAX_PER_TICK = 200
LOCK_TIMEOUT = "5s"
EVENT_TYPE = "tasks_open_notice"
TIER = "T2"
TEXT_TODAY = "B9.day_tasks_open_today"
TEXT_TOMORROW = "B9.day_tasks_open_tomorrow"
# Совпадает с app/projector.py (EVENT_KIND_DAY_ENTERED); сверяет tests/test_notify_ops.py.
# Импорта проектора нет: проектор импортирует этот модуль.
EVENT_KIND_DAY_ENTERED = "day_entered"

DECISION_SEND = "send"
DECISION_LATE = "late"

# НП1 (noon-1): время пушей, а не границы дня — поэтому здесь, а не в day_clock (Т2).
NOON_FROM = time(12, 0)
NOON_UNTIL = time(18, 0)
NOON_EVENT_TYPE = "noon_nudge"
NOON_TIER = "T3"
TEXT_NOON = "B9.day_noon_nudge"

# Тот же WHERE, что life_ops._CANDIDATES; плюс module_no и day_no (life_ops не меняется).
_NOON_CANDIDATES = text(
    """
    SELECT pid, tz, day_started_at, module_no, day_no
    FROM participant_state
    WHERE lifecycle_phase IN ('onboarding', 'active')
      AND author_pause_reason IS NULL
      AND day_no IS NOT NULL
      AND day_started_at IS NOT NULL
      AND NOT (status_flags && CAST(:flags AS text[]))
    ORDER BY day_started_at, pid
    """
)

# Колонки life_ops._STATE (для life_ops._eligible) плюс module_no.
_NOON_STATE = text(
    """
    SELECT lifecycle_phase, author_pause_reason, day_no, day_started_at, lives,
           missed_streak, tz, status_flags, module_no
    FROM participant_state
    WHERE pid = :pid
    """
)

_MARKS_ALL = text(
    """
    SELECT pid, day_started_at
    FROM day_marks
    WHERE pid = ANY(CAST(:pids AS uuid[]))
    GROUP BY pid, day_started_at
    """
)

_HAS_MARKS = text(
    "SELECT 1 FROM day_marks WHERE pid = :pid AND day_started_at = :started LIMIT 1"
)

_EXISTING_KEYS = text(
    "SELECT key FROM idempotency_keys WHERE key = ANY(CAST(:keys AS text[]))"
)

_ENTERED_ALL = text(
    """
    SELECT pid, at
    FROM participant_events
    WHERE kind = :kind AND pid = ANY(CAST(:pids AS uuid[]))
    """
)

_HAS_KEY = text("SELECT 1 FROM idempotency_keys WHERE key = :key LIMIT 1")

_ENTERED_ONE = text(
    "SELECT at FROM participant_events WHERE kind = :kind AND pid = :pid"
)

_LOCK_TIMEOUT = text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'")

_INSERT_KEY = text(
    """
    INSERT INTO idempotency_keys (key, kind, ttl)
    VALUES (:key, :kind, CAST(:ttl AS interval))
    ON CONFLICT DO NOTHING
    RETURNING key
    """
)

# Без возврата строк: у app_projector нет SELECT на outbox (миграция 0009).
# tx_id — xid8 NOT NULL без DEFAULT; pg_current_xact_id() — номер транзакции, не время.
_INSERT_OUTBOX = text(
    """
    INSERT INTO outbox (aggregate_id, event_type, payload, tx_id)
    VALUES (:aggregate_id, :event_type, CAST(:payload AS jsonb), pg_current_xact_id())
    """
)


@dataclass(frozen=True)
class NotifyResult:
    sent: int
    late: int
    skipped: int


@dataclass(frozen=True)
class NotifyTick:
    tasks_open: NotifyResult
    noon: NotifyResult


def _require_aware(now: datetime) -> None:
    if now.tzinfo is None or now.tzinfo.utcoffset(now) is None:
        raise ValueError("notify_ops: now — нужен datetime с часовым поясом (naive запрещён)")


def _utc(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc)


def choose_text(now: datetime, tz: str | None) -> str:
    """Местное время now < 04:00 → «сегодня», иначе «завтра» (В2 Б)."""
    _require_aware(now)
    local = _utc(now).astimezone(day_clock.zone(tz))
    if local.time() < day_clock.ACTIVATION_TIME:
        return TEXT_TODAY
    return TEXT_TOMORROW


def is_late(started: datetime, tz: str | None, now: datetime) -> bool:
    """Задания дня started уже открыты (В4 А): окно не not_active."""
    return day_clock.window(started, tz, now) != day_clock.WINDOW_NOT_ACTIVE


def decide(
    pid: uuid.UUID | str,
    started: datetime,
    tz: str | None,
    now: datetime,
    has_queue_key: bool,
    entered: bool,
) -> str | None:
    """None (не сейчас / не нужно) | "send" | "late". started — текущий day_started_at."""
    _require_aware(now)
    if has_queue_key:
        if _utc(now) < _utc(day_clock.queue_until(pid, started)):
            return None  # очередь ещё идёт
    elif not entered:
        return None
    return DECISION_LATE if is_late(started, tz, now) else DECISION_SEND


def _same_moment(a: datetime | None, b: datetime) -> bool:
    return a is not None and _utc(a) == _utc(b)


def _candidates(engine: Engine, now: datetime) -> list[uuid.UUID]:
    """Своя транзакция, только чтение; не больше MAX_PER_TICK."""
    with engine.connect() as conn:
        rows = conn.execute(
            life_ops._CANDIDATES, {"flags": list(life_ops.BLOCKING_FLAGS)}
        ).all()
        if not rows:
            conn.rollback()
            return []
        keys: list[str] = []
        for pid, _tz, started in rows:
            keys.append(key_tasks_open(pid, started))
            keys.append(key_day_queue(pid, started))
        existing = {r[0] for r in conn.execute(_EXISTING_KEYS, {"keys": keys}).all()}
        entered_rows = conn.execute(
            _ENTERED_ALL,
            {"kind": EVENT_KIND_DAY_ENTERED, "pids": [pid for pid, _tz, _s in rows]},
        ).all()
        conn.rollback()
    entered_at: dict[uuid.UUID, list[datetime]] = {}
    for pid, at in entered_rows:
        if at is not None:
            entered_at.setdefault(pid, []).append(at)
    found: list[uuid.UUID] = []
    for pid, tz, started in rows:
        if key_tasks_open(pid, started) in existing:
            continue
        has_queue = key_day_queue(pid, started) in existing
        entered = any(_same_moment(at, started) for at in entered_at.get(pid, ()))
        if decide(pid, started, tz, now, has_queue, entered) is None:
            continue
        found.append(pid)
        if len(found) >= MAX_PER_TICK:
            break
    return found


def _plan(conn: Connection, pid: uuid.UUID, row: Any, now: datetime) -> str | None:
    """Шаг 2 под замком: None — пропуск (ничего не писать)."""
    if not life_ops._eligible(row):
        return None
    if conn.execute(life_ops._PENDING_EVENT, {"pid": pid}).first() is not None:
        return None  # проектор не догнал pid — следующий тик
    started: datetime = row.day_started_at
    if conn.execute(_HAS_KEY, {"key": key_tasks_open(pid, started)}).first() is not None:
        return None
    has_queue = (
        conn.execute(_HAS_KEY, {"key": key_day_queue(pid, started)}).first() is not None
    )
    entered_rows = conn.execute(
        _ENTERED_ONE, {"kind": EVENT_KIND_DAY_ENTERED, "pid": pid}
    ).all()
    entered = any(_same_moment(r[0], started) for r in entered_rows)
    return decide(pid, started, row.tz, now, has_queue, entered)


def _write(conn: Connection, pid: uuid.UUID, row: Any, decision: str, now: datetime) -> bool:
    """Шаг 3: ключ, затем (для "send") строка outbox. Commit делает вызывающий."""
    inserted = conn.execute(
        _INSERT_KEY,
        {
            "key": key_tasks_open(pid, row.day_started_at),
            "kind": KIND_TASKS_OPEN,
            "ttl": TTL_TASKS_OPEN,
        },
    ).first()
    if inserted is None:
        return False  # ключ уже есть — ничего не пишем
    if decision == DECISION_SEND:
        payload = {"text_id": choose_text(now, row.tz), "payload_vars": {}, "tier": TIER}
        conn.execute(
            _INSERT_OUTBOX,
            {
                "aggregate_id": str(pid),
                "event_type": EVENT_TYPE,
                "payload": json.dumps(payload),
            },
        )
    return True


def notify_one(engine: Engine, pid: uuid.UUID, now: datetime) -> str | None:
    """Один pid — одна транзакция под замком participant:pid. Возвращает записанное решение."""
    with engine.connect() as conn:
        conn.execute(_LOCK_TIMEOUT)  # SET LOCAL — только эта транзакция
        lock_participant(conn, pid)
        row = conn.execute(life_ops._STATE, {"pid": pid}).first()
        decision = None if row is None else _plan(conn, pid, row, now)
        if decision is None or not _write(conn, pid, row, decision, now):
            conn.rollback()
            return None
        conn.commit()  # ключ + outbox — один commit
    return decision


def _run_rule(
    engine: Engine,
    now: datetime,
    label: str,
    candidates: Callable[[Engine, datetime], list[uuid.UUID]],
    one: Callable[[Engine, uuid.UUID, datetime], str | None],
) -> tuple[int, int, int]:
    """Общий цикл правила: каждый pid — try/except; (sent, late, skipped)."""
    sent = 0
    late = 0
    skipped = 0
    for pid in candidates(engine, now):
        try:
            decision = one(engine, pid, now)
        except Exception as exc:  # сбой одного pid не роняет тик
            # Без pid и текста исключения: только имя класса.
            logger.warning("notify_ops: error on %s (%s)", label, type(exc).__name__)
            decision = None
        if decision == DECISION_SEND:
            sent += 1
        elif decision == DECISION_LATE:
            late += 1
        else:
            skipped += 1
    return sent, late, skipped


def tick_tasks_open(engine: Engine, now: datetime) -> NotifyResult:
    """НП3 на момент now (aware). Ошибка чтения кандидатов — наружу."""
    _require_aware(now)
    sent, late, skipped = _run_rule(engine, now, "notify", _candidates, notify_one)
    logger.info("notify_ops: tick sent=%s late=%s skipped=%s", sent, late, skipped)
    return NotifyResult(sent, late, skipped)


# ------------------------------- НП1 (noon-1) -------------------------------


def _local(now: datetime, tz: str | None) -> datetime:
    _require_aware(now)
    return _utc(now).astimezone(day_clock.zone(tz))


def noon_window(now: datetime, tz: str | None) -> bool:
    """NOON_FROM ≤ местное время < NOON_UNTIL (НП1 А, В3 А)."""
    return NOON_FROM <= _local(now, tz).time() < NOON_UNTIL


def noon_local_date(now: datetime, tz: str | None) -> date:
    """Местная дата участника — для ключа noon (В5 А)."""
    return _local(now, tz).date()


def is_13p(module_no: int | None, day_no: int | None) -> bool:
    """13-P: день 13 чётного модуля (канон 03 §3.13; module_no сквозной по курсу)."""
    return day_no == 13 and module_no is not None and module_no % 2 == 0


def decide_noon(
    now: datetime,
    tz: str | None,
    started_at: datetime,
    module_no: int | None,
    day_no: int | None,
    marked: bool,
    done: bool,
    has_key: bool,
) -> str | None:
    """"send" | None. marked — есть отметки за started_at; done — ключ day_done; has_key — ключ noon."""
    if not noon_window(now, tz):
        return None
    if day_clock.window(started_at, tz, now) != day_clock.WINDOW_OPEN:
        return None
    if marked or done or has_key:
        return None
    if is_13p(module_no, day_no):
        return None
    return DECISION_SEND


def _noon_candidates(engine: Engine, now: datetime) -> list[uuid.UUID]:
    """Своя транзакция, только чтение; не больше MAX_PER_TICK."""
    with engine.connect() as conn:
        rows = conn.execute(
            _NOON_CANDIDATES, {"flags": list(life_ops.BLOCKING_FLAGS)}
        ).all()
        rows = [r for r in rows if noon_window(now, r.tz)]
        if not rows:
            conn.rollback()
            return []
        keys: list[str] = []
        for r in rows:
            keys.append(key_noon(r.pid, noon_local_date(now, r.tz)))
            keys.append(key_day_done(r.pid, r.day_started_at))
        existing = {k[0] for k in conn.execute(_EXISTING_KEYS, {"keys": keys}).all()}
        mark_rows = conn.execute(_MARKS_ALL, {"pids": [r.pid for r in rows]}).all()
        conn.rollback()
    marked: dict[uuid.UUID, set[datetime]] = {}
    for pid, started in mark_rows:
        marked.setdefault(pid, set()).add(_utc(started))
    found: list[uuid.UUID] = []
    for r in rows:
        decision = decide_noon(
            now,
            r.tz,
            r.day_started_at,
            r.module_no,
            r.day_no,
            _utc(r.day_started_at) in marked.get(r.pid, set()),
            key_day_done(r.pid, r.day_started_at) in existing,
            key_noon(r.pid, noon_local_date(now, r.tz)) in existing,
        )
        if decision is None:
            continue
        found.append(r.pid)
        if len(found) >= MAX_PER_TICK:
            break
    return found


def _plan_noon(conn: Connection, pid: uuid.UUID, row: Any, now: datetime) -> str | None:
    """Шаг 2 под замком: None — пропуск (ничего не писать)."""
    if not life_ops._eligible(row):
        return None
    if conn.execute(life_ops._PENDING_EVENT, {"pid": pid}).first() is not None:
        return None  # проектор не догнал pid — следующий тик
    started: datetime = row.day_started_at
    has_key = (
        conn.execute(_HAS_KEY, {"key": key_noon(pid, noon_local_date(now, row.tz))}).first()
        is not None
    )
    done = conn.execute(_HAS_KEY, {"key": key_day_done(pid, started)}).first() is not None
    marked = (
        conn.execute(_HAS_MARKS, {"pid": pid, "started": started}).first() is not None
    )
    return decide_noon(
        now, row.tz, started, row.module_no, row.day_no, marked, done, has_key
    )


def _write_noon(conn: Connection, pid: uuid.UUID, row: Any, now: datetime) -> bool:
    """Шаг 3: ключ noon, затем строка outbox. Commit делает вызывающий."""
    inserted = conn.execute(
        _INSERT_KEY,
        {
            "key": key_noon(pid, noon_local_date(now, row.tz)),
            "kind": KIND_NOON,
            "ttl": TTL_NOON,
        },
    ).first()
    if inserted is None:
        return False  # ключ уже есть — ничего не пишем
    payload = {"text_id": TEXT_NOON, "payload_vars": {}, "tier": NOON_TIER}
    conn.execute(
        _INSERT_OUTBOX,
        {
            "aggregate_id": str(pid),
            "event_type": NOON_EVENT_TYPE,
            "payload": json.dumps(payload),
        },
    )
    return True


def noon_one(engine: Engine, pid: uuid.UUID, now: datetime) -> str | None:
    """Один pid — одна транзакция под замком participant:pid. "send" — отправлено."""
    with engine.connect() as conn:
        conn.execute(_LOCK_TIMEOUT)  # SET LOCAL — только эта транзакция
        lock_participant(conn, pid)
        row = conn.execute(_NOON_STATE, {"pid": pid}).first()
        decision = None if row is None else _plan_noon(conn, pid, row, now)
        if decision is None or not _write_noon(conn, pid, row, now):
            conn.rollback()
            return None
        conn.commit()  # ключ + outbox — один commit
    return decision


def tick_noon(engine: Engine, now: datetime) -> NotifyResult:
    """НП1 на момент now (aware). late всегда 0. Ошибка чтения кандидатов — наружу."""
    _require_aware(now)
    sent, _late, skipped = _run_rule(engine, now, "noon", _noon_candidates, noon_one)
    logger.info("notify_ops: noon sent=%s skipped=%s", sent, skipped)
    return NotifyResult(sent, 0, skipped)


_EMPTY = NotifyResult(0, 0, 0)


def _safe_rule(
    name: str, rule: Callable[[Engine, datetime], NotifyResult], engine: Engine, now: datetime
) -> NotifyResult:
    try:
        return rule(engine, now)
    except Exception as exc:  # сбой правила не роняет другие правила
        logger.warning("notify_ops: rule %s failed (%s)", name, type(exc).__name__)
        return _EMPTY


def tick(engine: Engine, now: datetime) -> NotifyTick:
    """Вход для projector: правила tasks_open (НП3), затем noon (НП1). naive now → ValueError."""
    _require_aware(now)
    # Через имена модуля — подмена в тестах (monkeypatch) действует.
    tasks_open = _safe_rule("tasks_open", lambda e, n: tick_tasks_open(e, n), engine, now)
    noon = _safe_rule("noon", lambda e, n: tick_noon(e, n), engine, now)
    return NotifyTick(tasks_open, noon)
