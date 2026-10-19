"""Проектор participant_state: participant_events → participant_state (E1 / INV-1, projector-2).

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

Виды событий (PROJECTOR_VERSION 2):
  - mini_app_first_consent — строка состояния, фаза onboarding (без изменений с версии 1);
  - day_entered (iter2-api-2a) — позиция stage_no / module_no / day_no из payload,
    day_started_at = at события, missed_streak = 0; только если позиции ещё нет
    (WHERE day_no IS NULL). 0 строк (позиция уже есть или строки нет) → WARNING, пропуск.
    lifecycle_phase, status_flags и author_pause_reason не трогаются (В21).
    Граница: каждое из stage_no, module_no, day_no — целое от 1 до MAX_POSITION_VALUE
    (32767, предел smallint); вне границы, не целое или bool → «bad payload», пропуск;
  - day_report_submitted (iter2-api-2b, В18) — missed_streak = 0 при ЛЮБОМ вердикте, только
    если day_started_at строки совпадает с payload.day_started_at (текущий день, ревью #95).
    0 строк (старый день или строки нет) → WARNING, пропуск. Нет строки day_started_at
    в payload → «bad payload»; строка не разбирается как timestamptz → DataError в savepoint →
    «bad payload». Без ON CONFLICT; lifecycle_phase, status_flags и lives не упоминаются (Ш1).

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
participant_events только читается; at и payload читаются для day_entered и
day_report_submitted, в лог не идут.
author_pause_reason и last_seen_publish_epoch не трогаются.
DSN проектора — Settings.projector_dsn(): PROJECTOR_DATABASE_URL → DATABASE_URL → POSTGRES_*
(B-3a-2; роль app_projector — миграция 0006). DSN не логируется.
Битый DSN или нет драйвера диалекта (B-3c, api-melochi): WARNING только с именем класса
ошибки (ArgumentError, ValueError, ModuleNotFoundError), код выхода 1, цикл не стартует.
"""
from __future__ import annotations

import json
import logging
import signal
import sys
import time
import uuid
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import DataError, IntegrityError, SQLAlchemyError

from app.config import get_settings
from app.db.models import EVENT_KIND_MINI_APP_FIRST_CONSENT
from app.db.session import get_engine

logger = logging.getLogger("app.projector")

BATCH_SIZE = 500
POLL_SECONDS = 1.0
RETRY_SECONDS = 5.0
PROJECTOR_VERSION = 2
PHASE_PRE_REGISTERED = "pre_registered"
PHASE_ONBOARDING = "onboarding"
# Пишет POST /miniapp/v1/day/test-enter (app/routers/day.py) под замком participant:pid.
EVENT_KIND_DAY_ENTERED = "day_entered"
# Пишет POST /miniapp/v1/day/report/submit (app/routers/day.py) под замком participant:pid.
EVENT_KIND_DAY_REPORT_SUBMITTED = "day_report_submitted"
# Верхняя граница stage_no / module_no / day_no (smallint).
MAX_POSITION_VALUE = 32767
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
    RETURNING pid
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


def position_from_payload(payload: Any) -> tuple[int, int, int] | None:
    """(stage_no, module_no, day_no) из payload day_entered или None (битый payload).

    Каждое значение — int (не bool) от 1 до MAX_POSITION_VALUE включительно.
    """
    data = _payload_dict(payload)
    if data is None:
        return None
    values: list[int] = []
    for field in _POSITION_FIELDS:
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
    value = data.get("day_started_at")
    if not isinstance(value, str) or not value:
        return None
    return value


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
    return True


def _apply_day_report_submitted(
    conn: Connection, event_id: int, pid: uuid.UUID, kind: str, payload: Any
) -> bool:
    started = report_day_started_at(payload)
    if started is None:
        _skip(event_id, kind, "bad payload")
        return False
    applied = conn.execute(
        _RESET_MISSED_STREAK,
        {"pid": pid, "day_started_at": started, "version": PROJECTOR_VERSION},
    ).first()
    if applied is None:
        _skip(event_id, kind, "not current day or no state")
        return False
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


def run_once(engine: Engine) -> ProjectorResult:
    """Режим once: lock → проход (все пачки) → unlock."""
    with _advisory_lock(engine):
        return _drain(engine)


def run_forever(
    engine: Engine,
    *,
    poll_seconds: float = POLL_SECONDS,
    retry_seconds: float = RETRY_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Режим run: lock держится всё время; сбой БД → WARNING, пауза, повтор."""
    while True:
        try:
            with _advisory_lock(engine) as lock_conn:
                logger.info("projector: lock acquired, running")
                while True:
                    result = _drain(engine)
                    if result.processed or result.skipped:
                        logger.info(
                            "projector: обработано %s, пропущено %s",
                            result.processed,
                            result.skipped,
                        )
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
