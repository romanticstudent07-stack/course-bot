"""/miniapp/v1/onboarding/form* — анкета онбординга (api-i3-2; Р-16, Р-17).

initData и rate-limit — роутер miniapp_v1 в main.py. Конфиг — app.onboarding_form_config
(form.json и cities.csv в репо); ошибка конфига в маршруте → 503 SERVICE_MISCONFIGURED.

GET /onboarding/form/config — БД не нужна, участник не обязателен:
  200 {version, genders, wellbeing_question, wellbeing [{code, text}], weight {min, max, step},
       timezones [{tz, city}], fallback_title, cities [[город, регион, i]]}, i — индекс в timezones.

GET /onboarding/form — только чтение, без замка: нет активного участника → 404
PARTICIPANT_NOT_FOUND; иначе 200 {submitted, created_at}. Пол, код, вес и пояс не отдаются.

POST /onboarding/form — заголовок X-Client-Op-Id (UUID v4, обязателен), тело
{tz, gender, wellbeing_code, weight_kg}. tz — только из allowed_tz (11 поясов form.json и
cities.csv); код — только из конфига; вес 30–300, не больше 1 знака (без округления), bool → 422.
Лишние поля (city, name, phone, email) отбрасываются и нигде не пишутся (Р-16).
Одна транзакция:
  1) active_pid_locked: нет → 404 PARTICIPANT_NOT_FOUND;
  2) C0 и C1 действуют (consent_status): нет текста → 503 SERVICE_MISCONFIGURED;
     причины reconsent → 409 RECONSENT_REQUIRED;
  3) анкета pid и строка measurements_log с этим op_id;
  4) анкета есть: строка op kind body → повтор (commit, 200 с created_at анкеты);
     иначе → 409 ONBOARDING_FORM_EXISTS;
  5) анкеты нет, а op_id занят → 409 IDEMPOTENCY_CONFLICT;
  6) INSERT onboarding_form + measurements_log (kind body, occasion onboarding) + событие
     tz_set в participant_events (проектор сам пишет participant_state.tz; INV-1);
  7) commit → 200 {created_at}. Все три строки — или ни одной.
Любая SQLAlchemyError (и на commit) → rollback, 503 SERVICE_UNAVAILABLE; в лог — имя класса.
participant_state здесь не читается и не пишется; outbox и idempotency_keys не используются.
Лог (app.onboarding_form): INFO только tg_user_id и status. pid, op_id, пола, кода
самочувствия, веса и пояса в логе нет.
"""
from __future__ import annotations

import json
import logging
import uuid
from contextlib import suppress
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.exceptions import RequestValidationError
from pydantic import UUID4, BaseModel, Field, field_validator
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
from app.db.models import GENDERS, WEIGHT_MAX_KG, WEIGHT_MIN_KG, WELLBEING_CODE_PATTERN
from app.db.session import get_db_session
from app.onboarding_form_config import (
    MAX_TZ_LEN,
    OnboardingFormConfig,
    OnboardingFormConfigError,
    get_onboarding_form_config,
)
from app.participant_lock import active_pid_locked
from app.participants import find_active_participant
from app.telegram_init_data import InitDataContext, require_init_data

logger = logging.getLogger("app.onboarding_form")

# Префикс /miniapp/v1, проверка initData и rate-limit — в main.py (роутер miniapp_v1).
router = APIRouter(tags=["onboarding-form"])

CLIENT_OP_ID_HEADER = "X-Client-Op-Id"
KIND_BODY = "body"
# Тот же kind, что app.projector.EVENT_KIND_TZ_SET (проверяет тест 14).
EVENT_KIND_TZ_SET = "tz_set"
TZ_SET_SCHEMA_VERSION = 1
# Событие по действию участника (actor и actor_role).
ACTOR_PARTICIPANT = "participant"

_SELECT_FORM_SQL = text("SELECT created_at FROM onboarding_form WHERE pid = :pid")

_SELECT_OP_SQL = text(
    "SELECT kind FROM measurements_log WHERE pid = :pid AND client_op_id = :op"
)

_INSERT_FORM_SQL = text(
    "INSERT INTO onboarding_form (pid, gender, wellbeing_code) "
    "VALUES (:pid, :gender, :code) "
    "ON CONFLICT (pid) DO NOTHING RETURNING created_at"
)

_INSERT_BODY_SQL = text(
    "INSERT INTO measurements_log (pid, kind, occasion, stage_no, weight_kg, client_op_id) "
    "VALUES (:pid, 'body', 'onboarding', NULL, :w, :op) "
    "ON CONFLICT (pid, client_op_id) DO NOTHING RETURNING id"
)

_INSERT_EVENT_SQL = text(
    "INSERT INTO participant_events (pid, kind, payload, actor, actor_role) "
    "VALUES (:pid, :kind, CAST(:payload AS jsonb), :actor, :role)"
)


# ---------------------------- модели ----------------------------


class WellbeingOut(BaseModel):
    code: str
    text: str


class WeightOut(BaseModel):
    min: float
    max: float
    step: float


class TimezoneOut(BaseModel):
    tz: str
    city: str


class FormConfigOut(BaseModel):
    version: str
    genders: list[str]
    wellbeing_question: str
    wellbeing: list[WellbeingOut]
    weight: WeightOut
    timezones: list[TimezoneOut]
    fallback_title: str
    cities: list[tuple[str, str, int]]


class FormStatusOut(BaseModel):
    submitted: bool
    created_at: datetime | None


class FormSubmitIn(BaseModel):
    # Лишние поля (city, name, phone, email) отбрасываются (pydantic по умолчанию).
    tz: str = Field(min_length=1, max_length=MAX_TZ_LEN)
    gender: Literal["male", "female"]
    wellbeing_code: str = Field(pattern=WELLBEING_CODE_PATTERN)
    weight_kg: Decimal = Field(
        ge=WEIGHT_MIN_KG, le=WEIGHT_MAX_KG, max_digits=4, decimal_places=1
    )

    @field_validator("weight_kg", mode="before")
    @classmethod
    def _reject_bool(cls, value: Any) -> Any:
        # lax-режим pydantic принял бы true как Decimal 1.
        if isinstance(value, bool):
            raise ValueError("weight_kg: bool не допускается")
        return value


class FormSubmitOut(BaseModel):
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


def _service_misconfigured() -> HTTPException:
    return _error(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "SERVICE_MISCONFIGURED",
        "Сервис временно недоступен",
    )


def _form_exists() -> HTTPException:
    return _error(status.HTTP_409_CONFLICT, "ONBOARDING_FORM_EXISTS", "Анкета уже отправлена.")


def _idempotency_conflict() -> HTTPException:
    return _error(
        status.HTTP_409_CONFLICT,
        "IDEMPOTENCY_CONFLICT",
        "Этот X-Client-Op-Id уже использован с другим отчётом.",
    )


def _rollback(session: Session) -> None:
    with suppress(Exception):
        session.rollback()


def _released(session: Session, exc: Exception) -> Exception:
    """rollback (снимает xact-замок) и вернуть exc для raise."""
    _rollback(session)
    return exc


def form_config() -> OnboardingFormConfig:
    """Зависимость маршрутов: битый конфиг → 503 SERVICE_MISCONFIGURED."""
    try:
        return get_onboarding_form_config()
    except OnboardingFormConfigError as exc:
        logger.error("onboarding/form: конфиг анкеты не загружен (%s) — 503", type(exc).__name__)
        raise _service_misconfigured() from None


# ---------------------------- логика ----------------------------


def config_out(cfg: OnboardingFormConfig) -> FormConfigOut:
    return FormConfigOut(
        version=cfg.version,
        genders=list(GENDERS),
        wellbeing_question=cfg.wellbeing_question,
        wellbeing=[WellbeingOut(code=w.code, text=w.text) for w in cfg.wellbeing],
        weight=WeightOut(min=cfg.weight_min, max=cfg.weight_max, step=cfg.weight_step),
        timezones=[TimezoneOut(tz=t.tz, city=t.city) for t in cfg.timezones],
        fallback_title=cfg.fallback_title,
        cities=list(cfg.cities),
    )


def check_against_config(body: FormSubmitIn, cfg: OnboardingFormConfig) -> None:
    """tz и код — только из конфига; иначе 422 VALIDATION_ERROR (без значений полей)."""
    errors: list[dict[str, Any]] = []
    if body.tz not in cfg.allowed_tz:
        errors.append({"loc": ("body", "tz"), "msg": "tz не из конфига", "type": "value_error"})
    if body.wellbeing_code not in cfg.wellbeing_codes:
        errors.append(
            {
                "loc": ("body", "wellbeing_code"),
                "msg": "код не из конфига",
                "type": "value_error",
            }
        )
    if errors:
        raise RequestValidationError(errors)


def _insert_tz_event(session: Session, pid: uuid.UUID, tz: str) -> None:
    """Событие tz_set для проектора (participant_state.tz пишет только он; INV-1)."""
    session.execute(
        _INSERT_EVENT_SQL,
        {
            "pid": pid,
            "kind": EVENT_KIND_TZ_SET,
            "payload": json.dumps({"schema_version": TZ_SET_SCHEMA_VERSION, "tz": tz}),
            "actor": ACTOR_PARTICIPANT,
            "role": ACTOR_PARTICIPANT,
        },
    )


def submit_form(
    session: Session, tg_user_id: int, op_id: uuid.UUID, body: FormSubmitIn
) -> tuple[FormSubmitOut, str]:
    """Шаги 1–7 POST /onboarding/form → (ответ, status created / repeat). Ошибки —
    HTTPException / ConsentTextMissingError / SQLAlchemyError (вызывающий → 503).
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

    # 3) анкета и строка с этим op_id
    op = str(op_id)
    form_row = session.execute(_SELECT_FORM_SQL, {"pid": pid}).first()
    op_row = session.execute(_SELECT_OP_SQL, {"pid": pid, "op": op}).first()

    # 4) анкета уже есть: повтор того же op_id или 409
    if form_row is not None:
        if op_row is not None and op_row.kind == KIND_BODY:
            session.commit()
            return FormSubmitOut(created_at=form_row.created_at), "repeat"
        raise _released(session, _form_exists())

    # 5) анкеты нет, а op_id занят
    if op_row is not None:
        raise _released(session, _idempotency_conflict())

    # 6) три записи одной транзакцией
    inserted = session.execute(
        _INSERT_FORM_SQL,
        {"pid": pid, "gender": body.gender, "code": body.wellbeing_code},
    ).first()
    if inserted is None:
        raise _released(session, _form_exists())
    body_row = session.execute(
        _INSERT_BODY_SQL, {"pid": pid, "w": body.weight_kg, "op": op}
    ).first()
    if body_row is None:
        raise _released(session, _idempotency_conflict())
    _insert_tz_event(session, pid, body.tz)

    # 7) commit; ответ — только после него
    session.commit()
    return FormSubmitOut(created_at=inserted.created_at), "created"


# ---------------------------- маршруты ----------------------------


@router.get(
    "/onboarding/form/config",
    response_model=FormConfigOut,
    responses={
        401: {"description": "initData невалидна / истекла (TG_INIT_MISSING / TG_INIT_INVALID)"},
        503: {"description": "SERVICE_MISCONFIGURED (битый конфиг анкеты)"},
    },
)
def get_onboarding_form_config_route(
    ctx: InitDataContext = Depends(require_init_data),
    cfg: OnboardingFormConfig = Depends(form_config),
) -> FormConfigOut:
    logger.info("onboarding/form/config: tg_user_id=%s status=ok", ctx.tg_user_id)
    return config_out(cfg)


@router.get(
    "/onboarding/form",
    response_model=FormStatusOut,
    responses={
        404: {"description": "PARTICIPANT_NOT_FOUND"},
        503: {"description": "SERVICE_UNAVAILABLE (ошибка БД)"},
    },
)
def get_onboarding_form(
    ctx: InitDataContext = Depends(require_init_data),
    session: Session = Depends(get_db_session),
) -> FormStatusOut:
    try:
        found = find_active_participant(session, ctx.tg_user_id)
        row = (
            None
            if found is None
            else session.execute(_SELECT_FORM_SQL, {"pid": found[0]}).first()
        )
    except SQLAlchemyError as exc:
        _rollback(session)
        logger.error("onboarding/form GET: ошибка БД (%s) — 503", type(exc).__name__)
        raise _service_unavailable() from None
    if found is None:
        logger.info("onboarding/form GET: tg_user_id=%s status=404", ctx.tg_user_id)
        raise _participant_not_found()
    logger.info("onboarding/form GET: tg_user_id=%s status=ok", ctx.tg_user_id)
    return FormStatusOut(
        submitted=row is not None,
        created_at=row.created_at if row is not None else None,
    )


@router.post(
    "/onboarding/form",
    response_model=FormSubmitOut,
    responses={
        404: {"description": "PARTICIPANT_NOT_FOUND"},
        409: {"description": "RECONSENT_REQUIRED / ONBOARDING_FORM_EXISTS / IDEMPOTENCY_CONFLICT"},
        422: {"description": "VALIDATION_ERROR — нет или неверный X-Client-Op-Id / тело"},
        503: {"description": "SERVICE_UNAVAILABLE (ошибка БД, в т. ч. commit) / SERVICE_MISCONFIGURED"},
    },
)
def post_onboarding_form(
    body: FormSubmitIn,
    # Annotated, как в checkup.py: так FastAPI проверяет версию UUID4 (не-v4 → 422).
    client_op_id: Annotated[UUID4, Header(alias=CLIENT_OP_ID_HEADER)],
    ctx: InitDataContext = Depends(require_init_data),
    session: Session = Depends(get_db_session),
    cfg: OnboardingFormConfig = Depends(form_config),
) -> FormSubmitOut:
    # До БД: tz и код — только из конфига.
    check_against_config(body, cfg)
    try:
        result, outcome = submit_form(session, ctx.tg_user_id, client_op_id, body)
    except HTTPException as exc:
        _rollback(session)
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        outcome = "exists" if detail.get("code") == "ONBOARDING_FORM_EXISTS" else exc.status_code
        logger.info("onboarding/form: tg_user_id=%s status=%s", ctx.tg_user_id, outcome)
        raise
    except ConsentTextMissingError as exc:
        _rollback(session)
        logger.error("onboarding/form: нет текста согласия keys=%s (503)", ",".join(exc.keys))
        raise _service_misconfigured() from None
    except SQLAlchemyError as exc:
        _rollback(session)
        logger.error("onboarding/form: ошибка БД (%s) — 503", type(exc).__name__)
        raise _service_unavailable() from None
    logger.info("onboarding/form: tg_user_id=%s status=%s", ctx.tg_user_id, outcome)
    return result
