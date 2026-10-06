"""/miniapp/v1/consents — чтение своих согласий (1e-2, B-2).

Контракт: build/miniapp-api-contract.yaml → GET /miniapp/v1/consents
  200: [Consent {id, given_at, revoked_at, legal_status}]
  401: initData невалидна / истекла (require_init_data, роутер miniapp_v1 в main.py)
Вне контракта: 503 SERVICE_UNAVAILABLE — БД недоступна (как first-launch, D-12).

Правила:
  - pid — ТОЛЬКО по tg_user_id из проверенной initData, активная строка tg_user_registry
    (tombstoned_at IS NULL; app.participants.find_active_participant, returning-1).
    Параметров запроса нет: чужие согласия запросить нельзя
    (изоляция между пользователями, карточка 1e-2 §14);
  - нет участника → 200 [];
  - по каждому kind решает ПОСЛЕДНЕЕ событие (D-15 а): последнее give → revoked_at = null;
    последнее revoke → revoked_at = время отзыва; given_at — время последнего give;
    kind без единого give в ответ не попадает;
  - legal_status — из text_registry по text_key последнего give;
  - только чтение: здесь ничего не пишется (согласия пишет first-launch).
Лог: только tg_user_id и число согласий в ответе. Тексты согласий — никогда.
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.orm import Session

from app.db.models import (
    CONSENT_ACTION_GIVE,
    CONSENT_ACTION_REVOKE,
    ConsentEvent,
    TextRegistry,
)
from app.db.session import get_db_session
from app.participants import find_active_participant
from app.telegram_init_data import InitDataContext, require_init_data

logger = logging.getLogger(__name__)

# Префикс /miniapp/v1, проверка initData и rate-limit — в main.py (роутер miniapp_v1).
router = APIRouter(tags=["consents"])


class ConsentOut(BaseModel):
    id: str
    given_at: datetime
    revoked_at: datetime | None
    legal_status: str


@dataclass(frozen=True)
class EventRow:
    kind: str
    action: str
    at: datetime
    text_key: str


@dataclass(frozen=True)
class FoldedConsent:
    kind: str
    given_at: datetime
    revoked_at: datetime | None
    text_key: str


def fold_events(events: Sequence[EventRow]) -> list[FoldedConsent]:
    """События одного pid в порядке времени → состояние каждого kind (последнее событие).

    Чистая функция: тестируется без БД.
    """
    given: dict[str, tuple[datetime, str]] = {}
    revoked: dict[str, datetime | None] = {}
    for event in events:
        if event.action == CONSENT_ACTION_GIVE:
            given[event.kind] = (event.at, event.text_key)
            revoked[event.kind] = None
        elif event.action == CONSENT_ACTION_REVOKE:
            revoked[event.kind] = event.at
    return [
        FoldedConsent(
            kind=kind,
            given_at=given[kind][0],
            revoked_at=revoked.get(kind),
            text_key=given[kind][1],
        )
        for kind in sorted(given)
    ]


def _active_pid(session: Session, tg_user_id: int) -> uuid.UUID | None:
    found = find_active_participant(session, tg_user_id)
    if found is None:
        return None
    return found[0]


def read_consents(session: Session, tg_user_id: int) -> list[ConsentOut]:
    pid = _active_pid(session, tg_user_id)
    if pid is None:
        return []
    rows = session.execute(
        select(ConsentEvent.kind, ConsentEvent.action, ConsentEvent.at, ConsentEvent.text_key)
        .where(ConsentEvent.pid == pid)
        .order_by(ConsentEvent.at, ConsentEvent.id)
    ).all()
    folded = fold_events(
        [EventRow(kind=r.kind, action=r.action, at=r.at, text_key=r.text_key) for r in rows]
    )
    if not folded:
        return []
    keys = sorted({item.text_key for item in folded})
    statuses = {
        row.key: row.legal_status
        for row in session.execute(
            select(TextRegistry.key, TextRegistry.legal_status).where(TextRegistry.key.in_(keys))
        ).all()
    }
    # text_key — FK на text_registry (0004): статус есть у каждого события.
    return [
        ConsentOut(
            id=item.kind,
            given_at=item.given_at,
            revoked_at=item.revoked_at,
            legal_status=statuses[item.text_key],
        )
        for item in folded
    ]


@router.get(
    "/consents",
    response_model=list[ConsentOut],
    responses={
        401: {"description": "initData невалидна / истекла (TG_INIT_MISSING / TG_INIT_INVALID)"},
        503: {"description": "SERVICE_UNAVAILABLE — БД недоступна"},
    },
)
def get_consents(
    ctx: InitDataContext = Depends(require_init_data),
    session: Session = Depends(get_db_session),
) -> list[ConsentOut]:
    try:
        result = read_consents(session, ctx.tg_user_id)
    except (OperationalError, InterfaceError) as exc:
        logger.error("consents: БД недоступна (%s) — 503", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "SERVICE_UNAVAILABLE",
                "message": "Сервис временно недоступен. Попробуйте позже.",
            },
        ) from None
    logger.info("consents: tg_user_id=%s count=%d", ctx.tg_user_id, len(result))
    return result
