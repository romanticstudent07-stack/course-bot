"""apps/api/main.py — точка входа FastAPI (course-bot backend).

Запуск в контейнере: uvicorn main:app --host 0.0.0.0 --port 8080
(см. Dockerfile; публикация на хосте — только 127.0.0.1, docker-compose.dev.yml).

Маршруты:
  GET  /healthz                              — liveness (без initData)
  POST /miniapp/v1/onboarding/first-launch   — mock (SEAM-1), initData проверяется
  POST /security/csp-report                  — приёмник CSP-репортов (E2), без initData
                                               (security: [] в miniapp-api-contract.yaml)

Все маршруты /miniapp/v1/** подключаются ТОЛЬКО через miniapp_v1 — у него
зависимость require_init_data (HMAC + TTL). Новые роутеры Mini App добавлять сюда же.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, FastAPI

from app.config import get_settings
from app.errors import install_error_handlers
from app.routers import health, onboarding, security
from app.telegram_init_data import require_init_data


def build_miniapp_v1_router(*routers: APIRouter) -> APIRouter:
    """Общий роутер /miniapp/v1/**: require_init_data на КАЖДОМ вложенном маршруте."""
    miniapp_v1 = APIRouter(prefix="/miniapp/v1", dependencies=[Depends(require_init_data)])
    for router in routers:
        miniapp_v1.include_router(router)
    return miniapp_v1


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    app = FastAPI(
        title="course-bot API",
        version="0.1.0-iteration-0a",
        # OpenAPI/Swagger оставляем: публикация только на 127.0.0.1 + туннель.
        # TODO(прод): решить, закрывать ли /docs наружу.
    )
    install_error_handlers(app)
    app.include_router(health.router)

    # /miniapp/v1/** — проверка initData на уровне роутера, для всех маршрутов.
    app.include_router(build_miniapp_v1_router(onboarding.router))

    app.include_router(security.router)
    return app


app = create_app()
