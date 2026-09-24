"""Декларативная база SQLAlchemy. Её metadata — target_metadata в migrations/env.py."""
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
