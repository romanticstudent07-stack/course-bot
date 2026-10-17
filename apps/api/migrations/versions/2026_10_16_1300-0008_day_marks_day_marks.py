"""0008_day_marks — таблица day_marks (отметки блоков дня) и права.

Revision ID: 0008_day_marks
Revises: 0007_day_state
Create Date: 2026-10-16 13:00:00

iter2-db-2 (В1 = Б, В6 = А, В8 = А, В10 = А).
Отметка «Выполнил / Не выполнил» по блоку дня до отправки отчёта: value = true — «Выполнил».
«День» отметки — day_started_at: метка конкретной выдачи дня (participant_state.day_started_at,
его пишет только проектор). Пишет app_api, читает app_projector.

Обнуление при перевыдаче дня (DM 3.7, В10 = А) — схемой, без DELETE: при перевыдаче
проектор пишет новый participant_state.day_started_at. Текущие отметки — это
WHERE pid = :pid AND day_started_at = <текущее значение>. Старые строки остаются историей
и в выборку больше не попадают. Отметка, записанная в момент перевыдачи со старым днём,
просто станет невидимой — вреда нет.

Права (кортеж «право, объект, роль»):
- app_api INSERT — новая отметка. UPDATE только колонок value и at — участник может
  передумать (ON CONFLICT DO UPDATE требует UPDATE на колонки из SET).
  pid, day_started_at и block_id менять нельзя.
- app_api SELECT — нужен для ON CONFLICT DO UPDATE (чтение колонок конфликта и EXCLUDED),
  для RETURNING и для показа текущих отметок. Это право выдано, другого не нужно.
- app_projector SELECT — для «пришёл» (DM 3.4) и шага лестницы «+1 ч после отметки»
  (DM 3.17). Писать проектор не может.
- DELETE и TRUNCATE не получает никто (В10). FK проверяет владелец таблицы.
  В8: в каноне ролей day_marks нет, права выданы прямо app_*.
- Последовательности нет — USAGE не нужен. Отдельный индекс не нужен: первичный ключ
  начинается с pid.
- FK без ON DELETE: стирание участника (erasure) позже должно учитывать day_marks —
  это задача erasure, не эта.

downgrade: REVOKE в обратном порядке (колоночное право — своей строкой: табличный REVOKE
его не снимает), затем DROP TABLE IF EXISTS day_marks. Безопасен, пока отметки никто
не пишет (до iter2-api-2); после этого откат — только из бэкапа.
"""
from __future__ import annotations

from alembic import op

revision = "0008_day_marks"
down_revision = "0007_day_state"
branch_labels = None
depends_on = None

CREATE_DAY_MARKS = """
CREATE TABLE day_marks (
    pid            uuid NOT NULL,
    day_started_at timestamptz NOT NULL,
    block_id       text NOT NULL,
    value          boolean NOT NULL,
    at             timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT day_marks_pkey PRIMARY KEY (pid, day_started_at, block_id),
    CONSTRAINT day_marks_pid_fkey FOREIGN KEY (pid) REFERENCES tg_user_registry (pid),
    CONSTRAINT ck_day_marks_block_id_not_empty CHECK (block_id <> '')
)
"""

PRIVILEGES: tuple[tuple[str, str, str], ...] = (
    ("SELECT, INSERT", "TABLE day_marks", "app_api"),
    ("UPDATE (value, at)", "TABLE day_marks", "app_api"),
    ("SELECT", "TABLE day_marks", "app_projector"),
)


def upgrade() -> None:
    op.execute(CREATE_DAY_MARKS)
    for privilege, target, role in PRIVILEGES:
        op.execute(f"GRANT {privilege} ON {target} TO {role}")


def downgrade() -> None:
    for privilege, target, role in reversed(PRIVILEGES):
        op.execute(f"REVOKE {privilege} ON {target} FROM {role}")
    op.execute("DROP TABLE IF EXISTS day_marks")
