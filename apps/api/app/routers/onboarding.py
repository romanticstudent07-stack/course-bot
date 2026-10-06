"""/miniapp/v1/onboarding/* — онбординг SEAM-1 (Итерации 1b+1c, 1e-1a, projector-1, returning-1).

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
  (нет текста → откат, 503) → участник (get_or_create, строка заблокирована) → события
  согласий pid → consent_events: give для каждого присланного kind, согласие по которому
  НЕ действует (отозвано, сменился текст или give не было; returning-1, D-22) →
  participant_events (projector-1) → commit.

Повторное согласие (returning-1, D-22): раньше «уже данные согласия повторно не
  записываются»; теперь give пишется, если consent_status.consent_problem(...) is not None.
  Действующее согласие → 0 новых строк. revoke не пишется и не меняется.

Событие (docs/tasks/projector-1.md, раздел 7; D-16): только если pid СОЗДАН этим вызовом —
  INSERT participant_events kind mini_app_first_consent, payload {"schema_version": 1},
  actor / actor_role system — в той же транзакции, после consent_events, до commit.
  Повтор (pid уже есть, в т.ч. повторное согласие) события не пишет. Ошибка INSERT события —
  тот же путь, что ошибка INSERT consent_events (commit не выполняется, pid не создан).

GET /miniapp/v1/onboarding/status (returning-1, D-22; вне контракта до правки DOCS):
  параметров и тела нет; tg_user_id — только из InitDataContext; только чтение, без commit.
  200, ровно одна форма:
    {"status": "returning", "short_no": "#000123"} — активная строка есть, C0 и C1 действуют;
    {"status": "reconsent", "reasons": [...]} — строка есть, хоть одно не действует
        (перечень — consent_status.REASONS); short_no не отдаётся;
    {"status": "new"} — строки нет ИЛИ она tombstoned (erased): тело одинаковое.
  pid не отдаётся никогда. 401 / 429 — роутер miniapp_v1 (main.py). 403 не отдаётся.
  503 SERVICE_UNAVAILABLE — БД недоступна; 503 SERVICE_MISCONFIGURED — нет текста C0/C1.
  participant_state и проектор для решения НЕ используются (INV-1).

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
  - participant_state не пишется (единственный писатель — проектор, E1/INV-1);
    API пишет только событие в participant_events, состояние строит проектор (projector-2).

Лог first-launch: только tg_user_id, исход (created / existing) и число новых согласий;
для отказов по возрасту и согласиям — только reason, без tg_user_id.
Лог status: «status: tg_user_id=<id> status=<returning|reconsent|new>».
Имя, username, initData, дата рождения, текст согласия, pid, short_no, reasons — никогда.
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
from app.consent_status import (
    CONSENT_TEXT_KEYS,
    STATUS_KINDS,
    ConsentTextMissingError,
    consent_problem,
    current_texts,
    load_events,
    reasons,
    snapshot_of,
)
from app.db.models import (
    ACTOR_SYSTEM,
    CONSENT_ACTION_GIVE,
    CREATED_VIA_MINI_APP_FIRST_LAUNCH,
    EVENT_KIND_MINI_APP_FIRST_CONSENT,
    ConsentEvent,
    ParticipantEvent,
    TextRegistry,
)
from app.db.session import get_db_session
from app.participants import (
    Participant,
    find_active_participant,
    format_short_no,
    get_or_create_participant,
)
from app.telegram_init_data import InitDataContext, require_init_data

logger = logging.getLogger(__name__)

# Префикс /miniapp/v1 и проверка initData — в main.py (роутер miniapp_v1).
router = APIRouter(prefix="/onboarding", tags=["onboarding"])

ADULT_AGE_YEARS = 18  # Д-05 / ADD3: today - ДР >= 18 лет

# Consent.id из контракта; тот же список — app.db.models.CONSENT_KINDS (тест сверяет).
ConsentId = Literal["C0", "C1", "C2", "C3", "C4", "C5", "C6"]

# Решение Автора «В1 А»: до pid — C0 (18+) и C1 (ПДн).
REQUIRED_AT_FIRST_LAUNCH: frozenset[str] = frozenset({"C0", "C1"})
# CONSENT_TEXT_KEYS и ConsentTextMissingError живут в app.consent_status (returning-1)
# и импортированы сюда под теми же именами.

# payload события first-launch (projector-1, раздел 7). Бэкфилл 0005 добавляет "backfill".
FIRST_CONSENT_PAYLOAD: dict[str, Any] = {"schema_version": 1}


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


class OnboardingStatus(BaseModel):
    """Ответ GET /onboarding/status; пустые поля не отдаются (response_model_exclude_none)."""

    status: Literal["returning", "reconsent", "new"]
    short_no: str | None = None
    reasons: list[str] | None = None


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
    """Шаг 5 — ОДНА транзакция: тексты → участник → события → consent_events → событие → commit.

    kinds — только из CONSENT_TEXT_KEYS (обработчик проверяет до вызова).
    give пишется только по kind, согласие по которому не действует (consent_problem).
    Гонка при reconsent: FOR UPDATE в get_or_create держит строку до commit, второй вызов читает события после commit первого и новых give не пишет.
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
    # События читаются ПОСЛЕ получения (и блокировки) строки участника.
    events = load_events(session, participant.pid)
    new_kinds = [
        kind
        for kind in sorted(set(kinds))
        if consent_problem(events, kind, text_keys[kind], texts[text_keys[kind]].body)
        is not None
    ]
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
                text_snapshot=snapshot_of(source.body),
                created_via=CREATED_VIA_MINI_APP_FIRST_LAUNCH,
            )
        )
    if participant.created:
        # projector-1 (D-16): I2 pre_registered → onboarding, trigger mini_app_first_consent.
        session.execute(
            ParticipantEvent.__table__.insert().values(
                pid=participant.pid,
                kind=EVENT_KIND_MINI_APP_FIRST_CONSENT,
                payload=dict(FIRST_CONSENT_PAYLOAD),
                actor=ACTOR_SYSTEM,
                actor_role=ACTOR_SYSTEM,
            )
        )
    session.commit()
    return Registration(participant=participant, consents_recorded=len(new_kinds))


def read_onboarding_status(session: Session, tg_user_id: int) -> OnboardingStatus:
    """Кто открыл Mini App: returning / reconsent / new. Только чтение, без commit.

    Тексты C0/C1 проверяются всегда (fail closed): нет текста → ConsentTextMissingError.
    """
    texts = current_texts(session, STATUS_KINDS)
    found = find_active_participant(session, tg_user_id)
    if found is None:
        # Нет строки или она tombstoned (erased) — одно и то же тело.
        return OnboardingStatus(status="new")
    pid, short_no = found
    problems = reasons(load_events(session, pid), texts, STATUS_KINDS)
    if problems:
        return OnboardingStatus(status="reconsent", reasons=problems)
    return OnboardingStatus(status="returning", short_no=format_short_no(short_no))


@router.get(
    "/status",
    response_model=OnboardingStatus,
    response_model_exclude_none=True,
    responses={
        401: {"description": "initData невалидна / истекла (TG_INIT_MISSING / TG_INIT_INVALID)"},
        429: {"description": "rate-limit (B-1)"},
        503: {"description": "SERVICE_UNAVAILABLE (БД) / SERVICE_MISCONFIGURED (нет текста)"},
    },
)
def onboarding_status(
    init_data: InitDataContext = Depends(require_init_data),
    session: Session = Depends(get_db_session),
) -> OnboardingStatus:
    tg_user_id = init_data.tg_user_id  # только из проверенной initData
    try:
        result = read_onboarding_status(session, tg_user_id)
    except ConsentTextMissingError as exc:
        logger.error(
            "status: нет текста согласия в text_registry keys=%s (503)", ",".join(exc.keys)
        )
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "SERVICE_MISCONFIGURED",
            "Сервис временно недоступен",
        ) from None
    except (OperationalError, InterfaceError) as exc:
        # Текст исключения не логируем: в нём может быть адрес БД.
        logger.error(
            "status: БД недоступна tg_user_id=%s error=%s", tg_user_id, type(exc).__name__
        )
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "SERVICE_UNAVAILABLE",
            "Сервис временно недоступен. Попробуйте позже.",
        ) from None
    logger.info("status: tg_user_id=%s status=%s", tg_user_id, result.status)
    return result


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

    # --- 5. Одна транзакция: тексты → участник → согласия → событие ---
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
