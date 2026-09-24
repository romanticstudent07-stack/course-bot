import json
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

import pytest

# apps/api в sys.path — тесты запускаются из корня репо или из apps/api.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings, get_settings
from app.telegram_init_data import compute_hash

# Фейковый токен только для тестов: подпись строится в тестах, реальный токен не нужен.
FAKE_BOT_TOKEN = "123456:TEST-fake-token-for-pytest-only"
TEST_USER_ID = 42
# Недоступная БД (порт 1 на localhost — соединение отклоняется сразу).
# api_client использует её явно: тесты без БД не должны случайно попасть в DATABASE_URL.
UNREACHABLE_DSN = "postgresql+psycopg://nobody:nopass@127.0.0.1:1/none"


def sign_init_data(fields: dict[str, str], bot_token: str = FAKE_BOT_TOKEN) -> str:
    """Подписать поля так же, как Telegram, и вернуть сырую строку initData."""
    pairs = dict(fields)
    pairs["hash"] = compute_hash(pairs, bot_token)
    return urlencode(pairs)


def make_fields(
    user: dict | None = None, auth_date: int | None = None, **extra: str
) -> dict[str, str]:
    fields = {
        "auth_date": str(int(time.time()) if auth_date is None else auth_date),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps(
            user if user is not None else {"id": TEST_USER_ID, "first_name": "Test"},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }
    fields.update(extra)
    return fields


def valid_init_data(**kwargs) -> str:
    return sign_init_data(make_fields(**kwargs))


@pytest.fixture
def api_client():
    """TestClient с фейковым BOT_TOKEN и НЕДОСТУПНОЙ БД (не зависит от окружения)."""
    from fastapi.testclient import TestClient

    from main import app

    app.dependency_overrides[get_settings] = lambda: Settings(
        bot_token=FAKE_BOT_TOKEN, database_url=UNREACHABLE_DSN
    )
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# ====================== БД (Итерация 1b+1c) ======================
# Тесты с БД идут на живом Postgres: DATABASE_URL (CI: postgres:16 из job api).
# Нет DATABASE_URL → такие тесты пропускаются (skip), КРОМЕ случая REQUIRE_DB_TESTS=1:
# тогда отсутствие БД — ошибка (чтобы CI не «зеленел» молча без БД).
import os

API_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI = API_DIR / "migrations" / "alembic.ini"


def _database_url() -> str | None:
    return os.environ.get("DATABASE_URL") or None


def _alembic_config():
    from alembic.config import Config

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    return cfg


@pytest.fixture(scope="session")
def database_url() -> str:
    url = _database_url()
    if url is None:
        if os.environ.get("REQUIRE_DB_TESTS") == "1":
            pytest.fail("REQUIRE_DB_TESTS=1, но DATABASE_URL не задан")
        pytest.skip("DATABASE_URL не задан — тесты с БД пропущены")
    return url


@pytest.fixture(scope="session")
def migrated_db(database_url):
    """Схема на head на всю сессию; в конце — downgrade base (БД остаётся чистой)."""
    from alembic import command

    cfg = _alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield database_url
    command.downgrade(cfg, "base")


@pytest.fixture
def db_engine(migrated_db):
    from sqlalchemy import create_engine, text

    engine = create_engine(migrated_db)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE tg_user_registry RESTART IDENTITY"))
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_api_client(db_engine, migrated_db):
    """TestClient с фейковым BOT_TOKEN и настоящей БД (DATABASE_URL)."""
    from fastapi.testclient import TestClient

    from main import app

    app.dependency_overrides[get_settings] = lambda: Settings(
        bot_token=FAKE_BOT_TOKEN, database_url=migrated_db
    )
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def count_registry_rows(engine, tg_user_id: int | None = None) -> int:
    from sqlalchemy import text

    with engine.connect() as conn:
        if tg_user_id is None:
            return conn.execute(text("SELECT count(*) FROM tg_user_registry")).scalar_one()
        return conn.execute(
            text("SELECT count(*) FROM tg_user_registry WHERE tg_user_id = :u"),
            {"u": tg_user_id},
        ).scalar_one()
