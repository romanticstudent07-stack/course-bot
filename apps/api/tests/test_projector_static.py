"""projector-2: проверки без БД (docs/tasks/projector-2.md, раздел 9, тесты 8–9)."""
from __future__ import annotations

import re
import time
from pathlib import Path

import pytest

import app.projector as projector

APP_DIR = Path(__file__).resolve().parents[1] / "app"
PROJECTOR_FILE = APP_DIR / "projector.py"
# Тот же недоступный DSN, что UNREACHABLE_DSN в conftest.py (порт 1 — отказ сразу).
UNREACHABLE_DSN = "postgresql+psycopg://nobody:nopass@127.0.0.1:1/none"
# После имени — граница слова: participant_state_checkpoints не совпадает.
WRITE_RE = re.compile(r"\b(?:INSERT\s+INTO|UPDATE)\s+participant_state\b", re.IGNORECASE)


# 8. E1: SQL записи в participant_state — только в app/projector.py.
def test_e1_only_projector_writes_participant_state():
    offenders = []
    for path in sorted(APP_DIR.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path == PROJECTOR_FILE:
            continue
        if WRITE_RE.search(path.read_text(encoding="utf-8", errors="ignore")):
            offenders.append(str(path.relative_to(APP_DIR)))
    assert offenders == []


def test_e1_pattern_is_sane():
    assert WRITE_RE.search(PROJECTOR_FILE.read_text(encoding="utf-8"))
    assert WRITE_RE.search("update   Participant_State set x = 1")
    assert not WRITE_RE.search("INSERT INTO participant_state_checkpoints (pid) VALUES (1)")
    assert not WRITE_RE.search("UPDATE participant_state_checkpoints SET at = now()")


# 9. Неверный аргумент → usage, exit 2; к настройкам и БД не обращались.
@pytest.mark.parametrize("argv", [["bad"], [], ["once", "extra"]])
def test_bad_argument_returns_usage_without_db(argv, monkeypatch, capsys):
    def _forbidden(*_args, **_kwargs):
        raise AssertionError("main() с неверным аргументом не должен трогать настройки и БД")

    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_DSN)
    monkeypatch.setattr(projector, "get_settings", _forbidden)
    monkeypatch.setattr(projector, "get_engine", _forbidden)

    started = time.monotonic()
    assert projector.main(argv) == 2
    assert time.monotonic() - started < 1.0
    assert "usage: python -m app.projector run | once" in capsys.readouterr().err
