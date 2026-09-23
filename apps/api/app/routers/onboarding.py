"""/miniapp/v1/onboarding/* — онбординг SEAM-1.

ИТЕРАЦИЯ 0-А: MOCK. БД не трогается, pid НЕ создаётся.

Контракт: build/miniapp-api-contract.yaml → POST /miniapp/v1/onboarding/first-launch
  request:  {birth_date: date}
  201:      PidCreated {pid: uuid, short_no: "#000123"}
  401:      initData невалидна / истекла
  403:      возрастной гейт: < 18

Нормы, которые реальная реализация (Итерация 1) обязана соблюсти:
  - SEAM-PATCH-1: first-launch Mini App — единственная точка создания участника;
  - ADD3 INV-AGE-GATE-BEFORE-PID: pid не создаётся до hard-check даты рождения;
    порядок [age_soft_checkbox, age_hard_check_dob, legal_consents, pid_creation];
  - возраст считается по локальной дате участника (tz_at(pid_candidate));
  - идемпотентность по tg_user_id: повтор возвращает существующий pid;
  - initData валидируется на сервере (require_init_data).

Мок сейчас: возвращает 501 NOT_IMPLEMENTED с тем же форматом ошибки, что в контракте
(components.schemas.Error). Фиктивный pid не выдаётся намеренно: клиент не должен
получить «похожий на настоящий» идентификатор, которого нет в БД.
Возрастной гейт уже проверяется, чтобы форма ответа 403 была стабильной.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.telegram_init_data import InitDataContext, require_init_data

router = APIRouter(prefix="/miniapp/v1/onboarding", tags=["onboarding"])

ADULT_AGE_YEARS = 18  # Д-05 / ADD3: today - ДР >= 18 лет


class FirstLaunchRequest(BaseModel):
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


@router.post(
    "/first-launch",
    status_code=status.HTTP_201_CREATED,
    response_model=PidCreated,
    responses={
        401: {"description": "initData невалидна / истекла"},
        403: {"description": "Возрастной гейт: < 18"},
        501: {"description": "Итерация 0-А: mock, pid не создаётся"},
    },
)
async def first_launch(
    body: FirstLaunchRequest,
    init_data: InitDataContext = Depends(require_init_data),
) -> PidCreated:
    # TODO(Итерация 1): «сегодня» — локальная дата участника (tz_at), а не дата сервера.
    today = date.today()
    if body.birth_date > today:
        raise HTTPException(
            status_code=422,  # константа HTTP_422_* переименована в Starlette 1.x
            detail={"code": "BIRTH_DATE_IN_FUTURE", "message": "Дата рождения в будущем"},
        )
    if full_years(body.birth_date, today) < ADULT_AGE_YEARS:
        # ADD3 on_underage: pid не создаётся, мягкая блокировка на клиенте.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "AGE_GATE_UNDERAGE", "message": "Возрастной гейт: младше 18 лет"},
        )

    # TODO(Итерация 1): реальная валидация initData (init_data.verified должно быть True),
    # затем legal_consents → создание pid в tg_user_registry (идемпотентно по tg_user_id).
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "code": "NOT_IMPLEMENTED",
            "message": "first-launch: mock Итерации 0-А, pid не создаётся",
            "details": {"init_data_verified": init_data.verified},
        },
    )
