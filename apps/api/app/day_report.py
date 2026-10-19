"""Отчёт дня (iter2-api-2b): вердикт, проверка набора отметок, params_hash. Чистые функции.

verdict (docs/tasks/iter2-api-2b.md, §7; решения В18, Ш1):
  - all_not_done — все блоки not_done (§3.16: жизнь цела, день не засчитан);
  - passed — все критические блоки done и done среди некритических ≥ min_optional;
  - иначе not_passed.
Жизни здесь не меняются ни при каком вердикте (life_op — iter2-api-3).

marks_complete: набор block_id отчёта равен блокам дня — без лишних, недостающих и повторов.
params_hash: sha256 (hex) канонического JSON отсортированного списка [block_id, value];
порядок marks в теле на хеш не влияет.
БД, время и логи здесь не используются.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping

from app.day_content import Day

VERDICT_PASSED = "passed"
VERDICT_NOT_PASSED = "not_passed"
VERDICT_ALL_NOT_DONE = "all_not_done"
VERDICTS: tuple[str, ...] = (VERDICT_PASSED, VERDICT_NOT_PASSED, VERDICT_ALL_NOT_DONE)

VALUE_DONE = "done"
VALUE_NOT_DONE = "not_done"


def marks_complete(day: Day, block_ids: Iterable[str]) -> bool:
    """True — каждый блок дня ровно один раз и ничего лишнего."""
    ids = list(block_ids)
    expected = {block.block_id for block in day.blocks}
    return len(ids) == len(set(ids)) and set(ids) == expected


def verdict(day: Day, done: Mapping[str, bool]) -> str:
    """done: block_id → True (done) / False (not_done). Блок без отметки считается not_done."""
    if not any(done.get(block.block_id, False) for block in day.blocks):
        return VERDICT_ALL_NOT_DONE
    critical_ok = all(done.get(block.block_id, False) for block in day.blocks if block.critical)
    optional_done = sum(
        1 for block in day.blocks if not block.critical and done.get(block.block_id, False)
    )
    if critical_ok and optional_done >= day.min_optional:
        return VERDICT_PASSED
    return VERDICT_NOT_PASSED


def params_hash(marks: Iterable[tuple[str, str]]) -> str:
    """sha256 канонического JSON: [[block_id, value], …], отсортировано, без пробелов."""
    canonical = sorted([str(block_id), str(value)] for block_id, value in marks)
    raw = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
