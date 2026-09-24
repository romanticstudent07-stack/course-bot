import json
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

import pytest

# apps/api в sys.path — тесты запускаются из корня репо или из apps/api.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings, get_settings  # noqa: E402
from app.telegram_init_data import compute_hash  # noqa: E402

# Фейковый токен только для тестов: подпись строится в тестах, реальный токен не нужен.
FAKE_BOT_TOKEN = "123456:TEST-fake-token-for-pytest-only"
TEST_USER_ID = 42


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
    """TestClient с фейковым BOT_TOKEN (не зависит от окружения)."""
    from fastapi.testclient import TestClient

    from main import app

    app.dependency_overrides[get_settings] = lambda: Settings(bot_token=FAKE_BOT_TOKEN)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
