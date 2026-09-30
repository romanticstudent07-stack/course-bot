"""B-1: rate-limit /miniapp/v1/** (docs/tasks/B-1.md, раздел 9).

Без БД и без настоящего Redis: счётчик — FakeCounter, время — FakeClock.
Тестовое приложение собирается тем же build_miniapp_v1_router, что и main.py;
подключение в create_app проверяется на настоящем main.app (limit=2 → третий 429).
"""
from __future__ import annotations

import logging

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.errors import install_error_handlers
from app.rate_limit import (
    KEY_TTL_SECONDS,
    RATE_LIMITED_MESSAGE,
    RedisCounter,
    get_clock,
    get_counter,
    seconds_to_next_minute,
    selftest,
)
from app.routers import health
from app.telegram_init_data import INIT_DATA_HEADER
from main import app as main_app
from main import build_miniapp_v1_router
from tests.conftest import FAKE_BOT_TOKEN, UNREACHABLE_DSN, valid_init_data

T0 = 60 * 28_000_000 + 15  # 15-я секунда минуты → Retry-After = 45
MINUTE0 = T0 // 60
USER_A = 987654321
USER_B = 123456789
PING = "/miniapp/v1/ping"
FAIL_OPEN_MSG = "rate-limit: redis unavailable (%s), fail-open"


class FakeCounter:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}
        self.calls: list[tuple[str, int]] = []

    def incr(self, key: str, ttl_seconds: int) -> int:
        self.calls.append((key, ttl_seconds))
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]


class BrokenCounter:
    def __init__(self) -> None:
        self.calls = 0

    def incr(self, key: str, ttl_seconds: int) -> int:
        self.calls += 1
        raise ConnectionError("redis://secret-host:6379 refused")


class FakeClock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}
        self.expires: list[tuple[str, int]] = []

    def incr(self, key: str) -> int:
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    def expire(self, key: str, seconds: int) -> bool:
        self.expires.append((key, seconds))
        return True


def _headers(user_id: int = USER_A) -> dict[str, str]:
    return {INIT_DATA_HEADER: valid_init_data(user={"id": user_id, "first_name": "Test"})}


def _test_app() -> FastAPI:
    ping = APIRouter()

    @ping.get("/ping")
    def _ping() -> dict[str, bool]:
        return {"ok": True}

    app = FastAPI()
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(build_miniapp_v1_router(ping))
    return app


@pytest.fixture
def make_client():
    used: list[FastAPI] = []

    def _make(*, counter, limit: int = 60, clock: FakeClock | None = None, app: FastAPI | None = None):
        target = app if app is not None else _test_app()
        clk = clock if clock is not None else FakeClock(T0)
        target.dependency_overrides[get_settings] = lambda: Settings(
            bot_token=FAKE_BOT_TOKEN, database_url=UNREACHABLE_DSN, rate_limit_per_minute=limit
        )
        target.dependency_overrides[get_counter] = lambda: counter
        target.dependency_overrides[get_clock] = lambda: clk
        used.append(target)
        return TestClient(target)

    yield _make
    for target in used:
        target.dependency_overrides.clear()


def test_60_ok_then_61st_429_with_retry_after(make_client):
    counter = FakeCounter()
    client = make_client(counter=counter)
    h = _headers()
    for i in range(60):
        assert client.get(PING, headers=h).status_code == 200, i
    r = client.get(PING, headers=h)
    assert r.status_code == 429
    assert r.json() == {"code": "RATE_LIMITED", "message": "Слишком много запросов. Подождите минуту."}
    assert RATE_LIMITED_MESSAGE == "Слишком много запросов. Подождите минуту."
    retry = int(r.headers["Retry-After"])
    assert 1 <= retry <= 60
    assert retry == 45
    assert KEY_TTL_SECONDS == 120
    assert counter.calls[0] == (f"rl:miniapp:{USER_A}:{MINUTE0}", 120)


def test_seconds_to_next_minute_bounds():
    start = T0 - 15  # ровно начало минуты
    assert seconds_to_next_minute(start) == 60
    assert seconds_to_next_minute(start + 59.9) == 1
    assert seconds_to_next_minute(T0) == 45


def test_users_counted_separately(make_client):
    client = make_client(counter=FakeCounter(), limit=2)
    a, b = _headers(USER_A), _headers(USER_B)
    assert [client.get(PING, headers=a).status_code for _ in range(3)] == [200, 200, 429]
    assert [client.get(PING, headers=b).status_code for _ in range(2)] == [200, 200]


def test_new_minute_resets_count(make_client):
    counter = FakeCounter()
    clock = FakeClock(T0)
    client = make_client(counter=counter, limit=2, clock=clock)
    h = _headers()
    assert [client.get(PING, headers=h).status_code for _ in range(3)] == [200, 200, 429]
    clock.now = T0 + 60
    assert client.get(PING, headers=h).status_code == 200
    assert counter.values[f"rl:miniapp:{USER_A}:{MINUTE0 + 1}"] == 1


def test_counter_error_fail_open_and_clean_log(make_client, caplog):
    caplog.set_level(logging.WARNING, logger="app.rate_limit")
    counter = BrokenCounter()
    client = make_client(counter=counter, limit=1)
    h = _headers()
    assert [client.get(PING, headers=h).status_code for _ in range(3)] == [200, 200, 200]
    assert counter.calls == 3
    records = [rec for rec in caplog.records if rec.name == "app.rate_limit"]
    assert [rec.levelno for rec in records] == [logging.WARNING] * 3
    assert {rec.getMessage() for rec in records} == {FAIL_OPEN_MSG % "ConnectionError"}
    assert str(USER_A) not in caplog.text
    assert h[INIT_DATA_HEADER] not in caplog.text
    assert "hash" not in caplog.text
    assert "secret-host" not in caplog.text


def test_without_or_bad_init_data_401_counter_not_called(make_client):
    counter = FakeCounter()
    client = make_client(counter=counter)
    r = client.get(PING)
    assert r.status_code == 401
    assert r.json()["code"] == "TG_INIT_MISSING"
    r = client.get(PING, headers={INIT_DATA_HEADER: "user=%7B%7D&hash=bad"})
    assert r.status_code == 401
    assert r.json()["code"] == "TG_INIT_INVALID"
    assert counter.calls == []


def test_401_before_429(make_client):
    counter = FakeCounter()
    client = make_client(counter=counter, limit=1)
    h = _headers()
    assert [client.get(PING, headers=h).status_code for _ in range(2)] == [200, 429]
    r = client.get(PING)
    assert r.status_code == 401
    assert len(counter.calls) == 2


def test_healthz_not_limited(make_client):
    counter = FakeCounter()
    client = make_client(counter=counter, limit=1)
    assert [client.get("/healthz").status_code for _ in range(5)] == [200] * 5
    assert counter.calls == []


def test_main_app_healthz_not_limited(make_client):
    counter = FakeCounter()
    client = make_client(counter=counter, limit=1, app=main_app)
    assert [client.get("/healthz").status_code for _ in range(3)] == [200] * 3
    assert counter.calls == []


def test_main_app_limit_from_settings(make_client):
    counter = FakeCounter()
    client = make_client(counter=counter, limit=2, app=main_app)
    url = "/miniapp/v1/texts/B4.onb_welcome"
    h = _headers()
    codes = [client.get(url, headers=h).status_code for _ in range(3)]
    assert 429 not in codes[:2]  # БД недоступна → 503, но не 429
    assert codes[2] == 429
    assert len(counter.calls) == 3


def test_redis_counter_expire_only_on_first_incr():
    fake = FakeRedis()
    counter = RedisCounter(fake)
    assert counter.incr("rl:miniapp:1:1", 120) == 1
    assert counter.incr("rl:miniapp:1:1", 120) == 2
    assert fake.expires == [("rl:miniapp:1:1", 120)]


def test_get_counter_empty_url_fail_open(caplog):
    caplog.set_level(logging.WARNING, logger="app.rate_limit")
    assert get_counter(Settings(redis_url="")) is None
    assert FAIL_OPEN_MSG % "RedisUrlEmpty" in caplog.text


def test_get_counter_builds_redis_counter():
    counter = get_counter(Settings(redis_url="redis://127.0.0.1:1/0"))
    assert isinstance(counter, RedisCounter)


def test_settings_defaults_and_bounds(monkeypatch):
    monkeypatch.delenv("RATE_LIMIT_PER_MINUTE", raising=False)
    monkeypatch.delenv("RATE_LIMIT_REDIS_TIMEOUT_SECONDS", raising=False)
    s = Settings()
    assert s.rate_limit_per_minute == 60
    assert s.rate_limit_redis_timeout_seconds == 0.2
    with pytest.raises(ValidationError):
        Settings(rate_limit_per_minute=0)


def test_selftest_empty_url(capsys):
    assert selftest(Settings(redis_url="")) == 1
    assert capsys.readouterr().out.strip() == "rate-limit selftest: FAIL RedisUrlEmpty"


def test_selftest_unreachable_redis(capsys):
    assert selftest(Settings(redis_url="redis://127.0.0.1:1/0")) == 1
    out = capsys.readouterr().out.strip()
    assert out.startswith("rate-limit selftest: FAIL ")
    assert "127.0.0.1" not in out
