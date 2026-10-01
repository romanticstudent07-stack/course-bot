"""POST /miniapp/v1/onboarding/first-launch — Итерации 1b+1c и 1e-1a (SEAM-1, ADD3, B-2).

Две группы:
  - без БД: 401/403/422/503, согласия (422 до БД), часовой пояс, логи
    (БД недоступна: если бы к ней обратились — был бы 503);
  - с БД (фикстуры db_*; нужен DATABASE_URL; db_engine заливает seed текстов):
    pid + согласия одной транзакцией, повтор без дублей, нет текста → 503 без pid,
    гонка, участник без согласий, CHECK/FK consent_events, tombstone (Р243).
"""
from __future__ import annotations

import logging
import re
import threading
import uuid
from datetime import date, datetime, timezone
from typing import get_args

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import CONSENT_KINDS
from app.participants import format_short_no, get_or_create_participant
from app.routers import onboarding
from app.telegram_init_data import INIT_DATA_HEADER
from tests.conftest import (
    FAKE_BOT_TOKEN,
    TEST_USER_ID,
    UNREACHABLE_DSN,
    count_consent_rows,
    count_registry_rows,
    valid_init_data,
)

FIRST_LAUNCH = "/miniapp/v1/onboarding/first-launch"
ADULT = "1990-01-01"
CONSENTS = ["C0", "C1"]
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
SHORT_NO_RE = re.compile(r"^#\d{6,}$")


def _headers(user_id: int = TEST_USER_ID, **user_extra) -> dict[str, str]:
    user = {"id": user_id, "first_name": "Test", **user_extra}
    return {INIT_DATA_HEADER: valid_init_data(user=user)}


def _body(birth_date: str = ADULT, consents: list[str] | None = None, **extra) -> dict:
    data = {"birth_date": birth_date, "consents": list(CONSENTS) if consents is None else consents}
    data.update(extra)
    return data


def _msk_today() -> date:
    return datetime.now(timezone.utc).astimezone(onboarding.ZoneInfo("Europe/Moscow")).date()


def _minor_birth_date(today: date) -> str:
    """Дата рождения, при которой сегодня 17 полных лет (18-летие — завтра)."""
    try:
        eighteenth_birthday_today = date(today.year - 18, today.month, today.day)
    except ValueError:  # сегодня 29 февраля, а 18 лет назад его не было
        return date(today.year - 18, 3, 1).isoformat()
    return date.fromordinal(eighteenth_birthday_today.toordinal() + 1).isoformat()


@pytest.fixture
def fixed_now(monkeypatch):
    """Зафиксировать «сейчас» (UTC) для first-launch."""

    def _set(moment: datetime) -> None:
        monkeypatch.setattr(onboarding, "_utc_now", lambda: moment)

    return _set


@pytest.fixture
def unreachable_db_client(api_client):
    """Синоним api_client (у него БД недоступна) — для читаемости тестов гейта."""
    return api_client


# ============================ без БД ============================


def test_no_init_data_is_401_missing(api_client):
    r = api_client.post(FIRST_LAUNCH, json=_body())
    assert r.status_code == 401
    assert r.json()["code"] == "TG_INIT_MISSING"


def test_forged_init_data_is_401_invalid(api_client):
    forged = valid_init_data().replace("Test", "Evil")  # подпись больше не сходится
    r = api_client.post(FIRST_LAUNCH, json=_body(), headers={INIT_DATA_HEADER: forged})
    assert r.status_code == 401
    assert r.json()["code"] == "TG_INIT_INVALID"


def test_body_without_init_data_but_with_tg_user_id_is_401(api_client):
    # tg_user_id в теле не даёт доступа — только проверенная initData.
    r = api_client.post(FIRST_LAUNCH, json=_body(tg_user_id=TEST_USER_ID))
    assert r.status_code == 401


def test_underage_is_403_without_touching_db(unreachable_db_client):
    # БД недоступна, но гейт отвечает 403 — значит, к БД не обращались (ADD3).
    r = unreachable_db_client.post(
        FIRST_LAUNCH, json=_body(_minor_birth_date(_msk_today())), headers=_headers()
    )
    assert r.status_code == 403
    body = r.json()
    assert body["code"] == "AGE_GATE_UNDERAGE"
    assert "pid" not in body and "short_no" not in body


def test_underage_without_consents_is_403_age_first(unreachable_db_client):
    # Порядок карточки: возраст (403) раньше проверки согласий (422).
    r = unreachable_db_client.post(
        FIRST_LAUNCH, json=_body(_minor_birth_date(_msk_today()), consents=[]), headers=_headers()
    )
    assert r.status_code == 403
    assert r.json()["code"] == "AGE_GATE_UNDERAGE"


def test_without_c1_is_422_consents_required_without_db(unreachable_db_client):
    r = unreachable_db_client.post(FIRST_LAUNCH, json=_body(consents=["C0"]), headers=_headers())
    assert r.status_code == 422  # не 503 → к БД не обращались
    body = r.json()
    assert body["code"] == "CONSENTS_REQUIRED"
    assert body["details"] == {"missing": ["C1"]}


def test_empty_consents_lists_both_missing(unreachable_db_client):
    r = unreachable_db_client.post(FIRST_LAUNCH, json=_body(consents=[]), headers=_headers())
    assert r.status_code == 422
    assert r.json()["details"] == {"missing": ["C0", "C1"]}


def test_duplicate_consent_id_is_422(unreachable_db_client):
    r = unreachable_db_client.post(
        FIRST_LAUNCH, json=_body(consents=["C0", "C1", "C1"]), headers=_headers()
    )
    assert r.status_code == 422
    assert "detail" in r.json()  # ошибка валидации тела (Pydantic), до обработчика


def test_unknown_consent_id_is_422(unreachable_db_client):
    r = unreachable_db_client.post(
        FIRST_LAUNCH, json=_body(consents=["C0", "C1", "C9"]), headers=_headers()
    )
    assert r.status_code == 422
    assert "detail" in r.json()


def test_old_body_without_consents_is_422(unreachable_db_client):
    r = unreachable_db_client.post(FIRST_LAUNCH, json={"birth_date": ADULT}, headers=_headers())
    assert r.status_code == 422


def test_consent_not_accepted_at_first_launch_is_422(unreachable_db_client):
    # C5 — со своим экраном перед фото; C2–C4, C6 — не в И1 (решение «В1 А»).
    r = unreachable_db_client.post(
        FIRST_LAUNCH, json=_body(consents=["C0", "C1", "C5"]), headers=_headers()
    )
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "CONSENT_NOT_SUPPORTED"
    assert body["details"] == {"unsupported": ["C5"]}


def test_consent_constants():
    assert set(get_args(onboarding.ConsentId)) == set(CONSENT_KINDS)
    assert onboarding.REQUIRED_AT_FIRST_LAUNCH == {"C0", "C1"}
    assert onboarding.REQUIRED_AT_FIRST_LAUNCH <= set(onboarding.CONSENT_TEXT_KEYS)
    assert all(k.startswith("legal.") for k in onboarding.CONSENT_TEXT_KEYS.values())


def test_future_birth_date_is_422(unreachable_db_client):
    r = unreachable_db_client.post(FIRST_LAUNCH, json=_body("2999-01-01"), headers=_headers())
    assert r.status_code == 422
    assert r.json()["code"] == "BIRTH_DATE_IN_FUTURE"


def test_missing_birth_date_is_422(api_client):
    r = api_client.post(FIRST_LAUNCH, json={"consents": CONSENTS}, headers=_headers())
    assert r.status_code == 422


def test_db_unavailable_is_503_service_unavailable(unreachable_db_client):
    r = unreachable_db_client.post(FIRST_LAUNCH, json=_body(), headers=_headers())
    assert r.status_code == 503
    body = r.json()
    assert body["code"] == "SERVICE_UNAVAILABLE"
    assert set(body) <= {"code", "message", "details"}
    assert "127.0.0.1" not in r.text and "nopass" not in r.text


def test_unknown_server_timezone_is_503_misconfigured():
    from fastapi.testclient import TestClient

    from main import app

    app.dependency_overrides[get_settings] = lambda: Settings(
        bot_token=FAKE_BOT_TOKEN, database_url=UNREACHABLE_DSN, server_timezone="Mars/Olympus"
    )
    try:
        r = TestClient(app).post(FIRST_LAUNCH, json=_body(), headers=_headers())
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 503
    assert r.json()["code"] == "SERVICE_MISCONFIGURED"


def test_age_uses_server_timezone_not_utc(unreachable_db_client, fixed_now):
    # 2026-09-23 20:30 UTC = 2026-09-23 23:30 MSK: 18-летие (2008-09-24) ещё завтра → 403.
    fixed_now(datetime(2026, 9, 23, 20, 30, tzinfo=timezone.utc))
    r = unreachable_db_client.post(FIRST_LAUNCH, json=_body("2008-09-24"), headers=_headers())
    assert r.status_code == 403
    # 2026-09-23 21:30 UTC = 2026-09-24 00:30 MSK: по MSK уже 18 → гейт пройден
    # (дальше БД, она здесь недоступна → 503, а не 403). По UTC было бы ещё 17.
    fixed_now(datetime(2026, 9, 23, 21, 30, tzinfo=timezone.utc))
    r = unreachable_db_client.post(FIRST_LAUNCH, json=_body("2008-09-24"), headers=_headers())
    assert r.status_code == 503


def test_underage_log_has_only_reason(unreachable_db_client, caplog):
    caplog.set_level(logging.DEBUG)
    minor = _minor_birth_date(_msk_today())
    r = unreachable_db_client.post(
        FIRST_LAUNCH, json=_body(minor), headers=_headers(user_id=777001, username="secret_nick")
    )
    assert r.status_code == 403
    assert "reason=underage" in caplog.text
    assert "777001" not in caplog.text  # без tg_user_id (решение Автора)
    assert "secret_nick" not in caplog.text and "Test" not in caplog.text
    assert minor not in caplog.text


def test_consents_required_log_has_only_reason(unreachable_db_client, caplog):
    caplog.set_level(logging.DEBUG)
    r = unreachable_db_client.post(
        FIRST_LAUNCH, json=_body(consents=["C0"]), headers=_headers(user_id=777002)
    )
    assert r.status_code == 422
    assert "reason=consents_required missing=C1" in caplog.text
    assert "777002" not in caplog.text and ADULT not in caplog.text


@pytest.mark.parametrize(
    ("value", "expected"),
    [(1, "#000001"), (123, "#000123"), (999999, "#999999"), (1000000, "#1000000")],
)
def test_format_short_no(value, expected):
    assert format_short_no(value) == expected


def test_minor_birth_date_helper_is_17():
    for today in (date(2026, 9, 24), date(2028, 2, 29), date(2026, 12, 31), date(2027, 3, 1)):
        born = date.fromisoformat(_minor_birth_date(today))
        assert onboarding.full_years(born, today) == 17


# ============================ с БД ============================


def _consent_rows(engine, pid: uuid.UUID):
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT id, kind, action, at, ver_of_text, text_key, text_snapshot, ip, ua, "
                "created_via FROM consent_events WHERE pid = :p ORDER BY kind"
            ),
            {"p": pid},
        ).all()


def _registry_text(engine, key: str):
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT text, registry_version FROM text_registry WHERE key = :k"), {"k": key}
        ).one()


def _insert_participant(engine, tg_user_id: int) -> uuid.UUID:
    pid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tg_user_registry (pid, tg_user_id, created_via) "
                "VALUES (:pid, :u, 'mini_app_first_launch')"
            ),
            {"pid": pid, "u": tg_user_id},
        )
    return pid


def test_create_returns_201_by_contract(db_api_client, db_engine):
    r = db_api_client.post(FIRST_LAUNCH, json=_body(), headers=_headers())
    assert r.status_code == 201
    body = r.json()
    assert set(body) == {"pid", "short_no"}  # PidCreated, без лишних полей (и без details)
    assert UUID_RE.match(body["pid"])
    assert SHORT_NO_RE.match(body["short_no"])
    assert count_registry_rows(db_engine, TEST_USER_ID) == 1
    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT pid, created_via, tombstoned_at FROM tg_user_registry WHERE tg_user_id=:u"),
            {"u": TEST_USER_ID},
        ).one()
    assert str(row.pid) == body["pid"]
    assert row.created_via == "mini_app_first_launch"
    assert row.tombstoned_at is None


def test_create_writes_two_consents_with_text_snapshot(db_api_client, db_engine):
    r = db_api_client.post(FIRST_LAUNCH, json=_body(), headers=_headers())
    assert r.status_code == 201
    pid = uuid.UUID(r.json()["pid"])
    rows = _consent_rows(db_engine, pid)
    assert [row.kind for row in rows] == ["C0", "C1"]
    for row in rows:
        snapshot, version = _registry_text(db_engine, row.text_key)
        assert row.action == "give"
        assert row.text_key == onboarding.CONSENT_TEXT_KEYS[row.kind]
        assert row.text_snapshot == snapshot
        assert row.text_snapshot.startswith("[ЗАГЛУШКА]")
        assert row.ver_of_text == version
        assert row.ip is None and row.ua is None  # в И1 не собираем
        assert row.created_via == "mini_app_first_launch"
        assert row.at is not None
    assert count_registry_rows(db_engine) == 1
    assert count_consent_rows(db_engine) == 2


def test_repeat_call_is_201_same_body_no_duplicate(db_api_client, db_engine):
    first = db_api_client.post(FIRST_LAUNCH, json=_body(), headers=_headers())
    pid = uuid.UUID(first.json()["pid"])
    before = [(row.id, row.at) for row in _consent_rows(db_engine, pid)]
    second = db_api_client.post(FIRST_LAUNCH, json=_body(), headers=_headers())
    # Повтор с другой (тоже взрослой) датой — всё равно тот же участник: ДР не хранится.
    third = db_api_client.post(FIRST_LAUNCH, json=_body("1985-06-15"), headers=_headers())
    assert first.status_code == second.status_code == third.status_code == 201
    assert first.json() == second.json() == third.json()
    assert count_registry_rows(db_engine) == 1
    assert count_consent_rows(db_engine) == 2
    assert [(row.id, row.at) for row in _consent_rows(db_engine, pid)] == before


def test_missing_consent_text_is_503_and_no_pid(db_api_client, db_engine):
    with db_engine.begin() as conn:
        conn.execute(text("DELETE FROM text_registry WHERE key = 'legal.consent_c1_pdn'"))
    r = db_api_client.post(FIRST_LAUNCH, json=_body(), headers=_headers())
    assert r.status_code == 503
    assert r.json()["code"] == "SERVICE_MISCONFIGURED"
    assert count_registry_rows(db_engine) == 0
    assert count_consent_rows(db_engine) == 0


def test_existing_pid_without_consents_gets_them_once(db_api_client, db_engine):
    # Участник, созданный до 0004 (без согласий): повтор first-launch дописывает их один раз.
    pid = _insert_participant(db_engine, 5201)
    r1 = db_api_client.post(FIRST_LAUNCH, json=_body(), headers=_headers(5201))
    r2 = db_api_client.post(FIRST_LAUNCH, json=_body(), headers=_headers(5201))
    assert r1.status_code == r2.status_code == 201
    assert r1.json()["pid"] == r2.json()["pid"] == str(pid)
    assert count_registry_rows(db_engine, 5201) == 1
    assert count_consent_rows(db_engine, pid) == 2


def test_different_users_get_different_pid_and_short_no(db_api_client, db_engine):
    a = db_api_client.post(FIRST_LAUNCH, json=_body(), headers=_headers(1001)).json()
    b = db_api_client.post(FIRST_LAUNCH, json=_body(), headers=_headers(1002)).json()
    assert a["pid"] != b["pid"]
    assert a["short_no"] != b["short_no"]
    assert count_registry_rows(db_engine) == 2
    assert count_consent_rows(db_engine) == 4


def test_underage_creates_no_row(db_api_client, db_engine):
    # ADD3 ci_check no_pid_before_age_hardcheck.
    r = db_api_client.post(
        FIRST_LAUNCH, json=_body(_minor_birth_date(_msk_today())), headers=_headers(2001)
    )
    assert r.status_code == 403
    assert count_registry_rows(db_engine, 2001) == 0
    assert count_consent_rows(db_engine) == 0


def test_without_required_consent_creates_no_row(db_api_client, db_engine):
    r = db_api_client.post(FIRST_LAUNCH, json=_body(consents=["C1"]), headers=_headers(2002))
    assert r.status_code == 422
    assert count_registry_rows(db_engine, 2002) == 0
    assert count_consent_rows(db_engine) == 0


def test_rejected_init_data_creates_no_row(db_api_client, db_engine):
    db_api_client.post(FIRST_LAUNCH, json=_body())
    forged = valid_init_data().replace("Test", "Evil")
    db_api_client.post(FIRST_LAUNCH, json=_body(), headers={INIT_DATA_HEADER: forged})
    assert count_registry_rows(db_engine) == 0


def test_tg_user_id_from_body_is_ignored(db_api_client, db_engine):
    r = db_api_client.post(
        FIRST_LAUNCH,
        json=_body(tg_user_id=999999, pid=str(uuid.uuid4())),
        headers=_headers(3001),
    )
    assert r.status_code == 201
    assert count_registry_rows(db_engine, 3001) == 1
    assert count_registry_rows(db_engine, 999999) == 0
    assert count_registry_rows(db_engine) == 1


def test_create_log_has_tg_user_id_and_outcome_only(db_api_client, caplog):
    caplog.set_level(logging.DEBUG)
    headers = _headers(4001, username="secret_nick", last_name="Secretov")
    db_api_client.post(FIRST_LAUNCH, json=_body(), headers=headers)
    db_api_client.post(FIRST_LAUNCH, json=_body(), headers=headers)
    assert "tg_user_id=4001 outcome=created consents_recorded=2" in caplog.text
    assert "tg_user_id=4001 outcome=existing consents_recorded=0" in caplog.text
    for secret in ("secret_nick", "Secretov", ADULT, headers[INIT_DATA_HEADER], FAKE_BOT_TOKEN):
        assert secret not in caplog.text
    assert "[ЗАГЛУШКА]" not in caplog.text  # текст согласия в лог не попадает


def _run_concurrently(workers: int, target) -> tuple[list, list]:
    barrier = threading.Barrier(workers)
    results: list = []
    errors: list = []
    lock = threading.Lock()

    def run() -> None:
        try:
            barrier.wait(timeout=10)
            value = target()
            with lock:
                results.append(value)
        except Exception as exc:  # noqa: BLE001 — любую ошибку потока покажет assert ниже
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results, errors


def test_concurrent_first_launch_same_user_single_row(db_engine):
    """Гонка get_or_create: N потоков, у каждого своё соединение; commit — у вызывающего."""

    def call():
        with Session(db_engine) as session:
            p = get_or_create_participant(session, 5001)
            session.commit()
            return p

    results, errors = _run_concurrently(8, call)
    assert not errors, errors
    assert len(results) == 8
    assert len({p.pid for p in results}) == 1
    assert len({p.short_no for p in results}) == 1
    assert sum(p.created for p in results) == 1
    assert count_registry_rows(db_engine, 5001) == 1


def test_concurrent_registration_single_pid_no_duplicate_consents(db_engine):
    """Гонка шага 5 целиком: один pid и ровно 2 строки consent_events."""

    def call():
        with Session(db_engine) as session:
            return onboarding.register_with_consents(session, 5101, CONSENTS)

    results, errors = _run_concurrently(8, call)
    assert not errors, errors
    assert len(results) == 8
    assert len({r.participant.pid for r in results}) == 1
    assert sum(r.participant.created for r in results) == 1
    assert sum(r.consents_recorded for r in results) == 2
    assert count_registry_rows(db_engine, 5101) == 1
    assert count_consent_rows(db_engine) == 2


def test_get_or_create_does_not_commit(db_engine):
    # Транзакцией владеет вызывающий: без commit строки нет.
    with Session(db_engine) as session:
        get_or_create_participant(session, 5301)
        session.rollback()
    assert count_registry_rows(db_engine, 5301) == 0


def test_unique_index_rejects_second_active_row(db_engine):
    insert = text(
        "INSERT INTO tg_user_registry (pid, tg_user_id, created_via) "
        "VALUES (:pid, :u, 'mini_app_first_launch')"
    )
    with db_engine.begin() as conn:
        conn.execute(insert, {"pid": uuid.uuid4(), "u": 6001})
    with pytest.raises(IntegrityError), db_engine.begin() as conn:
        conn.execute(insert, {"pid": uuid.uuid4(), "u": 6001})
    assert count_registry_rows(db_engine, 6001) == 1


@pytest.mark.parametrize(
    ("tg_user_id", "created_via"),
    [(0, "mini_app_first_launch"), (-5, "mini_app_first_launch"), (7001, "bot_start")],
)
def test_check_constraints(db_engine, tg_user_id, created_via):
    # created_via — только mini_app_first_launch (SEAM-1: бот участника не создаёт).
    with pytest.raises(IntegrityError), db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tg_user_registry (pid, tg_user_id, created_via) "
                "VALUES (:pid, :u, :v)"
            ),
            {"pid": uuid.uuid4(), "u": tg_user_id, "v": created_via},
        )


@pytest.mark.parametrize(
    ("kind", "action", "text_key", "created_via"),
    [
        ("C9", "give", "legal.consent_c1_pdn", "mini_app_first_launch"),
        ("C1", "maybe", "legal.consent_c1_pdn", "mini_app_first_launch"),
        ("C1", "give", "legal.no_such_text", "mini_app_first_launch"),
        ("C1", "give", "legal.consent_c1_pdn", "bot_start"),
    ],
)
def test_consent_events_constraints(db_engine, kind, action, text_key, created_via):
    pid = _insert_participant(db_engine, 7101)
    with pytest.raises(IntegrityError), db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO consent_events "
                "(pid, kind, action, ver_of_text, text_key, text_snapshot, created_via) "
                "VALUES (:pid, :k, :a, '0.1.0', :t, '[ЗАГЛУШКА] x', :v)"
            ),
            {"pid": pid, "k": kind, "a": action, "t": text_key, "v": created_via},
        )
    assert count_consent_rows(db_engine) == 0


def test_consent_events_unknown_pid_rejected(db_engine):
    with pytest.raises(IntegrityError), db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO consent_events "
                "(pid, kind, action, ver_of_text, text_key, text_snapshot, created_via) "
                "VALUES (:pid, 'C1', 'give', '0.1.0', 'legal.consent_c1_pdn', "
                "'[ЗАГЛУШКА] x', 'mini_app_first_launch')"
            ),
            {"pid": uuid.uuid4()},
        )


def test_short_no_cannot_be_set_manually(db_engine):
    # GENERATED ALWAYS: ручное значение short_no отвергается (psycopg → ProgrammingError).
    from sqlalchemy.exc import ProgrammingError

    with pytest.raises(ProgrammingError), db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tg_user_registry (pid, tg_user_id, created_via, short_no) "
                "VALUES (:pid, 8001, 'mini_app_first_launch', 1)"
            ),
            {"pid": uuid.uuid4()},
        )


def test_after_tombstone_same_user_gets_new_pid(db_api_client, db_engine):
    # И1 tombstone_semantics / Р243: новая регистрация того же tg_user_id → новый pid.
    first = db_api_client.post(FIRST_LAUNCH, json=_body(), headers=_headers(9001))
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE tg_user_registry SET tombstoned_at = now() WHERE tg_user_id = 9001")
        )
    second = db_api_client.post(FIRST_LAUNCH, json=_body(), headers=_headers(9001))
    assert first.status_code == second.status_code == 201
    assert first.json()["pid"] != second.json()["pid"]
    assert first.json()["short_no"] != second.json()["short_no"]
    assert count_registry_rows(db_engine, 9001) == 2
    # Новый pid получает свои согласия: согласия старого pid не переносятся.
    assert count_consent_rows(db_engine, uuid.UUID(second.json()["pid"])) == 2
    third = db_api_client.post(FIRST_LAUNCH, json=_body(), headers=_headers(9001))
    assert third.json() == second.json()
