"""Пауза курса из Mini App (api-pause-2, T3; Р-6а / Р-20).

Маршруты (префикс /miniapp/v1, initData → общий rate_limit — main.py; своих лимитов нет):
  GET  /pause          — бюджет и текущая пауза; ничего не пишет, замок не берёт;
  POST /pause/request  — заявка «с завтра» на 1..7 дней, тело {"days", "start_date"},
                         X-Client-Op-Id (UUID4) → 201;
  POST /pause/cancel   — отмена заявки до старта, тело {"pause_id"}, X-Client-Op-Id (UUID4)
                         → 202 {"status": "accepted"};
  POST /pause/resume   — досрочный выход из активной паузы, тело {"pause_id"},
                         X-Client-Op-Id (UUID4) → 202.
API пишет только строку заявки (INSERT participant_pauses), события, ключи idempotency_keys
и (только при доказанной коллизии op-id) security_events.
Статус паузы, флаг, бюджет и позицию меняет проектор v8; старт и конец по сроку — pause_ops.

GET /pause:
  1) участник (find_active_participant, без замка) — нет → 404 PARTICIPANT_NOT_FOUND;
  2) состояние, бюджет (roll_cycle только для расчёта, без записи), открытая / активная строка;
  3) refusal: есть строка → "already_open" (константа роутера, только GET); иначе
     start_refusal(status="approved", days=1, start_at = завтра 00:00 по поясу).
  4) start_date — местная дата next_midnight(now, tz) по поясу участника, всегда
     (и при can_request = false); клиент шлёт её в POST /pause/request (R-2026-11-21).     
POST /pause/request (всё под замком participant:pid, одна транзакция; pause-api-a2):
  1) active_pid_locked — нет → 404;
  2) h = _params_hash(days, start_date), ключ pause_request:{pid}:{op}. Ключ есть: params_hash
     равен h → строка по op, commit, 201 «repeat»; не равен (в том числе NULL) → _OpIdConflict
     (доказанная коллизия). Ключа нет, строка (pid, op) есть → commit, 201 с ней без аудита
     (коллизия не доказана);
  3) открытая или активная строка kind user → 409 PAUSE_ALREADY_OPEN;
  4) start_at = day_clock.next_midnight(now, tz), planned_end_at = 00:00 местной даты start + N;
     pause_rules.pause_days — проверка; местная дата start_at ≠ start_date → 409 PAUSE_REFUSED
     {"reason": "start_date_passed"}, ничего не пишется (дата не сдвигается, R-2026-11-21);
  5) состояние, бюджет, stage_taken, last_ended_at → start_refusal(status="approved");
     причина → 409 PAUSE_REFUSED, details {"reason"};
  6) INSERT ON CONFLICT (pid, client_op_id) DO NOTHING RETURNING id; IntegrityError индекса
     participant_pauses_one_open_user_uq → rollback, 409 PAUSE_ALREADY_OPEN; пусто → как шаг 2;
  7) INSERT ключа pause_request (ref = id строки, params_hash = h) без ON CONFLICT;
     конфликт ключа → IntegrityError → 503 (под замком невозможен);
  8) commit → 201 {"pause": {...}}.
  _OpIdConflict в _run: сначала rollback сессии запроса (замок снят, соединение в пуле),
  затем record_security_event(session.get_bind(), client_op_id_conflict) — своё соединение
  и своя транзакция; при любом итоге записи → 409 IDEMPOTENCY_CONFLICT.
  Бизнес-409 (PAUSE_ALREADY_OPEN, PAUSE_REFUSED) — без аудита (OVERRIDES §AD-01).
POST /pause/cancel (resume — в скобках; pause-api-a4). Тело {"pause_id": int >= 1} и
X-Client-Op-Id (UUID4) обязательны, иначе 422. Всё под замком participant:pid, одна транзакция:
  1) active_pid_locked — нет → 404;
  2) h = _target_hash("cancel" ("resume"), pause_id), ключ pause_op:{pid}:{op}. Ключ есть:
     params_hash равен h → commit, 202 «repeat» без проверок и без события; не равен
     (в том числе NULL) → _OpIdConflict (op_kind pause_cancel / pause_resume);
  3) строка (pid, pause_id) kind user в статусе requested / approved (active) — нет (в том числе
     чужая или несуществующая пауза) → 409 PAUSE_NOT_CANCELLABLE (PAUSE_NOT_ACTIVE) без аудита;
     ответ одинаковый — чужие паузы не раскрываются;
  4) ключ часов pause_start (pause_end) этой паузы есть → тот же 409;
  5) INSERT маркера pause_cancel (pause_resume):{pid}:{pause_id} ON CONFLICT DO NOTHING RETURNING
     key; пусто (действие уже сделал другой op) → шаг 7, commit, 202 «repeat» без события;
  6) событие pause_cancel {"pause_id"} (pause_ended {"pause_id", "reason": "by_participant"}),
     at = now;
  7) INSERT ключа pause_op (ref = pause_id, params_hash = h) без ON CONFLICT;
     конфликт → IntegrityError → 503 (под замком невозможен);
  8) commit → 202 «accepted».
  Маркер, событие и ключ pause_op — один commit (часы — тот же замок). _OpIdConflict — как у request:
  rollback, затем record_security_event, 409 IDEMPOTENCY_CONFLICT. Один op на /pause/request и
  на cancel/resume не сверяется (разные виды ключа): клиент даёт новый UUID на каждую операцию.
now — зависимость get_now() → day_clock.utcnow() (тесты подменяют). C0/C1 не проверяются (Д10).
Любая SQLAlchemyError (и на commit) → rollback, 503 SERVICE_UNAVAILABLE; в лог — имя класса.

Права app_api (0018, 0006, 0007): participant_pauses — INSERT (pid, kind, status, start_at,
planned_end_at, client_op_id), SELECT, USAGE participant_pauses_id_seq; pause_budgets — SELECT;
participant_events — INSERT; idempotency_keys — SELECT, INSERT; participant_state — SELECT;
security_events — только INSERT (0022), без SELECT и RETURNING.
UPDATE / DELETE participant_pauses, запись в pause_budgets, participant_state, outbox — нет.
Лог (app.pause): INFO только tg_user_id и итог (created / repeat / accepted / код ошибки;
для IDEMPOTENCY_CONFLICT ещё audit=ok|failed). pid, pause_id, op, tz и start_date в логе нет.
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from contextlib import suppress
from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import UUID4, BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app import day_clock, day_keys, pause_rules
from app.db.session import get_db_session
from app.participant_lock import active_pid_locked
from app.participants import find_active_participant
from app.security_events import CLIENT_OP_ID_CONFLICT, record_security_event
from app.telegram_init_data import InitDataContext, require_init_data

logger = logging.getLogger("app.pause")

# Префикс /miniapp/v1, проверка initData и rate-limit — в main.py (роутер miniapp_v1).
router = APIRouter(tags=["pause"])

CLIENT_OP_ID_HEADER = "X-Client-Op-Id"
REFUSAL_ALREADY_OPEN = "already_open"  # только GET; в pause_rules.REFUSAL_REASONS нет
REFUSAL_START_DATE_PASSED = "start_date_passed"  # как already_open: в pause_rules нет
OP_KIND_REQUEST = "pause_request"
OP_KIND_CANCEL = "pause_cancel"
OP_KIND_RESUME = "pause_resume"
ACTION_CANCEL = "cancel"
ACTION_RESUME = "resume"
OPEN_INDEX = "participant_pauses_one_open_user_uq"
STATUS_REQUESTED = "requested"
CANCELLABLE = ("requested", "approved")
ACTIVE = "active"
EVENT_CANCEL = "pause_cancel"
EVENT_ENDED = "pause_ended"
REASON_BY_PARTICIPANT = "by_participant"

# 5.1
_BUDGET_SQL = text(
    "SELECT days_budget_remaining_annual, cycle_start_at, restart_no "
    "FROM pause_budgets WHERE pid = :pid"
)
# 5.2 (ORDER BY id DESC — детерминированный порядок, если строк две: active и requested)
_OPEN_SQL = text(
    "SELECT id, status, start_at, planned_end_at FROM participant_pauses "
    "WHERE pid = :pid AND kind = 'user' AND status IN ('requested', 'approved', 'active') "
    "ORDER BY id DESC"
)
_BY_OP_SQL = text(
    "SELECT id, status, start_at, planned_end_at FROM participant_pauses "
    "WHERE pid = :pid AND client_op_id = :op"
)
_STAGE_TAKEN_SQL = text(
    "SELECT 1 FROM participant_pauses WHERE pid = :pid AND kind = 'user' "
    "AND status IN ('active', 'ended') AND stage_no = :stage AND restart_no = :restart"
)
_LAST_END_SQL = text(
    "SELECT max(ended_at) AS last FROM participant_pauses "
    "WHERE pid = :pid AND kind = 'user' AND status = 'ended'"
)
_INSERT_SQL = text(
    "INSERT INTO participant_pauses (pid, kind, status, start_at, planned_end_at, client_op_id) "
    "VALUES (:pid, 'user', 'requested', :start, :end, :op) "
    "ON CONFLICT (pid, client_op_id) DO NOTHING RETURNING id"
)
# 5.3
_STATE_SQL = text(
    "SELECT lifecycle_phase, day_no, tz, status_flags, stage_no "
    "FROM participant_state WHERE pid = :pid"
)
_INSERT_EVENT_SQL = text(
    "INSERT INTO participant_events (pid, kind, payload, actor, actor_role, at) "
    "VALUES (:pid, :kind, CAST(:payload AS jsonb), 'participant', 'participant', :at)"
)
# 5.4
_KEY_EXISTS_SQL = text("SELECT 1 FROM idempotency_keys WHERE key = :key")
_INSERT_KEY_SQL = text(
    "INSERT INTO idempotency_keys (key, kind, ttl, result_ref) "
    "VALUES (:key, :kind, CAST(:ttl AS interval), :ref) "
    "ON CONFLICT DO NOTHING RETURNING key"
)
# pause-api-a2: ключ заявки с params_hash (0007); без ON CONFLICT — конфликт → IntegrityError → 503
_KEY_HASH_SQL = text("SELECT params_hash FROM idempotency_keys WHERE key = :key")
_INSERT_REQUEST_KEY_SQL = text(
    "INSERT INTO idempotency_keys (key, kind, ttl, result_ref, params_hash) "
    "VALUES (:key, :kind, CAST(:ttl AS interval), :ref, :h)"
)
# pause-api-a4: цель cancel / resume — только своя пауза (пара pid, pause_id)
_TARGET_SQL = text(
    "SELECT id, status FROM participant_pauses "
    "WHERE pid = :pid AND id = :pause_id AND kind = 'user'"
)


class _OpIdConflict(Exception):
    """Доказанная коллизия op-id (не HTTPException): _run откатывает, пишет аудит, 409."""

    def __init__(self, pid: uuid.UUID, op: str, op_kind: str) -> None:
        super().__init__("client_op_id_conflict")
        self.pid = pid
        self.op = op
        self.op_kind = op_kind


def get_now() -> datetime:
    """«Сейчас» для паузы (Д9); тесты подменяют через dependency_overrides."""
    return day_clock.utcnow()


# ---------------------------- модели ----------------------------


class PauseRequestIn(BaseModel):
    # Лишние поля отбрасываются (pydantic по умолчанию).
    days: int = Field(ge=1, le=pause_rules.MAX_DAYS)
    start_date: date  # местная дата начала, подтверждённая участником (R-2026-11-21)


class PauseTargetIn(BaseModel):
    # цель cancel / resume (pause-api-a4); лишние поля отбрасываются
    pause_id: int = Field(ge=1)


class PauseOut(BaseModel):
    id: int
    status: str
    start_at: datetime
    planned_end_at: datetime


class PauseStatusOut(BaseModel):
    budget_days_left: int
    budget_days_total: int
    cycle_ends_at: datetime | None
    pause: PauseOut | None
    can_request: bool
    refusal: str | None
    start_date: date


class PauseRequestOut(BaseModel):
    pause: PauseOut


class AcceptedOut(BaseModel):
    status: str


# ---------------------------- ошибки ----------------------------


def _error(
    status_code: int, code: str, message: str, details: dict[str, Any] | None = None
) -> HTTPException:
    detail: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        detail["details"] = details
    return HTTPException(status_code=status_code, detail=detail)


def _participant_not_found() -> HTTPException:
    return _error(
        status.HTTP_404_NOT_FOUND, "PARTICIPANT_NOT_FOUND", "Участник не найден. Пройдите онбординг."
    )


def _service_unavailable() -> HTTPException:
    return _error(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "SERVICE_UNAVAILABLE",
        "Сервис временно недоступен. Попробуйте позже.",
    )


def _already_open() -> HTTPException:
    return _error(status.HTTP_409_CONFLICT, "PAUSE_ALREADY_OPEN", "Пауза уже запрошена или идёт.")


def _not_cancellable() -> HTTPException:
    return _error(status.HTTP_409_CONFLICT, "PAUSE_NOT_CANCELLABLE", "Заявку уже нельзя отменить.")


def _not_active() -> HTTPException:
    return _error(status.HTTP_409_CONFLICT, "PAUSE_NOT_ACTIVE", "Активной паузы нет.")


def _refused(reason: str) -> HTTPException:
    return _error(
        status.HTTP_409_CONFLICT, "PAUSE_REFUSED", "Паузу сейчас взять нельзя.", {"reason": reason}
    )


def _idempotency_conflict() -> HTTPException:
    return _error(
        status.HTTP_409_CONFLICT,
        "IDEMPOTENCY_CONFLICT",
        "Операция уже выполнена с другими параметрами. Обновите экран.",
    )


def _rollback(session: Session) -> None:
    with suppress(Exception):
        session.rollback()


def _released(session: Session, exc: Exception) -> Exception:
    """rollback (снимает xact-замок) и вернуть exc для raise."""
    _rollback(session)
    return exc


# ---------------------------- логика ----------------------------


def _utc(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc)


def _pause_out(row: Any) -> PauseOut:
    return PauseOut(
        id=row.id,
        status=row.status,
        start_at=_utc(row.start_at),
        planned_end_at=_utc(row.planned_end_at),
    )


def _state(session: Session, pid: uuid.UUID) -> Any:
    return session.execute(_STATE_SQL, {"pid": pid}).first()


def _budget(
    session: Session, pid: uuid.UUID, now: datetime, tz: str | None
) -> tuple[int, int, datetime | None]:
    """(остаток после roll_cycle, restart_no, конец цикла) — без записи (Д5)."""
    row = session.execute(_BUDGET_SQL, {"pid": pid}).first()
    if row is None:
        return pause_rules.BUDGET_DAYS, 0, None
    start, left = pause_rules.roll_cycle(
        row.cycle_start_at, row.days_budget_remaining_annual, now, tz
    )
    return left, row.restart_no, pause_rules.anniversary(start, tz)


def _refusal(
    session: Session,
    pid: uuid.UUID,
    state: Any,
    days: int,
    days_left: int,
    restart: int,
    start_at: datetime,
) -> str | None:
    """start_refusal с аргументами как в pause_ops._plan_start; status="approved" (Д4)."""
    stage = state.stage_no if state is not None else None
    stage_taken = False
    if stage is not None:
        stage_taken = (
            session.execute(
                _STAGE_TAKEN_SQL, {"pid": pid, "stage": stage, "restart": restart}
            ).first()
            is not None
        )
    last = session.execute(_LAST_END_SQL, {"pid": pid}).one().last
    return pause_rules.start_refusal(
        status=pause_rules.STATUS_APPROVED,
        flags=list(state.status_flags or ()) if state is not None else None,
        phase=state.lifecycle_phase if state is not None else None,
        day_no=state.day_no if state is not None else None,
        days=days,
        days_left=days_left,
        stage_taken=stage_taken,
        last_ended_at=last,
        start_at=start_at,
    )


def _params_hash(days: int, start_date: date) -> str:
    """sha256 каноничного JSON параметров заявки — сверка повтора (pause-api-a2)."""
    payload = json.dumps(
        {"days": days, "start_date": start_date.isoformat()},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _target_hash(action: str, pause_id: int) -> str:
    """sha256 каноничного JSON цели cancel / resume — сверка повтора (pause-api-a4)."""
    payload = json.dumps(
        {"action": action, "pause_id": pause_id},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _repeat(session: Session, pid: uuid.UUID, op: str, h: str) -> Any:
    """Шаг 2: прежняя строка по op, None — нет; ключ с другим params_hash → _OpIdConflict."""
    key_row = session.execute(
        _KEY_HASH_SQL, {"key": day_keys.key_pause_request(pid, op)}
    ).first()
    if key_row is not None:
        if key_row.params_hash != h:
            raise _OpIdConflict(pid, op, OP_KIND_REQUEST)
        return session.execute(_BY_OP_SQL, {"pid": pid, "op": op}).one()
    # ключа нет: строка по op — прежний результат без аудита (коллизия не доказана)
    return session.execute(_BY_OP_SQL, {"pid": pid, "op": op}).first()


def _bounds(now: datetime, tz: str | None, days: int) -> tuple[datetime, datetime]:
    """Д3: start = следующая 00:00 по поясу; end = 00:00 местной даты start + days."""
    z = day_clock.zone(tz)
    start = day_clock.next_midnight(now, tz)
    end_day = _utc(start).astimezone(z).date() + timedelta(days=days)
    end = datetime.combine(end_day, time(0, 0), tzinfo=z).astimezone(timezone.utc)
    pause_rules.pause_days(start, end, tz)
    return _utc(start), end


def _local_start_date(now: datetime, tz: str | None) -> date:
    """Местная дата ближайшей 00:00 по поясу (Д3) — та же, что start_at в _bounds."""
    start = day_clock.next_midnight(now, tz)
    return _utc(start).astimezone(day_clock.zone(tz)).date()


def read_status(session: Session, tg_user_id: int, now: datetime) -> PauseStatusOut:
    found = find_active_participant(session, tg_user_id)
    if found is None:
        raise _participant_not_found()
    pid = found[0]
    state = _state(session, pid)
    tz = state.tz if state is not None else None
    days_left, restart, cycle_ends_at = _budget(session, pid, now, tz)
    open_row = session.execute(_OPEN_SQL, {"pid": pid}).first()
    start_at = day_clock.next_midnight(now, tz)
    if open_row is not None:
        refusal: str | None = REFUSAL_ALREADY_OPEN
    else:
        refusal = _refusal(session, pid, state, 1, days_left, restart, start_at)
    return PauseStatusOut(
        budget_days_left=days_left,
        budget_days_total=pause_rules.BUDGET_DAYS,
        cycle_ends_at=_utc(cycle_ends_at) if cycle_ends_at is not None else None,
        pause=_pause_out(open_row) if open_row is not None else None,
        can_request=refusal is None,
        refusal=refusal,
        start_date=_local_start_date(now, tz),
    )


def request_pause(
    session: Session,
    tg_user_id: int,
    op_id: uuid.UUID,
    days: int,
    start_date: date,
    now: datetime,
) -> tuple[str, PauseOut]:
    """Шаги 1–8 → (created / repeat, пауза). Ошибки — HTTPException / _OpIdConflict /
    SQLAlchemyError."""
    # 1) участник под замком
    pid = active_pid_locked(session, tg_user_id)
    if pid is None:
        raise _released(session, _participant_not_found())

    # 2) повтор того же op — раньше всех проверок; сверка params_hash
    op = str(op_id)
    h = _params_hash(days, start_date)
    same = _repeat(session, pid, op, h)
    if same is not None:
        session.commit()
        return "repeat", _pause_out(same)

    # 3) открытая или активная строка
    if session.execute(_OPEN_SQL, {"pid": pid}).first() is not None:
        raise _released(session, _already_open())

    # 4) границы
    state = _state(session, pid)
    tz = state.tz if state is not None else None
    start_at, end_at = _bounds(now, tz, days)
    if start_at.astimezone(day_clock.zone(tz)).date() != start_date:
        # дата не сдвигается молча (R-2026-11-21): отказ и новое подтверждение
        raise _released(session, _refused(REFUSAL_START_DATE_PASSED))

    # 5) правила старта
    days_left, restart, _ = _budget(session, pid, now, tz)
    reason = _refusal(session, pid, state, days, days_left, restart, start_at)
    if reason is not None:
        raise _released(session, _refused(reason))

    # 6) строка заявки
    try:
        inserted = session.execute(
            _INSERT_SQL, {"pid": pid, "start": start_at, "end": end_at, "op": op}
        ).first()
    except IntegrityError as exc:
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint == OPEN_INDEX:
            raise _released(session, _already_open()) from None
        raise
    if inserted is None:
        same = _repeat(session, pid, op, h)
        if same is None:
            same = session.execute(_BY_OP_SQL, {"pid": pid, "op": op}).one()
        session.commit()
        return "repeat", _pause_out(same)

    # 7) ключ заявки с params_hash (конфликт → IntegrityError → 503)
    session.execute(
        _INSERT_REQUEST_KEY_SQL,
        {
            "key": day_keys.key_pause_request(pid, op),
            "kind": day_keys.KIND_PAUSE_REQUEST,
            "ttl": day_keys.TTL_BY_KIND[day_keys.KIND_PAUSE_REQUEST],
            "ref": str(inserted.id),
            "h": h,
        },
    )

    # 8) commit; ответ — только после него
    session.commit()
    return "created", PauseOut(
        id=inserted.id, status=STATUS_REQUESTED, start_at=start_at, planned_end_at=end_at
    )


def _insert_op_key(session: Session, pid: uuid.UUID, op: str, pause_id: int, h: str) -> None:
    """Шаг 7: ключ pause_op без ON CONFLICT (конфликт → IntegrityError → 503)."""
    session.execute(
        _INSERT_REQUEST_KEY_SQL,
        {
            "key": day_keys.key_pause_op(pid, op),
            "kind": day_keys.KIND_PAUSE_OP,
            "ttl": day_keys.TTL_BY_KIND[day_keys.KIND_PAUSE_OP],
            "ref": str(pause_id),
            "h": h,
        },
    )


def _finish_pause(
    session: Session,
    tg_user_id: int,
    op_id: uuid.UUID,
    pause_id: int,
    now: datetime,
    *,
    action: str,
    op_kind: str,
    statuses: tuple[str, ...],
    clock_key: Any,
    own_kind: str,
    own_key: Any,
    event_kind: str,
    payload_extra: dict[str, str],
    refuse: Any,
) -> str:
    """cancel / resume шаги 1–8 → accepted / repeat. Маркер, событие и ключ pause_op —
    один commit под замком. Ошибки — HTTPException / _OpIdConflict / SQLAlchemyError."""
    # 1) участник под замком
    pid = active_pid_locked(session, tg_user_id)
    if pid is None:
        raise _released(session, _participant_not_found())

    # 2) повтор того же op — раньше всех проверок; сверка хеша цели
    op = str(op_id)
    h = _target_hash(action, pause_id)
    key_row = session.execute(_KEY_HASH_SQL, {"key": day_keys.key_pause_op(pid, op)}).first()
    if key_row is not None:
        if key_row.params_hash != h:
            raise _OpIdConflict(pid, op, op_kind)
        session.commit()
        return "repeat"

    # 3) цель — только своя пауза в нужном статусе; чужая / нет → тот же 409 без аудита
    target = session.execute(_TARGET_SQL, {"pid": pid, "pause_id": pause_id}).first()
    if target is None or target.status not in statuses:
        raise _released(session, refuse())

    # 4) гонка с часами: ключ часов этой паузы уже есть → поздно
    if session.execute(_KEY_EXISTS_SQL, {"key": clock_key(pid, target.id)}).first() is not None:
        raise _released(session, refuse())

    # 5) маркер действия по pause_id
    added = session.execute(
        _INSERT_KEY_SQL,
        {
            "key": own_key(pid, target.id),
            "kind": own_kind,
            "ttl": day_keys.TTL_BY_KIND[own_kind],
            "ref": str(target.id),
        },
    ).first()
    if added is None:
        # действие уже сделано другим op: только ключ этого op, без события
        _insert_op_key(session, pid, op, target.id, h)
        session.commit()
        return "repeat"

    # 6) событие
    session.execute(
        _INSERT_EVENT_SQL,
        {
            "pid": pid,
            "kind": event_kind,
            "payload": json.dumps({"pause_id": target.id, **payload_extra}),
            "at": now,
        },
    )

    # 7) ключ pause_op; 8) commit — ответ только после него
    _insert_op_key(session, pid, op, target.id, h)
    session.commit()
    return "accepted"


def cancel_pause(
    session: Session, tg_user_id: int, op_id: uuid.UUID, pause_id: int, now: datetime
) -> str:
    return _finish_pause(
        session,
        tg_user_id,
        op_id,
        pause_id,
        now,
        action=ACTION_CANCEL,
        op_kind=OP_KIND_CANCEL,
        statuses=CANCELLABLE,
        clock_key=day_keys.key_pause_start,
        own_kind=day_keys.KIND_PAUSE_CANCEL,
        own_key=day_keys.key_pause_cancel,
        event_kind=EVENT_CANCEL,
        payload_extra={},
        refuse=_not_cancellable,
    )


def resume_pause(
    session: Session, tg_user_id: int, op_id: uuid.UUID, pause_id: int, now: datetime
) -> str:
    return _finish_pause(
        session,
        tg_user_id,
        op_id,
        pause_id,
        now,
        action=ACTION_RESUME,
        op_kind=OP_KIND_RESUME,
        statuses=(ACTIVE,),
        clock_key=day_keys.key_pause_end,
        own_kind=day_keys.KIND_PAUSE_RESUME,
        own_key=day_keys.key_pause_resume,
        event_kind=EVENT_ENDED,
        payload_extra={"reason": REASON_BY_PARTICIPANT},
        refuse=_not_active,
    )


def _run(session: Session, tg_user_id: int, name: str, fn: Any, *args: Any) -> Any:
    """Общая обёртка: rollback и лог при HTTPException, 503 при SQLAlchemyError;
    _OpIdConflict → rollback, затем аудит в отдельной транзакции, 409 IDEMPOTENCY_CONFLICT."""
    try:
        return fn(session, tg_user_id, *args)
    except _OpIdConflict as exc:
        _rollback(session)  # сначала откат: соединение уходит в пул, замок снят
        saved = record_security_event(
            session.get_bind(),
            event_type=CLIENT_OP_ID_CONFLICT,
            pid=exc.pid,
            op_kind=exc.op_kind,
            client_op_id=exc.op,
        )
        logger.info(
            "%s: tg_user_id=%s status=IDEMPOTENCY_CONFLICT audit=%s",
            name,
            tg_user_id,
            "ok" if saved else "failed",
        )
        raise _idempotency_conflict() from None  # 409 при любом saved
    except HTTPException as exc:
        _rollback(session)
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        logger.info(
            "%s: tg_user_id=%s status=%s", name, tg_user_id, detail.get("code", exc.status_code)
        )
        raise
    except SQLAlchemyError as exc:
        _rollback(session)
        logger.error("%s: ошибка БД (%s) — 503", name, type(exc).__name__)
        raise _service_unavailable() from None


# ---------------------------- маршруты ----------------------------

_COMMON = {
    404: {"description": "PARTICIPANT_NOT_FOUND"},
    429: {"description": "RATE_LIMITED, заголовок Retry-After"},
    503: {"description": "SERVICE_UNAVAILABLE (ошибка БД, в т. ч. commit)"},
}


@router.get("/pause", response_model=PauseStatusOut, responses=_COMMON)
def get_pause(
    ctx: InitDataContext = Depends(require_init_data),
    session: Session = Depends(get_db_session),
    now: datetime = Depends(get_now),
) -> PauseStatusOut:
    result: PauseStatusOut = _run(session, ctx.tg_user_id, "pause", read_status, now)
    _rollback(session)  # только чтение: транзакцию закрываем без commit
    return result


@router.post(
    "/pause/request",
    status_code=status.HTTP_201_CREATED,
    response_model=PauseRequestOut,
    responses={
        **_COMMON,
        409: {
            "description": "PAUSE_ALREADY_OPEN / PAUSE_REFUSED (details.reason: причины "
            "pause_rules или start_date_passed) / IDEMPOTENCY_CONFLICT"
        },
        422: {"description": "VALIDATION_ERROR"},
    },
)
def post_pause_request(
    body: PauseRequestIn,
    # Annotated, как в support.py: так FastAPI проверяет версию UUID4 (не-v4 → 422).
    client_op_id: Annotated[UUID4, Header(alias=CLIENT_OP_ID_HEADER)],
    ctx: InitDataContext = Depends(require_init_data),
    session: Session = Depends(get_db_session),
    now: datetime = Depends(get_now),
) -> PauseRequestOut:
    outcome, pause = _run(
        session,
        ctx.tg_user_id,
        "pause/request",
        request_pause,
        client_op_id,
        body.days,
        body.start_date,
        now,
    )
    logger.info("pause/request: tg_user_id=%s status=%s", ctx.tg_user_id, outcome)
    return PauseRequestOut(pause=pause)


@router.post(
    "/pause/cancel",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AcceptedOut,
    responses={
        **_COMMON,
        409: {"description": "PAUSE_NOT_CANCELLABLE / IDEMPOTENCY_CONFLICT"},
        422: {"description": "VALIDATION_ERROR"},
    },
)
def post_pause_cancel(
    body: PauseTargetIn,
    client_op_id: Annotated[UUID4, Header(alias=CLIENT_OP_ID_HEADER)],
    ctx: InitDataContext = Depends(require_init_data),
    session: Session = Depends(get_db_session),
    now: datetime = Depends(get_now),
) -> AcceptedOut:
    outcome = _run(
        session, ctx.tg_user_id, "pause/cancel", cancel_pause, client_op_id, body.pause_id, now
    )
    logger.info("pause/cancel: tg_user_id=%s status=%s", ctx.tg_user_id, outcome)
    return AcceptedOut(status="accepted")


@router.post(
    "/pause/resume",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AcceptedOut,
    responses={
        **_COMMON,
        409: {"description": "PAUSE_NOT_ACTIVE / IDEMPOTENCY_CONFLICT"},
        422: {"description": "VALIDATION_ERROR"},
    },
)
def post_pause_resume(
    body: PauseTargetIn,
    client_op_id: Annotated[UUID4, Header(alias=CLIENT_OP_ID_HEADER)],
    ctx: InitDataContext = Depends(require_init_data),
    session: Session = Depends(get_db_session),
    now: datetime = Depends(get_now),
) -> AcceptedOut:
    outcome = _run(
        session, ctx.tg_user_id, "pause/resume", resume_pause, client_op_id, body.pause_id, now
    )
    logger.info("pause/resume: tg_user_id=%s status=%s", ctx.tg_user_id, outcome)
    return AcceptedOut(status="accepted")
