import json
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

import pytest
from sqlalchemy import text

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
    """Чистые участники, согласия, события и состояние + seed текстов (1e-1a, projector-1).

    participant_state_checkpoints, participant_state и access_grants (0010) FK на
    tg_user_registry не имеют —
    CASCADE их не очистит, поэтому они перечислены явно.
    """
    from sqlalchemy import create_engine, text

    from app.texts import load_seed, write_entries

    engine = create_engine(migrated_db)
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE participant_events, participant_state_checkpoints, participant_state, "
                "consent_events, tg_user_registry, access_grants RESTART IDENTITY CASCADE"
            )
        )
    write_entries(engine, load_seed())  # upsert всех config/texts/*.json (B4 + legal)
    grant_access(engine, TEST_USER_ID)  # api-access-1 (Р-2): без доступа first-launch → 403
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


def grant_access(engine_or_url, tg_user_id: int, status: str = "granted") -> None:
    """Строка access_grants под владельцем (api-access-1, Р-2); ON CONFLICT DO NOTHING.

    engine_or_url — engine или DSN (соединение владельца, не app_api: у app_api INSERT нет).
    status pending требует admin_message_id (CHECK 0010) — подставляется tg_user_id.
    """
    from sqlalchemy import create_engine, text

    engine = create_engine(engine_or_url) if isinstance(engine_or_url, str) else engine_or_url
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO access_grants (tg_user_id, status, admin_message_id, created_via) "
                    "VALUES (:u, :s, :m, 'bot_promo') ON CONFLICT DO NOTHING"
                ),
                {"u": tg_user_id, "s": status, "m": tg_user_id if status == "pending" else None},
            )
    finally:
        if isinstance(engine_or_url, str):
            engine.dispose()


_LOCK_WAITER_SQL = text(
    "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
    "AND NOT granted AND :h = ANY(pg_blocking_pids(pid))"
)


def wait_for_lock_waiter(engine, holder_pid: int, timeout: float = 10.0) -> bool:
    """True, когда кто-то ждёт advisory-замок, который держит holder_pid (iter2-api-3).

    Фильтр pg_blocking_pids — чужие ожидания в кластере не считаются. Опрос каждые 0.05 с.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with engine.connect() as conn:
            if conn.execute(_LOCK_WAITER_SQL, {"h": holder_pid}).scalar_one() > 0:
                return True
        time.sleep(0.05)
    return False


def count_registry_rows(engine, tg_user_id: int | None = None) -> int:
    from sqlalchemy import text

    with engine.connect() as conn:
        if tg_user_id is None:
            return conn.execute(text("SELECT count(*) FROM tg_user_registry")).scalar_one()
        return conn.execute(
            text("SELECT count(*) FROM tg_user_registry WHERE tg_user_id = :u"),
            {"u": tg_user_id},
        ).scalar_one()


def count_consent_rows(engine, pid=None) -> int:
    from sqlalchemy import text

    with engine.connect() as conn:
        if pid is None:
            return conn.execute(text("SELECT count(*) FROM consent_events")).scalar_one()
        return conn.execute(
            text("SELECT count(*) FROM consent_events WHERE pid = :p"), {"p": pid}
        ).scalar_one()
