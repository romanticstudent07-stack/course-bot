"""tools/build_cities.py — cities-1: города РФ с IANA-поясом для анкеты (Р-16, Р-17).

Источник: github.com/hflabs/city (HFLabs / DaData.ru), лицензия CC BY-SA 4.0,
закреплён по commit SOURCE_COMMIT. Пишет apps/api/config/onboarding/cities.csv
с колонками city,region,tz (UTF-8, LF). Только stdlib.

Запуск из корня репо:
    python3 tools/build_cities.py                     # скачать источник и записать файл
    python3 tools/build_cities.py --input city.csv    # локальная копия, без сети

Печатает «sha256: <64 hex>» исходника и число записей в нём. Любая ошибка данных
(неизвестный пояс или region_type, пустой город, дубль (city, region)) — все ошибки
списком, код 1, файл не пишется. Список городов руками не править — только этим скриптом.

Город — первое непустое по порядку: settlement; city; area при area_type «г»
(городские округа, запись уровня 3, например Московская обл, г Воскресенск);
region при region_type «г» (Москва, Санкт-Петербург, Севастополь).
Пояс «UTC+N» → один IANA-пояс на смещение (OFFSET_TO_TZ), летнего времени в РФ нет.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import sys
import urllib.error
import urllib.request
from pathlib import Path

SOURCE_COMMIT = "ae661bffe572880472249097c9b29c42b09650ea"
SOURCE_URL = f"https://raw.githubusercontent.com/hflabs/city/{SOURCE_COMMIT}/city.csv"
TIMEOUT_S = 30

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = ROOT / "apps" / "api" / "config" / "onboarding" / "cities.csv"

OFFSET_TO_TZ = {
    "UTC+2": "Europe/Kaliningrad",
    "UTC+3": "Europe/Moscow",
    "UTC+4": "Europe/Samara",
    "UTC+5": "Asia/Yekaterinburg",
    "UTC+6": "Asia/Omsk",
    "UTC+7": "Asia/Novosibirsk",
    "UTC+8": "Asia/Irkutsk",
    "UTC+9": "Asia/Yakutsk",
    "UTC+10": "Asia/Vladivostok",
    "UTC+11": "Asia/Magadan",
    "UTC+12": "Asia/Kamchatka",
}

REGION_FORMAT = {
    "обл": "{r} область",
    "край": "{r} край",
    "Респ": "Республика {r}",
    "АО": "{r} автономный округ",
    "Аобл": "{r} автономная область",
    "г": "{r}",
    "Чувашия": "{r}",
}

# Слово типа уже есть в названии (например «Кемеровская область - Кузбасс») — пишем как есть.
TYPE_WORD = {
    "обл": "область",
    "край": "край",
    "Респ": "республика",
    "АО": "автономный округ",
    "Аобл": "автономная область",
}

REQUIRED_COLUMNS = {"region_type", "region", "area_type", "area", "city", "settlement", "timezone"}


class SourceError(Exception):
    pass


def read_source(path: str | None) -> bytes:
    if path:
        try:
            return Path(path).read_bytes()
        except OSError as exc:
            raise SourceError(f"не прочитать файл {path} ({exc.__class__.__name__})") from None
    try:
        with urllib.request.urlopen(SOURCE_URL, timeout=TIMEOUT_S) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        raise SourceError(f"источник ответил HTTP {exc.code}: {SOURCE_URL}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SourceError(
            f"нет связи с источником ({exc.__class__.__name__}): {SOURCE_URL}. "
            "Скачай файл вручную и запусти с --input <файл>"
        ) from None


def format_region(region_type: str, region: str) -> str | None:
    template = REGION_FORMAT.get(region_type)
    if template is None or not region:
        return None
    word = TYPE_WORD.get(region_type)
    if word and f" {word} " in f" {region.lower()} ":
        return region
    return template.format(r=region)


def pick_city(rec: dict, region_type: str, region: str) -> str:
    city = (rec["settlement"] or "").strip() or (rec["city"] or "").strip()
    if not city and (rec["area_type"] or "").strip() == "г":
        city = (rec["area"] or "").strip()
    if not city and region_type == "г":
        city = region
    return city


def build_rows(text: str) -> tuple[list[tuple[str, str, str]], int, list[str]]:
    reader = csv.DictReader(io.StringIO(text))
    missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
    if missing:
        return [], 0, ["в источнике нет колонок: " + ", ".join(sorted(missing))]
    rows: list[tuple[str, str, str]] = []
    errors: list[str] = []
    seen: dict[tuple[str, str], int] = {}
    count = 0
    for rec in reader:
        count += 1
        line = reader.line_num
        offset = (rec["timezone"] or "").strip()
        region_type = (rec["region_type"] or "").strip()
        region = (rec["region"] or "").strip()
        tz = OFFSET_TO_TZ.get(offset)
        if tz is None:
            errors.append(f"строка {line}: неизвестный пояс {offset!r}")
        region_show = format_region(region_type, region)
        if region_show is None:
            errors.append(
                f"строка {line}: неизвестный region_type {region_type!r} (region {region!r})"
            )
        city = pick_city(rec, region_type, region)
        if not city:
            errors.append(f"строка {line}: пустой город (region_type {region_type!r})")
        if tz is None or region_show is None or not city:
            continue
        key = (city, region_show)
        if key in seen:
            errors.append(f"строка {line}: дубль {key}, первая строка {seen[key]}")
            continue
        seen[key] = line
        rows.append((city, region_show, tz))
    rows.sort(key=lambda r: (r[0], r[1]))
    return rows, count, errors


def write_rows(rows: list[tuple[str, str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["city", "region", "tz"])
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Города РФ с IANA-поясом → cities.csv")
    ap.add_argument("--input", help="локальная копия city.csv (без сети)")
    args = ap.parse_args(argv)
    try:
        raw = read_source(args.input)
    except SourceError as exc:
        print(f"ОШИБКА: {exc}", file=sys.stderr)
        return 1
    print(f"sha256: {hashlib.sha256(raw).hexdigest()}")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        print("ОШИБКА: источник не в UTF-8", file=sys.stderr)
        return 1
    rows, count, errors = build_rows(text)
    print(f"записей в источнике: {count}")
    if errors:
        print(f"ОШИБКИ ({len(errors)}), cities.csv не записан:", file=sys.stderr)
        for err in errors:
            print("  - " + err, file=sys.stderr)
        return 1
    write_rows(rows, OUTPUT_PATH)
    zones = {r[2] for r in rows}
    print(f"cities.csv: {len(rows)} строк, поясов {len(zones)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
