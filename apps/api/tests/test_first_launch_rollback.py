"""B-3b: откат first-launch при ошибке БД, гонка участника до 0004, CHECK consent_events.

Тесты с db_* фикстурами — только с живой БД (CI): без неё они пропускаются.
Соединение CI — суперпользователь: временные функция и триггер разрешены.
test_get_db_session_rolls_back — без БД (FakeSession).
"""
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import main
from app.config import Settings
from app.db import session as db_session
from tests.conftest import (
    FAKE_BOT_TOKEN,
    UNREACHABLE_DSN,
    count_consent_rows,
    count_registry_rows,
    valid_init_data,
)

FIRST_LAUNCH = "/miniapp/v1/onboarding/first-launch"
INIT_HEADER = "X-Telegram-Init-Data"
BODY = {"birth_date": "1990-01-01", "consents": ["C0", "C1"]}
FUNC = "b3b_test_fail_consent"
TRIGGER = "b3b_test_fail_consent_trg"
THREADS = 8


def _headers(tg_user_id: int) -> dict[str, str]:
    init_data = valid_init_data(user={"id": tg_user_id, "first_name": "Test"})
    return {INIT_HEADER: init_data}


def _install_failing_trigger(engine, errcode: str | None) -> None:
    using = f" USING ERRCODE = '{errcode}'" if errcode else ""
    with engine.begin() as conn:
        conn.execute(
            text(
                f"CREATE FUNCTION {FUNC}() RETURNS trigger LANGUAGE plpgsql AS $$ "
                f"BEGIN RAISE EXCEPTION 'b3b-test'{using}; END $$"
            )
        )
        conn.execute(
            text(
                f"CREATE TRIGGER {TRIGGER} BEFORE INSERT ON consent_events "
                f"FOR EACH ROW EXECUTE FUNCTION {FUNC}()"
            )
        )


def _drop_failing_trigger(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(f"DROP TRIGGER IF EXISTS {TRIGGER} ON consent_events"))
        conn.execute(text(f"DROP FUNCTION IF EXISTS {FUNC}()"))


def test_operational_error_on_consent_insert_rolls_back_participant(db_api_client, db_engine):
    try:
        _install_failing_trigger(db_engine, "57P01")
        r = db_api_client.post(FIRST_LAUNCH, headers=_headers(2001), json=BODY)
    finally:
        _drop_failing_trigger(db_engine)
    assert r.status_code == 503, r.text
    assert r.json()["code"] == "SERVICE_UNAVAILABLE"
    assert count_registry_rows(db_engine, 2001) == 0
    assert count_consent_rows(db_engine) == 0


def test_internal_error_on_consent_insert_rolls_back_participant(
    db_api_client, db_engine, caplog
):
    caplog.set_level(logging.DEBUG)
    try:
        _install_failing_trigger(db_engine, None)
        r = db_api_client.post(FIRST_LAUNCH, headers=_headers(2002), json=BODY)
    finally:
        _drop_failing_trigger(db_engine)
    assert r.status_code == 500, r.text
    assert r.json()["code"] == "INTERNAL_ERROR"
    assert "b3b-test" not in r.text
    assert "b3b-test" not in caplog.text
    assert count_registry_rows(db_engine, 2002) == 0
    assert count_consent_rows(db_engine) == 0


class _FakeSession:
    def __init__(self, calls: list[str], rollback_error: Exception | None = None) -> None:
        self.calls = calls
        self.rollback_error = rollback_error

    def rollback(self) -> None:
        self.calls.append("rollback")
        if self.rollback_error is not None:
            raise self.rollback_error

    def close(self) -> None:
        self.calls.append("close")


def _patch_session(monkeypatch, fake: _FakeSession) -> None:
    monkeypatch.setattr(db_session, "get_engine", lambda settings: object())
    monkeypatch.setattr(db_session, "sessionmaker", lambda **kwargs: (lambda: fake))


def _settings() -> Settings:
    return Settings(bot_token=FAKE_BOT_TOKEN, database_url=UNREACHABLE_DSN)


def test_get_db_session_rolls_back(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)

    calls: list[str] = []
    _patch_session(monkeypatch, _FakeSession(calls))
    gen = db_session.get_db_session(_settings())
    next(gen)
    with pytest.raises(RuntimeError):
        gen.throw(RuntimeError("x"))
    assert calls == ["rollback", "close"]

    calls2: list[str] = []
    _patch_session(monkeypatch, _FakeSession(calls2, rollback_error=ValueError("rb")))
    gen2 = db_session.get_db_session(_settings())
    next(gen2)
    with pytest.raises(RuntimeError):
        gen2.throw(RuntimeError("x"))
    assert calls2 == ["rollback", "close"]
    assert "ValueError" in caplog.text


def test_concurrent_first_launch_for_pre_0004_participant(db_api_client, db_engine):
    with db_engine.begin() as conn:
        pid = conn.execute(
            text(
                "INSERT INTO tg_user_registry (pid, tg_user_id, created_via, created_at) "
                "VALUES (gen_random_uuid(), :tg, 'mini_app_first_launch', now()) "
                "RETURNING pid"
            ),
            {"tg": 2101},
        ).scalar_one()
    headers = _headers(2101)
    barrier = threading.Barrier(THREADS)

    def call(_: int):
        client = TestClient(main.app)
        barrier.wait(timeout=30)
        return client.post(FIRST_LAUNCH, headers=headers, json=BODY)

    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        responses = list(pool.map(call, range(THREADS)))

    assert [r.status_code for r in responses] == [201] * THREADS, [r.text for r in responses]
    assert {str(r.json()["pid"]) for r in responses} == {str(pid)}
    with db_engine.connect() as conn:
        gives = conn.execute(
            text("SELECT count(*) FROM consent_events WHERE pid = :p AND action = 'give'"),
            {"p": pid},
        ).scalar_one()
        kinds = conn.execute(
            text("SELECT kind FROM consent_events WHERE pid = :p AND action = 'give'"),
            {"p": pid},
        ).scalars().all()
    assert gives == 2
    assert sorted(kinds) == ["C0", "C1"]


def test_consent_events_check_constraints(db_engine, migrated_db):
    with db_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conrelid = 'consent_events'::regclass AND contype = 'c'"
            )
        ).all()
    defs = {name: definition for name, definition in rows}
    assert set(defs) == {
        "consent_events_kind_check",
        "consent_events_action_check",
        "consent_events_created_via_check",
    }
    for kind in ("C0", "C1", "C2", "C3", "C4", "C5", "C6"):
        assert f"'{kind}'" in defs["consent_events_kind_check"]
    for action in ("give", "revoke"):
        assert f"'{action}'" in defs["consent_events_action_check"]
    assert "'mini_app_first_launch'" in defs["consent_events_created_via_check"]
