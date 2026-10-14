"""apps/api/tests/test_texts_load_errors.py — texts load при кривом DSN (B-3d-2).

Без БД: нечисловой порт в MIGRATIONS_DATABASE_URL → ValueError при создании engine.
run_load() выходит с кодом 1 и печатает только имя класса: без traceback, без DSN и пароля.
"""
from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.config import get_settings
from app.texts import run_load

_PASSWORD_MARKER = "pw-marker-b3d"
_BAD_PORT_DSN = f"postgresql+psycopg://u:{_PASSWORD_MARKER}@db:notaport/x"


@pytest.fixture
def bad_port_dsn(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("MIGRATIONS_DATABASE_URL", _BAD_PORT_DSN)
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()


def test_load_bad_port_exits_1_without_traceback(
    bad_port_dsn: None, capsys: pytest.CaptureFixture[str]
) -> None:
    code = run_load()
    captured = capsys.readouterr()
    output = captured.out + captured.err

    assert code == 1
    assert "ValueError" in output
    assert "Traceback" not in output
    assert _PASSWORD_MARKER not in output
    assert "notaport" not in output
