"""consent_events: журнал согласий C0–C6 (Итерация 1e-1a, B-2 / D-10)

Revision ID: 0004_consent_events
Revises: 0003_text_registry
Create Date: 2026-10-01 12:00:00

Источники (docs/architecture/**, read-only; выдержки — docs/tasks/1e-1.md, раздел 4):
  - И1 R_378: consent_events: columns [pid, kind, action, at, ip, ua, ver_of_text]; append_only;
  - И1 D_14: явный чекбокс ПДн, лог (pid, ver_of_text, at, ip, ua);
  - ADD3 INV-AGE-GATE-BEFORE-PID: pid — только после hard-check 18+ и согласий;
  - miniapp-api-contract.yaml: Consent.id ∈ {C0…C6}.

Сверх R_378 (docs/DEFECTS-FOUND.md, D-10): id, text_key (FK text_registry),
text_snapshot (текст, который принял участник), created_via.
ip и ua в И1 не заполняются (NULL): за туннелем IP недостоверен.
Append-only: UPDATE/DELETE запретит GRANT в B-3 (D-13). 0001–0003 не меняются.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0004_consent_events"
down_revision: str | None = "0003_text_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "consent_events"

DDL: tuple[str, ...] = (
    """
    CREATE TABLE consent_events (
        id            bigserial PRIMARY KEY,
        pid           uuid NOT NULL,
        kind          text NOT NULL,
        action        text NOT NULL,
        at            timestamptz NOT NULL DEFAULT now(),
        ip            inet,
        ua            text,
        ver_of_text   text NOT NULL,
        text_key      text NOT NULL,
        text_snapshot text NOT NULL,
        created_via   text NOT NULL,
        CONSTRAINT consent_events_pid_fkey
            FOREIGN KEY (pid) REFERENCES tg_user_registry (pid),
        CONSTRAINT consent_events_text_key_fkey
            FOREIGN KEY (text_key) REFERENCES text_registry (key),
        CONSTRAINT consent_events_kind_check
            CHECK (kind IN ('C0', 'C1', 'C2', 'C3', 'C4', 'C5', 'C6')),
        CONSTRAINT consent_events_action_check
            CHECK (action IN ('give', 'revoke')),
        CONSTRAINT consent_events_created_via_check
            CHECK (created_via IN ('mini_app_first_launch'))
    )
    """,
    """
    CREATE INDEX consent_events_pid_kind_at_idx ON consent_events (pid, kind, at)
    """,
)


def upgrade() -> None:
    for statement in DDL:
        op.execute(statement)


def downgrade() -> None:
    # Индекс и последовательность id удаляются вместе с таблицей.
    op.execute(f"DROP TABLE IF EXISTS {TABLE}")
