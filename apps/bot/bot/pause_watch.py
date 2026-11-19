"""apps/bot/bot/pause_watch.py — наблюдатель пауз (bot-pause-1, Р5–Р9).

Фоновая задача asyncio в процессе бота (по образцу воркера outbox в bot/app.py), тот же Bot и тот же
stop. Раз в PAUSE_WATCH_SECONDS: WATCH в своей транзакции; для каждой строки — метки pause.labels_for.
Каждая метка — своя транзакция:
  1. KEY_TTL pause_note:{pid}:{pause_id}:{метка}; rowcount 0 → уже отправлено, пропуск.
  2. Отправка: requested — карточка Автору (WORK_GROUP_ID, тема ACCESS_ADMIN_TOPIC_ID) с кнопками
     «pse:a:<id>» / «pse:r:<id>»; auto — алерт Автору туда же; остальное — участнику в личку.
  3. Успех → COMMIT; TelegramForbiddenError / TelegramBadRequest → COMMIT + WARNING (повтор
     бесполезен); прочая ошибка отправки → ROLLBACK, повтор в следующем тике.
auto — только для active и только если нет ключа pause_decide (KEY_EXISTS пусто).
Ошибка БД в тике → WARNING с именем класса, следующий тик.
Остановка (stop_pause_watcher): stop.set(), ожидание до PAUSE_STOP_TIMEOUT, затем cancel.
Соединение — bot.access.connect (BOT_DATABASE_URL), новое на каждый тик.
Логи: только метка, код и счётчики; без tg_user_id, pid, short_no и дат.
"""
from __future__ import annotations

import asyncio
import logging

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from bot import access, pause
from bot.config import BotConfig

logger = logging.getLogger(__name__)

PAUSE_WATCH_SECONDS = 60
PAUSE_STOP_TIMEOUT = 25


class _Retry(Exception):
    """Отправка не удалась временно → ROLLBACK ключа, повтор в следующем тике."""


async def _send(bot, config: BotConfig, label: str, row: pause.Row) -> None:
    text = pause.text_for_label(label, row)
    if label == pause.REQUESTED:
        await bot.send_message(chat_id=config.work_group_id, message_thread_id=config.access_admin_topic_id,
                               text=text, reply_markup=pause.card_keyboard(row.id))
    elif label == pause.AUTO:
        await bot.send_message(chat_id=config.work_group_id, message_thread_id=config.access_admin_topic_id,
                               text=text)
    else:
        await bot.send_message(chat_id=row.tg_user_id, text=text)


async def _note(conn, bot, config: BotConfig, label: str, row: pause.Row) -> str:
    """Одна метка в своей транзакции → «sent» | «skip» | «dropped» | «retry»."""
    outcome = "sent"
    try:
        async with conn.transaction():
            cur = await conn.execute(pause.KEY_TTL, (pause.note_key(row.pid, row.id, label), pause.NOTE_KIND, label))
            if cur.rowcount == 0:
                return "skip"
            try:
                await _send(bot, config, label, row)
            except (TelegramForbiddenError, TelegramBadRequest) as exc:
                logger.warning("pause: %s не доставлено, повтора не будет (%s)", label, type(exc).__name__)
                outcome = "dropped"
            except Exception as exc:  # noqa: BLE001 — прочая ошибка отправки → откат ключа
                logger.warning("pause: %s не отправлено, повтор (%s)", label, type(exc).__name__)
                raise _Retry from None
    except _Retry:
        return "retry"
    return outcome


async def _decided(conn, row: pause.Row) -> bool:
    cur = await conn.execute(pause.KEY_EXISTS, (pause.decide_key(row.pid, row.id),))
    return await cur.fetchone() is not None


async def tick(conn, bot, config: BotConfig) -> dict[str, int]:
    """Один проход наблюдателя → счётчики исходов."""
    counts = {"sent": 0, "skip": 0, "dropped": 0, "retry": 0}
    async with conn.transaction():
        cur = await conn.execute(pause.WATCH)
        rows = [pause.Row(*raw) for raw in await cur.fetchall()]
    for row in rows:
        _first, _last, n, _utc = pause.local_dates(row.start_at, row.planned_end_at, row.tz)
        decided = await _decided(conn, row) if row.status == pause.ACTIVE else False
        for label in pause.labels_for(row, n, decided):
            counts[await _note(conn, bot, config, label, row)] += 1
    return counts


async def run_watcher(bot, config: BotConfig, stop: asyncio.Event, connect=None) -> None:
    connect = connect or access.connect
    while not stop.is_set():
        try:
            conn = await connect(config.database_url)
            try:
                counts = await tick(conn, bot, config)
            finally:
                await conn.close()
            if counts["sent"] or counts["dropped"] or counts["retry"]:
                logger.info("pause: тик sent=%s dropped=%s retry=%s", counts["sent"], counts["dropped"],
                            counts["retry"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("pause: тик не выполнен (%s)", type(exc).__name__)
        try:
            await asyncio.wait_for(stop.wait(), timeout=PAUSE_WATCH_SECONDS)
        except asyncio.TimeoutError:
            pass


def start_pause_watcher(bot, config: BotConfig, stop: asyncio.Event, connect=None) -> "asyncio.Task":
    """Запустить наблюдатель фоновой задачей (вызывается только при config.access_enabled)."""
    return asyncio.create_task(run_watcher(bot, config, stop, connect), name="pause_watch")


async def stop_pause_watcher(task: "asyncio.Task | None", stop: asyncio.Event) -> None:
    stop.set()
    if task is None:
        return
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=PAUSE_STOP_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning("pause: наблюдатель не остановился за %s с — cancel", PAUSE_STOP_TIMEOUT)
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        logger.error("pause: наблюдатель завершился с ошибкой %s", type(exc).__name__)
