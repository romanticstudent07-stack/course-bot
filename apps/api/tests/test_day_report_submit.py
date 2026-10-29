"""POST /day/report/submit (iter2-api-2b): П-31, идемпотентность (В15), вердикты, замок.

С БД — только CI. Проверки заголовка X-Client-Op-Id (422) — без БД, через TestClient
(api_client: фейковый BOT_TOKEN, недоступная БД; rate_limit подменён).
"""
import logging
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app import day_clock
from app.day_content import get_day_content
from app.day_keys import dsa, key_day_done, key_day_queue, key_day_report
from app.day_report import params_hash
from app.projector import run_once
from app.rate_limit import rate_limit
from app.routers.day import (
    DayReportIn,
    enter_day_by_test_flag,
    post_day_report_submit,
    read_day_current,
    submit_day_report,
)
from app.routers.onboarding import register_with_consents
from app.telegram_init_data import INIT_DATA_HEADER, InitDataContext, TelegramUser
from tests.conftest import valid_init_data, wait_for_lock_waiter


# life-ops-b: «сейчас» — от фактического day_started_at после открытия дня (ревью #112, Н1):
# active_from(started, tz) + 1 ч. До открытия дня — фиксированный момент (результат проверок
# до окна от него не зависит). Реальное время запуска на тесты не влияет.
_FIXED_NOW = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
_CLOCK: dict[str, datetime] = {}


@pytest.fixture(autouse=True)
def _inside_day_window(monkeypatch):
    _CLOCK["now"] = _FIXED_NOW
    monkeypatch.setattr(day_clock, "utcnow", lambda: _CLOCK["now"])
    return _CLOCK


def _u(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc)


SUBMIT = "/miniapp/v1/day/report/submit"
WAIT_SECONDS = 10


# ------------------------------ без БД: заголовок ------------------------------


def _post(api_client, headers: dict):
    from main import app

    app.dependency_overrides[rate_limit] = lambda: None
    body = {"marks": [{"block_id": "task_1", "value": "done"}]}
    return api_client.post(SUBMIT, json=body, headers={INIT_DATA_HEADER: valid_init_data(), **headers})


def _header_error(response) -> bool:
    errors = response.json()["details"]["errors"]
    return any("x-client-op-id" in [str(p).lower() for p in e["loc"]] for e in errors)


def test_without_op_id_422(api_client):
    r = _post(api_client, {})
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"
    assert _header_error(r)


def test_op_id_not_uuid_422(api_client):
    r = _post(api_client, {"X-Client-Op-Id": "not-a-uuid"})
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"
    assert _header_error(r)


def test_op_id_v1_422(api_client):
    # api-3: заголовок — только UUID v4; uuid1 → 422.
    r = _post(api_client, {"X-Client-Op-Id": str(uuid.uuid1())})
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"
    assert _header_error(r)


def test_without_init_data_401(api_client):
    r = api_client.post(SUBMIT, json={"marks": []}, headers={"X-Client-Op-Id": str(uuid.uuid4())})
    assert r.status_code == 401


# ---------------------------------- с БД ----------------------------------


def _block_ids() -> list[str]:
    return [block.block_id for block in get_day_content().get(1, 1, 1).blocks]


def _registered(engine, tg_user_id: int):
    with Session(engine) as session:
        pid = register_with_consents(session, tg_user_id, ["C0", "C1"]).participant.pid
    run_once(engine)
    return pid


def _open_day(engine, tg_user_id: int):
    pid = _registered(engine, tg_user_id)
    with Session(engine) as session:
        enter_day_by_test_flag(session, tg_user_id, True)
    run_once(engine)
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT day_started_at, tz FROM participant_state WHERE pid = :p"), {"p": pid}
        ).one()
    _CLOCK["now"] = _u(day_clock.active_from(row.day_started_at, row.tz)) + timedelta(hours=1)
    return pid, row.day_started_at


def _body(values: dict[str, str], **extra) -> DayReportIn:
    marks = [{"block_id": b, "value": v} for b, v in values.items()]
    return DayReportIn.model_validate({"marks": marks, **extra})


def _all(value: str) -> dict[str, str]:
    return {b: value for b in _block_ids()}


def _submit(engine, tg_user_id: int, op_id, body: DayReportIn):
    with Session(engine) as session:
        return submit_day_report(session, tg_user_id, op_id, body, get_day_content())


def _http_error(engine, tg_user_id: int, op_id, body: DayReportIn) -> HTTPException:
    with pytest.raises(HTTPException) as exc:
        _submit(engine, tg_user_id, op_id, body)
    return exc.value


def _scalar(engine, sql: str, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar_one()


def _events(engine, pid) -> int:
    return _scalar(
        engine,
        "SELECT count(*) FROM participant_events WHERE pid = :p AND kind = 'day_report_submitted'",
        p=pid,
    )


def _keys(engine, pid) -> int:
    return _scalar(
        engine,
        "SELECT count(*) FROM idempotency_keys WHERE key LIKE :a OR key LIKE :b OR key LIKE :c",
        a=f"day_done:{pid}:%",
        b=f"day_report:{pid}:%",
        c=f"day_queue:{pid}:%",
    )


def _key_row(engine, key: str):
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT kind, result_ref, params_hash FROM idempotency_keys WHERE key = :k"),
            {"k": key},
        ).first()


def _marks(engine, pid) -> dict[str, bool]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT block_id, value FROM day_marks WHERE pid = :p"), {"p": pid}
        ).all()
    return {row.block_id: row.value for row in rows}


def _nothing_written(engine, pid) -> bool:
    # Нет события, ключей day_done / day_report / day_queue и отметок (П-31).
    return (_events(engine, pid), _keys(engine, pid), _marks(engine, pid)) == (0, 0, {})


def test_marks_incomplete_422(db_engine):
    pid, _ = _open_day(db_engine, 9301)
    blocks = _block_ids()
    missing = {b: "done" for b in blocks[:-1]}
    stranger = {**_all("done"), "zz_not_in_day": "done"}
    repeated = DayReportIn.model_validate(
        {"marks": [{"block_id": b, "value": "done"} for b in blocks + blocks[:1]]}
    )
    for body in (_body(missing), _body(stranger), repeated):
        err = _http_error(db_engine, 9301, uuid.uuid4(), body)
        assert (err.status_code, err.detail["code"]) == (422, "MARKS_INCOMPLETE")
    assert _nothing_written(db_engine, pid)


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({"task_1": "done", "task_2": "done", "task_3": "done", "task_4": "not_done"}, "passed"),
        ({"task_1": "not_done", "task_2": "done", "task_3": "done", "task_4": "done"}, "not_passed"),
        ({"task_1": "not_done", "task_2": "not_done", "task_3": "not_done", "task_4": "not_done"}, "all_not_done"),
    ],
)
def test_submit_verdicts(db_engine, values, expected, _inside_day_window):
    assert set(values) == set(_block_ids())  # заглушка дня 1: task_1..task_4
    pid, started = _open_day(db_engine, 9302)
    op_id = uuid.uuid4()
    out = _submit(db_engine, 9302, op_id, _body(values))
    assert (out.verdict, out.queued) == (expected, True)
    done = _key_row(db_engine, key_day_done(pid, started))
    report = _key_row(db_engine, key_day_report(pid, str(op_id)))
    assert (done.kind, done.result_ref) == ("day_done", expected)
    assert (report.kind, report.result_ref) == ("day_report", expected)
    assert report.params_hash
    assert _events(db_engine, pid) == 1
    with db_engine.connect() as conn:
        event = conn.execute(
            text(
                "SELECT payload, actor FROM participant_events "
                "WHERE pid = :p AND kind = 'day_report_submitted'"
            ),
            {"p": pid},
        ).one()
    assert event.actor == "participant"
    assert event.payload == {
        "day_started_at": dsa(started),
        "verdict": expected,
        "stage_no": 1,
        "module_no": 1,
        "day_no": 1,
        # life-ops-b: passed → день 2 (есть в контенте), иначе та же позиция; next — «сейчас».
        "next_stage_no": 1,
        "next_module_no": 1,
        "next_day_no": 2 if expected == "passed" else 1,
        "next_day_started_at": dsa(_inside_day_window["now"]),
    }
    assert _marks(db_engine, pid) == {b: v == "done" for b, v in values.items()}


def test_repeat_same_op_id_same_body(db_engine):
    pid, _ = _open_day(db_engine, 9303)
    op_id = uuid.uuid4()
    first = _submit(db_engine, 9303, op_id, _body(_all("done")))
    again = _submit(db_engine, 9303, op_id, _body(dict(reversed(list(_all("done").items())))))
    assert again == first
    assert _events(db_engine, pid) == 1


def test_same_op_id_other_body_409(db_engine):
    pid, _ = _open_day(db_engine, 9304)
    op_id = uuid.uuid4()
    _submit(db_engine, 9304, op_id, _body(_all("done")))
    err = _http_error(db_engine, 9304, op_id, _body(_all("not_done")))
    assert (err.status_code, err.detail["code"]) == (409, "IDEMPOTENCY_CONFLICT")
    assert _events(db_engine, pid) == 1


def test_new_op_id_after_submit_409(db_engine):
    pid, _ = _open_day(db_engine, 9305)
    _submit(db_engine, 9305, uuid.uuid4(), _body(_all("done")))
    err = _http_error(db_engine, 9305, uuid.uuid4(), _body(_all("done")))
    assert (err.status_code, err.detail["code"]) == (409, "DAY_ALREADY_SUBMITTED")
    assert _events(db_engine, pid) == 1


def test_day_not_started_409(db_engine):
    pid = _registered(db_engine, 9306)
    err = _http_error(db_engine, 9306, uuid.uuid4(), _body(_all("done")))
    assert (err.status_code, err.detail["code"]) == (409, "DAY_NOT_STARTED")
    assert _nothing_written(db_engine, pid)


def test_tombstoned_404_nothing_written(db_engine):
    pid, _ = _open_day(db_engine, 9307)
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE tg_user_registry SET tombstoned_at = now() WHERE pid = :p"), {"p": pid}
        )
    err = _http_error(db_engine, 9307, uuid.uuid4(), _body(_all("done")))
    assert (err.status_code, err.detail["code"]) == (404, "PARTICIPANT_NOT_FOUND")
    assert _nothing_written(db_engine, pid)


def test_pid_and_day_started_at_from_body_ignored(db_engine):
    pid, started = _open_day(db_engine, 9308)
    stranger = uuid.uuid4()
    body = _body(_all("done"), pid=str(stranger), day_started_at="2001-01-01T00:00:00+00:00")
    _submit(db_engine, 9308, uuid.uuid4(), body)
    assert _key_row(db_engine, key_day_done(pid, started)) is not None
    with db_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT pid, day_started_at FROM day_marks WHERE pid = :p"), {"p": pid}
        ).all()
    assert rows and all(dsa(r.day_started_at) == dsa(started) for r in rows)
    assert _nothing_written(db_engine, stranger)


def test_p31_commit_fails_503_nothing_written(db_engine, monkeypatch):
    pid, _ = _open_day(db_engine, 9309)
    ctx = InitDataContext(user=TelegramUser(id=9309), auth_date=int(time.time()))

    def failing_commit():
        raise OperationalError("COMMIT", {}, Exception("commit failed"))

    with Session(db_engine) as session:
        monkeypatch.setattr(session, "commit", failing_commit)
        with pytest.raises(HTTPException) as exc:
            post_day_report_submit(
                _body(_all("done")), uuid.uuid4(), ctx, session, get_day_content()
            )
    assert (exc.value.status_code, exc.value.detail["code"]) == (503, "SERVICE_UNAVAILABLE")
    assert _nothing_written(db_engine, pid)


def _ctx(tg_user_id: int) -> InitDataContext:
    return InitDataContext(user=TelegramUser(id=tg_user_id), auth_date=int(time.time()))


def _fail_insert(monkeypatch, session: Session, match) -> dict[str, bool]:
    """session.execute падает OperationalError на INSERT, для которого match(stmt, params)."""
    real = session.execute
    hit = {"hit": False}

    def execute(stmt, *args, **kwargs):
        params = args[0] if args else kwargs.get("params")
        if match(str(stmt), params if isinstance(params, dict) else {}):
            hit["hit"] = True
            raise OperationalError("INSERT", {}, Exception("insert failed"))
        return real(stmt, *args, **kwargs)

    monkeypatch.setattr(session, "execute", execute)
    return hit


def _is_queue_key(sql: str, params: dict) -> bool:
    return "INSERT INTO idempotency_keys" in sql and str(params.get("key", "")).startswith(
        "day_queue:"
    )


def _is_report_event(sql: str, params: dict) -> bool:
    return "INSERT INTO participant_events" in sql


@pytest.mark.parametrize(
    ("tg_user_id", "match"), [(9312, _is_queue_key), (9313, _is_report_event)]
)
def test_p31_insert_fails_503_nothing_written(db_engine, monkeypatch, tg_user_id, match):
    # Сбой INSERT ключа day_queue / события day_report_submitted → 503, ничего не записано.
    pid, _ = _open_day(db_engine, tg_user_id)
    with Session(db_engine) as session:
        hit = _fail_insert(monkeypatch, session, match)
        with pytest.raises(HTTPException) as exc:
            post_day_report_submit(
                _body(_all("done")), uuid.uuid4(), _ctx(tg_user_id), session, get_day_content()
            )
    assert hit["hit"]
    assert (exc.value.status_code, exc.value.detail["code"]) == (503, "SERVICE_UNAVAILABLE")
    assert _nothing_written(db_engine, pid)


def test_queue_key_conflict_503_nothing_written(db_engine, _inside_day_window):
    # Н6: ключ day_queue без ON CONFLICT — конфликт → IntegrityError → rollback → 503.
    pid, _ = _open_day(db_engine, 9314)
    queue_key = key_day_queue(pid, _inside_day_window["now"])  # next_started = now (окно open)
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO idempotency_keys (key, kind, ttl) "
                "VALUES (:k, 'day_queue', CAST('3650 days' AS interval))"
            ),
            {"k": queue_key},
        )
    with Session(db_engine) as session:
        with pytest.raises(HTTPException) as exc:
            post_day_report_submit(
                _body(_all("done")), uuid.uuid4(), _ctx(9314), session, get_day_content()
            )
    assert (exc.value.status_code, exc.value.detail["code"]) == (503, "SERVICE_UNAVAILABLE")
    assert _events(db_engine, pid) == 0
    assert _marks(db_engine, pid) == {}
    assert _scalar(
        db_engine,
        "SELECT count(*) FROM idempotency_keys WHERE key LIKE :a OR key LIKE :b",
        a=f"day_done:{pid}:%",
        b=f"day_report:{pid}:%",
    ) == 0


def _race_submits(engine, tg_user_id: int, op_ids, bodies) -> dict[str, object]:
    """Два submit одного pid: commit первого придержан, пока второй не ждёт замок participant:pid
    (pg_locks + pg_blocking_pids держателя, api-3). Возвращает {"first": …, "second": …}."""
    ready = threading.Event()
    release = threading.Event()
    out: dict[str, object] = {}
    holder: dict[str, int] = {}

    def run(name: str, hold: bool, op_id, body: DayReportIn):
        with Session(engine) as session:
            if hold:
                real_commit = session.commit

                def held_commit():
                    holder["pid"] = session.execute(text("SELECT pg_backend_pid()")).scalar_one()
                    ready.set()
                    release.wait(WAIT_SECONDS)
                    real_commit()

                session.commit = held_commit
            try:
                out[name] = submit_day_report(
                    session, tg_user_id, op_id, body, get_day_content()
                )
            except Exception as exc:
                out[name] = exc

    t1 = threading.Thread(target=run, args=("first", True, op_ids[0], bodies[0]))
    t2 = threading.Thread(target=run, args=("second", False, op_ids[1], bodies[1]))
    t1.start()
    try:
        assert ready.wait(WAIT_SECONDS)
        t2.start()
        assert wait_for_lock_waiter(engine, holder["pid"])  # второй ждёт замок participant:pid
    finally:
        release.set()
    t1.join(WAIT_SECONDS)
    t2.join(WAIT_SECONDS)
    return out


def test_parallel_submits_one_200_one_409(db_engine):
    pid, _ = _open_day(db_engine, 9310)
    out = _race_submits(
        db_engine, 9310, (uuid.uuid4(), uuid.uuid4()), (_body(_all("done")), _body(_all("done")))
    )
    assert out["first"].verdict == "passed"
    second = out["second"]
    assert isinstance(second, HTTPException)
    assert (second.status_code, second.detail["code"]) == (409, "DAY_ALREADY_SUBMITTED")
    assert _events(db_engine, pid) == 1


def test_double_tap_same_op_id_both_200(db_engine):
    # api-3: двойной тап — один op_id и одно тело в обоих потоках → оба 200 passed.
    pid, _ = _open_day(db_engine, 9315)
    op_id = uuid.uuid4()
    out = _race_submits(db_engine, 9315, (op_id, op_id), (_body(_all("done")), _body(_all("done"))))
    assert out["first"].verdict == "passed"
    assert out["second"].verdict == "passed"
    assert _events(db_engine, pid) == 1
    assert _keys(db_engine, pid) == 3  # day_done, day_report, day_queue — по одному


def _set_report_created_at(engine, pid, op_id, created_at: datetime) -> None:
    # Только в тесте, через db_engine (владелец БД); в коде приложения UPDATE ключей нет.
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE idempotency_keys SET created_at = :t WHERE key = :k"),
            {"t": created_at, "k": key_day_report(pid, str(op_id))},
        )


def _state_started(engine, pid):
    return _scalar(engine, "SELECT day_started_at FROM participant_state WHERE pid = :p", p=pid)


def test_repeat_within_ttl_after_projector_200(db_engine):
    # В15: повтор в пределах 1 ч — 200 тем же телом, даже после сдвига дня проектором.
    pid, started = _open_day(db_engine, 9316)
    op_id = uuid.uuid4()
    first = _submit(db_engine, 9316, op_id, _body(_all("done")))
    run_once(db_engine)
    assert dsa(_state_started(db_engine, pid)) != dsa(started)
    _set_report_created_at(db_engine, pid, op_id, _CLOCK["now"] - timedelta(minutes=30))
    assert _submit(db_engine, 9316, op_id, _body(_all("done"))) == first
    assert _events(db_engine, pid) == 1


def test_repeat_after_ttl_409(db_engine):
    # api-3: срок ключа day_report (1 ч) истёк → 409 IDEMPOTENCY_CONFLICT.
    pid, started = _open_day(db_engine, 9317)
    op_id = uuid.uuid4()
    _submit(db_engine, 9317, op_id, _body(_all("done")))
    run_once(db_engine)
    assert dsa(_state_started(db_engine, pid)) != dsa(started)
    _set_report_created_at(db_engine, pid, op_id, _CLOCK["now"] - timedelta(hours=2))
    err = _http_error(db_engine, 9317, op_id, _body(_all("done")))
    assert (err.status_code, err.detail["code"]) == (409, "IDEMPOTENCY_CONFLICT")
    assert _events(db_engine, pid) == 1
    assert _keys(db_engine, pid) == 3


def test_result_ref_outside_verdicts_503(db_engine, caplog):
    # ревью #103 п.5: битый result_ref → 503, WARNING без pid и op_id, ничего не записано.
    pid, _ = _open_day(db_engine, 9318)
    op_id = uuid.uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO idempotency_keys (key, kind, ttl, result_ref, params_hash, created_at) "
                "VALUES (:k, 'day_report', CAST('1 hour' AS interval), 'bogus', :h, :t)"
            ),
            {
                "k": key_day_report(pid, str(op_id)),
                "h": params_hash(list(_all("done").items())),
                "t": _CLOCK["now"],
            },
        )
    with caplog.at_level(logging.WARNING, logger="app.routers.day"):
        err = _http_error(db_engine, 9318, op_id, _body(_all("done")))
    assert (err.status_code, err.detail["code"]) == (503, "SERVICE_UNAVAILABLE")
    warnings = [
        r for r in caplog.records if r.name == "app.routers.day" and r.levelno == logging.WARNING
    ]
    assert warnings
    for record in warnings:
        message = record.getMessage()
        assert str(pid) not in message and str(op_id) not in message
    assert _events(db_engine, pid) == 0
    assert _marks(db_engine, pid) == {}


def test_report_key_created_at_is_request_now(db_engine):
    # api-3: created_at ключа day_report = «сейчас» запроса (day_clock), а не DEFAULT now().
    pid, _ = _open_day(db_engine, 9319)
    op_id = uuid.uuid4()
    _submit(db_engine, 9319, op_id, _body(_all("done")))
    created_at = _scalar(
        db_engine,
        "SELECT created_at FROM idempotency_keys WHERE key = :k",
        k=key_day_report(pid, str(op_id)),
    )
    assert _u(created_at) == _u(_CLOCK["now"])


def test_lives_unchanged_and_get_submitted(db_engine):
    pid, _ = _open_day(db_engine, 9311)

    def lives():
        return _scalar(db_engine, "SELECT lives FROM participant_state WHERE pid = :p", p=pid)

    before = lives()
    _submit(db_engine, 9311, uuid.uuid4(), _body(_all("not_done")))
    run_once(db_engine)
    assert lives() == before  # Ш1: жизни не меняются ни при каком вердикте
    with Session(db_engine) as session:
        current = read_day_current(session, 9311, get_day_content(), False)
    # life-ops-b: проектор v3 сдвинул день по next_* — новый день в очереди показа.
    assert current.status == "queued"
    assert current.can_submit is False
