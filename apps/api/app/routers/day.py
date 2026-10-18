"""/miniapp/v1/day/current — текущий день участника (iter2-api-1), только чтение.

initData и rate-limit — роутер miniapp_v1 в main.py.
Правила:
  - pid — ТОЛЬКО по tg_user_id из проверенной initData (find_active_participant);
    параметров запроса нет; нет активного pid (или tombstoned) → 404 PARTICIPANT_NOT_FOUND;
  - participant_state читается text-SQL SELECT (lives, stage_no, module_no, day_no,
    day_started_at). Это только чтение: писатель participant_state — проектор (E1/INV-1);
  - нет строки state → not_started, lives 3 (DEFAULT колонки);
  - позиции нет (day_no NULL) → entering, если есть ключ day_enter, иначе not_started;
  - позиция есть → open или submitted (есть ключ day_done по текущему day_started_at);
  - отметки — из day_marks только по pid и текущему day_started_at (true → done,
    false → not_done, нет строки → null);
  - can_submit = все блоки отмечены и статус open; test_entry пока всегда false (iter2-api-2a);
  - позиция есть, а контента дня нет → 503 DAY_CONTENT_MISSING, в лог ERROR
    (stage, module, day; без pid);
  - БД недоступна → 503 SERVICE_UNAVAILABLE (как consents.py).
Здесь ничего не пишется: ни participant_state, ни day_marks, ни idempotency_keys.
Лог INFO: только tg_user_id и status.
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.orm import Session

from app.day_content import Day, DayContent, get_day_content
from app.day_keys import key_day_done, key_day_enter
from app.db.models import DayMark, IdempotencyKey
from app.db.session import get_db_session
from app.participants import find_active_participant
from app.telegram_init_data import InitDataContext, require_init_data

logger = logging.getLogger(__name__)

# Префикс /miniapp/v1, проверка initData и rate-limit — в main.py (роутер miniapp_v1).
router = APIRouter(tags=["day"])

DEFAULT_LIVES = 3  # DEFAULT колонки participant_state.lives

STATUS_NOT_STARTED = "not_started"
STATUS_ENTERING = "entering"
STATUS_OPEN = "open"
STATUS_SUBMITTED = "submitted"

MARK_DONE = "done"
MARK_NOT_DONE = "not_done"

DayStatus = Literal["not_started", "entering", "open", "submitted"]
Mark = Literal["done", "not_done"]

# Только SELECT: participant_state пишет проектор (E1).
_STATE_SQL = text(
    "SELECT lives, stage_no, module_no, day_no, day_started_at "
    "FROM participant_state WHERE pid = :pid"
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


class DayContentMissing(Exception):
    def __init__(self, stage_no: int, module_no: int, day_no: int) -> None:
        super().__init__(f"stage={stage_no} module={module_no} day={day_no}")
        self.stage_no = stage_no
        self.module_no = module_no
        self.day_no = day_no


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


def _marks(session: Session, pid: uuid.UUID, started: datetime) -> dict[str, bool]:
    rows = session.execute(
        select(DayMark.block_id, DayMark.value).where(
            DayMark.pid == pid, DayMark.day_started_at == started
        )
    ).all()
    return {row.block_id: row.value for row in rows}


def read_day_current(
    session: Session, tg_user_id: int, content: DayContent
) -> DayCurrentOut | None:
    """None — нет активного участника. DayContentMissing — позиция без контента."""
    found = find_active_participant(session, tg_user_id)
    if found is None:
        return None
    pid = found[0]

    row = session.execute(_STATE_SQL, {"pid": pid}).first()
    if row is None:
        return DayCurrentOut(status=STATUS_NOT_STARTED, lives=DEFAULT_LIVES, test_entry=False)
    lives = DEFAULT_LIVES if row.lives is None else row.lives

    if row.day_no is None or row.stage_no is None or row.module_no is None:
        day_status = STATUS_ENTERING if _has_key(session, key_day_enter(pid)) else STATUS_NOT_STARTED
        return DayCurrentOut(status=day_status, lives=lives, test_entry=False)

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
) -> DayCurrentOut:
    try:
        result = read_day_current(session, ctx.tg_user_id, content)
    except DayContentMissing as exc:
        logger.error(
            "day/current: нет контента дня stage=%s module=%s day=%s — 503",
            exc.stage_no,
            exc.module_no,
            exc.day_no,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "DAY_CONTENT_MISSING",
                "message": "День временно недоступен. Попробуйте позже.",
            },
        ) from None
    except (OperationalError, InterfaceError) as exc:
        logger.error("day/current: БД недоступна (%s) — 503", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "SERVICE_UNAVAILABLE",
                "message": "Сервис временно недоступен. Попробуйте позже.",
            },
        ) from None
    if result is None:
        logger.info("day/current: tg_user_id=%s status=participant_not_found", ctx.tg_user_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "PARTICIPANT_NOT_FOUND",
                "message": "Участник не найден. Пройдите онбординг.",
            },
        )
    logger.info("day/current: tg_user_id=%s status=%s", ctx.tg_user_id, result.status)
    return result
