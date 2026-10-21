"""/miniapp/v1/day/* — день участника (iter2-api-1: GET current; iter2-api-2a: test-enter, marks;
iter2-api-2b: report/submit; life-ops-b: окно дня 04:00–00:00, позиция в отчёте, очередь в GET).

Время (life-ops-b, У1): «сейчас» — только day_clock.utcnow(), один раз за запрос: в marks и
submit — после замка participant:pid, в GET — в начале read_day_current. Окно, границы и
очередь — функции day_clock; свои сравнения моментов — только в UTC (docstring day_clock).
tz — из participant_state тем же SELECT; пустой tz передаётся в day_clock как есть.

initData и rate-limit — роутер miniapp_v1 в main.py.
Общие правила:
  - pid — ТОЛЬКО по tg_user_id из проверенной initData (find_active_participant);
    pid и day_started_at из тела запроса не берутся никогда (лишние поля игнорируются);
  - participant_state читается text-SQL SELECT (lives, stage_no, module_no, day_no,
    day_started_at, tz). Это только чтение: писатель participant_state — проектор (E1/INV-1);
  - любая ошибка БД (SQLAlchemyError) → 503 SERVICE_UNAVAILABLE, в лог только имя класса;
  - транзакция закрывается сразу (ревью #101): GET — rollback перед ответом; test-enter,
    marks и report/submit — rollback перед каждым возвратом без записи и перед каждой ошибкой
    после замка, чтобы xact-замок participant:pid снимался сразу.

GET /day/current — только чтение, ничего не пишет:
  - нет активного pid (или tombstoned) → 404 PARTICIPANT_NOT_FOUND;
  - нет строки state → not_started, lives 3 (DEFAULT колонки);
  - позиции нет (day_no NULL) → entering, если есть ключ day_enter, иначе not_started;
  - позиция есть, статус по приоритету (life-ops-b): submitted (ключ day_done по текущему
    day_started_at) → queued (ключ day_queue по текущему day_started_at и now < queued_until;
    position, blocks, min_optional = null) → closed (окно closed) → open;
  - при позиции: active_from, deadline_at (пояс участника), queued_until (только queued,
    иначе null), buttons_active = окно open и статус не submitted/queued (submitted и queued →
    false всегда: после сдачи marks отвечает 409 DAY_ALREADY_SUBMITTED);
  - отметки — из day_marks только по pid и текущему day_started_at (true → done,
    false → not_done, нет строки → null);
  - can_submit = все блоки отмечены, статус open и окно open;
  - test_entry = флаг DAY_TEST_ENTRY_ENABLED включён и позиции нет (iter2-api-2a);
  - позиция есть, а контента дня нет → 503 DAY_CONTENT_MISSING, в лог ERROR
    (stage, module, day; без pid).

POST /day/test-enter (iter2-api-2a, В3 — А; тела нет). Писатель событий существующего pid:
замок participant:pid (participant_lock.py) берётся ДО записи и держится до commit.
  1) флаг выключен → 404 NOT_FOUND до любых обращений к сессии БД (обработчик проверяет
     флаг до try — даже rollback не вызывается; Д2, iter2-api-2b);
  2) нет активного pid под замком → 404 PARTICIPANT_NOT_FOUND;
  3) C0 или C1 не действует (та же проверка, что GET /onboarding/status) → 409 RECONSENT_REQUIRED;
     нет текста согласия → 503 SERVICE_MISCONFIGURED;
  4) нет строки state → 409 DAY_STATE_SYNCING + Retry-After: 1;
  5) позиция есть → 200 {status: already};
  6) есть ключ day_enter → 202 {status: entering}, без события;
  7) нет контента дня (1, 1, 1) → 503 DAY_CONTENT_MISSING, ничего не записано;
  8) INSERT idempotency_keys (day_enter) → INSERT participant_events kind day_entered,
     payload {stage_no 1, module_no 1, day_no 1, source test_flag}, actor system → commit → 202.
  Фаза участника не меняется (В21): позицию и day_started_at ставит проектор.

PUT /day/marks (iter2-api-2a), тело {block_id ^[a-z0-9_]{1,32}$, value done | not_done}:
  нет активного pid под замком → 404; позиции нет → 409 DAY_NOT_STARTED;
  окно not_active → 409 DAY_NOT_ACTIVE, closed → 409 DAY_CLOSED; нет контента → 503;
  block_id не из блоков текущего дня → 422 BLOCK_NOT_IN_DAY;
  есть ключ day_done → 409 DAY_ALREADY_SUBMITTED;
  INSERT day_marks (pid и day_started_at — с сервера) ON CONFLICT DO UPDATE SET value:
  at не меняется — время первой отметки блока («пришёл» = min(at), В19) → commit → 200.

POST /day/report/submit (iter2-api-2b; П-31, В15, В18, В22), заголовок X-Client-Op-Id (uuid,
обязателен; нет или не uuid → 422 VALIDATION_ERROR), тело {marks: [{block_id, value}]}.
Одна транзакция, порядок:
  1) нет активного pid под замком → 404 PARTICIPANT_NOT_FOUND;
  2) есть ключ day_report:{pid}:{op_id}: params_hash тот же → 200 {verdict: result_ref,
     queued: true} без записи (В15); другой → 409 IDEMPOTENCY_CONFLICT;
  3) позиции нет → 409 DAY_NOT_STARTED; контента нет → 503 DAY_CONTENT_MISSING;
     окно not_active → 409 DAY_NOT_ACTIVE, closed → 409 DAY_CLOSED (повтор op_id — раньше);
  4) набор block_id ≠ блоки дня (лишний, недостающий, повтор) → 422 MARKS_INCOMPLETE;
  5) есть ключ day_done по текущему day_started_at → 409 DAY_ALREADY_SUBMITTED;
  6) UPSERT day_marks, как PUT (at не меняется);
  7) вердикт — app/day_report.py; жизни не меняются (Ш1);
  8) INSERT idempotency_keys: day_done (result_ref = verdict) и day_report (result_ref,
     params_hash) — без ON CONFLICT: под замком дубля нет, а если будет — ошибка БД → 503;
  8а) INSERT idempotency_keys day_queue:{pid}:{dsa(next_started)} (kind day_queue) — тоже без
     ON CONFLICT, как day_done: конфликт → IntegrityError → rollback → 503;
  9) INSERT participant_events kind day_report_submitted, payload {day_started_at (dsa),
     verdict, stage_no, module_no, day_no, next_stage_no, next_module_no, next_day_no,
     next_day_started_at = dsa(next_started)}, actor participant. passed → day_no + 1, если
     такой день есть в контенте, иначе та же позиция; not_passed / all_not_done → та же.
     next_started = now; если active_from(now) ≤ now (сдача ровно в 04:00) → now + 1 мкс:
     кнопки следующего дня строго позже сдачи (У3);
  10) commit → 200 {verdict, queued: true}. Ответ строится только после успешного commit:
     ошибка БД, в том числе на commit → rollback, 503 (ложного 200 нет, П-31).
  Время — day_clock.utcnow() после замка; время клиента не принимается.
Лог INFO: только tg_user_id и status (для marks — ещё block_id). pid и op_id в лог не идут.
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import day_clock
from app.config import Settings, get_settings
from app.consent_status import (
    STATUS_KINDS,
    ConsentTextMissingError,
    current_texts,
    load_events,
    reasons,
)
from app.day_content import Day, DayContent, get_day_content
from app.day_keys import (
    KIND_DAY_DONE,
    KIND_DAY_ENTER,
    KIND_DAY_QUEUE,
    KIND_DAY_REPORT,
    TTL_BY_KIND,
    dsa,
    key_day_done,
    key_day_enter,
    key_day_queue,
    key_day_report,
)
from app.day_report import VERDICT_PASSED, marks_complete, params_hash, verdict
from app.db.models import ACTOR_SYSTEM, DayMark, IdempotencyKey, ParticipantEvent
from app.db.session import get_db_session
from app.participant_lock import active_pid_locked
from app.participants import find_active_participant
from app.projector import EVENT_KIND_DAY_ENTERED, EVENT_KIND_DAY_REPORT_SUBMITTED
from app.telegram_init_data import InitDataContext, require_init_data

logger = logging.getLogger(__name__)

# Префикс /miniapp/v1, проверка initData и rate-limit — в main.py (роутер miniapp_v1).
router = APIRouter(tags=["day"])

DEFAULT_LIVES = 3  # DEFAULT колонки participant_state.lives

STATUS_NOT_STARTED = "not_started"
STATUS_ENTERING = "entering"
STATUS_OPEN = "open"
STATUS_SUBMITTED = "submitted"
STATUS_QUEUED = "queued"
STATUS_CLOSED = "closed"
ENTER_ALREADY = "already"

MARK_DONE = "done"
MARK_NOT_DONE = "not_done"

CLIENT_OP_ID_HEADER = "X-Client-Op-Id"
ACTOR_PARTICIPANT = "participant"
MAX_REPORT_MARKS = 64  # верхняя граница длины marks (защита от огромного тела)

# Тестовый вход — всегда день 1 этапа 1 модуля 1 (В3 — А).
TEST_ENTRY_PAYLOAD: dict[str, Any] = {
    "stage_no": 1,
    "module_no": 1,
    "day_no": 1,
    "source": "test_flag",
}

DayStatus = Literal["not_started", "entering", "open", "submitted", "queued", "closed"]
Mark = Literal["done", "not_done"]
Verdict = Literal["passed", "not_passed", "all_not_done"]

# Только SELECT: participant_state пишет проектор (E1).
_STATE_SQL = text(
    "SELECT lives, stage_no, module_no, day_no, day_started_at, tz "
    "FROM participant_state WHERE pid = :pid"
)

# Ключ day_enter (test-enter). Ключи не обновляются и не удаляются (day_keys.py).
_INSERT_KEY_SQL = text(
    "INSERT INTO idempotency_keys (key, kind, ttl) "
    "VALUES (:key, :kind, CAST(:ttl AS interval)) ON CONFLICT DO NOTHING"
)

# report/submit: ключи day_done, day_report, day_queue. Без ON CONFLICT: дубль → ошибка БД → 503
# (П-31).
_INSERT_RESULT_KEY_SQL = text(
    "INSERT INTO idempotency_keys (key, kind, ttl, result_ref, params_hash) "
    "VALUES (:key, :kind, CAST(:ttl AS interval), :result_ref, :params_hash)"
)


class PositionOut(BaseModel):
    stage_no: int
    module_no: int
    day_no: int


class BlockOut(BaseModel):
    block_id: str
    title_key: str
    help_key: str
    critical: bool
    mark: Mark | None


class DayCurrentOut(BaseModel):
    status: DayStatus
    lives: int
    test_entry: bool
    position: PositionOut | None = None
    day_started_at: datetime | None = None
    blocks: list[BlockOut] | None = None
    min_optional: int | None = None
    can_submit: bool | None = None
    # life-ops-b: только при позиции (exclude_unset — в ветках без позиции не задаются).
    active_from: datetime | None = None
    deadline_at: datetime | None = None
    queued_until: datetime | None = None
    buttons_active: bool | None = None


class TestEnterOut(BaseModel):
    status: Literal["already", "entering"]


class DayMarkIn(BaseModel):
    # Лишние поля (pid, day_started_at, …) игнорируются: pydantic по умолчанию extra="ignore".
    block_id: str = Field(pattern=r"^[a-z0-9_]{1,32}$")
    value: Mark


class DayMarkOut(BaseModel):
    block_id: str
    value: Mark


class DayReportIn(BaseModel):
    # Лишние поля (pid, day_started_at, …) игнорируются (extra="ignore").
    marks: list[DayMarkIn] = Field(max_length=MAX_REPORT_MARKS)


class DayReportOut(BaseModel):
    verdict: Verdict
    queued: bool


class DayContentMissing(Exception):
    def __init__(self, stage_no: int, module_no: int, day_no: int) -> None:
        super().__init__(f"stage={stage_no} module={module_no} day={day_no}")
        self.stage_no = stage_no
        self.module_no = module_no
        self.day_no = day_no


def _error(
    status_code: int, code: str, message: str, headers: dict[str, str] | None = None
) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message}, headers=headers
    )


def _participant_not_found() -> HTTPException:
    return _error(
        status.HTTP_404_NOT_FOUND,
        "PARTICIPANT_NOT_FOUND",
        "Участник не найден. Пройдите онбординг.",
    )


def _service_unavailable() -> HTTPException:
    return _error(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "SERVICE_UNAVAILABLE",
        "Сервис временно недоступен. Попробуйте позже.",
    )


def _flag_off() -> HTTPException:
    return _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Не найдено.")


def _day_not_started() -> HTTPException:
    return _error(status.HTTP_409_CONFLICT, "DAY_NOT_STARTED", "День ещё не начат.")


def _day_already_submitted() -> HTTPException:
    return _error(
        status.HTTP_409_CONFLICT, "DAY_ALREADY_SUBMITTED", "Отчёт за день уже отправлен."
    )


def _window_error(win: str) -> HTTPException | None:
    """409 по окну дня (life-ops-b) или None, если окно open."""
    if win == day_clock.WINDOW_NOT_ACTIVE:
        return _error(
            status.HTTP_409_CONFLICT, "DAY_NOT_ACTIVE", "Кнопки дня станут активны в 04:00."
        )
    if win == day_clock.WINDOW_CLOSED:
        return _error(
            status.HTTP_409_CONFLICT, "DAY_CLOSED", "День закрыт: отчёт принимался до 00:00."
        )
    return None


def _utc(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc)


def next_day_started(now: datetime, tz: str | None) -> datetime:
    """day_started_at следующего дня: now, но кнопки (active_from) строго позже now (У3)."""
    if _utc(day_clock.active_from(now, tz)) <= _utc(now):
        return now + timedelta(microseconds=1)
    return now


def next_position(content: DayContent, row: Any, result: str) -> tuple[int, int, int]:
    """passed → day_no + 1, если такой день есть в контенте; иначе та же позиция (ЛО-3)."""
    if result == VERDICT_PASSED and content.get(row.stage_no, row.module_no, row.day_no + 1):
        return row.stage_no, row.module_no, row.day_no + 1
    return row.stage_no, row.module_no, row.day_no


def _content_missing(exc: DayContentMissing, where: str) -> HTTPException:
    logger.error(
        "%s: нет контента дня stage=%s module=%s day=%s — 503",
        where,
        exc.stage_no,
        exc.module_no,
        exc.day_no,
    )
    return _error(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "DAY_CONTENT_MISSING",
        "День временно недоступен. Попробуйте позже.",
    )


def _rollback(session: Session) -> None:
    with suppress(Exception):
        session.rollback()


def _released(session: Session, exc: Exception) -> Exception:
    """rollback (снимает xact-замок) и вернуть exc для raise."""
    _rollback(session)
    return exc


def build_blocks(day: Day, marks: Mapping[str, bool]) -> list[BlockOut]:
    """Блоки дня + отметки. Отметки чужих block_id игнорируются. Чистая функция."""
    out: list[BlockOut] = []
    for block in day.blocks:
        value = marks.get(block.block_id)
        mark: Mark | None
        if value is None:
            mark = None
        else:
            mark = MARK_DONE if value else MARK_NOT_DONE
        out.append(
            BlockOut(
                block_id=block.block_id,
                title_key=block.title_key,
                help_key=block.help_key,
                critical=block.critical,
                mark=mark,
            )
        )
    return out


def _has_key(session: Session, key: str) -> bool:
    found = session.execute(
        select(IdempotencyKey.key).where(IdempotencyKey.key == key)
    ).first()
    return found is not None


def insert_idempotency_key(session: Session, key: str, kind: str) -> None:
    """Ключ дня (day_keys.py). COMMIT здесь нет: транзакцией владеет вызывающий."""
    session.execute(_INSERT_KEY_SQL, {"key": key, "kind": kind, "ttl": TTL_BY_KIND[kind]})


def _insert_result_key(
    session: Session, key: str, kind: str, result_ref: str | None, p_hash: str | None
) -> None:
    session.execute(
        _INSERT_RESULT_KEY_SQL,
        {
            "key": key,
            "kind": kind,
            "ttl": TTL_BY_KIND[kind],
            "result_ref": result_ref,
            "params_hash": p_hash,
        },
    )


def _upsert_mark(
    session: Session, pid: uuid.UUID, started: datetime, block_id: str, done: bool
) -> None:
    """INSERT day_marks ON CONFLICT DO UPDATE SET value; at не обновляется (В19)."""
    stmt = pg_insert(DayMark.__table__).values(
        pid=pid,
        day_started_at=started,
        block_id=block_id,
        value=done,
        at=func.now(),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["pid", "day_started_at", "block_id"],
        set_={"value": stmt.excluded.value},
    )
    session.execute(stmt)


def _marks(session: Session, pid: uuid.UUID, started: datetime) -> dict[str, bool]:
    rows = session.execute(
        select(DayMark.block_id, DayMark.value).where(
            DayMark.pid == pid, DayMark.day_started_at == started
        )
    ).all()
    return {row.block_id: row.value for row in rows}


def _has_position(row: Any) -> bool:
    return not (row.day_no is None or row.stage_no is None or row.module_no is None)


def read_day_current(
    session: Session,
    tg_user_id: int,
    content: DayContent,
    test_entry_enabled: bool = False,
) -> DayCurrentOut | None:
    """None — нет активного участника. DayContentMissing — позиция без контента."""
    now = day_clock.utcnow()  # один раз за запрос (У1)
    found = find_active_participant(session, tg_user_id)
    if found is None:
        return None
    pid = found[0]

    row = session.execute(_STATE_SQL, {"pid": pid}).first()
    if row is None:
        return DayCurrentOut(
            status=STATUS_NOT_STARTED, lives=DEFAULT_LIVES, test_entry=test_entry_enabled
        )
    lives = DEFAULT_LIVES if row.lives is None else row.lives

    if not _has_position(row):
        day_status = STATUS_ENTERING if _has_key(session, key_day_enter(pid)) else STATUS_NOT_STARTED
        return DayCurrentOut(status=day_status, lives=lives, test_entry=test_entry_enabled)

    day = content.get(row.stage_no, row.module_no, row.day_no)
    if day is None:
        raise DayContentMissing(row.stage_no, row.module_no, row.day_no)

    started = row.day_started_at
    tz = row.tz
    active_from: datetime | None = None
    deadline_at: datetime | None = None
    win: str | None = None
    queued_until: datetime | None = None
    if started is None:
        marks: dict[str, bool] = {}
        submitted = False
    else:
        marks = _marks(session, pid, started)
        submitted = _has_key(session, key_day_done(pid, started))
        active_from = day_clock.active_from(started, tz)
        deadline_at = day_clock.deadline_at(started, tz)
        win = day_clock.window(started, tz, now)
        if not submitted and _has_key(session, key_day_queue(pid, started)):
            until = day_clock.queue_until(pid, started)
            if _utc(now) < _utc(until):
                queued_until = until.astimezone(day_clock.zone(tz))

    if queued_until is not None:
        return DayCurrentOut(
            status=STATUS_QUEUED,
            lives=lives,
            test_entry=False,
            position=None,
            day_started_at=started,
            blocks=None,
            min_optional=None,
            can_submit=False,
            active_from=active_from,
            deadline_at=deadline_at,
            queued_until=queued_until,
            buttons_active=False,
        )

    blocks = build_blocks(day, marks)
    if submitted:
        day_status = STATUS_SUBMITTED
    elif win == day_clock.WINDOW_CLOSED:
        day_status = STATUS_CLOSED
    else:
        day_status = STATUS_OPEN
    window_open = win == day_clock.WINDOW_OPEN
    can_submit = (
        day_status == STATUS_OPEN and all(b.mark is not None for b in blocks) and window_open
    )
    return DayCurrentOut(
        status=day_status,
        lives=lives,
        test_entry=False,
        position=PositionOut(
            stage_no=row.stage_no, module_no=row.module_no, day_no=row.day_no
        ),
        day_started_at=started,
        blocks=blocks,
        min_optional=day.min_optional,
        can_submit=can_submit,
        active_from=active_from,
        deadline_at=deadline_at,
        queued_until=None,
        buttons_active=window_open and not submitted,  # Р1: после сдачи кнопки неактивны
    )


def enter_day_by_test_flag(
    session: Session,
    tg_user_id: int,
    enabled: bool,
    content: DayContent | None = None,
) -> TestEnterOut:
    """Шаги 1–8 POST /day/test-enter. Ошибки — HTTPException / DayContentMissing.

    commit только на шаге 8; во всех остальных выходах после замка — rollback.
    content не передан → get_day_content().
    """
    if not enabled:
        # До любых запросов к БД (В3 — А).
        raise _flag_off()
    pid = active_pid_locked(session, tg_user_id)
    if pid is None:
        raise _released(session, _participant_not_found())
    try:
        texts = current_texts(session, STATUS_KINDS)
    except ConsentTextMissingError as exc:
        raise _released(session, exc)
    if reasons(load_events(session, pid), texts, STATUS_KINDS):
        raise _released(
            session,
            _error(
                status.HTTP_409_CONFLICT,
                "RECONSENT_REQUIRED",
                "Нужно заново подтвердить согласия.",
            ),
        )
    row = session.execute(_STATE_SQL, {"pid": pid}).first()
    if row is None:
        raise _released(
            session,
            _error(
                status.HTTP_409_CONFLICT,
                "DAY_STATE_SYNCING",
                "Данные обновляются. Повторите через секунду.",
                headers={"Retry-After": "1"},
            ),
        )
    if _has_position(row):
        _rollback(session)
        return TestEnterOut(status=ENTER_ALREADY)
    enter_key = key_day_enter(pid)
    if _has_key(session, enter_key):
        _rollback(session)
        return TestEnterOut(status=STATUS_ENTERING)
    stage_no = TEST_ENTRY_PAYLOAD["stage_no"]
    module_no = TEST_ENTRY_PAYLOAD["module_no"]
    day_no = TEST_ENTRY_PAYLOAD["day_no"]
    day_content = content if content is not None else get_day_content()
    if day_content.get(stage_no, module_no, day_no) is None:
        raise _released(session, DayContentMissing(stage_no, module_no, day_no))
    insert_idempotency_key(session, enter_key, KIND_DAY_ENTER)
    session.execute(
        ParticipantEvent.__table__.insert().values(
            pid=pid,
            kind=EVENT_KIND_DAY_ENTERED,
            payload=dict(TEST_ENTRY_PAYLOAD),
            actor=ACTOR_SYSTEM,
            actor_role=ACTOR_SYSTEM,
        )
    )
    session.commit()
    return TestEnterOut(status=STATUS_ENTERING)


def put_day_mark(
    session: Session, tg_user_id: int, body: DayMarkIn, content: DayContent
) -> DayMarkOut:
    """PUT /day/marks. pid и day_started_at — только с сервера.

    commit — в конце; во всех выходах с ошибкой после замка — rollback.
    """
    pid = active_pid_locked(session, tg_user_id)
    if pid is None:
        raise _released(session, _participant_not_found())
    now = day_clock.utcnow()  # после замка (У1)
    row = session.execute(_STATE_SQL, {"pid": pid}).first()
    if row is None or not _has_position(row) or row.day_started_at is None:
        raise _released(session, _day_not_started())
    window_error = _window_error(day_clock.window(row.day_started_at, row.tz, now))
    if window_error is not None:
        raise _released(session, window_error)
    day = content.get(row.stage_no, row.module_no, row.day_no)
    if day is None:
        raise _released(session, DayContentMissing(row.stage_no, row.module_no, row.day_no))
    if body.block_id not in {block.block_id for block in day.blocks}:
        raise _released(
            session,
            _error(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "BLOCK_NOT_IN_DAY",
                "Такого блока нет в текущем дне.",
            ),
        )
    started = row.day_started_at
    if _has_key(session, key_day_done(pid, started)):
        raise _released(session, _day_already_submitted())
    _upsert_mark(session, pid, started, body.block_id, body.value == MARK_DONE)
    session.commit()
    return DayMarkOut(block_id=body.block_id, value=body.value)


def submit_day_report(
    session: Session,
    tg_user_id: int,
    op_id: uuid.UUID,
    body: DayReportIn,
    content: DayContent,
) -> DayReportOut:
    """Шаги 1–10 POST /day/report/submit. Ошибки — HTTPException / DayContentMissing /
    SQLAlchemyError (вызывающий → 503). commit — только на шаге 10, ответ — после него.
    """
    pid = active_pid_locked(session, tg_user_id)
    if pid is None:
        raise _released(session, _participant_not_found())
    now = day_clock.utcnow()  # после замка (У1)

    pairs = [(mark.block_id, mark.value) for mark in body.marks]
    p_hash = params_hash(pairs)
    report_key = key_day_report(pid, str(op_id))
    previous = session.execute(
        select(IdempotencyKey.result_ref, IdempotencyKey.params_hash).where(
            IdempotencyKey.key == report_key
        )
    ).first()
    if previous is not None:
        if previous.params_hash == p_hash:
            _rollback(session)
            return DayReportOut(verdict=previous.result_ref, queued=True)
        raise _released(
            session,
            _error(
                status.HTTP_409_CONFLICT,
                "IDEMPOTENCY_CONFLICT",
                "Этот X-Client-Op-Id уже использован с другим отчётом.",
            ),
        )

    row = session.execute(_STATE_SQL, {"pid": pid}).first()
    if row is None or not _has_position(row) or row.day_started_at is None:
        raise _released(session, _day_not_started())
    day = content.get(row.stage_no, row.module_no, row.day_no)
    if day is None:
        raise _released(session, DayContentMissing(row.stage_no, row.module_no, row.day_no))
    window_error = _window_error(day_clock.window(row.day_started_at, row.tz, now))
    if window_error is not None:
        raise _released(session, window_error)
    if not marks_complete(day, [block_id for block_id, _ in pairs]):
        raise _released(
            session,
            _error(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "MARKS_INCOMPLETE",
                "Отметьте каждый блок дня ровно один раз.",
            ),
        )
    started = row.day_started_at
    done_key = key_day_done(pid, started)
    if _has_key(session, done_key):
        raise _released(session, _day_already_submitted())

    done = {block_id: value == MARK_DONE for block_id, value in pairs}
    for block_id, is_done in done.items():
        _upsert_mark(session, pid, started, block_id, is_done)
    result = verdict(day, done)
    _insert_result_key(session, done_key, KIND_DAY_DONE, result, None)
    _insert_result_key(session, report_key, KIND_DAY_REPORT, result, p_hash)
    # Один и тот же next_started — в ключ очереди и в payload (У4).
    next_started = next_day_started(now, row.tz)
    next_stage_no, next_module_no, next_day_no = next_position(content, row, result)
    _insert_result_key(session, key_day_queue(pid, next_started), KIND_DAY_QUEUE, None, None)
    session.execute(
        ParticipantEvent.__table__.insert().values(
            pid=pid,
            kind=EVENT_KIND_DAY_REPORT_SUBMITTED,
            payload={
                "day_started_at": dsa(started),
                "verdict": result,
                "stage_no": row.stage_no,
                "module_no": row.module_no,
                "day_no": row.day_no,
                "next_stage_no": next_stage_no,
                "next_module_no": next_module_no,
                "next_day_no": next_day_no,
                "next_day_started_at": dsa(next_started),
            },
            actor=ACTOR_PARTICIPANT,
            actor_role=ACTOR_PARTICIPANT,
        )
    )
    session.commit()  # П-31: зачёт — только после подтверждённой записи
    return DayReportOut(verdict=result, queued=True)


@router.get(
    "/day/current",
    response_model=DayCurrentOut,
    response_model_exclude_unset=True,
    responses={
        401: {"description": "initData невалидна / истекла (TG_INIT_MISSING / TG_INIT_INVALID)"},
        404: {"description": "PARTICIPANT_NOT_FOUND — нет активного участника"},
        503: {"description": "SERVICE_UNAVAILABLE — ошибка БД; DAY_CONTENT_MISSING"},
    },
)
def get_day_current(
    ctx: InitDataContext = Depends(require_init_data),
    session: Session = Depends(get_db_session),
    content: DayContent = Depends(get_day_content),
    settings: Settings = Depends(get_settings),
) -> DayCurrentOut:
    try:
        result = read_day_current(
            session, ctx.tg_user_id, content, settings.day_test_entry_enabled
        )
    except DayContentMissing as exc:
        raise _content_missing(exc, "day/current") from None
    except SQLAlchemyError as exc:
        logger.error("day/current: ошибка БД (%s) — 503", type(exc).__name__)
        raise _service_unavailable() from None
    finally:
        # Только чтение: транзакцию закрываем до ответа.
        _rollback(session)
    if result is None:
        logger.info("day/current: tg_user_id=%s status=participant_not_found", ctx.tg_user_id)
        raise _participant_not_found()
    logger.info("day/current: tg_user_id=%s status=%s", ctx.tg_user_id, result.status)
    return result


@router.post(
    "/day/test-enter",
    response_model=TestEnterOut,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        200: {"description": "already — позиция уже есть"},
        404: {"description": "NOT_FOUND (флаг выключен) / PARTICIPANT_NOT_FOUND"},
        409: {"description": "RECONSENT_REQUIRED / DAY_STATE_SYNCING (Retry-After: 1)"},
        503: {"description": "SERVICE_UNAVAILABLE / SERVICE_MISCONFIGURED / DAY_CONTENT_MISSING"},
    },
)
def post_day_test_enter(
    response: Response,
    ctx: InitDataContext = Depends(require_init_data),
    session: Session = Depends(get_db_session),
    content: DayContent = Depends(get_day_content),
    settings: Settings = Depends(get_settings),
) -> TestEnterOut:
    if not settings.day_test_entry_enabled:
        # Д2: до try — к сессии не обращаемся вовсе (даже rollback).
        logger.info("day/test-enter: tg_user_id=%s status=404", ctx.tg_user_id)
        raise _flag_off()
    try:
        result = enter_day_by_test_flag(session, ctx.tg_user_id, True, content)
    except HTTPException as exc:
        _rollback(session)
        logger.info("day/test-enter: tg_user_id=%s status=%s", ctx.tg_user_id, exc.status_code)
        raise
    except ConsentTextMissingError as exc:
        _rollback(session)
        logger.error("day/test-enter: нет текста согласия keys=%s (503)", ",".join(exc.keys))
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "SERVICE_MISCONFIGURED",
            "Сервис временно недоступен",
        ) from None
    except DayContentMissing as exc:
        _rollback(session)
        raise _content_missing(exc, "day/test-enter") from None
    except SQLAlchemyError as exc:
        _rollback(session)
        logger.error("day/test-enter: ошибка БД (%s) — 503", type(exc).__name__)
        raise _service_unavailable() from None
    if result.status == ENTER_ALREADY:
        response.status_code = status.HTTP_200_OK
    logger.info("day/test-enter: tg_user_id=%s status=%s", ctx.tg_user_id, result.status)
    return result


@router.put(
    "/day/marks",
    response_model=DayMarkOut,
    responses={
        404: {"description": "PARTICIPANT_NOT_FOUND"},
        409: {
            "description": "DAY_NOT_STARTED / DAY_NOT_ACTIVE / DAY_CLOSED / DAY_ALREADY_SUBMITTED"
        },
        422: {"description": "BLOCK_NOT_IN_DAY / невалидное тело"},
        503: {"description": "SERVICE_UNAVAILABLE — ошибка БД; DAY_CONTENT_MISSING"},
    },
)
def put_day_marks(
    body: DayMarkIn,
    ctx: InitDataContext = Depends(require_init_data),
    session: Session = Depends(get_db_session),
    content: DayContent = Depends(get_day_content),
) -> DayMarkOut:
    try:
        result = put_day_mark(session, ctx.tg_user_id, body, content)
    except HTTPException as exc:
        _rollback(session)
        logger.info("day/marks: tg_user_id=%s status=%s", ctx.tg_user_id, exc.status_code)
        raise
    except DayContentMissing as exc:
        _rollback(session)
        raise _content_missing(exc, "day/marks") from None
    except SQLAlchemyError as exc:
        _rollback(session)
        logger.error("day/marks: ошибка БД (%s) — 503", type(exc).__name__)
        raise _service_unavailable() from None
    logger.info(
        "day/marks: tg_user_id=%s status=ok block_id=%s", ctx.tg_user_id, result.block_id
    )
    return result


@router.post(
    "/day/report/submit",
    response_model=DayReportOut,
    responses={
        404: {"description": "PARTICIPANT_NOT_FOUND"},
        409: {
            "description": "IDEMPOTENCY_CONFLICT / DAY_NOT_STARTED / DAY_NOT_ACTIVE / "
            "DAY_CLOSED / DAY_ALREADY_SUBMITTED"
        },
        422: {"description": "MARKS_INCOMPLETE / нет или неверный X-Client-Op-Id / тело"},
        503: {"description": "SERVICE_UNAVAILABLE — ошибка БД (в т. ч. commit); DAY_CONTENT_MISSING"},
    },
)
def post_day_report_submit(
    body: DayReportIn,
    client_op_id: uuid.UUID = Header(alias=CLIENT_OP_ID_HEADER),
    ctx: InitDataContext = Depends(require_init_data),
    session: Session = Depends(get_db_session),
    content: DayContent = Depends(get_day_content),
) -> DayReportOut:
    try:
        result = submit_day_report(session, ctx.tg_user_id, client_op_id, body, content)
    except HTTPException as exc:
        _rollback(session)
        logger.info("day/report/submit: tg_user_id=%s status=%s", ctx.tg_user_id, exc.status_code)
        raise
    except DayContentMissing as exc:
        _rollback(session)
        raise _content_missing(exc, "day/report/submit") from None
    except SQLAlchemyError as exc:
        _rollback(session)
        logger.error("day/report/submit: ошибка БД (%s) — 503", type(exc).__name__)
        raise _service_unavailable() from None
    logger.info(
        "day/report/submit: tg_user_id=%s status=ok verdict=%s", ctx.tg_user_id, result.verdict
    )
    return result
