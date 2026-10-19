"""app/day_report.py (iter2-api-2b): вердикт, полнота набора, params_hash. Без БД.

Плюс чистые части роутера и проектора: DayReportIn (граница длины, лишние поля)
и report_day_started_at (разбор payload day_report_submitted).
"""
import pytest
from pydantic import ValidationError

from app.day_content import Block, Day
from app.day_report import (
    VERDICT_ALL_NOT_DONE,
    VERDICT_NOT_PASSED,
    VERDICT_PASSED,
    marks_complete,
    params_hash,
    verdict,
)
from app.projector import report_day_started_at
from app.routers.day import MAX_REPORT_MARKS, DayReportIn


def _block(block_id: str, critical: bool) -> Block:
    return Block(
        block_id=block_id,
        critical=critical,
        title_key=f"B9.test_{block_id}_title",
        help_key=f"B9.test_{block_id}_help",
    )


def _day(min_optional: int, critical: int = 2, optional: int = 2) -> Day:
    blocks = tuple(_block(f"c{i}", True) for i in range(critical)) + tuple(
        _block(f"o{i}", False) for i in range(optional)
    )
    return Day(
        stage_no=1, module_no=1, day_no=1, min_optional=min_optional, blocks=blocks, source="test"
    )


def _done(day: Day, *done_ids: str) -> dict[str, bool]:
    return {block.block_id: block.block_id in done_ids for block in day.blocks}


@pytest.mark.parametrize("min_optional", [0, 1, 2])
def test_all_not_done(min_optional):
    day = _day(min_optional)
    assert verdict(day, _done(day)) == VERDICT_ALL_NOT_DONE


def test_passed_all_done():
    day = _day(1)
    assert verdict(day, _done(day, "c0", "c1", "o0", "o1")) == VERDICT_PASSED


def test_passed_exactly_min_optional():
    day = _day(1)
    assert verdict(day, _done(day, "c0", "c1", "o1")) == VERDICT_PASSED


def test_not_passed_critical_missing():
    day = _day(1)
    assert verdict(day, _done(day, "c0", "o0", "o1")) == VERDICT_NOT_PASSED


def test_not_passed_optional_below_min():
    day = _day(2)
    assert verdict(day, _done(day, "c0", "c1", "o0")) == VERDICT_NOT_PASSED


def test_min_optional_zero():
    day = _day(0)
    assert verdict(day, _done(day, "c0", "c1")) == VERDICT_PASSED
    assert verdict(day, _done(day, "o0")) == VERDICT_NOT_PASSED


def test_missing_mark_counts_as_not_done():
    day = _day(0)
    assert verdict(day, {"c0": True}) == VERDICT_NOT_PASSED
    assert verdict(day, {}) == VERDICT_ALL_NOT_DONE


def test_marks_complete():
    day = _day(1)
    assert marks_complete(day, ["o1", "c0", "o0", "c1"])
    assert not marks_complete(day, ["c0", "c1", "o0"])  # недостающий
    assert not marks_complete(day, ["c0", "c1", "o0", "o1", "zz"])  # лишний
    assert not marks_complete(day, ["c0", "c1", "o0", "o0"])  # повтор вместо o1
    assert not marks_complete(day, ["c0", "c1", "o0", "o1", "o1"])  # повтор сверх набора
    assert not marks_complete(day, [])


def test_params_hash_order_independent():
    a = params_hash([("c0", "done"), ("c1", "not_done"), ("o0", "done")])
    b = params_hash([("o0", "done"), ("c0", "done"), ("c1", "not_done")])
    assert a == b
    assert len(a) == 64 and int(a, 16) >= 0


def test_params_hash_depends_on_values_and_blocks():
    base = params_hash([("c0", "done"), ("c1", "done")])
    assert params_hash([("c0", "done"), ("c1", "not_done")]) != base
    assert params_hash([("c0", "done"), ("c2", "done")]) != base
    assert params_hash([("c0", "done")]) != base


def test_report_body_validation():
    with pytest.raises(ValidationError):
        DayReportIn.model_validate({"marks": [{"block_id": "Bad-Id", "value": "done"}]})
    with pytest.raises(ValidationError):
        DayReportIn.model_validate({"marks": [{"block_id": "ok", "value": "maybe"}]})
    with pytest.raises(ValidationError):
        DayReportIn.model_validate({})
    too_many = [{"block_id": f"b{i}", "value": "done"} for i in range(MAX_REPORT_MARKS + 1)]
    with pytest.raises(ValidationError):
        DayReportIn.model_validate({"marks": too_many})
    body = DayReportIn.model_validate(
        {
            "marks": [{"block_id": "ok", "value": "done"}],
            "pid": "x",
            "day_started_at": "2001-01-01T00:00:00+00:00",
        }
    )
    assert not hasattr(body, "pid") and not hasattr(body, "day_started_at")


def test_report_day_started_at_payload():
    ts = "2026-10-19T10:00:00+00:00"
    assert report_day_started_at({"day_started_at": ts, "verdict": "passed"}) == ts
    assert report_day_started_at('{"day_started_at": "' + ts + '"}') == ts
    assert report_day_started_at({}) is None
    assert report_day_started_at({"day_started_at": ""}) is None
    assert report_day_started_at({"day_started_at": 123}) is None
    assert report_day_started_at([ts]) is None
    assert report_day_started_at("not json") is None
