"""participant_events (projector-1, D-16 / D-11). Нужен DATABASE_URL (только CI).

1-2: шаг 5 first-launch (register_with_consents — та же функция, что вызывает обработчик)
     пишет ровно одно событие mini_app_first_consent при создании pid; повтор — без дублей.
3:   CHECK lifecycle_phase на participant_state (FSM I2, 6А). SQL прямо в тесте:
     статический тест E1 (projector-2) смотрит только apps/api/app/**.
4:   бэкфилл 0005: pid с C1 give — одно событие (at = give C1), без C1 — ничего; повтор без дублей.
"""
from __future__ import annotations

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import ACTOR_SYSTEM, EVENT_KIND_MINI_APP_FIRST_CONSENT
from app.routers.onboarding import register_with_consents
from tests.conftest import _alembic_config, count_consent_rows

TG_USER_NEW = 2101
TG_USER_A = 2201
TG_USER_B = 2202

_EVENTS_SQL = text(
    "SELECT kind, payload, actor, actor_role, at FROM participant_events "
    "WHERE pid = :p ORDER BY id"
)


def _events(engine, pid):
    with engine.connect() as conn:
        return conn.execute(_EVENTS_SQL, {"p": pid}).all()


def _first_launch_step5(engine, tg_user_id: int):
    with Session(engine) as session:
        return register_with_consents(session, tg_user_id, ["C0", "C1"])


def test_first_launch_writes_one_event(db_engine):
    registration = _first_launch_step5(db_engine, TG_USER_NEW)
    assert registration.participant.created is True
    pid = registration.participant.pid

    events = _events(db_engine, pid)
    assert len(events) == 1
    event = events[0]
    assert event.kind == EVENT_KIND_MINI_APP_FIRST_CONSENT == "mini_app_first_consent"
    assert event.payload == {"schema_version": 1}
    assert event.actor == ACTOR_SYSTEM == "system"
    assert event.actor_role == "system"
    assert count_consent_rows(db_engine, pid) == 2  # запись согласий не изменилась


def test_repeat_first_launch_no_duplicate_event(db_engine):
    first = _first_launch_step5(db_engine, TG_USER_NEW)
    second = _first_launch_step5(db_engine, TG_USER_NEW)
    assert second.participant.created is False
    assert second.participant.pid == first.participant.pid
    assert len(_events(db_engine, first.participant.pid)) == 1
    assert count_consent_rows(db_engine, first.participant.pid) == 2


_INSERT_STATE_SQL = text(
    "INSERT INTO participant_state (pid, lifecycle_phase, updated_at, projector_version) "
    "VALUES (gen_random_uuid(), :phase, now(), 1)"
)


def test_lifecycle_phase_check(db_engine):
    with pytest.raises(IntegrityError):
        with db_engine.begin() as conn:
            conn.execute(_INSERT_STATE_SQL, {"phase": "banned_soft"})
    with db_engine.begin() as conn:
        conn.execute(_INSERT_STATE_SQL, {"phase": "onboarding"})
    with db_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM participant_state")).scalar_one() == 1


_INSERT_PARTICIPANT_SQL = text(
    "INSERT INTO tg_user_registry (pid, tg_user_id, created_via, created_at) "
    "VALUES (gen_random_uuid(), :u, 'mini_app_first_launch', now()) RETURNING pid"
)
_INSERT_CONSENT_SQL = text(
    "INSERT INTO consent_events (pid, kind, action, ver_of_text, text_key, text_snapshot, "
    "created_via) VALUES (:p, :k, 'give', '0.1.0', :key, 'snapshot', 'mini_app_first_launch')"
)


def _assert_backfilled(engine, pid_a, pid_b, c1_at) -> None:
    events_a = _events(engine, pid_a)
    assert len(events_a) == 1
    assert events_a[0].kind == "mini_app_first_consent"
    assert events_a[0].payload == {"schema_version": 1, "backfill": "0005"}
    assert events_a[0].actor == "migration_0005"
    assert events_a[0].actor_role == "system"
    assert events_a[0].at == c1_at
    assert _events(engine, pid_b) == []


def test_backfill_0005(db_engine):
    cfg = _alembic_config()
    try:
        command.downgrade(cfg, "0004_consent_events")
        with db_engine.begin() as conn:
            pid_a = conn.execute(_INSERT_PARTICIPANT_SQL, {"u": TG_USER_A}).scalar_one()
            pid_b = conn.execute(_INSERT_PARTICIPANT_SQL, {"u": TG_USER_B}).scalar_one()
            for kind, key in (
                ("C0", "legal.consent_c0_age_18_plus"),
                ("C1", "legal.consent_c1_pdn"),
            ):
                conn.execute(_INSERT_CONSENT_SQL, {"p": pid_a, "k": kind, "key": key})
            c1_at = conn.execute(
                text("SELECT at FROM consent_events WHERE pid = :p AND kind = 'C1'"),
                {"p": pid_a},
            ).scalar_one()

        command.upgrade(cfg, "0005_participant_events")
        _assert_backfilled(db_engine, pid_a, pid_b, c1_at)

        command.downgrade(cfg, "0004_consent_events")
        command.upgrade(cfg, "head")
        _assert_backfilled(db_engine, pid_a, pid_b, c1_at)
    finally:
        command.upgrade(cfg, "head")
