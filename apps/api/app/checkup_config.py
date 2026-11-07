"""Конфиг Чек-Апа — JSON-файл в репо (api-i3-1).

До Панели (И6) конфиг — файл apps/api/config/checkup/checkup.v1.json (Л2); его version
пишется в measurements_log.checkup_config_version. Связь балл ↔ зона — только здесь (Р-7):
зоны green 0–9, yellow 10–22, red 23–45, границы включительные.

  - load_checkup_config(path) → CheckupConfig (неизменяемый) или CheckupConfigError;
  - get_checkup_config() — кеш (functools.lru_cache); путь берётся из CHECKUP_CONFIG_PATH
    в момент вызова (тесты подменяют константу и вызывают cache_clear);
  - score_and_zone(answers, cfg) → (score, zone_id) — чистая функция.

create_app (main.py) вызывает get_checkup_config(): битый конфиг → api не стартует.
legal_status здесь только проверяется на допустимое значение; гейт Legal — не здесь.
Тексты конфига — заглушки (репо публичный); в лог они не пишутся.
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

CHECKUP_CONFIG_PATH: Path = (
    Path(__file__).resolve().parents[1] / "config" / "checkup" / "checkup.v1.json"
)

SCALE_MIN = 0
SCALE_MAX = 3
BLOCKS_COUNT = 4
QUESTIONS_COUNT = 15
ZONE_IDS: tuple[str, ...] = ("green", "yellow", "red")
SCORE_MAX = QUESTIONS_COUNT * SCALE_MAX  # 45
MAX_VERSION_LEN = 64
LEGAL_STATUSES: tuple[str, ...] = ("approved", "pre-legal-review")


class CheckupConfigError(Exception):
    """Конфиг Чек-Апа отсутствует, не JSON или не проходит проверки."""


@dataclass(frozen=True)
class CheckupBlock:
    id: int
    title: str


@dataclass(frozen=True)
class CheckupQuestion:
    id: str
    block: int
    text: str


@dataclass(frozen=True)
class CheckupZone:
    id: str
    min: int
    max: int
    title: str
    text: str
    legal_status: str


@dataclass(frozen=True)
class CheckupConfig:
    version: str
    scale_min: int
    scale_max: int
    blocks: tuple[CheckupBlock, ...]
    questions: tuple[CheckupQuestion, ...]
    zones: tuple[CheckupZone, ...]
    disclaimer: str


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CheckupConfigError(f"{where}: пустой или не строка")
    return value


def _list(value: Any, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise CheckupConfigError(f"{where}: не список")
    return value


def _dict(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CheckupConfigError(f"{where}: не объект")
    return value


def _parse(data: Any) -> CheckupConfig:
    root = _dict(data, "конфиг")

    version = root.get("version")
    if not isinstance(version, str) or not version.strip() or len(version.strip()) > MAX_VERSION_LEN:
        raise CheckupConfigError("version: пустая, не строка или длиннее 64")

    scale = _dict(root.get("scale"), "scale")
    if not (
        _is_int(scale.get("min"))
        and _is_int(scale.get("max"))
        and scale["min"] == SCALE_MIN
        and scale["max"] == SCALE_MAX
    ):
        raise CheckupConfigError("scale: ожидается {min: 0, max: 3}")

    raw_blocks = _list(root.get("blocks"), "blocks")
    if len(raw_blocks) != BLOCKS_COUNT:
        raise CheckupConfigError(f"blocks: ожидается {BLOCKS_COUNT}")
    blocks: list[CheckupBlock] = []
    for i, raw in enumerate(raw_blocks):
        item = _dict(raw, f"blocks[{i}]")
        if not _is_int(item.get("id")):
            raise CheckupConfigError(f"blocks[{i}].id: не целое")
        blocks.append(CheckupBlock(id=item["id"], title=_text(item.get("title"), f"blocks[{i}].title")))
    block_ids = [b.id for b in blocks]
    if len(set(block_ids)) != len(block_ids):
        raise CheckupConfigError("blocks: повтор id")

    raw_questions = _list(root.get("questions"), "questions")
    if len(raw_questions) != QUESTIONS_COUNT:
        raise CheckupConfigError(f"questions: ожидается {QUESTIONS_COUNT}")
    questions: list[CheckupQuestion] = []
    for i, raw in enumerate(raw_questions):
        item = _dict(raw, f"questions[{i}]")
        qid = item.get("id")
        if not isinstance(qid, str) or not qid.strip():
            raise CheckupConfigError(f"questions[{i}].id: пустой или не строка")
        block = item.get("block")
        if not _is_int(block) or block not in block_ids:
            raise CheckupConfigError(f"questions[{i}].block: нет такого блока")
        questions.append(
            CheckupQuestion(id=qid, block=block, text=_text(item.get("text"), f"questions[{i}].text"))
        )
    question_ids = [q.id for q in questions]
    if len(set(question_ids)) != len(question_ids):
        raise CheckupConfigError("questions: повтор id")

    raw_zones = _list(root.get("zones"), "zones")
    if len(raw_zones) != len(ZONE_IDS):
        raise CheckupConfigError(f"zones: ожидается {len(ZONE_IDS)}")
    zones: list[CheckupZone] = []
    for i, raw in enumerate(raw_zones):
        item = _dict(raw, f"zones[{i}]")
        if item.get("id") != ZONE_IDS[i]:
            raise CheckupConfigError("zones: ожидается порядок green, yellow, red")
        zmin, zmax = item.get("min"), item.get("max")
        if not (_is_int(zmin) and _is_int(zmax)):
            raise CheckupConfigError(f"zones[{i}]: min / max не целые")
        if zmin > zmax:
            raise CheckupConfigError(f"zones[{i}]: min > max")
        if i == 0 and zmin != SCALE_MIN * QUESTIONS_COUNT:
            raise CheckupConfigError("zones: первая min ≠ 0")
        if i > 0 and zmin != zones[-1].max + 1:
            raise CheckupConfigError(f"zones[{i}]: дырка или перекрытие с предыдущей зоной")
        legal_status = item.get("legal_status")
        if legal_status not in LEGAL_STATUSES:
            raise CheckupConfigError(f"zones[{i}].legal_status: недопустимое значение")
        zones.append(
            CheckupZone(
                id=item["id"],
                min=zmin,
                max=zmax,
                title=_text(item.get("title"), f"zones[{i}].title"),
                text=_text(item.get("text"), f"zones[{i}].text"),
                legal_status=legal_status,
            )
        )
    if zones[-1].max != SCORE_MAX:
        raise CheckupConfigError(f"zones: последняя max ≠ {SCORE_MAX}")

    return CheckupConfig(
        version=version.strip(),
        scale_min=SCALE_MIN,
        scale_max=SCALE_MAX,
        blocks=tuple(blocks),
        questions=tuple(questions),
        zones=tuple(zones),
        disclaimer=_text(root.get("disclaimer"), "disclaimer"),
    )


def load_checkup_config(path: Path) -> CheckupConfig:
    """Прочитать и проверить конфиг; любая проблема → CheckupConfigError."""
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise CheckupConfigError(f"не удалось прочитать файл ({type(exc).__name__})") from None
    try:
        data = json.loads(raw)
    except ValueError:
        raise CheckupConfigError("файл не JSON") from None
    return _parse(data)


@lru_cache
def get_checkup_config() -> CheckupConfig:
    """Конфиг из CHECKUP_CONFIG_PATH (путь читается в момент вызова; результат кешируется)."""
    return load_checkup_config(CHECKUP_CONFIG_PATH)


def score_and_zone(answers: Sequence[int], cfg: CheckupConfig) -> tuple[int, str]:
    """(балл, id зоны) по ответам. Чистая функция.

    Ответы проверены роутером (15 целых 0–3); здесь повторная защита — ValueError.
    """
    if len(answers) != len(cfg.questions):
        raise ValueError("число ответов не совпадает с числом вопросов")
    for value in answers:
        if not _is_int(value) or not cfg.scale_min <= value <= cfg.scale_max:
            raise ValueError("ответ вне шкалы")
    score = sum(answers)
    for zone in cfg.zones:
        if zone.min <= score <= zone.max:
            return score, zone.id
    raise ValueError("балл вне зон")
