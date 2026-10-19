"""Проектор: kind day_report_submitted (iter2-api-2b, В18, Ш1). С БД — только CI.

missed_streak = 0 только при совпадении day_started_at с payload (текущий день);
старый день и битый payload → WARNING и пропуск; status_flags, lives и фаза не меняются.
Тестовое состояние (missed_streak, status_flags, lives) готовится прямым UPDATE от владельца
БД — только в тесте; API participant_state не пишет.
"""
import json
import logging

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.day_keys import dsa
from app.projector import EVENT_KIND_DAY_REPORT_SUBMITTED, ProjectorResult, run_once
from app.routers.day import enter_day_by_test_flag
from app.routers.onboarding import register_with_consents

OLD_DAY = "2001-01-01T00:00:00+00:00"


def _open_day(engine, tg_user_id: int):
    with Session(engine) as session:
        pid = register_with_consents(session, tg_user_id, ["C0", "C1"]).participant.pid
    run_once(engine)
    with Session(engine) as session:
        enter_day_by_test_flag(session, tg_user_id, True)
    run_once(engine)
    with engine.connect() as conn:
        started = conn.execute(
            text("SELECT day_started_at FROM participant_state WHERE pid = :p"), {"p": pid}
        ).scalar_one()
    return pid, started


def _prepare(engine, pid) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE participant_state SET missed_streak = 2, "
                "status_flags = CAST(:f AS text[]), lives = 2 WHERE pid = :p"
            ),
            {"p": pid, "f": "{block_lives}"},
        )


def _event(engine, pid, payload) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO participant_events (pid, kind, payload, actor, actor_role) "
                "VALUES (:p, :k, CAST(:pl AS jsonb), 'participant', 'participant')"
            ),
            {"p": pid, "k": EVENT_KIND_DAY_REPORT_SUBMITTED, "pl": json.dumps(payload)},
        )


def _state(engine, pid):
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT missed_streak, status_flags, lives, lifecycle_phase, day_started_at "
                "FROM participant_state WHERE pid = :p"
            ),
            {"p": pid},
        ).one()


def _payload(started_str: str, verdict: str = "passed") -> dict:
    return {
        "day_started_at": started_str,
        "verdict": verdict,
        "stage_no": 1,
        "module_no": 1,
        "day_no": 1,
    }


@pytest.mark.parametrize("verdict", ["passed", "not_passed", "all_not_done"])
def test_current_day_resets_missed_streak(db_engine, verdict):
    pid, started = _open_day(db_engine, 9401)
    _prepare(db_engine, pid)
    _event(db_engine, pid, _payload(dsa(started), verdict))
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    state = _state(db_engine, pid)
    assert state.missed_streak == 0  # В18: любой вердикт
    assert list(state.status_flags) == ["block_lives"]
    assert state.lives == 2  # Ш1: жизни не меняются
    assert state.lifecycle_phase == "onboarding"
    assert dsa(state.day_started_at) == dsa(started)


def test_old_day_skipped_with_warning(db_engine, caplog):
    pid, _ = _open_day(db_engine, 9402)
    _prepare(db_engine, pid)
    _event(db_engine, pid, _payload(OLD_DAY))
    with caplog.at_level(logging.WARNING, logger="app.projector"):
        assert run_once(db_engine) == ProjectorResult(processed=0, skipped=1)
    assert _state(db_engine, pid).missed_streak == 2
    messages = [r.getMessage() for r in caplog.records if r.name == "app.projector"]
    assert any(f"kind={EVENT_KIND_DAY_REPORT_SUBMITTED}" in m for m in messages)
    assert all(str(pid) not in m for m in messages)


def test_bad_payload_skipped_next_event_applied(db_engine):
    pid, started = _open_day(db_engine, 9403)
    _prepare(db_engine, pid)
    _event(db_engine, pid, {"verdict": "passed"})  # нет day_started_at
    _event(db_engine, pid, _payload("not-a-date"))  # DataError в savepoint
    _event(db_engine, pid, _payload(dsa(started)))
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=2)
    assert _state(db_engine, pid).missed_streak == 0
    assert run_once(db_engine) == ProjectorResult(processed=0, skipped=0)  # checkpoint сдвинут
