"""GET /miniapp/v1/onboarding/status + повторный give в first-launch (returning-1, D-22).

Без БД: consent_problem / reasons (тест 1), 401 (6), 401 раньше rate-limit и 429 (7), 503 (13).
С БД (DATABASE_URL, в CI обязательно): returning (2), reconsent по revoke (3) и по смене
текста (4), new и erased одним телом (5), лог (8), first-launch после revoke (9) и смены
текста (10), повтор без новых строк (11), reconsent не пишет participant_events (12),
нет текста согласия → 503 SERVICE_MISCONFIGURED без данных участника (14).
Ревью PR #62:
  - тест 5: порядок «A есть → B новый»: тело B — ровно {"status":"new"}, без short_no A,
    строка B не создана; после tombstone A тело A побайтно равно телу B;
  - тест 8: два сценария — returning и reconsent (после revoke C1); в логе есть status и
    tg_user_id, нет reasons («C1_revoked», «C1_»), pid, short_no, initData;
  - тест 14: подменяется current_texts в app.routers.onboarding (имя, под которым его
    вызывает onboarding_status); тексты в БД не меняются.
Тексты text_registry фикстура не откатывает → тесты 4 и 10 возвращают текст в finally.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import text

from app.consent_status import (
    REASONS,
    ConsentTextMissingError,
    consent_problem,
    reasons,
    snapshot_of,
)
from app.telegram_init_data import INIT_DATA_HEADER
from tests.conftest import count_consent_rows, count_registry_rows, valid_init_data

STATUS = "/miniapp/v1/onboarding/status"
FIRST_LAUNCH = "/miniapp/v1/onboarding/first-launch"
BODY = {"birth_date": "1990-01-01", "consents": ["C0", "C1"]}
C0_KEY = "legal.consent_c0_age_18_plus"
C1_KEY = "legal.consent_c1_pdn"
TEXTS = {C0_KEY: "текст C0", C1_KEY: "текст C1"}
LOGGER = "app.routers.onboarding"


def _headers(user_id: int) -> dict[str, str]:
    return {INIT_DATA_HEADER: valid_init_data(user={"id": user_id, "first_name": "Test"})}


def _first_launch(client, user_id: int) -> dict:
    r = client.post(FIRST_LAUNCH, json=BODY, headers=_headers(user_id))
    assert r.status_code == 201
    return r.json()


def _status(client, user_id: int):
    r = client.get(STATUS, headers=_headers(user_id))
    assert r.status_code == 200
    return r


def _revoke(engine, pid: str, kind: str) -> None:
    # at = now() (не now() + 1 минута): новый give из first-launch будет позже revoke.
    key = C0_KEY if kind == "C0" else C1_KEY
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO consent_events "
                "(pid, kind, action, at, ver_of_text, text_key, text_snapshot, created_via) "
                "VALUES (:pid, :k, 'revoke', now(), '0.2.0', :t, "
                "'[ЗАГЛУШКА] x', 'mini_app_first_launch')"
            ),
            {"pid": uuid.UUID(pid), "k": kind, "t": key},
        )


def _get_text(engine, key: str) -> str:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT text FROM text_registry WHERE key = :k"), {"k": key}
        ).scalar_one()


def _set_text(engine, key: str, value: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE text_registry SET text = :v WHERE key = :k"), {"v": value, "k": key}
        )


def _rows(engine, pid: str) -> list[tuple[str, str, str]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT kind, action, text_snapshot FROM consent_events "
                "WHERE pid = :p ORDER BY at, id"
            ),
            {"p": uuid.UUID(pid)},
        ).all()
    return [(r.kind, r.action, r.text_snapshot) for r in rows]


def _participant_events(engine, pid: str) -> int:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT count(*) FROM participant_events WHERE pid = :p"),
            {"p": uuid.UUID(pid)},
        ).scalar_one()


def _log_lines(caplog) -> list[str]:
    return [rec.getMessage() for rec in caplog.records if rec.name == LOGGER]


# ============================ без БД ============================


def _give(kind: str, key: str, snap: str) -> tuple[str, str, str, str]:
    return (kind, "give", key, snap)


def _rev(kind: str, key: str) -> tuple[str, str, str, str]:
    return (kind, "revoke", key, "x")


def test_consent_problem_pure_cases():  # тест 1
    assert snapshot_of("abc") == "abc"
    ok = _give("C1", C1_KEY, "t")
    assert consent_problem([ok], "C1", C1_KEY, "t") is None
    assert consent_problem([ok, _rev("C1", C1_KEY)], "C1", C1_KEY, "t") == "revoked"
    assert consent_problem([_rev("C1", C1_KEY), ok], "C1", C1_KEY, "t") is None
    old = _give("C1", C1_KEY, "старый")
    assert consent_problem([old], "C1", C1_KEY, "t") == "text_changed"
    other_key = _give("C1", "legal.other", "t")
    assert consent_problem([other_key], "C1", C1_KEY, "t") == "text_changed"
    assert consent_problem([], "C1", C1_KEY, "t") == "missing"
    assert consent_problem([_give("C0", C0_KEY, "t")], "C1", C1_KEY, "t") == "missing"
    # Порядок (at, id) решает: последнее событие по kind.
    assert consent_problem([old, ok], "C1", C1_KEY, "t") is None
    assert consent_problem([ok, old], "C1", C1_KEY, "t") == "text_changed"


def test_reasons_closed_list_and_order():
    assert reasons([], TEXTS) == ["C0_missing", "C1_missing"]
    events = [
        _give("C0", C0_KEY, TEXTS[C0_KEY]),
        _give("C1", C1_KEY, TEXTS[C1_KEY]),
        _rev("C1", C1_KEY),
    ]
    assert reasons(events, TEXTS) == ["C1_revoked"]
    events = [_give("C1", C1_KEY, "старый"), _rev("C0", C0_KEY)]
    out = reasons(events, TEXTS)
    assert out == ["C0_revoked", "C1_text_changed"]
    assert set(out) <= set(REASONS)


def test_status_without_init_data_is_401(api_client):  # тест 6
    r = api_client.get(STATUS)
    assert r.status_code == 401
    assert r.json()["code"] == "TG_INIT_MISSING"


def test_status_401_before_rate_limit_and_429(api_client):  # тест 7
    # Маршрут под miniapp_v1: require_init_data, затем rate_limit (main.py, B-1).
    from app.rate_limit import get_counter
    from main import app

    class FakeCounter:
        def __init__(self, value: int) -> None:
            self.value = value
            self.calls: list[tuple[str, int]] = []

        def incr(self, key: str, ttl_seconds: int) -> int:
            self.calls.append((key, ttl_seconds))
            return self.value

    fake = FakeCounter(10**6)  # заведомо больше любого лимита в минуту
    app.dependency_overrides[get_counter] = lambda: fake

    forged = valid_init_data().replace("Test", "Evil")
    r = api_client.get(STATUS, headers={INIT_DATA_HEADER: forged})
    assert r.status_code == 401
    assert r.json()["code"] == "TG_INIT_INVALID"
    assert fake.calls == []  # без валидной initData счётчик не тронут

    r = api_client.get(STATUS, headers=_headers(42))
    assert r.status_code == 429
    assert len(fake.calls) == 1


def test_status_db_unavailable_is_503(api_client):  # тест 13
    r = api_client.get(STATUS, headers=_headers(42))
    assert r.status_code == 503
    assert r.json()["code"] == "SERVICE_UNAVAILABLE"
    assert "127.0.0.1" not in r.text and "nopass" not in r.text


# ============================ с БД ============================


def test_status_returning(db_api_client):  # тест 2
    created = _first_launch(db_api_client, 2101)
    body = _status(db_api_client, 2101).json()
    assert body == {"status": "returning", "short_no": created["short_no"]}
    assert len(body) == 2 and "pid" not in body


def test_status_reconsent_after_revoke(db_api_client, db_engine):  # тест 3
    pid = _first_launch(db_api_client, 2201)["pid"]
    _revoke(db_engine, pid, "C1")
    body = _status(db_api_client, 2201).json()
    assert body == {"status": "reconsent", "reasons": ["C1_revoked"]}
    assert "short_no" not in body and "pid" not in body


def test_status_reconsent_after_text_change(db_api_client, db_engine):  # тест 4
    _first_launch(db_api_client, 2301)
    original = _get_text(db_engine, C0_KEY)
    try:
        _set_text(db_engine, C0_KEY, original + " [изм.]")
        body = _status(db_api_client, 2301).json()
        assert body == {"status": "reconsent", "reasons": ["C0_text_changed"]}
    finally:
        _set_text(db_engine, C0_KEY, original)


def test_status_new_and_erased_same_body(db_api_client, db_engine):  # тест 5
    # A есть → B новый: чужой участник не просачивается в ответ B.
    created_a = _first_launch(db_api_client, 2402)
    body_b = _status(db_api_client, 2401).content
    assert body_b == b'{"status":"new"}'
    assert created_a["short_no"].encode() not in body_b
    assert count_registry_rows(db_engine, 2401) == 0  # GET ничего не создаёт
    # tombstone A (erased) → тело A побайтно как у B.
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE tg_user_registry SET tombstoned_at = now() WHERE tg_user_id = 2402")
        )
    body_a = _status(db_api_client, 2402).content
    assert body_a == body_b


def test_status_log_has_no_secrets(db_api_client, db_engine, caplog):  # тест 8
    # Сценарий 1: returning.
    created = _first_launch(db_api_client, 2501)
    headers = _headers(2501)
    caplog.clear()
    with caplog.at_level(logging.INFO, logger=LOGGER):
        r = db_api_client.get(STATUS, headers=headers)
    assert r.json()["status"] == "returning"
    lines = _log_lines(caplog)
    assert any("status=returning" in line and "tg_user_id=2501" in line for line in lines)
    joined = "\n".join(lines)
    assert created["short_no"] not in joined
    assert created["pid"] not in joined
    assert "C1_" not in joined
    assert headers[INIT_DATA_HEADER] not in joined
    assert "hash=" not in joined

    # Сценарий 2: reconsent после revoke C1 — reasons в лог не попадают.
    created2 = _first_launch(db_api_client, 2502)
    _revoke(db_engine, created2["pid"], "C1")
    headers2 = _headers(2502)
    caplog.clear()
    with caplog.at_level(logging.INFO, logger=LOGGER):
        r = db_api_client.get(STATUS, headers=headers2)
    assert r.json() == {"status": "reconsent", "reasons": ["C1_revoked"]}
    lines = _log_lines(caplog)
    assert any("status=reconsent" in line and "tg_user_id=2502" in line for line in lines)
    joined = "\n".join(lines)
    assert "C1_revoked" not in joined
    assert "C1_" not in joined
    assert created2["pid"] not in joined
    assert created2["short_no"] not in joined
    assert headers2[INIT_DATA_HEADER] not in joined
    assert "hash=" not in joined


def test_first_launch_after_revoke_writes_one_give(db_api_client, db_engine):  # тест 9
    pid = _first_launch(db_api_client, 2601)["pid"]
    _revoke(db_engine, pid, "C1")
    before = count_consent_rows(db_engine, uuid.UUID(pid))
    again = _first_launch(db_api_client, 2601)
    assert again["pid"] == pid
    rows = _rows(db_engine, pid)
    assert len(rows) == before + 1
    assert rows[-1][:2] == ("C1", "give")
    assert _status(db_api_client, 2601).json()["status"] == "returning"


def test_first_launch_after_text_change_writes_new_snapshot(db_api_client, db_engine):  # 10
    pid = _first_launch(db_api_client, 2701)["pid"]
    original = _get_text(db_engine, C0_KEY)
    changed = original + " [изм.]"
    try:
        _set_text(db_engine, C0_KEY, changed)
        before = count_consent_rows(db_engine, uuid.UUID(pid))
        _first_launch(db_api_client, 2701)
        rows = _rows(db_engine, pid)
        assert len(rows) == before + 1
        assert rows[-1] == ("C0", "give", changed)
        assert _status(db_api_client, 2701).json()["status"] == "returning"
    finally:
        _set_text(db_engine, C0_KEY, original)


def test_repeat_first_launch_with_valid_consents_writes_nothing(db_api_client, db_engine):  # 11
    pid = _first_launch(db_api_client, 2801)["pid"]
    before = count_consent_rows(db_engine, uuid.UUID(pid))
    assert before == 2
    assert _first_launch(db_api_client, 2801)["pid"] == pid
    assert count_consent_rows(db_engine, uuid.UUID(pid)) == before


def test_reconsent_does_not_write_participant_events(db_api_client, db_engine):  # тест 12
    pid = _first_launch(db_api_client, 2901)["pid"]
    assert _participant_events(db_engine, pid) == 1
    _revoke(db_engine, pid, "C1")
    _first_launch(db_api_client, 2901)
    assert _participant_events(db_engine, pid) == 1


def test_status_text_missing_is_503_misconfigured(db_api_client, monkeypatch):  # тест 14
    created = _first_launch(db_api_client, 3001)

    def _no_text(session, kinds):
        raise ConsentTextMissingError([C0_KEY])

    # Подмена там, где её вызывает onboarding_status; тексты в БД не меняются.
    monkeypatch.setattr("app.routers.onboarding.current_texts", _no_text)
    r = db_api_client.get(STATUS, headers=_headers(3001))
    assert r.status_code == 503
    assert r.json()["code"] == "SERVICE_MISCONFIGURED"
    assert '"short_no"' not in r.text
    assert "returning" not in r.text
    assert created["pid"] not in r.text
    assert created["short_no"] not in r.text
