"""Лестница «пришёл, но не отправил» (ladder-1, DM 3.17): +1 ч, 22:00, 23:30.

Источник — docs/tasks/ladder-1.md (§2, §6). Участник отметил хотя бы одно задание текущего дня
(есть строки day_marks за текущий day_started_at), отчёт не сдан (нет ключа day_done) — бот
напоминает три раза:
  - plus1h   — через 1 ч после первой отметки дня (min(day_marks.at)), но не позже «−2 ч»;
  - minus2h  — за 2 ч до дедлайна day_clock (00:00 следующих суток после активации);
  - minus30m — за 30 мин до дедлайна.
Шаги считаются в UTC (Т2). В7 А: отправляется только самый поздний наступивший шаг; более ранние
наступившие шаги без ключа — только ключ (late), без отправки. plus1h ограничен «−2 ч» (min):
если first + 1 ч ≥ дедлайн − 2 ч, plus1h наступает вместе с minus2h и всегда уходит в late.

Вход один — notify_ops.tick (Т1). notify_ops импортирует этот модуль внутри tick, а этот модуль
импортирует notify_ops и берёт его помощники только при вызове: _run_rule, _LOCK_TIMEOUT,
_EXISTING_KEYS, _HAS_KEY, _INSERT_KEY, _INSERT_OUTBOX, MAX_PER_TICK, logger. Своего INSERT
в outbox здесь нет. Пишется только idempotency_keys (kind ladder) и outbox; participant_state и
participant_events не пишутся (E1 / INV-1). Алерт Автору «день 2 проблемы» — вне задачи.

tick_ladder(engine, now) → NotifyResult(sent, late, skipped):
  1. Кандидаты — своя транзакция, только чтение: фильтр life_ops (_CANDIDATES, BLOCKING_FLAGS);
     окно дня open; батчем — первая отметка min(at) по (pid, day_started_at), ключи day_done и
     ladder трёх шагов; decide_ladder; не больше MAX_PER_TICK.
  2. Каждый pid — своя транзакция под lock_participant (lock_timeout): состояние заново,
     life_ops._eligible, «проектор догнал pid», данные и решение заново.
  3. Ключи late (ON CONFLICT DO NOTHING), ключ send (RETURNING; 0 строк → rollback), строка
     outbox ladder_reminder (T2). Один commit на pid.
sent — pid с отправкой; late — записанные ключи без отправки; skipped — остальные кандидаты.

Время: now — только аргумент; сравнения — в UTC. Лог: без pid, tz, payload и ПДн.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Connection, Engine, text

# notify_ops не импортирует этот модуль на уровне модуля (только внутри tick) — цикла нет.
from app import day_clock, life_ops, notify_ops
from app.day_keys import (
    KIND_LADDER,
    LADDER_STEPS,
    TTL_LADDER,
    key_day_done,
    key_ladder,
)
from app.participant_lock import lock_participant

EVENT_TYPE = "ladder_reminder"
TIER = "T2"
STEP_PLUS1H, STEP_MINUS2H, STEP_MINUS30M = LADDER_STEPS
PLUS1H = timedelta(hours=1)
MINUS2H = timedelta(hours=2)
MINUS30M = timedelta(minutes=30)
TEXT_BY_STEP: dict[str, str] = {
    STEP_PLUS1H: "B9.day_ladder_plus1h",
    STEP_MINUS2H: "B9.day_ladder_minus2h",
    STEP_MINUS30M: "B9.day_ladder_minus30m",
}

_FIRST_MARKS_ALL = text(
    """
    SELECT pid, day_started_at, min(at) AS first_at
    FROM day_marks
    WHERE pid = ANY(CAST(:pids AS uuid[]))
    GROUP BY pid, day_started_at
    """
)

_FIRST_MARK_ONE = text(
    "SELECT min(at) FROM day_marks WHERE pid = :pid AND day_started_at = :started"
)


@dataclass(frozen=True)
class LadderPlan:
    send: str
    late: tuple[str, ...]


def _utc(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc)


def step_times(first_mark_at: datetime, deadline: datetime) -> list[tuple[str, datetime]]:
    """[(plus1h, min(first + 1 ч, дедлайн − 2 ч)), (minus2h, дедлайн − 2 ч), (minus30m, …)] в UTC."""
    first_u = _utc(first_mark_at)
    deadline_u = _utc(deadline)
    minus2h = deadline_u - MINUS2H
    return [
        (STEP_PLUS1H, min(first_u + PLUS1H, minus2h)),
        (STEP_MINUS2H, minus2h),
        (STEP_MINUS30M, deadline_u - MINUS30M),
    ]


def decide_ladder(
    now: datetime,
    window_open: bool,
    first_mark_at: datetime | None,
    deadline: datetime,
    done: bool,
    keyed: set[str] | frozenset[str] | tuple[str, ...],
) -> LadderPlan | None:
    """None | LadderPlan(send — последний наступивший шаг без ключа, late — остальные такие)."""
    notify_ops._require_aware(now)
    if not window_open or first_mark_at is None or done:
        return None
    now_u = _utc(now)
    due = [
        step
        for step, at in step_times(first_mark_at, deadline)
        if at <= now_u and step not in keyed
    ]
    if not due:
        return None
    return LadderPlan(send=due[-1], late=tuple(due[:-1]))


def _decide_for(
    now: datetime,
    tz: str | None,
    started: datetime,
    first_mark_at: datetime | None,
    done: bool,
    keyed: set[str],
) -> LadderPlan | None:
    window_open = day_clock.window(started, tz, now) == day_clock.WINDOW_OPEN
    deadline = day_clock.deadline_at(started, tz)
    return decide_ladder(now, window_open, first_mark_at, deadline, done, keyed)


def _candidates(engine: Engine, now: datetime) -> list[uuid.UUID]:
    """Своя транзакция, только чтение; не больше MAX_PER_TICK."""
    with engine.connect() as conn:
        rows = conn.execute(
            life_ops._CANDIDATES, {"flags": list(life_ops.BLOCKING_FLAGS)}
        ).all()
        rows = [
            (pid, tz, started)
            for pid, tz, started in rows
            if day_clock.window(started, tz, now) == day_clock.WINDOW_OPEN
        ]
        if not rows:
            conn.rollback()
            return []
        keys: list[str] = []
        for pid, _tz, started in rows:
            keys.append(key_day_done(pid, started))
            keys.extend(key_ladder(pid, started, step) for step in LADDER_STEPS)
        existing = {
            r[0] for r in conn.execute(notify_ops._EXISTING_KEYS, {"keys": keys}).all()
        }
        mark_rows = conn.execute(
            _FIRST_MARKS_ALL, {"pids": [pid for pid, _tz, _s in rows]}
        ).all()
        conn.rollback()
    first_at: dict[tuple[uuid.UUID, datetime], datetime] = {}
    for pid, started, at in mark_rows:
        if at is not None:
            first_at[(pid, _utc(started))] = at
    found: list[uuid.UUID] = []
    for pid, tz, started in rows:
        keyed = {s for s in LADDER_STEPS if key_ladder(pid, started, s) in existing}
        plan = _decide_for(
            now,
            tz,
            started,
            first_at.get((pid, _utc(started))),
            key_day_done(pid, started) in existing,
            keyed,
        )
        if plan is None:
            continue
        found.append(pid)
        if len(found) >= notify_ops.MAX_PER_TICK:
            break
    return found


def _has_key(conn: Connection, key: str) -> bool:
    return conn.execute(notify_ops._HAS_KEY, {"key": key}).first() is not None


def _plan(conn: Connection, pid: uuid.UUID, row: Any, now: datetime) -> LadderPlan | None:
    """Шаг 2 под замком: None — пропуск (ничего не писать)."""
    if not life_ops._eligible(row):
        return None
    if conn.execute(life_ops._PENDING_EVENT, {"pid": pid}).first() is not None:
        return None  # проектор не догнал pid — следующий тик
    started: datetime = row.day_started_at
    done = _has_key(conn, key_day_done(pid, started))
    keyed = {s for s in LADDER_STEPS if _has_key(conn, key_ladder(pid, started, s))}
    first_mark_at = conn.execute(
        _FIRST_MARK_ONE, {"pid": pid, "started": started}
    ).scalar()
    return _decide_for(now, row.tz, started, first_mark_at, done, keyed)


def _insert_key(conn: Connection, pid: uuid.UUID, started: datetime, step: str) -> bool:
    inserted = conn.execute(
        notify_ops._INSERT_KEY,
        {"key": key_ladder(pid, started, step), "kind": KIND_LADDER, "ttl": TTL_LADDER},
    ).first()
    return inserted is not None


def _write(conn: Connection, pid: uuid.UUID, row: Any, plan: LadderPlan) -> int | None:
    """Шаг 3: ключи late, ключ send, строка outbox. None — ключ send уже есть (rollback).
    Возвращает число записанных ключей late. Commit делает вызывающий."""
    started: datetime = row.day_started_at
    late_written = sum(1 for step in plan.late if _insert_key(conn, pid, started, step))
    if not _insert_key(conn, pid, started, plan.send):
        return None
    payload = {"text_id": TEXT_BY_STEP[plan.send], "payload_vars": {}, "tier": TIER}
    conn.execute(
        notify_ops._INSERT_OUTBOX,
        {"aggregate_id": str(pid), "event_type": EVENT_TYPE, "payload": json.dumps(payload)},
    )
    return late_written


def ladder_one(
    engine: Engine, pid: uuid.UUID, now: datetime, late_counter: list[int] | None = None
) -> str | None:
    """Один pid — одна транзакция под замком participant:pid. "send" — отправлено.
    late_counter[0] += число записанных ключей late (после commit)."""
    with engine.connect() as conn:
        conn.execute(notify_ops._LOCK_TIMEOUT)  # SET LOCAL — только эта транзакция
        lock_participant(conn, pid)
        row = conn.execute(life_ops._STATE, {"pid": pid}).first()
        plan = None if row is None else _plan(conn, pid, row, now)
        late_written = None if plan is None else _write(conn, pid, row, plan)
        if late_written is None:
            conn.rollback()
            return None
        conn.commit()  # ключи + outbox — один commit
    if late_counter is not None:
        late_counter[0] += late_written
    return notify_ops.DECISION_SEND


def tick_ladder(engine: Engine, now: datetime) -> notify_ops.NotifyResult:
    """Лестница на момент now (aware). Ошибка чтения кандидатов — наружу."""
    notify_ops._require_aware(now)
    late_counter = [0]
    sent, _late, skipped = notify_ops._run_rule(
        engine,
        now,
        "ladder",
        _candidates,
        lambda e, p, n: ladder_one(e, p, n, late_counter),
    )
    late = late_counter[0]
    notify_ops.logger.info(
        "notify_ops: ladder sent=%s late=%s skipped=%s", sent, late, skipped
    )
    return notify_ops.NotifyResult(sent, late, skipped)
