"""Контент дня (iter2-api-1, карточка §9): заглушки валидны, по одному отказу на правило,
ключи title/help есть в заглушках текстов, битый контент роняет create_app. Без БД."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

import app.day_content as day_content
from app.day_content import CONTENT_DIR, DayContentError, load_day_content
from app.texts import load_seed

DAY_01 = CONTENT_DIR / "module_1" / "day_01.json"


def _base() -> dict:
    return json.loads(DAY_01.read_text(encoding="utf-8"))


def _write(root: Path, data, module: str = "module_1", name: str = "day_01.json") -> Path:
    folder = root / module
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    body = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    path.write_text(body, encoding="utf-8")
    return path


def _fails(tmp_path: Path, data, needle: str, name: str = "day_01.json") -> str:
    _write(tmp_path, data, name=name)
    with pytest.raises(DayContentError) as exc:
        load_day_content(tmp_path)
    message = str(exc.value)
    assert name in message
    assert needle in message
    return message


def test_stub_content_is_valid():
    content = load_day_content()
    day1 = content.get(1, 1, 1)
    day2 = content.get(1, 1, 2)
    assert day1 is not None and len(day1.blocks) == 4
    assert day2 is not None and len(day2.blocks) == 5
    for day in content.days():
        assert any(b.critical for b in day.blocks)
        assert day.min_optional <= sum(1 for b in day.blocks if not b.critical)
        assert len({b.block_id for b in day.blocks}) == len(day.blocks)


def test_copy_of_stub_is_valid(tmp_path):
    _write(tmp_path, _base())
    assert load_day_content(tmp_path).get(1, 1, 1) is not None


def test_schema_extra_field(tmp_path):
    data = _base()
    data["extra"] = 1
    _fails(tmp_path, data, "схема")


def test_schema_too_few_blocks(tmp_path):
    data = _base()
    data["blocks"] = data["blocks"][:3]
    _fails(tmp_path, data, "схема")


def test_schema_bad_block_id(tmp_path):
    data = _base()
    data["blocks"][0]["block_id"] = "Task-1"
    _fails(tmp_path, data, "схема")


def test_duplicate_block_id(tmp_path):
    data = _base()
    data["blocks"][1]["block_id"] = data["blocks"][0]["block_id"]
    _fails(tmp_path, data, "block_id повторяется")


def test_no_critical_block(tmp_path):
    data = _base()
    for block in data["blocks"]:
        block["critical"] = False
    _fails(tmp_path, data, "нет критического блока")


def test_min_optional_too_big(tmp_path):
    data = _base()  # 2 критических + 2 некритических
    data["min_optional"] = 3
    _fails(tmp_path, data, "min_optional=3")


def test_day_no_mismatch_with_file_name(tmp_path):
    data = _base()
    data["day_no"] = 2
    _fails(tmp_path, data, "day_no=2")


def test_bad_file_name(tmp_path):
    _fails(tmp_path, _base(), "имя файла", name="day_1.json")


def test_broken_json(tmp_path):
    _fails(tmp_path, "{", "не JSON")


def test_duplicate_position(tmp_path):
    _write(tmp_path, _base())
    _write(tmp_path, _base(), module="module_2")
    with pytest.raises(DayContentError) as exc:
        load_day_content(tmp_path)
    assert "повторяется" in str(exc.value)


def test_empty_content_dir(tmp_path):
    with pytest.raises(DayContentError) as exc:
        load_day_content(tmp_path)
    assert "нет ни одного дня" in str(exc.value)


def test_error_is_logged_with_path(tmp_path, caplog):
    data = _base()
    data["min_optional"] = 3
    with caplog.at_level(logging.ERROR, logger="app.day_content"):
        _fails(tmp_path, data, "min_optional")
    assert any(
        r.levelno == logging.ERROR and "day_01.json" in r.getMessage() for r in caplog.records
    )


def test_create_app_fails_on_broken_content(tmp_path, monkeypatch):
    import main

    data = _base()
    data["blocks"] = data["blocks"][:2]
    _write(tmp_path, data)
    monkeypatch.setattr(day_content, "CONTENT_DIR", tmp_path)
    with pytest.raises(DayContentError):
        main.create_app()


def test_all_title_and_help_keys_in_seed():
    seed_keys = {entry.key for entry in load_seed()}
    missing = []
    for day in load_day_content().days():
        for block in day.blocks:
            for key in (block.title_key, block.help_key):
                if key not in seed_keys:
                    missing.append(f"{day.source}: {key}")
    assert missing == []
