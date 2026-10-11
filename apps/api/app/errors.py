"""Единый формат ошибок — components.schemas.Error из miniapp-api-contract.yaml.

HTTPException — как раньше (detail-dict с "code" отдаётся как есть).
RequestValidationError (422) — VALIDATION_ERROR; в details.errors только loc и type,
без input / ctx / msg / url (D-18: значения полей, например дата рождения, клиенту не уходят).
Любое непойманное исключение — 500 INTERNAL_ERROR через http-middleware; в лог только имя
класса исключения: без текста, без traceback (там бывают ПДн и параметры SQL).
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

logger = logging.getLogger("app.errors")

VALIDATION_ERROR_CODE = "VALIDATION_ERROR"
VALIDATION_ERROR_MESSAGE = "Неверный формат запроса."
INTERNAL_ERROR_CODE = "INTERNAL_ERROR"
INTERNAL_ERROR_MESSAGE = "Внутренняя ошибка. Попробуйте позже."


def _safe_validation_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    """Только loc и type каждой ошибки — без значений из запроса."""
    result: list[dict[str, Any]] = []
    for err in exc.errors():
        loc = [part if isinstance(part, (str, int)) else str(part) for part in err.get("loc", ())]
        result.append({"loc": loc, "type": str(err.get("type", ""))})
    return result


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def _http_exc(_: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, dict) and "code" in detail:
            payload = detail
        else:
            payload = {"code": f"HTTP_{exc.status_code}", "message": str(detail)}
        return JSONResponse(status_code=exc.status_code, content=payload, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation_exc(_: Request, exc: RequestValidationError) -> JSONResponse:
        payload = {
            "code": VALIDATION_ERROR_CODE,
            "message": VALIDATION_ERROR_MESSAGE,
            "details": {"errors": _safe_validation_errors(exc)},
        }
        return JSONResponse(status_code=422, content=payload)

    # Middleware, а не exception_handler(Exception): после такого обработчика Starlette
    # бросает исключение заново, и uvicorn пишет traceback.
    @app.middleware("http")
    async def _internal_error(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:
            logger.error("unhandled exception: %s", type(exc).__name__)
            return JSONResponse(
                status_code=500,
                content={"code": INTERNAL_ERROR_CODE, "message": INTERNAL_ERROR_MESSAGE},
            )
