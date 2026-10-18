"""Контент дня (iter2-api-1): загрузка, проверка, поиск дня по позиции.

Файлы: apps/api/content/module_<M>/day_<NN>.json; схема — apps/api/content/day.schema.json
(JSON Schema draft 2020-12, additionalProperties: false). Путь — от каталога apps/api
(как API_DIR в texts.py); в Docker-образ api каталог попадает (COPY . /app/).

Проверки сверх схемы:
  - block_id в дне уникальны;
  - есть хотя бы один критический блок (critical: true);
  - min_optional не больше числа некритических блоков;
  - day_no совпадает с номером в имени файла (day_01.json → 1);
  - позиция (stage_no, module_no, day_no) не повторяется в разных файлах
    (иначе поиск дня неоднозначен).
Любая ошибка → DayContentError; в лог ERROR — путь файла и причина.
create_app (main.py) вызывает load_day_content() до создания приложения:
битый контент → api не стартует.

Тексты (названия и справки блоков) здесь не хранятся — только ключи text_registry
title_key / help_key; заглушки — config/texts/day.json.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

logger = logging.getLogger(__name__)

API_DIR = Path(__file__).resolve().parents[1]
CONTENT_DIR = API_DIR / "content"
SCHEMA_FILE = CONTENT_DIR / "day.schema.json"

MODULE_DIR_RE = re.compile(r"^module_(\d+)$")
DAY_FILE_RE = re.compile(r"^day_(\d{2,})\.json$")


class DayContentError(Exception):
    """Контент дня битый или отсутствует. С таким контентом api не стартует."""


@dataclass(frozen=True)
class Block:
    block_id: str
    critical: bool
    title_key: str
    help_key: str


@dataclass(frozen=True)
class Day:
    stage_no: int
    module_no: int
    day_no: int
    min_optional: int
    blocks: tuple[Block, ...]
    source: str  # module_<M>/day_<NN>.json


class DayContent:
    """Все дни курса, поиск по (stage_no, module_no, day_no)."""

    def __init__(self, days: dict[tuple[int, int, int], Day]) -> None:
        self._days = dict(days)

    def get(self, stage_no: int, module_no: int, day_no: int) -> Day | None:
        return self._days.get((stage_no, module_no, day_no))

    def days(self) -> list[Day]:
        return [self._days[pos] for pos in sorted(self._days)]

    def __len__(self) -> int:
        return len(self._days)


def _fail(path: Path, reason: str) -> DayContentError:
    message = f"контент дня: {path}: {reason}"
    logger.error("%s", message)
    return DayContentError(message)


def _validator(schema_file: Path) -> Draft202012Validator:
    try:
        schema = json.loads(schema_file.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
    except FileNotFoundError:
        raise _fail(schema_file, "файл схемы не найден") from None
    except json.JSONDecodeError as exc:
        raise _fail(schema_file, f"не JSON ({exc.msg}, строка {exc.lineno})") from None
    except SchemaError as exc:
        raise _fail(schema_file, f"схема некорректна: {exc.message}") from None
    return Draft202012Validator(schema)


def _check_day(
    data: Any, path: Path, file_day_no: int, source: str, validator: Draft202012Validator
) -> Day:
    errors = sorted(
        validator.iter_errors(data), key=lambda e: [str(p) for p in e.absolute_path]
    )
    if errors:
        err = errors[0]
        where = "/".join(str(p) for p in err.absolute_path) or "(корень)"
        raise _fail(path, f"схема: {where}: {err.message}")

    blocks = tuple(
        Block(
            block_id=b["block_id"],
            critical=b["critical"],
            title_key=b["title_key"],
            help_key=b["help_key"],
        )
        for b in data["blocks"]
    )
    ids = [b.block_id for b in blocks]
    repeated = sorted({i for i in ids if ids.count(i) > 1})
    if repeated:
        raise _fail(path, "block_id повторяется: " + ", ".join(repeated))
    if not any(b.critical for b in blocks):
        raise _fail(path, "нет критического блока (critical: true)")
    optional = sum(1 for b in blocks if not b.critical)
    if data["min_optional"] > optional:
        raise _fail(
            path,
            f"min_optional={data['min_optional']} больше числа некритических блоков ({optional})",
        )
    if data["day_no"] != file_day_no:
        raise _fail(
            path, f"day_no={data['day_no']} не совпадает с именем файла (день {file_day_no})"
        )
    return Day(
        stage_no=data["stage_no"],
        module_no=data["module_no"],
        day_no=data["day_no"],
        min_optional=data["min_optional"],
        blocks=blocks,
        source=source,
    )


_cache: DayContent | None = None


def load_day_content(content_dir: Path | None = None) -> DayContent:
    """Загрузить и проверить все дни. Ошибка → DayContentError (и ERROR в лог).

    content_dir=None — рабочий каталог apps/api/content; результат кэшируется
    для get_day_content(). Другой каталог (тесты) кэш не трогает.
    Схема всегда из SCHEMA_FILE.
    """
    global _cache
    use_default = content_dir is None
    root = CONTENT_DIR if use_default else Path(content_dir)
    validator = _validator(SCHEMA_FILE)
    if not root.is_dir():
        raise _fail(root, "каталог контента не найден")

    days: dict[tuple[int, int, int], Day] = {}
    for module_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        if MODULE_DIR_RE.match(module_dir.name) is None:
            raise _fail(module_dir, "имя каталога не module_<номер>")
        for path in sorted(module_dir.glob("*.json")):
            match = DAY_FILE_RE.match(path.name)
            if match is None:
                raise _fail(path, "имя файла не day_<NN>.json")
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise _fail(path, f"не JSON ({exc.msg}, строка {exc.lineno})") from None
            source = f"{module_dir.name}/{path.name}"
            day = _check_day(data, path, int(match.group(1)), source, validator)
            pos = (day.stage_no, day.module_no, day.day_no)
            if pos in days:
                raise _fail(path, f"позиция {pos} повторяется (уже в {days[pos].source})")
            days[pos] = day

    if not days:
        raise _fail(root, "нет ни одного дня (module_<M>/day_<NN>.json)")
    content = DayContent(days)
    if use_default:
        _cache = content
    logger.info("контент дня: загружено дней %d", len(content))
    return content


def get_day_content() -> DayContent:
    """Зависимость FastAPI: контент, загруженный при старте (или загрузить сейчас)."""
    if _cache is None:
        return load_day_content()
    return _cache
