"""/miniapp/v1/texts/* — чтение текстов из text_registry (Итерация 1d).

Контракт: build/miniapp-api-contract.yaml →
  GET  /miniapp/v1/texts/{key} — текст по ключу;
  POST /miniapp/v1/texts/bulk  — пачка по списку ключей (клиент кэширует в IndexedDB).

Отличия от контракта (решение Автора, docs/DEFECTS-FOUND.md D-14):
  - ключ — шаблон СХЕМЫ (app.texts.KEY_PATTERN), не контракта;
  - 404 TEXT_NOT_FOUND; 422 — ключ не по шаблону / пустой или > 100 ключей;
    503 SERVICE_UNAVAILABLE — БД недоступна.
401 — из общего роутера /miniapp/v1 (main.py, require_init_data).
notes наружу не отдаются. В лог — только тип ошибки БД.
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.texts import KEY_PATTERN, ParticipantText, get_texts_for_participant

logger = logging.getLogger(__name__)

# Префикс /miniapp/v1 и проверка initData — в main.py (роутер miniapp_v1).
router = APIRouter(prefix="/texts", tags=["texts"])

MAX_BULK_KEYS = 100

TextKey = Annotated[str, StringConstraints(pattern=KEY_PATTERN)]


class TextOut(BaseModel):
    key: str
    tone: str
    legal_status: str
    text: str
    plurals_ru: dict[str, str] | None


class TextsBulkRequest(BaseModel):
    keys: list[TextKey] = Field(min_length=1, max_length=MAX_BULK_KEYS)


class TextsBulkResponse(BaseModel):
    texts: list[TextOut]
    missing: list[str]


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _out(view: ParticipantText) -> TextOut:
    return TextOut(
        key=view.key,
        tone=view.tone,
        legal_status=view.legal_status,
        text=view.text,
        plurals_ru=view.plurals_ru,
    )


def _read(session: Session, keys: list[str]) -> dict[str, ParticipantText]:
    try:
        return get_texts_for_participant(session, keys)
    except (OperationalError, InterfaceError) as exc:
        session.rollback()
        # Текст исключения не логируем: в нём может быть адрес БД.
        logger.error("texts: БД недоступна error=%s", type(exc).__name__)
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "SERVICE_UNAVAILABLE",
            "Сервис временно недоступен. Попробуйте позже.",
        ) from None


@router.get(
    "/{key}",
    response_model=TextOut,
    responses={
        401: {"description": "initData невалидна / истекла (TG_INIT_MISSING / TG_INIT_INVALID)"},
        404: {"description": "TEXT_NOT_FOUND"},
        422: {"description": "Ключ не по шаблону схемы (D-14)"},
        503: {"description": "SERVICE_UNAVAILABLE — БД недоступна"},
    },
)
def get_text(
    key: Annotated[str, Path(pattern=KEY_PATTERN)],
    session: Session = Depends(get_db_session),
) -> TextOut:
    view = _read(session, [key]).get(key)
    if view is None:
        raise _error(status.HTTP_404_NOT_FOUND, "TEXT_NOT_FOUND", "Текст не найден")
    return _out(view)


@router.post(
    "/bulk",
    response_model=TextsBulkResponse,
    responses={
        401: {"description": "initData невалидна / истекла (TG_INIT_MISSING / TG_INIT_INVALID)"},
        422: {"description": "Пустой список, больше 100 ключей или ключ не по шаблону"},
        503: {"description": "SERVICE_UNAVAILABLE — БД недоступна"},
    },
)
def get_texts_bulk(
    body: TextsBulkRequest,
    session: Session = Depends(get_db_session),
) -> TextsBulkResponse:
    keys = list(dict.fromkeys(body.keys))  # дубли схлопнуть, порядок запроса сохранить
    found = _read(session, keys)
    return TextsBulkResponse(
        texts=[_out(found[k]) for k in keys if k in found],
        missing=[k for k in keys if k not in found],
    )
