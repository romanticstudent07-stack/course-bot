#!/usr/bin/env python3
"""tools/unpack.py — раскладывает «пакет» из чата по файлам репозитория.

Формат пакета (обычный текст; текст вне блоков игнорируется):
    ===== FILE: apps/api/app/example.py =====
    <полный текст файла>
    ===== END =====
    ===== DELETE: apps/api/app/old.py =====

Запуск из корня репо (в Codespaces):
    python3 tools/unpack.py .tmp/bundle.txt           # проверить и записать
    python3 tools/unpack.py --check .tmp/bundle.txt   # только проверить
    python3 tools/unpack.py --selftest                # самопроверка скрипта

Сначала проверяется ВЕСЬ пакет. Любая ошибка → не записывается ни один файл.
"""
import argparse
import re
import sys
from pathlib import Path

FILE_RE = re.compile(r"^===== FILE: (.+) =====$")
DELETE_RE = re.compile(r"^===== DELETE: (.+) =====$")
END_LINE = "===== END ====="

ALLOWED_DIRS = ("apps/", "packages/", "infra/", "tools/", "docs/", ".devcontainer/")
ALLOWED_FILES = {
    "AGENT-BRIEF.md", "AGENTS.md", "CONTEXT.md", "README.md",
    ".env.example", ".gitignore", ".editorconfig", ".genspark/rules.md",
}
FORBIDDEN_DIRS = ("docs/architecture/", ".github/", ".githooks/")

PLACEHOLDER_LINES = {"...", "…", "# ...", "# …", "// ...", "// …", "/* ... */", "<!-- ... -->"}
PLACEHOLDER_PHRASES = (
    "остальное без изменений", "остальной код без изменений", "без изменений ниже",
    "rest of the file", "rest unchanged", "code unchanged", "existing code",
)
NO_PLACEHOLDER_CHECK = {"tools/unpack.py"}  # сам скрипт содержит эти фразы в списках


class BundleError(Exception):
    pass


def check_path(p):
    """Текст ошибки или None, если путь разрешён."""
    if not p or p != p.strip():
        return "пустой путь или пробелы по краям"
    if "\\" in p or p.startswith("/") or re.match(r"^[A-Za-z]:", p):
        return "нужен путь от корня репо через / (без C:\\ и без / в начале)"
    parts = p.split("/")
    if any(x in ("", ".", "..") for x in parts):
        return "в пути есть '..', '.' или '//'"
    if p.startswith(FORBIDDEN_DIRS):
        return "запрещённая папка (docs/architecture/, .github/, .githooks/)"
    name = parts[-1]
    if name != ".env.example" and (name == ".env" or name.startswith(".env.") or name.endswith(".env")):
        return "файлы .env запрещены (разрешён только .env.example)"
    if p in ALLOWED_FILES or p.startswith(ALLOWED_DIRS):
        return None
    return "путь вне разрешённого списка"


def parse(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    items = []  # (вид, путь, текст, номер строки)
    cur_path, cur_start, buf = None, 0, []
    for no, line in enumerate(text.split("\n"), 1):
        s = line.rstrip()
        if cur_path is None:
            m = FILE_RE.match(s)
            if m:
                cur_path, cur_start, buf = m.group(1), no, []
                continue
            m = DELETE_RE.match(s)
            if m:
                items.append(("delete", m.group(1), None, no))
                continue
            if s == END_LINE:
                raise BundleError(f"строка {no}: END без FILE")
        else:
            if s == END_LINE:
                items.append(("file", cur_path, "\n".join(buf) + "\n", cur_start))
                cur_path = None
                continue
            if FILE_RE.match(s) or DELETE_RE.match(s):
                raise BundleError(f"строка {no}: новый блок, а FILE со строки {cur_start} не закрыт END")
            buf.append(line)
    if cur_path is not None:
        raise BundleError(f"FILE со строки {cur_start} ({cur_path}) не закрыт {END_LINE} — пакет обрезан?")
    if not items:
        raise BundleError("в пакете нет ни одного блока FILE/DELETE — проверь метки")
    return items


def validate(items, root, allow_placeholder):
    errors, seen = [], set()
    for kind, path, body, no in items:
        err = check_path(path)
        if err:
            errors.append(f"строка {no}: {path}: {err}")
            continue
        if path in seen:
            errors.append(f"строка {no}: {path}: путь повторяется в пакете")
        seen.add(path)
        target = root / path
        if kind == "delete":
            if not target.is_file():
                errors.append(f"строка {no}: {path}: удалять нечего — файла нет")
            continue
        if target.is_dir():
            errors.append(f"строка {no}: {path}: это папка, а не файл")
        if allow_placeholder or path in NO_PLACEHOLDER_CHECK:
            continue
        for i, bl in enumerate(body.split("\n"), no + 1):
            t = bl.strip()
            if t in PLACEHOLDER_LINES or any(ph in t.lower() for ph in PLACEHOLDER_PHRASES):
                errors.append(f"строка {i}: {path}: похоже на заглушку вместо кода: {t[:60]!r}")
    return errors


def apply(items, root):
    for kind, path, body, _ in items:
        target = root / path
        if kind == "delete":
            target.unlink()
            print(f"  удалён:  {path}")
            continue
        existed = target.exists()
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8", newline="\n") as f:
            f.write(body)
        print(f"  {'изменён' if existed else 'новый  '}: {path}")


def selftest():
    ok = True

    def expect(cond, name):
        nonlocal ok
        print(("OK    " if cond else "FAIL  ") + name)
        ok = ok and cond

    for p in ["apps/api/app/x.py", "docs/STATE.md", ".env.example", "apps/api/.env.example",
              "AGENTS.md", ".devcontainer/devcontainer.json", "tools/check.sh"]:
        expect(check_path(p) is None, "разрешён: " + p)
    for p in ["docs/architecture/a.md", ".github/workflows/ci.yml", ".githooks/pre-commit",
              ".env", "apps/api/.env.local", "prod.env", "../x.py", "/etc/passwd",
              "apps\\api\\x.py", "C:/x.py", "random.txt", "apps//x.py"]:
        expect(check_path(p) is not None, "запрещён: " + p)
    good = "\n".join(["заметка вне блоков", "===== FILE: tools/a.py =====", "print(1)",
                      "===== END =====", "===== DELETE: tools/b.py ====="])
    items = parse(good)
    expect(len(items) == 2 and items[0][2] == "print(1)\n", "разбор FILE + DELETE")
    for bad, name in [("===== FILE: tools/a.py =====\nprint(1)\n", "ловит незакрытый FILE"),
                      ("просто текст", "ловит пустой пакет"),
                      ("===== END =====", "ловит END без FILE")]:
        try:
            parse(bad)
            expect(False, name)
        except BundleError:
            expect(True, name)
    ph = parse("===== FILE: tools/a.py =====\nx = 1\n...\n===== END =====")
    expect(any("заглушку" in e for e in validate(ph, Path("."), False)), "ловит заглушку '...'")
    print("САМОПРОВЕРКА ПРОЙДЕНА" if ok else "САМОПРОВЕРКА НЕ ПРОЙДЕНА")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="Раскладка пакета из чата по файлам репо")
    ap.add_argument("bundle", nargs="?", help="файл пакета, обычно .tmp/bundle.txt")
    ap.add_argument("--check", action="store_true", help="только проверить, ничего не писать")
    ap.add_argument("--allow-placeholder", action="store_true", help="не искать заглушки")
    ap.add_argument("--selftest", action="store_true", help="самопроверка скрипта")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.bundle:
        ap.error("укажи файл пакета: python3 tools/unpack.py .tmp/bundle.txt")
    root = Path.cwd()
    if not (root / ".git").exists():
        print("ОШИБКА: запускай из корня репо (там, где папка .git): cd /workspaces/course-bot")
        return 2
    try:
        items = parse(Path(a.bundle).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        print(f"ОШИБКА: нет файла {a.bundle}")
        return 2
    except BundleError as e:
        print(f"ОШИБКА В ПАКЕТЕ: {e}")
        return 1
    errors = validate(items, root, a.allow_placeholder)
    if errors:
        print("ПАКЕТ ОТКЛОНЁН, ничего не записано:")
        for e in errors:
            print("  - " + e)
        print("Отправь этот список в чат КОДЕР — он пришлёт исправленный пакет.")
        return 1
    n_files = sum(1 for it in items if it[0] == "file")
    n_del = len(items) - n_files
    if a.check:
        print(f"ПАКЕТ В ПОРЯДКЕ: файлов {n_files}, удалений {n_del} (--check: ничего не записано)")
        return 0
    apply(items, root)
    print(f"ГОТОВО: файлов {n_files}, удалений {n_del}. Сверь список с «Files changed» в PR.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
