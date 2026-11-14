"""POST /miniapp/v1/support/question — вопрос в поддержку (api-sup-1, Р-19).

Заголовок X-Client-Op-Id (UUID v4, обязателен), тело {topic_code, text}; лишние поля
отбрасываются. Пост в тему группы делает бот (bot-sup-1) по строке outbox support_question.

Порядок:
  0) зависимости роутера miniapp_v1 (main.py): initData → rate_limit — раньше разбора
     заголовка и тела (401 раньше 422);
  1) до БД: topic_code не из SUPPORT_TOPIC_CODES → 422 SUPPORT_TOPIC_INVALID; затем
     len(text.strip()) < 2, len(text) > 2000 или NUL в тексте → 422 SUPPORT_TEXT_INVALID;
     body = text.strip() (strip режет не меньше btrim → CHECK 0017 не сработает);
  2) одна транзакция: active_pid_locked — нет → 404 PARTICIPANT_NOT_FOUND;
  3) C0 и C1 действуют (consent_status): нет текста → 503 SERVICE_MISCONFIGURED;
     причины reconsent → 409 RECONSENT_REQUIRED;
  4) повтор (раньше частоты): строка (pid, client_op_id) есть → commit, 201, outbox не пишется;
     тело повтора не сравнивается (SELECT body у app_api нет);
  5) частота: max(created_at) по pid и now() — время БД; меньше SUPPORT_MIN_INTERVAL_S →
     429 SUPPORT_TOO_FREQUENT + Retry-After (целое 1…30);
  6) INSERT support_questions ON CONFLICT (pid, client_op_id) DO NOTHING RETURNING id;
     None (гонка, замок её исключает) → commit, 201 как повтор;
  7) INSERT outbox: event_type support_question, aggregate_id str(pid),
     payload {"pid", "question_id"} — текста и topic_code в outbox нет (DLQ копирует payload);
  8) commit → 201 {"status": "sent"}. Строка и outbox — обе или ни одной.
Любая SQLAlchemyError (и на commit) → rollback, 503 SERVICE_UNAVAILABLE; в лог — имя класса.

Права app_api (миграции 0017, 0012): support_questions — INSERT (pid, topic_code, body,
client_op_id), SELECT (id, pid, client_op_id, created_at), USAGE support_questions_id_seq;
outbox — INSERT. body и topic_code из БД не читаются.
idempotency_keys, day_keys, participant_events, participant_state не пишутся.
Лог (app.support): INFO только tg_user_id и status (created / repeat / код ошибки).
pid, op_id, topic_code и текста вопроса в логе нет.
"""
from __future__ import annotations

import json
import logging
import math
import uuid
from contextlib import suppress
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import UUID4, BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.consent_status import (
    STATUS_KINDS,
    ConsentTextMissingError,
    current_texts,
    load_events,
    reasons,
)
from app.db.models import SUPPORT_BODY_MAX_LEN, SUPPORT_BODY_MIN_LEN, SUPPORT_TOPIC_CODES
from app.db.session import get_db_session
from app.notify_ops import _INSERT_OUTBOX
from app.participant_lock import active_pid_locked
from app.telegram_init_data import InitDataContext, require_init_data

logger = logging.getLogger("app.support")

# Префикс /miniapp/v1, проверка initData и rate-limit — в main.py (роутер miniapp_v1).
router = APIRouter(tags=["support"])

EVENT_TYPE = "support_question"
SUPPORT_MIN_INTERVAL_S = 30
CLIENT_OP_ID_HEADER = "X-Client-Op-Id"

_SELECT_OP_SQL = text(
    "SELECT id FROM support_questions WHERE pid = :pid AND client_op_id = :op"
)

_FREQ_SQL = text(
    "SELECT max(created_at) AS last, now() AS now FROM support_questions WHERE pid = :pid"
)

_INSERT_SQL = text(
    "INSERT INTO support_questions (pid, topic_code, body, client_op_id) "
    "VALUES (:pid, :topic, :body, :op) "
    "ON CONFLICT (pid, client_op_id) DO NOTHING RETURNING id"
)


# ---------------------------- модели ----------------------------


class SupportQuestionIn(BaseModel):
    # Лишние поля отбрасываются (pydantic по умолчанию). Номера темы группы в API нет.
    topic_code: str = Field(max_length=16)
    text: str


class SupportQuestionOut(BaseModel):
    status: str


# ---------------------------- ошибки ----------------------------


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


def _service_misconfigured() -> HTTPException:
    return _error(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "SERVICE_MISCONFIGURED",
        "Сервис временно недоступен",
    )


def _too_frequent(retry_after: int) -> HTTPException:
    return _error(
        status.HTTP_429_TOO_MANY_REQUESTS,
        "SUPPORT_TOO_FREQUENT",
        "Слишком часто. Подождите немного и отправьте снова.",
        headers={"Retry-After": str(retry_after)},
    )


def _rollback(session: Session) -> None:
    with suppress(Exception):
        session.rollback()


def _released(session: Session, exc: Exception) -> Exception:
    """rollback (снимает xact-замок) и вернуть exc для raise."""
    _rollback(session)
    return exc


# ---------------------------- логика ----------------------------


def check_body(body: SupportQuestionIn) -> str:
    """Шаг 1 (до БД): тема, затем текст → body = text.strip(); иначе 422."""
    if body.topic_code not in SUPPORT_TOPIC_CODES:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "SUPPORT_TOPIC_INVALID", "Неизвестная тема."
        )
    stripped = body.text.strip()
    if (
        len(stripped) < SUPPORT_BODY_MIN_LEN
        or len(body.text) > SUPPORT_BODY_MAX_LEN
        or "\x00" in body.text
    ):
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "SUPPORT_TEXT_INVALID",
            "Вопрос — от 2 до 2000 символов.",
        )
    return stripped


def submit_question(
    session: Session, tg_user_id: int, op_id: uuid.UUID, topic: str, body: str
) -> str:
    """Шаги 2–8 → status created / repeat. Ошибки — HTTPException /
    ConsentTextMissingError / SQLAlchemyError (вызывающий → 503).
    """
    # 2) участник под замком
    pid = active_pid_locked(session, tg_user_id)
    if pid is None:
        raise _released(session, _participant_not_found())

    # 3) C0 и C1 действуют
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

    # 4) повтор того же op_id — раньше частоты
    op = str(op_id)
    if session.execute(_SELECT_OP_SQL, {"pid": pid, "op": op}).first() is not None:
        session.commit()
        return "repeat"

    # 5) частота — по времени БД
    freq = session.execute(_FREQ_SQL, {"pid": pid}).one()
    if freq.last is not None:
        elapsed = (freq.now - freq.last).total_seconds()
        if elapsed < SUPPORT_MIN_INTERVAL_S:
            retry_after = max(1, math.ceil(SUPPORT_MIN_INTERVAL_S - elapsed))
            raise _released(session, _too_frequent(retry_after))

    # 6) строка вопроса
    inserted = session.execute(
        _INSERT_SQL, {"pid": pid, "topic": topic, "body": body, "op": op}
    ).first()
    if inserted is None:
        session.commit()
        return "repeat"

    # 7) outbox — без текста и topic_code
    session.execute(
        _INSERT_OUTBOX,
        {
            "aggregate_id": str(pid),
            "event_type": EVENT_TYPE,
            "payload": json.dumps({"pid": str(pid), "question_id": inserted.id}),
        },
    )

    # 8) commit; ответ — только после него
    session.commit()
    return "created"


# ---------------------------- маршрут ----------------------------


@router.post(
    "/support/question",
    status_code=status.HTTP_201_CREATED,
    response_model=SupportQuestionOut,
    responses={
        404: {"description": "PARTICIPANT_NOT_FOUND"},
        409: {"description": "RECONSENT_REQUIRED"},
        422: {"description": "VALIDATION_ERROR / SUPPORT_TOPIC_INVALID / SUPPORT_TEXT_INVALID"},
        429: {"description": "RATE_LIMITED / SUPPORT_TOO_FREQUENT, заголовок Retry-After"},
        503: {"description": "SERVICE_UNAVAILABLE (ошибка БД, в т. ч. commit) / SERVICE_MISCONFIGURED"},
    },
)
def post_support_question(
    body: SupportQuestionIn,
    # Annotated, как в onboarding_form.py: так FastAPI проверяет версию UUID4 (не-v4 → 422).
    client_op_id: Annotated[UUID4, Header(alias=CLIENT_OP_ID_HEADER)],
    ctx: InitDataContext = Depends(require_init_data),
    session: Session = Depends(get_db_session),
) -> SupportQuestionOut:
    try:
        question = check_body(body)
        outcome = submit_question(
            session, ctx.tg_user_id, client_op_id, body.topic_code, question
        )
    except HTTPException as exc:
        _rollback(session)
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        logger.info(
            "support/question: tg_user_id=%s status=%s",
            ctx.tg_user_id,
            detail.get("code", exc.status_code),
        )
        raise
    except ConsentTextMissingError as exc:
        _rollback(session)
        logger.error("support/question: нет текста согласия keys=%s (503)", ",".join(exc.keys))
        raise _service_misconfigured() from None
    except SQLAlchemyError as exc:
        _rollback(session)
        logger.error("support/question: ошибка БД (%s) — 503", type(exc).__name__)
        raise _service_unavailable() from None
    logger.info("support/question: tg_user_id=%s status=%s", ctx.tg_user_id, outcome)
    return SupportQuestionOut(status="sent")
