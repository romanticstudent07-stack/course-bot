"""Проектор participant_state: participant_events → participant_state (E1 / INV-1, projector-2, life-ops-a).

Запуск: python -m app.projector run | once
  - run  — постоянный цикл: проход раз в 1 с, пачки до 500 событий; advisory lock держится
           на отдельном соединении всё время работы (второй экземпляр ждёт);
  - once — один проход: lock → проход → unlock;
           печатает «projector once: обработано K, пропущено S».
           На сервере рядом с run не запускать (infra/SERVER-IRONCLAD.md:146) — проверка по логам.

Источники (docs/architecture/**, read-only; выдержки — docs/tasks/projector-2.md, раздел 4,
docs/tasks/iter2-api-2a.md, раздел 8, и docs/tasks/iter2-api-2b.md, раздел 8):
  - errata-unified E1: participant_state — обычная таблица, наполняемая проектором; API туда
    не пишет никогда (INV-1). SQL записи в participant_state — только в этом модуле
    (проверяет tests/test_projector_static.py);
  - I2 fsm_participant: pre_registered → onboarding по mini_app_first_consent (6А, D-11);
  - I2 checkpoint_table: participant_state_checkpoints (pid, last_event_id, at).

Виды событий (PROJECTOR_VERSION 8, api-pause-1a; выдержки — docs/tasks/life-ops-a.md, раздел 7,
docs/tasks/projector-i3-2.md, разделы 3–4 и 7, docs/tasks/api-sleep-1a.md, раздел 4, и
docs/tasks/api-sleep-1b.md, разделы 4 и 7, docs/tasks/api-revive-1.md, разделы 4 и 7,
docs/tasks/api-pause-1a.md, разделы 2, 4 и 5):
  - mini_app_first_consent — строка состояния, фаза onboarding (без изменений с версии 1);
  - day_entered (iter2-api-2a) — позиция stage_no / module_no / day_no из payload,
    day_started_at = at события, missed_streak = 0; только если позиции ещё нет
    (WHERE day_no IS NULL). 0 строк (позиция уже есть или строки нет) → WARNING, пропуск.
    lifecycle_phase, status_flags и author_pause_reason не трогаются (В21).
    v8 (api-pause-1a, Р12): в том же SAVEPOINT — строка pause_budgets, если её нет
    (INSERT … ON CONFLICT (pid) DO NOTHING): остаток 14, cycle_start_at =
    day_clock.last_midnight(day_clock.active_from(at, tz), tz) — формула бэкфилла 0018,
    restart_no 0; tz — RETURNING в SQL позиции;
    Граница: каждое из stage_no, module_no, day_no — целое от 1 до MAX_POSITION_VALUE
    (32767, предел smallint); вне границы, не целое или bool → «bad payload», пропуск;
  - day_report_submitted (iter2-api-2b, В18) — missed_streak = 0 при ЛЮБОМ вердикте, только
    если day_started_at строки совпадает с payload.day_started_at (текущий день, ревью #95).
    0 строк (старый день или строки нет) → WARNING, пропуск. Нет строки day_started_at
    в payload → «bad payload»; строка не разбирается как timestamptz → DataError в savepoint →
    «bad payload». Без ON CONFLICT; lifecycle_phase, status_flags и lives не упоминаются (Ш1).
    v3 (life-ops-a): если в payload есть все четыре поля next_stage_no, next_module_no,
    next_day_no, next_day_started_at — позиция = next_*, day_started_at = next_day_started_at,
    missed_streak = 0 (условие то же: текущий day_started_at = payload.day_started_at).
    Ни одного поля → поведение v2 (старый payload #103 — только счётчик). Часть полей,
    позиция вне [1, MAX_POSITION_VALUE] или битая строка → WARNING «bad payload», пропуск;
  - life_op — две ветки по payload.reason (v5, api-sleep-1a); прочие reason → «bad payload».
    Общее (Р3, pause-2 §4, Р-20): lives + delta = 0 → флаг block_lives (без дубля) и
    lifecycle_phase = 'sleeping'. Фаза пересчитывается только в UPDATE, меняющем флаги.
    (а) reason "missed_days" (life-ops-c, В31) — payload {day_started_at, delta, reason}:
    lives = lives + delta. Условие — day_started_at совпадает, фаза onboarding или active
    (В29; muted / sleeping / erased не трогаются, ревью #111, Н2) и 0 ≤ lives + delta ≤ 3.
    0 строк → WARNING, пропуск. Payload: только delta == −1 (int, не bool), иначе
    «bad payload» (Н3). После UPDATE в том же SAVEPOINT — строка журнала life_writeoffs
    (0019): pid события, event_id = id события, позиция из RETURNING; ON CONFLICT (event_id)
    DO NOTHING. Позиции нет (NULL) → WARNING «life_writeoffs skipped, no position», строки
    нет, жизнь списана. IntegrityError на INSERT откатывает весь life_op (Ш6, риск принят).
    (б) reason "author_cmd" (/life, ШТАБ 16.11 Ш1) — payload {delta, reason}: delta int
    (не bool), ≠ 0, |delta| ≤ MAX_LIVES; day_started_at не читается. lives = lives + delta;
    позиция, day_started_at и missed_streak не трогаются (03 §3.6). Условие — фаза onboarding
    или active, 0 ≤ lives + delta ≤ 3, прибавка только при lives > 0 и без block_lives
    (оттуда — revive, Р-20). 0 строк → WARNING с причиной (no state, phase not allowed,
    lives_zero_use_revive, life_above_max, life_below_zero). В журнал не пишет;
  - day_closed (life-ops-c, В31) — payload {day_started_at, outcome came|silent, missed_streak,
    next_day_started_at}: day_started_at = next_day_started_at, missed_streak из payload;
    позиция не меняется. Условие — day_started_at совпадает и next_day_started_at строго
    позже него (Н5: равные → пропуск, иначе повтор применился бы снова). 0 строк → WARNING,
    пропуск;
  - tz_set (projector-i3-2, Р-16: город → только tz IANA) — payload {tz}: participant_state.tz =
    tz, только если первый день ещё не начат (WHERE day_no IS NULL). 04 yaml «timezone:
    applies_next_day», 14 §14.11 — смена пояса со следующего дня; до первого дня «следующего
    дня» нет → пояс сразу; смена пояса на курсе — отдельная задача. 0 строк (день начат или
    строки нет) → WARNING «tz_set: day started or no state», пропуск. tz — строка длиной
    1–MAX_TZ_LEN (64), шаблон _TZ_RE (П-4: проверка до ZoneInfo, ZoneInfo открывает файл
    по имени), ZoneInfo(tz) без исключения; иначе «bad payload». Набор поясов анкеты сверяет
    API, не проектор. Фаза, флаги и позиция не упоминаются; tz в лог не идёт.
  - restart_paid (v6, api-sleep-1b, Р-20: рестарт по промокоду из block_lives) — payload должен
    быть dict (grant_id не читается), at обязателен; иначе «bad payload». Применяется, только
    если строка есть, в status_flags есть block_lives и stage_no не NULL; иначе пропуск
    («no state» / «restart: not blocked or no position»). lives = 3, block_lives снимается,
    фаза — phase_for_flags (Р2); затем reissue_day(текущий stage, 1, 1) и бюджет пауз
    (Р-6а): pause_budgets UPSERT — остаток PAUSE_BUDGET_DAYS (14), cycle_start_at = D,
    restart_no + 1 (SQL дословно из docstring 0018; права app_projector — 0018).
    author_pause_reason, muted и erased не трогаются. Всё — в SAVEPOINT события.
  - revive_by_author (v7, api-revive-1, Р-20: revive из block_lives) — payload {target:
    {stage_no, module_no, day_no}, lives_returned}: поля target — int (не bool) ≥ 1,
    lives_returned — int (не bool) ≥ 0, лишние ключи игнорируются; at обязателен; иначе
    «bad payload». lives_returned берётся из payload — его считает бот (bot-revive-1, Ш1 = А);
    проектор life_writeoffs не читает и не пересчитывает. Применяется, только если строка есть,
    есть block_lives и stage_no не NULL («no state» / «revive: not blocked or no position»),
    target.stage_no = stage_no («revive: other stage») и (module, day) target не впереди
    текущих («revive: target ahead»; равенство допустимо). lives = min(MAX_LIVES,
    1 + lives_returned), block_lives снимается, фаза — phase_for_flags (Р2); затем
    reissue_day(target). Роль события не проверяется (как у restart_paid). pause_budgets,
    day_marks, отчёты, рефлексии, life_writeoffs не трогаются. Всё — в SAVEPOINT события.
  - паузы участника (v8, api-pause-1a, Р-6а / Р-20; правила — app/pause_rules.py). Payload:
    pause_id — int (не bool) ≥ 1; reason — строка из списка; иначе «bad payload». Строка
    participant_pauses ищется по (id, pid, kind 'user'); статус меняет только UPDATE … WHERE
    id, pid, kind 'user' и ожидаемый статус (права 0018). Нет строки или не тот статус →
    WARNING, пропуск. Переходы:
      pause_approved {pause_id}: requested → approved; at ≥ start_at → cancelled (Р14);
      pause_rejected {pause_id}: requested → rejected;
      pause_cancel {pause_id}: requested | approved → cancelled;
      pause_start_failed {pause_id, reason ∈ pause_rules.REFUSAL_REASONS}: requested |
        approved → cancelled;
      pause_started {pause_id}: approved → active. Бюджет — pause_budgets (нет строки → создать
        тем же SQL, что в day_entered, по первому day_entered), roll_cycle по at (Р9);
        N = pause_rules.pause_days (плохой период → пропуск); start_refusal (Р15) → cancelled,
        WARNING «pause_started отклонён: <reason>», флага нет. Иначе: остаток −= N (UPDATE …
        WHERE остаток ≥ N), stage_no = Этап позиции, restart_no из pause_budgets, флаг
        pause_user, фаза phase_for_flags (Р4). Повтор — статус уже active → пропуск;
      pause_ended {pause_id, reason expired | by_participant}: active → ended, ended_at = at;
        pause_user снимается, фаза phase_for_flags; D: expired — last_midnight(at, tz)
        (at < planned_end_at → пропуск, Р5), by_participant — next_midnight(at, tz) (Р6);
        reissue_day(текущая позиция, day_start = D) (Р7); возврат by_participant —
        pause_rules.refund_days, только если start_at ≥ cycle_start_at после roll_cycle по at,
        остаток не выше 14 (Р8).
    Всё — в SAVEPOINT события. Уведомлений (outbox) нет.
  reissue_day(conn, pid, target, at, tz, day_start=None) — внутренняя функция, не событие и не
  day_entered: позиция = target, missed_streak 0, day_started_at = D = day_start или
  day_clock.next_midnight(at, tz) (Ш2: D из at события, не из payload; day_start — паузы v8).
  До 04:00 даты D окно not_active.
  Порядок в life-ops-c: life_op раньше day_closed (меньший id) — оба видят старый
  day_started_at. Защита от повтора (ревью #111, Н4) — ТОЛЬКО для пары life_op + day_closed:
  после day_closed day_started_at уже другой, и повтор обоих пропускается. Сам по себе
  life_op повторно применяется: два life_op одного дня без day_closed между ними —
  оба (−2 жизни); проектор это не ловит. Поэтому писатель (life-ops-c) обязан писать
  life_op, day_closed и ключ day_close:{pid}:{dsa} в ОДНОЙ транзакции под замком
  participant:pid — тогда ни одно из трёх не появится без остальных.

«Часы» в run_forever (once — без них): life_ops.tick (закрытие дня; день рефлексии 6 / 13 без
отчёта — −1 жизнь сразу, clocks-1) и notify_ops.tick (pushi-notify-1, НП3 «Задания откроются …
в 04:00» — ключ tasks_open и outbox; НП1 noon_nudge (T3, noon-1); лестница ladder_reminder (T2,
ladder-1) + алерт Автору ladder_day2_alert (clocks-1) — ключи и outbox, без participant_state).

Бэкфилл block_lives (v5): run_once — после lock до прохода; run_forever — сразу после
«lock acquired», до цикла. Один UPDATE: sleeping, lives = 0, без block_lives → флаг
block_lives. Лог INFO — только число строк.

Курсор — по pid: события e с e.id > coalesce(c.last_event_id, 0) через LEFT JOIN
participant_state_checkpoints c USING (pid), ORDER BY e.id, LIMIT 500. Глобальный
max(last_event_id) не используется: коммиты разных pid идут не по порядку id.
Порядок внутри одного pid держится: писатели событий существующего pid берут замок
participant:pid (participant_lock.py) до INSERT и держат до commit; first-launch пишет
событие только для pid, созданного тем же вызовом (Ш2, iter2-api-2a).

Пачка — одна транзакция. Неизвестный kind, запрещённый переход или битый payload → WARNING
(id и kind события, без payload и pid), событие пропускается, checkpoint сдвигается.
Каждое событие применяется внутри SAVEPOINT (conn.begin_nested(), ревью #101):
DataError или IntegrityError → откат только этого savepoint, WARNING «bad payload» с id,
kind и именем класса ошибки (без payload и pid), пропуск, checkpoint pid сдвигается на id
события — одно битое событие не останавливает проектор. Другие SQLAlchemyError — откат
всей пачки, как раньше.
participant_events только читается; at и payload читаются для day_entered, restart_paid,
revive_by_author и видов пауз;
payload — для day_report_submitted, life_op, day_closed и tz_set; в лог не идут.
participant_pauses (0018) — SELECT и UPDATE (status, stage_no, restart_no, ended_at), INSERT нет.
pause_budgets (0018) — SELECT, INSERT в day_entered и pause_started (ON CONFLICT DO NOTHING),
UPDATE (остаток, cycle_start_at) в паузах, UPSERT в restart_paid.
author_pause_reason и last_seen_publish_epoch не трогаются.
DSN проектора — Settings.projector_dsn(): PROJECTOR_DATABASE_URL → DATABASE_URL → POSTGRES_*
(B-3a-2; роль app_projector — миграция 0006). DSN не логируется.
Битый DSN или нет драйвера диалекта (B-3c, api-melochi): WARNING только с именем класса
ошибки (ArgumentError, ValueError, ModuleNotFoundError), код выхода 1, цикл не стартует.
"""
from __future__ import annotations

import json
import logging
import re
import signal
import sys
import time
import uuid
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import DataError, IntegrityError, SQLAlchemyError

from app import day_clock, life_ops, notify_ops, pause_ops, pause_rules
from app.config import get_settings
from app.db.models import EVENT_KIND_MINI_APP_FIRST_CONSENT
from app.db.session import get_engine

logger = logging.getLogger("app.projector")

BATCH_SIZE = 500
POLL_SECONDS = 1.0
RETRY_SECONDS = 5.0
PROJECTOR_VERSION = 8
# «Часы» пауз (api-pause-1b, Ч1): тот же интервал, что у life_ops.LIFE_OPS_INTERVAL_S.
PAUSE_OPS_INTERVAL_S = life_ops.LIFE_OPS_INTERVAL_S
PHASE_PRE_REGISTERED = "pre_registered"
PHASE_ONBOARDING = "onboarding"
# Пишет POST /miniapp/v1/day/test-enter (app/routers/day.py) под замком participant:pid.
EVENT_KIND_DAY_ENTERED = "day_entered"
# Пишет POST /miniapp/v1/day/report/submit (app/routers/day.py) под замком participant:pid.
EVENT_KIND_DAY_REPORT_SUBMITTED = "day_report_submitted"
# Пишет life-ops-c (закрытие дня) под замком participant:pid; раньше day_closed того же дня.
EVENT_KIND_LIFE_OP = "life_op"
# Пишет life-ops-c (закрытие дня) под замком participant:pid.
EVENT_KIND_DAY_CLOSED = "day_closed"
# Пояс из анкеты (projector-i3-2, Р-16); писатель — API анкеты (api-i3-2, после этой задачи).
EVENT_KIND_TZ_SET = "tz_set"
# Рестарт по промокоду из block_lives (api-sleep-1b, Р-20); писатель — бот (T6b, позже).
EVENT_KIND_RESTART_PAID = "restart_paid"
# revive из block_lives (api-revive-1, Р-20); писатель — бот (bot-revive-1, позже).
EVENT_KIND_REVIVE_BY_AUTHOR = "revive_by_author"
# Паузы участника (api-pause-1a, раздел 5): бот — approved / rejected, API — cancel и
# ended by_participant, часы T2b — started, start_failed и ended expired.
EVENT_KIND_PAUSE_APPROVED = "pause_approved"
EVENT_KIND_PAUSE_REJECTED = "pause_rejected"
EVENT_KIND_PAUSE_CANCEL = "pause_cancel"
EVENT_KIND_PAUSE_START_FAILED = "pause_start_failed"
EVENT_KIND_PAUSE_STARTED = "pause_started"
EVENT_KIND_PAUSE_ENDED = "pause_ended"
PAUSE_END_EXPIRED = "expired"
PAUSE_END_BY_PARTICIPANT = "by_participant"
PAUSE_END_REASONS = (PAUSE_END_EXPIRED, PAUSE_END_BY_PARTICIPANT)
FLAG_PAUSE_USER = "pause_user"
PHASE_SLEEPING = "sleeping"
DAY_CLOSED_OUTCOMES = ("came", "silent")
# life_op: единственные допустимые delta и reason (life-ops-a §7, ревью #111, Н3).
LIFE_OP_DELTAS = (-1,)
LIFE_OP_REASON = "missed_days"
# life_op от команды /life (api-sleep-1a, ШТАБ 16.11 Ш1): ±N без дня.
LIFE_OP_REASON_AUTHOR = "author_cmd"
FLAG_BLOCK_LIVES = "block_lives"
# Флаги сна (канон I2 через pause-2 §4); freeze_unpaid — не фаза.
SLEEP_FLAGS = ("pause_user", "author_pause", "pause_shadow", "block_lives", "ban_mod")
# Фазы, которые флаги сна не меняют.
_PHASES_KEEP = ("muted", "erased")
PHASE_ACTIVE = "active"
_LIFE_OP_PHASES = (PHASE_ONBOARDING, PHASE_ACTIVE)
# Граница lives (CHECK ck_participant_state_lives_range, миграция 0007).
MAX_LIVES = 3
# Рестарт (Р-20): 3 жизни; бюджет пауз за годовой цикл (Р-6а).
RESTART_LIVES = MAX_LIVES
PAUSE_BUDGET_DAYS = 14
# Верхняя граница stage_no / module_no / day_no (smallint).
MAX_POSITION_VALUE = 32767
# Граница длины tz (projector-i3-2, Ш-1).
MAX_TZ_LEN = 64
# Шаблон имени пояса до ZoneInfo (projector-i3-2, П-4): ZoneInfo открывает файл по имени.
_TZ_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_+-]*(/[A-Za-z0-9_+-]+){0,2}$")
USAGE = "usage: python -m app.projector run | once"

_LOCK = text("SELECT pg_advisory_lock(hashtext('participant_state_projector'))")
_UNLOCK = text("SELECT pg_advisory_unlock(hashtext('participant_state_projector'))")
_PING = text("SELECT 1")

# at и payload нужны для day_entered и day_report_submitted; в лог не попадают (только id и kind).
_SELECT_BATCH = text(
    """
    SELECT e.id, e.pid, e.kind, e.at, e.payload
    FROM participant_events e
    LEFT JOIN participant_state_checkpoints c USING (pid)
    WHERE e.id > coalesce(c.last_event_id, 0)
    ORDER BY e.id
    LIMIT :limit
    """
)

# Переход разрешён только из «нет строки» или pre_registered; иначе RETURNING пуст.
_UPSERT_STATE = text(
    """
    INSERT INTO participant_state
        (pid, lifecycle_phase, status_flags, updated_at, projector_version)
    VALUES (:pid, :phase, CAST('{}' AS text[]), now(), :version)
    ON CONFLICT (pid) DO UPDATE
        SET lifecycle_phase = EXCLUDED.lifecycle_phase,
            status_flags = EXCLUDED.status_flags,
            updated_at = EXCLUDED.updated_at,
            projector_version = EXCLUDED.projector_version
        WHERE participant_state.lifecycle_phase = :from_phase
    RETURNING pid
    """
)

# day_entered: позиция только если её ещё нет. Без ON CONFLICT; фаза и флаги не упоминаются.
_SET_POSITION = text(
    """
    UPDATE participant_state
    SET stage_no = :stage_no,
        module_no = :module_no,
        day_no = :day_no,
        day_started_at = :at,
        missed_streak = 0,
        updated_at = now(),
        projector_version = :version
    WHERE pid = :pid AND day_no IS NULL
    RETURNING pid, tz
    """
)

# day_report_submitted: только текущий день (совпадение day_started_at). Без ON CONFLICT;
# фаза, флаги и жизни не упоминаются (Ш1, В18).
_RESET_MISSED_STREAK = text(
    """
    UPDATE participant_state
    SET missed_streak = 0,
        updated_at = now(),
        projector_version = :version
    WHERE pid = :pid AND day_started_at = CAST(:day_started_at AS timestamptz)
    RETURNING pid
    """
)

# day_report_submitted v3: переход на следующий день. Фаза, флаги и жизни не упоминаются.
_ADVANCE_DAY = text(
    """
    UPDATE participant_state
    SET stage_no = :stage_no,
        module_no = :module_no,
        day_no = :day_no,
        day_started_at = CAST(:next_day_started_at AS timestamptz),
        missed_streak = 0,
        updated_at = now(),
        projector_version = :version
    WHERE pid = :pid AND day_started_at = CAST(:day_started_at AS timestamptz)
    RETURNING pid
    """
)

# life_op missed_days: жизни ± delta только для текущего дня, фазы onboarding / active
# (В29, Н2) и в границах [0, MAX_LIVES]; 0 жизней → block_lives (без дубля) и sleeping
# (Р477, Р3). RETURNING позиции — для журнала life_writeoffs (Р5).
_APPLY_LIFE_OP = text(
    """
    UPDATE participant_state
    SET lives = lives + :delta,
        status_flags = CASE
            WHEN lives + :delta = 0
                 AND NOT ('block_lives' = ANY(coalesce(status_flags, CAST('{}' AS text[]))))
            THEN array_append(coalesce(status_flags, CAST('{}' AS text[])), 'block_lives')
            ELSE status_flags END,
        lifecycle_phase = CASE WHEN lives + :delta = 0 THEN CAST(:sleeping AS text)
                               ELSE lifecycle_phase END,
        updated_at = now(),
        projector_version = :version
    WHERE pid = :pid
      AND day_started_at = CAST(:day_started_at AS timestamptz)
      AND lifecycle_phase IN ('onboarding', 'active')
      AND lives + :delta BETWEEN 0 AND :max_lives
    RETURNING pid, stage_no, module_no, day_no
    """
)

# life_op author_cmd (/life): ±N без дня; позиция, day_started_at, missed_streak
# не упоминаются (03 §3.6). Прибавка — только при lives > 0 и без block_lives (Р-20).
_APPLY_AUTHOR_LIFE_OP = text(
    """
    UPDATE participant_state
    SET lives = lives + :delta,
        status_flags = CASE
            WHEN lives + :delta = 0
                 AND NOT ('block_lives' = ANY(coalesce(status_flags, CAST('{}' AS text[]))))
            THEN array_append(coalesce(status_flags, CAST('{}' AS text[])), 'block_lives')
            ELSE status_flags END,
        lifecycle_phase = CASE WHEN lives + :delta = 0 THEN CAST(:sleeping AS text)
                               ELSE lifecycle_phase END,
        updated_at = now(),
        projector_version = :version
    WHERE pid = :pid
      AND lifecycle_phase IN ('onboarding', 'active')
      AND lives + :delta BETWEEN 0 AND :max_lives
      AND (:delta < 0
           OR (lives > 0
               AND NOT ('block_lives' = ANY(coalesce(status_flags, CAST('{}' AS text[]))))))
    RETURNING pid
    """
)

# Причина пропуска author_cmd (0 строк UPDATE).
_SELECT_LIFE_STATE = text(
    """
    SELECT lives, status_flags, lifecycle_phase
    FROM participant_state
    WHERE pid = :pid
    """
)

# Журнал списаний (0019): дословно по docstring миграции, без RETURNING.
_INSERT_LIFE_WRITEOFF = text(
    """
    INSERT INTO life_writeoffs (pid, event_id, stage_no, module_no, day_no)
    VALUES (:pid, :event_id, :s, :m, :d) ON CONFLICT (event_id) DO NOTHING
    """
)

# Бэкфилл block_lives (Р3): строки sleeping с 0 жизней без флага.
_BACKFILL_BLOCK_LIVES = text(
    """
    UPDATE participant_state
    SET status_flags = array_append(coalesce(status_flags, CAST('{}' AS text[])), 'block_lives'),
        updated_at = now(),
        projector_version = :version
    WHERE lifecycle_phase = 'sleeping'
      AND lives = 0
      AND NOT ('block_lives' = ANY(coalesce(status_flags, CAST('{}' AS text[]))))
    """
)

# day_closed: следующий день по часам, счётчик из payload; позиция, фаза и жизни не упоминаются.
# Следующий день строго позже текущего (Н5).
_CLOSE_DAY = text(
    """
    UPDATE participant_state
    SET day_started_at = CAST(:next_day_started_at AS timestamptz),
        missed_streak = :missed_streak,
        updated_at = now(),
        projector_version = :version
    WHERE pid = :pid AND day_started_at = CAST(:day_started_at AS timestamptz)
      AND CAST(:next_day_started_at AS timestamptz) > day_started_at
    RETURNING pid
    """
)

# tz_set: пояс только до первого дня (projector-i3-2, Ш-1). Без ON CONFLICT;
# фаза, флаги, позиция и жизни не упоминаются.
_SET_TZ = text(
    """
    UPDATE participant_state
    SET tz = :tz,
        updated_at = now(),
        projector_version = :version
    WHERE pid = :pid AND day_no IS NULL
    RETURNING pid
    """
)

# restart_paid: снять block_lives, 3 жизни, фаза по Р2. Позиция — в reissue_day.
_APPLY_RESTART = text(
    """
    UPDATE participant_state
    SET lives = :lives,
        status_flags = CAST(:flags AS text[]),
        lifecycle_phase = :phase,
        updated_at = now(),
        projector_version = :version
    WHERE pid = :pid
      AND 'block_lives' = ANY(coalesce(status_flags, CAST('{}' AS text[])))
      AND stage_no IS NOT NULL
    RETURNING pid
    """
)

_SELECT_RESTART_STATE = text(
    """
    SELECT lifecycle_phase, status_flags, stage_no, tz
    FROM participant_state
    WHERE pid = :pid
    """
)

# reissue_day: перевыдача дня с D (00:00 по поясу). Фаза, флаги, жизни и
# author_pause_reason не упоминаются.
_REISSUE_DAY = text(
    """
    UPDATE participant_state
    SET stage_no = :stage_no,
        module_no = :module_no,
        day_no = :day_no,
        day_started_at = :started,
        missed_streak = 0,
        updated_at = now(),
        projector_version = :version
    WHERE pid = :pid
    RETURNING pid
    """
)

# revive_by_author: снять block_lives, lives из payload, фаза по Р2. Позиция — в reissue_day.
_APPLY_REVIVE = text(
    """
    UPDATE participant_state
    SET lives = :lives,
        status_flags = CAST(:flags AS text[]),
        lifecycle_phase = :phase,
        updated_at = now(),
        projector_version = :version
    WHERE pid = :pid
      AND 'block_lives' = ANY(coalesce(status_flags, CAST('{}' AS text[])))
      AND stage_no = :s
    RETURNING pid
    """
)

_SELECT_REVIVE_STATE = text(
    """
    SELECT lifecycle_phase, status_flags, stage_no, module_no, day_no, tz
    FROM participant_state
    WHERE pid = :pid
    """
)

_SELECT_RESTART_NO = text("SELECT restart_no FROM pause_budgets WHERE pid = :pid")

# Бюджет пауз (0018): дословно по docstring миграции.
_UPSERT_PAUSE_BUDGET = text(
    """
    INSERT INTO pause_budgets (pid, days_budget_remaining_annual, cycle_start_at, restart_no)
    VALUES (:pid, :d, :c, :r) ON CONFLICT (pid) DO UPDATE SET
    days_budget_remaining_annual = EXCLUDED.days_budget_remaining_annual,
    cycle_start_at = EXCLUDED.cycle_start_at, restart_no = EXCLUDED.restart_no
    """
)

# Строка бюджета пауз (Р12): остаток 14, restart_no 0 — как бэкфилл 0018; повтор не меняет.
_INSERT_PAUSE_BUDGET = text(
    """
    INSERT INTO pause_budgets (pid, days_budget_remaining_annual, cycle_start_at, restart_no)
    VALUES (:pid, :d, :c, 0) ON CONFLICT (pid) DO NOTHING
    """
)

_SELECT_PAUSE_BUDGET = text(
    """
    SELECT days_budget_remaining_annual, cycle_start_at, restart_no
    FROM pause_budgets
    WHERE pid = :pid
    """
)

# Ленивая смена цикла (Р9) и возврат (Р8): остаток и начало цикла.
_UPDATE_PAUSE_BUDGET = text(
    """
    UPDATE pause_budgets
    SET days_budget_remaining_annual = :d, cycle_start_at = :c
    WHERE pid = :pid
    """
)

# Списание N при старте паузы (Р8): только если остатка хватает.
_CHARGE_PAUSE_BUDGET = text(
    """
    UPDATE pause_budgets
    SET days_budget_remaining_annual = days_budget_remaining_annual - :n
    WHERE pid = :pid AND days_budget_remaining_annual >= :n
    RETURNING pid
    """
)

_SELECT_FIRST_DAY_ENTERED = text(
    """
    SELECT at FROM participant_events
    WHERE pid = :pid AND kind = 'day_entered'
    ORDER BY id
    LIMIT 1
    """
)

# Строка паузы участника (Р1): только kind 'user'.
_SELECT_PAUSE = text(
    """
    SELECT status, start_at, planned_end_at
    FROM participant_pauses
    WHERE id = :id AND pid = :pid AND kind = 'user'
    """
)

_SET_PAUSE_STATUS = text(
    """
    UPDATE participant_pauses
    SET status = :to
    WHERE id = :id AND pid = :pid AND kind = 'user' AND status = :from
    RETURNING id
    """
)

_START_PAUSE = text(
    """
    UPDATE participant_pauses
    SET status = 'active', stage_no = :s, restart_no = :r
    WHERE id = :id AND pid = :pid AND kind = 'user' AND status = 'approved'
    RETURNING id
    """
)

_END_PAUSE = text(
    """
    UPDATE participant_pauses
    SET status = 'ended', ended_at = :at
    WHERE id = :id AND pid = :pid AND kind = 'user' AND status = 'active'
    RETURNING id
    """
)

# Пауза Этапа уже взята (Р10): active или ended с тем же (stage_no, restart_no).
_SELECT_STAGE_TAKEN = text(
    """
    SELECT EXISTS (
        SELECT 1 FROM participant_pauses
        WHERE pid = :pid AND kind = 'user' AND status IN ('active', 'ended')
          AND stage_no = :s AND restart_no = :r
    )
    """
)

_SELECT_LAST_PAUSE_END = text(
    """
    SELECT max(ended_at) FROM participant_pauses
    WHERE pid = :pid AND kind = 'user' AND status = 'ended'
    """
)

_SELECT_PAUSE_STATE = text(
    """
    SELECT lifecycle_phase, status_flags, stage_no, module_no, day_no, tz
    FROM participant_state
    WHERE pid = :pid
    """
)

# Флаг pause_user и фаза по Р2/Р4. Позиция — в reissue_day.
_SET_PAUSE_FLAGS = text(
    """
    UPDATE participant_state
    SET status_flags = CAST(:flags AS text[]),
        lifecycle_phase = :phase,
        updated_at = now(),
        projector_version = :version
    WHERE pid = :pid
    RETURNING pid
    """
)

_UPSERT_CHECKPOINT = text(
    """
    INSERT INTO participant_state_checkpoints (pid, last_event_id, at)
    VALUES (:pid, :last_event_id, now())
    ON CONFLICT (pid) DO UPDATE
        SET last_event_id = GREATEST(participant_state_checkpoints.last_event_id,
                                     EXCLUDED.last_event_id),
            at = EXCLUDED.at
    """
)

_POSITION_FIELDS = ("stage_no", "module_no", "day_no")
_NEXT_POSITION_FIELDS = ("next_stage_no", "next_module_no", "next_day_no")
_NEXT_FIELDS = (*_NEXT_POSITION_FIELDS, "next_day_started_at")
# Отметка «нет полей v3» — отличается от None («bad payload»).
_NO_NEXT = object()


@dataclass(frozen=True)
class ProjectorResult:
    processed: int
    skipped: int


def _skip(event_id: int, kind: str, reason: str) -> None:
    logger.warning("projector: skip event id=%s kind=%s (%s)", event_id, kind, reason)


def _payload_dict(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            return None
    if not isinstance(payload, dict):
        return None
    return payload


def _int_value(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _str_value(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return value


def position_from_payload(
    payload: Any, fields: tuple[str, str, str] = _POSITION_FIELDS
) -> tuple[int, int, int] | None:
    """(stage_no, module_no, day_no) из payload day_entered или None (битый payload).

    Каждое значение — int (не bool) от 1 до MAX_POSITION_VALUE включительно.
    fields — имена полей (для day_report_submitted v3 — next_*).
    """
    data = _payload_dict(payload)
    if data is None:
        return None
    values: list[int] = []
    for field in fields:
        value = data.get(field)
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        if value < 1 or value > MAX_POSITION_VALUE:
            return None
        values.append(value)
    return values[0], values[1], values[2]


def report_day_started_at(payload: Any) -> str | None:
    """payload.day_started_at (строка dsa) из day_report_submitted или None (битый payload).

    Разбор строки как timestamptz — в SQL (CAST): ошибка → DataError в savepoint.
    """
    data = _payload_dict(payload)
    if data is None:
        return None
    return _str_value(data.get("day_started_at"))


def report_next_day(payload: Any) -> tuple[int, int, int, str] | object | None:
    """Поля v3 day_report_submitted: (stage, module, day, next_day_started_at) или _NO_NEXT.

    Ни одного из четырёх полей → _NO_NEXT (поведение v2); часть полей или битое значение →
    None («bad payload»). Разбор next_day_started_at как timestamptz — в SQL (DataError).
    """
    data = _payload_dict(payload)
    if data is None:
        return None
    present = [field in data for field in _NEXT_FIELDS]
    if not any(present):
        return _NO_NEXT
    if not all(present):
        return None
    position = position_from_payload(data, _NEXT_POSITION_FIELDS)
    next_started = _str_value(data.get("next_day_started_at"))
    if position is None or next_started is None:
        return None
    return (*position, next_started)


def life_op_from_payload(payload: Any) -> tuple[str, int] | None:
    """(day_started_at, delta) из payload life_op или None (битый payload).

    delta — только из LIFE_OP_DELTAS (int, не bool), reason == LIFE_OP_REASON.
    """
    data = _payload_dict(payload)
    if data is None:
        return None
    started = _str_value(data.get("day_started_at"))
    delta = _int_value(data.get("delta"))
    if started is None or delta is None or delta not in LIFE_OP_DELTAS:
        return None
    if data.get("reason") != LIFE_OP_REASON:
        return None
    return started, delta


def author_life_op_from_payload(payload: Any) -> int | None:
    """delta из payload life_op author_cmd (/life) или None (битый payload).

    delta — int (не bool), ≠ 0, |delta| ≤ MAX_LIVES; day_started_at не нужен и не читается.
    reason проверяет вызывающий.
    """
    data = _payload_dict(payload)
    if data is None:
        return None
    delta = _int_value(data.get("delta"))
    if delta is None or delta == 0 or abs(delta) > MAX_LIVES:
        return None
    return delta


def classify_life_op(lives: int, delta: int, flags: Sequence[str] | None) -> str | None:
    """Причина отказа life_op author_cmd или None (чистая функция, без pid)."""
    flag_list = list(flags or ())
    if delta > 0 and (lives == 0 or FLAG_BLOCK_LIVES in flag_list):
        return "lives_zero_use_revive"
    if lives + delta > MAX_LIVES:
        return "life_above_max"
    if lives + delta < 0:
        return "life_below_zero"
    return None


def phase_for_flags(phase: str, flags: Sequence[str] | None) -> str:
    """Фаза по флагам сна (Р2): muted / erased — без изменений; флаг сна → sleeping;
    sleeping без флагов сна → active; иначе прежняя. onboarding → active не делает.
    """
    if phase in _PHASES_KEEP:
        return phase
    flag_list = list(flags or ())
    if any(flag in SLEEP_FLAGS for flag in flag_list):
        return PHASE_SLEEPING
    if phase == PHASE_SLEEPING:
        return PHASE_ACTIVE
    return phase


def day_closed_from_payload(payload: Any) -> tuple[str, int, str] | None:
    """(day_started_at, missed_streak, next_day_started_at) из payload day_closed или None."""
    data = _payload_dict(payload)
    if data is None:
        return None
    started = _str_value(data.get("day_started_at"))
    next_started = _str_value(data.get("next_day_started_at"))
    streak = _int_value(data.get("missed_streak"))
    if (
        started is None
        or next_started is None
        or streak is None
        or streak < 0
        or streak > MAX_POSITION_VALUE
        or data.get("outcome") not in DAY_CLOSED_OUTCOMES
    ):
        return None
    return started, streak, next_started


def tz_from_payload(payload: Any) -> str | None:
    """payload.tz (имя пояса IANA) из tz_set или None (битый payload).

    payload — dict или JSON-строка; лишние ключи игнорируются. tz — str длиной
    1–MAX_TZ_LEN, совпадает с _TZ_RE (до ZoneInfo: П-4) и открывается ZoneInfo.
    Набор поясов анкеты здесь не сверяется — это делает API.
    """
    data = _payload_dict(payload)
    if data is None:
        return None
    tz = data.get("tz")
    if not isinstance(tz, str) or not 1 <= len(tz) <= MAX_TZ_LEN:
        return None
    if _TZ_RE.fullmatch(tz) is None:
        return None
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return None
    return tz


def revive_from_payload(payload: Any) -> tuple[tuple[int, int, int], int] | None:
    """((stage_no, module_no, day_no), lives_returned) из payload revive_by_author или None.

    target — dict; каждое поле — int (не bool) ≥ 1; lives_returned — int (не bool) ≥ 0.
    Лишние ключи игнорируются.
    """
    data = _payload_dict(payload)
    if data is None:
        return None
    target = data.get("target")
    if not isinstance(target, dict):
        return None
    values: list[int] = []
    for field in _POSITION_FIELDS:
        value = _int_value(target.get(field))
        if value is None or value < 1:
            return None
        values.append(value)
    lives_returned = _int_value(data.get("lives_returned"))
    if lives_returned is None or lives_returned < 0:
        return None
    return (values[0], values[1], values[2]), lives_returned


def _apply_first_consent(conn: Connection, event_id: int, pid: uuid.UUID, kind: str) -> bool:
    applied = conn.execute(
        _UPSERT_STATE,
        {
            "pid": pid,
            "phase": PHASE_ONBOARDING,
            "version": PROJECTOR_VERSION,
            "from_phase": PHASE_PRE_REGISTERED,
        },
    ).first()
    if applied is None:
        _skip(event_id, kind, "transition not allowed")
        return False
    return True


def _apply_day_entered(
    conn: Connection,
    event_id: int,
    pid: uuid.UUID,
    kind: str,
    at: datetime | None,
    payload: Any,
) -> bool:
    position = position_from_payload(payload)
    if position is None or at is None:
        _skip(event_id, kind, "bad payload")
        return False
    stage_no, module_no, day_no = position
    applied = conn.execute(
        _SET_POSITION,
        {
            "pid": pid,
            "stage_no": stage_no,
            "module_no": module_no,
            "day_no": day_no,
            "at": at,
            "version": PROJECTOR_VERSION,
        },
    ).first()
    if applied is None:
        _skip(event_id, kind, "position already set or no state")
        return False
    _insert_pause_budget(conn, pid, at, applied[1])
    return True


def _insert_pause_budget(
    conn: Connection, pid: uuid.UUID, first_day_at: datetime, tz: str | None
) -> None:
    """Строка pause_budgets, если её нет (Р12): 14, цикл — формула бэкфилла 0018, restart_no 0."""
    tz = tz or day_clock.DEFAULT_TZ  # как бэкфилл 0018: нет пояса → Europe/Moscow
    cycle_start = day_clock.last_midnight(day_clock.active_from(first_day_at, tz), tz)
    conn.execute(
        _INSERT_PAUSE_BUDGET,
        {"pid": pid, "d": pause_rules.BUDGET_DAYS, "c": cycle_start},
    )


def _apply_day_report_submitted(
    conn: Connection, event_id: int, pid: uuid.UUID, kind: str, payload: Any
) -> bool:
    started = report_day_started_at(payload)
    next_day = report_next_day(payload)
    if started is None or next_day is None:
        _skip(event_id, kind, "bad payload")
        return False
    if next_day is _NO_NEXT:
        applied = conn.execute(
            _RESET_MISSED_STREAK,
            {"pid": pid, "day_started_at": started, "version": PROJECTOR_VERSION},
        ).first()
    else:
        stage_no, module_no, day_no, next_started = next_day  # type: ignore[misc]
        applied = conn.execute(
            _ADVANCE_DAY,
            {
                "pid": pid,
                "stage_no": stage_no,
                "module_no": module_no,
                "day_no": day_no,
                "next_day_started_at": next_started,
                "day_started_at": started,
                "version": PROJECTOR_VERSION,
            },
        ).first()
    if applied is None:
        _skip(event_id, kind, "not current day or no state")
        return False
    return True


def _apply_life_op(
    conn: Connection, event_id: int, pid: uuid.UUID, kind: str, payload: Any
) -> bool:
    data = _payload_dict(payload)
    reason = data.get("reason") if data is not None else None
    if reason == LIFE_OP_REASON_AUTHOR:
        return _apply_author_life_op(conn, event_id, pid, kind, payload)
    if reason != LIFE_OP_REASON:
        _skip(event_id, kind, "bad payload")
        return False
    return _apply_missed_days_life_op(conn, event_id, pid, kind, payload)


def _apply_missed_days_life_op(
    conn: Connection, event_id: int, pid: uuid.UUID, kind: str, payload: Any
) -> bool:
    parsed = life_op_from_payload(payload)
    if parsed is None:
        _skip(event_id, kind, "bad payload")
        return False
    started, delta = parsed
    applied = conn.execute(
        _APPLY_LIFE_OP,
        {
            "pid": pid,
            "delta": delta,
            "sleeping": PHASE_SLEEPING,
            "day_started_at": started,
            "max_lives": MAX_LIVES,
            "version": PROJECTOR_VERSION,
        },
    ).first()
    if applied is None:
        _skip(event_id, kind, "not current day, phase, lives out of range or no state")
        return False
    _, stage_no, module_no, day_no = applied
    if stage_no is None or module_no is None or day_no is None:
        logger.warning("projector: life_writeoffs skipped, no position, event id=%s", event_id)
        return True
    conn.execute(
        _INSERT_LIFE_WRITEOFF,
        {"pid": pid, "event_id": event_id, "s": stage_no, "m": module_no, "d": day_no},
    )
    return True


def _apply_author_life_op(
    conn: Connection, event_id: int, pid: uuid.UUID, kind: str, payload: Any
) -> bool:
    delta = author_life_op_from_payload(payload)
    if delta is None:
        _skip(event_id, kind, "bad payload")
        return False
    applied = conn.execute(
        _APPLY_AUTHOR_LIFE_OP,
        {
            "pid": pid,
            "delta": delta,
            "sleeping": PHASE_SLEEPING,
            "max_lives": MAX_LIVES,
            "version": PROJECTOR_VERSION,
        },
    ).first()
    if applied is not None:
        return True
    row = conn.execute(_SELECT_LIFE_STATE, {"pid": pid}).first()
    if row is None:
        _skip(event_id, kind, "no state")
        return False
    lives, flags, phase = row
    if phase not in _LIFE_OP_PHASES:
        _skip(event_id, kind, "phase not allowed")
        return False
    _skip(event_id, kind, classify_life_op(lives, delta, flags) or "not applied")
    return False


def _apply_day_closed(
    conn: Connection, event_id: int, pid: uuid.UUID, kind: str, payload: Any
) -> bool:
    parsed = day_closed_from_payload(payload)
    if parsed is None:
        _skip(event_id, kind, "bad payload")
        return False
    started, streak, next_started = parsed
    applied = conn.execute(
        _CLOSE_DAY,
        {
            "pid": pid,
            "day_started_at": started,
            "missed_streak": streak,
            "next_day_started_at": next_started,
            "version": PROJECTOR_VERSION,
        },
    ).first()
    if applied is None:
        _skip(event_id, kind, "not current day or no state")
        return False
    return True


def _apply_tz_set(
    conn: Connection, event_id: int, pid: uuid.UUID, kind: str, payload: Any
) -> bool:
    tz = tz_from_payload(payload)
    if tz is None:
        _skip(event_id, kind, "bad payload")
        return False
    applied = conn.execute(
        _SET_TZ,
        {"pid": pid, "tz": tz, "version": PROJECTOR_VERSION},
    ).first()
    if applied is None:
        _skip(event_id, kind, "tz_set: day started or no state")
        return False
    return True


def reissue_day(
    conn: Connection,
    pid: uuid.UUID,
    target: tuple[int, int, int],
    at: datetime,
    tz: str | None,
    day_start: datetime | None = None,
) -> datetime:
    """Перевыдача дня (не событие и не day_entered): позиция = target, missed_streak 0,
    day_started_at = D = day_start или day_clock.next_midnight(at, tz) (None — как v7).
    Возвращает D."""
    started = day_start if day_start is not None else day_clock.next_midnight(at, tz)
    stage_no, module_no, day_no = target
    conn.execute(
        _REISSUE_DAY,
        {
            "pid": pid,
            "stage_no": stage_no,
            "module_no": module_no,
            "day_no": day_no,
            "started": started,
            "version": PROJECTOR_VERSION,
        },
    )
    return started


def _apply_restart_paid(
    conn: Connection,
    event_id: int,
    pid: uuid.UUID,
    kind: str,
    at: datetime | None,
    payload: Any,
) -> bool:
    if _payload_dict(payload) is None or at is None:
        _skip(event_id, kind, "bad payload")
        return False
    row = conn.execute(_SELECT_RESTART_STATE, {"pid": pid}).first()
    if row is None:
        _skip(event_id, kind, "no state")
        return False
    phase, status_flags, stage_no, tz = row
    flag_list = list(status_flags or ())
    if FLAG_BLOCK_LIVES not in flag_list or stage_no is None:
        _skip(event_id, kind, "restart: not blocked or no position")
        return False
    flags = [flag for flag in flag_list if flag != FLAG_BLOCK_LIVES]
    applied = conn.execute(
        _APPLY_RESTART,
        {
            "pid": pid,
            "lives": RESTART_LIVES,
            "flags": flags,
            "phase": phase_for_flags(phase, flags),
            "version": PROJECTOR_VERSION,
        },
    ).first()
    if applied is None:
        _skip(event_id, kind, "restart: not blocked or no position")
        return False
    started = reissue_day(conn, pid, (stage_no, 1, 1), at, tz)
    restart_no = conn.execute(_SELECT_RESTART_NO, {"pid": pid}).scalar()
    conn.execute(
        _UPSERT_PAUSE_BUDGET,
        {"pid": pid, "d": PAUSE_BUDGET_DAYS, "c": started, "r": (restart_no or 0) + 1},
    )
    return True


def _apply_revive_by_author(
    conn: Connection,
    event_id: int,
    pid: uuid.UUID,
    kind: str,
    at: datetime | None,
    payload: Any,
) -> bool:
    parsed = revive_from_payload(payload)
    if parsed is None or at is None:
        _skip(event_id, kind, "bad payload")
        return False
    target, lives_returned = parsed
    row = conn.execute(_SELECT_REVIVE_STATE, {"pid": pid}).first()
    if row is None:
        _skip(event_id, kind, "no state")
        return False
    phase, status_flags, stage_no, module_no, day_no, tz = row
    flag_list = list(status_flags or ())
    if FLAG_BLOCK_LIVES not in flag_list or stage_no is None:
        _skip(event_id, kind, "revive: not blocked or no position")
        return False
    if target[0] != stage_no:
        _skip(event_id, kind, "revive: other stage")
        return False
    if (target[1], target[2]) > (module_no, day_no):
        _skip(event_id, kind, "revive: target ahead")
        return False
    flags = [flag for flag in flag_list if flag != FLAG_BLOCK_LIVES]
    applied = conn.execute(
        _APPLY_REVIVE,
        {
            "pid": pid,
            "lives": min(MAX_LIVES, 1 + lives_returned),
            "flags": flags,
            "phase": phase_for_flags(phase, flags),
            "s": stage_no,
            "version": PROJECTOR_VERSION,
        },
    ).first()
    if applied is None:
        _skip(event_id, kind, "revive: not blocked or no position")
        return False
    reissue_day(conn, pid, target, at, tz)
    return True


def pause_id_from_payload(payload: Any) -> int | None:
    """payload.pause_id — int (не bool) ≥ 1, или None (битый payload)."""
    data = _payload_dict(payload)
    if data is None:
        return None
    pause_id = _int_value(data.get("pause_id"))
    if pause_id is None or pause_id < 1:
        return None
    return pause_id


def pause_reason_from_payload(payload: Any, allowed: Sequence[str]) -> str | None:
    """payload.reason из списка allowed или None (битый payload)."""
    data = _payload_dict(payload)
    if data is None:
        return None
    reason = data.get("reason")
    if not isinstance(reason, str) or reason not in allowed:
        return None
    return reason


def _utc(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc)


def _set_pause_status(
    conn: Connection,
    event_id: int,
    pid: uuid.UUID,
    kind: str,
    pause_id: int,
    allowed_from: Sequence[str],
    to_status: Callable[[Any], str],
) -> bool:
    """Смена статуса строки паузы (Р1): из allowed_from в to_status(row); иначе пропуск."""
    row = conn.execute(_SELECT_PAUSE, {"id": pause_id, "pid": pid}).first()
    if row is None:
        _skip(event_id, kind, "pause: not found")
        return False
    if row.status not in allowed_from:
        _skip(event_id, kind, "pause: status not allowed")
        return False
    applied = conn.execute(
        _SET_PAUSE_STATUS,
        {"id": pause_id, "pid": pid, "from": row.status, "to": to_status(row)},
    ).first()
    if applied is None:
        _skip(event_id, kind, "pause: status not allowed")
        return False
    return True


def _apply_pause_approved(
    conn: Connection,
    event_id: int,
    pid: uuid.UUID,
    kind: str,
    at: datetime | None,
    payload: Any,
) -> bool:
    pause_id = pause_id_from_payload(payload)
    if pause_id is None or at is None:
        _skip(event_id, kind, "bad payload")
        return False

    def _to(row: Any) -> str:
        # Р14: одобрение после start_at — заявка сгорает.
        return "cancelled" if _utc(at) >= _utc(row.start_at) else "approved"

    return _set_pause_status(conn, event_id, pid, kind, pause_id, ("requested",), _to)


def _apply_pause_simple(
    conn: Connection,
    event_id: int,
    pid: uuid.UUID,
    kind: str,
    payload: Any,
    allowed_from: Sequence[str],
    to: str,
    reasons: Sequence[str] | None = None,
) -> bool:
    pause_id = pause_id_from_payload(payload)
    if pause_id is None or (
        reasons is not None and pause_reason_from_payload(payload, reasons) is None
    ):
        _skip(event_id, kind, "bad payload")
        return False
    return _set_pause_status(conn, event_id, pid, kind, pause_id, allowed_from, lambda _r: to)


def _pause_budget(
    conn: Connection, pid: uuid.UUID, at: datetime, tz: str | None
) -> tuple[datetime, int, int]:
    """(cycle_start_at, остаток, restart_no) после ленивой смены цикла по at (Р9).

    Строки нет → создать тем же SQL, что в day_entered (Р12, запасной путь): по первому
    day_entered, а без него — по at события. Смена цикла записывается сразу.
    """
    row = conn.execute(_SELECT_PAUSE_BUDGET, {"pid": pid}).first()
    if row is None:
        first_at = conn.execute(_SELECT_FIRST_DAY_ENTERED, {"pid": pid}).scalar()
        _insert_pause_budget(conn, pid, first_at if first_at is not None else at, tz)
        row = conn.execute(_SELECT_PAUSE_BUDGET, {"pid": pid}).one()
    days_left, cycle_start, restart_no = row
    new_start, new_left = pause_rules.roll_cycle(cycle_start, days_left, at, tz)
    if _utc(new_start) != _utc(cycle_start) or new_left != days_left:
        conn.execute(_UPDATE_PAUSE_BUDGET, {"pid": pid, "d": new_left, "c": new_start})
    return new_start, new_left, restart_no


def _apply_pause_started(
    conn: Connection,
    event_id: int,
    pid: uuid.UUID,
    kind: str,
    at: datetime | None,
    payload: Any,
) -> bool:
    pause_id = pause_id_from_payload(payload)
    if pause_id is None or at is None:
        _skip(event_id, kind, "bad payload")
        return False
    pause = conn.execute(_SELECT_PAUSE, {"id": pause_id, "pid": pid}).first()
    if pause is None:
        _skip(event_id, kind, "pause: not found")
        return False
    if pause.status != "approved":
        _skip(event_id, kind, "pause: status not allowed")
        return False
    state = conn.execute(_SELECT_PAUSE_STATE, {"pid": pid}).first()
    if state is None:
        _skip(event_id, kind, "no state")
        return False
    phase, status_flags, stage_no, _module_no, day_no, tz = state
    try:
        days = pause_rules.pause_days(pause.start_at, pause.planned_end_at, tz)
    except ValueError:
        _skip(event_id, kind, "pause: bad period")
        return False
    _cycle_start, days_left, restart_no = _pause_budget(conn, pid, at, tz)
    stage_taken = bool(
        conn.execute(
            _SELECT_STAGE_TAKEN, {"pid": pid, "s": stage_no, "r": restart_no}
        ).scalar()
    )
    last_ended_at = conn.execute(_SELECT_LAST_PAUSE_END, {"pid": pid}).scalar()
    flag_list = list(status_flags or ())
    refusal = pause_rules.start_refusal(
        status=pause.status,
        flags=flag_list,
        phase=phase,
        day_no=day_no,
        days=days,
        days_left=days_left,
        stage_taken=stage_taken,
        last_ended_at=last_ended_at,
        start_at=pause.start_at,
    )
    if refusal is None:
        charged = conn.execute(_CHARGE_PAUSE_BUDGET, {"pid": pid, "n": days}).first()
        if charged is None:
            refusal = pause_rules.REASON_NO_BUDGET
    if refusal is not None:
        # Р15: правило нарушено → заявка сгорает, флага нет.
        conn.execute(
            _SET_PAUSE_STATUS,
            {"id": pause_id, "pid": pid, "from": "approved", "to": "cancelled"},
        )
        logger.warning(
            "projector: pause_started отклонён: %s, event id=%s", refusal, event_id
        )
        return True
    conn.execute(
        _START_PAUSE, {"id": pause_id, "pid": pid, "s": stage_no, "r": restart_no}
    )
    flags = flag_list if FLAG_PAUSE_USER in flag_list else [*flag_list, FLAG_PAUSE_USER]
    conn.execute(
        _SET_PAUSE_FLAGS,
        {
            "pid": pid,
            "flags": flags,
            "phase": phase_for_flags(phase, flags),
            "version": PROJECTOR_VERSION,
        },
    )
    return True


def _apply_pause_ended(
    conn: Connection,
    event_id: int,
    pid: uuid.UUID,
    kind: str,
    at: datetime | None,
    payload: Any,
) -> bool:
    pause_id = pause_id_from_payload(payload)
    reason = pause_reason_from_payload(payload, PAUSE_END_REASONS)
    if pause_id is None or reason is None or at is None:
        _skip(event_id, kind, "bad payload")
        return False
    pause = conn.execute(_SELECT_PAUSE, {"id": pause_id, "pid": pid}).first()
    if pause is None:
        _skip(event_id, kind, "pause: not found")
        return False
    if pause.status != "active":
        _skip(event_id, kind, "pause: status not allowed")
        return False
    state = conn.execute(_SELECT_PAUSE_STATE, {"pid": pid}).first()
    if state is None:
        _skip(event_id, kind, "no state")
        return False
    phase, status_flags, stage_no, module_no, day_no, tz = state
    if stage_no is None or module_no is None or day_no is None:
        _skip(event_id, kind, "pause: no position")
        return False
    if reason == PAUSE_END_EXPIRED:
        if _utc(at) < _utc(pause.planned_end_at):
            _skip(event_id, kind, "pause: expired before planned end")
            return False
        day_start = day_clock.last_midnight(at, tz)  # Р5
    else:
        day_start = day_clock.next_midnight(at, tz)  # Р6
    conn.execute(_END_PAUSE, {"id": pause_id, "pid": pid, "at": at})
    flags = [flag for flag in (status_flags or ()) if flag != FLAG_PAUSE_USER]
    conn.execute(
        _SET_PAUSE_FLAGS,
        {
            "pid": pid,
            "flags": flags,
            "phase": phase_for_flags(phase, flags),
            "version": PROJECTOR_VERSION,
        },
    )
    reissue_day(conn, pid, (stage_no, module_no, day_no), at, tz, day_start=day_start)  # Р7
    if reason == PAUSE_END_BY_PARTICIPANT:
        refund = pause_rules.refund_days(pause.planned_end_at, day_start, tz)
        if refund > 0:
            cycle_start, days_left, _restart_no = _pause_budget(conn, pid, at, tz)
            # Р8: возврат — только за паузу текущего цикла, остаток не выше 14.
            if _utc(pause.start_at) >= _utc(cycle_start):
                conn.execute(
                    _UPDATE_PAUSE_BUDGET,
                    {
                        "pid": pid,
                        "d": min(pause_rules.BUDGET_DAYS, days_left + refund),
                        "c": cycle_start,
                    },
                )
    return True


def _apply_event(
    conn: Connection,
    event_id: int,
    pid: uuid.UUID,
    kind: str,
    at: datetime | None = None,
    payload: Any = None,
) -> bool:
    """True — событие применено; False — пропущено (WARNING уже записан)."""
    if kind == EVENT_KIND_MINI_APP_FIRST_CONSENT:
        return _apply_first_consent(conn, event_id, pid, kind)
    if kind == EVENT_KIND_DAY_ENTERED:
        return _apply_day_entered(conn, event_id, pid, kind, at, payload)
    if kind == EVENT_KIND_DAY_REPORT_SUBMITTED:
        return _apply_day_report_submitted(conn, event_id, pid, kind, payload)
    if kind == EVENT_KIND_LIFE_OP:
        return _apply_life_op(conn, event_id, pid, kind, payload)
    if kind == EVENT_KIND_DAY_CLOSED:
        return _apply_day_closed(conn, event_id, pid, kind, payload)
    if kind == EVENT_KIND_TZ_SET:
        return _apply_tz_set(conn, event_id, pid, kind, payload)
    if kind == EVENT_KIND_RESTART_PAID:
        return _apply_restart_paid(conn, event_id, pid, kind, at, payload)
    if kind == EVENT_KIND_REVIVE_BY_AUTHOR:
        return _apply_revive_by_author(conn, event_id, pid, kind, at, payload)
    if kind == EVENT_KIND_PAUSE_APPROVED:
        return _apply_pause_approved(conn, event_id, pid, kind, at, payload)
    if kind == EVENT_KIND_PAUSE_REJECTED:
        return _apply_pause_simple(conn, event_id, pid, kind, payload, ("requested",), "rejected")
    if kind == EVENT_KIND_PAUSE_CANCEL:
        return _apply_pause_simple(
            conn, event_id, pid, kind, payload, ("requested", "approved"), "cancelled"
        )
    if kind == EVENT_KIND_PAUSE_START_FAILED:
        return _apply_pause_simple(
            conn,
            event_id,
            pid,
            kind,
            payload,
            ("requested", "approved"),
            "cancelled",
            pause_rules.REFUSAL_REASONS,
        )
    if kind == EVENT_KIND_PAUSE_STARTED:
        return _apply_pause_started(conn, event_id, pid, kind, at, payload)
    if kind == EVENT_KIND_PAUSE_ENDED:
        return _apply_pause_ended(conn, event_id, pid, kind, at, payload)
    _skip(event_id, kind, "unknown kind")
    return False


def _apply_in_savepoint(
    conn: Connection,
    event_id: int,
    pid: uuid.UUID,
    kind: str,
    at: datetime | None,
    payload: Any,
) -> bool:
    """Событие внутри SAVEPOINT. DataError / IntegrityError → откат savepoint, пропуск.

    Другие SQLAlchemyError не ловятся: вызывающий откатывает всю пачку.
    """
    savepoint = conn.begin_nested()
    try:
        applied = _apply_event(conn, event_id, pid, kind, at, payload)
    except (DataError, IntegrityError) as exc:
        savepoint.rollback()
        # Только id, kind и имя класса: текст исключения может содержать значения.
        _skip(event_id, kind, f"bad payload, {type(exc).__name__}")
        return False
    savepoint.commit()
    return applied


def _process_batch(engine: Engine) -> tuple[ProjectorResult, int]:
    """Одна пачка — одна транзакция. Возвращает итог и число прочитанных событий."""
    processed = 0
    skipped = 0
    with engine.begin() as conn:
        rows = conn.execute(_SELECT_BATCH, {"limit": BATCH_SIZE}).all()
        last_ids: dict[uuid.UUID, int] = {}
        for event_id, pid, kind, at, payload in rows:
            if _apply_in_savepoint(conn, event_id, pid, kind, at, payload):
                processed += 1
            else:
                skipped += 1
            last_ids[pid] = event_id  # строки идут по возрастанию id
        if last_ids:
            conn.execute(
                _UPSERT_CHECKPOINT,
                [{"pid": pid, "last_event_id": last} for pid, last in last_ids.items()],
            )
    return ProjectorResult(processed, skipped), len(rows)


def _drain(engine: Engine) -> ProjectorResult:
    """Пачки по BATCH_SIZE, пока новые события есть. Lock берёт вызывающий."""
    processed = 0
    skipped = 0
    while True:
        result, read = _process_batch(engine)
        processed += result.processed
        skipped += result.skipped
        if read < BATCH_SIZE:
            return ProjectorResult(processed, skipped)


@contextmanager
def _advisory_lock(engine: Engine) -> Iterator[Connection]:
    """pg_advisory_lock на отдельном соединении; второй экземпляр ждёт здесь."""
    conn = engine.connect()
    released = False
    try:
        conn.execute(_LOCK)
        conn.commit()
        yield conn
        conn.execute(_UNLOCK)
        conn.commit()
        released = True
    finally:
        if not released:
            # Ошибка или остановка: соединение закрываем, Postgres снимет lock сам;
            # в пул соединение с lock не вернётся.
            with suppress(Exception):
                conn.invalidate()
        conn.close()


def _backfill_block_lives(engine: Engine) -> int:
    """Бэкфилл (Р3): sleeping с 0 жизней без флага → block_lives. Своя транзакция.

    Ошибки не глушатся. В лог — только число строк.
    """
    with engine.begin() as conn:
        count = conn.execute(_BACKFILL_BLOCK_LIVES, {"version": PROJECTOR_VERSION}).rowcount
    count = max(count or 0, 0)
    logger.info("projector: backfill block_lives, строк %s", count)
    return count


def run_once(engine: Engine) -> ProjectorResult:
    """Режим once: lock → бэкфилл block_lives → проход (все пачки) → unlock."""
    with _advisory_lock(engine):
        _backfill_block_lives(engine)
        return _drain(engine)


def _life_ops_step(engine: Engine, last_tick: datetime | None) -> datetime | None:
    """«Часы» (life-ops-c): tick раз в LIFE_OPS_INTERVAL_S по day_clock.utcnow().

    Любая ошибка tick → WARNING с именем класса, цикл проектора живёт дальше (У7).
    Часы назад (now < last_tick) → tick сразу. Возвращает момент последнего tick.
    """
    now = day_clock.utcnow()
    interval = timedelta(seconds=life_ops.LIFE_OPS_INTERVAL_S)
    if last_tick is not None and timedelta(0) <= now - last_tick < interval:
        return last_tick
    try:
        life_ops.tick(engine, now)
    except Exception as exc:  # noqa: BLE001 — шаг «часов» не роняет проектор
        logger.warning("projector: life_ops tick failed (%s)", type(exc).__name__)
    return now


def _pause_ops_step(engine: Engine, last_tick: datetime | None) -> datetime | None:
    """«Часы» пауз (api-pause-1b, Ч1): tick раз в PAUSE_OPS_INTERVAL_S по day_clock.utcnow().

    Любая ошибка tick → WARNING с именем класса, цикл проектора живёт дальше.
    Часы назад (now < last_tick) → tick сразу. Возвращает момент последнего tick.
    """
    now = day_clock.utcnow()
    interval = timedelta(seconds=PAUSE_OPS_INTERVAL_S)
    if last_tick is not None and timedelta(0) <= now - last_tick < interval:
        return last_tick
    try:
        pause_ops.tick(engine, now)
    except Exception as exc:  # noqa: BLE001 — шаг «часов» не роняет проектор
        logger.warning("projector: pause_ops tick failed (%s)", type(exc).__name__)
    return now


def _notify_ops_step(engine: Engine, last_tick: datetime | None) -> datetime | None:
    """«Часы» НП3 (pushi-notify-1): tick раз в NOTIFY_OPS_INTERVAL_S по day_clock.utcnow().

    Любая ошибка tick → WARNING с именем класса, цикл проектора живёт дальше.
    Часы назад (now < last_tick) → tick сразу. Возвращает момент последнего tick.
    """
    now = day_clock.utcnow()
    interval = timedelta(seconds=notify_ops.NOTIFY_OPS_INTERVAL_S)
    if last_tick is not None and timedelta(0) <= now - last_tick < interval:
        return last_tick
    try:
        notify_ops.tick(engine, now)
    except Exception as exc:  # noqa: BLE001 — шаг «часов» не роняет проектор
        logger.warning("projector: notify_ops tick failed (%s)", type(exc).__name__)
    return now


def run_forever(
    engine: Engine,
    *,
    poll_seconds: float = POLL_SECONDS,
    retry_seconds: float = RETRY_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Режим run: lock держится всё время; сбой БД → WARNING, пауза, повтор.

    После lock — бэкфилл block_lives (один раз на lock). После прохода — шаги «часов» (_life_ops_step, затем _notify_ops_step) под тем же lock
    проектора; once — без них.
    """
    last_tick: datetime | None = None
    last_notify: datetime | None = None
    last_pause: datetime | None = None
    while True:
        try:
            with _advisory_lock(engine) as lock_conn:
                logger.info("projector: lock acquired, running (version %s)", PROJECTOR_VERSION)
                _backfill_block_lives(engine)
                while True:
                    result = _drain(engine)
                    if result.processed or result.skipped:
                        logger.info(
                            "projector: обработано %s, пропущено %s",
                            result.processed,
                            result.skipped,
                        )
                    last_tick = _life_ops_step(engine, last_tick)
                    last_pause = _pause_ops_step(engine, last_pause)  # Ч1: сразу после life_ops
                    last_notify = _notify_ops_step(engine, last_notify)
                    # Проверка, что соединение с lock живо (иначе — повтор с начала).
                    lock_conn.execute(_PING)
                    lock_conn.commit()
                    sleep(poll_seconds)
        except SQLAlchemyError as exc:
            # Без traceback и текста исключения: только имя класса.
            logger.warning("projector: db error (%s)", type(exc).__name__)
            sleep(retry_seconds)


def _stop(signum: int, frame: object) -> None:
    raise SystemExit(0)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in ("run", "once"):
        print(USAGE, file=sys.stderr)
        return 2  # к настройкам и БД не обращаемся

    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # Свой DSN проектора (B-3a-2); сигнатура get_engine прежняя. DSN не логируем.
    # Битый DSN (B-3c): текст исключения может содержать части DSN, поэтому
    # в лог только имя класса — без str(exc) и без traceback. Для once и для run.
    # Нет драйвера диалекта (ImportError, в том числе ModuleNotFoundError) — тем же
    # путём (api-melochi).
    try:
        engine = get_engine(
            settings.model_copy(update={"database_url": settings.projector_dsn()})
        )
    except (SQLAlchemyError, ValueError, ImportError) as exc:
        logger.warning("projector: bad database url (%s)", type(exc).__name__)
        return 1

    if args[0] == "once":
        try:
            result = run_once(engine)
        except SQLAlchemyError as exc:
            logger.warning("projector: db error (%s)", type(exc).__name__)
            return 1
        print(f"projector once: обработано {result.processed}, пропущено {result.skipped}")
        return 0

    signal.signal(signal.SIGTERM, _stop)
    try:
        run_forever(engine)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
