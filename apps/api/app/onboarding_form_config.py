"""Конфиг анкеты онбординга — файлы в репо (api-i3-2; Р-16, Р-17).

Два файла, один источник для клиента и для проверки на сервере:
  - apps/api/config/onboarding/form.json — version, вопрос и коды самочувствия, границы веса,
    fallback_title и 11 поясов «Моего города нет» (порядок — как в файле);
  - apps/api/config/onboarding/cities.csv (cities-1) — city, region, tz.

  - load_onboarding_form_config(form_path, cities_path) → OnboardingFormConfig (неизменяемый)
    или OnboardingFormConfigError;
  - get_onboarding_form_config() — кеш (functools.lru_cache); пути берутся из FORM_CONFIG_PATH
    и CITIES_PATH в момент вызова (тесты подменяют константы и вызывают cache_clear).

Проверки: коды самочувствия уникальны и по WELLBEING_CODE_PATTERN; ровно 11 поясов, каждый
открывается ZoneInfo, без повторов; каждый tz из cities.csv есть среди 11 поясов.
allowed_tz — множество допустимых поясов (на сервер уходит только tz; город не хранится).
create_app (main.py) вызывает get_onboarding_form_config(): битый файл → api не стартует.
Тексты — заглушки (репо публичный); в лог не пишутся.
"""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.db.models import WEIGHT_MAX_KG, WEIGHT_MIN_KG, WELLBEING_CODE_PATTERN

_CONFIG_DIR: Path = Path(__file__).resolve().parents[1] / "config" / "onboarding"
FORM_CONFIG_PATH: Path = _CONFIG_DIR / "form.json"
CITIES_PATH: Path = _CONFIG_DIR / "cities.csv"

TIMEZONES_COUNT = 11
MAX_VERSION_LEN = 64
MAX_TZ_LEN = 64
CITIES_HEADER: tuple[str, ...] = ("city", "region", "tz")

_CODE_RE = re.compile(WELLBEING_CODE_PATTERN)


class OnboardingFormConfigError(Exception):
    """form.json или cities.csv отсутствует, не читается или не проходит проверки."""


@dataclass(frozen=True)
class WellbeingOption:
    code: str
    text: str


@dataclass(frozen=True)
class FallbackTimezone:
    tz: str
    city: str


@dataclass(frozen=True)
class OnboardingFormConfig:
    version: str
    wellbeing_question: str
    wellbeing: tuple[WellbeingOption, ...]
    weight_min: float
    weight_max: float
    weight_step: float
    fallback_title: str
    timezones: tuple[FallbackTimezone, ...]
    # (город, регион, индекс пояса в timezones)
    cities: tuple[tuple[str, str, int], ...]
    allowed_tz: frozenset[str]
    wellbeing_codes: frozenset[str]


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OnboardingFormConfigError(f"{where}: пустой или не строка")
    return value


def _list(value: Any, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise OnboardingFormConfigError(f"{where}: не список")
    return value


def _dict(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise OnboardingFormConfigError(f"{where}: не объект")
    return value


def _check_zone(tz: str, where: str) -> None:
    if len(tz) > MAX_TZ_LEN:
        raise OnboardingFormConfigError(f"{where}: длиннее {MAX_TZ_LEN}")
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise OnboardingFormConfigError(f"{where}: ZoneInfo не открывает пояс") from None


def _parse_form(data: Any) -> dict[str, Any]:
    root = _dict(data, "form.json")

    version = root.get("version")
    if not isinstance(version, str) or not version.strip() or len(version.strip()) > MAX_VERSION_LEN:
        raise OnboardingFormConfigError("version: пустая, не строка или длиннее 64")

    raw_wellbeing = _list(root.get("wellbeing"), "wellbeing")
    if not raw_wellbeing:
        raise OnboardingFormConfigError("wellbeing: пустой список")
    wellbeing: list[WellbeingOption] = []
    for i, raw in enumerate(raw_wellbeing):
        item = _dict(raw, f"wellbeing[{i}]")
        code = item.get("code")
        if not isinstance(code, str) or not _CODE_RE.fullmatch(code):
            raise OnboardingFormConfigError(f"wellbeing[{i}].code: не по шаблону")
        wellbeing.append(WellbeingOption(code=code, text=_text(item.get("text"), f"wellbeing[{i}].text")))
    codes = [w.code for w in wellbeing]
    if len(set(codes)) != len(codes):
        raise OnboardingFormConfigError("wellbeing: повтор code")

    weight = _dict(root.get("weight"), "weight")
    wmin, wmax, wstep = weight.get("min"), weight.get("max"), weight.get("step")
    if not (_is_number(wmin) and _is_number(wmax) and _is_number(wstep)):
        raise OnboardingFormConfigError("weight: min / max / step не числа")
    # Границы — те же, что проверяет сервер (модель тела и CHECK 0014).
    if wmin != WEIGHT_MIN_KG or wmax != WEIGHT_MAX_KG or not 0 < wstep <= 1:
        raise OnboardingFormConfigError("weight: ожидается {min: 30, max: 300, 0 < step ≤ 1}")

    raw_tz = _list(root.get("timezones"), "timezones")
    if len(raw_tz) != TIMEZONES_COUNT:
        raise OnboardingFormConfigError(f"timezones: ожидается {TIMEZONES_COUNT}")
    timezones: list[FallbackTimezone] = []
    for i, raw in enumerate(raw_tz):
        item = _dict(raw, f"timezones[{i}]")
        tz = _text(item.get("tz"), f"timezones[{i}].tz")
        _check_zone(tz, f"timezones[{i}].tz")
        timezones.append(FallbackTimezone(tz=tz, city=_text(item.get("city"), f"timezones[{i}].city")))
    tz_list = [t.tz for t in timezones]
    if len(set(tz_list)) != len(tz_list):
        raise OnboardingFormConfigError("timezones: повтор tz")

    return {
        "version": version.strip(),
        "wellbeing_question": _text(root.get("wellbeing_question"), "wellbeing_question"),
        "wellbeing": tuple(wellbeing),
        "weight_min": wmin,
        "weight_max": wmax,
        "weight_step": wstep,
        "fallback_title": _text(root.get("fallback_title"), "fallback_title"),
        "timezones": tuple(timezones),
    }


def _parse_cities(raw: str, tz_index: dict[str, int]) -> tuple[tuple[str, str, int], ...]:
    reader = csv.reader(io.StringIO(raw))
    header = next(reader, None)
    if header is None or tuple(h.strip() for h in header) != CITIES_HEADER:
        raise OnboardingFormConfigError("cities.csv: ожидается заголовок city,region,tz")
    cities: list[tuple[str, str, int]] = []
    for n, row in enumerate(reader, start=2):
        if not row:
            continue
        if len(row) != len(CITIES_HEADER):
            raise OnboardingFormConfigError(f"cities.csv строка {n}: ожидается 3 поля")
        city, region, tz = (v.strip() for v in row)
        if not city or not region or not tz:
            raise OnboardingFormConfigError(f"cities.csv строка {n}: пустое поле")
        if tz not in tz_index:
            raise OnboardingFormConfigError(f"cities.csv строка {n}: пояса нет в timezones")
        cities.append((city, region, tz_index[tz]))
    if not cities:
        raise OnboardingFormConfigError("cities.csv: нет строк")
    return tuple(cities)


def _read(path: Path, name: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise OnboardingFormConfigError(
            f"{name}: не удалось прочитать файл ({type(exc).__name__})"
        ) from None


def load_onboarding_form_config(form_path: Path, cities_path: Path) -> OnboardingFormConfig:
    """Прочитать и проверить form.json и cities.csv; любая проблема → OnboardingFormConfigError."""
    try:
        data = json.loads(_read(form_path, "form.json"))
    except ValueError:
        raise OnboardingFormConfigError("form.json: файл не JSON") from None
    form = _parse_form(data)
    tz_index = {t.tz: i for i, t in enumerate(form["timezones"])}
    cities = _parse_cities(_read(cities_path, "cities.csv"), tz_index)
    return OnboardingFormConfig(
        **form,
        cities=cities,
        allowed_tz=frozenset(tz_index),
        wellbeing_codes=frozenset(w.code for w in form["wellbeing"]),
    )


@lru_cache
def get_onboarding_form_config() -> OnboardingFormConfig:
    """Конфиг из FORM_CONFIG_PATH и CITIES_PATH (пути читаются в момент вызова; кешируется)."""
    return load_onboarding_form_config(FORM_CONFIG_PATH, CITIES_PATH)
