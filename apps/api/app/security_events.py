"""Долговечная запись событий безопасности (pause-api-a1, R-2026-11-21).

record_security_event пишет в СВОЁМ соединении из пула и своей транзакции (engine.begin()),
а не в сессии запроса: откат транзакции запроса перед 409 запись не стирает.
Без RETURNING и SELECT — у app_api нет SELECT на security_events.
Отказ записи не выходит наружу: в лог только имя класса исключения (как session.py, D-18);
pid, op_kind, client_op_id, initData, токены и tg_user_id в лог не попадают.
Решение, писать ли событие (доказанная коллизия op-id), принимает вызывающий код (A2).
"""
import logging
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger("app.security_events")

CLIENT_OP_ID_CONFLICT = "client_op_id_conflict"

INSERT_SQL = text(
    "INSERT INTO security_events (event_type, pid, op_kind, client_op_id) "
    "VALUES (:event_type, :pid, :op_kind, :client_op_id)"
)


def record_security_event(
    engine: Engine,
    *,
    event_type: str,
    pid: uuid.UUID,
    op_kind: str,
    client_op_id: str,
) -> bool:
    """Записать событие отдельной транзакцией. Успех — True, любой отказ — False."""
    params = {
        "event_type": event_type,
        "pid": pid,
        "op_kind": op_kind,
        "client_op_id": client_op_id,
    }
    try:
        with engine.begin() as conn:
            conn.execute(INSERT_SQL, params)
    except Exception as exc:
        logger.error("security_event_write_failed (%s)", type(exc).__name__)
        return False
    return True
