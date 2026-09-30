"""1d: text_registry — seed, загрузчик, GET/POST /miniapp/v1/texts (docs/tasks/1d.md, раздел 9).

Без БД: схема = зеркало, seed по схеме, только заглушки, загрузчик отклоняет плохой seed,
401 / 422 / 503 от API.
С БД (DATABASE_URL, в CI обязательно): загрузка идемпотентна, лишние ключи не удаляются,
GET 200 без notes, 404, bulk texts + missing, CHECK на tone.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from jsonschema import Draft202012Validator
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.telegram_init_data import INIT_DATA_HEADER
from app.texts import (
    KEY_PATTERN,
    SCHEMA_PATH,
    TEXTS_DIR,
    LoadResult,
    load_seed,
    run_load,
    write_entries,
)
from tests.conftest import valid_init_data

API_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = API_DIR.parents[1]
MIRROR_SCHEMA = (
    REPO_ROOT / "docs" / "architecture" / "build" / "config-schemas" / "text_registry.schema.json"
)
MIGRATION_0003 = next((API_DIR / "migrations" / "versions").glob("*0003_text_registry*.py"))
B4_KEYS = {"B4.onb_welcome", "B4.onb_age_gate", "B4.onb_age_underage", "B4.onb_done"}
URL = "/miniapp/v1/texts"


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _headers() -> dict[str, str]:
    return {INIT_DATA_HEADER: valid_init_data()}


def _entry(key: str, **over) -> dict:
    e = {"key": key, "tone": "neutral", "legal_status": "pre-legal-review", "text": "[ЗАГЛУШКА] тест"}
    e.update(over)
    return e


def _write_seed(path: Path, entries: list[dict]) -> None:
    doc = {"version": "0.1.0", "owner_block": "B9", "durability_block": "B14", "entries": entries}
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


# ====================== без БД ======================


def test_schema_copy_equals_mirror():
    assert _read_json(SCHEMA_PATH) == _read_json(MIRROR_SCHEMA)


def test_key_pattern_equals_schema():
    schema = _read_json(SCHEMA_PATH)
    assert KEY_PATTERN == schema["$defs"]["entry"]["properties"]["key"]["pattern"]


def test_migration_check_uses_key_pattern():
    spec = importlib.util.spec_from_file_location("mig_0003_text_registry", MIGRATION_0003)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert KEY_PATTERN in " ".join(module.DDL)
    assert module.down_revision == "0002_tg_user_registry"


def test_b4_seed_passes_schema():
    data = _read_json(TEXTS_DIR / "B4.json")
    Draft202012Validator(_read_json(SCHEMA_PATH)).validate(data)
    assert data["version"] == "0.1.0"
    assert {e["key"] for e in data["entries"]} == B4_KEYS


def test_all_seed_entries_are_placeholders():
    files = sorted(TEXTS_DIR.glob("*.json"))
    assert files
    for path in files:
        for e in _read_json(path)["entries"]:
            assert e["legal_status"] == "pre-legal-review", (path.name, e["key"])
            assert e["text"].startswith("[ЗАГЛУШКА]"), (path.name, e["key"])
            for form in (e.get("plurals_ru") or {}).values():
                assert form.startswith("[ЗАГЛУШКА]"), (path.name, e["key"])


def test_load_seed_reads_repo_files():
    entries = load_seed()
    assert B4_KEYS <= {e.key for e in entries}
    assert all(e.registry_version == "0.1.0" for e in entries if e.source == "B4.json")


def test_loader_rejects_bad_tone(tmp_path, capsys):
    _write_seed(tmp_path / "B4.json", [_entry("B4.onb_x", tone="loud")])
    writer = Mock()
    assert run_load(tmp_path, SCHEMA_PATH, writer) == 1
    writer.assert_not_called()
    assert "loud" in capsys.readouterr().err


def test_loader_rejects_duplicate_key_between_files(tmp_path, capsys):
    _write_seed(tmp_path / "B4.json", [_entry("B4.onb_same")])
    _write_seed(tmp_path / "B9.json", [_entry("B4.onb_same")])
    writer = Mock()
    assert run_load(tmp_path, SCHEMA_PATH, writer) == 1
    writer.assert_not_called()
    assert "B4.onb_same" in capsys.readouterr().err


def test_loader_rejects_empty_dir(tmp_path):
    writer = Mock()
    assert run_load(tmp_path, SCHEMA_PATH, writer) == 1
    writer.assert_not_called()


def test_loader_success_prints_counts(tmp_path, capsys):
    _write_seed(tmp_path / "B4.json", [_entry("B4.onb_x")])
    writer = Mock(return_value=LoadResult(inserted=1, updated=0, extra=[]))
    assert run_load(tmp_path, SCHEMA_PATH, writer) == 0
    writer.assert_called_once()
    assert "загружено 1, обновлено 0, лишних в БД 0" in capsys.readouterr().out


def test_get_without_init_data_401(api_client):
    r = api_client.get(f"{URL}/B4.onb_welcome")
    assert r.status_code == 401
    assert r.json()["code"] == "TG_INIT_MISSING"


@pytest.mark.parametrize("key", ["b4.onb_welcome", "B4.Bad", "B4", "X1.onb_welcome"])
def test_get_bad_key_422(api_client, key):
    r = api_client.get(f"{URL}/{key}", headers=_headers())
    assert r.status_code == 422


def test_bulk_101_keys_422(api_client):
    keys = [f"B4.k{i}" for i in range(101)]
    r = api_client.post(f"{URL}/bulk", json={"keys": keys}, headers=_headers())
    assert r.status_code == 422


@pytest.mark.parametrize("keys", [[], ["b4.onb_welcome"], ["B4.onb_done", "B4.Bad"]])
def test_bulk_empty_or_bad_key_422(api_client, keys):
    r = api_client.post(f"{URL}/bulk", json={"keys": keys}, headers=_headers())
    assert r.status_code == 422


def test_get_db_unavailable_503(api_client):
    r = api_client.get(f"{URL}/B4.onb_welcome", headers=_headers())
    assert r.status_code == 503
    assert r.json()["code"] == "SERVICE_UNAVAILABLE"


# ====================== с БД ======================


def _truncate(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE text_registry"))


@pytest.fixture
def text_engine(migrated_db):
    engine = create_engine(migrated_db)
    _truncate(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def seeded_db(text_engine):
    write_entries(text_engine, load_seed())
    return text_engine


def test_load_twice_same_rows(text_engine):
    entries = load_seed()
    keys = {e.key for e in entries}
    first = write_entries(text_engine, entries)
    second = write_entries(text_engine, entries)
    assert (first.inserted, first.updated, first.extra) == (len(entries), 0, [])
    assert (second.inserted, second.updated, second.extra) == (0, len(entries), [])
    with text_engine.connect() as conn:
        rows = conn.execute(text("SELECT key, registry_version FROM text_registry")).all()
    assert len(rows) == len(entries)
    assert {r[0] for r in rows} == keys
    assert B4_KEYS <= keys


def test_extra_db_keys_are_listed_not_deleted(text_engine):
    with text_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO text_registry (key, tone, legal_status, text, registry_version) "
                "VALUES ('B9.extra_key', 'neutral', 'pre-legal-review', '[ЗАГЛУШКА] x', '0.0.1')"
            )
        )
    result = write_entries(text_engine, load_seed())
    assert result.extra == ["B9.extra_key"]
    with text_engine.connect() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM text_registry WHERE key = 'B9.extra_key'")
        ).scalar_one()
    assert n == 1


def test_get_text_200_without_notes(seeded_db, db_api_client):
    r = db_api_client.get(f"{URL}/B4.onb_welcome", headers=_headers())
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"key", "tone", "legal_status", "text", "plurals_ru"}
    assert body["key"] == "B4.onb_welcome"
    assert body["text"].startswith("[ЗАГЛУШКА]")
    assert body["plurals_ru"] is None


def test_get_missing_404(seeded_db, db_api_client):
    r = db_api_client.get(f"{URL}/B4.no_such_key", headers=_headers())
    assert r.status_code == 404
    assert r.json()["code"] == "TEXT_NOT_FOUND"


def test_bulk_texts_and_missing(seeded_db, db_api_client):
    keys = ["B4.onb_done", "B4.no_such_key", "B4.onb_welcome", "B4.onb_done"]
    r = db_api_client.post(f"{URL}/bulk", json={"keys": keys}, headers=_headers())
    assert r.status_code == 200, r.text
    body = r.json()
    assert [t["key"] for t in body["texts"]] == ["B4.onb_done", "B4.onb_welcome"]
    assert body["missing"] == ["B4.no_such_key"]
    assert all("notes" not in t for t in body["texts"])


def test_check_rejects_bad_tone(text_engine):
    with pytest.raises(IntegrityError):
        with text_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO text_registry (key, tone, legal_status, text, registry_version) "
                    "VALUES ('B4.onb_loud', 'loud', 'pre-legal-review', '[ЗАГЛУШКА] x', '0.1.0')"
                )
            )
