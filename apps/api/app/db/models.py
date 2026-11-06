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

consent_events — журнал согласий C0–C6 (миграция 0004, B-2 / D-10):
  - колонки И1 R_378 [pid, kind, action, at, ip, ua, ver_of_text] + id, text_key,
    text_snapshot, created_via (docs/DEFECTS-FOUND.md, D-10);
  - append-only: пишет только first-launch (INSERT give); UPDATE/DELETE запретит B-3;
  - ip / ua в И1 не заполняются (NULL).

participant_events — журнал событий участника (миграция 0005, projector-1, D-16):
  - колонки I2 participant_state_contract.storage.event_log
    [id, pid, kind, payload, publish_epoch, at, actor, actor_role];
    индексы (pid, at), (kind, at); партиций pid_bucket в И1 нет (D-16);
  - append-only: first-launch пишет mini_app_first_consent только при создании pid,
    в той же транзакции, что pid и consent_events; бэкфилл 0005 — участникам с C1;
  - читает проектор (projector-2); UPDATE/DELETE запретит B-3a.

participant_state_checkpoints — чекпоинт проектора (миграция 0005, I2 checkpoint_table):
  - (pid, last_event_id, at); FK нет; пишет только проектор.

idempotency_keys — ключи идемпотентности (миграция 0007, iter2-db-1):
  - key text PK, kind, created_at, ttl interval (DEFAULT 1 hour), result_ref NULL,
    params_hash NULL; индекс idempotency_keys_created_at_idx (created_at);
    CHECK key <> '' и ttl > 0 — в миграции 0007;
  - ключи и kind дня — app/day_keys.py; срок ttl в логике не проверяется
    (строка есть → ключ есть); iter2-api-1 только читает.

day_marks — отметки блоков дня (миграция 0008, iter2-db-2):
  - PK (pid, day_started_at, block_id); FK pid → tg_user_registry;
  - отметки относятся к одному дню по day_started_at; iter2-api-1 только читает
    (GET /miniapp/v1/day/current), пишет — iter2-api-2.

access_grants — флажок доступа по промокоду (миграция 0010, db-access-1, Р-2):
  - PK tg_user_id (не pid: заявка идёт до онбординга); tg_user_registry не трогается;
  - status pending / granted / denied, deny_count, locked_until (пауза; NULL — нет паузы),
    admin_message_id — сообщение последней заявки в админ-теме (после решения не
    обнуляется), requested_at, decided_at, decided_by, created_via bot_promo / backfill_0010;
  - кодовое слово, имя и username НЕ хранятся (минимизация ПДн); updated_at пишет код;
  - CHECK (ck_access_grants_*) и частичный UNIQUE по admin_message_id — в миграции 0010;
  - app_bot: SELECT / INSERT / UPDATE по колонкам; app_api читает только (tg_user_id, status);
    DELETE нет ни у кого; backfill 0010 — granted активным строкам tg_user_registry.

reflections_log (0011, db-1) — неизменяемый лог рефлексий дней 6 / 13-M / 13-P (03 §3.12):
  - id bigint (reflections_log_id_seq), pid → tg_user_registry (reflections_log_pid_fkey),
    позиция дня stage_no / module_no / day_no, day_started_at (попытка дня, как в day_marks),
    body, created_at; индекс reflections_log_pid_day_idx — не уникальный;
  - каждая сдача и ревёрт — новая строка, действующая — последняя по created_at;
    UNIQUE и updated_at нет (повтор гасит idempotency_keys);
  - CHECK ck_reflections_log_position_positive и ck_reflections_log_body_len
    (после btrim не короче REFLECTION_MIN_LEN, всего не длиннее REFLECTION_MAX_LEN) —
    в миграции 0011; 422 REFLECTION_REQUIRED отдаёт API (api-refl-1), CHECK — страховка;
  - app_api: INSERT по 6 колонкам, SELECT, USAGE последовательности; app_bot: SELECT
    и SELECT (short_no) на tg_user_registry; UPDATE / DELETE / TRUNCATE нет ни у кого;
    app_projector прав нет.

measurements_log (0014, db-i3-2) — append-only журнал замеров: Чек-Ап и стартовый вес:
  - id bigint (measurements_log_id_seq), pid → tg_user_registry (measurements_log_pid_fkey),
    kind checkup / body, occasion onboarding / stage_end (stage_no — только у stage_end),
    checkup_answers (15 ответов 0–3), checkup_score, checkup_zone, checkup_config_version,
    weight_kg numeric(5,1), client_op_id, created_at; updated_at нет;
  - UNIQUE (pid, client_op_id) — повтор гасит ON CONFLICT DO NOTHING; индекс
    measurements_log_pid_kind_idx (pid, kind, created_at) — не уникальный;
  - CHECK ck_measurements_log_* — в миграции 0014: балл = сумма 15 ответов; связи
    балл↔зона нет (Р-7: границы зон в конфиге, их проверяет API); вес — от WEIGHT_MIN_KG
    до WEIGHT_MAX_KG; объёмы, город, ФИО, телефон, email не хранятся (Р-16, А1);
  - app_api: INSERT по 10 колонкам, SELECT, USAGE последовательности; app_bot: SELECT
    (pid, kind, occasion, checkup_zone, weight_kg, created_at) — без балла и ответов;
    UPDATE / DELETE / TRUNCATE нет ни у кого; app_projector прав нет.

participant_state (0001) здесь НЕ моделируется: единственный писатель — проектор
(E1/INV-1), колонка last_seen_publish_epoch — xid8 (SQLAlchemy его не знает).
CHECK lifecycle_phase (FSM I2, D-11 «6А») добавлен миграцией 0005.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, INET, INTERVAL, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

CREATED_VIA_MINI_APP_FIRST_LAUNCH = "mini_app_first_launch"

# Реестр согласий (miniapp-api-contract.yaml: Consent.id). Тот же список — в CHECK миграции 0004.
CONSENT_KINDS: tuple[str, ...] = ("C0", "C1", "C2", "C3", "C4", "C5", "C6")
CONSENT_ACTION_GIVE = "give"
CONSENT_ACTION_REVOKE = "revoke"

# participant_events (0005): I2 fsm_participant — pre_registered → onboarding,
# trigger mini_app_first_consent, actor system. Импортирует проектор (projector-2).
EVENT_KIND_MINI_APP_FIRST_CONSENT = "mini_app_first_consent"
ACTOR_SYSTEM = "system"

# access_grants (0010, Р-2). Тот же список — в CHECK миграции 0010.
ACCESS_STATUS_PENDING = "pending"
ACCESS_STATUS_GRANTED = "granted"
ACCESS_STATUS_DENIED = "denied"
ACCESS_STATUSES: tuple[str, ...] = (
    ACCESS_STATUS_PENDING,
    ACCESS_STATUS_GRANTED,
    ACCESS_STATUS_DENIED,
)
ACCESS_CREATED_VIA_BOT_PROMO = "bot_promo"
ACCESS_CREATED_VIA_BACKFILL = "backfill_0010"

# reflections_log (0011, db-1): длина текста рефлексии (для api-refl-1).
# Те же числа — в CHECK ck_reflections_log_body_len миграции 0011.
REFLECTION_MIN_LEN = 2
REFLECTION_MAX_LEN = 2000

# measurements_log (0014, db-i3-2): Чек-Ап и стартовый вес (для api-1, api-2, bot-1).
# Те же значения — в CHECK ck_measurements_log_* миграции 0014.
MEASUREMENT_KINDS: tuple[str, ...] = ("checkup", "body")
MEASUREMENT_OCCASIONS: tuple[str, ...] = ("onboarding", "stage_end")
CHECKUP_ZONES: tuple[str, ...] = ("green", "yellow", "red")
CHECKUP_ANSWERS_COUNT = 15
CHECKUP_ANSWER_MAX = 3
WEIGHT_MIN_KG = 30
WEIGHT_MAX_KG = 300


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


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


class ConsentEvent(Base):
    __tablename__ = "consent_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    pid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tg_user_registry.pid", name="consent_events_pid_fkey"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ip: Mapped[str | None] = mapped_column(INET)
    ua: Mapped[str | None] = mapped_column(Text)
    ver_of_text: Mapped[str] = mapped_column(Text, nullable=False)
    text_key: Mapped[str] = mapped_column(
        Text,
        ForeignKey("text_registry.key", name="consent_events_text_key_fkey"),
        nullable=False,
    )
    text_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    created_via: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint(_in_list("kind", CONSENT_KINDS), name="consent_events_kind_check"),
        CheckConstraint(
            _in_list("action", (CONSENT_ACTION_GIVE, CONSENT_ACTION_REVOKE)),
            name="consent_events_action_check",
        ),
        CheckConstraint(
            f"created_via IN ('{CREATED_VIA_MINI_APP_FIRST_LAUNCH}')",
            name="consent_events_created_via_check",
        ),
        Index("consent_events_pid_kind_at_idx", "pid", "kind", "at"),
    )


class ParticipantEvent(Base):
    __tablename__ = "participant_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    pid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tg_user_registry.pid", name="participant_events_pid_fkey"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    publish_epoch: Mapped[int | None] = mapped_column(BigInteger)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    actor_role: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("participant_events_pid_at_idx", "pid", "at"),
        Index("participant_events_kind_at_idx", "kind", "at"),
    )


class ParticipantStateCheckpoint(Base):
    __tablename__ = "participant_state_checkpoints"

    pid: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    last_event_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ttl: Mapped[timedelta] = mapped_column(
        INTERVAL, nullable=False, server_default=text("interval '1 hour'")
    )
    result_ref: Mapped[str | None] = mapped_column(Text)
    params_hash: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("key <> ''", name="ck_idempotency_keys_key_not_empty"),
        CheckConstraint("ttl > interval '0'", name="ck_idempotency_keys_ttl_positive"),
        Index("idempotency_keys_created_at_idx", "created_at"),
    )


class DayMark(Base):
    __tablename__ = "day_marks"

    pid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tg_user_registry.pid", name="day_marks_pid_fkey"),
        primary_key=True,
    )
    day_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )
    block_id: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[bool] = mapped_column(Boolean, nullable=False)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("block_id <> ''", name="ck_day_marks_block_id_not_empty"),
    )


class AccessGrant(Base):
    __tablename__ = "access_grants"

    tg_user_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    deny_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    admin_message_id: Mapped[int | None] = mapped_column(BigInteger)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[int | None] = mapped_column(BigInteger)
    created_via: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("tg_user_id > 0", name="ck_access_grants_tg_user_id_positive"),
        CheckConstraint(_in_list("status", ACCESS_STATUSES), name="ck_access_grants_status"),
        CheckConstraint("deny_count >= 0", name="ck_access_grants_deny_count_nonneg"),
        CheckConstraint(
            _in_list(
                "created_via", (ACCESS_CREATED_VIA_BOT_PROMO, ACCESS_CREATED_VIA_BACKFILL)
            ),
            name="ck_access_grants_created_via",
        ),
        CheckConstraint(
            f"status <> '{ACCESS_STATUS_PENDING}' OR admin_message_id IS NOT NULL",
            name="ck_access_grants_pending_msg",
        ),
        Index(
            "uq_access_grants_admin_message_id",
            "admin_message_id",
            unique=True,
            postgresql_where=text("admin_message_id IS NOT NULL"),
        ),
    )


class ReflectionLog(Base):
    __tablename__ = "reflections_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    pid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tg_user_registry.pid", name="reflections_log_pid_fkey"),
        nullable=False,
    )
    stage_no: Mapped[int] = mapped_column(Integer, nullable=False)
    module_no: Mapped[int] = mapped_column(Integer, nullable=False)
    day_no: Mapped[int] = mapped_column(Integer, nullable=False)
    day_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "stage_no > 0 AND module_no > 0 AND day_no > 0",
            name="ck_reflections_log_position_positive",
        ),
        CheckConstraint(
            f"char_length(btrim(body)) >= {REFLECTION_MIN_LEN} "
            f"AND char_length(body) <= {REFLECTION_MAX_LEN}",
            name="ck_reflections_log_body_len",
        ),
        Index(
            "reflections_log_pid_day_idx",
            "pid",
            "stage_no",
            "module_no",
            "day_no",
            "created_at",
        ),
    )


class MeasurementsLog(Base):
    __tablename__ = "measurements_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    pid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tg_user_registry.pid", name="measurements_log_pid_fkey"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    occasion: Mapped[str] = mapped_column(Text, nullable=False)
    stage_no: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    checkup_answers: Mapped[list[int] | None] = mapped_column(
        ARRAY(SmallInteger), nullable=True
    )
    checkup_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    checkup_zone: Mapped[str | None] = mapped_column(Text, nullable=True)
    checkup_config_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 1), nullable=True)
    client_op_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(_in_list("kind", MEASUREMENT_KINDS), name="ck_measurements_log_kind"),
        CheckConstraint(
            _in_list("occasion", MEASUREMENT_OCCASIONS), name="ck_measurements_log_occasion"
        ),
        CheckConstraint(
            "(occasion='onboarding' AND stage_no IS NULL) "
            "OR (occasion='stage_end' AND stage_no IS NOT NULL AND stage_no >= 1)",
            name="ck_measurements_log_stage",
        ),
        CheckConstraint(
            "kind <> 'checkup' OR (checkup_answers IS NOT NULL AND checkup_score IS NOT NULL "
            "AND checkup_zone IS NOT NULL AND checkup_config_version IS NOT NULL "
            "AND weight_kg IS NULL)",
            name="ck_measurements_log_kind_checkup",
        ),
        CheckConstraint(
            "kind <> 'body' OR (weight_kg IS NOT NULL AND checkup_answers IS NULL "
            "AND checkup_score IS NULL AND checkup_zone IS NULL "
            "AND checkup_config_version IS NULL)",
            name="ck_measurements_log_kind_body",
        ),
        CheckConstraint(
            "checkup_answers IS NULL OR (array_ndims(checkup_answers) = 1 "
            "AND array_lower(checkup_answers, 1) = 1 "
            f"AND cardinality(checkup_answers) = {CHECKUP_ANSWERS_COUNT} "
            "AND array_position(checkup_answers, NULL) IS NULL "
            f"AND 0 <= ALL (checkup_answers) AND {CHECKUP_ANSWER_MAX} >= ALL (checkup_answers))",
            name="ck_measurements_log_answers",
        ),
        CheckConstraint(
            "checkup_score IS NULL OR checkup_score = "
            + " + ".join(
                f"checkup_answers[{i}]" for i in range(1, CHECKUP_ANSWERS_COUNT + 1)
            ),
            name="ck_measurements_log_score_sum",
        ),
        CheckConstraint(
            "checkup_score IS NULL OR checkup_score BETWEEN 0 AND "
            f"{CHECKUP_ANSWERS_COUNT * CHECKUP_ANSWER_MAX}",
            name="ck_measurements_log_score_range",
        ),
        CheckConstraint(
            "checkup_zone IS NULL OR " + _in_list("checkup_zone", CHECKUP_ZONES),
            name="ck_measurements_log_zone",
        ),
        CheckConstraint(
            "checkup_config_version IS NULL "
            "OR char_length(btrim(checkup_config_version)) BETWEEN 1 AND 64",
            name="ck_measurements_log_config_version",
        ),
        CheckConstraint(
            f"weight_kg IS NULL OR weight_kg BETWEEN {WEIGHT_MIN_KG} AND {WEIGHT_MAX_KG}",
            name="ck_measurements_log_weight",
        ),
        CheckConstraint(
            "char_length(client_op_id) BETWEEN 1 AND 64",
            name="ck_measurements_log_client_op_id",
        ),
        UniqueConstraint(
            "pid", "client_op_id", name="measurements_log_pid_client_op_id_key"
        ),
        Index("measurements_log_pid_kind_idx", "pid", "kind", "created_at"),
    )
