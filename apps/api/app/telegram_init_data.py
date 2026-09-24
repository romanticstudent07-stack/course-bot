"""apps/api/app/telegram_init_data.py — проверка Telegram initData (Итерация 1a).

Источники:
  - AGENTS.md, «Как валидировать initData»;
  - build/miniapp-api-contract.yaml → securitySchemes.TelegramInitData,
    components.responses.Unauthorized (401), schemas.Error;
  - build/miniapp-security-checklist.md §1, §2 (свежесть), §7 (новые поля);
  - core.telegram.org/bots/webapps — «Validating data received via the Mini App».

Алгоритм:
  1. secret_key        = HMAC-SHA256(key="WebAppData", msg=BOT_TOKEN)
  2. data_check_string = все пары key=value, КРОМЕ hash, сортировка по ключу, через "\\n"
                         (поле signature и любые неизвестные поля ОСТАЮТСЯ в строке)
  3. expected_hash     = hex(HMAC-SHA256(key=secret_key, msg=data_check_string))
  4. hmac.compare_digest(expected_hash, hash)
  5. auth_date: не старше max_age и не дальше future_skew в будущем.

Безопасность:
  - ни сырая initData, ни hash, ни BOT_TOKEN, ни data_check_string не попадают
    в ответ, в лог и в InitDataContext;
  - в ответе только два кода: TG_INIT_MISSING / TG_INIT_INVALID (без уточнения причины);
    точная причина (reason) — только в лог;
  - пустой BOT_TOKEN → 503 SERVICE_MISCONFIGURED (fail closed), ERROR в лог;
  - dev-обхода проверки нет и быть не должно.

Никогда не использовать initDataUnsafe клиента — только сырую строку initData.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any
from urllib.parse import parse_qsl

from fastapi import Depends, Header, HTTPException, status

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

INIT_DATA_HEADER = "X-Telegram-Init-Data"
_WEBAPP_DATA_KEY = b"WebAppData"


class InitDataReason(str, Enum):
    """Точная причина отказа. Идёт только в лог, клиенту — нет."""

    MISSING = "missing"  # нет заголовка / пустой заголовок
    MALFORMED = "malformed"  # битая строка, нет обязательных полей
    BAD_SIGNATURE = "bad_signature"  # hash не совпал
    EXPIRED = "expired"  # auth_date старше max_age
    FUTURE = "future"  # auth_date дальше future_skew в будущем


class InitDataError(Exception):
    """Ошибка проверки initData. Сообщение не содержит данных initData."""

    def __init__(self, reason: InitDataReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


@dataclass(frozen=True)
class TelegramUser:
    id: int
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None
    is_premium: bool | None = None
    photo_url: str | None = None
    allows_write_to_pm: bool | None = None


@dataclass(frozen=True)
class InitDataContext:
    """Проверенные данные initData. Сырую строку и hash намеренно не храним."""

    user: TelegramUser
    auth_date: int
    query_id: str | None = None
    start_param: str | None = None
    chat_type: str | None = None
    chat_instance: str | None = None

    @property
    def tg_user_id(self) -> int:
        return self.user.id


def _secret_key(bot_token: str) -> bytes:
    return hmac.new(_WEBAPP_DATA_KEY, bot_token.encode("utf-8"), hashlib.sha256).digest()


def build_data_check_string(pairs: dict[str, str]) -> str:
    """Все пары, кроме hash, по ключу, "key=value" через "\\n"."""
    return "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs) if k != "hash")


def compute_hash(pairs: dict[str, str], bot_token: str) -> str:
    """hex(HMAC-SHA256(secret_key, data_check_string)). Используется и тестами для подписи."""
    return hmac.new(
        _secret_key(bot_token),
        build_data_check_string(pairs).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _parse_pairs(raw: str) -> dict[str, str]:
    try:
        items = parse_qsl(raw, keep_blank_values=True, strict_parsing=True, errors="strict")
    except ValueError as exc:  # включает UnicodeDecodeError
        raise InitDataError(InitDataReason.MALFORMED) from exc
    pairs: dict[str, str] = {}
    for key, value in items:
        if key in pairs:  # повтор ключа — неоднозначная строка
            raise InitDataError(InitDataReason.MALFORMED)
        pairs[key] = value
    return pairs


def _opt_str(obj: dict[str, Any], key: str) -> str | None:
    value = obj.get(key)
    return value if isinstance(value, str) else None


def _opt_bool(obj: dict[str, Any], key: str) -> bool | None:
    value = obj.get(key)
    return value if isinstance(value, bool) else None


def _parse_user(user_raw: str | None) -> TelegramUser:
    if not user_raw:
        raise InitDataError(InitDataReason.MALFORMED)
    try:
        obj = json.loads(user_raw)
    except ValueError as exc:
        raise InitDataError(InitDataReason.MALFORMED) from exc
    if not isinstance(obj, dict):
        raise InitDataError(InitDataReason.MALFORMED)
    user_id = obj.get("id")
    # bool — подкласс int в Python, отсекаем явно.
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise InitDataError(InitDataReason.MALFORMED)
    return TelegramUser(
        id=user_id,
        first_name=_opt_str(obj, "first_name"),
        last_name=_opt_str(obj, "last_name"),
        username=_opt_str(obj, "username"),
        language_code=_opt_str(obj, "language_code"),
        is_premium=_opt_bool(obj, "is_premium"),
        photo_url=_opt_str(obj, "photo_url"),
        allows_write_to_pm=_opt_bool(obj, "allows_write_to_pm"),
    )


def validate_init_data(
    raw: str,
    *,
    bot_token: str,
    max_age_seconds: int,
    future_skew_seconds: int,
    now: float | None = None,
) -> InitDataContext:
    """Полная проверка initData. При ошибке — InitDataError(reason).

    Порядок: разбор → подпись → свежесть → разбор user. Поля, не прошедшие
    подпись, не интерпретируются.
    """
    if not bot_token:
        # Вызывающий код обязан проверить это раньше (503); здесь — страховка.
        raise ValueError("bot_token is empty")
    if not raw:
        raise InitDataError(InitDataReason.MISSING)

    pairs = _parse_pairs(raw)

    received_hash = pairs.get("hash")
    if not received_hash:
        raise InitDataError(InitDataReason.MALFORMED)

    expected_hash = compute_hash(pairs, bot_token)
    if not hmac.compare_digest(
        expected_hash.encode("ascii"), received_hash.encode("utf-8")
    ):
        raise InitDataError(InitDataReason.BAD_SIGNATURE)

    auth_date_raw = pairs.get("auth_date", "")
    if not auth_date_raw.isascii() or not auth_date_raw.isdigit():
        raise InitDataError(InitDataReason.MALFORMED)
    auth_date = int(auth_date_raw)

    current = time.time() if now is None else now
    if auth_date > current + future_skew_seconds:
        raise InitDataError(InitDataReason.FUTURE)
    if current - auth_date > max_age_seconds:
        raise InitDataError(InitDataReason.EXPIRED)

    user = _parse_user(pairs.get("user"))

    return InitDataContext(
        user=user,
        auth_date=auth_date,
        query_id=pairs.get("query_id"),
        start_param=pairs.get("start_param"),
        chat_type=pairs.get("chat_type"),
        chat_instance=pairs.get("chat_instance"),
    )


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def require_init_data(
    x_telegram_init_data: str | None = Header(default=None, alias=INIT_DATA_HEADER),
    settings: Settings = Depends(get_settings),
) -> InitDataContext:
    """FastAPI-зависимость для ВСЕХ маршрутов /miniapp/v1/** (подключена в main.py)."""
    bot_token = settings.bot_token.get_secret_value()
    if not bot_token:
        logger.error("initData: BOT_TOKEN не задан — проверка невозможна, запрос отклонён (503)")
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "SERVICE_MISCONFIGURED",
            "Сервис временно недоступен",
        )

    if not x_telegram_init_data or not x_telegram_init_data.strip():
        logger.info("initData отклонён: reason=%s", InitDataReason.MISSING.value)
        raise _error(
            status.HTTP_401_UNAUTHORIZED,
            "TG_INIT_MISSING",
            "Нет данных авторизации Telegram. Переоткройте Mini App.",
        )

    try:
        ctx = validate_init_data(
            x_telegram_init_data,
            bot_token=bot_token,
            max_age_seconds=settings.init_data_max_age_seconds,
            future_skew_seconds=settings.init_data_future_skew_seconds,
        )
    except InitDataError as exc:
        # Только причина. Ни initData, ни hash, ни токена.
        logger.info("initData отклонён: reason=%s", exc.reason.value)
        raise _error(
            status.HTTP_401_UNAUTHORIZED,
            "TG_INIT_INVALID",
            "Данные авторизации Telegram недействительны или устарели. Переоткройте Mini App.",
        ) from None
    return ctx
