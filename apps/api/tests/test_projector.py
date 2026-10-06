"""projector-2: проектор participant_events → participant_state (тесты с БД — только CI).

Номера — docs/tasks/projector-2.md, раздел 9. Тест 5 — по уточнению ШТАБа: не через HTTP,
а через register_with_consents (та же функция, что вызывает first-launch); HTTP проверяется
живым запуском на сервере.
"""
from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy import text

import app.projector as projector
from app.config import Settings
from app.db.models import EVENT_KIND_MINI_APP_FIRST_CONSENT
from app.projector import ProjectorResult, run_once


def _participant(engine, tg_user_id: int) -> uuid.UUID:
    with engine.begin() as conn:
        return conn.execute(
            text(
                "INSERT INTO tg_user_registry (pid, tg_user_id, created_via, created_at) "
                "VALUES (gen_random_uuid(), :u, 'mini_app_first_launch', now()) RETURNING pid"
            ),
            {"u": tg_user_id},
        ).scalar_one()


def _event(
    engine,
    pid,
    kind: str = EVENT_KIND_MINI_APP_FIRST_CONSENT,
    payload: dict | None = None,
    actor: str = "system",
    event_id: int | None = None,
) -> int:
    params = {
        "pid": pid,
        "kind": kind,
        "payload": json.dumps(payload if payload is not None else {"schema_version": 1}),
        "actor": actor,
    }
    if event_id is None:
        sql = (
            "INSERT INTO participant_events (pid, kind, payload, actor, actor_role) "
            "VALUES (:pid, :kind, CAST(:payload AS jsonb), :actor, 'system') RETURNING id"
        )
    else:
        params["id"] = event_id
        sql = (
            "INSERT INTO participant_events (id, pid, kind, payload, actor, actor_role) "
            "VALUES (:id, :pid, :kind, CAST(:payload AS jsonb), :actor, 'system') RETURNING id"
        )
    with engine.begin() as conn:
        return conn.execute(text(sql), params).scalar_one()


def _state(engine, pid):
    with engine.connect() as conn:
        return (
            conn.execute(
                text(
                    "SELECT lifecycle_phase, status_flags, projector_version, updated_at "
                    "FROM participant_state WHERE pid = :p"
                ),
                {"p": pid},
            )
            .mappings()
            .one_or_none()
        )


def _checkpoint(engine, pid) -> int | None:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT last_event_id FROM participant_state_checkpoints WHERE pid = :p"),
            {"p": pid},
        ).scalar_one_or_none()


def _count(engine, sql: str) -> int:
    with engine.connect() as conn:
        return conn.execute(text(sql)).scalar_one()


# 1. mini_app_first_consent → onboarding, status_flags '{}', projector_version 1; checkpoint.
def test_first_consent_builds_onboarding(db_engine):
    pid = _participant(db_engine, 910001)
    event_id = _event(db_engine, pid)

    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)

    state = _state(db_engine, pid)
    assert state is not None
    assert state["lifecycle_phase"] == "onboarding"
    assert list(state["status_flags"]) == []
    assert state["projector_version"] == 1
    assert _checkpoint(db_engine, pid) == event_id


# 2. Повторный once → без изменений.
def test_second_pass_changes_nothing(db_engine):
    pid = _participant(db_engine, 910002)
    _event(db_engine, pid)
    run_once(db_engine)
    before = _state(db_engine, pid)

    assert run_once(db_engine) == ProjectorResult(processed=0, skipped=0)

    after = _state(db_engine, pid)
    assert after["updated_at"] == before["updated_at"]
    assert after["lifecycle_phase"] == "onboarding"


# 3. Неизвестный kind → пропуск, checkpoint сдвинут, строки нет; WARNING без payload и pid.
def test_unknown_kind_skipped_without_payload(db_engine, caplog):
    caplog.set_level(logging.WARNING, logger="app.projector")
    pid = _participant(db_engine, 910003)
    event_id = _event(
        db_engine, pid, kind="test_unknown_kind", payload={"marker": "secret-payload-1"}
    )

    assert run_once(db_engine) == ProjectorResult(processed=0, skipped=1)

    assert _state(db_engine, pid) is None
    assert _checkpoint(db_engine, pid) == event_id
    messages = [r.getMessage() for r in caplog.records if r.name == "app.projector"]
    assert any(
        f"id={event_id}" in m and "kind=test_unknown_kind" in m and "unknown kind" in m
        for m in messages
    )
    assert "secret-payload-1" not in caplog.text
    assert str(pid) not in caplog.text
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


# 4. Запрещённый переход: строка 'active' → событие → WARNING; фаза 'active'; checkpoint сдвинут.
def test_forbidden_transition_keeps_phase(db_engine, caplog):
    caplog.set_level(logging.WARNING, logger="app.projector")
    pid = _participant(db_engine, 910004)
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO participant_state (pid, lifecycle_phase, updated_at, projector_version) "
                "VALUES (:p, 'active', now(), 1)"
            ),
            {"p": pid},
        )
    event_id = _event(db_engine, pid)

    assert run_once(db_engine) == ProjectorResult(processed=0, skipped=1)

    assert _state(db_engine, pid)["lifecycle_phase"] == "active"
    assert _checkpoint(db_engine, pid) == event_id
    assert any(
        f"id={event_id}" in r.getMessage() and "transition not allowed" in r.getMessage()
        for r in caplog.records
        if r.name == "app.projector"
    )
    assert str(pid) not in caplog.text


# 5. Сквозной: регистрация той же функцией, что first-launch → run_once → onboarding.
def test_end_to_end_register_with_consents(db_engine):
    from sqlalchemy.orm import Session

    from app.routers.onboarding import register_with_consents

    with Session(db_engine) as session:
        registration = register_with_consents(session, 910005, ["C0", "C1"])
    assert registration.participant.created is True
    pid = uuid.UUID(str(registration.participant.pid))

    result = run_once(db_engine)

    assert result.processed == 1 and result.skipped == 0
    assert _state(db_engine, pid)["lifecycle_phase"] == "onboarding"


# 6. Бэкфилл: A — событие как от 0005, B — без события → CLI once → A onboarding, у B строки нет.
def test_backfill_event_via_cli_once(db_engine, migrated_db, monkeypatch, capsys):
    pid_a = _participant(db_engine, 910061)
    pid_b = _participant(db_engine, 910062)
    _event(
        db_engine,
        pid_a,
        payload={"schema_version": 1, "backfill": "0005"},
        actor="migration_0005",
    )
    monkeypatch.setattr(projector, "get_settings", lambda: Settings(database_url=migrated_db))

    assert projector.main(["once"]) == 0

    assert "projector once: обработано 1, пропущено 0" in capsys.readouterr().out
    assert _state(db_engine, pid_a)["lifecycle_phase"] == "onboarding"
    assert _state(db_engine, pid_b) is None


# 7. Пачка: 501 событие (501 участник) → processed 501; checkpoint каждого pid = id его события.
def test_batch_of_501(db_engine):
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tg_user_registry (pid, tg_user_id, created_via, created_at) "
                "SELECT gen_random_uuid(), 920000 + g, 'mini_app_first_launch', now() "
                "FROM generate_series(1, 501) AS g"
            )
        )
        conn.execute(
            text(
                "INSERT INTO participant_events (pid, kind, payload, actor, actor_role) "
                "SELECT pid, :kind, CAST(:payload AS jsonb), 'system', 'system' "
                "FROM tg_user_registry ORDER BY tg_user_id"
            ),
            {"kind": EVENT_KIND_MINI_APP_FIRST_CONSENT, "payload": '{"schema_version": 1}'},
        )

    assert run_once(db_engine) == ProjectorResult(processed=501, skipped=0)

    assert (
        _count(
            db_engine,
            "SELECT count(*) FROM participant_events e "
            "JOIN participant_state_checkpoints c ON c.pid = e.pid AND c.last_event_id = e.id",
        )
        == 501
    )
    assert (
        _count(
            db_engine,
            "SELECT count(*) FROM participant_state WHERE lifecycle_phase = 'onboarding'",
        )
        == 501
    )


# 10. Событие A с меньшим id закоммичено позже обработанного события B → не потеряно.
def test_lower_id_committed_later_not_lost(db_engine):
    pid_a = _participant(db_engine, 910101)
    pid_b = _participant(db_engine, 910102)
    _event(db_engine, pid_b, event_id=1000000002)
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    assert _checkpoint(db_engine, pid_b) == 1000000002

    _event(db_engine, pid_a, event_id=1000000001)

    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    assert _state(db_engine, pid_a)["lifecycle_phase"] == "onboarding"
    assert _checkpoint(db_engine, pid_a) == 1000000001
    assert _checkpoint(db_engine, pid_b) == 1000000002
