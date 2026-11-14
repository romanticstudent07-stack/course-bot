"""apps/api/main.py — точка входа FastAPI (course-bot backend).

Запуск в контейнере: uvicorn main:app --host 0.0.0.0 --port 8080
(см. Dockerfile; публикация на хосте — только 127.0.0.1, docker-compose.dev.yml).

Маршруты:
  GET  /healthz                              — liveness (без initData, без rate-limit)
  POST /miniapp/v1/onboarding/first-launch   — SEAM-1: создание/поиск участника
                                               (tg_user_registry), initData проверяется
  GET  /miniapp/v1/consents                  — свои согласия (1e-2), только чтение
  GET  /miniapp/v1/texts/{key}               — текст из text_registry по ключу (1d)
  POST /miniapp/v1/texts/bulk                — пачка текстов по списку ключей (1d)
  GET  /miniapp/v1/day/current               — текущий день участника (iter2-api-1),
                                               только чтение
  GET  /miniapp/v1/checkup/config            — конфиг Чек-Апа из файла (api-i3-1), без БД
  POST /miniapp/v1/checkup/submit            — 15 ответов Чек-Апа → зона (api-i3-1),
                                               measurements_log, X-Client-Op-Id
  GET  /miniapp/v1/onboarding/form/config    — конфиг анкеты из файлов (api-i3-2), без БД
  GET  /miniapp/v1/onboarding/form           — отправлена ли анкета (api-i3-2), только чтение
  POST /miniapp/v1/onboarding/form           — анкета один раз (api-i3-2): onboarding_form,
                                               вес в measurements_log, событие tz_set
  GET  /miniapp/v1/me/card                   — карточка участника (api-i3-3), только чтение
  GET  /miniapp/v1/me/change-map             — Карта изменений на лету (api-i3-3), только чтение
  POST /miniapp/v1/support/question        — вопрос в поддержку (api-sup-1, Р-19): support_questions + outbox, X-Client-Op-Id
  POST /security/csp-report                  — приёмник CSP-репортов (E2), без initData
                                               (security: [] в miniapp-api-contract.yaml),
                                               без rate-limit

Все маршруты /miniapp/v1/** подключаются ТОЛЬКО через miniapp_v1 — у него
зависимости require_init_data (HMAC + TTL) и затем rate_limit (B-1: Redis,
RATE_LIMIT_PER_MINUTE на tg_user_id, fail-open). Новые роутеры Mini App добавлять сюда же.

Контент дня (apps/api/content) загружается и проверяется в create_app:
битый контент → исключение DayContentError, api не стартует (iter2-api-1).
Конфиг Чек-Апа (apps/api/config/checkup) — так же: битый → CheckupConfigError (api-i3-1).
Конфиг анкеты (apps/api/config/onboarding: form.json, cities.csv) — так же: битый → OnboardingFormConfigError (api-i3-2).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, FastAPI

from app.checkup_config import get_checkup_config
from app.config import get_settings
from app.day_content import load_day_content
from app.errors import install_error_handlers
from app.onboarding_form_config import get_onboarding_form_config
from app.rate_limit import rate_limit
from app.routers import (
    checkup,
    consents,
    day,
    health,
    me,
    onboarding,
    onboarding_form,
    security,
    support,
    texts,
)
from app.telegram_init_data import require_init_data


def build_miniapp_v1_router(*routers: APIRouter) -> APIRouter:
    """Общий роутер /miniapp/v1/**: require_init_data, затем rate_limit на КАЖДОМ маршруте.

    Порядок важен: без валидной initData — 401 раньше 429, счётчик не трогается.
    rate_limit сам зависит от require_init_data; FastAPI кэширует результат в запросе.
    """
    miniapp_v1 = APIRouter(
        prefix="/miniapp/v1",
        dependencies=[Depends(require_init_data), Depends(rate_limit)],
    )
    for router in routers:
        miniapp_v1.include_router(router)
    return miniapp_v1


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    # Контент дня: битый или отсутствующий → исключение, api не стартует (iter2-api-1).
    load_day_content()
    # Конфиг Чек-Апа: битый или отсутствующий → CheckupConfigError, api не стартует (api-i3-1).
    get_checkup_config()
    # Конфиг анкеты: битый form.json или cities.csv → OnboardingFormConfigError (api-i3-2).
    get_onboarding_form_config()

    app = FastAPI(
        title="course-bot API",
        version="0.1.0-iteration-0a",
        # OpenAPI/Swagger оставляем: публикация только на 127.0.0.1 + туннель.
        # TODO(прод): решить, закрывать ли /docs наружу.
    )
    install_error_handlers(app)
    app.include_router(health.router)

    # /miniapp/v1/** — проверка initData и rate-limit на уровне роутера, для всех маршрутов.
    app.include_router(
        build_miniapp_v1_router(
            onboarding.router,
            consents.router,
            texts.router,
            day.router,
            checkup.router,
            onboarding_form.router,
            me.router,
            support.router,
        )
    )

    app.include_router(security.router)
    return app


app = create_app()
