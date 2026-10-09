"""Проектор participant_state: participant_events → participant_state (E1 / INV-1, projector-2).

Запуск: python -m app.projector run | once
  - run  — постоянный цикл: проход раз в 1 с, пачки до 500 событий; advisory lock держится
           на отдельном соединении всё время работы (второй экземпляр ждёт);
  - once — один проход: lock → проход → unlock;
           печатает «projector once: обработано K, пропущено S».

Источники (docs/architecture/**, read-only; выдержки — docs/tasks/projector-2.md, раздел 4):
  - errata-unified E1: participant_state — обычная таблица, наполняемая проектором; API туда
    не пишет никогда (INV-1). SQL записи в participant_state — только в этом модуле
    (проверяет tests/test_projector_static.py);
  - I2 fsm_participant: pre_registered → onboarding по mini_app_first_consent (6А, D-11);
  - I2 checkpoint_table: participant_state_checkpoints (pid, last_event_id, at).

Курсор — по pid: события e с e.id > coalesce(c.last_event_id, 0) через LEFT JOIN
participant_state_checkpoints c USING (pid), ORDER BY e.id, LIMIT 500. Глобальный
max(last_event_id) не используется: коммиты разных pid идут не по порядку id.
Порядок внутри одного pid держится, пока у pid один писатель событий (сейчас — first-launch); новые писатели событий — пересмотреть курсор (заметка для будущих карточек).

Пачка — одна транзакция. Неизвестный kind или запрещённый переход → WARNING (id и kind
события, без payload и pid), событие пропускается, checkpoint сдвигается.
participant_events только читается; author_pause_reason и last_seen_publish_epoch не трогаются.
DSN проектора — Settings.projector_dsn(): PROJECTOR_DATABASE_URL → DATABASE_URL → POSTGRES_*
(B-3a-2; роль app_projector — миграция 0006). DSN не логируется.
"""
from __future__ import annotations

import logging
import signal
import sys
import time
import uuid
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass

from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.db.models import EVENT_KIND_MINI_APP_FIRST_CONSENT
from app.db.session import get_engine

logger = logging.getLogger("app.projector")

BATCH_SIZE = 500
POLL_SECONDS = 1.0
RETRY_SECONDS = 5.0
PROJECTOR_VERSION = 1
PHASE_PRE_REGISTERED = "pre_registered"
PHASE_ONBOARDING = "onboarding"
USAGE = "usage: python -m app.projector run | once"

_LOCK = text("SELECT pg_advisory_lock(hashtext('participant_state_projector'))")
_UNLOCK = text("SELECT pg_advisory_unlock(hashtext('participant_state_projector'))")
_PING = text("SELECT 1")

# payload не читаем: проектору он не нужен и не должен попасть в лог.
_SELECT_BATCH = text(
    """
    SELECT e.id, e.pid, e.kind
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


@dataclass(frozen=True)
class ProjectorResult:
    processed: int
    skipped: int


def _skip(event_id: int, kind: str, reason: str) -> None:
    logger.warning("projector: skip event id=%s kind=%s (%s)", event_id, kind, reason)


def _apply_event(conn: Connection, event_id: int, pid: uuid.UUID, kind: str) -> bool:
    """True — событие применено; False — пропущено (WARNING уже записан)."""
    if kind != EVENT_KIND_MINI_APP_FIRST_CONSENT:
        _skip(event_id, kind, "unknown kind")
        return False
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


def _process_batch(engine: Engine) -> tuple[ProjectorResult, int]:
    """Одна пачка — одна транзакция. Возвращает итог и число прочитанных событий."""
    processed = 0
    skipped = 0
    with engine.begin() as conn:
        rows = conn.execute(_SELECT_BATCH, {"limit": BATCH_SIZE}).all()
        last_ids: dict[uuid.UUID, int] = {}
        for event_id, pid, kind in rows:
            if _apply_event(conn, event_id, pid, kind):
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
    engine = get_engine(settings.model_copy(update={"database_url": settings.projector_dsn()}))

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
