"""/miniapp/v1/onboarding/* — онбординг SEAM-1 (Итерации 1b+1c, 1e-1a).

Контракт: build/miniapp-api-contract.yaml → POST /miniapp/v1/onboarding/first-launch
  request:  {birth_date: date, consents: ["C0", "C1", ...]}
            (consents — расширение контракта, решение Автора «2А», docs/DEFECTS-FOUND.md D-10)
  201:      PidCreated {pid: uuid, short_no: "#000123"} — и при создании, и при повторе
            («Идемпотентность через tg_user_id: повторный вызов возвращает существующий pid»)
  401:      initData невалидна / истекла (require_init_data, PR 1a)
  403:      возрастной гейт: < 18

Вне контракта (docs/DEFECTS-FOUND.md, D-10, D-12):
  422 CONSENTS_REQUIRED {details: {missing: [...]}} — нет обязательных согласий (C0, C1);
  422 CONSENT_NOT_SUPPORTED {details: {unsupported: [...]}} — согласие, которое
      first-launch не принимает (C2–C6: не в И1 или со своим экраном, как C5);
  422 BIRTH_DATE_IN_FUTURE / ошибки валидации тела (нет consents, дубли, id вне C0–C6);
  503 SERVICE_UNAVAILABLE — БД недоступна; 503 SERVICE_MISCONFIGURED — нет BOT_TOKEN,
  неизвестный SERVER_TIMEZONE или нет текста согласия в text_registry (fail closed).

Порядок (docs/tasks/1e-1.md, раздел 7 — НЕ МЕНЯТЬ):
  1) initData (роутер) → 2) тело (Pydantic) → 3) возраст БЕЗ БД → 403
  → 4) обязательные согласия → 422 → 5) ОДНА транзакция: тексты согласий из text_registry
  (нет текста → откат, 503) → участник (get_or_create) → consent_events: give для каждого
  присланного kind, у которого у pid ещё нет give → commit.

Нормы:
  - SEAM-PATCH-1: first-launch Mini App — единственная точка создания участника;
    403 для неизвестного tg_user_id НЕ отдаётся (решение Автора; D-9 п.2);
  - ADD3 INV-AGE-GATE-BEFORE-PID: hard-check даты рождения ДО любого обращения к БД;
    при < 18 строка tg_user_registry не создаётся;
  - B-2: pid создаётся только вместе с согласиями C0 и C1, в одной транзакции;
  - текст согласия выбирает СЕРВЕР (CONSENT_TEXT_KEYS), клиент шлёт только id;
  - tg_user_id — ТОЛЬКО из проверенного InitDataContext, никогда из тела запроса;
  - «сегодня» — дата в SERVER_TIMEZONE (Europe/Moscow), явно, а не по TZ процесса;
  - дата рождения не хранится и не логируется (решение Автора);
  - ip и ua в consent_events не заполняются (NULL): за туннелем IP недостоверен;
  - participant_state не пишется (единственный писатель — проектор, E1/INV-1).

Лог: только tg_user_id, исход (created / existing) и число новых согласий; для отказов
по возрасту и согласиям — только reason, без tg_user_id. Имя, username, initData,
дата рождения, текст согласия — никогда.
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import (
    CONSENT_ACTION_GIVE,
    CREATED_VIA_MINI_APP_FIRST_LAUNCH,
    ConsentEvent,
    TextRegistry,
)
from app.db.session import get_db_session
from app.participants import Participant, format_short_no, get_or_create_participant
from app.telegram_init_data import InitDataContext, require_init_data

logger = logging.getLogger(__name__)

# Префикс /miniapp/v1 и проверка initData — в main.py (роутер miniapp_v1).
router = APIRouter(prefix="/onboarding", tags=["onboarding"])

ADULT_AGE_YEARS = 18  # Д-05 / ADD3: today - ДР >= 18 лет

# Consent.id из контракта; тот же список — app.db.models.CONSENT_KINDS (тест сверяет).
ConsentId = Literal["C0", "C1", "C2", "C3", "C4", "C5", "C6"]

# Решение Автора «В1 А»: до pid — C0 (18+) и C1 (ПДн).
REQUIRED_AT_FIRST_LAUNCH: frozenset[str] = frozenset({"C0", "C1"})
# Какой текст из text_registry принят вместе с согласием (выбирает сервер).
CONSENT_TEXT_KEYS: dict[str, str] = {
    "C0": "legal.consent_c0_age_18_plus",
    "C1": "legal.consent_c1_pdn",
}


class FirstLaunchRequest(BaseModel):
    # Лишние поля (в т.ч. tg_user_id) игнорируются: pydantic по умолчанию extra="ignore".
    birth_date: date
    consents: list[ConsentId]

    @field_validator("consents")
    @classmethod
    def _consents_unique(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("consents: id не должны повторяться")
        return value


class PidCreated(BaseModel):
    pid: str
    short_no: str


class ConsentTextMissingError(Exception):
    """В text_registry нет текста согласия — pid не создаётся (fail closed)."""

    def __init__(self, keys: list[str]) -> None:
        super().__init__(", ".join(keys))
        self.keys = keys


@dataclass(frozen=True)
class Registration:
    participant: Participant
    consents_recorded: int  # сколько строк give записано этим вызовом


def full_years(birth_date: date, today: date) -> int:
    """Полных лет на дату today."""
    years = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        years -= 1
    return years


def _utc_now() -> datetime:
    """Отдельная функция — чтобы тесты могли зафиксировать «сейчас»."""
    return datetime.now(timezone.utc)


def _error(
    status_code: int, code: str, message: str, details: dict[str, Any] | None = None
) -> HTTPException:
    detail: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        detail["details"] = details
    return HTTPException(status_code=status_code, detail=detail)


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


def register_with_consents(
    session: Session, tg_user_id: int, kinds: Sequence[str]
) -> Registration:
    """Шаг 5 — ОДНА транзакция: тексты → участник → consent_events → commit.

    kinds — только из CONSENT_TEXT_KEYS (обработчик проверяет до вызова).
    Ошибка на любом шаге → commit не выполняется; откат делает вызывающий
    (или закрытие сессии).
    """
    text_keys = {kind: CONSENT_TEXT_KEYS[kind] for kind in kinds}
    wanted = sorted(set(text_keys.values()))
    rows = session.execute(
        select(TextRegistry.key, TextRegistry.body, TextRegistry.registry_version).where(
            TextRegistry.key.in_(wanted)
        )
    ).all()
    texts = {row.key: row for row in rows}
    missing = [key for key in wanted if key not in texts]
    if missing:
        raise ConsentTextMissingError(missing)

    participant = get_or_create_participant(session, tg_user_id)
    given = set(
        session.execute(
            select(ConsentEvent.kind).where(
                ConsentEvent.pid == participant.pid,
                ConsentEvent.action == CONSENT_ACTION_GIVE,
            )
        ).scalars()
    )
    new_kinds = sorted(set(kinds) - given)
    table = ConsentEvent.__table__
    for kind in new_kinds:
        source = texts[text_keys[kind]]
        session.execute(
            table.insert().values(
                pid=participant.pid,
                kind=kind,
                action=CONSENT_ACTION_GIVE,
                ver_of_text=source.registry_version,
                text_key=source.key,
                text_snapshot=source.body,
                created_via=CREATED_VIA_MINI_APP_FIRST_LAUNCH,
            )
        )
    session.commit()
    return Registration(participant=participant, consents_recorded=len(new_kinds))


@router.post(
    "/first-launch",
    status_code=status.HTTP_201_CREATED,
    response_model=PidCreated,
    responses={
        401: {"description": "initData невалидна / истекла (TG_INIT_MISSING / TG_INIT_INVALID)"},
        403: {"description": "Возрастной гейт: < 18 (AGE_GATE_UNDERAGE)"},
        422: {
            "description": "CONSENTS_REQUIRED / CONSENT_NOT_SUPPORTED / BIRTH_DATE_IN_FUTURE / "
            "невалидное тело (вне контракта, D-10, D-12)"
        },
        503: {"description": "SERVICE_UNAVAILABLE (БД) / SERVICE_MISCONFIGURED (вне контракта)"},
    },
)
def first_launch(
    body: FirstLaunchRequest,
    init_data: InitDataContext = Depends(require_init_data),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_db_session),
) -> PidCreated:
    # --- 3. Hard-check возраста (ADD3) — до любого обращения к БД ---
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

    # --- 4. Обязательные согласия (B-2) — тоже до БД ---
    sent = set(body.consents)
    missing = sorted(REQUIRED_AT_FIRST_LAUNCH - sent)
    if missing:
        logger.info("first-launch отклонён: reason=consents_required missing=%s", ",".join(missing))
        raise _error(
            422,
            "CONSENTS_REQUIRED",
            "Нужны обязательные согласия",
            details={"missing": missing},
        )
    unsupported = sorted(sent - set(CONSENT_TEXT_KEYS))
    if unsupported:
        logger.info(
            "first-launch отклонён: reason=consent_not_supported kinds=%s", ",".join(unsupported)
        )
        raise _error(
            422,
            "CONSENT_NOT_SUPPORTED",
            "Это согласие даётся не на этом шаге",
            details={"unsupported": unsupported},
        )

    # --- 5. Одна транзакция: тексты → участник → согласия ---
    tg_user_id = init_data.tg_user_id  # только из проверенной initData
    try:
        registration = register_with_consents(session, tg_user_id, body.consents)
    except ConsentTextMissingError as exc:
        session.rollback()
        logger.error(
            "first-launch: нет текста согласия в text_registry keys=%s — pid не создан (503)",
            ",".join(exc.keys),
        )
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "SERVICE_MISCONFIGURED",
            "Сервис временно недоступен",
        ) from None
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

    participant = registration.participant
    logger.info(
        "first-launch: tg_user_id=%s outcome=%s consents_recorded=%d",
        tg_user_id,
        "created" if participant.created else "existing",
        registration.consents_recorded,
    )
    return PidCreated(pid=str(participant.pid), short_no=format_short_no(participant.short_no))
