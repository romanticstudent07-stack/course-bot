"""day_state: жизни, позиция дня и пояс в participant_state, idempotency_keys, права (iter2-db-1)

Revision ID: 0007_day_state
Revises: 0006_app_roles
Create Date: 2026-10-16 12:00:00

participant_state (пишет только проектор, E1 / INV-1) получает 7 колонок:
  - lives smallint NOT NULL DEFAULT 3, CHECK 0..3 — жизни на Этап (AL 2.2); 0 → sleeping (Р477);
  - stage_no, module_no, day_no smallint и day_started_at timestamptz — позиция дня
    (этап, модуль, день) и начало текущего дня. Либо все четыре NULL (участник ещё не начал
    день), либо все четыре заданы и номера >= 1. IS NOT NULL в CHECK написан явно: в CHECK
    результат NULL считается «пройдено» — без него «stage_no NULL, остальные заданы» прошло бы.
    Не упрощать;
  - missed_streak smallint NOT NULL DEFAULT 0, CHECK >= 0 — пропуски подряд (DM 3.6);
  - tz text NOT NULL DEFAULT 'Europe/Moscow', CHECK <> '' — пояс участника (В2 = А, DM 3.1, 3.21).
    Что это реальный IANA-пояс, проверяет код, а не CHECK.
Новые колонки имеют DEFAULT или NULL: текущий UPSERT проектора работает без правок.

idempotency_keys — по канону I2B [key, kind, created_at, ttl, result_ref, params_hash_optional];
params_hash здесь = params_hash_optional канона (NULL допустим). ttl по умолчанию 1 ч. FK нет.

Права (кортеж PRIVILEGES, как в 0006):
  - app_projector: INSERT participant_events + USAGE participant_events_id_seq — life_op по канону
    выполняет процесс проектора (В9 = А); bigserial берёт номер из последовательности;
    RETURNING id покрыт SELECT participant_events из 0006;
  - app_api: SELECT, INSERT idempotency_keys — отчёт дня пишет ключ в той же транзакции, что и
    событие; повтор с тем же ключом читает result_ref; SELECT нужен и для RETURNING;
  - app_projector: SELECT, INSERT idempotency_keys — ключ «life_op:{pid}:{client_op_id}»;
  - UPDATE, DELETE и TRUNCATE idempotency_keys не получает никто: result_ref пишется сразу при
    INSERT в той же транзакции; очистка по ttl — отдельная задача позже;
  - participant_state: новых GRANT нет (Н4). В 0001 права на participant_state выданы на ВСЮ
    таблицу, а не на колонки, поэтому новые колонки сразу доступны: app_projector — на запись
    (INSERT, UPDATE), app_api — только на чтение. SELECT FOR UPDATE у app_api невозможен (нет UPDATE).
pg_advisory_lock доступен через PUBLIC; замков (advisory lock) в миграции нет.

Соответствие ролям канона (В8 = А — права выданы прямо app_*):
  - app_projector = participant_state_projector + participant_state_reader (членство из 0006);
  - app_api = participant_state_reader (членство из 0006);
  - outbox_writer и outbox_relay — в 0009 (iter2-db-3);
  - idempotency_keys в каноне ролей нет, поэтому права выданы прямо app_*.
ALTER DEFAULT PRIVILEGES не используется.

downgrade: REVOKE в обратном порядке (пока таблица существует), DROP TABLE idempotency_keys,
снять 4 CHECK и 7 колонок participant_state. Колоночных прав в 0007 нет.
0001–0006 не меняются.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0007_day_state"
down_revision: str | None = "0006_app_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATE_TABLE = "participant_state"
KEYS_TABLE = "idempotency_keys"

NEW_COLUMNS: tuple[str, ...] = (
    "lives",
    "stage_no",
    "module_no",
    "day_no",
    "day_started_at",
    "missed_streak",
    "tz",
)

# (имя, условие) — CHECK на participant_state.
STATE_CHECKS: tuple[tuple[str, str], ...] = (
    ("ck_participant_state_lives_range", "lives BETWEEN 0 AND 3"),
    ("ck_participant_state_missed_streak_nonneg", "missed_streak >= 0"),
    ("ck_participant_state_tz_not_empty", "tz <> ''"),
    (
        "ck_participant_state_day_position",
        """
        (stage_no IS NULL AND module_no IS NULL AND day_no IS NULL AND day_started_at IS NULL)
        OR (stage_no IS NOT NULL AND module_no IS NOT NULL AND day_no IS NOT NULL
            AND day_started_at IS NOT NULL
            AND stage_no >= 1 AND module_no >= 1 AND day_no >= 1)
        """,
    ),
)

# (право, объект, роль) — GRANT в upgrade, REVOKE в обратном порядке в downgrade.
PRIVILEGES: tuple[tuple[str, str, str], ...] = (
    ("INSERT", "TABLE participant_events", "app_projector"),
    ("USAGE", "SEQUENCE participant_events_id_seq", "app_projector"),
    ("SELECT, INSERT", "TABLE idempotency_keys", "app_api"),
    ("SELECT, INSERT", "TABLE idempotency_keys", "app_projector"),
)


def upgrade() -> None:
    op.execute(
        f"""
        ALTER TABLE {STATE_TABLE}
            ADD COLUMN lives smallint NOT NULL DEFAULT 3,
            ADD COLUMN stage_no smallint,
            ADD COLUMN module_no smallint,
            ADD COLUMN day_no smallint,
            ADD COLUMN day_started_at timestamptz,
            ADD COLUMN missed_streak smallint NOT NULL DEFAULT 0,
            ADD COLUMN tz text NOT NULL DEFAULT 'Europe/Moscow'
        """
    )
    for name, condition in STATE_CHECKS:
        op.execute(f"ALTER TABLE {STATE_TABLE} ADD CONSTRAINT {name} CHECK ({condition})")
    op.execute(
        f"""
        CREATE TABLE {KEYS_TABLE} (
            key         text PRIMARY KEY,
            kind        text NOT NULL,
            created_at  timestamptz NOT NULL DEFAULT now(),
            ttl         interval NOT NULL DEFAULT interval '1 hour',
            result_ref  text,
            params_hash text,
            CONSTRAINT ck_idempotency_keys_key_not_empty CHECK (key <> ''),
            CONSTRAINT ck_idempotency_keys_ttl_positive CHECK (ttl > interval '0')
        )
        """
    )
    op.execute(f"CREATE INDEX idempotency_keys_created_at_idx ON {KEYS_TABLE} (created_at)")
    for privilege, target, role in PRIVILEGES:
        op.execute(f"GRANT {privilege} ON {target} TO {role}")


def downgrade() -> None:
    # Сначала права — пока таблица idempotency_keys существует. Колоночных прав в 0007 нет.
    for privilege, target, role in reversed(PRIVILEGES):
        op.execute(f"REVOKE {privilege} ON {target} FROM {role}")
    op.execute(f"DROP TABLE IF EXISTS {KEYS_TABLE}")
    for name, _condition in reversed(STATE_CHECKS):
        op.execute(f"ALTER TABLE {STATE_TABLE} DROP CONSTRAINT IF EXISTS {name}")
    drop_columns = ", ".join(f"DROP COLUMN IF EXISTS {column}" for column in NEW_COLUMNS)
    op.execute(f"ALTER TABLE {STATE_TABLE} {drop_columns}")
