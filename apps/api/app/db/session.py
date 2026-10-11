"""Engine и сессии SQLAlchemy (синхронно, psycopg 3).

DSN — только из настроек (.env), см. Settings.sqlalchemy_dsn(). Engine создаётся
лениво и кэшируется по DSN: импорт модуля к БД не подключается.
hide_parameters=True: параметры SQL не попадают в текст исключений и логи (D-18).
"""
from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from fastapi import Depends
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings

# Короткий таймаут подключения: при недоступной БД клиент быстро получает 503.
_CONNECT_TIMEOUT_SECONDS = 5


@lru_cache(maxsize=4)
def _engine_for(dsn: str) -> Engine:
    return create_engine(
        dsn,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        connect_args={"connect_timeout": _CONNECT_TIMEOUT_SECONDS},
        hide_parameters=True,
    )


def get_engine(settings: Settings) -> Engine:
    return _engine_for(settings.sqlalchemy_dsn())


def get_db_session(settings: Settings = Depends(get_settings)) -> Iterator[Session]:
    """FastAPI-зависимость. Соединение берётся из пула только при первом запросе к БД.

    Любое исключение в обработчике — явный rollback, затем исключение идёт дальше (D-15 г).
    """
    factory = sessionmaker(bind=get_engine(settings), expire_on_commit=False)
    session = factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
