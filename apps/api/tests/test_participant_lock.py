"""participant_lock (iter2-api-2a): замок participant:pid и active_pid_locked. С БД — только CI."""
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

import app.participant_lock as participant_lock
from app.participant_lock import LOCK_KEY_PREFIX, active_pid_locked, lock_participant

TRY_SQL = text("SELECT pg_try_advisory_xact_lock(hashtext('participant:' || CAST(:pid AS text)))")


def _participant(engine, tg_user_id: int) -> uuid.UUID:
    with engine.begin() as conn:
        return conn.execute(
            text(
                "INSERT INTO tg_user_registry (pid, tg_user_id, created_via, created_at) "
                "VALUES (gen_random_uuid(), :u, 'mini_app_first_launch', now()) RETURNING pid"
            ),
            {"u": tg_user_id},
        ).scalar_one()


def _tombstone(engine, pid) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE tg_user_registry SET tombstoned_at = now() WHERE pid = :p"), {"p": pid}
        )


def test_lock_key_prefix():
    assert LOCK_KEY_PREFIX == "participant:"


def test_second_session_cannot_take_lock(db_engine):
    pid = _participant(db_engine, 7001)
    holder = db_engine.connect()
    other = db_engine.connect()
    try:
        lock_participant(holder, pid)
        assert other.execute(TRY_SQL, {"pid": str(pid)}).scalar_one() is False
        other.rollback()
        holder.rollback()  # конец транзакции — замок снят
        assert other.execute(TRY_SQL, {"pid": str(pid)}).scalar_one() is True
        other.rollback()
    finally:
        holder.close()
        other.close()


def test_active_pid_locked_returns_pid(db_engine):
    pid = _participant(db_engine, 7002)
    with Session(db_engine) as session:
        assert active_pid_locked(session, 7002) == pid


def test_active_pid_locked_no_participant(db_engine):
    with Session(db_engine) as session:
        assert active_pid_locked(session, 7003) is None


def test_tombstoned_after_find_returns_none(db_engine, monkeypatch):
    pid = _participant(db_engine, 7004)
    # find увидел активную строку, а до замка её пометили tombstoned.
    monkeypatch.setattr(participant_lock, "find_active_participant", lambda s, u: (pid, 1))
    _tombstone(db_engine, pid)
    with Session(db_engine) as session:
        assert active_pid_locked(session, 7004) is None
