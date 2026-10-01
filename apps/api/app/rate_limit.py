"""apps/api/app/rate_limit.py — rate-limit /miniapp/v1/** (B-1, Б14 R328).

Контракт (docs/tasks/B-1.md, раздел 7):
  - фиксированное окно 1 минута: ключ rl:miniapp:{tg_user_id}:{unix_minute}, INCR;
    результат 1 → EXPIRE 120; результат > RATE_LIMIT_PER_MINUTE → 429;
  - 429: Error {code: RATE_LIMITED}, заголовок Retry-After = секунд до конца минуты (1..60);
  - ключ — tg_user_id из ПРОВЕРЕННОЙ initData (в R328 — pid; pid есть не у всех,
    его создаёт first-launch) — docs/DEFECTS-FOUND.md, D-7;
  - порядок: require_init_data → rate_limit. Без валидной initData — 401, счётчик не
    трогается. FastAPI кэширует require_init_data в запросе: HMAC второй раз не считается;
  - fail-open: пустой REDIS_URL или ошибка Redis → запрос проходит, WARNING с ИМЕНЕМ
    исключения. Текста исключения, initData, tg_user_id, REDIS_URL в логе нет.
    Ошибки проверки initData сюда не доходят: они возникают раньше, в require_init_data.

Самопроверка на сервере (настоящий Redis):
    python -m app.rate_limit selftest
"""
from __future__ import annotations

import logging
import sys
import time
from collections.abc import Callable
from functools import lru_cache
from typing import Protocol

import redis
from fastapi import Depends, HTTPException, status

from app.config import Settings, get_settings
from app.telegram_init_data import InitDataContext, require_init_data

logger = logging.getLogger(__name__)

WINDOW_SECONDS = 60
KEY_TTL_SECONDS = 120
KEY_PREFIX = "rl:miniapp"
SELFTEST_KEY = "rl:selftest"
RATE_LIMITED_CODE = "RATE_LIMITED"
RATE_LIMITED_MESSAGE = "Слишком много запросов. Подождите минуту."
_FAIL_OPEN_LOG = "rate-limit: redis unavailable (%s), fail-open"


class Counter(Protocol):
    """Счётчик окна: увеличить ключ и вернуть новое значение."""

    def incr(self, key: str, ttl_seconds: int) -> int:
        """Первый INCR (результат 1) ставит ключу срок жизни ttl_seconds."""


class RedisCounter:
    """Counter поверх redis-py: INCR, при результате 1 — EXPIRE."""

    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    def incr(self, key: str, ttl_seconds: int) -> int:
        value = int(self._client.incr(key))
        if value == 1:
            self._client.expire(key, ttl_seconds)
        return value


@lru_cache(maxsize=4)
def _redis_client(url: str, timeout_seconds: float) -> redis.Redis:
    """Один клиент (с пулом соединений) на процесс. Соединение — при первом запросе."""
    return redis.Redis.from_url(
        url,
        socket_timeout=timeout_seconds,
        socket_connect_timeout=timeout_seconds,
    )


def _warn_fail_open(reason: str) -> None:
    # Только имя причины/исключения: без текста исключения (там бывает адрес Redis).
    logger.warning(_FAIL_OPEN_LOG, reason)


def get_counter(settings: Settings = Depends(get_settings)) -> Counter | None:
    """Зависимость: счётчик или None (fail-open). Тесты подставляют фейк."""
    if not settings.redis_url:
        _warn_fail_open("RedisUrlEmpty")
        return None
    try:
        client = _redis_client(settings.redis_url, settings.rate_limit_redis_timeout_seconds)
    except Exception as exc:  # noqa: BLE001 — любая ошибка клиента → fail-open
        _warn_fail_open(type(exc).__name__)
        return None
    return RedisCounter(client)


def get_clock() -> Callable[[], float]:
    """Зависимость: источник времени (unix-секунды). Тесты подставляют фейк."""
    return time.time


def seconds_to_next_minute(now: float) -> int:
    """Секунд до конца текущей минуты: 1..60."""
    return WINDOW_SECONDS - int(now) % WINDOW_SECONDS


def window_key(tg_user_id: int, now: float) -> str:
    return f"{KEY_PREFIX}:{tg_user_id}:{int(now) // WINDOW_SECONDS}"


def rate_limit(
    ctx: InitDataContext = Depends(require_init_data),
    settings: Settings = Depends(get_settings),
    counter: Counter | None = Depends(get_counter),
    clock: Callable[[], float] = Depends(get_clock),
) -> None:
    """FastAPI-зависимость для ВСЕХ /miniapp/v1/** (подключена в main.py после require_init_data).

    Синхронная: FastAPI выполняет её в пуле потоков, вызов Redis не блокирует event loop.
    """
    if counter is None:
        return
    now = clock()
    try:
        count = counter.incr(window_key(ctx.tg_user_id, now), KEY_TTL_SECONDS)
    except Exception as exc:  # noqa: BLE001 — fail-open на любую ошибку счётчика
        _warn_fail_open(type(exc).__name__)
        return
    if count > settings.rate_limit_per_minute:
        logger.info("rate-limit: 429 (limit=%s/min)", settings.rate_limit_per_minute)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": RATE_LIMITED_CODE, "message": RATE_LIMITED_MESSAGE},
            headers={"Retry-After": str(seconds_to_next_minute(now))},
        )


def selftest(settings: Settings | None = None) -> int:
    """INCR/EXPIRE ключа rl:selftest в настоящем Redis. 0 — OK, 1 — FAIL."""
    settings = settings if settings is not None else get_settings()
    if not settings.redis_url:
        print("rate-limit selftest: FAIL RedisUrlEmpty")
        return 1
    try:
        client = _redis_client(settings.redis_url, settings.rate_limit_redis_timeout_seconds)
        RedisCounter(client).incr(SELFTEST_KEY, KEY_TTL_SECONDS)
        client.expire(SELFTEST_KEY, KEY_TTL_SECONDS)
    except Exception as exc:  # noqa: BLE001 — печатаем только имя исключения
        print(f"rate-limit selftest: FAIL {type(exc).__name__}")
        return 1
    print("rate-limit selftest: OK")
    return 0


def main(argv: list[str]) -> int:
    if argv[1:] == ["selftest"]:
        return selftest()
    print("usage: python -m app.rate_limit selftest", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
