"""/healthz — liveness для Docker HEALTHCHECK и compose."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    # Только liveness процесса: без обращения к БД/Redis/S3, чтобы падение
    # зависимостей не уводило контейнер в рестарт-цикл. Readiness — позже.
    return {"status": "ok"}
