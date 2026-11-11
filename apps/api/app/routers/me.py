"""/miniapp/v1/me/* — карточка участника и Карта изменений (api-i3-3).

initData и rate-limit — роутер miniapp_v1 в main.py. Оба GET только читают: замка нет,
согласия не проверяются (как GET /checkup/status); перед ответом — rollback.
pid — только find_active_participant(tg_user_id из initData); нет активного участника
(или tombstoned) → 404 PARTICIPANT_NOT_FOUND. SQLAlchemyError → 503 SERVICE_UNAVAILABLE,
в лог — имя класса.

GET /me/card — свежая из БД (06 §6.1), ключи:
  short_no ("#000123", format_short_no), registered_at (tg_user_registry.created_at),
  tz (participant_state.tz, только если есть строка state И строка onboarding_form, иначе null),
  position {stage_no, module_no, day_no} | null (нет state или хоть один номер NULL),
  lives (нет строки state → 3, DEFAULT колонки, как /day/current),
  measurements {weight_start_kg, weight_current_kg, checkup_completed, zone_start, zone_last}:
  вес — первая и последняя строки kind body, зона — первая и последняя kind checkup
  (порядок created_at, id); checkup_completed — есть kind checkup AND occasion onboarding.

GET /me/change-map — на лету (кэша нет), слои anthro, wellbeing, checkup, functional:
  {layer, metric, baseline: Point | null, recent: [Point]}, Point = {value, at}.
  baseline — первая строка (created_at, затем id; 14 §14.1); recent — до 5 последних после
  baseline, по возрастанию. wellbeing — baseline из onboarding_form, recent []; checkup —
  только зона; functional — нет данных. photo4 нет (Р-3).

Даты — UTC. Балл, ответы Чек-Апа, пол, город не выбираются и не отдаются.
Лог (app.me): INFO только tg_user_id и status — ни pid, ни веса, ни зоны, ни кода самочувствия.
"""
from __future__ import annotations

import logging
import uuid
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.participants import find_active_participant, format_short_no
from app.telegram_init_data import InitDataContext, require_init_data

logger = logging.getLogger("app.me")

# Префикс /miniapp/v1, проверка initData и rate-limit — в main.py (роутер miniapp_v1).
router = APIRouter(tags=["me"])

DEFAULT_LIVES = 3  # DEFAULT колонки participant_state.lives (как day.DEFAULT_LIVES)
RECENT_LIMIT = 5
KIND_BODY = "body"
KIND_CHECKUP = "checkup"
OCCASION_ONBOARDING = "onboarding"

# Только SELECT. checkup_score и checkup_answers не выбираются никогда.
_REGISTRY_SQL = text("SELECT created_at FROM tg_user_registry WHERE pid = :pid")
_STATE_SQL = text(
    "SELECT lives, stage_no, module_no, day_no, tz FROM participant_state WHERE pid = :pid"
)
_FORM_SQL = text("SELECT wellbeing_code, created_at FROM onboarding_form WHERE pid = :pid")
_MEASUREMENTS_SQL = text(
    "SELECT id, kind, occasion, checkup_zone, weight_kg, created_at "
    "FROM measurements_log WHERE pid = :pid ORDER BY created_at, id"
)

Zone = Literal["green", "yellow", "red"]


# ---------------------------- модели ----------------------------


class PositionOut(BaseModel):
    stage_no: int
    module_no: int
    day_no: int


class MeasurementsOut(BaseModel):
    weight_start_kg: float | None
    weight_current_kg: float | None
    checkup_completed: bool
    zone_start: Zone | None
    zone_last: Zone | None


class CardOut(BaseModel):
    short_no: str
    registered_at: datetime
    tz: str | None
    position: PositionOut | None
    lives: int
    measurements: MeasurementsOut


class PointOut(BaseModel):
    value: float | str
    at: datetime


class LayerOut(BaseModel):
    layer: Literal["anthro", "wellbeing", "checkup", "functional"]
    metric: Literal["weight_kg", "wellbeing_code", "inflammation_zone"] | None
    baseline: PointOut | None
    recent: list[PointOut]


class ChangeMapOut(BaseModel):
    layers: list[LayerOut]


# ---------------------------- ошибки ----------------------------


def _participant_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": "PARTICIPANT_NOT_FOUND",
            "message": "Участник не найден. Пройдите онбординг.",
        },
    )


def _service_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": "SERVICE_UNAVAILABLE",
            "message": "Сервис временно недоступен. Попробуйте позже.",
        },
    )


def _rollback(session: Session) -> None:
    with suppress(Exception):
        session.rollback()


# ---------------------------- логика ----------------------------


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc) if value.tzinfo is not None else value


def build_position(
    stage_no: int | None, module_no: int | None, day_no: int | None
) -> PositionOut | None:
    """Позиция дня: None, если хоть один номер NULL; иначе объект."""
    if stage_no is None or module_no is None or day_no is None:
        return None
    return PositionOut(stage_no=stage_no, module_no=module_no, day_no=day_no)


def _point(value: Any, at: datetime) -> PointOut:
    return PointOut(value=value, at=_utc(at))


def _layer(layer: str, metric: str | None, points: list[PointOut]) -> LayerOut:
    """baseline — первая точка; recent — до 5 последних после baseline, по возрастанию."""
    if not points:
        return LayerOut(layer=layer, metric=metric, baseline=None, recent=[])
    return LayerOut(
        layer=layer, metric=metric, baseline=points[0], recent=points[1:][-RECENT_LIMIT:]
    )


def build_card(short_no: int, registered_at: datetime, state, form, rows) -> CardOut:
    bodies = [r for r in rows if r.kind == KIND_BODY]
    checkups = [r for r in rows if r.kind == KIND_CHECKUP]
    tz = state.tz if state is not None and form is not None else None
    if state is None:
        position, lives = None, DEFAULT_LIVES
    else:
        position = build_position(state.stage_no, state.module_no, state.day_no)
        lives = DEFAULT_LIVES if state.lives is None else state.lives
    return CardOut(
        short_no=format_short_no(short_no),
        registered_at=_utc(registered_at),
        tz=tz,
        position=position,
        lives=lives,
        measurements=MeasurementsOut(
            weight_start_kg=float(bodies[0].weight_kg) if bodies else None,
            weight_current_kg=float(bodies[-1].weight_kg) if bodies else None,
            checkup_completed=any(r.occasion == OCCASION_ONBOARDING for r in checkups),
            zone_start=checkups[0].checkup_zone if checkups else None,
            zone_last=checkups[-1].checkup_zone if checkups else None,
        ),
    )


def build_change_map(form, rows) -> ChangeMapOut:
    anthro = [_point(float(r.weight_kg), r.created_at) for r in rows if r.kind == KIND_BODY]
    checkup = [_point(r.checkup_zone, r.created_at) for r in rows if r.kind == KIND_CHECKUP]
    wellbeing = (
        LayerOut(
            layer="wellbeing",
            metric="wellbeing_code",
            baseline=_point(form.wellbeing_code, form.created_at),
            recent=[],
        )
        if form is not None
        else LayerOut(layer="wellbeing", metric="wellbeing_code", baseline=None, recent=[])
    )
    return ChangeMapOut(
        layers=[
            _layer("anthro", "weight_kg", anthro),
            wellbeing,
            _layer("checkup", "inflammation_zone", checkup),
            LayerOut(layer="functional", metric=None, baseline=None, recent=[]),
        ]
    )


def _load_card(session: Session, tg_user_id: int) -> CardOut | None:
    found = find_active_participant(session, tg_user_id)
    if found is None:
        return None
    pid, short_no = found
    params: dict[str, uuid.UUID] = {"pid": pid}
    registered_at = session.execute(_REGISTRY_SQL, params).scalar_one()
    state = session.execute(_STATE_SQL, params).first()
    form = session.execute(_FORM_SQL, params).first()
    rows = session.execute(_MEASUREMENTS_SQL, params).all()
    return build_card(short_no, registered_at, state, form, rows)


def _load_change_map(session: Session, tg_user_id: int) -> ChangeMapOut | None:
    found = find_active_participant(session, tg_user_id)
    if found is None:
        return None
    params: dict[str, uuid.UUID] = {"pid": found[0]}
    form = session.execute(_FORM_SQL, params).first()
    rows = session.execute(_MEASUREMENTS_SQL, params).all()
    return build_change_map(form, rows)


def _read(session: Session, tg_user_id: int, name: str, loader):
    """Только чтение: rollback перед ответом; ошибка БД → 503; нет участника → 404."""
    try:
        result = loader(session, tg_user_id)
    except SQLAlchemyError as exc:
        _rollback(session)
        logger.error("%s: ошибка БД (%s) — 503", name, type(exc).__name__)
        raise _service_unavailable() from None
    _rollback(session)
    if result is None:
        logger.info("%s: tg_user_id=%s status=404", name, tg_user_id)
        raise _participant_not_found()
    logger.info("%s: tg_user_id=%s status=ok", name, tg_user_id)
    return result


# ---------------------------- маршруты ----------------------------

_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"description": "PARTICIPANT_NOT_FOUND"},
    503: {"description": "SERVICE_UNAVAILABLE (ошибка БД)"},
}


@router.get("/me/card", response_model=CardOut, responses=_RESPONSES)
def get_me_card(
    ctx: InitDataContext = Depends(require_init_data),
    session: Session = Depends(get_db_session),
) -> CardOut:
    return _read(session, ctx.tg_user_id, "me/card", _load_card)


@router.get("/me/change-map", response_model=ChangeMapOut, responses=_RESPONSES)
def get_me_change_map(
    ctx: InitDataContext = Depends(require_init_data),
    session: Session = Depends(get_db_session),
) -> ChangeMapOut:
    return _read(session, ctx.tg_user_id, "me/change-map", _load_change_map)
