"""apps/api/main.py — точка входа FastAPI (course-bot backend).

Запуск в контейнере: uvicorn main:app --host 0.0.0.0 --port 8080
(см. Dockerfile; публикация на хосте — только 127.0.0.1, docker-compose.dev.yml).

Итерация 0-А — скелет:
  GET  /healthz                              — liveness
  POST /miniapp/v1/onboarding/first-launch   — mock (SEAM-1, реализация в Итерации 1)
  POST /security/csp-report                  — приёмник CSP-репортов (E2)
"""
from __future__ import annotations

import logging

from fastapi import FastAPI

from app.config import get_settings
from app.errors import install_error_handlers
from app.routers import health, onboarding, security


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
    app.include_router(onboarding.router)
    app.include_router(security.router)
    return app


app = create_app()
