"""cities-1: проверка данных apps/api/config/onboarding/cities.csv — без БД.

Файл генерирует tools/build_cities.py (запускает Автор), руками не правится.
Нет файла — тест падает, не пропускается.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

CITIES_PATH = Path(__file__).resolve().parents[1] / "config" / "onboarding" / "cities.csv"

RU_TZ = {
    "Europe/Kaliningrad",
    "Europe/Moscow",
    "Europe/Samara",
    "Asia/Yekaterinburg",
    "Asia/Omsk",
    "Asia/Novosibirsk",
    "Asia/Irkutsk",
    "Asia/Yakutsk",
    "Asia/Vladivostok",
    "Asia/Magadan",
    "Asia/Kamchatka",
}


@pytest.fixture(scope="module")
def table() -> list[list[str]]:
    if not CITIES_PATH.is_file():
        pytest.fail(f"нет {CITIES_PATH} — запусти python3 tools/build_cities.py")
    with CITIES_PATH.open(encoding="utf-8", newline="") as f:
        return list(csv.reader(f))


@pytest.fixture(scope="module")
def rows(table) -> list[list[str]]:
    return table[1:]


def test_header_fields_and_count(table, rows):
    assert table[0] == ["city", "region", "tz"]
    assert b"\r" not in CITIES_PATH.read_bytes()
    for row in rows:
        assert len(row) == 3, row
        assert all(field.strip() for field in row), row
    assert 1000 <= len(rows) <= 1300, len(rows)


def test_every_tz_opens_with_zoneinfo(rows):
    for tz in {row[2] for row in rows}:
        ZoneInfo(tz)


def test_tz_set_is_exactly_11_russian_zones(rows):
    assert {row[2] for row in rows} == RU_TZ


def test_yakutia_has_at_least_two_zones(rows):
    zones = {row[2] for row in rows if "Якути" in row[1]}
    assert len(zones) >= 2, zones


def test_no_duplicate_city_region(rows):
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for row in rows:
        counts[(row[0], row[1])] += 1
    dups = [key for key, n in counts.items() if n > 1]
    assert not dups, dups


@pytest.mark.parametrize(
    ("city", "tz"),
    [
        ("Москва", "Europe/Moscow"),
        ("Калининград", "Europe/Kaliningrad"),
        ("Петропавловск-Камчатский", "Asia/Kamchatka"),
    ],
)
def test_known_cities(rows, city, tz):
    found = {row[2] for row in rows if row[0] == city}
    assert found == {tz}, (city, found)
