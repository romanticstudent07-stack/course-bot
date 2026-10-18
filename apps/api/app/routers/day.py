"""/miniapp/v1/day/* — день участника (iter2-api-1: GET current; iter2-api-2a: test-enter, marks).

initData и rate-limit — роутер miniapp_v1 в main.py.
Общие правила:
  - pid — ТОЛЬКО по tg_user_id из проверенной initData (find_active_participant);
    pid и day_started_at из тела запроса не берутся никогда (лишние поля игнорируются);
  - participant_state читается text-SQL SELECT (lives, stage_no, module_no, day_no,
    day_started_at). Это только чтение: писатель participant_state — проектор (E1/INV-1);
  - БД недоступна → 503 SERVICE_UNAVAILABLE (как consents.py).

GET /day/current — только чтение, ничего не пишет:
  - нет активного pid (или tombstoned) → 404 PARTICIPANT_NOT_FOUND;
  - нет строки state → not_started, lives 3 (DEFAULT колонки);
  - позиции нет (day_no NULL) → entering, если есть ключ day_enter, иначе not_started;
  - позиция есть → open или submitted (есть ключ day_done по текущему day_started_at);
  - отметки — из day_marks только по pid и текущему day_started_at (true → done,
    false → not_done, нет строки → null);
  - can_submit = все блоки отмечены и статус open;
  - test_entry = флаг DAY_TEST_ENTRY_ENABLED включён и позиции нет (iter2-api-2a);
  - позиция есть, а контента дня нет → 503 DAY_CONTENT_MISSING, в лог ERROR
    (stage, module, day; без pid).

POST /day/test-enter (iter2-api-2a, В3 — А; тела нет). Писатель событий существующего pid:
замок participant:pid (participant_lock.py) берётся ДО записи и держится до commit.
  1) флаг выключен → 404 NOT_FOUND до любых запросов к БД;
  2) нет активного pid под замком → 404 PARTICIPANT_NOT_FOUND;
  3) C0 или C1 не действует (та же проверка, что GET /onboarding/status) → 409 RECONSENT_REQUIRED;
     нет текста согласия → 503 SERVICE_MISCONFIGURED;
  4) нет строки state → 409 DAY_STATE_SYNCING + Retry-After: 1;
  5) позиция есть → 200 {status: already};
  6) есть ключ day_enter → 202 {status: entering}, без события;
  7) INSERT idempotency_keys (day_enter) → INSERT participant_events kind day_entered,
     payload {stage_no 1, module_no 1, day_no 1, source test_flag}, actor system → commit → 202.
  Фаза участника не меняется (В21): позицию и day_started_at ставит проектор.

PUT /day/marks (iter2-api-2a), тело {block_id ^[a-z0-9_]{1,32}$, value done | not_done}:
  нет активного pid под замком → 404; позиции нет → 409 DAY_NOT_STARTED;
  block_id не из блоков текущего дня → 422 BLOCK_NOT_IN_DAY;
  есть ключ day_done → 409 DAY_ALREADY_SUBMITTED;
  INSERT day_marks (pid и day_started_at — с сервера) ON CONFLICT DO UPDATE SET value:
  at не меняется — время первой отметки блока («пришёл» = min(at), В19) → commit → 200.
Лог INFO: только tg_user_id и status (для marks — ещё block_id). pid в лог не идёт.
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from contextlib import suppress
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.consent_status import (
    STATUS_KINDS,
    ConsentTextMissingError,
    current_texts,
    load_events,
    reasons,
)
from app.day_content import Day, DayContent, get_day_content
from app.day_keys import KIND_DAY_ENTER, TTL_BY_KIND, key_day_done, key_day_enter
from app.db.models import ACTOR_SYSTEM, DayMark, IdempotencyKey, ParticipantEvent
from app.db.session import get_db_session
from app.participant_lock import active_pid_locked
from app.participants import find_active_participant
from app.projector import EVENT_KIND_DAY_ENTERED
from app.telegram_init_data import InitDataContext, require_init_data

logger = logging.getLogger(__name__)

# Префикс /miniapp/v1, проверка initData и rate-limit — в main.py (роутер miniapp_v1).
router = APIRouter(tags=["day"])

DEFAULT_LIVES = 3  # DEFAULT колонки participant_state.lives

STATUS_NOT_STARTED = "not_started"
STATUS_ENTERING = "entering"
STATUS_OPEN = "open"
STATUS_SUBMITTED = "submitted"
ENTER_ALREADY = "already"

MARK_DONE = "done"
MARK_NOT_DONE = "not_done"

# Тестовый вход — всегда день 1 этапа 1 модуля 1 (В3 — А).
TEST_ENTRY_PAYLOAD: dict[str, Any] = {
    "stage_no": 1,
    "module_no": 1,
    "day_no": 1,
    "source": "test_flag",
}

DayStatus = Literal["not_started", "entering", "open", "submitted"]
Mark = Literal["done", "not_done"]

# Только SELECT: participant_state пишет проектор (E1).
_STATE_SQL = text(
    "SELECT lives, stage_no, module_no, day_no, day_started_at "
    "FROM participant_state WHERE pid = :pid"
)

# Ключи не обновляются и не удаляются (day_keys.py); повтор под замком невозможен,
# ON CONFLICT DO NOTHING — страховка.
_INSERT_KEY_SQL = text(
    "INSERT INTO idempotency_keys (key, kind, ttl) "
    "VALUES (:key, :kind, CAST(:ttl AS interval)) ON CONFLICT DO NOTHING"
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


class TestEnterOut(BaseModel):
    status: Literal["already", "entering"]


class DayMarkIn(BaseModel):
    # Лишние поля (pid, day_started_at, …) игнорируются: pydantic по умолчанию extra="ignore".
    block_id: str = Field(pattern=r"^[a-z0-9_]{1,32}$")
    value: Mark


class DayMarkOut(BaseModel):
    block_id: str
    value: Mark


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
    if started is None:
        marks: dict[str, bool] = {}
        submitted = False
    else:
        marks = _marks(session, pid, started)
        submitted = _has_key(session, key_day_done(pid, started))

    blocks = build_blocks(day, marks)
    day_status = STATUS_SUBMITTED if submitted else STATUS_OPEN
    can_submit = day_status == STATUS_OPEN and all(b.mark is not None for b in blocks)
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
    )


def enter_day_by_test_flag(session: Session, tg_user_id: int, enabled: bool) -> TestEnterOut:
    """Шаги 1–8 POST /day/test-enter. Ошибки — HTTPException; commit только на шаге 8."""
    if not enabled:
        # До любых запросов к БД (В3 — А).
        raise _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Не найдено.")
    pid = active_pid_locked(session, tg_user_id)
    if pid is None:
        raise _participant_not_found()
    texts = current_texts(session, STATUS_KINDS)
    if reasons(load_events(session, pid), texts, STATUS_KINDS):
        raise _error(
            status.HTTP_409_CONFLICT,
            "RECONSENT_REQUIRED",
            "Нужно заново подтвердить согласия.",
        )
    row = session.execute(_STATE_SQL, {"pid": pid}).first()
    if row is None:
        raise _error(
            status.HTTP_409_CONFLICT,
            "DAY_STATE_SYNCING",
            "Данные обновляются. Повторите через секунду.",
            headers={"Retry-After": "1"},
        )
    if _has_position(row):
        return TestEnterOut(status=ENTER_ALREADY)
    enter_key = key_day_enter(pid)
    if _has_key(session, enter_key):
        return TestEnterOut(status=STATUS_ENTERING)
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
    """PUT /day/marks. pid и day_started_at — только с сервера. commit — в конце."""
    pid = active_pid_locked(session, tg_user_id)
    if pid is None:
        raise _participant_not_found()
    row = session.execute(_STATE_SQL, {"pid": pid}).first()
    if row is None or not _has_position(row) or row.day_started_at is None:
        raise _error(status.HTTP_409_CONFLICT, "DAY_NOT_STARTED", "День ещё не начат.")
    day = content.get(row.stage_no, row.module_no, row.day_no)
    if day is None:
        raise DayContentMissing(row.stage_no, row.module_no, row.day_no)
    if body.block_id not in {block.block_id for block in day.blocks}:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "BLOCK_NOT_IN_DAY",
            "Такого блока нет в текущем дне.",
        )
    started = row.day_started_at
    if _has_key(session, key_day_done(pid, started)):
        raise _error(
            status.HTTP_409_CONFLICT,
            "DAY_ALREADY_SUBMITTED",
            "Отчёт за день уже отправлен.",
        )
    stmt = pg_insert(DayMark.__table__).values(
        pid=pid,
        day_started_at=started,
        block_id=body.block_id,
        value=body.value == MARK_DONE,
        at=func.now(),
    )
    # at не обновляется: время первой отметки блока (В19).
    stmt = stmt.on_conflict_do_update(
        index_elements=["pid", "day_started_at", "block_id"],
        set_={"value": stmt.excluded.value},
    )
    session.execute(stmt)
    session.commit()
    return DayMarkOut(block_id=body.block_id, value=body.value)


@router.get(
    "/day/current",
    response_model=DayCurrentOut,
    response_model_exclude_unset=True,
    responses={
        401: {"description": "initData невалидна / истекла (TG_INIT_MISSING / TG_INIT_INVALID)"},
        404: {"description": "PARTICIPANT_NOT_FOUND — нет активного участника"},
        503: {"description": "SERVICE_UNAVAILABLE — БД недоступна; DAY_CONTENT_MISSING"},
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
    except (OperationalError, InterfaceError) as exc:
        logger.error("day/current: БД недоступна (%s) — 503", type(exc).__name__)
        raise _service_unavailable() from None
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
        503: {"description": "SERVICE_UNAVAILABLE / SERVICE_MISCONFIGURED"},
    },
)
def post_day_test_enter(
    response: Response,
    ctx: InitDataContext = Depends(require_init_data),
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> TestEnterOut:
    try:
        result = enter_day_by_test_flag(session, ctx.tg_user_id, settings.day_test_entry_enabled)
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
    except (OperationalError, InterfaceError) as exc:
        _rollback(session)
        logger.error("day/test-enter: БД недоступна (%s) — 503", type(exc).__name__)
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
        409: {"description": "DAY_NOT_STARTED / DAY_ALREADY_SUBMITTED"},
        422: {"description": "BLOCK_NOT_IN_DAY / невалидное тело"},
        503: {"description": "SERVICE_UNAVAILABLE — БД недоступна; DAY_CONTENT_MISSING"},
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
    except (OperationalError, InterfaceError) as exc:
        _rollback(session)
        logger.error("day/marks: БД недоступна (%s) — 503", type(exc).__name__)
        raise _service_unavailable() from None
    logger.info(
        "day/marks: tg_user_id=%s status=ok block_id=%s", ctx.tg_user_id, result.block_id
    )
    return result
