"""Ключи idempotency_keys для дня (iter2-api-1; решения В22 и Ш4).

Формат ключей:
  day_enter:{pid}             — участник начал вход в день (kind day_enter, ttl 3650 days);
  day_done:{pid}:{dsa}        — день с этим day_started_at сдан (kind day_done, ttl 3650 days);
  day_report:{pid}:{op_id}    — отчёт по client_op_id (kind day_report, ttl 1 hour);
  day_close:{pid}:{dsa}       — день с этим day_started_at закрыт (kind day_close, ttl 3650 days,
                                life-ops-a; пишет life-ops-c);
  day_queue:{pid}:{dsa}       — задания следующего дня после этого дня отправлены в очередь
                                (kind day_queue, ttl 3650 days, life-ops-a; пишет life-ops-b);
  tasks_open:{pid}:{dsa}      — НП3 «Задания откроются … в 04:00» к дню с этим day_started_at
                                обработано (kind tasks_open, ttl 3650 days, pushi-notify-1;
                                пишет notify_ops);
  noon:{pid}:{YYYY-MM-DD}     — НП1 полуденное за эту местную дату участника отправлено
                                (kind noon, ttl 3650 days, noon-1; пишет notify_ops);
  ladder:{pid}:{dsa}:{step}   — шаг лестницы «пришёл, но не отправил» (DM 3.17) к дню с этим
                                day_started_at обработан; step ∈ LADDER_STEPS (kind ladder,
                                ttl 3650 days, ladder-1; пишет notify_ladder);
  ladder_day2:{pid}:{dsa}     — алерт Автору «день 2 проблемы» (ladder_day2_alert) к дню с этим
                                day_started_at записан (kind ladder_day2, ttl 3650 days,
                                clocks-1; пишет notify_ladder);
  pause_start:{pid}:{pause_id} — заявка паузы обработана часами в start_at: pause_started или
                                pause_start_failed (взаимоисключающие; kind pause_start,
                                ttl 3650 days, api-pause-1b; пишет pause_ops);
  pause_end:{pid}:{pause_id}  — пауза закончена по сроку, pause_ended expired записан
                                (kind pause_end, ttl 3650 days, api-pause-1b; пишет pause_ops);
  pause_cancel:{pid}:{pause_id} — участник отменил заявку паузы, событие pause_cancel записано
                                (kind pause_cancel, ttl 3650 days, api-pause-2; пишет routers/pause);
  pause_resume:{pid}:{pause_id} — участник вышел из паузы досрочно, pause_ended by_participant
                                записан (kind pause_resume, ttl 3650 days, api-pause-2;
                                пишет routers/pause);
  pause_request:{pid}:{op_id} — заявка паузы по client_op_id создана, result_ref — id строки,
                                params_hash — хеш параметров (kind pause_request, ttl 3650 days,
                                pause-api-a2; пишет routers/pause);
  pause_op:{pid}:{op_id}      — cancel или resume по client_op_id; result_ref = pause_id,
                                params_hash — хеш цели (kind pause_op, ttl 3650 days,
                                pause-api-a4; пишет routers/pause).

dsa (Ш4) — day_started_at в UTC, ISO 8601: ts.astimezone(timezone.utc).isoformat().
Один и тот же момент в любом поясе даёт один и тот же ключ; naive datetime → ValueError
(момент без пояса неоднозначен).

Срок ttl в логике не проверяется, кроме day_report: submit отвечает 409
на повтор после created_at + ttl (api-3). UPDATE и DELETE ключей нет ни у кого. Здесь только построение ключей; пишут их iter2-api-2a/2b.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

KIND_DAY_ENTER = "day_enter"
KIND_DAY_DONE = "day_done"
KIND_DAY_REPORT = "day_report"
KIND_DAY_CLOSE = "day_close"
KIND_DAY_QUEUE = "day_queue"
KIND_TASKS_OPEN = "tasks_open"
KIND_NOON = "noon"
KIND_LADDER = "ladder"
KIND_LADDER_DAY2 = "ladder_day2"
KIND_PAUSE_START = "pause_start"
KIND_PAUSE_END = "pause_end"
KIND_PAUSE_CANCEL = "pause_cancel"
KIND_PAUSE_RESUME = "pause_resume"
KIND_PAUSE_REQUEST = "pause_request"
KIND_PAUSE_OP = "pause_op"

TTL_DAY_ENTER = "3650 days"
TTL_DAY_DONE = "3650 days"
TTL_DAY_REPORT = "1 hour"
TTL_DAY_CLOSE = "3650 days"
TTL_DAY_QUEUE = "3650 days"
TTL_TASKS_OPEN = "3650 days"
TTL_NOON = "3650 days"
TTL_LADDER = "3650 days"
TTL_LADDER_DAY2 = "3650 days"
TTL_PAUSE_START = "3650 days"
TTL_PAUSE_END = "3650 days"
TTL_PAUSE_CANCEL = "3650 days"
TTL_PAUSE_RESUME = "3650 days"
TTL_PAUSE_REQUEST = "3650 days"
TTL_PAUSE_OP = "3650 days"

LADDER_STEPS = ("plus1h", "minus2h", "minus30m")

TTL_BY_KIND: dict[str, str] = {
    KIND_DAY_ENTER: TTL_DAY_ENTER,
    KIND_DAY_DONE: TTL_DAY_DONE,
    KIND_DAY_REPORT: TTL_DAY_REPORT,
    KIND_DAY_CLOSE: TTL_DAY_CLOSE,
    KIND_DAY_QUEUE: TTL_DAY_QUEUE,
    KIND_TASKS_OPEN: TTL_TASKS_OPEN,
    KIND_NOON: TTL_NOON,
    KIND_LADDER: TTL_LADDER,
    KIND_LADDER_DAY2: TTL_LADDER_DAY2,
    KIND_PAUSE_START: TTL_PAUSE_START,
    KIND_PAUSE_END: TTL_PAUSE_END,
    KIND_PAUSE_CANCEL: TTL_PAUSE_CANCEL,
    KIND_PAUSE_RESUME: TTL_PAUSE_RESUME,
    KIND_PAUSE_REQUEST: TTL_PAUSE_REQUEST,
    KIND_PAUSE_OP: TTL_PAUSE_OP,
}


def dsa(ts: datetime) -> str:
    """day_started_at → строка UTC ISO 8601. Naive datetime → ValueError."""
    if ts.tzinfo is None or ts.tzinfo.utcoffset(ts) is None:
        raise ValueError("dsa: нужен datetime с часовым поясом (naive запрещён)")
    return ts.astimezone(timezone.utc).isoformat()


def key_day_enter(pid: uuid.UUID | str) -> str:
    return f"{KIND_DAY_ENTER}:{pid}"


def key_day_done(pid: uuid.UUID | str, ts: datetime) -> str:
    return f"{KIND_DAY_DONE}:{pid}:{dsa(ts)}"


def key_day_report(pid: uuid.UUID | str, op_id: str) -> str:
    return f"{KIND_DAY_REPORT}:{pid}:{op_id}"


def key_day_close(pid: uuid.UUID | str, ts: datetime) -> str:
    return f"{KIND_DAY_CLOSE}:{pid}:{dsa(ts)}"


def key_day_queue(pid: uuid.UUID | str, ts: datetime) -> str:
    return f"{KIND_DAY_QUEUE}:{pid}:{dsa(ts)}"


def key_tasks_open(pid: uuid.UUID | str, ts: datetime) -> str:
    return f"{KIND_TASKS_OPEN}:{pid}:{dsa(ts)}"


def key_noon(pid: uuid.UUID | str, local_date: date) -> str:
    """local_date — местная дата участника (В5 А: одно полуденное в местные сутки)."""
    return f"{KIND_NOON}:{pid}:{local_date.isoformat()}"


def key_ladder(pid: uuid.UUID | str, started_at: datetime, step: str) -> str:
    """step — один из LADDER_STEPS; иначе ValueError."""
    if step not in LADDER_STEPS:
        raise ValueError("key_ladder: неизвестный шаг лестницы")
    return f"{KIND_LADDER}:{pid}:{dsa(started_at)}:{step}"


def key_ladder_day2(pid: uuid.UUID | str, started_at: datetime) -> str:
    """Алерт «день 2 проблемы» к дню с этим day_started_at (clocks-1)."""
    return f"{KIND_LADDER_DAY2}:{pid}:{dsa(started_at)}"


def key_pause_start(pid: uuid.UUID | str, pause_id: int | str) -> str:
    """Старт заявки паузы обработан (pause_started или pause_start_failed; api-pause-1b)."""
    return f"{KIND_PAUSE_START}:{pid}:{pause_id}"


def key_pause_end(pid: uuid.UUID | str, pause_id: int | str) -> str:
    """Пауза закончена по сроку (pause_ended expired; api-pause-1b)."""
    return f"{KIND_PAUSE_END}:{pid}:{pause_id}"


def key_pause_cancel(pid: uuid.UUID | str, pause_id: int | str) -> str:
    """Участник отменил заявку паузы (pause_cancel; api-pause-2)."""
    return f"{KIND_PAUSE_CANCEL}:{pid}:{pause_id}"


def key_pause_resume(pid: uuid.UUID | str, pause_id: int | str) -> str:
    """Участник вышел из паузы досрочно (pause_ended by_participant; api-pause-2)."""
    return f"{KIND_PAUSE_RESUME}:{pid}:{pause_id}"


def key_pause_request(pid: uuid.UUID | str, op_id: uuid.UUID | str) -> str:
    """Заявка паузы по client_op_id (params_hash — сверка повтора; pause-api-a2)."""
    return f"{KIND_PAUSE_REQUEST}:{pid}:{op_id}"


def key_pause_op(pid: uuid.UUID | str, op_id: uuid.UUID | str) -> str:
    """cancel / resume паузы по client_op_id (params_hash — хеш цели; pause-api-a4)."""
    return f"{KIND_PAUSE_OP}:{pid}:{op_id}"
