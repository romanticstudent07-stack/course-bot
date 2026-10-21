"""apps/bot/bot/outbox.py — воркер outbox: доставка в Telegram под ролью app_bot (send-1b).

Цикл asyncio в процессе бота: строка outbox -> адресат по pid (aggregate_id) -> текст
(text_registry + render из send-1a) -> Telegram -> sent_at; окончательная ошибка -> outbox_dlq.
БД — psycopg 3 (async, без SQLAlchemy), DSN — BOT_DATABASE_URL (coursebot_bot, роль app_bot).

SQL и права (миграция 0009_app_bot; других прав у app_bot нет):
    CLAIM     SELECT (id, aggregate_id, event_type, payload, created_at) на outbox
    MARK      UPDATE (sent_at) на outbox
    TO_DLQ    INSERT (original_id, payload, error) на outbox_dlq + USAGE outbox_dlq_id_seq
    ADDRESSEE SELECT (pid, tg_user_id, tombstoned_at) на tg_user_registry
    TEXT      SELECT на text_registry
Нет: INSERT в outbox, SELECT outbox_dlq, RETURNING, SELECT *, tx_id. Только параметры %s.
Отличие от 0009 §7 — LIMIT 1 вместо :n и created_at в списке (для expired).

Семантика:
- sent_at = обработано, не доставлено (В13): после DLQ sent_at = now() в той же транзакции;
  адресат стёрт (tombstoned_at) -> sent_at без отправки и без DLQ (В11).
- Как минимум один раз: дубль только при аварии (kill -9, падение БД) между ответом Telegram
  и commit; при SIGTERM дубля нет, кроме многочастного сообщения, прерванного во время паузы:
  после рестарта оно уйдёт с первой части.
- Одна строка = одна короткая транзакция (FOR UPDATE SKIP LOCKED). Временные сбои Telegram
  (сеть, 5xx, таймаут) и retry_after > 25 с -> выход без MARK, строка остаётся; повтор со
  следующей неотправленной части (счётчик в памяти). Строка старше 24 ч -> DLQ expired.
- SQL бота CI на настоящей БД не проверяет — только живая проверка на сервере.
- Р-11: адрес API Telegram — умолчание aiogram, своей сессии и прокси нет.
Логи: только outbox id, event_type, код ошибки, число частей. Никогда: tg_user_id, pid, текст,
payload_vars, DSN, BOT_TOKEN.

Самопроверка прав: python -m bot.outbox selfcheck.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import psycopg
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramNotFound,
    TelegramRetryAfter,
    TelegramServerError,
    TelegramUnauthorizedError,
)
from psycopg.types.json import Jsonb

from bot.render import MissingVarError, TemplateError, build_html_parts, build_plain_parts

logger = logging.getLogger(__name__)

CLAIM = (
    "SELECT id, aggregate_id, event_type, payload, created_at FROM outbox "
    "WHERE sent_at IS NULL ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED"
)
ADDRESSEE = "SELECT tg_user_id, tombstoned_at FROM tg_user_registry WHERE pid = %s"
TEXT = "SELECT text FROM text_registry WHERE key = %s"
MARK = "UPDATE outbox SET sent_at = now() WHERE id = %s AND sent_at IS NULL"
TO_DLQ = "INSERT INTO outbox_dlq (original_id, payload, error) VALUES (%s, %s, %s)"

IDLE_SECONDS = 2
DB_RETRY_SECONDS = 5
BACKOFF_MAX_SECONDS = 300
RETRY_AFTER_INLINE_MAX = 25  # retry_after <= 25 с — ждём внутри транзакции (У1)
EXPIRE_AFTER = timedelta(hours=24)
REQUEST_TIMEOUT = 20

# Исходы обработки одной строки.
IDLE, DONE, NET_RETRY, LATER, STOPPED = "idle", "done", "net_retry", "later", "stopped"


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _pause(stop: asyncio.Event, seconds: float) -> bool:
    """Пауза, прерываемая stop. True — пришёл stop."""
    if stop.is_set():
        return True
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
        return True
    except asyncio.TimeoutError:
        return False


class _Rollback(Exception):
    """Выйти из транзакции без MARK (строка остаётся в outbox)."""

    def __init__(self, outcome: str, delay: float = 0) -> None:
        super().__init__(outcome)
        self.outcome = outcome
        self.delay = delay


class _Final(Exception):
    """Окончательная ошибка строки -> DLQ с кодом."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class OutboxWorker:
    def __init__(self, bot, stop: asyncio.Event) -> None:
        self.bot = bot
        self.stop = stop
        self.sent: dict[int, int] = {}  # {outbox_id: число отправленных частей}
        self.plain: set[int] = set()  # строки, перешедшие на plain после «can't parse entities»
        self.net_failures = 0

    def _forget(self, oid: int) -> None:
        self.sent.pop(oid, None)
        self.plain.discard(oid)

    def next_backoff(self) -> int:
        delay = min(BACKOFF_MAX_SECONDS, 2 ** self.net_failures)
        self.net_failures += 1
        return delay

    async def _mark(self, conn, oid: int, event_type: str) -> None:
        cur = await conn.execute(MARK, (oid,))
        if cur.rowcount == 0:
            logger.warning("outbox %s %s: MARK не изменил строку (rowcount=0)", oid, event_type)
        self._forget(oid)

    async def _dlq(self, conn, oid: int, event_type: str, payload, code: str) -> None:
        await conn.execute(TO_DLQ, (oid, Jsonb(payload), code))
        logger.warning("outbox %s %s: dlq %s", oid, event_type, code)
        await self._mark(conn, oid, event_type)

    async def process_one(self, conn) -> tuple[str, float]:
        """Одна строка в одной транзакции -> (исход, пауза для LATER)."""
        try:
            async with conn.transaction():
                cur = await conn.execute(CLAIM)
                row = await cur.fetchone()
                if row is None:
                    return IDLE, 0
                oid, aggregate_id, event_type, payload, created_at = row
                try:
                    await self._deliver(conn, oid, aggregate_id, event_type, payload, created_at)
                except _Final as exc:
                    await self._dlq(conn, oid, event_type, payload, exc.code)
                return DONE, 0
        except _Rollback as rb:
            return rb.outcome, rb.delay

    async def _deliver(self, conn, oid, aggregate_id, event_type, payload, created_at) -> None:
        # 2. Срок жизни строки.
        if _now() - created_at > EXPIRE_AFTER:
            raise _Final("expired")
        # 3. Конверт.
        if not isinstance(payload, dict):
            raise _Final("bad_payload")
        text_id = payload.get("text_id")
        variables = payload.get("payload_vars", {})
        if not isinstance(text_id, str) or not text_id or not isinstance(variables, dict):
            raise _Final("bad_payload")
        tier = payload.get("tier")
        # 4. pid — до любого SQL с адресом (Н1).
        try:
            pid = uuid.UUID(aggregate_id)
        except (ValueError, TypeError, AttributeError):
            raise _Final("bad_aggregate_id") from None
        # 5. Адресат; стёртому — ничего не шлём (Н2, В11).
        cur = await conn.execute(ADDRESSEE, (pid,))
        addressee = await cur.fetchone()
        if addressee is None:
            raise _Final("addressee_not_found")
        tg_user_id, tombstoned_at = addressee
        if tombstoned_at is not None:
            logger.info("outbox %s %s: skipped: tombstoned", oid, event_type)
            await self._mark(conn, oid, event_type)
            return
        # 6. Текст.
        cur = await conn.execute(TEXT, (text_id,))
        text_row = await cur.fetchone()
        if text_row is None:
            raise _Final("text_not_found")
        template = text_row[0]
        try:
            if oid in self.plain:
                raise TemplateError("plain после can't parse entities")
            parts, parse_mode = build_html_parts(template, variables, tier), "HTML"
        except MissingVarError:
            raise _Final("missing_var") from None
        except TemplateError:
            try:
                parts, parse_mode = build_plain_parts(template, variables, tier), None
            except MissingVarError:
                raise _Final("missing_var") from None
            except TemplateError:
                raise _Final("template_broken") from None
        # 7. Части по очереди, со следующей неотправленной.
        idx = self.sent.get(oid, 0)
        while idx < len(parts):
            try:
                await self.bot.send_message(
                    chat_id=tg_user_id,
                    text=parts[idx],
                    parse_mode=parse_mode,
                    request_timeout=REQUEST_TIMEOUT,
                )
            except TelegramRetryAfter as exc:
                wait = exc.retry_after
                if wait > RETRY_AFTER_INLINE_MAX:
                    self.sent[oid] = idx
                    logger.warning("outbox %s %s: retry_after %s с — вне транзакции", oid, event_type, wait)
                    raise _Rollback(LATER, wait) from None
                logger.warning("outbox %s %s: retry_after %s с", oid, event_type, wait)
                if await _pause(self.stop, wait):
                    raise _Rollback(STOPPED) from None
                continue
            except TelegramUnauthorizedError:
                raise
            except (TelegramNetworkError, TelegramServerError, asyncio.TimeoutError) as exc:
                self.sent[oid] = idx
                logger.warning("outbox %s %s: временная ошибка %s", oid, event_type, type(exc).__name__)
                raise _Rollback(NET_RETRY) from None
            except TelegramBadRequest as exc:
                if parse_mode == "HTML" and "can't parse entities" in (exc.message or "").lower():
                    logger.warning("outbox %s %s: can't parse entities -> plain", oid, event_type)
                    self.plain.add(oid)
                    try:
                        parts, parse_mode = build_plain_parts(template, variables, tier), None
                    except (MissingVarError, TemplateError):
                        raise _Final("template_broken") from None
                    idx = 0
                    continue
                raise _Final("tg_bad_request") from None
            except TelegramForbiddenError:
                raise _Final("tg_forbidden") from None
            except TelegramNotFound:
                raise _Final("tg_not_found") from None
            except TelegramAPIError:
                raise _Final("tg_api_error") from None
            self.net_failures = 0
            idx += 1
            self.sent[oid] = idx
        # 8. Все части ушли.
        await self._mark(conn, oid, event_type)
        logger.info("outbox %s %s: sent, parts=%s", oid, event_type, len(parts))

    async def run(self, connect) -> None:
        """Главный цикл. connect() -> psycopg.AsyncConnection (autocommit=True)."""
        logger.info("outbox: воркер стартовал")
        while not self.stop.is_set():
            conn = None
            try:
                conn = await connect()
                while not self.stop.is_set():
                    outcome, delay = await self.process_one(conn)
                    if outcome == STOPPED:
                        return
                    if outcome == IDLE:
                        delay = IDLE_SECONDS
                    elif outcome == NET_RETRY:
                        delay = self.next_backoff()
                    elif outcome == DONE:
                        continue
                    if await _pause(self.stop, delay):
                        return
            except TelegramUnauthorizedError:
                logger.error("outbox: Telegram отклонил BOT_TOKEN (Unauthorized) — воркер остановлен")
                return
            except psycopg.OperationalError as exc:
                logger.warning("outbox: БД недоступна (%s), переподключение через %s с",
                               type(exc).__name__, DB_RETRY_SECONDS)
            except Exception as exc:  # noqa: BLE001 — неожиданная ошибка не должна убить воркер молча
                logger.error("outbox: неожиданная ошибка %s, повтор через %s с",
                             type(exc).__name__, DB_RETRY_SECONDS)
            finally:
                if conn is not None:
                    try:
                        await conn.close()
                    except Exception:  # noqa: BLE001
                        pass
            if await _pause(self.stop, DB_RETRY_SECONDS):
                return
        logger.info("outbox: воркер остановлен")


async def _connect(dsn: str):
    return await psycopg.AsyncConnection.connect(dsn, autocommit=True)


async def run_worker(bot, dsn: str, stop: asyncio.Event, connect=None) -> None:
    worker = OutboxWorker(bot, stop)
    await worker.run(connect or (lambda: _connect(dsn)))


# --- Самопроверка прав: python -m bot.outbox selfcheck ---

WHOAMI = "SELECT session_user, current_user, pg_has_role(session_user, 'app_bot', 'MEMBER')"
DENIED_CHECKS = (
    ("consent_events", "SELECT pid FROM consent_events LIMIT 1"),
    ("outbox SELECT *", "SELECT * FROM outbox LIMIT 1"),
)


async def selfcheck(conn) -> int:
    cur = await conn.execute(WHOAMI)
    session_user, current_user, member = await cur.fetchone()
    print(f"session_user = {session_user}")
    print(f"current_user = {current_user}")
    print(f"pg_has_role(session_user, 'app_bot', 'MEMBER') = {'t' if member else 'f'}")
    ok = bool(member)
    for label, sql in DENIED_CHECKS:
        try:
            async with conn.transaction(force_rollback=True):
                await conn.execute(sql)
        except psycopg.errors.InsufficientPrivilege:
            print(f"{label}: denied OK")
        else:
            print(f"{label}: FAIL (запрос прошёл)")
            ok = False
    print("selfcheck: OK" if ok else "selfcheck: FAIL")
    return 0 if ok else 1


async def _selfcheck_main(dsn: str) -> int:
    try:
        conn = await _connect(dsn)
    except psycopg.Error as exc:
        print(f"selfcheck: нет подключения к БД ({type(exc).__name__})")
        return 1
    try:
        return await selfcheck(conn)
    finally:
        await conn.close()


def main(argv: list[str]) -> int:
    if argv != ["selfcheck"]:
        print("использование: python -m bot.outbox selfcheck")
        return 2
    from bot.config import ConfigError, parse_database_url

    try:
        dsn = parse_database_url(os.environ)
    except ConfigError as exc:
        print(f"selfcheck: {exc}")
        return 1
    if not dsn:
        print("selfcheck: BOT_DATABASE_URL пуст — доставка выключена")
        return 1
    return asyncio.run(_selfcheck_main(dsn))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
