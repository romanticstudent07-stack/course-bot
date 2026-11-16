"""0018_pauses: participant_pauses и pause_budgets, колоночные права, бэкфилл бюджета (db-pause-1).

Revision ID: 0018_pauses
Revises: 0017_support_questions
Create Date: 2026-11-16 12:00:00

Паузы по Р-6а / Р-20 (R-2026-11-15 А3): одна пауза на Этап, не дольше 7 дн.; не больше 14 дн.
за годовой цикл; между паузами ≥ 24 ч. Номера 0016 нет (решил ШТАБ, pause-2 §1).

participant_pauses — заявки и паузы участника: kind user / author / shadow; статус пишет только
проектор (бот и API пишут события). Частичные UNIQUE-индексы защищают в самой БД:
  - participant_pauses_one_active_uq — не больше одной активной паузы у pid;
  - participant_pauses_one_open_user_uq — не больше одной открытой (requested / approved)
    паузы участника; второй запрос с другим op → UniqueViolation (API отвечает 409);
  - participant_pauses_stage_taken_uq — пауза Этапа (stage_no, restart_no) тратится один раз;
    отменённая до старта в индекс не входит; restart_no открывает паузу того же Этапа без
    удаления истории.
ck_participant_pauses_user_max — 169 часов, а не 7 дней: граница паузы — 00:00 местного пояса,
при переводе часов 7 суток = 167–169 ч; interval '7 days' зависит от TimeZone сессии. Точные
7 местных суток проверяет код T2. В каждом CHECK NULL обработан явно.

pause_budgets — бюджет пауз на годовой цикл (I2 user_pause_quota): остаток дней, начало цикла
(00:00 по поясу в дату первой 04:00 первого дня), restart_no. Верхней границы остатка нет —
это конфиг потока. Счётчик пишет проектор.

Права и SQL, который их требует (раздел 7 карточки db-pause-1; код — T2–T4):

- app_api (T3) INSERT (pid, kind, status, start_at, planned_end_at, client_op_id) + SELECT всех
  колонок participant_pauses + USAGE participant_pauses_id_seq + SELECT pause_budgets:
      INSERT INTO participant_pauses (pid, kind, status, start_at, planned_end_at, client_op_id)
      VALUES (:pid, 'user', 'requested', :start, :end, :op)
      ON CONFLICT (pid, client_op_id) DO NOTHING RETURNING id
      SELECT * FROM participant_pauses WHERE pid = :pid ORDER BY id DESC
      SELECT days_budget_remaining_annual, cycle_start_at, restart_no FROM pause_budgets
      WHERE pid = :pid
- app_projector (T2) SELECT participant_pauses + UPDATE (status, stage_no, restart_no, ended_at);
  SELECT, INSERT pause_budgets + UPDATE (days_budget_remaining_annual, cycle_start_at, restart_no):
      UPDATE participant_pauses SET status = 'active', stage_no = :s, restart_no = :r
      WHERE id = :id AND status = 'approved'
      INSERT INTO pause_budgets (pid, days_budget_remaining_annual, cycle_start_at, restart_no)
      VALUES (:pid, :d, :c, :r) ON CONFLICT (pid) DO UPDATE SET
      days_budget_remaining_annual = EXCLUDED.days_budget_remaining_annual,
      cycle_start_at = EXCLUDED.cycle_start_at, restart_no = EXCLUDED.restart_no
- app_bot (T4, T6b, T7) — на таблицах прошлых миграций (FOREIGN_PRIVILEGES), без RETURNING:
  INSERT (pid, kind, payload, actor, actor_role) participant_events + USAGE
  participant_events_id_seq; INSERT (key, kind, result_ref) + SELECT (key, result_ref)
  idempotency_keys:
      INSERT INTO idempotency_keys (key, kind, result_ref) VALUES (:key, :kind, :ref)
      ON CONFLICT (key) DO NOTHING
      SELECT result_ref FROM idempotency_keys WHERE key = :key
      INSERT INTO participant_events (pid, kind, payload, actor, actor_role)
      VALUES (:pid, :kind, :payload, :actor, :role)
- app_api UPDATE на participant_pauses не получает; app_bot прав на participant_pauses и
  pause_budgets не получает; DELETE и TRUNCATE не выданы никому; ALTER DEFAULT PRIVILEGES
  и PUBLIC не используются. Все права выдаются одним циклом.

Бэкфилл (после выдачи прав): каждому pid без tombstone, у которого есть participant_state и
событие day_entered, — строка pause_budgets (14, cycle_start_at, 0). cycle_start_at =
day_clock.last_midnight(day_clock.active_from(at, tz), tz), at — первое day_entered по id;
пояс не из pg_timezone_names → Europe/Moscow (как day_clock.zone). Нет day_entered → строки
нет, её создаст проектор (T2). ON CONFLICT DO NOTHING — повтор не создаёт дублей.

Роли создаются, если их нет (как в 0017). downgrade: REVOKE прав на чужих таблицах в обратном
порядке (каждое право своей строкой), DROP трёх индексов, DROP TABLE pause_budgets и
participant_pauses (права на новые таблицы уходят вместе с ними); роли не удаляются.
access_grants, participant_state и status_flags не меняются; 0001–0017 не меняются.
Таблиц после миграции — 22.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_pauses"
down_revision: str | None = "0017_support_questions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PAUSES_TABLE = "participant_pauses"
BUDGETS_TABLE = "pause_budgets"
ROLES: tuple[str, ...] = ("app_api", "app_bot", "app_projector")

# (имя, условие); имена и условия — раздел 8 карточки db-pause-1; NULL обработан явно.
CHECKS_PAUSES: tuple[tuple[str, str], ...] = (
    (
        "ck_participant_pauses_kind",
        "kind IS NOT NULL AND kind IN ('user', 'author', 'shadow')",
    ),
    (
        "ck_participant_pauses_status",
        "status IS NOT NULL AND status IN "
        "('requested', 'approved', 'active', 'ended', 'cancelled', 'rejected')",
    ),
    (
        "ck_participant_pauses_period",
        "start_at IS NOT NULL AND planned_end_at IS NOT NULL AND planned_end_at > start_at",
    ),
    (
        "ck_participant_pauses_user_max",
        "kind IS NOT NULL AND start_at IS NOT NULL AND planned_end_at IS NOT NULL AND "
        "(kind <> 'user' OR planned_end_at <= start_at + interval '169 hours')",
    ),
    (
        "ck_participant_pauses_user_stage",
        "kind IS NOT NULL AND status IS NOT NULL AND "
        "(kind <> 'user' OR status NOT IN ('active', 'ended') "
        "OR (stage_no IS NOT NULL AND restart_no IS NOT NULL))",
    ),
    (
        "ck_participant_pauses_ended_at",
        "status IS NOT NULL AND (status <> 'ended' OR ended_at IS NOT NULL)",
    ),
    ("ck_participant_pauses_stage_no", "stage_no IS NULL OR stage_no >= 1"),
    ("ck_participant_pauses_restart_no", "restart_no IS NULL OR restart_no >= 0"),
    (
        "ck_participant_pauses_client_op_id",
        "client_op_id IS NOT NULL AND char_length(client_op_id) BETWEEN 1 AND 64",
    ),
)

CHECKS_BUDGETS: tuple[tuple[str, str], ...] = (
    (
        "ck_pause_budgets_days_remaining",
        "days_budget_remaining_annual IS NOT NULL AND days_budget_remaining_annual >= 0",
    ),
    ("ck_pause_budgets_restart_no", "restart_no IS NOT NULL AND restart_no >= 0"),
)

# (имя, колонки, условие) — частичные UNIQUE-индексы participant_pauses.
INDEXES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("participant_pauses_one_active_uq", ("pid",), "status = 'active'"),
    (
        "participant_pauses_one_open_user_uq",
        ("pid",),
        "kind = 'user' AND status IN ('requested', 'approved')",
    ),
    (
        "participant_pauses_stage_taken_uq",
        ("pid", "stage_no", "restart_no"),
        "kind = 'user' AND status IN ('active', 'ended')",
    ),
)

PP = (
    "id, pid, kind, status, start_at, planned_end_at, ended_at, stage_no, restart_no, "
    "client_op_id, created_at"
)
PB = "pid, days_budget_remaining_annual, cycle_start_at, restart_no"

# (право, объект, роль) на новых таблицах; одна строка — одно (колоночное) право.
PRIVILEGES: tuple[tuple[str, str, str], ...] = (
    (
        "INSERT (pid, kind, status, start_at, planned_end_at, client_op_id)",
        "TABLE participant_pauses",
        "app_api",
    ),
    (f"SELECT ({PP})", "TABLE participant_pauses", "app_api"),
    ("USAGE", "SEQUENCE participant_pauses_id_seq", "app_api"),
    (f"SELECT ({PB})", "TABLE pause_budgets", "app_api"),
    (f"SELECT ({PP})", "TABLE participant_pauses", "app_projector"),
    (
        "UPDATE (status, stage_no, restart_no, ended_at)",
        "TABLE participant_pauses",
        "app_projector",
    ),
    (f"SELECT ({PB})", "TABLE pause_budgets", "app_projector"),
    (f"INSERT ({PB})", "TABLE pause_budgets", "app_projector"),
    (
        "UPDATE (days_budget_remaining_annual, cycle_start_at, restart_no)",
        "TABLE pause_budgets",
        "app_projector",
    ),
)

# (право, объект, роль) на таблицах прошлых миграций; в downgrade — REVOKE в обратном порядке.
FOREIGN_PRIVILEGES: tuple[tuple[str, str, str], ...] = (
    ("INSERT (pid, kind, payload, actor, actor_role)", "TABLE participant_events", "app_bot"),
    ("USAGE", "SEQUENCE participant_events_id_seq", "app_bot"),
    ("INSERT (key, kind, result_ref)", "TABLE idempotency_keys", "app_bot"),
    ("SELECT (key, result_ref)", "TABLE idempotency_keys", "app_bot"),
)

# cycle_start_at = last_midnight(active_from(at, tz), tz); плохой пояс → Europe/Moscow.
BACKFILL = """
    WITH first_day AS (SELECT DISTINCT ON (pe.pid) pe.pid, pe.at FROM participant_events pe
                       WHERE pe.kind = 'day_entered' ORDER BY pe.pid, pe.id),
    src AS (SELECT fd.pid, fd.at,
                   CASE WHEN EXISTS (SELECT 1 FROM pg_timezone_names n WHERE n.name = ps.tz)
                        THEN ps.tz ELSE 'Europe/Moscow' END AS tz
            FROM first_day fd JOIN participant_state ps ON ps.pid = fd.pid
            JOIN tg_user_registry r ON r.pid = fd.pid WHERE r.tombstoned_at IS NULL),
    act AS (SELECT pid, tz, CASE WHEN CAST(at AT TIME ZONE tz AS time) <= time '04:00'
                                 THEN CAST(at AT TIME ZONE tz AS date)
                                 ELSE CAST(at AT TIME ZONE tz AS date) + 1 END AS d FROM src)
    INSERT INTO pause_budgets (pid, days_budget_remaining_annual, cycle_start_at, restart_no)
    SELECT pid, 14, CAST(d AS timestamp) AT TIME ZONE tz, 0 FROM act ON CONFLICT (pid) DO NOTHING
"""


def _create_role_if_missing(role: str) -> None:
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles "
        f"WHERE rolname = '{role}') "
        f"THEN CREATE ROLE {role}; "
        "END IF; END $$"
    )


def upgrade() -> None:
    op.create_table(
        PAUSES_TABLE,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("pid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("planned_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stage_no", sa.SmallInteger(), nullable=True),
        sa.Column("restart_no", sa.SmallInteger(), nullable=True),
        sa.Column("client_op_id", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="participant_pauses_pkey"),
        sa.ForeignKeyConstraint(
            ["pid"], ["tg_user_registry.pid"], name="participant_pauses_pid_fkey"
        ),
        sa.UniqueConstraint(
            "pid", "client_op_id", name="participant_pauses_pid_client_op_id_key"
        ),
        *(sa.CheckConstraint(condition, name=name) for name, condition in CHECKS_PAUSES),
    )
    for name, columns, where in INDEXES:
        op.create_index(
            name,
            PAUSES_TABLE,
            list(columns),
            unique=True,
            postgresql_where=sa.text(where),
        )
    op.create_table(
        BUDGETS_TABLE,
        sa.Column("pid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("days_budget_remaining_annual", sa.SmallInteger(), nullable=False),
        sa.Column("cycle_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "restart_no",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.PrimaryKeyConstraint("pid", name="pause_budgets_pkey"),
        sa.ForeignKeyConstraint(
            ["pid"], ["tg_user_registry.pid"], name="pause_budgets_pid_fkey"
        ),
        *(sa.CheckConstraint(condition, name=name) for name, condition in CHECKS_BUDGETS),
    )
    for role in ROLES:
        _create_role_if_missing(role)
    for privilege, target, role in (*PRIVILEGES, *FOREIGN_PRIVILEGES):
        op.execute(f"GRANT {privilege} ON {target} TO {role}")
    op.execute(BACKFILL)


def downgrade() -> None:
    # Сначала права на таблицах 0005 и 0007 — каждое своей строкой, колоночные тоже.
    for privilege, target, role in reversed(FOREIGN_PRIVILEGES):
        op.execute(f"REVOKE {privilege} ON {target} FROM {role}")
    for name, _columns, _where in reversed(INDEXES):
        op.drop_index(name, table_name=PAUSES_TABLE)
    op.drop_table(BUDGETS_TABLE)
    op.drop_table(PAUSES_TABLE)
