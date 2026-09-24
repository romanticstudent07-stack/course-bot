"""/miniapp/v1/onboarding/* — онбординг SEAM-1 (Итерация 1b+1c).

Контракт: build/miniapp-api-contract.yaml → POST /miniapp/v1/onboarding/first-launch
  request:  {birth_date: date}
  201:      PidCreated {pid: uuid, short_no: "#000123"} — и при создании, и при повторе
            («Идемпотентность через tg_user_id: повторный вызов возвращает существующий pid»)
  401:      initData невалидна / истекла (require_init_data, PR 1a)
  403:      возрастной гейт: < 18

Вне контракта (docs/DEFECTS-FOUND.md, D-12):
  422 BIRTH_DATE_IN_FUTURE / ошибки валидации тела;
  503 SERVICE_UNAVAILABLE — БД недоступна; 503 SERVICE_MISCONFIGURED — нет BOT_TOKEN
  или неизвестный SERVER_TIMEZONE (fail closed).

Нормы:
  - SEAM-PATCH-1: first-launch Mini App — единственная точка создания участника;
    403 для неизвестного tg_user_id НЕ отдаётся (решение Автора; 01-architecture.md;
    Б14 R327 перекрыт SEAM-1, D-9 п.2);
  - ADD3 INV-AGE-GATE-BEFORE-PID: hard-check даты рождения ДО любого обращения к БД;
    при < 18 строка tg_user_registry не создаётся;
  - tg_user_id — ТОЛЬКО из проверенного InitDataContext, никогда из тела запроса;
  - «сегодня» — дата в SERVER_TIMEZONE (Europe/Moscow), явно, а не по TZ процесса
    (решение Автора; tz участника на first-launch ещё неизвестен);
  - дата рождения не хранится и не логируется (решение Автора);
  - ВРЕМЕННО: pid создаётся сразу после проверки возраста, без legal_consents —
    БЛОКЕР до любого внешнего доступа (D-10);
  - participant_state не пишется (единственный писатель — проектор, E1/INV-1; отдельный PR).

Лог: только tg_user_id и исход (created / existing); для отказа по возрасту —
только reason=underage, без tg_user_id (решение Автора). Имя, username, initData — никогда.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.session import get_db_session
from app.participants import format_short_no, get_or_create_participant
from app.telegram_init_data import InitDataContext, require_init_data

logger = logging.getLogger(__name__)

# Префикс /miniapp/v1 и проверка initData — в main.py (роутер miniapp_v1).
router = APIRouter(prefix="/onboarding", tags=["onboarding"])

ADULT_AGE_YEARS = 18  # Д-05 / ADD3: today - ДР >= 18 лет


class FirstLaunchRequest(BaseModel):
    # Лишние поля (в т.ч. tg_user_id) игнорируются: pydantic по умолчанию extra="ignore".
    birth_date: date


class PidCreated(BaseModel):
    pid: str
    short_no: str


def full_years(birth_date: date, today: date) -> int:
    """Полных лет на дату today."""
    years = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        years -= 1
    return years


def _utc_now() -> datetime:
    """Отдельная функция — чтобы тесты могли зафиксировать «сейчас»."""
    return datetime.now(timezone.utc)


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def today_in_server_timezone(settings: Settings) -> date:
    try:
        tz = ZoneInfo(settings.server_timezone)
    except (ZoneInfoNotFoundError, ValueError):
        logger.error("first-launch: неизвестный SERVER_TIMEZONE — запрос отклонён (503)")
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "SERVICE_MISCONFIGURED",
            "Сервис временно недоступен",
        ) from None
    return _utc_now().astimezone(tz).date()


@router.post(
    "/first-launch",
    status_code=status.HTTP_201_CREATED,
    response_model=PidCreated,
    responses={
        401: {"description": "initData невалидна / истекла (TG_INIT_MISSING / TG_INIT_INVALID)"},
        403: {"description": "Возрастной гейт: < 18 (AGE_GATE_UNDERAGE)"},
        422: {"description": "Дата рождения в будущем / невалидное тело (вне контракта, D-12)"},
        503: {"description": "SERVICE_UNAVAILABLE (БД) / SERVICE_MISCONFIGURED (вне контракта)"},
    },
)
def first_launch(
    body: FirstLaunchRequest,
    init_data: InitDataContext = Depends(require_init_data),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_db_session),
) -> PidCreated:
    # --- 1. Hard-check возраста (ADD3) — до любого обращения к БД ---
    today = today_in_server_timezone(settings)
    if body.birth_date > today:
        logger.info("first-launch отклонён: reason=birth_date_in_future")
        raise _error(422, "BIRTH_DATE_IN_FUTURE", "Дата рождения в будущем")
    if full_years(body.birth_date, today) < ADULT_AGE_YEARS:
        # ADD3 on_underage: pid не создаётся. В лог — без tg_user_id (решение Автора).
        logger.info("first-launch отклонён: reason=underage")
        raise _error(
            status.HTTP_403_FORBIDDEN, "AGE_GATE_UNDERAGE", "Возрастной гейт: младше 18 лет"
        )

    # --- 2. Создать / найти участника (идемпотентно, уникальность в БД) ---
    tg_user_id = init_data.tg_user_id  # только из проверенной initData
    try:
        participant = get_or_create_participant(session, tg_user_id)
    except (OperationalError, InterfaceError) as exc:
        session.rollback()
        # Текст исключения не логируем: в нём может быть адрес БД.
        logger.error(
            "first-launch: БД недоступна tg_user_id=%s error=%s",
            tg_user_id,
            type(exc).__name__,
        )
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "SERVICE_UNAVAILABLE",
            "Сервис временно недоступен. Попробуйте позже.",
        ) from None

    logger.info(
        "first-launch: tg_user_id=%s outcome=%s",
        tg_user_id,
        "created" if participant.created else "existing",
    )
    return PidCreated(pid=str(participant.pid), short_no=format_short_no(participant.short_no))
