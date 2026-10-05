"""participant_events: журнал событий участника + бэкфилл (projector-1, D-16 / D-11)

Revision ID: 0005_participant_events
Revises: 0004_consent_events
Create Date: 2026-10-05 12:00:00

Источники (docs/architecture/**, read-only; выдержки — docs/tasks/projector-1.md, раздел 4):
  - I2 participant_state_contract.storage.event_log: table participant_events; append_only;
    columns [id, pid, kind, payload, publish_epoch, at, actor, actor_role];
    indexes [(pid, at), (kind, at)];
  - I2 checkpoint_table: participant_state_checkpoints (pid, last_event_id, at);
  - I2 fsm_participant: states [pre_registered, onboarding, active, sleeping, muted, erased];
    pre_registered → onboarding: {trigger: mini_app_first_consent, actor: system};
  - errata-unified E1: participant_state наполняет только проектор (INV-1).

Решения Автора: журнал participant_events — D-16; lifecycle_phase — FSM I2 (D-11, «6А»):
CHECK на participant_state.lifecycle_phase. Партиций pid_bucket в И1 нет (D-16).
Бэкфилл: каждому pid с consent_events (C1, give) без события — ОДНО событие
mini_app_first_consent (at = самый ранний give C1, actor migration_0005, actor_role system);
NOT EXISTS — повтор не создаёт дублей. consent_events и tg_user_registry только читаются;
participant_state миграция не пишет (строит проектор, projector-2).
Append-only: UPDATE/DELETE запретит GRANT в B-3a. 0001–0004 не меняются.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0005_participant_events"
down_revision: str | None = "0004_consent_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EVENTS_TABLE = "participant_events"
CHECKPOINTS_TABLE = "participant_state_checkpoints"
PHASE_CHECK = "participant_state_lifecycle_phase_check"

# I2 fsm_participant.states — тот же список, что в CHECK ниже (решение 6А, D-11).
LIFECYCLE_PHASES: tuple[str, ...] = (
    "pre_registered",
    "onboarding",
    "active",
    "sleeping",
    "muted",
    "erased",
)

DDL: tuple[str, ...] = (
    """
    CREATE TABLE participant_events (
        id            bigserial PRIMARY KEY,
        pid           uuid NOT NULL,
        kind          text NOT NULL,
        payload       jsonb NOT NULL,
        publish_epoch bigint,
        at            timestamptz NOT NULL DEFAULT now(),
        actor         text NOT NULL,
        actor_role    text NOT NULL,
        CONSTRAINT participant_events_pid_fkey
            FOREIGN KEY (pid) REFERENCES tg_user_registry (pid)
    )
    """,
    """
    CREATE INDEX participant_events_pid_at_idx ON participant_events (pid, at)
    """,
    """
    CREATE INDEX participant_events_kind_at_idx ON participant_events (kind, at)
    """,
    """
    CREATE TABLE participant_state_checkpoints (
        pid           uuid PRIMARY KEY,
        last_event_id bigint NOT NULL,
        at            timestamptz NOT NULL DEFAULT now()
    )
    """,
    f"""
    ALTER TABLE participant_state ADD CONSTRAINT {PHASE_CHECK}
        CHECK (lifecycle_phase IN ({", ".join(f"'{p}'" for p in LIFECYCLE_PHASES)}))
    """,
)

# Бэкфилл: только чтение consent_events; одно событие на pid; повтор — без дублей.
BACKFILL = """
    INSERT INTO participant_events (pid, kind, payload, at, actor, actor_role)
    SELECT ce.pid, 'mini_app_first_consent',
           CAST('{"schema_version": 1, "backfill": "0005"}' AS jsonb),
           min(ce.at), 'migration_0005', 'system'
    FROM consent_events ce
    WHERE ce.kind = 'C1' AND ce.action = 'give'
      AND NOT EXISTS (SELECT 1 FROM participant_events pe
                      WHERE pe.pid = ce.pid AND pe.kind = 'mini_app_first_consent')
    GROUP BY ce.pid
    ORDER BY min(ce.at), ce.pid
"""


def upgrade() -> None:
    for statement in DDL:
        op.execute(statement)
    op.execute(BACKFILL)


def downgrade() -> None:
    # События бэкфилла уходят вместе с таблицей; индексы и последовательность id — тоже.
    op.execute(f"ALTER TABLE participant_state DROP CONSTRAINT IF EXISTS {PHASE_CHECK}")
    op.execute(f"DROP TABLE IF EXISTS {CHECKPOINTS_TABLE}")
    op.execute(f"DROP TABLE IF EXISTS {EVENTS_TABLE}")
