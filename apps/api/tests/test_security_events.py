"""pause-api-a1: record_security_event — отдельная транзакция, отказ без исключения и утечек.

Тесты с БД — только в CI (REQUIRE_DB_TESTS=1). db_engine security_events не очищает:
в каждом тесте новый pid uuid4 и фильтр по pid.
"""
import logging
import uuid

from sqlalchemy import create_engine, text

from app.security_events import CLIENT_OP_ID_CONFLICT, record_security_event
from tests.conftest import UNREACHABLE_DSN

ROW = text(
    "SELECT event_type, pid, op_kind, client_op_id, created_at "
    "FROM security_events WHERE pid = :p"
)
COUNT = text("SELECT count(*) FROM security_events WHERE pid = :p")


def _record(engine, pid: uuid.UUID, op: str = "op-conflict-1") -> bool:
    return record_security_event(
        engine,
        event_type=CLIENT_OP_ID_CONFLICT,
        pid=pid,
        op_kind="pause_start",
        client_op_id=op,
    )


def _count(db_engine, pid: uuid.UUID) -> int:
    with db_engine.connect() as conn:
        return conn.execute(COUNT, {"p": pid}).scalar_one()


def test_record_survives_outer_rollback(db_engine):
    pid = uuid.uuid4()
    with db_engine.connect() as outer:
        outer.begin()
        outer.execute(text("SELECT 1"))
        assert _record(db_engine, pid) is True
        outer.rollback()
    assert _count(db_engine, pid) == 1


def test_record_returns_true_and_row_fields(db_engine):
    pid = uuid.uuid4()
    assert _record(db_engine, pid, op="op-fields") is True
    with db_engine.connect() as conn:
        row = conn.execute(ROW, {"p": pid}).one()
    assert (row.event_type, row.pid, row.op_kind, row.client_op_id) == (
        CLIENT_OP_ID_CONFLICT,
        pid,
        "pause_start",
        "op-fields",
    )
    assert row.created_at is not None


def test_record_failure_no_raise(caplog):
    caplog.set_level(logging.ERROR, logger="app.security_events")
    pid = uuid.uuid4()
    engine = create_engine(UNREACHABLE_DSN)
    try:
        assert _record(engine, pid, op="op-secret-77") is False
    finally:
        engine.dispose()
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert any("security_event_write_failed" in r.getMessage() for r in errors)
    assert str(pid) not in caplog.text
    assert "pause_start" not in caplog.text
    assert "op-secret-77" not in caplog.text


def test_record_check_violation_returns_false(db_engine):
    pid = uuid.uuid4()
    assert _record(db_engine, pid, op="x" * 65) is False
    assert _count(db_engine, pid) == 0
