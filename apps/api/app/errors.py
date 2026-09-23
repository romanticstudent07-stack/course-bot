"""Единый формат ошибок — components.schemas.Error из miniapp-api-contract.yaml."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def _http_exc(_: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, dict) and "code" in detail:
            payload = detail
        else:
            payload = {"code": f"HTTP_{exc.status_code}", "message": str(detail)}
        return JSONResponse(status_code=exc.status_code, content=payload, headers=exc.headers)
