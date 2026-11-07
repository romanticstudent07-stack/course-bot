"""/miniapp/v1/checkup/* — Чек-Ап (api-i3-1).

initData и rate-limit — роутер miniapp_v1 в main.py. Конфиг — app.checkup_config (файл в репо).

GET /checkup/config — БД не нужна, участник не обязателен; гейта Legal здесь нет
(карточка api-i3-1, «Канон и решения» (б)):
  200 {version, scale {min, max}, blocks [{id, title}], questions [{id, block, text}],
       zones [{id, title, text}], disclaimer}. Границы зон (min, max) и legal_status
  клиенту не отдаются; балла нет.

POST /checkup/submit — заголовок X-Client-Op-Id (UUID v4, обязателен), тело
{occasion: "onboarding", answers: 15 целых 0–3 (StrictInt)}. Лишние поля (score, zone,
stage_no) игнорируются: балл и зону считает только сервер. Иначе → 422 VALIDATION_ERROR.
Одна транзакция:
  1) active_pid_locked: нет → 404 PARTICIPANT_NOT_FOUND;
  2) C0 и C1 действуют (consent_status): нет текста → 503 SERVICE_MISCONFIGURED;
     причины reconsent → 409 RECONSENT_REQUIRED;
  3) score_and_zone по 15 ответам, версия — cfg.version;
  4) INSERT measurements_log … ON CONFLICT (pid, client_op_id) DO NOTHING RETURNING;
  5) повтор op_id → сохранённые значения (без пересчёта); op_id занят не checkup →
     409 IDEMPOTENCY_CONFLICT;
  6) commit → 200 {zone, config_version, created_at}. Балла в ответе нет никогда.
Любая SQLAlchemyError (и на commit) → rollback, 503 SERVICE_UNAVAILABLE; в лог — имя класса.
Пишется только measurements_log (participant_events, outbox, idempotency_keys — нет).
Лог (app.checkup): INFO только tg_user_id и status. pid, op_id, ответов, балла и зоны
в логе нет — это данные о здоровье.
"""
from __future__ import annotations

import logging
import uuid
from contextlib import suppress
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import UUID4, BaseModel, Field, StrictInt
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.checkup_config import (
    QUESTIONS_COUNT,
    SCALE_MAX,
    SCALE_MIN,
    CheckupConfig,
    get_checkup_config,
    score_and_zone,
)
from app.consent_status import (
    STATUS_KINDS,
    ConsentTextMissingError,
    current_texts,
    load_events,
    reasons,
)
from app.db.session import get_db_session
from app.participant_lock import active_pid_locked
from app.telegram_init_data import InitDataContext, require_init_data

logger = logging.getLogger("app.checkup")

# Префикс /miniapp/v1, проверка initData и rate-limit — в main.py (роутер miniapp_v1).
router = APIRouter(tags=["checkup"])

CLIENT_OP_ID_HEADER = "X-Client-Op-Id"
KIND_CHECKUP = "checkup"

_INSERT_SQL = text(
    "INSERT INTO measurements_log (pid, kind, occasion, stage_no, checkup_answers, "
    "checkup_score, checkup_zone, checkup_config_version, client_op_id) "
    "VALUES (:pid, 'checkup', 'onboarding', NULL, CAST(:answers AS smallint[]), "
    ":score, :zone, :ver, :op) "
    "ON CONFLICT (pid, client_op_id) DO NOTHING "
    "RETURNING checkup_zone, checkup_config_version, created_at"
)

_SELECT_SQL = text(
    "SELECT kind, checkup_zone, checkup_config_version, created_at "
    "FROM measurements_log WHERE pid = :pid AND client_op_id = :op"
)


# ---------------------------- модели ----------------------------


class ScaleOut(BaseModel):
    min: int
    max: int


class BlockOut(BaseModel):
    id: int
    title: str


class QuestionOut(BaseModel):
    id: str
    block: int
    text: str


class ZoneOut(BaseModel):
    id: str
    title: str
    text: str


class CheckupConfigOut(BaseModel):
    version: str
    scale: ScaleOut
    blocks: list[BlockOut]
    questions: list[QuestionOut]
    zones: list[ZoneOut]
    disclaimer: str


Answer = Annotated[StrictInt, Field(ge=SCALE_MIN, le=SCALE_MAX)]


class CheckupSubmitIn(BaseModel):
    # Лишние поля (score, zone, stage_no) игнорируются (pydantic по умолчанию).
    occasion: Literal["onboarding"]
    answers: list[Answer] = Field(min_length=QUESTIONS_COUNT, max_length=QUESTIONS_COUNT)


class CheckupSubmitOut(BaseModel):
    zone: str
    config_version: str
    created_at: datetime


# ---------------------------- ошибки ----------------------------


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


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


def _rollback(session: Session) -> None:
    with suppress(Exception):
        session.rollback()


def _released(session: Session, exc: Exception) -> Exception:
    """rollback (снимает xact-замок) и вернуть exc для raise."""
    _rollback(session)
    return exc


# ---------------------------- логика ----------------------------


def config_out(cfg: CheckupConfig) -> CheckupConfigOut:
    """Конфиг для клиента: без границ зон, legal_status и балла."""
    return CheckupConfigOut(
        version=cfg.version,
        scale=ScaleOut(min=cfg.scale_min, max=cfg.scale_max),
        blocks=[BlockOut(id=b.id, title=b.title) for b in cfg.blocks],
        questions=[QuestionOut(id=q.id, block=q.block, text=q.text) for q in cfg.questions],
        zones=[ZoneOut(id=z.id, title=z.title, text=z.text) for z in cfg.zones],
        disclaimer=cfg.disclaimer,
    )


def submit_checkup(
    session: Session,
    tg_user_id: int,
    op_id: uuid.UUID,
    body: CheckupSubmitIn,
    cfg: CheckupConfig,
) -> tuple[CheckupSubmitOut, bool]:
    """Шаги 1–6 POST /checkup/submit → (ответ, created). Ошибки — HTTPException /
    ConsentTextMissingError / SQLAlchemyError (вызывающий → 503). commit — только на шаге 6.
    """
    # 1) участник под замком
    pid = active_pid_locked(session, tg_user_id)
    if pid is None:
        raise _released(session, _participant_not_found())

    # 2) C0 и C1 действуют
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

    # 3) балл и зону считает сервер
    score, zone = score_and_zone(body.answers, cfg)

    # 4) запись; повтор op_id гасит UNIQUE (pid, client_op_id)
    op = str(op_id)
    row = session.execute(
        _INSERT_SQL,
        {
            "pid": pid,
            "answers": list(body.answers),
            "score": score,
            "zone": zone,
            "ver": cfg.version,
            "op": op,
        },
    ).first()
    created = row is not None

    # 5) повтор: сохранённые значения, без пересчёта
    if row is None:
        row = session.execute(_SELECT_SQL, {"pid": pid, "op": op}).first()
        if row is None or row.kind != KIND_CHECKUP:
            raise _released(
                session,
                _error(
                    status.HTTP_409_CONFLICT,
                    "IDEMPOTENCY_CONFLICT",
                    "Этот X-Client-Op-Id уже использован с другим отчётом.",
                ),
            )

    # 6) commit; ответ строится только после него
    session.commit()
    return (
        CheckupSubmitOut(
            zone=row.checkup_zone,
            config_version=row.checkup_config_version,
            created_at=row.created_at,
        ),
        created,
    )


# ---------------------------- маршруты ----------------------------


@router.get(
    "/checkup/config",
    response_model=CheckupConfigOut,
    responses={
        401: {"description": "initData невалидна / истекла (TG_INIT_MISSING / TG_INIT_INVALID)"},
    },
)
def get_checkup_config_route(
    ctx: InitDataContext = Depends(require_init_data),
    cfg: CheckupConfig = Depends(get_checkup_config),
) -> CheckupConfigOut:
    logger.info("checkup/config: tg_user_id=%s status=ok", ctx.tg_user_id)
    return config_out(cfg)


@router.post(
    "/checkup/submit",
    response_model=CheckupSubmitOut,
    responses={
        404: {"description": "PARTICIPANT_NOT_FOUND"},
        409: {"description": "RECONSENT_REQUIRED / IDEMPOTENCY_CONFLICT"},
        422: {"description": "VALIDATION_ERROR — нет или неверный X-Client-Op-Id / тело"},
        503: {"description": "SERVICE_UNAVAILABLE (ошибка БД, в т. ч. commit) / SERVICE_MISCONFIGURED"},
    },
)
def post_checkup_submit(
    body: CheckupSubmitIn,
    # Annotated, как в day.py report/submit: так FastAPI проверяет версию UUID4 (не-v4 → 422).
    client_op_id: Annotated[UUID4, Header(alias=CLIENT_OP_ID_HEADER)],
    ctx: InitDataContext = Depends(require_init_data),
    session: Session = Depends(get_db_session),
    cfg: CheckupConfig = Depends(get_checkup_config),
) -> CheckupSubmitOut:
    try:
        result, created = submit_checkup(session, ctx.tg_user_id, client_op_id, body, cfg)
    except HTTPException as exc:
        _rollback(session)
        logger.info("checkup/submit: tg_user_id=%s status=%s", ctx.tg_user_id, exc.status_code)
        raise
    except ConsentTextMissingError as exc:
        _rollback(session)
        logger.error("checkup/submit: нет текста согласия keys=%s (503)", ",".join(exc.keys))
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "SERVICE_MISCONFIGURED",
            "Сервис временно недоступен",
        ) from None
    except SQLAlchemyError as exc:
        _rollback(session)
        logger.error("checkup/submit: ошибка БД (%s) — 503", type(exc).__name__)
        raise _service_unavailable() from None
    logger.info(
        "checkup/submit: tg_user_id=%s status=%s",
        ctx.tg_user_id,
        "created" if created else "repeat",
    )
    return result
