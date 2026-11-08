"""Проектор: kind tz_set (projector-i3-2, PROJECTOR_VERSION 4). С БД — только CI.

Номера — docs/tasks/projector-i3-2.md, раздел 9. tg_user_id 4101–4199 (решил ШТАБ, У9).
Тесты 1–2 — без БД (check.sh api), 3–7 — с БД.
"""
import json
import logging

from sqlalchemy import text

from app.projector import (
    EVENT_KIND_TZ_SET,
    PROJECTOR_VERSION,
    ProjectorResult,
    run_once,
    tz_from_payload,
)

DEFAULT_TZ = "Europe/Moscow"  # DEFAULT столбца tz (миграция 0007)
NEW_TZ = "Asia/Yekaterinburg"
POSITION = {"stage_no": 1, "module_no": 1, "day_no": 1, "source": "test_flag"}


def _participant(engine, tg_user_id: int):
    with engine.begin() as conn:
        return conn.execute(
            text(
                "INSERT INTO tg_user_registry (pid, tg_user_id, created_via, created_at) "
                "VALUES (gen_random_uuid(), :u, 'mini_app_first_launch', now()) RETURNING pid"
            ),
            {"u": tg_user_id},
        ).scalar_one()


def _event(engine, pid, kind: str, payload: dict):
    with engine.begin() as conn:
        return conn.execute(
            text(
                "INSERT INTO participant_events (pid, kind, payload, actor, actor_role) "
                "VALUES (:pid, :kind, CAST(:payload AS jsonb), 'system', 'system') "
                "RETURNING id, at"
            ),
            {"pid": pid, "kind": kind, "payload": json.dumps(payload)},
        ).one()


def _state(engine, pid):
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT lifecycle_phase, status_flags, tz, day_no, projector_version "
                "FROM participant_state WHERE pid = :p"
            ),
            {"p": pid},
        ).one()


def _checkpoint(engine, pid):
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT last_event_id FROM participant_state_checkpoints WHERE pid = :p"),
            {"p": pid},
        ).scalar_one_or_none()


def _onboarded(engine, tg_user_id: int):
    pid = _participant(engine, tg_user_id)
    _event(engine, pid, "mini_app_first_consent", {"schema_version": 1})
    assert run_once(engine) == ProjectorResult(processed=1, skipped=0)
    return pid


def _projector_warnings(caplog) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.name == "app.projector" and r.levelno == logging.WARNING
    ]


# 1. tz_from_payload: годные и битые значения (без БД).
def test_tz_from_payload():
    assert tz_from_payload({"tz": "Europe/Moscow"}) == "Europe/Moscow"
    assert tz_from_payload({"tz": "Asia/Yekaterinburg"}) == "Asia/Yekaterinburg"
    assert tz_from_payload(json.dumps({"tz": "Europe/Moscow"})) == "Europe/Moscow"
    assert tz_from_payload({"tz": "Europe/Moscow", "extra": 1}) == "Europe/Moscow"
    assert tz_from_payload({}) is None
    assert tz_from_payload({"tz": ""}) is None
    assert tz_from_payload({"tz": "A" * 65}) is None
    assert tz_from_payload({"tz": 123}) is None
    assert tz_from_payload({"tz": "Mars/Olympus"}) is None
    assert tz_from_payload({"tz": "../etc/passwd"}) is None
    assert tz_from_payload({"tz": "/etc/localtime"}) is None
    assert tz_from_payload({"tz": "Europe/Moscow "}) is None
    assert tz_from_payload("not json") is None


# 2. Версия и имя kind (без БД).
def test_version_and_kind():
    assert PROJECTOR_VERSION == 4
    assert EVENT_KIND_TZ_SET == "tz_set"


# 3. Онбординг + tz_set → tz записан, версия 4, фаза и флаги прежние.
def test_tz_set_before_first_day(db_engine):
    pid = _onboarded(db_engine, 4101)
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE participant_state SET status_flags = '{block_lives}' WHERE pid = :p"),
            {"p": pid},
        )
    event = _event(db_engine, pid, EVENT_KIND_TZ_SET, {"tz": NEW_TZ})
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    state = _state(db_engine, pid)
    assert state.tz == NEW_TZ
    assert state.projector_version == 4
    assert state.lifecycle_phase == "onboarding"
    assert list(state.status_flags) == ["block_lives"]
    assert state.day_no is None
    assert _checkpoint(db_engine, pid) == event.id


# 4. Два tz_set подряд до дня → действует последний.
def test_two_tz_set_last_wins(db_engine):
    pid = _onboarded(db_engine, 4102)
    _event(db_engine, pid, EVENT_KIND_TZ_SET, {"tz": NEW_TZ})
    _event(db_engine, pid, EVENT_KIND_TZ_SET, {"tz": "Asia/Vladivostok"})
    assert run_once(db_engine) == ProjectorResult(processed=2, skipped=0)
    assert _state(db_engine, pid).tz == "Asia/Vladivostok"


# 5. День начат → tz_set пропущен, tz прежний, checkpoint сдвинут; WARNING без pid и tz.
def test_tz_set_after_day_started_skipped(db_engine, caplog):
    pid = _onboarded(db_engine, 4103)
    _event(db_engine, pid, "day_entered", POSITION)
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=0)
    event = _event(db_engine, pid, EVENT_KIND_TZ_SET, {"tz": NEW_TZ})
    caplog.set_level(logging.WARNING, logger="app.projector")
    assert run_once(db_engine) == ProjectorResult(processed=0, skipped=1)
    state = _state(db_engine, pid)
    assert state.tz == DEFAULT_TZ
    assert state.day_no == 1
    assert _checkpoint(db_engine, pid) == event.id
    warnings = _projector_warnings(caplog)
    assert any(f"id={event.id}" in m and "kind=tz_set" in m for m in warnings)
    assert all(str(pid) not in m and NEW_TZ not in m for m in warnings)


# 6. Нет строки состояния → пропуск, строка не создана, checkpoint сдвинут.
def test_tz_set_without_state_skipped(db_engine):
    pid = _participant(db_engine, 4104)
    event = _event(db_engine, pid, EVENT_KIND_TZ_SET, {"tz": NEW_TZ})
    assert run_once(db_engine) == ProjectorResult(processed=0, skipped=1)
    with db_engine.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM participant_state WHERE pid = :p"), {"p": pid}
        ).scalar_one()
    assert count == 0
    assert _checkpoint(db_engine, pid) == event.id


# 7. Битый payload → пропуск; следующее событие в той же пачке применено.
def test_bad_payload_skipped_next_applied(db_engine, caplog):
    pid = _onboarded(db_engine, 4105)
    bad = _event(db_engine, pid, EVENT_KIND_TZ_SET, {"tz": "Mars/Olympus"})
    good = _event(db_engine, pid, EVENT_KIND_TZ_SET, {"tz": NEW_TZ})
    caplog.set_level(logging.WARNING, logger="app.projector")
    assert run_once(db_engine) == ProjectorResult(processed=1, skipped=1)
    assert _state(db_engine, pid).tz == NEW_TZ
    assert _checkpoint(db_engine, pid) == good.id
    warnings = _projector_warnings(caplog)
    assert any(f"id={bad.id}" in m and "kind=tz_set" in m and "bad payload" in m for m in warnings)
    assert all(str(pid) not in m and "Mars/Olympus" not in m for m in warnings)
