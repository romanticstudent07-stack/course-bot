"""B-3b: откат first-launch при ошибке БД, гонка участника до 0004, CHECK consent_events.

Только с живой БД (CI): без неё фикстуры db_engine / db_api_client пропускают тесты.
Соединение CI — суперпользователь: временные функция и триггер разрешены.
"""
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from sqlalchemy import text

import main
from tests.conftest import count_consent_rows, count_registry_rows, valid_init_data

FIRST_LAUNCH = "/miniapp/v1/onboarding/first-launch"
INIT_HEADER = "X-Telegram-Init-Data"
BODY = {"birth_date": "1990-01-01", "consents": ["C0", "C1"]}
FUNC = "b3b_test_fail_consent"
TRIGGER = "b3b_test_fail_consent_trg"


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
    assert r.status_code in (500, 503), r.text
    assert count_registry_rows(db_engine, 2001) == 0
    assert count_consent_rows(db_engine) == 0


def test_internal_error_on_consent_insert_rolls_back_participant(db_api_client, db_engine):
    try:
        _install_failing_trigger(db_engine, None)
        r = db_api_client.post(FIRST_LAUNCH, headers=_headers(2002), json=BODY)
    finally:
        _drop_failing_trigger(db_engine)
    assert r.status_code in (500, 503), r.text
    assert "code" in r.json()
    assert "b3b-test" not in r.text
    assert count_registry_rows(db_engine, 2002) == 0
    assert count_consent_rows(db_engine) == 0


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

    def call(_: int):
        client = TestClient(main.app)
        return client.post(FIRST_LAUNCH, headers=headers, json=BODY)

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(call, range(8)))

    assert [r.status_code for r in responses] == [201] * 8, [r.text for r in responses]
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
