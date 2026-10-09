"""apps/api/app/texts.py — text_registry: seed-файлы, загрузчик, чтение для участника (1d).

Источники: build/build-order.md (Уровень 1, п.3), config-schemas/text_registry.schema.json
(копия: apps/api/config/text_registry.schema.json), normative/I4-wave-d.md §1.
Расхождения схемы, контракта и И4 — docs/DEFECTS-FOUND.md, D-14.

Seed: apps/api/config/texts/<домен>.json — один файл на домен (И4 per_domain_files),
каждый файл — отдельный документ по схеме. В репо только заглушки «[ЗАГЛУШКА] …» до 0-Б.

Загрузчик (из /app в контейнере):
    python -m app.texts load
  0. DSN — Settings.migrations_dsn(): MIGRATIONS_DATABASE_URL → DATABASE_URL → POSTGRES_*
     (B-3a-2). DSN не печатается. Эндпоинты /texts — через get_db_session (DATABASE_URL).
  1. Читает все config/texts/*.json, проверяет каждый схемой (Draft 2020-12),
     ищет дубли ключей между файлами.
  2. Ошибка → exit 1, в БД ничего не пишется.
  3. Успех → одна транзакция INSERT … ON CONFLICT (key) DO UPDATE,
     registry_version = version файла. Лишние ключи в БД не удаляются — только список.
  Вывод: «загружено N, обновлено M, лишних в БД K».

Чтение: get_texts_for_participant — аудитория «участник» (И4: без общего render();
других аудиторий пока нет). notes наружу не отдаются.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import TextRegistry

API_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = API_DIR / "config"
SCHEMA_PATH = CONFIG_DIR / "text_registry.schema.json"
TEXTS_DIR = CONFIG_DIR / "texts"

# Шаблон ключа СХЕМЫ (решение Автора, D-14). Один на API, загрузчик и CHECK миграции 0003.
KEY_PATTERN = r"^(B2|B4|B5|B7|B9|B10|B14|B15|B16|legal)\.[a-z][a-z0-9_]*$"


class SeedError(Exception):
    """Seed не прошёл проверку. Сообщение — список ошибок по строкам."""


@dataclass(frozen=True)
class SeedEntry:
    key: str
    tone: str
    legal_status: str
    text: str
    plurals_ru: dict[str, str] | None
    notes: str | None
    registry_version: str
    source: str  # имя файла seed


@dataclass(frozen=True)
class LoadResult:
    inserted: int
    updated: int
    extra: list[str]  # ключи в БД, которых нет в seed (не удаляются)


@dataclass(frozen=True)
class ParticipantText:
    """Текст для участника (Mini App). Без notes."""

    key: str
    tone: str
    legal_status: str
    text: str
    plurals_ru: dict[str, str] | None


def _validator(schema_path: Path) -> Draft202012Validator:
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
    except (OSError, ValueError) as exc:
        raise SeedError(f"{schema_path.name}: схема не прочитана ({type(exc).__name__})") from None
    except SchemaError as exc:
        raise SeedError(f"{schema_path.name}: схема неверна: {exc.message}") from None
    return Draft202012Validator(schema)


def load_seed(texts_dir: Path = TEXTS_DIR, schema_path: Path = SCHEMA_PATH) -> list[SeedEntry]:
    """Прочитать и проверить все seed-файлы. Любая ошибка → SeedError со всеми ошибками."""
    validator = _validator(schema_path)
    files = sorted(texts_dir.glob("*.json"))
    if not files:
        raise SeedError(f"в {texts_dir} нет файлов *.json")

    errors: list[str] = []
    entries: list[SeedEntry] = []
    seen: dict[str, str] = {}
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            errors.append(f"{path.name}: не прочитан как JSON ({type(exc).__name__})")
            continue
        file_errors = sorted(
            validator.iter_errors(data), key=lambda e: [str(p) for p in e.absolute_path]
        )
        if file_errors:
            for err in file_errors:
                where = "/".join(str(p) for p in err.absolute_path) or "(корень)"
                errors.append(f"{path.name}: {where}: {err.message}")
            continue
        for item in data["entries"]:
            key = item["key"]
            if key in seen:
                errors.append(f"{path.name}: ключ {key} уже есть в {seen[key]}")
                continue
            seen[key] = path.name
            entries.append(
                SeedEntry(
                    key=key,
                    tone=item["tone"],
                    legal_status=item["legal_status"],
                    text=item["text"],
                    plurals_ru=item.get("plurals_ru"),
                    notes=item.get("notes"),
                    registry_version=data["version"],
                    source=path.name,
                )
            )
    if errors:
        raise SeedError("\n".join(errors))
    return entries


_UPSERT_SQL = text(
    """
    INSERT INTO text_registry
        (key, tone, legal_status, text, plurals_ru, notes, registry_version)
    VALUES
        (:key, :tone, :legal_status, :text, CAST(:plurals_ru AS jsonb), :notes, :registry_version)
    ON CONFLICT (key) DO UPDATE SET
        tone = EXCLUDED.tone,
        legal_status = EXCLUDED.legal_status,
        text = EXCLUDED.text,
        plurals_ru = EXCLUDED.plurals_ru,
        notes = EXCLUDED.notes,
        registry_version = EXCLUDED.registry_version,
        updated_at = now()
    RETURNING (xmax = 0) AS inserted
    """
)


def write_entries(engine: Engine, entries: Sequence[SeedEntry]) -> LoadResult:
    """Одна транзакция: upsert всех записей. Ошибка → откат, в БД ничего не меняется."""
    inserted = updated = 0
    with engine.begin() as conn:
        for e in entries:
            was_inserted = conn.execute(
                _UPSERT_SQL,
                {
                    "key": e.key,
                    "tone": e.tone,
                    "legal_status": e.legal_status,
                    "text": e.text,
                    "plurals_ru": (
                        None if e.plurals_ru is None
                        else json.dumps(e.plurals_ru, ensure_ascii=False)
                    ),
                    "notes": e.notes,
                    "registry_version": e.registry_version,
                },
            ).scalar_one()
            if was_inserted:
                inserted += 1
            else:
                updated += 1
        db_keys = set(conn.execute(text("SELECT key FROM text_registry")).scalars())
    extra = sorted(db_keys - {e.key for e in entries})
    return LoadResult(inserted=inserted, updated=updated, extra=extra)


def get_texts_for_participant(session: Session, keys: Sequence[str]) -> dict[str, ParticipantText]:
    """Тексты для участника по ключам: {key: текст}. Отсутствующих ключей в ответе нет."""
    if not keys:
        return {}
    rows = session.execute(
        select(
            TextRegistry.key,
            TextRegistry.tone,
            TextRegistry.legal_status,
            TextRegistry.body,
            TextRegistry.plurals_ru,
        ).where(TextRegistry.key.in_(list(keys)))
    ).all()
    return {
        r.key: ParticipantText(
            key=r.key,
            tone=r.tone,
            legal_status=r.legal_status,
            text=r.body,
            plurals_ru=r.plurals_ru,
        )
        for r in rows
    }


Writer = Callable[[Sequence[SeedEntry]], LoadResult]


def _write_to_configured_db(entries: Sequence[SeedEntry]) -> LoadResult:
    """Загрузчик пишет под Settings.migrations_dsn() (B-3a-2). DSN не печатается."""
    from app.config import get_settings
    from app.db.session import get_engine

    settings = get_settings()
    engine = get_engine(settings.model_copy(update={"database_url": settings.migrations_dsn()}))
    return write_entries(engine, entries)


def run_load(
    texts_dir: Path = TEXTS_DIR,
    schema_path: Path = SCHEMA_PATH,
    writer: Writer = _write_to_configured_db,
) -> int:
    """Проверить seed и записать в БД. Код выхода: 0 — успех, 1 — ошибка."""
    try:
        entries = load_seed(texts_dir, schema_path)
    except SeedError as exc:
        print("ОШИБКА: seed не прошёл проверку:", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        print("В БД ничего не записано.", file=sys.stderr)
        return 1
    try:
        result = writer(entries)
    except SQLAlchemyError as exc:
        # Текст исключения не печатаем: в нём может быть адрес БД.
        print(
            f"ОШИБКА БД: {type(exc).__name__}. Транзакция откатилась, в БД ничего не записано.",
            file=sys.stderr,
        )
        return 1
    print(
        f"загружено {result.inserted}, обновлено {result.updated}, "
        f"лишних в БД {len(result.extra)}"
    )
    if result.extra:
        print("лишние ключи (не удалены): " + ", ".join(result.extra))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.texts", description="text_registry")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("load", help="проверить config/texts/*.json и загрузить в text_registry")
    args = parser.parse_args(argv)
    if args.command == "load":
        return run_load()
    return 2


if __name__ == "__main__":
    sys.exit(main())
