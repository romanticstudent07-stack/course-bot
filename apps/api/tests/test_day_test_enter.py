"""POST /day/test-enter (iter2-api-2a): флаг, замок, событие day_entered. С БД — только CI."""
import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import Settings
from app.day_content import get_day_content
from app.projector import ProjectorResult, run_once
from app.routers.day import enter_day_by_test_flag, read_day_current
from app.routers.onboarding import register_with_consents


class _NoDb:
    def __getattr__(self, name):
        raise AssertionError("при выключенном флаге БД трогать нельзя")


def _registered(engine, tg_user_id: int):
    with Session(engine) as session:
        return register_with_consents(session, tg_user_id, ["C0", "C1"]).participant.pid


def _bare(engine, tg_user_id: int):
    with engine.begin() as conn:
        return conn.execute(
            text(
                "INSERT INTO tg_user_registry (pid, tg_user_id, created_via, created_at) "
                "VALUES (gen_random_uuid(), :u, 'mini_app_first_launch', now()) RETURNING pid"
            ),
            {"u": tg_user_id},
        ).scalar_one()


def _count(engine, sql: str, pid) -> int:
    with engine.connect() as conn:
        return conn.execute(text(sql), {"p": pid}).scalar_one()


def _entered(engine, pid) -> int:
    return _count(
        engine, "SELECT count(*) FROM participant_events WHERE pid = :p AND kind = 'day_entered'", pid
    )


def _keys(engine, pid) -> int:
    return _count(
        engine, "SELECT count(*) FROM idempotency_keys WHERE key = 'day_enter:' || CAST(:p AS text)", pid
    )


def _enter(engine, tg_user_id: int, enabled: bool = True):
    with Session(engine) as session:
        return enter_day_by_test_flag(session, tg_user_id, enabled)


def _error_code(engine, tg_user_id: int, enabled: bool = True) -> HTTPException:
    with pytest.raises(HTTPException) as exc:
        _enter(engine, tg_user_id, enabled)
    return exc.value


def test_flag_default_off():
    assert Settings().day_test_entry_enabled is False


def test_flag_off_404_before_db():
    with pytest.raises(HTTPException) as exc:
        enter_day_by_test_flag(_NoDb(), 1, False)
    assert exc.value.status_code == 404
    assert exc.value.detail["code"] == "NOT_FOUND"


def test_flag_off_no_events(db_engine):
    pid = _registered(db_engine, 8001)
    run_once(db_engine)
    assert _error_code(db_engine, 8001, enabled=False).status_code == 404
    assert _entered(db_engine, pid) == 0


def test_reconsent_required(db_engine):
    pid = _bare(db_engine, 8002)  # участник без согласий C0 / C1
    err = _error_code(db_engine, 8002)
    assert (err.status_code, err.detail["code"]) == (409, "RECONSENT_REQUIRED")
    assert _entered(db_engine, pid) == 0


def test_no_state_syncing(db_engine):
    pid = _registered(db_engine, 8003)  # проектор ещё не запускался
    err = _error_code(db_engine, 8003)
    assert (err.status_code, err.detail["code"]) == (409, "DAY_STATE_SYNCING")
    assert err.headers == {"Retry-After": "1"}
    assert _entered(db_engine, pid) == 0


def test_enter_then_repeat_then_already(db_engine):
    content = get_day_content()
    pid = _registered(db_engine, 8004)
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    with Session(db_engine) as session:
        before = read_day_current(session, 8004, content, True)
    assert (before.status, before.test_entry) == ("not_started", True)

    assert _enter(db_engine, 8004).status == "entering"
    assert (_entered(db_engine, pid), _keys(db_engine, pid)) == (1, 1)
    assert _enter(db_engine, 8004).status == "entering"
    assert (_entered(db_engine, pid), _keys(db_engine, pid)) == (1, 1)
    with Session(db_engine) as session:
        assert read_day_current(session, 8004, content, True).status == "entering"

    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    assert _enter(db_engine, 8004).status == "already"
    assert _entered(db_engine, pid) == 1
    with Session(db_engine) as session:
        after = read_day_current(session, 8004, content, True)
    assert (after.status, after.test_entry) == ("open", False)
    with db_engine.connect() as conn:
        phase = conn.execute(
            text("SELECT lifecycle_phase FROM participant_state WHERE pid = :p"), {"p": pid}
        ).scalar_one()
    assert phase == "onboarding"  # В21: фаза не меняется


def test_tombstoned_404_nothing_written(db_engine):
    pid = _registered(db_engine, 8005)
    run_once(db_engine)
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE tg_user_registry SET tombstoned_at = now() WHERE pid = :p"), {"p": pid}
        )
    err = _error_code(db_engine, 8005)
    assert (err.status_code, err.detail["code"]) == (404, "PARTICIPANT_NOT_FOUND")
    assert (_entered(db_engine, pid), _keys(db_engine, pid)) == (0, 0)
