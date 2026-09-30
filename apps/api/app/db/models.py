"""Модели SQLAlchemy.

Схему создают миграции Alembic (не create_all). Модели обязаны совпадать с живой
схемой после `alembic upgrade head` — это проверяет tests/test_db_models.py.

tg_user_registry — реестр tg_user_id ↔ pid (миграция 0002):
  - колонки: normative/I1-wave-a.md → tg_user_id_pid_registry
    [tg_user_id, pid, created_via, created_at, tombstoned_at];
  - short_no: 06-participant-card.md §6.3 («#000123», assigned_at: registration) —
    в колонках И1 его нет, см. docs/DEFECTS-FOUND.md D-12;
  - уникальность активной пары: один активный pid на tg_user_id; после tombstone
    тот же tg_user_id получает НОВЫЙ pid (И1 tombstone_semantics, Р243);
  - created_via: единственный канал — first-launch Mini App (SEAM-PATCH-1,
    И1 autocreate_source: mini_app_only).

text_registry — реестр текстов (миграция 0003, Б9 / Б14):
  - колонки — по config-schemas/text_registry.schema.json + registry_version, updated_at;
  - CHECK (шаблон ключа, tone, legal_status, длина текста) — в миграции 0003;
  - колонка text в модели — атрибут body (имя text занято функцией sqlalchemy.text).

participant_state (0001) здесь НЕ моделируется: единственный писатель — проектор
(E1/INV-1), модель появится вместе с ним (решение Автора, PR 1b+1c).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Identity,
    Index,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

CREATED_VIA_MINI_APP_FIRST_LAUNCH = "mini_app_first_launch"


class TgUserRegistry(Base):
    __tablename__ = "tg_user_registry"

    pid: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tg_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    short_no: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), nullable=False
    )
    created_via: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    tombstoned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("tg_user_id > 0", name="tg_user_registry_tg_user_id_positive"),
        CheckConstraint(
            f"created_via IN ('{CREATED_VIA_MINI_APP_FIRST_LAUNCH}')",
            name="tg_user_registry_created_via_check",
        ),
        UniqueConstraint("short_no", name="tg_user_registry_short_no_key"),
        Index(
            "tg_user_registry_active_tg_user_uidx",
            "tg_user_id",
            unique=True,
            postgresql_where=text("tombstoned_at IS NULL"),
        ),
    )


class TextRegistry(Base):
    __tablename__ = "text_registry"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    tone: Mapped[str] = mapped_column(Text, nullable=False)
    legal_status: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column("text", Text, nullable=False)
    plurals_ru: Mapped[dict[str, str] | None] = mapped_column(JSONB)
    notes: Mapped[str | None] = mapped_column(Text)
    registry_version: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
