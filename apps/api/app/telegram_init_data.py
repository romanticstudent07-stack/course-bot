"""apps/api/app/telegram_init_data.py — валидация Telegram initData.

ИТЕРАЦИЯ 0-А: ЗАГЛУШКА. Реальная реализация — Итерация 1 (build-order.md).

Контракт (AGENTS.md; build/miniapp-api-contract.yaml → securitySchemes.TelegramInitData):
  1. secret_key       = HMAC-SHA256(key="WebAppData", msg=BOT_TOKEN)
  2. data_check_string = пары key=value (кроме hash), сортировка по ключу, через "\\n"
  3. expected_hash    = HMAC-SHA256(key=secret_key, msg=data_check_string)
  4. сравнить с hash (constant-time)
  5. проверить auth_date: TTL 24 ч; для /refund, /erasure_* — 1 ч
  Валидатор строгий по безопасности, но устойчив к новым необязательным полям
  (miniapp-security-checklist.md, п.7).

Что делает заглушка сейчас:
  - требует заголовок X-Telegram-Init-Data (без него — 401 TG_INIT_MISSING);
  - разбирает строку и достаёт user.id, НО ПОДПИСЬ НЕ ПРОВЕРЯЕТ;
  - результат помечен verified=False — ни один код не должен принимать
    необратимых решений на его основе, пока verified=False.

Никогда не использовать initDataUnsafe клиента — только сырую строку initData.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException, status

logger = logging.getLogger(__name__)

INIT_DATA_HEADER = "X-Telegram-Init-Data"


@dataclass(frozen=True)
class InitDataContext:
    """Результат разбора initData."""

    tg_user_id: int | None
    auth_date: int | None
    raw: str
    verified: bool  # False до Итерации 1: подпись НЕ проверена


def _unauthorized(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": code, "message": message},
    )


def parse_init_data_unverified(raw: str) -> InitDataContext:
    """Разбирает initData БЕЗ проверки подписи (заглушка Итерации 0-А)."""
    pairs = dict(parse_qsl(raw, keep_blank_values=True, strict_parsing=False))
    if "hash" not in pairs:
        raise _unauthorized("TG_INIT_INVALID", "initData не содержит hash")

    tg_user_id: int | None = None
    user_raw = pairs.get("user")
    if user_raw:
        try:
            user_obj = json.loads(user_raw)
            tg_user_id = int(user_obj["id"])
        except (ValueError, KeyError, TypeError) as exc:
            raise _unauthorized("TG_INIT_INVALID", "initData.user повреждён") from exc

    auth_date: int | None = None
    if pairs.get("auth_date"):
        try:
            auth_date = int(pairs["auth_date"])
        except ValueError as exc:
            raise _unauthorized("TG_INIT_INVALID", "initData.auth_date повреждён") from exc

    return InitDataContext(tg_user_id=tg_user_id, auth_date=auth_date, raw=raw, verified=False)


async def require_init_data(
    x_telegram_init_data: str | None = Header(default=None, alias=INIT_DATA_HEADER),
) -> InitDataContext:
    """FastAPI-зависимость для /miniapp/v1/**.

    TODO(Итерация 1): заменить на полную HMAC-валидацию + TTL auth_date
    (см. docstring модуля). До этого verified=False.
    """
    if not x_telegram_init_data:
        raise _unauthorized("TG_INIT_MISSING", f"Нет заголовка {INIT_DATA_HEADER}")
    ctx = parse_init_data_unverified(x_telegram_init_data)
    logger.warning("initData НЕ валидирован (заглушка Итерации 0-А), tg_user_id=%s", ctx.tg_user_id)
    return ctx
