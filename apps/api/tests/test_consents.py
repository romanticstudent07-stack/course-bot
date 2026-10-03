"""GET /miniapp/v1/consents — чтение своих согласий (1e-2, B-2; ревью #43 — 1e-2b-3).

Без БД: fold_events (последнее событие решает), 401, 503,
невалидная initData → 401 раньше rate-limit (фейковый счётчик не вызван).
С БД (DATABASE_URL, в CI обязательно): нет участника → [], после first-launch → C0 и C1,
изоляция между tg_user_id (параметры запроса игнорируются; в т.ч. когда у обоих есть pid),
revoke, tombstone, GET ничего не пишет, перезагрузка текстов не меняет ver_of_text
старых записей (D-15 в).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.routers.consents import EventRow, fold_events
from app.telegram_init_data import INIT_DATA_HEADER
from app.texts import load_seed, write_entries
from tests.conftest import count_consent_rows, count_registry_rows, valid_init_data

URL = "/miniapp/v1/consents"
FIRST_LAUNCH = "/miniapp/v1/onboarding/first-launch"
BODY = {"birth_date": "1990-01-01", "consents": ["C0", "C1"]}
T0 = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)
C0_KEY = "legal.consent_c0_age_18_plus"
C1_KEY = "legal.consent_c1_pdn"


def _headers(user_id: int) -> dict[str, str]:
    return {INIT_DATA_HEADER: valid_init_data(user={"id": user_id, "first_name": "Test"})}


def _ev(kind: str, action: str, minutes: int, key: str = C1_KEY) -> EventRow:
    return EventRow(kind=kind, action=action, at=T0 + timedelta(minutes=minutes), text_key=key)


def _insert_event(engine, pid: str, kind: str, action: str, ver: str = "0.2.0") -> None:
    key = C0_KEY if kind == "C0" else C1_KEY
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO consent_events "
                "(pid, kind, action, at, ver_of_text, text_key, text_snapshot, created_via) "
                "VALUES (:pid, :k, :a, now() + interval '1 minute', :v, :t, "
                "'[ЗАГЛУШКА] x', 'mini_app_first_launch')"
            ),
            {"pid": uuid.UUID(pid), "k": kind, "a": action, "v": ver, "t": key},
        )


# ============================ без БД ============================


def test_fold_give_only_sorted_by_kind():
    out = fold_events([_ev("C1", "give", 0), _ev("C0", "give", 0, C0_KEY)])
    assert [(c.kind, c.given_at, c.revoked_at, c.text_key) for c in out] == [
        ("C0", T0, None, C0_KEY),
        ("C1", T0, None, C1_KEY),
    ]


def test_fold_last_event_wins():
    out = fold_events([_ev("C1", "give", 0), _ev("C1", "revoke", 5)])
    assert len(out) == 1
    assert out[0].given_at == T0
    assert out[0].revoked_at == T0 + timedelta(minutes=5)
    out = fold_events([_ev("C1", "give", 0), _ev("C1", "revoke", 5), _ev("C1", "give", 9)])
    assert out[0].given_at == T0 + timedelta(minutes=9)
    assert out[0].revoked_at is None


def test_fold_revoke_without_give_is_skipped():
    assert fold_events([_ev("C2", "revoke", 0)]) == []
    assert fold_events([]) == []


def test_no_init_data_is_401(api_client):
    r = api_client.get(URL)
    assert r.status_code == 401
    assert r.json()["code"] == "TG_INIT_MISSING"


def test_forged_init_data_is_401(api_client):
    forged = valid_init_data().replace("Test", "Evil")
    r = api_client.get(URL, headers={INIT_DATA_HEADER: forged})
    assert r.status_code == 401
    assert r.json()["code"] == "TG_INIT_INVALID"


def test_db_unavailable_is_503(api_client):
    r = api_client.get(URL, headers=_headers(42))
    assert r.status_code == 503
    assert r.json()["code"] == "SERVICE_UNAVAILABLE"
    assert "127.0.0.1" not in r.text and "nopass" not in r.text


def test_invalid_init_data_401_rate_limit_counter_not_called(api_client):
    # Ревью #43: без валидной initData — 401 раньше счётчика rate-limit.
    from main import app
    from app.rate_limit import get_counter

    class FakeCounter:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int]] = []

        def incr(self, key: str, ttl_seconds: int) -> int:
            self.calls.append((key, ttl_seconds))
            return 1

    counter = FakeCounter()
    # Подмену очистит фикстура api_client (app.dependency_overrides.clear()).
    app.dependency_overrides[get_counter] = lambda: counter

    forged = valid_init_data().replace("Test", "Evil")
    r = api_client.get(URL, headers={INIT_DATA_HEADER: forged})
    assert r.status_code == 401
    assert r.json()["code"] == "TG_INIT_INVALID"
    assert counter.calls == []

    # Контроль подмены: с валидной initData счётчик вызывается (дальше 503 — БД недоступна).
    r = api_client.get(URL, headers=_headers(42))
    assert r.status_code == 503
    assert len(counter.calls) == 1


# ============================ с БД ============================


def test_no_participant_is_empty_list(db_api_client):
    r = db_api_client.get(URL, headers=_headers(1001))
    assert r.status_code == 200
    assert r.json() == []


def test_after_first_launch_c0_and_c1(db_api_client):
    assert db_api_client.post(FIRST_LAUNCH, json=BODY, headers=_headers(1002)).status_code == 201
    r = db_api_client.get(URL, headers=_headers(1002))
    assert r.status_code == 200
    body = r.json()
    assert [c["id"] for c in body] == ["C0", "C1"]
    for c in body:
        assert set(c) == {"id", "given_at", "revoked_at", "legal_status"}
        assert c["given_at"]
        assert c["revoked_at"] is None
        assert c["legal_status"] == "pre-legal-review"


def test_isolation_between_users(db_api_client, db_engine):
    a = db_api_client.post(FIRST_LAUNCH, json=BODY, headers=_headers(1101)).json()
    # B без участника не видит согласий A, даже если подставит pid и tg_user_id A в запрос.
    r = db_api_client.get(
        URL, params={"tg_user_id": 1101, "pid": a["pid"]}, headers=_headers(1102)
    )
    assert r.status_code == 200
    assert r.json() == []
    db_api_client.post(FIRST_LAUNCH, json=BODY, headers=_headers(1102))
    _insert_event(db_engine, a["pid"], "C1", "revoke")
    a_view = {c["id"]: c for c in db_api_client.get(URL, headers=_headers(1101)).json()}
    b_view = {c["id"]: c for c in db_api_client.get(URL, headers=_headers(1102)).json()}
    assert a_view["C1"]["revoked_at"] is not None
    assert a_view["C0"]["revoked_at"] is None
    assert set(b_view) == {"C0", "C1"}
    assert all(c["revoked_at"] is None for c in b_view.values())


def test_isolation_both_have_pid_query_params_ignored(db_api_client, db_engine):
    # Ревью #43: у A и B свои pid; B подставляет pid и tg_user_id A — видит только свои согласия.
    ra = db_api_client.post(FIRST_LAUNCH, json=BODY, headers=_headers(1501))
    rb = db_api_client.post(FIRST_LAUNCH, json=BODY, headers=_headers(1502))
    assert ra.status_code == 201
    assert rb.status_code == 201
    pid_a = ra.json()["pid"]
    pid_b = rb.json()["pid"]
    assert pid_a != pid_b
    # Метка: у A C1 отозвано — утечка согласий A в ответ B стала бы видна.
    _insert_event(db_engine, pid_a, "C1", "revoke")

    r1 = db_api_client.get(
        URL, params={"pid": pid_a, "tg_user_id": 1501}, headers=_headers(1502)
    )
    assert r1.status_code == 200
    body = r1.json()
    assert [c["id"] for c in body] == ["C0", "C1"]
    assert all(c["revoked_at"] is None for c in body)

    r2 = db_api_client.get(URL, headers=_headers(1502))
    assert r2.status_code == 200
    assert r1.json() == r2.json()


def test_tombstoned_participant_is_empty_list(db_api_client, db_engine):
    db_api_client.post(FIRST_LAUNCH, json=BODY, headers=_headers(1201))
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE tg_user_registry SET tombstoned_at = now() WHERE tg_user_id = 1201")
        )
    r = db_api_client.get(URL, headers=_headers(1201))
    assert r.status_code == 200
    assert r.json() == []


def test_get_writes_nothing(db_api_client, db_engine):
    db_api_client.post(FIRST_LAUNCH, json=BODY, headers=_headers(1301))
    before = (count_registry_rows(db_engine), count_consent_rows(db_engine))
    db_api_client.get(URL, headers=_headers(1301))
    db_api_client.get(URL, headers=_headers(1302))  # без участника — тоже ничего не создаёт
    assert (count_registry_rows(db_engine), count_consent_rows(db_engine)) == before
    assert count_registry_rows(db_engine, 1302) == 0


def test_reload_texts_keeps_old_ver_of_text(db_api_client, db_engine):
    # D-15 в: смена версии текстов (0.2.0) не меняет ver_of_text уже записанных согласий.
    pid = db_api_client.post(FIRST_LAUNCH, json=BODY, headers=_headers(1401)).json()["pid"]
    _insert_event(db_engine, pid, "C1", "give", ver="0.1.0")
    write_entries(db_engine, load_seed())
    with db_engine.connect() as conn:
        versions = conn.execute(
            text("SELECT ver_of_text FROM consent_events WHERE pid = :p ORDER BY id"),
            {"p": uuid.UUID(pid)},
        ).scalars().all()
    assert versions[-1] == "0.1.0"
    assert len(versions) == 3
